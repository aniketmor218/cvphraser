"""Tokenisation and phrase matching.

The whole matcher rests on one idea: a skill is a *phrase*, not a word.
"machine learning" and "learning" mean very different things on a CV, and a
naive substring search matches "R" inside "Rust". So text is tokenised once,
positions are kept, and phrases are matched over token n-grams using a trie.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass

# Keep +, # and . inside tokens so "c++", "c#" and "node.js" survive intact.
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#.\-]*", re.IGNORECASE)
_TRAILING_PUNCT = re.compile(r"[.\-]+$")

#: Words with no discriminating power; dropped before IDF ranking.
STOPWORDS = frozenset(
    """
    a an the and or but if then than so as of to in on at by for with from into
    over under again further once here there all any both each few more most
    other some such no nor not only own same too very can will just should now
    is are was were be been being have has had do does did doing you your we our
    they their this that these those it its will would could about across
    experience experienced working work works role team teams strong good great
    excellent ability able using use used help helps within across including
    etc via per year years plus
    """.split()
)


@dataclass(frozen=True)
class Token:
    """A single word with its character span in the source text."""

    text: str
    start: int
    end: int


def tokenise(text: str) -> list[Token]:
    """Split text into lowercase tokens, remembering where each one came from.

    Character spans are what let the report quote the sentence a skill was
    found in, rather than just asserting that it was found.
    """
    tokens: list[Token] = []
    for match in _TOKEN_RE.finditer(text):
        raw = match.group(0).lower()
        cleaned = _TRAILING_PUNCT.sub("", raw)
        if not cleaned:
            continue
        tokens.append(Token(cleaned, match.start(), match.start() + len(cleaned)))
    return tokens


def ngrams(tokens: Sequence[Token], size: int) -> Iterator[tuple[int, Sequence[Token]]]:
    """Yield ``(start_index, window)`` pairs for every n-gram of length *size*."""
    if size <= 0:
        raise ValueError("n-gram size must be positive")
    for i in range(len(tokens) - size + 1):
        yield i, tokens[i : i + size]


class PhraseMatcher:
    """Trie-backed multi-phrase matcher.

    Building one trie over every alias in the taxonomy means a document is
    scanned once, in O(tokens x longest_phrase), instead of once per skill.
    Longest-match-wins, so "machine learning engineer" never also reports a
    separate hit for "machine learning" at the same position.
    """

    _TERMINAL = "\x00"

    def __init__(self) -> None:
        self._root: dict = {}
        self._max_len = 0

    def add(self, phrase: str, payload: str) -> None:
        """Register *phrase*; matches on it report *payload* as the canonical name."""
        tokens = [t.text for t in tokenise(phrase)]
        if not tokens:
            return
        node = self._root
        for token in tokens:
            node = node.setdefault(token, {})
        node[self._TERMINAL] = payload
        self._max_len = max(self._max_len, len(tokens))

    def find(self, tokens: Sequence[Token]) -> list[tuple[str, int, int]]:
        """Return ``(payload, token_start, token_end)`` for each non-overlapping hit."""
        hits: list[tuple[str, int, int]] = []
        i = 0
        while i < len(tokens):
            node = self._root
            best: tuple[str, int] | None = None
            for offset in range(min(self._max_len, len(tokens) - i)):
                node = node.get(tokens[i + offset].text)
                if node is None:
                    break
                payload = node.get(self._TERMINAL)
                if payload is not None:
                    best = (payload, i + offset + 1)
            if best is not None:
                hits.append((best[0], i, best[1]))
                i = best[1]  # longest match wins; skip past it
            else:
                i += 1
        return hits

    def __len__(self) -> int:
        def count(node: dict) -> int:
            total = 1 if self._TERMINAL in node else 0
            for key, child in node.items():
                if key != self._TERMINAL:
                    total += count(child)
            return total

        return count(self._root)


def sentence_around(text: str, start: int, end: int, window: int = 140) -> str:
    """Pull a readable snippet around a character span, for evidence in reports."""
    left = text.rfind(".", 0, start)
    right = text.find(".", end)
    left = start - window if left == -1 or start - left > window else left + 1
    right = end + window if right == -1 or right - end > window else right
    snippet = text[max(0, left) : min(len(text), right)]
    return " ".join(snippet.split()).strip(" -•\t")


def content_terms(tokens: Iterable[Token]) -> Counter:
    """Count non-stopword terms, used for the IDF-weighted keyword pass."""
    counts: Counter = Counter()
    for token in tokens:
        if token.text in STOPWORDS or len(token.text) < 2 or token.text.isdigit():
            continue
        counts[token.text] += 1
    return counts


def inverse_document_frequency(documents: Sequence[Counter]) -> dict[str, float]:
    """Smoothed IDF over a corpus of term-count maps.

    Implemented by hand rather than pulled from scikit-learn: the corpus here
    is a few dozen job descriptions, and a 60 MB dependency to compute one
    logarithm is a poor trade.
    """
    n = len(documents)
    if n == 0:
        return {}
    doc_freq: Counter = Counter()
    for doc in documents:
        doc_freq.update(doc.keys())
    return {term: math.log((n + 1) / (df + 1)) + 1.0 for term, df in doc_freq.items()}
