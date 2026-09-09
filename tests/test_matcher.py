from skillsift.documents import Emphasis
from skillsift.matcher import Matcher
from skillsift.text import content_terms, inverse_document_frequency, tokenise


def make(index, settings):
    return Matcher(index, settings)


def test_required_and_preferred_are_separated(index, settings, jd_text):
    job = make(index, settings).profile_job("MLE", jd_text)
    assert "Python" in {r.skill for r in job.required}
    assert "Rust" in {r.skill for r in job.preferred}


def test_bullet_skills_survive_section_parsing(index, settings, jd_text):
    """Regression: skills on bulleted requirement lines were being dropped."""
    job = make(index, settings).profile_job("MLE", jd_text)
    assert {"Python", "SQL", "PyTorch", "Docker"} <= set(job.requirements)


def test_strongest_emphasis_wins(index, settings):
    jd = "About the role\nYou will use Docker.\n\nRequirements\n- Docker\n"
    job = make(index, settings).profile_job("x", jd)
    assert job.requirements["Docker"].emphasis is Emphasis.REQUIRED


def test_context_only_skills_are_demoted_not_dropped(index, settings):
    jd = "Requirements\n- Python\n\nBenefits\n- Free AWS training\n"
    job = make(index, settings).profile_job("x", jd)
    assert job.requirements["AWS"].emphasis is Emphasis.PREFERRED


def test_perfect_match_scores_one(index, settings):
    matcher = make(index, settings)
    job = matcher.profile_job("x", "Requirements\n- Python\n- Docker\n")
    cv = matcher.profile_candidate("me", "I use Python and Docker.")
    assert matcher.match(job, cv).score == 1.0


def test_no_overlap_scores_zero(index, settings):
    matcher = make(index, settings)
    job = matcher.profile_job("x", "Requirements\n- Rust\n- Kubernetes\n")
    cv = matcher.profile_candidate("me", "I use Python and Docker.")
    assert matcher.match(job, cv).score == 0.0


def test_required_skills_outweigh_preferred(index, settings):
    matcher = make(index, settings)
    jd = "Requirements\n- Python\n\nNice to have\n- Rust\n"
    has_required = matcher.match(matcher.profile_job("x", jd),
                                 matcher.profile_candidate("a", "Python"))
    has_preferred = matcher.match(matcher.profile_job("x", jd),
                                  matcher.profile_candidate("b", "Rust"))
    assert has_required.score > has_preferred.score


def test_gaps_carry_the_line_they_came_from(index, settings, jd_text, cv_text):
    matcher = make(index, settings)
    result = matcher.match(matcher.profile_job("MLE", jd_text),
                           matcher.profile_candidate("me", cv_text))
    kubernetes = next(g for g in result.gaps if g.skill == "Kubernetes")
    assert kubernetes.evidence


def test_extras_are_skills_the_posting_never_asked_for(index, settings, cv_text):
    matcher = make(index, settings)
    job = matcher.profile_job("x", "Requirements\n- Python\n")
    result = matcher.match(job, matcher.profile_candidate("me", cv_text))
    assert "Flask" in result.extras
    assert "Python" not in result.extras


def test_thin_postings_are_flagged(index, settings):
    matcher = make(index, settings)
    job = matcher.profile_job("x", "We want a great person who is a team player.\n")
    result = matcher.match(job, matcher.profile_candidate("me", "Python"))
    assert any("weak evidence" in w for w in result.warnings)


def test_empty_cv_is_flagged(index, settings, jd_text):
    matcher = make(index, settings)
    result = matcher.match(matcher.profile_job("x", jd_text),
                           matcher.profile_candidate("me", ""))
    assert any("no known skills found in the CV" in w for w in result.warnings)


def test_keyword_score_is_none_without_a_corpus(index, settings, jd_text, cv_text):
    matcher = make(index, settings)
    result = matcher.match(matcher.profile_job("x", jd_text),
                           matcher.profile_candidate("me", cv_text))
    assert result.keyword_score is None
    assert result.score == result.skill_score


def test_keyword_score_blends_in_when_a_corpus_exists(index, settings, jd_text, cv_text):
    matcher = make(index, settings)
    idf = inverse_document_frequency(
        [content_terms(tokenise(t)) for t in [jd_text, cv_text, "unrelated posting about Rust"]]
    )
    result = matcher.match(matcher.profile_job("x", jd_text),
                           matcher.profile_candidate("me", cv_text), idf)
    assert result.keyword_score is not None
    assert 0.0 <= result.score <= 1.0


def test_category_breakdown_totals_match(index, settings, jd_text, cv_text):
    matcher = make(index, settings)
    job = matcher.profile_job("x", jd_text)
    result = matcher.match(job, matcher.profile_candidate("me", cv_text))
    assert sum(total for _, total in result.by_category.values()) == len(job.requirements)


def test_verdicts_are_ordered(index, settings, jd_text, cv_text):
    matcher = make(index, settings)
    result = matcher.match(matcher.profile_job("x", jd_text),
                           matcher.profile_candidate("me", cv_text))
    assert result.verdict(0.0) == "strong match"
    assert result.verdict(1.0) == "poor fit"
