from skillsift.text import (
    PhraseMatcher,
    content_terms,
    inverse_document_frequency,
    ngrams,
    sentence_around,
    tokenise,
)


def test_tokenise_keeps_symbols_that_matter():
    tokens = [t.text for t in tokenise("I write C++, C# and Node.js.")]
    assert "c++" in tokens
    assert "c#" in tokens
    assert "node.js" in tokens


def test_tokenise_records_spans():
    token = tokenise("hello world")[1]
    assert (token.start, token.end) == (6, 11)


def test_matcher_prefers_the_longest_phrase():
    matcher = PhraseMatcher()
    matcher.add("machine learning", "ML")
    matcher.add("machine learning engineer", "MLE")
    hits = matcher.find(tokenise("a machine learning engineer role"))
    assert [h[0] for h in hits] == ["MLE"]


def test_matcher_does_not_match_inside_words():
    """The 'R' problem: a one-letter skill must not match inside 'Rust'."""
    matcher = PhraseMatcher()
    matcher.add("r", "R")
    assert matcher.find(tokenise("we use Rust here")) == []
    assert [h[0] for h in matcher.find(tokenise("we use R here"))] == ["R"]


def test_matcher_finds_repeated_phrases():
    matcher = PhraseMatcher()
    matcher.add("python", "Python")
    assert len(matcher.find(tokenise("python and more python"))) == 2


def test_ngrams_windows():
    tokens = tokenise("a b c")
    assert [i for i, _ in ngrams(tokens, 2)] == [0, 1]
    assert list(ngrams(tokens, 4)) == []


def test_sentence_around_returns_the_containing_sentence():
    text = "First sentence. We need Python here. Third one."
    assert "Python" in sentence_around(text, 24, 30)
    assert "First sentence" not in sentence_around(text, 24, 30)


def test_content_terms_drops_stopwords():
    counts = content_terms(tokenise("the team and the python"))
    assert "the" not in counts
    assert counts["python"] == 1


def test_idf_rewards_rare_terms():
    docs = [content_terms(tokenise(t)) for t in ["python docker", "python java", "python go"]]
    idf = inverse_document_frequency(docs)
    assert idf["docker"] > idf["python"]


def test_idf_of_empty_corpus_is_empty():
    assert inverse_document_frequency([]) == {}
