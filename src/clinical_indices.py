"""
Clinical Indices Module (Spec 07)

Calculates standard haemodynamic indices from validated beat data and patient metadata.
These are the "clinical" metrics typically reported in right heart catheterisation studies.
"""

import numpy as np
import pandas as pd
from typing import Optional, Any
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# Helper Functions
# =============================================================================

def _to_float(val: Any) -> Optional[float]:
    """
    Convert various types to float.
    
    Args:
        val: Value to convert (int, float, str, list, or None).
        
    Returns:
        Float value or None if conversion fails.
    """
    if val is None:
        return None
    
    try:
        if isinstance(val, (list, tuple)):
            # Take mean of list (e.g., CO measurements)
            return float(np.mean(val))
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_mean(df: pd.DataFrame, col: str) -> float:
    """
    Calculate mean of a column, handling missing columns and NaN values.
    
    Args:
        df: DataFrame to operate on.
        col: Column name.
        
    Returns:
        Mean value or NaN if column missing or all NaN.
    """
    if col not in df.columns:
        return np.nan
    return df[col].mean()


def _safe_std(df: pd.DataFrame, col: str) -> float:
    """
    Calculate standard deviation of a column, handling missing columns.
    
    Args:
        df: DataFrame to operate on.
        col: Column name.
        
    Returns:
        Std value or NaN if column missing or all NaN.
    """
    if col not in df.columns:
        return np.nan
    return df[col].std()


def _calculate_cv(df: pd.DataFrame, col: str) -> float:
    """
    Calculate coefficient of variation (CV = std/mean * 100).
    
    Args:
        df: DataFrame to operate on.
        col: Column name.
        
    Returns:
        CV as percentage, or NaN if mean is zero or column missing.
    """
    mean_val = _safe_mean(df, col)
    std_val = _safe_std(df, col)
    
    if np.isnan(mean_val) or np.isnan(std_val) or mean_val == 0:
        return np.nan
    
    return (std_val / mean_val) * 100


# =============================================================================
# Main Function
# =============================================================================

