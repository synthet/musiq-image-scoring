import logging
from .schemas import TechnicalFailurePayload
from .classical_metrics import compute_classical_metrics
from .calibration import calibrate_technical_failure_score, determine_primary_reject_reason

logger = logging.getLogger(__name__)

def detect_technical_failures(image_path: str, context: dict = None) -> TechnicalFailurePayload:
    """
    Main orchestrator for technical failure detection.
    Args:
        image_path: Path to the preprocessed (or original) image to analyze.
        context: Optional configuration or contextual information.
    Returns:
        TechnicalFailurePayload containing the metrics and calibrated scores.
    """
    context = context or {}
    use_classical = context.get("use_classical_metrics", True)
    
    metrics = {}
    
    if use_classical:
        try:
            metrics = compute_classical_metrics(image_path)
        except Exception as e:
            logger.error(f"Error computing classical metrics for {image_path}: {e}")
            if context.get("fail_on_detector_error", False):
                raise
    
    score = calibrate_technical_failure_score(metrics)
    reason = determine_primary_reject_reason(metrics)
    
    return TechnicalFailurePayload(
        technical_failure_score=score,
        primary_reject_reason=reason,
        **metrics
    )
