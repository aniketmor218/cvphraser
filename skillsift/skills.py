"""Loading the skill taxonomy and extracting skills from free text."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .text import PhraseMatcher, Token, sentence_around, tokenise


class TaxonomyError(ValueError):
    """Raised when the taxonomy file is malformed."""


@dataclass(frozen=True)
class Skill:
    name: str
    category: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class Mention:
    """One occurrence of a skill in a document."""

    skill: str
    category: str
    surface: str  # the text as it actually appeared
    char_start: int
    char_end: int

    def evidence(self, source: str) -> str:
        return sentence_around(source, self.char_start, self.char_end)


@dataclass
class SkillIndex:
    """The taxonomy, plus a compiled matcher over every alias in it."""

    skills: dict[str, Skill] = field(default_factory=dict)
    _matcher: PhraseMatcher = field(default_factory=PhraseMatcher, repr=False)

    @classmethod
    def from_file(cls, path: str | Path) -> SkillIndex:
        path = Path(path)
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise TaxonomyError(f"taxonomy file not found: {path}") from exc
        except yaml.YAMLError as exc:
            raise TaxonomyError(f"taxonomy file is not valid YAML: {exc}") from exc
        return cls.from_mapping(raw or {})

    @classmethod
    def from_mapping(cls, raw: dict) -> SkillIndex:
        if not isinstance(raw, dict):
            raise TaxonomyError("taxonomy must be a mapping of category -> skills")
        index = cls()
        for category, entries in raw.items():
            if not isinstance(entries, dict):
                raise TaxonomyError(f"category {category!r} must map skills to alias lists")
            for name, aliases in entries.items():
                aliases = aliases or []
                if isinstance(aliases, str):
                    aliases = [aliases]
                index.add(Skill(str(name), str(category), tuple(str(a) for a in aliases)))
        if not index.skills:
            raise TaxonomyError("taxonomy is empty")
        return index

    def add(self, skill: Skill) -> None:
        if skill.name in self.skills:
            raise TaxonomyError(f"duplicate skill name: {skill.name}")
        self.skills[skill.name] = skill
        # The canonical name is itself a valid surface form.
        for phrase in (skill.name, *skill.aliases):
            self._matcher.add(phrase, skill.name)

    def category_of(self, name: str) -> str:
        skill = self.skills.get(name)
        return skill.category if skill else "other"

    def extract(self, text: str, tokens: Iterable[Token] | None = None) -> list[Mention]:
        """Find every skill mentioned in *text*, in order of appearance."""
        token_list = list(tokens) if tokens is not None else tokenise(text)
        mentions: list[Mention] = []
        for name, start_idx, end_idx in self._matcher.find(token_list):
            first, last = token_list[start_idx], token_list[end_idx - 1]
            mentions.append(
                Mention(
                    skill=name,
                    category=self.category_of(name),
                    surface=text[first.start : last.end],
                    char_start=first.start,
                    char_end=last.end,
                )
            )
        return mentions

    def unique(self, text: str) -> dict[str, Mention]:
        """First mention of each distinct skill, keyed by canonical name."""
        found: dict[str, Mention] = {}
        for mention in self.extract(text):
            found.setdefault(mention.skill, mention)
        return found

    def __len__(self) -> int:
        return len(self.skills)