def calculate_clinical_indices(
    classified_beats: pd.DataFrame,
    metadata: Optional[dict] = None
) -> dict:
    """
    Calculate clinical haemodynamic indices from classified beat data.
    
    Args:
        classified_beats: DataFrame with columns including:
            - interval_status: 'ACCEPTED' or rejection status
            - anatomical_loc: 'PA', 'RV', or 'UNCERTAIN'
            - p_max, p_min_decay, p_mean, pulse_pressure, p_min_onset
        metadata: Optional dict with 'hemodynamics' section containing:
            - RA, RV, PA, Wedge (each with systolic/diastolic/mean)
            - CO (list of measurements)
            - HR (heart rate)
            
    Returns:
        Dict with sections: waveform, variability, derived, reference, quality
    """
    # -------------------------------------------------------------------------
    # Filter to accepted beats only
    # -------------------------------------------------------------------------
    accepted = classified_beats[
        classified_beats['interval_status'] == 'ACCEPTED'
    ].copy()
    
    # Filter by anatomical location
    pa_beats = accepted[accepted['anatomical_loc'] == 'PA']
    rv_beats = accepted[accepted['anatomical_loc'] == 'RV']
    
    n_pa = len(pa_beats)
    n_rv = len(rv_beats)
    
    logger.info(f"Clinical indices: {n_pa} PA beats, {n_rv} RV beats")
    
    # -------------------------------------------------------------------------
    # Waveform-Derived Indices
    # -------------------------------------------------------------------------
    waveform = {
        # PA-derived
        'sPAP': _safe_mean(pa_beats, 'p_max'),
        'dPAP': _safe_mean(pa_beats, 'p_min_decay'),
        'mPAP': _safe_mean(pa_beats, 'p_mean'),
        'PP': _safe_mean(pa_beats, 'pulse_pressure'),
        # RV-derived
        'sRVP': _safe_mean(rv_beats, 'p_max'),
        'dRVP': _safe_mean(rv_beats, 'p_min_onset'),
        # Sample counts
        'n_PA': n_pa,
        'n_RV': n_rv,
    }
    
    # -------------------------------------------------------------------------
    # Variability Statistics (PA only)
    # -------------------------------------------------------------------------
    variability = {
        'sPAP_SD': _safe_std(pa_beats, 'p_max'),
        'sPAP_CV': _calculate_cv(pa_beats, 'p_max'),
        'dPAP_SD': _safe_std(pa_beats, 'p_min_decay'),
        'PP_SD': _safe_std(pa_beats, 'pulse_pressure'),
    }
    
    # -------------------------------------------------------------------------
    # Reference Values from Metadata
    # -------------------------------------------------------------------------
    reference = {}
    hemo = metadata.get('hemodynamics', {}) if metadata else {}
    
    # Extract reference pressures
    for chamber, prefix in [('RA', 'RAP'), ('RV', 'RVP'), ('PA', 'PAP'), ('Wedge', 'PCWP')]:
        chamber_data = hemo.get(chamber, {})
        if isinstance(chamber_data, dict):
            reference[f's{prefix}_ref'] = _to_float(chamber_data.get('systolic'))
            reference[f'd{prefix}_ref'] = _to_float(chamber_data.get('diastolic'))
            reference[f'm{prefix}_ref'] = _to_float(chamber_data.get('mean'))
    
    # Cardiac output
    co_raw = hemo.get('CO')
    reference['mCO_ref'] = _to_float(co_raw)  # Mean of list if list
    reference['HR_ref'] = _to_float(hemo.get('HR'))
    
    # Store raw measurements if available (as comma-separated string)
    if isinstance(co_raw, (list, tuple)):
        reference['CO_measurements'] = ", ".join(map(str, co_raw))
    elif co_raw is not None:
        reference['CO_measurements'] = str(co_raw)
    else:
        reference['CO_measurements'] = None
    
    # Calculate stroke volume if CO and HR available
    co_ref = reference.get('mCO_ref')
    hr_ref = reference.get('HR_ref')
    if co_ref and hr_ref and hr_ref > 0:
        reference['SV_ref'] = (co_ref / hr_ref) * 1000  # mL
    else:
        reference['SV_ref'] = None

    # Calculate HR from waveform
    # mean_rr is in milliseconds. HR = 60000 / mean_rr
    mean_rr = _safe_mean(accepted, 'rr_interval')
    if not np.isnan(mean_rr) and mean_rr > 0:
        waveform['HR_calc'] = 60000.0 / mean_rr
    else:
        waveform['HR_calc'] = np.nan
        
    # Calculate SV using calculated HR
    hr_calc = waveform.get('HR_calc')
    if co_ref and hr_calc and not np.isnan(hr_calc) and hr_calc > 0:
        reference['SV_calc'] = (co_ref / hr_calc) * 1000 # mL
    else:
        reference['SV_calc'] = None
    
    # -------------------------------------------------------------------------
    # Derived Indices (require both waveform and reference)
    # -------------------------------------------------------------------------
    mPAP = waveform['mPAP']
    dPAP = waveform['dPAP']
    PP = waveform['PP']
    mPCWP = reference.get('mPCWP_ref')
    CO = reference.get('mCO_ref')
    SV_ref = reference.get('SV_ref')
    SV_calc = reference.get('SV_calc')
    
    derived = {}
    
    # Transpulmonary gradient
    if not np.isnan(mPAP) and mPCWP is not None:
        derived['TPG'] = mPAP - mPCWP
    else:
        derived['TPG'] = np.nan
    
    # Diastolic pressure gradient
    if not np.isnan(dPAP) and mPCWP is not None:
        derived['DPG'] = dPAP - mPCWP
    else:
        derived['DPG'] = np.nan
    
    # Pulmonary vascular resistance
    if not np.isnan(mPAP) and mPCWP is not None and CO is not None and CO > 0:
        derived['PVR'] = ((mPAP - mPCWP) / CO) * 80  # dyn·s·cm⁻⁵
        derived['PVR_WU'] = (mPAP - mPCWP) / CO  # Wood units
    else:
        derived['PVR'] = np.nan
        derived['PVR_WU'] = np.nan
    
    # --- Pulmonary Arterial Compliance (PAC) ---
    
    # 1. Reference PAC (using metadata HR)
    if SV_ref is not None and not np.isnan(PP) and PP > 0:
        derived['PAC_ref'] = SV_ref / PP  # mL/mmHg
    else:
        derived['PAC_ref'] = np.nan

    # 2. Calculated PAC (using waveform HR)
    if SV_calc is not None and not np.isnan(PP) and PP > 0:
        derived['PAC_calc'] = SV_calc / PP  # mL/mmHg
    else:
        derived['PAC_calc'] = np.nan
    
    # --- RC Time Constant ---
    
    # 1. Reference RC Time
    if not np.isnan(derived.get('PVR', np.nan)) and not np.isnan(derived.get('PAC_ref', np.nan)):
        # Convert to ms: PVR_WU (=PVR/80) × PAC gives seconds/1000, × 60 → ms
        derived['RC_time_ref'] = (derived['PVR'] * derived['PAC_ref'] / 80) * 60.0
    else:
        derived['RC_time_ref'] = np.nan

    # 2. Calculated RC Time
    if not np.isnan(derived.get('PVR', np.nan)) and not np.isnan(derived.get('PAC_calc', np.nan)):
        derived['RC_time_calc'] = (derived['PVR'] * derived['PAC_calc'] / 80) * 60.0
    else:
        derived['RC_time_calc'] = np.nan
    
    # -------------------------------------------------------------------------
    # Quality Metrics
    # -------------------------------------------------------------------------
    n_total = len(classified_beats)
    n_valid = len(accepted)
    
    quality = {
        'n_beats_total': n_total,
        'n_beats_valid': n_valid,
        'pct_valid': (n_valid / n_total * 100) if n_total > 0 else 0.0,
    }
    
    return {
        'waveform': waveform,
        'variability': variability,
        'derived': derived,
        'reference': reference,
        'quality': quality,
    }
