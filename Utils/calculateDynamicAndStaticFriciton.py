import numpy as np
import pandas as pd
from typing import Tuple, Dict, Any

def _rolling_median(x: np.ndarray, w: int) -> np.ndarray:
    """Centered rolling median using pandas (handles edges)."""
    return (
        pd.Series(x)
        .rolling(window=w, center=True, min_periods=1)
        .median()
        .to_numpy()
    )

def _rolling_mad(x: np.ndarray, w: int, med: np.ndarray) -> np.ndarray:
    """Centered rolling MAD (median absolute deviation)."""
    abs_dev = np.abs(x - med)
    return (
        pd.Series(abs_dev)
        .rolling(window=w, center=True, min_periods=1)
        .median()
        .to_numpy()
    )

def despike_force(
    df: pd.DataFrame,
    window: int = 21,
    n_sigmas: float = 6.0,
    replace_with: str = "median",  # "median" or "interp"
) -> pd.DataFrame:
    """
    Spike removal using a Hampel-style filter (rolling median + MAD).
    Marks points far from local median and replaces them.
    """
    out = df.copy()
    F = out["force"].to_numpy(dtype=float)

    if len(F) == 0:
        return out

    window = max(int(window), 3)
    if window % 2 == 0:
        window += 1

    med = _rolling_median(F, window)
    mad = _rolling_mad(F, window, med)

    # Convert MAD to sigma-like scale; avoid divide-by-zero
    scale = 1.4826 * mad
    scale[scale < 1e-12] = 1e-12

    mask = np.abs(F - med) > (n_sigmas * scale)

    if not np.any(mask):
        return out

    if replace_with == "median":
        F2 = F.copy()
        F2[mask] = med[mask]
        out["force"] = F2
        return out

    # replace_with == "interp"
    F2 = F.copy()
    F2[mask] = np.nan
    out["force"] = pd.Series(F2).interpolate(limit_direction="both").to_numpy()
    return out


def trim_after_motor_stop(
    df: pd.DataFrame,
    drop_sigmas: float = 8.0,
    min_consecutive: int = 2,
) -> pd.DataFrame:
    """
    Trim data after the motor stops by detecting the first *large, sustained*
    negative drop in force derivative.

    - Compute dF = diff(force)
    - Use robust scale (MAD) on dF
    - Find first index where dF < -drop_sigmas * scale for >= min_consecutive samples
    - Keep data up to that point (inclusive of the last "pre-drop" sample)
    """
    out = df.copy()
    t = out["time"].to_numpy(dtype=float)
    F = out["force"].to_numpy(dtype=float)

    n = len(F)
    if n < 3:
        return out

    dF = np.diff(F)

    # robust scale for dF
    dF_med = np.median(dF)
    mad = np.median(np.abs(dF - dF_med))
    scale = 1.4826 * mad
    if not np.isfinite(scale) or scale < 1e-12:
        # fallback: if scale degenerates, don't trim
        return out

    thr = -drop_sigmas * scale
    bad = dF < thr

    # require sustained drop: min_consecutive diffs in a row
    if min_consecutive <= 1:
        idxs = np.where(bad)[0]
        if len(idxs) == 0:
            return out
        cut_i = int(idxs[0])  # dF index; cut keeps up to sample cut_i
        return out.iloc[: cut_i + 1].reset_index(drop=True)

    run = 0
    start = None
    for i, is_bad in enumerate(bad):
        if is_bad:
            run += 1
            if start is None:
                start = i
            if run >= min_consecutive:
                cut_i = int(start)  # keep up to start sample (pre-drop)
                return out.iloc[: cut_i + 1].reset_index(drop=True)
        else:
            run = 0
            start = None

    return out


def clean_time_force_for_friction(
    df: pd.DataFrame,
    spike_window: int = 21,
    spike_sigmas: float = 6.0,
    drop_sigmas: float = 8.0,
    drop_min_consecutive: int = 2,
    spike_replace: str = "median",  # "median" or "interp"
) -> pd.DataFrame:
    """
    Full cleanup:
      1) Despike
      2) Trim after motor-stop drop
    """
    df1 = despike_force(df, window=spike_window, n_sigmas=spike_sigmas, replace_with=spike_replace)
    df2 = trim_after_motor_stop(df1, drop_sigmas=drop_sigmas, min_consecutive=drop_min_consecutive)
    return df2

def _first_increase_start_idx(F: np.ndarray) -> int:
    """
    Find where the first incremental (increasing) section begins.
    If force never increases, return 0.
    """
    if len(F) < 2:
        return 0
    dF = np.diff(F)
    inc = np.where(dF > 0)[0]
    return int(inc[0]) if len(inc) else 0


