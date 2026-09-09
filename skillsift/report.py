"""Rendering results for a terminal.

Colour is opt-out and auto-disabled when stdout is not a TTY or NO_COLOR is
set, so piping to a file or into CI produces clean text.
"""

from __future__ import annotations

import dataclasses
import json
import os
import sys
from collections.abc import Iterable, Sequence
from typing import Any

from .documents import Emphasis
from .matcher import MatchResult
from .store import Application

RESET = "\033[0m"
_COLOURS = {"red": "\033[31m", "yellow": "\033[33m", "green": "\033[32m",
            "grey": "\033[90m", "bold": "\033[1m"}


def colour_enabled(stream: Any = None) -> bool:
    stream = stream or sys.stdout
    if os.environ.get("NO_COLOR"):
        return False
    return bool(getattr(stream, "isatty", lambda: False)())


class Painter:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def __call__(self, text: str, colour: str) -> str:
        if not self.enabled or colour not in _COLOURS:
            return text
        return f"{_COLOURS[colour]}{text}{RESET}"


def score_bar(score: float, width: int = 24) -> str:
    filled = max(0, min(width, round(score * width)))
    return "█" * filled + "·" * (width - filled)


def _score_colour(score: float, threshold: float) -> str:
    if score >= threshold + 0.15:
        return "green"
    if score >= threshold:
        return "yellow"
    return "red"


def render_match(result: MatchResult, threshold: float, paint: Painter | None = None) -> str:
    paint = paint or Painter(colour_enabled())
    colour = _score_colour(result.score, threshold)
    lines: list[str] = []

    lines.append(paint(f"{result.job_title}", "bold"))
    lines.append(
        f"  {score_bar(result.score)}  "
        + paint(f"{result.percentage}%", colour)
        + paint(f"  ({result.verdict(threshold)})", "grey")
    )
    detail = f"  skills {result.skill_score:.0%}"
    if result.keyword_score is not None:
        detail += f" · keywords {result.keyword_score:.0%}"
    lines.append(paint(detail, "grey"))
    lines.append("")

    if result.matched:
        lines.append(paint("You have", "bold"))
        lines.append("  " + ", ".join(r.skill for r in result.matched))
        lines.append("")

    required = result.required_gaps
    if required:
        lines.append(paint("Missing — required", "bold"))
        for gap in required:
            lines.append("  " + paint("✗", "red") + f" {gap.skill}")
            if gap.evidence:
                lines.append(paint(f"      “{_truncate(gap.evidence, 92)}”", "grey"))
        lines.append("")

    preferred = result.preferred_gaps
    if preferred:
        lines.append(paint("Missing — nice to have", "bold"))
        lines.append("  " + ", ".join(g.skill for g in preferred))
        lines.append("")

    if result.by_category:
        lines.append(paint("By category", "bold"))
        for category, (have, total) in result.by_category.items():
            lines.append(f"  {category:<12} {have}/{total}  {score_bar(have / total, 12)}")
        lines.append("")

    if result.extras:
        lines.append(paint("On your CV but not asked for", "bold"))
        lines.append(paint("  " + ", ".join(result.extras), "grey"))
        lines.append("")

    for warning in result.warnings:
        lines.append(paint(f"! {warning}", "yellow"))

    return "\n".join(lines).rstrip() + "\n"


def render_applications(apps: Sequence[Application], paint: Painter | None = None) -> str:
    paint = paint or Painter(colour_enabled())
    if not apps:
        return "No applications tracked yet. Add one with: skillsift match CV JD --save\n"
    rows = [("ID", "SCORE", "STATUS", "ROLE", "COMPANY")]
    rows += [
        (str(a.posting_id), f"{a.score:.0%}", a.status.value, _truncate(a.title, 40),
         _truncate(a.company or "—", 24))
        for a in apps
    ]
    return _table(rows, paint) + "\n"


def render_gaps(gaps: Iterable[tuple[str, int]], paint: Painter | None = None) -> str:
    paint = paint or Painter(colour_enabled())
    gaps = list(gaps)
    if not gaps:
        return "No gaps recorded yet.\n"
    biggest = max(n for _, n in gaps)
    lines = [paint("Skills you are missing most often", "bold"), ""]
    for skill, count in gaps:
        lines.append(f"  {skill:<20} {score_bar(count / biggest, 18)} {count}")
    return "\n".join(lines) + "\n"


def to_json(result: MatchResult) -> str:
    """Machine-readable output, so the tool composes with jq and CI."""

    def encode(obj: Any) -> Any:
        if isinstance(obj, Emphasis):
            return obj.value
        if dataclasses.is_dataclass(obj):
            return dataclasses.asdict(obj)
        raise TypeError(f"not JSON serialisable: {type(obj).__name__}")

    payload = dataclasses.asdict(result)
    payload["percentage"] = result.percentage
    return json.dumps(payload, indent=2, default=encode)


def _truncate(text: str, width: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 1] + "…"


def _table(rows: Sequence[Sequence[str]], paint: Painter) -> str:
    widths = [max(len(str(r[i])) for r in rows) for i in range(len(rows[0]))]
    out = []
    for n, row in enumerate(rows):
        line = "  ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)).rstrip()
        out.append(paint(line, "bold") if n == 0 else line)
    return "\n".join(out)
