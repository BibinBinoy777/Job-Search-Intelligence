from typing import Any, Mapping, Protocol, Sequence

from app.api.schemas import JobOut, ProfileOut


class ResumeParser(Protocol):
    def extract_for_review(self, private_document_ref: str) -> Mapping[str, Any]: ...


class SkillExtractor(Protocol):
    def extract_with_evidence(self, text: str) -> Sequence[Mapping[str, Any]]: ...


class EmbeddingProvider(Protocol):
    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...


class EligibilityEvaluator(Protocol):
    def evaluate(self, candidate: ProfileOut, job: JobOut) -> Mapping[str, Any]: ...


class RankingService(Protocol):
    def rank_with_evidence(
        self, candidate: ProfileOut, jobs: Sequence[JobOut]
    ) -> Sequence[Mapping[str, Any]]: ...


class CareerInsights(Protocol):
    def explain_gaps(self, candidate: ProfileOut, jobs: Sequence[JobOut]) -> Mapping[str, Any]: ...


# Future integration contracts. The deterministic Phase 3 matching implementation
# lives in modules/matching; no external AI provider or resume pipeline runs.
