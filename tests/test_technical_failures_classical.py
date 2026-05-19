import numpy as np
import tempfile
import os
from PIL import Image

from modules.technical_failures.classical_metrics import compute_classical_metrics
from modules.technical_failures.detector import detect_technical_failures
from modules.technical_failures.schemas import (
    PRIMARY_REJECT_REASONS,
    TECHNICAL_FAILURE_METRIC_KEYS,
    TechnicalFailurePayload,
)

def _create_synthetic_image(fill_value, path):
    # 100x100 solid color
    arr = np.full((100, 100), fill_value, dtype=np.uint8)
    Image.fromarray(arr).save(path)

def test_classical_metrics_overexposed():
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        path = f.name
    try:
        _create_synthetic_image(255, path)
        metrics = compute_classical_metrics(path)
        assert metrics["highlight_clipping"] == 1.0
        assert metrics["overexposed"] > 0.0
        assert metrics["underexposed"] == 0.0
    finally:
        if os.path.exists(path):
            os.remove(path)

def test_classical_metrics_underexposed():
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        path = f.name
    try:
        _create_synthetic_image(0, path)
        metrics = compute_classical_metrics(path)
        assert metrics["shadow_crushing"] == 1.0
        assert metrics["underexposed"] > 0.0
        assert metrics["overexposed"] == 0.0
    finally:
        if os.path.exists(path):
            os.remove(path)

def test_payload_detection_dict_shape():
    payload = TechnicalFailurePayload(
        technical_failure_score=42.0,
        primary_reject_reason="blur",
        blur=0.8,
    )
    det = payload.to_detection_dict()
    assert det["technical_failure_score"] == 42.0
    assert det["primary_reject_reason"] == "blur"
    assert set(det["technical_failures"].keys()) == set(TECHNICAL_FAILURE_METRIC_KEYS)
    assert set(PRIMARY_REJECT_REASONS) >= set(TECHNICAL_FAILURE_METRIC_KEYS) | {"none"}


def test_calibration_and_detector():
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        path = f.name
    try:
        # Create a totally blank image (severe underexposure, blur=1.0)
        _create_synthetic_image(0, path)
        payload = detect_technical_failures(path)
        
        assert payload.technical_failure_score > 50.0
        assert payload.primary_reject_reason in ("blur", "underexposed")
        assert payload.blur == 1.0
    finally:
        if os.path.exists(path):
            os.remove(path)
