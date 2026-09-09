import pytest

from skillsift.skills import SkillIndex, TaxonomyError


def test_taxonomy_loads(index):
    assert len(index) > 40
    assert "Python" in index.skills


def test_aliases_resolve_to_canonical_names(index):
    found = index.unique("We use sklearn, k8s and nodejs.")
    assert set(found) == {"scikit-learn", "Kubernetes", "Node.js"}


def test_extract_is_case_insensitive(index):
    assert "Python" in index.unique("PYTHON and python and Python")


def test_mentions_carry_usable_evidence(index):
    text = "Other stuff here. You will write Python every day. And more."
    mention = index.unique(text)["Python"]
    assert "write Python every day" in mention.evidence(text)


def test_category_lookup(index):
    assert index.category_of("PyTorch") == "ml"
    assert index.category_of("Nonexistent") == "other"


def test_duplicate_skill_names_are_rejected():
    with pytest.raises(TaxonomyError):
        SkillIndex.from_mapping({"a": {"Python": ["py"]}, "b": {"Python": ["python3"]}})


def test_empty_taxonomy_is_rejected():
    with pytest.raises(TaxonomyError):
        SkillIndex.from_mapping({})


def test_malformed_taxonomy_is_rejected():
    with pytest.raises(TaxonomyError):
        SkillIndex.from_mapping({"languages": ["Python"]})


def test_missing_file_is_reported_clearly():
    with pytest.raises(TaxonomyError, match="not found"):
        SkillIndex.from_file("/nope/skills.yml")
