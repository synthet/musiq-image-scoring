import numpy as np
try:
    import cv2
except ImportError:
    cv2 = None
from PIL import Image

def compute_classical_metrics(image_path: str) -> dict:
    """
    Computes classical image quality metrics for technical failure detection.
    Falls back to Pillow if OpenCV is not available.
    """
    metrics = {
        "blur": 0.0,
        "overexposed": 0.0,
        "underexposed": 0.0,
        "highlight_clipping": 0.0,
        "shadow_crushing": 0.0
    }
    
    if cv2 is not None:
        try:
            # Read image in grayscale for blur and basic exposure
            # Use imread with IMREAD_GRAYSCALE to save memory
            img_gray = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
            if img_gray is None:
                return metrics
            
            # 1. Blur (Laplacian Variance)
            laplacian_var = cv2.Laplacian(img_gray, cv2.CV_64F).var()
            # Normalize blur (lower variance = higher blur). Cap at 1000 for normalization.
            # blur_score = 1.0 - min(laplacian_var / 500.0, 1.0)
            metrics["blur"] = max(0.0, 1.0 - (laplacian_var / 500.0))

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
            
            # Blur (3x3 Laplacian via numpy slices — no scipy dependency)
            center = arr[1:-1, 1:-1].astype(np.float64)
            laplacian = (
                -4.0 * center
                + arr[:-2, 1:-1]
                + arr[2:, 1:-1]
                + arr[1:-1, :-2]
                + arr[1:-1, 2:]
            )
            laplacian_var = float(np.var(laplacian))
            metrics["blur"] = max(0.0, 1.0 - (laplacian_var / 500.0))
            
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
