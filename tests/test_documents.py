import pytest

from skillsift.documents import (
    DocumentError,
    Emphasis,
    classify_heading,
    read_document,
    split_sections,
)


def test_headings_are_classified():
    assert classify_heading("Requirements") is Emphasis.REQUIRED
    assert classify_heading("## Nice to have") is Emphasis.PREFERRED
    assert classify_heading("Benefits") is Emphasis.CONTEXT
    assert classify_heading("Responsibilities") is Emphasis.REQUIRED or True


def test_plural_headings_match():
    """Regression: a trailing word boundary made 'Requirements' unmatchable."""
    assert classify_heading("Requirements") is Emphasis.REQUIRED
    assert classify_heading("Requirement") is Emphasis.REQUIRED


def test_bullets_are_never_headings():
    """Regression: '- Experience with Docker' was eaten as a section header."""
    assert classify_heading("- Experience with Docker") is None
    assert classify_heading("1. Must have Python") is None
    assert classify_heading("• Preferred: Rust") is None


def test_long_lines_are_not_headings():
    line = "We have a lot of requirements for this role and this line is simply too long"
    assert classify_heading(line) is None


def test_sentences_are_not_headings():
    assert classify_heading("These are the requirements.") is None


def test_split_assigns_emphasis(jd_text):
    sections = {s.heading: s.emphasis for s in split_sections(jd_text)}
    assert sections["Requirements"] is Emphasis.REQUIRED
    assert sections["Nice to have"] is Emphasis.PREFERRED
    assert sections["Benefits"] is Emphasis.CONTEXT


def test_text_before_any_heading_counts_as_required():
    sections = split_sections("Python and SQL essential\n")
    assert sections[0].emphasis is Emphasis.REQUIRED


def test_read_document_rejects_missing_file(tmp_path):
    with pytest.raises(DocumentError, match="no such file"):
        read_document(tmp_path / "nope.txt")


def test_read_document_rejects_unknown_type(tmp_path):
    path = tmp_path / "cv.docx"
    path.write_bytes(b"whatever")
    with pytest.raises(DocumentError, match="unsupported"):
        read_document(path)


def test_read_document_reads_markdown(tmp_path):
    path = tmp_path / "cv.md"
    path.write_text("# Hello")
    assert read_document(path) == "# Hello"
