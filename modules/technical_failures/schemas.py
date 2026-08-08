from typing import Any

from pydantic import BaseModel, Field

#: Metrics with a column in ``image_technical_failures``. **Adding to this tuple
#: is a schema change**: ``db_legacy._write_image_technical_failures`` builds its
#: row from it against a hand-written INSERT, so an extra key here without a
#: matching column and placeholder makes every write fail — and that write only
#: logs a warning, so it would fail silently.
TECHNICAL_FAILURE_METRIC_KEYS = (
    "blur",
    "overexposed",
    "underexposed",
    "highlight_clipping",
    "shadow_crushing",
)

#: Metrics computed and returned in the payload but **not** persisted, so they
#: need no migration. Promote one into the tuple above only alongside an Alembic
#: migration and the matching SQL change.
TECHNICAL_FAILURE_EXTRA_KEYS = ("noise",)

#: Everything the detector reports.
TECHNICAL_FAILURE_ALL_KEYS = TECHNICAL_FAILURE_METRIC_KEYS + TECHNICAL_FAILURE_EXTRA_KEYS

PRIMARY_REJECT_REASONS = ("none",) + TECHNICAL_FAILURE_ALL_KEYS


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
    noise: float = Field(
        0.0,
        description=(
            "Sensor noise severity (0-1), from an Immerkaer sigma estimate. Also "
            "gates blur: past a high sigma no sharpness reading is trustworthy."
        ),
    )

    model_config = {"extra": "allow"}

    def technical_failures_dict(self) -> dict[str, float]:
        """Every metric, persisted or not — the API/scores_json shape."""
        return {key: float(getattr(self, key)) for key in TECHNICAL_FAILURE_ALL_KEYS}

    def to_detection_dict(self) -> dict[str, Any]:
        """API / scores_json shape: metrics nested under ``technical_failures``."""
        return {
            "version": self.version,
            "technical_failure_score": self.technical_failure_score,
            "primary_reject_reason": self.primary_reject_reason,
            "technical_failures": self.technical_failures_dict(),
        }
