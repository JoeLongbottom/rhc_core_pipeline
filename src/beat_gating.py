"""
Beat Gating Module (Spec 05)

Apply quality control checks to each beat using both ECG and pressure features.
Assign status codes that determine eligibility for downstream analysis.

See: docs/specs/05_beat_gating.md
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# =============================================================================
# Status Code Constants
# =============================================================================

# ECG Status Codes
ECG_VALID = 'VALID'
ECG_NOISE = 'NOISE_ECG'
ECG_ARTIFACT_NOISE = 'ARTIFACT_NOISE'
ECG_ARTIFACT_MISSED = 'ARTIFACT_MISSED'
ECG_ECTOPIC_PREMATURE = 'ECTOPIC_PREMATURE'
ECG_ECTOPIC_PAUSE = 'ECTOPIC_PAUSE'
ECG_KUBIOS_ECTOPIC = 'KUBIOS_ECTOPIC'
ECG_KUBIOS_MISSED = 'KUBIOS_MISSED'
ECG_KUBIOS_EXTRA = 'KUBIOS_EXTRA'
ECG_KUBIOS_LONGSHORT = 'KUBIOS_LONGSHORT'

# Pressure Status Codes
PRES_VALID = 'VALID'
PRES_WHIP = 'WHIP_ARTIFACT'
PRES_PHANTOM = 'PHANTOM'
PRES_OUTLIER_JUMP = 'OUTLIER_JUMP'
PRES_OUTLIER_MEDIAN = 'OUTLIER_MEDIAN'
PRES_OUTLIER_PHYSIO = 'OUTLIER_PHYSIO'

# Interval Status Codes
INT_ACCEPTED = 'ACCEPTED'
INT_REJECT_ECG = 'REJECT_ECG'
INT_REJECT_PRESSURE = 'REJECT_PRESSURE'
INT_REJECT_GAP = 'REJECT_GAP'


def apply_beat_gating(
    ecg_features: pd.DataFrame,
    pressure_features: pd.DataFrame,
    config: Optional[dict] = None
) -> pd.DataFrame:
    """
    Apply quality control checks and Chain of Trust logic.
    
    Merges ECG and pressure features, applies all quality checks,
    and determines final interval status.
    
    Args:
        ecg_features: DataFrame from ecg_features.extract_ecg_features().
        pressure_features: DataFrame from pressure_features.extract_pressure_features().
        config: Optional configuration dict.
        
    Returns:
        Merged DataFrame with additional columns:
        - ecg_status: Signal quality of closing peak.
        - prev_ecg_status: Signal quality of opening peak.
        - pressure_status: Pressure quality status.
        - interval_status: Final verdict ('ACCEPTED' or 'REJECT_*').
    """
    # Default configuration
    if config is None:
        config = {}
    gate_config = config.get('beat_gating', {})
    
    # -------------------------------------------------------------------------
    # Step 1: Apply ECG Quality Checks
    # -------------------------------------------------------------------------
    ecg_with_status = _apply_ecg_quality_checks(ecg_features.copy(), gate_config)
    
    # -------------------------------------------------------------------------
    # Step 2: Apply Pressure Quality Checks
    # -------------------------------------------------------------------------
    pressure_with_status = _apply_pressure_quality_checks(pressure_features.copy(), gate_config)
    
    # -------------------------------------------------------------------------
    # Step 3: Merge DataFrames on global_sample_idx (Closing Index)
    # -------------------------------------------------------------------------
    # Pressure features are indexed by closing R-peak
    merged = pd.merge(
        ecg_with_status,
        pressure_with_status,
        on='global_sample_idx',
        how='left',
        suffixes=('', '_pres')
    )
    
    # -------------------------------------------------------------------------
    # Step 4: Get Previous ECG Status (Opening Pillar)
    # -------------------------------------------------------------------------
    merged['prev_ecg_status'] = merged['ecg_status'].shift(1)
    merged.loc[merged.index[0], 'prev_ecg_status'] = 'NO_PREDECESSOR'
    
    # -------------------------------------------------------------------------
    # Step 5: Apply Chain of Trust Logic
    # -------------------------------------------------------------------------
    merged = _apply_chain_of_trust(merged, gate_config)
    
    # -------------------------------------------------------------------------
    # Step 6: Clean up columns
    # -------------------------------------------------------------------------
    # Keep essential columns
    output_columns = [
        'global_sample_idx',
        'timestamp',
        'period_start_sample_idx',
        'sqi_average_qrs',
        'rr_interval',
        'sqi_zhao_class',
        'ecg_status',
        'prev_ecg_status',
        'p_max',
        'dpdt_max',
        'p_min_onset',
        't_zpoint',
        'pulse_pressure',
        'dpdt_min',
        'p_min_decay',
        'p_mean',
        'pressure_status',
        'interval_status'
    ]
    
    # Only keep columns that exist
    output_columns = [c for c in output_columns if c in merged.columns]
    result = merged[output_columns].copy()
    
    # Log summary
    n_total = len(result)
    n_accepted = (result['interval_status'] == INT_ACCEPTED).sum()
    pct_accepted = (n_accepted / n_total * 100) if n_total > 0 else 0
    
    logger.info(
        f"Beat gating complete: {n_accepted}/{n_total} beats ACCEPTED ({pct_accepted:.1f}%)"
    )
    
    return result


def _apply_ecg_quality_checks(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """
    Apply all ECG quality checks and assign ecg_status.
    
    Check order (first failing check wins):
    1. Global Zhao check (vetoes entire segment)
    2. Local SQI threshold
    3. Physiological limits
    4. Arrhythmia detection (20% rule)
    """
    sqi_threshold = config.get('sqi_threshold', 0.7)
    rr_min_ms = config.get('rr_min_ms', 300)
    rr_max_ms = config.get('rr_max_ms', 2000)
    ectopic_threshold = config.get('ectopic_threshold', 0.20)
    median_window = config.get('median_window', 5)
    
    # Initialise status to VALID
    df['ecg_status'] = ECG_VALID
    
    # --- Check 1: Global Zhao2018 Check ---
    # If ANY beat has 'Unacceptable', flag entire segment
    if 'sqi_zhao_class' in df.columns:
        if (df['sqi_zhao_class'] == 'Unacceptable').any():
            logger.warning("Global ECG quality check failed (Zhao2018: Unacceptable)")
            df['ecg_status'] = ECG_NOISE
            return df
    
    # --- Check 2: Local SQI Threshold ---
    if 'sqi_average_qrs' in df.columns:
        low_sqi_mask = df['sqi_average_qrs'] < sqi_threshold
        df.loc[low_sqi_mask, 'ecg_status'] = ECG_NOISE
    
    # --- Check 3: Physiological Limits ---
    if 'rr_interval' in df.columns:
        # Only update if still VALID
        valid_mask = df['ecg_status'] == ECG_VALID
        
        too_fast = valid_mask & (df['rr_interval'] < rr_min_ms) & df['rr_interval'].notna()
        too_slow = valid_mask & (df['rr_interval'] > rr_max_ms) & df['rr_interval'].notna()
        
        df.loc[too_fast, 'ecg_status'] = ECG_ARTIFACT_NOISE
        df.loc[too_slow, 'ecg_status'] = ECG_ARTIFACT_MISSED
    
    # --- Check 4: Arrhythmia Detection (20% Rule) ---
    if 'rr_interval' in df.columns:
        valid_mask = df['ecg_status'] == ECG_VALID
        
        # Calculate rolling median using only physiologically valid RRs
        rr_for_median = df['rr_interval'].copy()
        rr_for_median[(rr_for_median < rr_min_ms) | (rr_for_median > rr_max_ms)] = np.nan
        
        rolling_median = rr_for_median.rolling(
            window=median_window,
            center=True,
            min_periods=1
        ).median()
        
        # Premature: RR < (1 - threshold) × median
        premature_mask = (
            valid_mask &
            (df['rr_interval'] < (1 - ectopic_threshold) * rolling_median) &
            df['rr_interval'].notna()
        )
        
        # Pause: RR > (1 + threshold) × median
        pause_mask = (
            valid_mask &
            (df['rr_interval'] > (1 + ectopic_threshold) * rolling_median) &
            df['rr_interval'].notna()
        )
        
        df.loc[premature_mask, 'ecg_status'] = ECG_ECTOPIC_PREMATURE
        df.loc[pause_mask, 'ecg_status'] = ECG_ECTOPIC_PAUSE
    
    return df


def _apply_pressure_quality_checks(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """
    Apply all pressure quality checks and assign pressure_status.
    
    Check order (reordered for logical priority):
    1. Physiological range (basic sanity: is this even possible?)
    2. Slew rate limits (whip detection)
    3. Mechanical coupling (phantom detection)
    4. Sudden jump filter
    5. Rolling median filter
    """
    dp_dt_max_limit = config.get('dp_dt_max_limit', 1000)
    dp_dt_min_limit = config.get('dp_dt_min_limit', -1000)
    dp_dt_min_coupling = config.get('dp_dt_min_coupling', 10)
    jump_threshold = config.get('jump_threshold_mmhg', 20)
    rolling_pct = config.get('rolling_median_pct', 0.20)
    rolling_floor = config.get('rolling_median_floor', 4.0)
    rolling_window = config.get('rolling_median_window', 30)
    p_max_upper = config.get('p_max_upper', 200)
    p_max_lower = config.get('p_max_lower', 2)
    pp_min = config.get('pulse_pressure_min', 2)
    
    # Initialise status to VALID
    df['pressure_status'] = PRES_VALID
    
    if len(df) == 0:
        return df
    
    # --- Check 1: Physiological Range (Basic Sanity) ---
    # Run first: if pressure is physically impossible, no need for further checks
    if 'p_max' in df.columns and 'pulse_pressure' in df.columns:
        valid_mask = df['pressure_status'] == PRES_VALID
        
        physio_fail = valid_mask & (
            (df['p_max'] > p_max_upper) |
            (df['p_max'] < p_max_lower) |
            (df['pulse_pressure'] < pp_min)
        )
        
        df.loc[physio_fail, 'pressure_status'] = PRES_OUTLIER_PHYSIO
    
    # --- Check 2: Slew Rate Limits (Whip Detection) ---
    if 'dpdt_max' in df.columns and 'dpdt_min' in df.columns:
        valid_mask = df['pressure_status'] == PRES_VALID
        whip_mask = valid_mask & (
            (df['dpdt_max'] > dp_dt_max_limit) |
            (df['dpdt_min'] < dp_dt_min_limit)
        )
        df.loc[whip_mask, 'pressure_status'] = PRES_WHIP
    
    # --- Check 3: Mechanical Coupling (Phantom Detection) ---
    if 'dpdt_max' in df.columns:
        valid_mask = df['pressure_status'] == PRES_VALID
        phantom_mask = valid_mask & (df['dpdt_max'] < dp_dt_min_coupling)
        df.loc[phantom_mask, 'pressure_status'] = PRES_PHANTOM
    
    # --- Check 4: Sudden Jump Filter (Triplet Check) ---
    if 'p_max' in df.columns and len(df) >= 3:
        valid_mask = df['pressure_status'] == PRES_VALID
        p_max = df['p_max'].values
        
        for i in range(1, len(df) - 1):
            if not valid_mask.iloc[i]:
                continue
            
            # Check: (P[i] - P[i-1]) > threshold AND (P[i+1] - P[i]) < -threshold
            rise = p_max[i] - p_max[i - 1]
            fall = p_max[i + 1] - p_max[i]
            
            if rise > jump_threshold and fall < -jump_threshold:
                df.iloc[i, df.columns.get_loc('pressure_status')] = PRES_OUTLIER_JUMP
    
    # --- Check 5: Rolling Median Filter ---
    if 'p_max' in df.columns:
        valid_mask = df['pressure_status'] == PRES_VALID
        
        # Calculate rolling median
        rolling_median = df['p_max'].rolling(
            window=rolling_window,
            center=True,
            min_periods=1
        ).median()
        
        # Dynamic threshold: (Median × pct) + floor
        threshold = (rolling_median * rolling_pct) + rolling_floor
        
        deviation = np.abs(df['p_max'] - rolling_median)
        outlier_mask = valid_mask & (deviation > threshold)
        
        df.loc[outlier_mask, 'pressure_status'] = PRES_OUTLIER_MEDIAN
    
    return df


def _apply_chain_of_trust(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """
    Apply Chain of Trust logic to determine final interval status.
    
    A beat interval is only ACCEPTED if:
    1. Current beat (Closing Pillar) passes ECG checks
    2. Previous beat (Opening Pillar) passes ECG checks
    3. Current beat passes pressure checks
    4. Gap between beats is not too large
    """
    gap_max_ms = config.get('gap_max_ms', 3000)
    
    df['interval_status'] = INT_REJECT_ECG  # Default to reject
    
    # Define valid ECG statuses
    valid_ecg_statuses = {ECG_VALID}
    
    for i in range(len(df)):
        ecg_end_ok = df.iloc[i]['ecg_status'] in valid_ecg_statuses
        ecg_start_ok = df.iloc[i]['prev_ecg_status'] in valid_ecg_statuses
        
        # Check pressure status (may be NaN if merge failed)
        pres_status = df.iloc[i].get('pressure_status', PRES_VALID)
        pres_ok = pres_status == PRES_VALID
        
        # Check gap (RR interval not too long)
        rr = df.iloc[i].get('rr_interval', np.nan)
        gap_ok = pd.isna(rr) or rr < gap_max_ms
        
        if ecg_start_ok and ecg_end_ok and pres_ok and gap_ok:
            df.iloc[i, df.columns.get_loc('interval_status')] = INT_ACCEPTED
        elif not (ecg_start_ok and ecg_end_ok):
            df.iloc[i, df.columns.get_loc('interval_status')] = INT_REJECT_ECG
        elif not pres_ok:
            df.iloc[i, df.columns.get_loc('interval_status')] = INT_REJECT_PRESSURE
        else:
            df.iloc[i, df.columns.get_loc('interval_status')] = INT_REJECT_GAP
    
    return df
