"""HTTP routes: a small dashboard plus a JSON endpoint."""

from __future__ import annotations

import os
from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from .. import __version__
from ..documents import DocumentError, read_document
from ..matcher import MIN_CORPUS_FOR_IDF, Matcher
from ..store import Status, Store
from ..text import content_terms, inverse_document_frequency, tokenise

bp = Blueprint("main", __name__)

MAX_TEXT_BYTES = 200_000


def _settings():
    return current_app.config["SETTINGS"]


def _matcher() -> Matcher:
    return Matcher(current_app.config["SKILL_INDEX"], _settings())


def _store() -> Store:
    return Store(_settings().database_path)


def _default_cv() -> str:
    """Pre-fill the CV box from ``SKILLSIFT_CV`` so the common case is one paste."""
    path = os.environ.get("SKILLSIFT_CV")
    if not path:
        return ""
    try:
        return read_document(Path(path))
    except DocumentError:
        return ""


def _score(title: str, jd_text: str, cv_text: str, store: Store):
    matcher = _matcher()
    corpus = store.all_posting_texts()
    idf = None
    if len(corpus) >= MIN_CORPUS_FOR_IDF:
        idf = inverse_document_frequency([content_terms(tokenise(t)) for t in corpus])
    job = matcher.profile_job(title, jd_text)
    candidate = matcher.profile_candidate("cv", cv_text)
    return matcher.match(job, candidate, idf)


@bp.get("/")
def dashboard():
    with _store() as store:
        return render_template(
            "index.html",
            applications=store.list_applications(),
            counts=store.status_counts(),
            gaps=store.recurring_gaps(8),
            statuses=list(Status),
        )


@bp.route("/match", methods=["GET", "POST"])
def match():
    if request.method == "GET":
        return render_template("match.html", cv=_default_cv(), result=None)

    cv_text = request.form.get("cv", "")
    jd_text = request.form.get("jd", "")
    title = request.form.get("title", "").strip() or "Untitled role"
    company = request.form.get("company", "").strip()
    url = request.form.get("url", "").strip()

    errors = []
    if not cv_text.strip():
        errors.append("Paste your CV.")
    if not jd_text.strip():
        errors.append("Paste the job description.")
    if len(cv_text) + len(jd_text) > MAX_TEXT_BYTES:
        errors.append("That is a lot of text — keep the two documents under 200 KB.")
    if errors:
        return render_template(
            "match.html", cv=cv_text, jd=jd_text, title=title, result=None, errors=errors
        ), 400

    with _store() as store:
        result = _score(title, jd_text, cv_text, store)
        posting_id = None
        if request.form.get("save"):
            posting_id = store.add_posting(title, jd_text, company, url)
            store.record_match(posting_id, result.score, [g.skill for g in result.required_gaps])

    return render_template(
        "match.html",
        cv=cv_text,
        jd=jd_text,
        title=title,
        result=result,
        posting_id=posting_id,
        threshold=_settings().pass_threshold,
    )


@bp.get("/postings/<int:posting_id>")
def posting(posting_id: int):
    with _store() as store:
        record = store.get_posting(posting_id)
        if record is None:
            abort(404)
        applications = {a.posting_id: a for a in store.list_applications()}
        return render_template(
            "posting.html",
            posting=record,
            application=applications.get(posting_id),
            statuses=list(Status),
        )


@bp.post("/postings/<int:posting_id>/status")
def update_status(posting_id: int):
    try:
        status = Status.parse(request.form.get("status", ""))
    except ValueError as exc:
        abort(400, str(exc))
    with _store() as store:
        if not store.set_status(posting_id, status, request.form.get("notes")):
            abort(404)
    return redirect(url_for("main.posting", posting_id=posting_id))


@bp.post("/api/match")
def api_match():
    """JSON endpoint, so the scorer can be called from a script or a browser extension."""
    payload = request.get_json(silent=True) or {}
    cv_text, jd_text = payload.get("cv", ""), payload.get("jd", "")
    if not cv_text or not jd_text:
        return jsonify(error="both 'cv' and 'jd' are required"), 400
    if len(cv_text) + len(jd_text) > MAX_TEXT_BYTES:
        return jsonify(error="payload too large"), 413

    with _store() as store:
        result = _score(payload.get("title", "Untitled role"), jd_text, cv_text, store)
    return jsonify(
        title=result.job_title,
        score=result.score,
        percentage=result.percentage,
        skill_score=result.skill_score,
        keyword_score=result.keyword_score,
        matched=[r.skill for r in result.matched],
        missing_required=[g.skill for g in result.required_gaps],
        missing_preferred=[g.skill for g in result.preferred_gaps],
        warnings=result.warnings,
    )


@bp.get("/api/health")
def health():
    """Liveness probe: confirms the taxonomy loaded and the database is reachable."""
    with _store() as store:
        store.status_counts()
    return jsonify(
        status="ok",
        version=__version__,
        skills=len(current_app.config["SKILL_INDEX"]),
    )
