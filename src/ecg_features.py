"""
ECG Features Module (Spec 03)

Process raw ECG signals to extract beat timing information (R-peaks),
calculate RR intervals, and assess signal quality for each detected beat.

See: docs/specs/03_ecg_features.md
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd
import neurokit2 as nk

from .utils import samples_to_time

logger = logging.getLogger(__name__)


def extract_ecg_features(
    ecg_signal: np.ndarray,
    sampling_rate: float,
    config: Optional[dict] = None,
    chunk_offset: int = 0
) -> tuple[pd.DataFrame, dict]:
    """
    Process raw ECG to extract R-peaks, RR intervals, and signal quality indices.
    
    This function implements the "Closing Index" convention where row i represents
    the cardiac cycle concluding at R-peak i.
    
    Args:
        ecg_signal: Raw ECG signal array.
        sampling_rate: Sampling rate in Hz (must be provided, no default).
        config: Optional configuration dict with keys from pipeline_config.yaml.
        chunk_offset: Global sample offset for chunked processing.
        
    Returns:
        Tuple of (features_df, signals_dict) where:
        
        features_df - DataFrame with columns:
        - global_sample_idx: Absolute sample index of the Closing R-peak.
        - timestamp: Time of the Closing R-peak (seconds).
        - period_start_sample_idx: Absolute sample index of the Opening R-peak.
        - sqi_average_qrs: Template match quality score (0.0 to 1.0).
        - rr_interval: Duration of interval in ms (NaN for first beat).
        - sqi_zhao_class: Categorical quality ('Excellent', 'Barely Acceptable', 'Unacceptable').
        
        signals_dict - Dictionary with keys:
        - 'ecg_raw': Original input ECG signal.
        - 'ecg_cleaned': Cleaned ECG signal (filtered).
        - 'ecg_quality': Continuous quality score array (0-1).
        - 'pqrst_features': (Optional) Full NeuroKit2 DataFrame with all detected
          cardiac events (P, Q, R, S, T peaks and onsets/offsets). Only included
          if config['ecg_features']['return_pqrst_features'] is True.
        
    Raises:
        ValueError: If sampling_rate is not provided or signal is too short.
    """
    # Default configuration
    if config is None:
        config = {}
    ecg_config = config.get('ecg_features', {})
    
    # Method configuration
    clean_method = ecg_config.get('clean_method', 'neurokit')
    peak_method = ecg_config.get('peak_method', 'kalidas2017')
    delineate_method = ecg_config.get('delineate_method', 'dwt')
    sqi_method = ecg_config.get('sqi_method', 'averageQRS')
    return_pqrst = ecg_config.get('return_pqrst_features', False)
    min_duration_sec = ecg_config.get('min_duration_sec', 10)
    
    # Validate inputs
    if sampling_rate is None or sampling_rate <= 0:
        raise ValueError("sampling_rate must be a positive number")
    
    signal_duration = len(ecg_signal) / sampling_rate
    if signal_duration < min_duration_sec:
        logger.warning(
            f"Signal duration ({signal_duration:.1f}s) is less than minimum "
            f"({min_duration_sec}s). R-peak detection may be unreliable."
        )
    
    # Check for flatline/disconnect
    signal_std = np.std(ecg_signal)
    if signal_std < 1e-6:
        logger.error("ECG signal appears to be flat (near-zero variance)")
        return _create_empty_ecg_dataframe(), {}
    
    try:
        # -------------------------------------------------------------------------
        # Step 1: ECG Cleaning
        # -------------------------------------------------------------------------
        ecg_cleaned = nk.ecg_clean(
            ecg_signal,
            sampling_rate=sampling_rate,
            method=clean_method
        )
        
        # -------------------------------------------------------------------------
        # Step 2: R-Peak Detection (configurable method)
        # -------------------------------------------------------------------------
        _, peaks_info = nk.ecg_peaks(
            ecg_cleaned,
            sampling_rate=sampling_rate,
            method=peak_method,
            correct_artifacts=False
        )
        r_peaks = peaks_info['ECG_R_Peaks']
        
        if len(r_peaks) == 0:
            logger.warning("No R-peaks detected in ECG signal")
            return _create_empty_ecg_dataframe(), {}
        
        logger.debug(f"Detected {len(r_peaks)} R-peaks using method '{peak_method}'")
        
        # -------------------------------------------------------------------------
        # Step 3: Signal Quality Assessment (Template Matching - Continuous)
        # -------------------------------------------------------------------------
        try:
            sqi_continuous = nk.ecg_quality(
                ecg_cleaned,
                rpeaks=r_peaks,
                sampling_rate=sampling_rate,
                method=sqi_method
            )
            # Ensure we have per-sample quality array
            if isinstance(sqi_continuous, (list, np.ndarray)):
                if len(sqi_continuous) == len(r_peaks):
                    # Per-beat quality, expand to per-sample (set at R-peaks)
                    sqi_at_peaks = np.array(sqi_continuous)
                    sqi_continuous = np.full(len(ecg_signal), np.nan)
                    sqi_continuous[r_peaks] = sqi_at_peaks
                elif len(sqi_continuous) == len(ecg_signal):
                    sqi_at_peaks = np.array(sqi_continuous)[r_peaks]
                else:
                    # Fallback
                    sqi_at_peaks = np.ones(len(r_peaks))
                    sqi_continuous = np.ones(len(ecg_signal))
            else:
                # Single value returned
                sqi_at_peaks = np.full(len(r_peaks), float(sqi_continuous))
                sqi_continuous = np.full(len(ecg_signal), float(sqi_continuous))
        except Exception as e:
            logger.warning(f"SQI calculation failed: {e}, using default values")
            sqi_at_peaks = np.ones(len(r_peaks))
            sqi_continuous = np.ones(len(ecg_signal))
        
        # -------------------------------------------------------------------------
        # Step 4: Zhao2018 Quality Assessment (Categorical)
        # -------------------------------------------------------------------------
        try:
            zhao_quality = nk.ecg_quality(
                ecg_cleaned,
                rpeaks=r_peaks,
                sampling_rate=sampling_rate,
                method='zhao2018'
            )
            # Zhao method returns a single categorical value for the chunk
            if isinstance(zhao_quality, str):
                sqi_zhao_array = np.full(len(r_peaks), zhao_quality)
            else:
                sqi_zhao_array = np.array(zhao_quality)
                if len(sqi_zhao_array) == 1:
                    sqi_zhao_array = np.full(len(r_peaks), sqi_zhao_array[0])
        except Exception as e:
            logger.warning(f"Zhao2018 quality assessment failed: {e}")
            sqi_zhao_array = np.full(len(r_peaks), 'Unknown')
        
        # -------------------------------------------------------------------------
        # Step 5: PQRST Delineation (Optional)
        # -------------------------------------------------------------------------
        pqrst_df = None
        if return_pqrst:
            try:
                _, waves = nk.ecg_delineate(
                    ecg_cleaned,
                    rpeaks=r_peaks,
                    sampling_rate=sampling_rate,
                    method=delineate_method
                )
                # waves is a dict with P_Peaks, Q_Peaks, S_Peaks, T_Peaks, etc.
                # NeuroKit doesn't include R_Peaks, so add them manually
                pqrst_df = pd.DataFrame(waves)
                pqrst_df['ECG_R_Peaks'] = r_peaks
                
                # Reorder columns logically: P -> Q -> R -> S -> T
                preferred_order = [
                    'ECG_P_Onsets', 'ECG_P_Peaks', 'ECG_P_Offsets',
                    'ECG_Q_Onsets', 'ECG_Q_Peaks', 'ECG_Q_Offsets',
                    'ECG_R_Onsets', 'ECG_R_Peaks', 'ECG_R_Offsets',
                    'ECG_S_Onsets', 'ECG_S_Peaks', 'ECG_S_Offsets',
                    'ECG_T_Onsets', 'ECG_T_Peaks', 'ECG_T_Offsets'
                ]
                existing_cols = [c for c in preferred_order if c in pqrst_df.columns]
                other_cols = [c for c in pqrst_df.columns if c not in existing_cols]
                pqrst_df = pqrst_df[existing_cols + other_cols]
                
                logger.debug(f"PQRST delineation complete using '{delineate_method}'")
            except Exception as e:
                logger.warning(f"PQRST delineation failed: {e}")
        
        # -------------------------------------------------------------------------
        # Step 6: Build Output DataFrame ("Closing Index" Convention)
        # -------------------------------------------------------------------------
        n_beats = len(r_peaks)
        
        # Global sample indices (accounting for chunk offset)
        global_sample_idx = r_peaks + chunk_offset
        
        # Timestamps
        timestamps = samples_to_time(r_peaks, sampling_rate)
        
        # Period start indices (previous R-peak)
        # First beat has no predecessor, set to NaN (will use -1 as sentinel)
        period_start_sample_idx = np.empty(n_beats, dtype=np.int64)
        period_start_sample_idx[0] = -1  # Sentinel for first beat
        period_start_sample_idx[1:] = global_sample_idx[:-1]
        
        # RR Intervals in milliseconds
        # Formula: RR[i] = (r_peak[i] - r_peak[i-1]) / sampling_rate * 1000
        rr_intervals = np.empty(n_beats)
        rr_intervals[0] = np.nan  # First beat has no preceding interval
        rr_intervals[1:] = np.diff(r_peaks) / sampling_rate * 1000
        
        # Build DataFrame
        result = pd.DataFrame({
            'global_sample_idx': global_sample_idx,
            'timestamp': timestamps,
            'period_start_sample_idx': period_start_sample_idx,
            'sqi_average_qrs': sqi_at_peaks,
            'rr_interval': rr_intervals,
            'sqi_zhao_class': sqi_zhao_array
        })
        
        # Build signals dictionary
        signals = {
            'ecg_raw': ecg_signal,
            'ecg_cleaned': ecg_cleaned,
            'ecg_quality': sqi_continuous
        }
        
        # Optionally include PQRST features
        if return_pqrst and pqrst_df is not None:
            signals['pqrst_features'] = pqrst_df
        
        logger.info(
            f"Extracted {n_beats} beats from ECG signal "
            f"(duration: {signal_duration:.1f}s, mean RR: {np.nanmean(rr_intervals):.0f}ms)"
        )
        
        return result, signals
        
    except Exception as e:
        logger.error(f"ECG processing failed: {e}")
        return _create_empty_ecg_dataframe(), {}


def _create_empty_ecg_dataframe() -> pd.DataFrame:
    """Create an empty DataFrame with the correct schema."""
    return pd.DataFrame({
        'global_sample_idx': pd.array([], dtype='int64'),
        'timestamp': pd.array([], dtype='float64'),
        'period_start_sample_idx': pd.array([], dtype='int64'),
        'sqi_average_qrs': pd.array([], dtype='float64'),
        'rr_interval': pd.array([], dtype='float64'),
        'sqi_zhao_class': pd.array([], dtype='object')
    })


def get_r_peak_indices(ecg_features: pd.DataFrame) -> np.ndarray:
    """
    Extract R-peak sample indices from ECG features DataFrame.
    
    This is a convenience function for passing to pressure_features.
    
    Args:
        ecg_features: DataFrame from extract_ecg_features().
        
    Returns:
        Array of R-peak sample indices.
    """
    return ecg_features['global_sample_idx'].values
