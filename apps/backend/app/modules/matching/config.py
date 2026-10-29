import hashlib
import json
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class RankingConfig:
    version: str = "evidence-baseline-1.0.1"
    extractor_version: str = "requirements-1.0"
    taxonomy_version: str = "skills-1.0"
    max_batch: int = 200
    weights: tuple = (
        ("required_skills", 0.40),
        ("preferred_skills", 0.10),
        ("experience", 0.20),
        ("role", 0.15),
        ("location", 0.10),
        ("preferences", 0.05),
    )

    def __post_init__(self):
        required = {
            "required_skills",
            "preferred_skills",
            "experience",
            "role",
            "location",
            "preferences",
        }
        if (
            len(self.weights) != 6
            or {key for key, _ in self.weights} != required
            or any(not math.isfinite(value) or value < 0 for _, value in self.weights)
            or not math.isclose(sum(value for _, value in self.weights), 1)
        ):
            raise ValueError(
                "Ranking weights must uniquely cover six components, be finite/nonnegative and sum to one"
            )

    def manifest(self):
        return {
            "version": self.version,
            "extractor_version": self.extractor_version,
            "taxonomy_version": self.taxonomy_version,
            "weights": dict(self.weights),
            "missing_policy": "available_weight_normalization_with_disclosed_coverage",
            "clock_policy": "UTC assessment day participates in match fingerprint; future employment end dates are not credited as completed experience",
            "score_meaning": "recorded professional relevance; not hiring probability",
        }

    @property
    def fingerprint(self):
        return hashlib.sha256(json.dumps(self.manifest(), sort_keys=True).encode()).hexdigest()

    @property
    def identity(self):
        return self.version + "+" + self.fingerprint[:12]


CONFIG = RankingConfig()
