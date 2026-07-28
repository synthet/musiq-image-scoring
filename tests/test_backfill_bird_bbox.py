"""
Tests for scripts/backfill_bird_bbox.py — detector-only bird_bbox backfill.

No GPU/ML: stubs replace decode and BirdDetector.detect_best_box.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from modules.bird_detection import BBOX_NOT_DETECTED

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "backfill_bird_bbox.py"


def _load_script():
    """Load the backfill script as a module (scripts/ is not a package)."""
    name = "backfill_bird_bbox_under_test"
    spec = importlib.util.spec_from_file_location(name, _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def backfill():
    return _load_script()


class _FakeDetector:
    def __init__(self, boxes_by_id: dict):
        self.boxes_by_id = boxes_by_id
        self.calls = []

    def detect_best_box(self, img):
        image_id = getattr(img, "image_id", None)
        self.calls.append(image_id)
        return self.boxes_by_id.get(image_id)


class _FakeImg:
    def __init__(self, image_id: int):
        self.image_id = image_id
        self.closed = False

    def close(self):
        self.closed = True


def test_bbox_not_detected_sentinel_shape():
    assert BBOX_NOT_DETECTED == {"detected": False}
    assert "img_w" not in BBOX_NOT_DETECTED
    assert "x1" not in BBOX_NOT_DETECTED


def test_apply_detection_result_writes_box(backfill):
    writes = []

    def update_fn(image_id, payload):
        writes.append((image_id, payload))
        return True

    box = {"x1": 1, "y1": 2, "x2": 3, "y2": 4, "conf": 0.9, "img_w": 10, "img_h": 10}
    assert backfill.apply_detection_result(7, box, dry_run=False, update_fn=update_fn) == "detected"
    assert writes == [(7, box)]


def test_apply_detection_result_writes_sentinel(backfill):
    writes = []

    def update_fn(image_id, payload):
        writes.append((image_id, payload))
        return True

    assert (
        backfill.apply_detection_result(8, None, dry_run=False, update_fn=update_fn)
        == "not_detected"
    )
    assert writes == [(8, BBOX_NOT_DETECTED)]


def test_apply_detection_result_dry_run_skips_write(backfill):
    writes = []

    def update_fn(image_id, payload):
        writes.append((image_id, payload))
        return True

    assert backfill.apply_detection_result(9, None, dry_run=True, update_fn=update_fn) == "not_detected"
    assert writes == []


def test_process_batch_detected_not_detected_and_skip(backfill):
    writes = []

    def update_fn(image_id, payload):
        writes.append((image_id, payload))
        return True

    box = {
        "x1": 10,
        "y1": 10,
        "x2": 50,
        "y2": 50,
        "conf": 0.88,
        "img_w": 100,
        "img_h": 100,
        "area_frac": 0.16,
    }
    detector = _FakeDetector({1: box, 2: None})

    def decode_fn(row):
        image_id = int(row["id"])
        if image_id == 3:
            return image_id, None, "file_missing"
        return image_id, _FakeImg(image_id), None

    rows = [
        {"id": 1, "file_path": "/a.NEF"},
        {"id": 2, "file_path": "/b.NEF"},
        {"id": 3, "file_path": "/missing.NEF"},
    ]
    summary = backfill.process_batch(
        rows,
        detector=detector,
        dry_run=False,
        workers=2,
        progress_every=0,
        decode_fn=decode_fn,
        update_fn=update_fn,
    )

    assert summary["detected"] == 1
    assert summary["not_detected"] == 1
    assert summary["skipped"] == 1
    assert summary["errors"] == 0
    assert summary["written"] == 2
    assert writes == [(1, box), (2, BBOX_NOT_DETECTED)]


def test_process_batch_dry_run_does_not_write(backfill):
    writes = []

    def update_fn(image_id, payload):
        writes.append((image_id, payload))
        return True

    detector = _FakeDetector({1: None})

    def decode_fn(row):
        return int(row["id"]), _FakeImg(int(row["id"])), None

    summary = backfill.process_batch(
        [{"id": 1, "file_path": "/a.NEF"}],
        detector=detector,
        dry_run=True,
        workers=1,
        progress_every=0,
        decode_fn=decode_fn,
        update_fn=update_fn,
    )
    assert summary["not_detected"] == 1
    assert summary["written"] == 0
    assert writes == []
