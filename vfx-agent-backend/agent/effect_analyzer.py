"""Isolated analysis of explicitly referenced saved Effects."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import re
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field

from config import (
    MAX_REFERENCE_EVIDENCE_CHARS,
    REFERENCE_ANALYZER_CONCURRENCY,
    REFERENCE_ANALYZER_MODEL,
)
from .llm import call_llm_structured
from .schemas import (
    ReferenceEvidence,
    ReferenceFinding,
    ReferenceSafeSummary,
    ReferenceSource,
)


INTERNAL_REFERENCE_SYSTEM = """You analyze one explicitly referenced PromptPoseFX Effect for CodeAgent.
Return only evidence relevant to the stated reference intent. Each evidence value must be a short, exact, contiguous substring copied from SOURCE CODE. Provide one to five findings. Do not summarize unrelated joints, motion, colors, controls, or implementation. The usage field should explain how CodeAgent may reuse that evidence without requiring a full-code copy.
"""


SAFE_REFERENCE_SYSTEM = """Describe the requested visual behavior of one PromptPoseFX Effect for an ordinary creator. Return concise English prose only through the schema. Do not include code, identifiers, expressions, API names, implementation-specific numeric literals, or source excerpts. Explain observable visuals and motion, not implementation.
"""


class _EvidenceDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    findings: list[ReferenceFinding] = Field(min_length=1, max_length=5)


class _SummaryDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1)


class ReferenceAnalysisError(RuntimeError):
    """Raised when reference output cannot be safely validated."""


StructuredCall = Callable[..., BaseModel]


class EffectAnalyzer:
    """Produce verified evidence or code-free summaries from saved Effect code."""

    def __init__(
        self,
        model: str = REFERENCE_ANALYZER_MODEL,
        max_evidence_chars: int = MAX_REFERENCE_EVIDENCE_CHARS,
        concurrency: int = REFERENCE_ANALYZER_CONCURRENCY,
        structured_call: StructuredCall | None = None,
    ) -> None:
        self.model = model
        self.max_evidence_chars = max(1, max_evidence_chars)
        self.concurrency = max(1, min(3, concurrency))
        self.structured_call = structured_call or call_llm_structured

    def analyze_evidence(
        self,
        sources: list[ReferenceSource],
    ) -> list[ReferenceEvidence]:
        """Analyze sources concurrently, preserve input order, and enforce one budget."""
        if not sources:
            return []
        with ThreadPoolExecutor(max_workers=min(self.concurrency, len(sources))) as pool:
            evidence = list(pool.map(self._analyze_one, sources))
        return self._fit_budget(evidence)

    def summarize(self, source: ReferenceSource) -> ReferenceSafeSummary:
        """Return a validated code-free summary for MainAgent or a product response."""
        user = self._source_prompt(source)
        last_error = ""
        for attempt in range(2):
            prompt = user
            if last_error:
                prompt += (
                    "\n\nYour previous summary was unsafe. Return a new code-free summary. "
                    f"Validation error: {last_error}"
                )
            try:
                draft = self.structured_call(
                    model=self.model,
                    system=SAFE_REFERENCE_SYSTEM,
                    user=prompt,
                    output_schema=_SummaryDraft,
                    temperature=0.2,
                )
                self._validate_safe_summary(draft.summary, source.code)
                return ReferenceSafeSummary(
                    effect_id=source.effect_id,
                    summary=draft.summary.strip(),
                )
            except Exception as error:
                last_error = str(error)
                if attempt == 1:
                    raise ReferenceAnalysisError(
                        f"Safe reference summary failed: {last_error}"
                    ) from error
        raise ReferenceAnalysisError("Safe reference summary failed")

    def summarize_many(
        self,
        sources: list[ReferenceSource],
    ) -> list[ReferenceSafeSummary]:
        """Summarize up to three sources concurrently while preserving input order."""
        if not sources:
            return []
        with ThreadPoolExecutor(max_workers=min(self.concurrency, len(sources))) as pool:
            return list(pool.map(self.summarize, sources))

    def _analyze_one(self, source: ReferenceSource) -> ReferenceEvidence:
        user = self._source_prompt(source)
        last_error = ""
        for attempt in range(2):
            prompt = user
            if last_error:
                prompt += (
                    "\n\nThe previous evidence was invalid. Every evidence value must be an "
                    f"exact substring of SOURCE CODE. Validation error: {last_error}"
                )
            try:
                draft = self.structured_call(
                    model=self.model,
                    system=INTERNAL_REFERENCE_SYSTEM,
                    user=prompt,
                    output_schema=_EvidenceDraft,
                    temperature=0.1,
                )
                for finding in draft.findings:
                    if finding.evidence not in source.code:
                        raise ValueError("evidence is not an exact source substring")
                return ReferenceEvidence(
                    effect_id=source.effect_id,
                    reference_intent=source.reference_intent,
                    findings=draft.findings,
                )
            except Exception as error:
                last_error = str(error)
                if attempt == 1:
                    raise ReferenceAnalysisError(
                        f"Reference evidence failed exact source substring validation: {last_error}"
                    ) from error
        raise ReferenceAnalysisError("Reference evidence analysis failed")

    def _fit_budget(
        self,
        evidence: list[ReferenceEvidence],
    ) -> list[ReferenceEvidence]:
        if self.max_evidence_chars < len(evidence):
            raise ReferenceAnalysisError(
                "Reference evidence budget cannot retain one excerpt per Effect; reduce references"
            )

        selected: list[list[ReferenceFinding]] = [[] for _ in evidence]
        remaining = self.max_evidence_chars

        for index, item in enumerate(evidence):
            references_left = len(evidence) - index
            allowance = max(1, remaining // references_left)
            first = item.findings[0]
            excerpt = first.evidence[:allowance]
            selected[index].append(first.model_copy(update={"evidence": excerpt}))
            remaining -= len(excerpt)

        for finding_index in range(1, 5):
            for item_index, item in enumerate(evidence):
                if finding_index >= len(item.findings):
                    continue
                finding = item.findings[finding_index]
                if len(finding.evidence) <= remaining:
                    selected[item_index].append(finding)
                    remaining -= len(finding.evidence)

        return [
            item.model_copy(update={"findings": selected[index]})
            for index, item in enumerate(evidence)
        ]

    @staticmethod
    def _source_prompt(source: ReferenceSource) -> str:
        return (
            f"EFFECT ID: {source.effect_id}\n"
            f"REFERENCE INTENT: {source.reference_intent}\n"
            f"SOURCE CODE:\n{source.code}"
        )

    @staticmethod
    def _validate_safe_summary(summary: str, code: str) -> None:
        text = summary.strip()
        if any(character.isdigit() for character in text):
            raise ValueError("summary contains implementation-specific numeric text")
        forbidden = (
            "```", "class Effect", "static CONFIG", "this.", "sketch.",
            "frameData", "params.", "=>", ";", "{", "}",
        )
        if any(token in text for token in forbidden):
            raise ValueError("summary contains code or API text")
        if re.search(r"\b[A-Za-z_$][\w$]*\.[A-Za-z_$][\w$]*\b", text):
            raise ValueError("summary contains an implementation expression")
        for line in code.splitlines():
            source_fragment = line.strip()
            if len(source_fragment) >= 16 and source_fragment in text:
                raise ValueError("summary contains a source excerpt")


__all__ = [
    "EffectAnalyzer",
    "ReferenceAnalysisError",
    "ReferenceSource",
]