def _steady_decrease_trough_idx(F: np.ndarray, peak_idx: int) -> int:
    """
    From peak_idx onward, find the 'lowest force after a steady decrease'.

    Heuristic:
      - Look for the first decreasing run after the peak (diff < 0).
      - Extend the run while diffs stay <= 0 (monotone non-increasing).
      - Take the minimum force inside that run as the trough.
      - If no decreasing run exists, use the minimum of the remaining data.
    """
    n = len(F)
    if n == 0:
        return 0
    if peak_idx >= n - 1:
        return peak_idx

    post = F[peak_idx:]
    if len(post) < 2:
        return peak_idx

    dpost = np.diff(post)

    # where a decrease starts (first negative slope)
    neg = np.where(dpost < 0)[0]
    if len(neg) == 0:
        # no sustained decrease; just take global min after peak
        return int(peak_idx + np.argmin(post))

    dec_start = int(neg[0])  # index in dpost; corresponds to post[dec_start] -> post[dec_start+1] drop

    # extend while non-increasing (<= 0)
    k = dec_start
    while k < len(dpost) and dpost[k] <= 0:
        k += 1
    dec_end_exclusive = k + 1  # in 'post' indexing, include the last point of the run

    run = post[dec_start:dec_end_exclusive]
    trough_in_run = int(np.argmin(run))
    trough_idx = peak_idx + dec_start + trough_in_run
    return int(trough_idx)


def estimate_static_dynamic_forces(
    df: pd.DataFrame,
    include_peak_in_dynamic: bool = False
) -> Dict[str, Any]:
    """
    Implements your requested definitions:

    Static friction force:
      - Find first increasing point in the CSV (start of first incremental section)
      - Static = peak force after that point

    Dynamic friction force:
      - From that static peak onward, find the lowest force after a steady monotone decrease
      - Dynamic = mean force between peak and that trough (no minimum length requirement)

    Returns a dict with forces + index/time windows.
    """
    t = df["time"].to_numpy()
    F = df["force"].to_numpy()

    n = len(F)
    if n == 0:
        return {
            "Fs_max": np.nan,
            "Fk_mean": np.nan,
            "start_inc_idx": None,
            "peak_idx": None,
            "trough_idx": None,
            "static_time": (None, None),
            "dynamic_time": (None, None),
            "dynamic_n": 0,
        }

    # 1) start of first incremental section
    start_inc_idx = _first_increase_start_idx(F)

    # 2) static = peak after that
    peak_rel = int(np.argmax(F[start_inc_idx:])) if start_inc_idx < n else 0
    peak_idx = int(start_inc_idx + peak_rel)
    Fs_max = float(F[peak_idx])

    # 3) trough after a steady decrease (post-peak)
    trough_idx = _steady_decrease_trough_idx(F, peak_idx)

    # 4) dynamic segment = between peak and trough (tiny segments allowed)
    a = peak_idx if include_peak_in_dynamic else min(peak_idx + 1, n - 1)
    b = trough_idx

    if b < a:
        # if trough ended up before the dynamic start, fall back to a single-point segment at trough
        a = b

    seg = F[a:b + 1] if (0 <= a <= b < n) else np.array([], dtype=float)
    Fk_mean = float(np.mean(seg)) if len(seg) else float(F[trough_idx])

    return {
        "Fs_max": Fs_max,
        "Fk_mean": Fk_mean,
        "start_inc_idx": start_inc_idx,
        "peak_idx": peak_idx,
        "trough_idx": trough_idx,
        "static_time": (float(t[peak_idx]), float(t[peak_idx])),
        "dynamic_time": (float(t[a]), float(t[b])) if len(t) else (None, None),
        "dynamic_n": int(len(seg)),
    }

def load_time_force(filepath: str) -> pd.DataFrame:
    """
    Load CSV and return DataFrame with columns:
      - time (s, relative)
      - force
    """
    df = pd.read_csv(filepath)

    # --- time ---
    if "time" in df.columns:
        time = pd.to_numeric(df["time"], errors="coerce")
    elif "Host_Time_s" in df.columns:
        host = pd.to_numeric(df["Host_Time_s"], errors="coerce")
        time = host - host.iloc[0]
    else:
        raise ValueError("Missing time column")

    # --- force ---
    if "filtered_line" in df.columns:
        force = pd.to_numeric(df["filtered_line"], errors="coerce")
    elif "Filtered_Line" in df.columns:
        force = pd.to_numeric(df["Filtered_Line"], errors="coerce")
    elif "Raw_Data_Line" in df.columns:
        force = pd.to_numeric(df["Raw_Data_Line"], errors="coerce")
    else:
        raise ValueError("Missing force column")

    out = pd.DataFrame({"time": time, "force": force}).dropna()
    out = out.sort_values("time").reset_index(drop=True)

    if len(out) < 20:
        raise ValueError("Not enough valid samples")

    return out
