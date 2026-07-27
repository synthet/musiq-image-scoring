"""
Tests for modules/bird_detection.py — YOLO bird localization / crop step.

All tests here run without GPU, ultralytics, or huggingface_hub: the pure helpers
(select_best_box, crop_to_box) and the fail-open detector wiring are exercised with
stubs and real PIL images only.

Run with:
    pytest tests/test_bird_detection.py -v
"""

from PIL import Image

from modules.bird_detection import BirdDetector, select_best_box


# ──────────────────────────────────────────────────────────────────────────────
# select_best_box — pure helper
# ──────────────────────────────────────────────────────────────────────────────

def test_select_best_box_empty_returns_none():
    assert select_best_box([]) is None


def test_select_best_box_picks_highest_confidence():
    boxes = [
        {"xyxy": (0, 0, 10, 10), "conf": 0.30},
        {"xyxy": (5, 5, 20, 20), "conf": 0.91},
        {"xyxy": (1, 1, 8, 8), "conf": 0.55},
    ]
    best = select_best_box(boxes)
    assert best["conf"] == 0.91
    assert best["xyxy"] == (5, 5, 20, 20)


# ──────────────────────────────────────────────────────────────────────────────
# crop_to_box — padding + clamping
# ──────────────────────────────────────────────────────────────────────────────

def _detector():
    # Construct without touching config or loading any model.
    return BirdDetector(config={"enabled": True}, device="cpu")


def test_crop_to_box_expands_by_padding():
    img = Image.new("RGB", (100, 100))
    box = {"x1": 10, "y1": 10, "x2": 30, "y2": 30}
    crop = _detector().crop_to_box(img, box, padding=0.1)  # pad = 20 * 0.1 = 2 px
    assert crop.size == (24, 24)  # (32-8, 32-8)


def test_crop_to_box_clamps_to_image_bounds():
    img = Image.new("RGB", (100, 100))
    box = {"x1": 90, "y1": 90, "x2": 100, "y2": 100}
    crop = _detector().crop_to_box(img, box, padding=0.1)  # pad = 1 px, right/bottom clamp at 100
    assert crop.size == (11, 11)  # (100-89, 100-89)


def test_crop_to_box_degenerate_returns_original():
    img = Image.new("RGB", (100, 100))
    box = {"x1": 50, "y1": 50, "x2": 50, "y2": 50}
    crop = _detector().crop_to_box(img, box, padding=0.0)
    assert crop is img  # zero-area crop → whole image


# ──────────────────────────────────────────────────────────────────────────────
# detect_and_crop — fallback vs. crop
# ──────────────────────────────────────────────────────────────────────────────

def test_detect_and_crop_no_detection_returns_original():
    det = _detector()
    det.detect_best_box = lambda image: None  # stub out YOLO
    img = Image.new("RGB", (100, 100))
    out_img, box = det.detect_and_crop(img)
    assert out_img is img
    assert box is None


def test_detect_and_crop_with_box_crops():
    det = _detector()
    box = {"x1": 20, "y1": 20, "x2": 60, "y2": 60, "conf": 0.9, "img_w": 100, "img_h": 100}
    det.detect_best_box = lambda image: box
    img = Image.new("RGB", (100, 100))
    out_img, out_box = det.detect_and_crop(img)
    assert out_box is box
    assert out_img.size != (100, 100)  # cropped
    assert out_img.size[0] < 100 and out_img.size[1] < 100


# ──────────────────────────────────────────────────────────────────────────────
# config defaults
# ──────────────────────────────────────────────────────────────────────────────

def test_detector_config_defaults():
    """Defaults must match the canonical contract in synthet/image-scoring-model."""
    det = BirdDetector(config={}, device="cpu")
    assert det.enabled is True
    assert det.model_repo == "synthet/bird-detect-v0"
    assert det.model_file == "bird_detect_v0.pt"
    assert det.confidence == 0.25
    assert det.padding == 0.10
    assert det.imgsz == 640
    assert det.max_det == 10
    assert det.fail_open is True


def test_detector_config_overrides():
    det = BirdDetector(
        config={
            "enabled": False,
            "model_repo": "x/y",
            "confidence": 0.5,
            "padding": 0.2,
            "imgsz": 1280,
            "max_det": 3,
        },
        device="cpu",
    )
    assert det.enabled is False
    assert det.model_repo == "x/y"
    assert det.confidence == 0.5
    assert det.padding == 0.2
    assert det.imgsz == 1280
    assert det.max_det == 3


def test_detector_local_path_preferred_over_download(tmp_path):
    weights = tmp_path / "bird_detect_v0.pt"
    weights.write_bytes(b"stub")
    det = BirdDetector(config={"local_path": str(weights)}, device="cpu")
    # Must not attempt a HuggingFace download when a local file is present.
    assert det._resolve_weights_path() == str(weights)


