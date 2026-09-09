import pytest

from skillsift.store import Status, Store


@pytest.fixture
def store(tmp_path):
    with Store(tmp_path / "s.db") as s:
        yield s


def test_add_and_fetch_posting(store):
    pid = store.add_posting("MLE", "Requirements\n- Python\n", company="Acme")
    posting = store.get_posting(pid)
    assert posting.title == "MLE"
    assert posting.company == "Acme"


def test_missing_posting_returns_none(store):
    assert store.get_posting(999) is None


def test_blank_title_is_rejected(store):
    with pytest.raises(ValueError, match="title"):
        store.add_posting("  ", "some text")


def test_blank_text_is_rejected(store):
    with pytest.raises(ValueError, match="text"):
        store.add_posting("MLE", "   ")


def test_rescoring_preserves_status_and_notes(store):
    """The bug this guards: re-running a match reset every application to 'saved'."""
    pid = store.add_posting("MLE", "text")
    store.record_match(pid, 0.5, ["Rust"])
    store.set_status(pid, Status.INTERVIEW, "phone screen booked")
    store.record_match(pid, 0.8, ["Kubernetes"])

    app = store.list_applications()[0]
    assert app.status is Status.INTERVIEW
    assert app.notes == "phone screen booked"
    assert app.score == 0.8
    assert app.gaps == ["Kubernetes"]


def test_status_filter(store):
    a = store.add_posting("A", "t")
    b = store.add_posting("B", "t")
    store.record_match(a, 0.5, [])
    store.record_match(b, 0.5, [])
    store.set_status(b, Status.APPLIED)
    assert [x.posting_id for x in store.list_applications(Status.APPLIED)] == [b]


def test_status_update_on_unknown_posting_returns_false(store):
    assert store.set_status(404, Status.APPLIED) is False


def test_unknown_status_string_is_rejected():
    with pytest.raises(ValueError, match="unknown status"):
        Status.parse("ghosted")


def test_status_parse_is_forgiving():
    assert Status.parse("  Applied ") is Status.APPLIED


def test_recurring_gaps_rank_by_frequency(store):
    for gaps in (["Rust", "Kubernetes"], ["Rust"], ["Rust", "AWS"]):
        pid = store.add_posting("role", "t")
        store.record_match(pid, 0.5, gaps)
    assert store.recurring_gaps()[0] == ("Rust", 3)


def test_deleting_a_posting_cascades(store):
    pid = store.add_posting("A", "t")
    store.record_match(pid, 0.5, [])
    assert store.delete_posting(pid) is True
    assert store.list_applications() == []


def test_applications_are_unique_per_posting(store):
    pid = store.add_posting("A", "t")
    store.record_match(pid, 0.5, [])
    store.record_match(pid, 0.9, [])
    assert len(store.list_applications()) == 1


def test_schema_survives_reopening(tmp_path):
    path = tmp_path / "s.db"
    with Store(path) as first:
        pid = first.add_posting("A", "t")
        first.record_match(pid, 0.5, [])
    with Store(path) as second:
        assert len(second.list_applications()) == 1
