"""The scoring engine.

Scoring is deliberately transparent. Every number a user sees can be traced
back to a specific skill in a specific section of the posting, because a score
you cannot argue with is a score nobody trusts.

    score = 0.8 * weighted skill coverage + 0.2 * IDF keyword coverage

The second term only participates once there are enough stored postings to
compute a meaningful IDF; with a thin corpus it is dropped and the skill term
is used alone rather than blended with noise.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .config import Settings
from .documents import Emphasis, split_sections
from .skills import Mention, SkillIndex
from .text import content_terms, tokenise

#: Minimum corpus size before IDF keyword blending kicks in.
MIN_CORPUS_FOR_IDF = 5
SKILL_WEIGHT = 0.8
KEYWORD_WEIGHT = 0.2


@dataclass(frozen=True)
class Requirement:
    skill: str
    category: str
    emphasis: Emphasis
    weight: float
    evidence: str


@dataclass
class JobProfile:
    """What a posting actually asks for."""

    title: str
    requirements: dict[str, Requirement] = field(default_factory=dict)
    terms: Counter = field(default_factory=Counter)
    raw_text: str = ""

    @property
    def required(self) -> list[Requirement]:
        return [r for r in self.requirements.values() if r.emphasis is Emphasis.REQUIRED]

    @property
    def preferred(self) -> list[Requirement]:
        return [r for r in self.requirements.values() if r.emphasis is Emphasis.PREFERRED]

    @property
    def is_thin(self) -> bool:
        """True when too few skills were found to score the posting honestly."""
        return len(self.requirements) < 3


@dataclass
class CandidateProfile:
    """What a CV demonstrates."""

    name: str
    mentions: dict[str, Mention] = field(default_factory=dict)
    terms: Counter = field(default_factory=Counter)
    raw_text: str = ""

    @property
    def skills(self) -> set[str]:
        return set(self.mentions)


@dataclass(frozen=True)
class Gap:
    skill: str
    category: str
    emphasis: Emphasis
    evidence: str


@dataclass
class MatchResult:
    job_title: str
    candidate_name: str
    score: float
    skill_score: float
    keyword_score: float | None
    matched: list[Requirement]
    gaps: list[Gap]
    extras: list[str]
    by_category: dict[str, tuple[int, int]]
    warnings: list[str] = field(default_factory=list)

    @property
    def percentage(self) -> int:
        return round(self.score * 100)

    @property
    def required_gaps(self) -> list[Gap]:
        return [g for g in self.gaps if g.emphasis is Emphasis.REQUIRED]

    @property
    def preferred_gaps(self) -> list[Gap]:
        return [g for g in self.gaps if g.emphasis is Emphasis.PREFERRED]

    def verdict(self, threshold: float) -> str:
        if self.score >= threshold + 0.15:
            return "strong match"
        if self.score >= threshold:
            return "worth applying"
        if self.score >= threshold - 0.2:
            return "stretch"
        return "poor fit"


class Matcher:
    """Builds profiles and compares them."""

    def __init__(self, index: SkillIndex, settings: Settings) -> None:
        self.index = index
        self.settings = settings

    # ---------------------------------------------------------------- profiles

    def profile_job(self, title: str, text: str) -> JobProfile:
        """Extract weighted requirements from a job description.

        A skill mentioned in more than one section keeps its strongest
        emphasis: appearing under both "responsibilities" and "requirements"
        means required, not context.
        """
        profile = JobProfile(title=title, raw_text=text)
        rank = {Emphasis.REQUIRED: 2, Emphasis.PREFERRED: 1, Emphasis.CONTEXT: 0}

        for section in split_sections(text):
            for skill, mention in self.index.unique(section.body).items():
                existing = profile.requirements.get(skill)
                if existing and rank[existing.emphasis] >= rank[section.emphasis]:
                    continue
                profile.requirements[skill] = Requirement(
                    skill=skill,
                    category=mention.category,
                    emphasis=section.emphasis,
                    weight=self._weight(section.emphasis),
                    evidence=mention.evidence(section.body),
                )

        # Skills that only ever appeared in context sections still count, but
        # at the lower "preferred" weight rather than being silently dropped.
        for skill, requirement in list(profile.requirements.items()):
            if requirement.emphasis is Emphasis.CONTEXT:
                profile.requirements[skill] = Requirement(
                    skill=requirement.skill,
                    category=requirement.category,
                    emphasis=Emphasis.PREFERRED,
                    weight=self._weight(Emphasis.PREFERRED),
                    evidence=requirement.evidence,
                )

        profile.terms = content_terms(tokenise(text))
        return profile

    def profile_candidate(self, name: str, text: str) -> CandidateProfile:
        return CandidateProfile(
            name=name,
            mentions=self.index.unique(text),
            terms=content_terms(tokenise(text)),
            raw_text=text,
        )

    def _weight(self, emphasis: Emphasis) -> float:
        if emphasis is Emphasis.REQUIRED:
            return self.settings.required_weight
        return self.settings.preferred_weight

    # ----------------------------------------------------------------- scoring

    def match(
        self,
        job: JobProfile,
        candidate: CandidateProfile,
        idf: dict[str, float] | None = None,
    ) -> MatchResult:
        matched: list[Requirement] = []
        gaps: list[Gap] = []
        by_category: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        earned = 0.0
        available = 0.0

        for requirement in job.requirements.values():
            available += requirement.weight
            by_category[requirement.category][1] += 1
            if requirement.skill in candidate.skills:
                earned += requirement.weight
                matched.append(requirement)
                by_category[requirement.category][0] += 1
            else:
                gaps.append(
                    Gap(
                        skill=requirement.skill,
                        category=requirement.category,
                        emphasis=requirement.emphasis,
                        evidence=requirement.evidence,
                    )
                )

        skill_score = earned / available if available else 0.0
        keyword_score = self._keyword_score(job, candidate, idf)

        if keyword_score is None:
            score = skill_score
        else:
            score = SKILL_WEIGHT * skill_score + KEYWORD_WEIGHT * keyword_score

        warnings: list[str] = []
        if job.is_thin:
            warnings.append(
                f"only {len(job.requirements)} known skills found in this posting — "
                "the score is weak evidence; consider extending the taxonomy"
            )
        if not candidate.skills:
            warnings.append("no known skills found in the CV — check the file parsed correctly")

        matched.sort(key=lambda r: (-r.weight, r.skill))
        gaps.sort(key=lambda g: (g.emphasis is not Emphasis.REQUIRED, g.skill))

        return MatchResult(
            job_title=job.title,
            candidate_name=candidate.name,
            score=round(score, 4),
            skill_score=round(skill_score, 4),
            keyword_score=round(keyword_score, 4) if keyword_score is not None else None,
            matched=matched,
            gaps=gaps,
            extras=sorted(candidate.skills - set(job.requirements)),
            by_category={k: (v[0], v[1]) for k, v in sorted(by_category.items())},
            warnings=warnings,
        )

    def _keyword_score(
        self,
        job: JobProfile,
        candidate: CandidateProfile,
        idf: dict[str, float] | None,
    ) -> float | None:
        """Share of the posting's *distinctive* vocabulary present in the CV.

        Weighting by IDF is what stops boilerplate ("fast-paced environment")
        from counting as much as the terms that make this posting different
        from every other one in the corpus.
        """
        if not idf:
            return None
        weights = {term: idf.get(term, 0.0) for term in job.terms}
        total = sum(weights.values())
        if total <= 0:
            return None
        covered = sum(w for term, w in weights.items() if term in candidate.terms)
        return covered / total
