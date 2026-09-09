"""Command line interface.

Exit codes are part of the contract:
  0 — the match met the threshold
  1 — it did not (so ``skillsift match ... || notify-me`` works)
  2 — the tool could not run (bad file, bad taxonomy, bad arguments)
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .config import Settings
from .documents import DocumentError, read_document
from .matcher import MIN_CORPUS_FOR_IDF, Matcher
from .report import (
    Painter,
    colour_enabled,
    render_applications,
    render_gaps,
    render_match,
    to_json,
)
from .skills import SkillIndex, TaxonomyError
from .store import Status, Store
from .text import content_terms, inverse_document_frequency, tokenise

EXIT_OK = 0
EXIT_BELOW_THRESHOLD = 1
EXIT_ERROR = 2


def build_parser() -> argparse.ArgumentParser:
    # Global options live on a parent parser that every subcommand inherits, so
    # both "skillsift --db X list" and "skillsift list --db X" work. Requiring
    # them before the subcommand is the kind of papercut that makes a tool feel
    # hostile the first time you use it.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--db", type=Path, help="path to the SQLite database")
    common.add_argument("--taxonomy", type=Path, help="path to an alternative skills.yml")
    common.add_argument("--no-color", action="store_true", help="disable coloured output")

    parser = argparse.ArgumentParser(
        prog="skillsift",
        parents=[common],
        description="Score a CV against job descriptions and track applications.",
    )
    parser.add_argument("--version", action="version", version=f"skillsift {__version__}")

    sub = parser.add_subparsers(dest="command", required=True)

    match = sub.add_parser("match", help="score a CV against a job description", parents=[common])
    match.add_argument("cv", type=Path)
    match.add_argument("jd", type=Path)
    match.add_argument("--title", help="job title (defaults to the JD filename)")
    match.add_argument("--company", default="")
    match.add_argument("--url", default="")
    match.add_argument("--save", action="store_true", help="store the posting and result")
    match.add_argument("--json", action="store_true", dest="as_json")
    match.set_defaults(func=cmd_match)

    listing = sub.add_parser("list", help="list tracked applications", parents=[common])
    listing.add_argument("--status", help="filter by status")
    listing.set_defaults(func=cmd_list)

    status = sub.add_parser("status", help="update the status of an application", parents=[common])
    status.add_argument("posting_id", type=int)
    status.add_argument("new_status")
    status.add_argument("--note", help="replace the note attached to this application")
    status.set_defaults(func=cmd_status)

    gaps = sub.add_parser(
        "gaps", help="required skills missing across the most postings", parents=[common]
    )
    gaps.add_argument("--limit", type=int, default=10)
    gaps.set_defaults(func=cmd_gaps)

    skills = sub.add_parser(
        "skills", help="list the skills the taxonomy knows about", parents=[common]
    )
    skills.add_argument("--category")
    skills.set_defaults(func=cmd_skills)

    serve = sub.add_parser("serve", help="run the web interface", parents=[common])
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=5000)
    serve.add_argument("--debug", action="store_true")
    serve.set_defaults(func=cmd_serve)

    return parser


def _settings(args: argparse.Namespace) -> Settings:
    settings = Settings.from_env()
    overrides = {}
    if args.db:
        overrides["database_path"] = args.db
    if args.taxonomy:
        overrides["taxonomy_path"] = args.taxonomy
    if overrides:
        settings = Settings(**{**settings.__dict__, **overrides})
    settings.ensure_dirs()
    return settings


def _painter(args: argparse.Namespace) -> Painter:
    return Painter(False if args.no_color else colour_enabled())


# --------------------------------------------------------------------- commands


def cmd_match(args: argparse.Namespace, settings: Settings) -> int:
    cv_text = read_document(args.cv)
    jd_text = read_document(args.jd)
    title = args.title or args.jd.stem.replace("-", " ").replace("_", " ").title()

    index = SkillIndex.from_file(settings.taxonomy_path)
    matcher = Matcher(index, settings)
    job = matcher.profile_job(title, jd_text)
    candidate = matcher.profile_candidate(args.cv.stem, cv_text)

    with Store(settings.database_path) as store:
        corpus = store.all_posting_texts()
        idf = None
        if len(corpus) >= MIN_CORPUS_FOR_IDF:
            idf = inverse_document_frequency([content_terms(tokenise(t)) for t in corpus])

        result = matcher.match(job, candidate, idf)

        if args.save:
            posting_id = store.add_posting(title, jd_text, args.company, args.url)
            store.record_match(
                posting_id,
                result.score,
                [g.skill for g in result.required_gaps],
            )
            saved_note = f"Saved as posting #{posting_id}."
        else:
            saved_note = ""

    if args.as_json:
        print(to_json(result))
    else:
        print(render_match(result, settings.pass_threshold, _painter(args)))
        if saved_note:
            print(saved_note)

    return EXIT_OK if result.score >= settings.pass_threshold else EXIT_BELOW_THRESHOLD


def cmd_list(args: argparse.Namespace, settings: Settings) -> int:
    status = Status.parse(args.status) if args.status else None
    with Store(settings.database_path) as store:
        print(render_applications(store.list_applications(status), _painter(args)), end="")
    return EXIT_OK


def cmd_status(args: argparse.Namespace, settings: Settings) -> int:
    status = Status.parse(args.new_status)
    with Store(settings.database_path) as store:
        if not store.set_status(args.posting_id, status, args.note):
            print(f"No application found for posting #{args.posting_id}.", file=sys.stderr)
            return EXIT_ERROR
    print(f"Posting #{args.posting_id} is now '{status.value}'.")
    return EXIT_OK


def cmd_gaps(args: argparse.Namespace, settings: Settings) -> int:
    with Store(settings.database_path) as store:
        print(render_gaps(store.recurring_gaps(args.limit), _painter(args)), end="")
    return EXIT_OK


def cmd_skills(args: argparse.Namespace, settings: Settings) -> int:
    index = SkillIndex.from_file(settings.taxonomy_path)
    for name, skill in sorted(index.skills.items(), key=lambda kv: (kv[1].category, kv[0])):
        if args.category and skill.category != args.category:
            continue
        print(f"{skill.category:<12} {name:<20} {', '.join(skill.aliases)}")
    return EXIT_OK


def cmd_serve(args: argparse.Namespace, settings: Settings) -> int:
    from .web import create_app

    app = create_app(settings)
    app.run(host=args.host, port=args.port, debug=args.debug)
    return EXIT_OK


# ------------------------------------------------------------------ entrypoint


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        settings = _settings(args)
        return args.func(args, settings)
    except (DocumentError, TaxonomyError, ValueError) as exc:
        print(f"skillsift: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except KeyboardInterrupt:  # pragma: no cover - interactive only
        print()
        return EXIT_ERROR


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
