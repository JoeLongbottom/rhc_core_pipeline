"""
Pressure Features Module (Spec 04)

Extract haemodynamic features from RV and PA pressure waveforms.
Robust against respiratory baseline drift, catheter whip, and arrhythmia.

See: docs/specs/04_pressure_features.md
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd
from scipy.signal import butter, filtfilt, savgol_filter

from .utils import make_odd

logger = logging.getLogger(__name__)


def extract_pressure_features(
    pressure_signal: np.ndarray,
    r_peak_indices: np.ndarray,
    sampling_rate: float,
    config: Optional[dict] = None,
    chunk_offset: int = 0
) -> tuple[pd.DataFrame, dict]:
    """
    Extract haemodynamic features from pressure waveform using R-peaks as anchors.
    
    Implements the "Closing Index" convention where features for beat i are
    calculated within the interval [R_peak[i-1], R_peak[i]].
    
    Args:
        pressure_signal: Raw pressure signal array (mmHg).
        r_peak_indices: Array of R-peak sample indices (local to this chunk).
        sampling_rate: Sampling rate in Hz.
        config: Optional configuration dict.
        chunk_offset: Global sample offset for chunked processing.
        
    Returns:
        Tuple of (features_df, signals_dict) where:
        
        features_df - DataFrame with columns:
        - global_sample_idx: Closing R-peak index.
        - period_start_sample_idx: Opening R-peak index.
        - p_max: Systolic peak pressure (mmHg).
        - dpdt_max: Maximum upstroke slope (mmHg/s).
        - p_min_onset: Minimum pressure in upstroke corridor (mmHg).
        - t_zpoint: Z-point timing (seconds from chunk start).
        - pulse_pressure: p_max - p_min_onset (mmHg).
        - dpdt_min: Maximum downstroke slope (mmHg/s, negative value).
        - p_min_decay: Minimum pressure in descent phase (mmHg).
        - p_mean: Mean pressure over cycle (mmHg).
        
        signals_dict - Dictionary with keys:
        - 'pressure_raw': Original input pressure signal.
        - 'pressure_filtered': Low-pass filtered pressure signal.
        - 'dpdt': Derivative (dP/dt) signal in mmHg/s.
    """
    # Default configuration
    if config is None:
        config = {}
    pres_config = config.get('pressure_features', {})
    
    lowpass_cutoff = pres_config.get('lowpass_cutoff_hz', 25.0)
    lowpass_order = pres_config.get('lowpass_order', 4)
    savgol_window_sec = pres_config.get('savgol_window_sec', 0.025)
    savgol_polyorder = pres_config.get('savgol_polyorder', 2)
    
    # Convert R-peak indices to local if they include chunk_offset
    # (For this function we expect local indices)
    local_r_peaks = r_peak_indices - chunk_offset if chunk_offset > 0 else r_peak_indices
    
    n_beats = len(local_r_peaks)
    if n_beats < 2:
        logger.warning("Insufficient R-peaks for pressure feature extraction (need >= 2)")
        return _create_empty_pressure_dataframe(), {}
    
    # -------------------------------------------------------------------------
    # Step 1: Signal Conditioning
    # -------------------------------------------------------------------------
    # Low-pass Butterworth filter
    pressure_filtered = _apply_lowpass_filter(
        pressure_signal, lowpass_cutoff, lowpass_order, sampling_rate
    )
    
    # Calculate dP/dt using Savitzky-Golay derivative
    dpdt = _calculate_dpdt(
        pressure_filtered, sampling_rate, savgol_window_sec, savgol_polyorder
    )
    
    # -------------------------------------------------------------------------
    # Step 2: Per-Beat Feature Extraction
    # -------------------------------------------------------------------------
    # Initialise output arrays
    results = {
        'global_sample_idx': [],
        'period_start_sample_idx': [],
        'p_max': [],
        'dpdt_max': [],
        'p_min_onset': [],
        't_zpoint': [],
        'pulse_pressure': [],
        'dpdt_min': [],
        'p_min_decay': [],
        'p_mean': []
    }
    
    for i in range(1, n_beats):
        # Beat i: interval from R_peak[i-1] to R_peak[i]
        start_idx = int(local_r_peaks[i - 1])
        end_idx = int(local_r_peaks[i])
        
        # Validate window bounds
        if start_idx < 0 or end_idx > len(pressure_filtered) or start_idx >= end_idx:
            logger.debug(f"Skipping beat {i}: invalid window [{start_idx}, {end_idx}]")
            continue
        
        # Extract window data
        p_window = pressure_filtered[start_idx:end_idx]
        dpdt_window = dpdt[start_idx:end_idx]
        
        if len(p_window) == 0:
            continue
        
        # Global indices
        global_start = start_idx + chunk_offset
        global_end = end_idx + chunk_offset
        
        # --- Step 3.1: Global Maximum (P_max) ---
        p_max_rel_idx = np.argmax(p_window)
        p_max = p_window[p_max_rel_idx]
        p_max_abs_idx = start_idx + p_max_rel_idx
        
        # --- Step 3.2: Maximum Upstroke Slope (dP/dt_max) ---
        # Search window: Upstroke Window [R_peak[i-1], P_max_idx]
        upstroke_dpdt = dpdt_window[:p_max_rel_idx + 1] if p_max_rel_idx > 0 else dpdt_window[:1]
        if len(upstroke_dpdt) > 0:
            dpdt_max_rel_idx = np.argmax(upstroke_dpdt)
            dpdt_max = upstroke_dpdt[dpdt_max_rel_idx]
            dpdt_max_abs_idx = start_idx + dpdt_max_rel_idx
        else:
            dpdt_max = np.nan
            dpdt_max_rel_idx = 0
            dpdt_max_abs_idx = start_idx
        
        # --- Step 3.3: Upstroke Minimum (P_min_onset) ---
        upstroke_p = p_window[:p_max_rel_idx + 1] if p_max_rel_idx > 0 else p_window[:1]
        if len(upstroke_p) > 0:
            p_min_onset_rel_idx = np.argmin(upstroke_p)
            p_min_onset = upstroke_p[p_min_onset_rel_idx]
        else:
            p_min_onset = np.nan
        
        # --- Step 3.4: Z-Point Timing (T_zpoint) ---
        # Formula: T_zpoint = T_dpdt_max - (P_dpdt_max - P_min_onset) / dpdt_max
        if not np.isnan(dpdt_max) and dpdt_max > 0 and not np.isnan(p_min_onset):
            p_at_dpdt_max = p_window[dpdt_max_rel_idx] if dpdt_max_rel_idx < len(p_window) else p_window[0]
            t_dpdt_max = (dpdt_max_abs_idx) / sampling_rate
            t_zpoint = t_dpdt_max - (p_at_dpdt_max - p_min_onset) / dpdt_max
        else:
            t_zpoint = np.nan
        
        # --- Step 3.5: Pulse Pressure ---
        if not np.isnan(p_min_onset):
            pulse_pressure = p_max - p_min_onset
        else:
            pulse_pressure = np.nan
        
        # --- Step 3.6: Maximum Downstroke Slope (dP/dt_min) ---
        # Search window: Descent Phase [P_max_idx, R_peak[i]]
        descent_dpdt = dpdt_window[p_max_rel_idx:] if p_max_rel_idx < len(dpdt_window) else dpdt_window[-1:]
        if len(descent_dpdt) > 0:
            dpdt_min = np.min(descent_dpdt)  # Most negative value
        else:
            dpdt_min = np.nan
        
        # --- Step 3.7: Decay Minimum (P_min_decay) ---
        descent_p = p_window[p_max_rel_idx:] if p_max_rel_idx < len(p_window) else p_window[-1:]
        if len(descent_p) > 0:
            p_min_decay = np.min(descent_p)
        else:
            p_min_decay = np.nan
        
        # --- Mean Pressure ---
        p_mean = np.mean(p_window)
        
        # Store results
        results['global_sample_idx'].append(global_end)
        results['period_start_sample_idx'].append(global_start)
        results['p_max'].append(p_max)
        results['dpdt_max'].append(dpdt_max)
        results['p_min_onset'].append(p_min_onset)
        results['t_zpoint'].append(t_zpoint)
        results['pulse_pressure'].append(pulse_pressure)
        results['dpdt_min'].append(dpdt_min)
        results['p_min_decay'].append(p_min_decay)
        results['p_mean'].append(p_mean)
    
    # Build DataFrame
    result_df = pd.DataFrame(results)
    
    # Build signals dictionary
    signals = {
        'pressure_raw': pressure_signal,
        'pressure_filtered': pressure_filtered,
        'dpdt': dpdt
    }
    
    logger.info(
        f"Extracted pressure features for {len(result_df)} beats "
        f"(mean p_max: {result_df['p_max'].mean():.1f} mmHg)"
    )
    
    return result_df, signals


def _apply_lowpass_filter(
    signal: np.ndarray,
    cutoff: float,
    order: int,
    sampling_rate: float
) -> np.ndarray:
    """
    Apply zero-phase Butterworth low-pass filter.
    
    Args:
        signal: Input signal.
        cutoff: Cutoff frequency (Hz).
        order: Filter order.
        sampling_rate: Sampling rate (Hz).
        
    Returns:
        Filtered signal.
    """
    nyquist = sampling_rate / 2
    normalised_cutoff = cutoff / nyquist
    
    # Clamp to valid range
    normalised_cutoff = min(normalised_cutoff, 0.99)
    
    b, a = butter(order, normalised_cutoff, btype='low')
    
    # Use filtfilt for zero-phase filtering
    return filtfilt(b, a, signal)


def _calculate_dpdt(
    signal: np.ndarray,
    sampling_rate: float,
    window_sec: float,
    polyorder: int
) -> np.ndarray:
    """
    Calculate dP/dt using Savitzky-Golay derivative.
    
    Args:
        signal: Input pressure signal.
        sampling_rate: Sampling rate (Hz).
        window_sec: Window length in seconds.
        polyorder: Polynomial order.
        
    Returns:
        Derivative signal (mmHg/s).
    """
    # Convert window to samples (must be odd)
    window_samples = int(window_sec * sampling_rate)
    window_samples = make_odd(max(window_samples, polyorder + 2))
    
    # Ensure window doesn't exceed signal length
    if window_samples > len(signal):
        window_samples = make_odd(len(signal) - 1) if len(signal) > polyorder + 2 else polyorder + 2
    
    # Calculate derivative (deriv=1)
    # Multiply by sampling_rate to get mmHg/s
    dpdt = savgol_filter(signal, window_samples, polyorder, deriv=1) * sampling_rate
    
    return dpdt


def _create_empty_pressure_dataframe() -> pd.DataFrame:
    """Create an empty DataFrame with the correct schema."""
    return pd.DataFrame({
        'global_sample_idx': pd.array([], dtype='int64'),
        'period_start_sample_idx': pd.array([], dtype='int64'),
        'p_max': pd.array([], dtype='float64'),
        'dpdt_max': pd.array([], dtype='float64'),
        'p_min_onset': pd.array([], dtype='float64'),
        't_zpoint': pd.array([], dtype='float64'),
        'pulse_pressure': pd.array([], dtype='float64'),
        'dpdt_min': pd.array([], dtype='float64'),
        'p_min_decay': pd.array([], dtype='float64'),
        'p_mean': pd.array([], dtype='float64')
    })