# ──────────────────────────────────────────────────────────────────────────────
# detect_best_box — box payload (stubbed YOLO)
# ──────────────────────────────────────────────────────────────────────────────

class _FakeTensorVal:
    def __init__(self, value):
        self._value = value

    def item(self):
        return self._value


class _FakeXYXY:
    def __init__(self, coords):
        self._coords = coords

    def tolist(self):
        return list(self._coords)


class _FakeBox:
    def __init__(self, coords, conf):
        self.xyxy = [_FakeXYXY(coords)]
        self.conf = [_FakeTensorVal(conf)]


class _FakeResult:
    def __init__(self, boxes):
        self.boxes = boxes


class _FakeYOLO:
    def __init__(self, boxes):
        self._boxes = boxes
        self.predict_kwargs = None

    def predict(self, image, **kwargs):
        self.predict_kwargs = kwargs
        return [_FakeResult(self._boxes)]


def test_detect_best_box_payload_includes_area_frac():
    det = BirdDetector(config={}, device="cpu")
    # 40x40 box on a 100x100 image → area_frac = 1600 / 10000 = 0.16
    det.model = _FakeYOLO([_FakeBox((20.0, 20.0, 60.0, 60.0), 0.87)])
    box = det.detect_best_box(Image.new("RGB", (100, 100)))
    assert box["x1"] == 20 and box["y1"] == 20
    assert box["x2"] == 60 and box["y2"] == 60
    assert box["conf"] == 0.87
    assert box["img_w"] == 100 and box["img_h"] == 100
    assert box["area_frac"] == 0.16


def test_detect_best_box_passes_imgsz_and_max_det():
    det = BirdDetector(config={"imgsz": 960, "max_det": 4}, device="cpu")
    fake = _FakeYOLO([_FakeBox((0.0, 0.0, 10.0, 10.0), 0.5)])
    det.model = fake
    det.detect_best_box(Image.new("RGB", (100, 100)))
    assert fake.predict_kwargs["imgsz"] == 960
    assert fake.predict_kwargs["max_det"] == 4
    assert fake.predict_kwargs["conf"] == 0.25


def test_detect_best_box_returns_none_when_no_boxes():
    det = BirdDetector(config={}, device="cpu")
    det.model = _FakeYOLO([])
    assert det.detect_best_box(Image.new("RGB", (100, 100))) is None


def test_detect_best_box_picks_highest_of_several():
    det = BirdDetector(config={}, device="cpu")
    det.model = _FakeYOLO([
        _FakeBox((0.0, 0.0, 10.0, 10.0), 0.30),
        _FakeBox((10.0, 10.0, 50.0, 50.0), 0.95),
        _FakeBox((5.0, 5.0, 20.0, 20.0), 0.60),
    ])
    box = det.detect_best_box(Image.new("RGB", (100, 100)))
    assert box["conf"] == 0.95
    assert (box["x1"], box["y1"], box["x2"], box["y2"]) == (10, 10, 50, 50)


# ──────────────────────────────────────────────────────────────────────────────
# BioCLIPClassifier._ensure_detector — fail-open wiring (no BioCLIP load)
# ──────────────────────────────────────────────────────────────────────────────

def test_ensure_detector_disabled_via_config(monkeypatch):
    from modules.bird_species import BioCLIPClassifier

    class _FakeDetector:
        enabled = False

        def __init__(self, *a, **kw):
            pass

    monkeypatch.setattr("modules.bird_detection.BirdDetector", _FakeDetector)
    clf = BioCLIPClassifier(device="cpu")
    assert clf._ensure_detector() is None
    assert clf._detector_state == "disabled"


def test_ensure_detector_fail_open_on_load_error(monkeypatch):
    from modules.bird_species import BioCLIPClassifier

    class _FakeDetector:
        enabled = True

        def __init__(self, *a, **kw):
            pass

        def load_model(self):
            raise RuntimeError("weights unavailable")

    monkeypatch.setattr("modules.bird_detection.BirdDetector", _FakeDetector)
    clf = BioCLIPClassifier(device="cpu")
    assert clf._ensure_detector() is None
    assert clf._detector_state == "disabled"


def test_ensure_detector_enabled_and_cached(monkeypatch):
    from modules.bird_species import BioCLIPClassifier

    load_calls = []

    class _FakeDetector:
        enabled = True

        def __init__(self, *a, **kw):
            pass

        def load_model(self):
            load_calls.append(1)

    monkeypatch.setattr("modules.bird_detection.BirdDetector", _FakeDetector)
    clf = BioCLIPClassifier(device="cpu")
    det1 = clf._ensure_detector()
    det2 = clf._ensure_detector()
    assert det1 is det2
    assert clf._detector_state == "enabled"
    assert len(load_calls) == 1  # resolved once, not per call
