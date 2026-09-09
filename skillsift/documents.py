"""Reading CVs and job descriptions, and splitting a posting into sections.

A job description is not a flat bag of words. "You must have 3 years of Python"
and "Rust is a nice-to-have" carry very different weight, and the difference is
almost always signalled by a heading. Splitting on those headings is the single
change that moved this tool from "keyword counter" to something worth trusting.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class Emphasis(str, Enum):
    REQUIRED = "required"
    PREFERRED = "preferred"
    CONTEXT = "context"  # responsibilities, benefits, company blurb


# Matched as prefixes (no trailing \b) so "Requirements" and
# "Responsibilities" hit the same rule as their singular forms.
_HEADING_PATTERNS: list[tuple[re.Pattern, Emphasis]] = [
    (re.compile(r"\b(nice[\s-]?to[\s-]?have|desirable|preferred|bonus|plus|"
                r"good to have|advantageous|we'?d love)", re.I), Emphasis.PREFERRED),
    (re.compile(r"\b(requirement|required|must[\s-]?have|essential|qualification|"
                r"what you'?ll need|who you are|you have|skills? (and|&) experience|"
                r"minimum|about you)", re.I), Emphasis.REQUIRED),
    (re.compile(r"\b(responsibilit|what you'?ll do|the role|about (us|the team|the role)|"
                r"benefit|perk|how to apply|day[\s-]to[\s-]day|package|salary|"
                r"equal opportunit|our stack)", re.I), Emphasis.CONTEXT),
]

#: A heading is a short line — long prose lines are body text even if they
#: happen to contain the word "requirements".
_MAX_HEADING_WORDS = 9

#: A bullet is content, never a heading. Without this, a line like
#: "- Must have Python" is read as a section header and its skills vanish
#: into the heading text instead of being scored.
_BULLET_RE = re.compile(r"^\s*([-*+•·–—]|\(?\d{1,2}[.)])\s+")

_SUPPORTED_SUFFIXES = {".txt", ".md", ".markdown", ".rst", ".pdf"}


@dataclass(frozen=True)
class Section:
    heading: str
    emphasis: Emphasis
    body: str
    offset: int  # char offset of body within the full document


class DocumentError(ValueError):
    """Raised when a document cannot be read."""


def read_document(path: str | Path) -> str:
    """Read a CV or job description from disk.

    PDF support is optional: ``pypdf`` is only imported if a PDF is actually
    handed over, so the core install stays at three dependencies.
    """
    path = Path(path)
    if not path.exists():
        raise DocumentError(f"no such file: {path}")
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _read_pdf(path)
    if suffix and suffix not in _SUPPORTED_SUFFIXES:
        raise DocumentError(
            f"unsupported file type {suffix!r}; supported: "
            + ", ".join(sorted(_SUPPORTED_SUFFIXES))
        )
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise DocumentError(f"{path} is not UTF-8 text (is it a binary file?)") from exc


def _read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - depends on install extras
        raise DocumentError(
            "reading PDFs needs the optional dependency: pip install 'skillsift[pdf]'"
        ) from exc
    reader = PdfReader(str(path))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    if not text.strip():
        raise DocumentError(
            f"{path} yielded no text — it is probably a scanned image, not a text PDF"
        )
    return text


def classify_heading(line: str) -> Emphasis | None:
    """Return the emphasis a line implies, or ``None`` if it is not a heading."""
    if _BULLET_RE.match(line):
        return None
    stripped = line.strip().strip("#*_:•-— ").strip()
    if not stripped or len(stripped.split()) > _MAX_HEADING_WORDS:
        return None
    if stripped.endswith((".", ",", ";")):
        return None  # a sentence, not a heading
    for pattern, emphasis in _HEADING_PATTERNS:
        if pattern.search(stripped):
            return emphasis
    return None


def split_sections(text: str) -> list[Section]:
    """Split a job description into emphasis-tagged sections.

    Text before the first recognised heading is treated as REQUIRED: short
    postings often list must-haves with no heading at all, and under-weighting
    them is worse than over-weighting a company blurb.
    """
    lines = text.splitlines(keepends=True)
    sections: list[Section] = []
    heading = "(intro)"
    emphasis = Emphasis.REQUIRED
    buffer: list[str] = []
    offset = 0
    cursor = 0

    def flush() -> None:
        body = "".join(buffer)
        if body.strip():
            sections.append(Section(heading, emphasis, body, offset))

    for line in lines:
        found = classify_heading(line)
        if found is not None:
            flush()
            heading = line.strip().strip("#*_: ").strip()
            emphasis = found
            # The heading line stays in the body it introduces. Postings very
            # often inline skills into the header itself ("Essential skills:
            # Python, SQL"), and dropping the line drops those skills.
            buffer = [line]
            offset = cursor
        else:
            buffer.append(line)
        cursor += len(line)
    flush()
    return sections
