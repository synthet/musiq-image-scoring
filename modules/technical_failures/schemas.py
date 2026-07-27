from typing import Any

from pydantic import BaseModel, Field

TECHNICAL_FAILURE_METRIC_KEYS = (
    "blur",
    "overexposed",
    "underexposed",
    "highlight_clipping",
    "shadow_crushing",
)

PRIMARY_REJECT_REASONS = ("none",) + TECHNICAL_FAILURE_METRIC_KEYS


class TechnicalFailurePayload(BaseModel):
    version: str = "1.0.0"
    technical_failure_score: float = Field(
        0.0,
        description="Calibrated aggregate technical failure score (0-100); 100 is severe.",
    )
    primary_reject_reason: str = Field(
        "none",
        description="Dominant technical reject reason, or 'none'.",
    )

    blur: float = Field(0.0, description="Blur severity (0-1).")
    overexposed: float = Field(0.0, description="Overexposure severity (0-1).")
    underexposed: float = Field(0.0, description="Underexposure severity (0-1).")
    highlight_clipping: float = Field(0.0, description="Highlight clipping ratio (0-1).")
    shadow_crushing: float = Field(0.0, description="Shadow crushing ratio (0-1).")

    model_config = {"extra": "allow"}

    def technical_failures_dict(self) -> dict[str, float]:
        return {key: float(getattr(self, key)) for key in TECHNICAL_FAILURE_METRIC_KEYS}

    def to_detection_dict(self) -> dict[str, Any]:
        """API / scores_json shape: metrics nested under ``technical_failures``."""
        return {
            "version": self.version,
            "technical_failure_score": self.technical_failure_score,
            "primary_reject_reason": self.primary_reject_reason,
            "technical_failures": self.technical_failures_dict(),
        }
