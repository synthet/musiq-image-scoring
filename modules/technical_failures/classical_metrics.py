import logging

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None
from PIL import Image

logger = logging.getLogger(__name__)

#: Noise sigma (0-255 scale) that maps to a severity of 1.0. Sensor noise beyond
#: roughly this level is objectionable at any viewing size; below it the severity
#: scales linearly. An engineering default, not a validated cut-off.
_NOISE_SEVERITY_FULL_SCALE = 25.0


def _focus_metrics(gray, box=None) -> dict:
    """Blur and noise severities in 0-1, via the noise-aware scorer.

    Kept separate so both the OpenCV and the Pillow path share one definition of
    blur — they previously duplicated the formula, and duplicated its bug.
    """
    try:
        from modules.focus_quality import analyze

        result = analyze(np.asarray(gray, dtype=np.float64), box=box)
    except Exception as exc:  # noqa: BLE001 — a metric failure must not fail the image
        logger.warning("focus_quality failed, reporting no blur/noise: %s", exc)
        return {}
    return {
        # `blur` is already a 0-1 perceptual severity, so it needs no rescaling —
        # which was the second problem with `1 - lapvar/500`.
        "blur": round(float(result.blur), 4),
        "noise": round(min(1.0, result.noise_sigma / _NOISE_SEVERITY_FULL_SCALE), 4),
    }


def compute_classical_metrics(image_path: str, box=None) -> dict:
    """
    Computes classical image quality metrics for technical failure detection.
    Falls back to Pillow if OpenCV is not available.

    ``blur`` and ``noise`` come from :mod:`modules.focus_quality`, which estimates
    the sensor noise and subtracts it before judging sharpness. The previous
    formula here — ``1 - laplacian_variance / 500`` — could not work: on a
    defocused region, sigma=15 grain moved Laplacian variance from 0.019 to 4435,
    so a blurred high-ISO frame scored as tack sharp. See
    ``docs/reports/BIRD_CROP_FOCUS_MEASURES_2026-08-03.md``.

    ``box`` is an optional ``(x1, y1, x2, y2)`` subject rectangle. Supplying one
    scores the *subject* at native resolution instead of averaging over the whole
    frame, which measured 2.42x-17.51x less sensitive to subject-only degradation.
    """
    metrics = {
        "blur": 0.0,
        "overexposed": 0.0,
        "underexposed": 0.0,
        "highlight_clipping": 0.0,
        "shadow_crushing": 0.0,
        "noise": 0.0,
    }

    if cv2 is not None:
        try:
            # Read image in grayscale for blur and basic exposure
            # Use imread with IMREAD_GRAYSCALE to save memory
            img_gray = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
            if img_gray is None:
                return metrics

            # 1. Blur and noise, noise-aware (see module docstring).
            metrics.update(_focus_metrics(img_gray, box))

            # 2. Exposure & Clipping (Histogram)
            # Calculate percentages of pixels near 0 and 255
            total_pixels = img_gray.size
            hist = cv2.calcHist([img_gray], [0], None, [256], [0, 256])
            
            # Shadow crushing (pixels <= 5)
            shadow_pixels = np.sum(hist[:6])
            metrics["shadow_crushing"] = float(shadow_pixels / total_pixels)
            
            # Highlight clipping (pixels >= 250)
            highlight_pixels = np.sum(hist[250:])
            metrics["highlight_clipping"] = float(highlight_pixels / total_pixels)
            
            # Mean brightness
            mean_brightness = np.mean(img_gray)
            # Overexposed (mean > 200)
            if mean_brightness > 200:
                metrics["overexposed"] = float((mean_brightness - 200) / 55.0)
            # Underexposed (mean < 50)
            if mean_brightness < 50:
                metrics["underexposed"] = float((50 - mean_brightness) / 50.0)
                
            return metrics
        except Exception:
            pass # Fall back to PIL if cv2 fails

    # PIL Fallback
    try:
        with Image.open(image_path) as img:
            img_gray = img.convert('L')
            arr = np.array(img_gray)

            metrics.update(_focus_metrics(arr, box))

            # Exposure
            total_pixels = arr.size
            metrics["shadow_crushing"] = float(np.sum(arr <= 5) / total_pixels)
            metrics["highlight_clipping"] = float(np.sum(arr >= 250) / total_pixels)
            
            mean_brightness = np.mean(arr)
            if mean_brightness > 200:
                metrics["overexposed"] = float((mean_brightness - 200) / 55.0)
            if mean_brightness < 50:
                metrics["underexposed"] = float((50 - mean_brightness) / 50.0)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Classical metrics calculation failed: %s", e)

    return metrics
