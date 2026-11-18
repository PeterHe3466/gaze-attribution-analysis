import numpy as np
import pandas as pd


def screen_masks(data, roi):
    x = pd.to_numeric(data['filtered_gaze_pos_x'], errors='raise').to_numpy(dtype=float)
    y = pd.to_numeric(data['filtered_gaze_pos_y'], errors='raise').to_numpy(dtype=float)
    fx, fy = np.isfinite(x), np.isfinite(y)
    inside = fx & fy & (x >= roi['x_min']) & (x <= roi['x_max']) & (y >= roi['y_min']) & (y <= roi['y_max'])
    outside = (fx & ((x < roi['x_min']) | (x > roi['x_max']))) | (fy & ((y < roi['y_min']) | (y > roi['y_max'])))
    return inside, outside, data['Screen-Space_pupil'].notna().to_numpy()


def clean_pupil_artifacts(data, rules):
    """Repair boolean looking flags only; never alter pupil or gaze measurements.

    Preserve the historical single-frame pass followed by the two-frame pass.
    Observed points outside the screen ROI cannot be repaired as missing data.
    """
    result = data.copy()
    inside, outside, prior = screen_masks(result, rules['screen_roi'])
    original = (inside & prior).tolist()
    looking = original.copy()
    if rules['missing_gap_max_frames'] >= 1:
        for i in range(1, len(looking) - 1):
            if not looking[i] and not outside[i] and looking[i-1] and looking[i+1]:
                looking[i] = True
    if rules['missing_gap_max_frames'] >= 2:
        for i in range(1, len(looking) - 2):
            if (not looking[i] and not looking[i+1] and not outside[i] and not outside[i+1]
                    and looking[i-1] and looking[i+2]):
                looking[i] = looking[i+1] = True
    result['is_looking'] = looking
    return result, sum(a != b for a, b in zip(original, looking))


def check_validation_period(data, rules):
    window = data[data.frame_time.between(rules['validation_start_ms'], rules['validation_end_ms'])]
    if window.empty:
        return False, 0.0
    cleaned, _ = clean_pupil_artifacts(window, rules)
    proportion = float(cleaned.is_looking.mean())
    return proportion >= rules['validation_threshold'], proportion
