def calibrate_technical_failure_score(metrics: dict) -> float:
    """
    Converts raw classical metric scores (0-1) into a calibrated technical failure score (0-100).
    Uses a simple weighted max or sum approach for the MVP.
    """
    weights = {
        "blur": 100.0,
        "overexposed": 80.0,
        "underexposed": 80.0,
        "highlight_clipping": 90.0,
        "shadow_crushing": 70.0,
        # Below blur: heavy grain degrades an image but rarely ruins it outright,
        # and it is often a deliberate consequence of getting the shot at all.
        "noise": 60.0,
    }
    
    max_score = 0.0
    for key, weight in weights.items():
        val = metrics.get(key, 0.0)
        max_score = max(max_score, val * weight)
        
    return min(100.0, max_score)

def determine_primary_reject_reason(metrics: dict, threshold: float = 0.3) -> str:
    """
    Determines the primary reject reason based on severity thresholds.
    Tie-break priority (highest to lowest): blur > overexposed > underexposed > highlight_clipping > shadow_crushing > noise
    """
    # Priority order
    priorities = [
        "blur",
        "overexposed",
        "underexposed",
        "highlight_clipping",
        "shadow_crushing",
        "noise",
    ]
    
    # Return the first metric that exceeds the threshold (they are checked in priority order)
    # Or find the absolute maximum if multiple exceed threshold
    max_val = 0.0
    reason = "none"
    
    for key in priorities:
        val = metrics.get(key, 0.0)
        # If it's a severe defect and higher than what we've seen so far
        if val >= threshold and val > max_val:
            max_val = val
            reason = key
            
    return reason
