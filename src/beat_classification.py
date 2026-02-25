"""
Beat Classification Module (Spec 06)

Classify validated beats as Pulmonary Artery (PA) or UNCERTAIN based on
haemodynamic pressure features.

Current implementation: PA-only classification. RV and other chambers
are marked as UNCERTAIN (future work).

See: docs/specs/06_beat_classification.md
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# =============================================================================
# Classification Constants
# =============================================================================

LOC_PA = 'PA'
LOC_UNCERTAIN = 'UNCERTAIN'

# Retained for backwards compatibility but not used in classification
LOC_RV = 'RV'


def classify_beats(
    validated_beats: pd.DataFrame,
    config: Optional[dict] = None
) -> pd.DataFrame:
    """
    Classify beats as PA or UNCERTAIN.
    
    Uses a two-phase approach:
    1. Active Beat Check: Is the beat "active" (sufficient pressure)?
    2. PA Identification: Does diastolic pressure remain elevated?
    
    Args:
        validated_beats: DataFrame from beat_gating.apply_beat_gating().
        config: Optional configuration dict.
        
    Returns:
        DataFrame with added column:
        - anatomical_loc: 'PA' or 'UNCERTAIN'
    """
    # Default configuration
    if config is None:
        config = {}
    class_config = config.get('beat_classification', {})
    
    sys_hard_floor = class_config.get('sys_hard_floor', 25)
    sys_ref_percentile = class_config.get('sys_ref_percentile', 75)
    sys_tolerance = class_config.get('sys_tolerance', 0.25)
    dia_factor = class_config.get('dia_factor', 0.25)
    dia_floor = class_config.get('dia_floor', 8.0)
    
    # Create a copy to avoid modifying input
    df = validated_beats.copy()
    
    # Initialise classification to UNCERTAIN
    df['anatomical_loc'] = LOC_UNCERTAIN
    
    # Only process beats with valid pressure
    if 'pressure_status' not in df.columns:
        logger.warning("No pressure_status column found, skipping classification")
        return df
    
    valid_pressure_mask = df['pressure_status'] == 'VALID'
    
    if not valid_pressure_mask.any():
        logger.warning("No beats with valid pressure, skipping classification")
        return df
    
    # -------------------------------------------------------------------------
    # Phase A: Active Beat Check
    # -------------------------------------------------------------------------
    if 'p_max' not in df.columns:
        logger.warning("No p_max column found, skipping classification")
        return df
    
    # Reference population: beats with p_max > hard_floor
    reference_mask = valid_pressure_mask & (df['p_max'] > sys_hard_floor)
    
    if not reference_mask.any():
        logger.warning(
            f"No beats with p_max > {sys_hard_floor} mmHg, "
            "cannot establish reference population"
        )
        return df
    
    # Calculate Operating Pressure (P_ref) and Active Threshold (P_active)
    p_ref = np.percentile(df.loc[reference_mask, 'p_max'], sys_ref_percentile)
    p_active = p_ref * (1 - sys_tolerance)
    
    # Pulse Pressure Check
    pp_fraction = class_config.get('pp_fraction', 0.30)
    min_pp_threshold = p_active * pp_fraction
    
    logger.info(
        f"Classification thresholds: P_ref={p_ref:.1f} mmHg, "
        f"P_active={p_active:.1f} mmHg (tolerance={sys_tolerance*100:.0f}%), "
        f"Min PP={min_pp_threshold:.1f} mmHg (fraction={pp_fraction:.2f})"
    )
    
    # Filter: beats below P_active OR below Min PP remain UNCERTAIN
    active_mask = (
        valid_pressure_mask & 
        (df['p_max'] >= p_active) &
        (df['pulse_pressure'] >= min_pp_threshold)
    )
    
    # -------------------------------------------------------------------------
    # Phase B: PA Identification (Diastolic Check)
    # -------------------------------------------------------------------------
    if 'p_min_decay' not in df.columns:
        logger.warning("No p_min_decay column found, skipping classification")
        return df
    
    # Adaptive Diastolic Threshold: max(P_active * dia_factor, dia_floor)
    p_dia_thresh = max(p_active * dia_factor, dia_floor)
    
    logger.info(
        f"  → Diastolic Threshold: >= {p_dia_thresh:.1f} mmHg "
        f"(max({dia_factor} × P_active, {dia_floor}))"
    )
    
    # PA: Diastolic pressure remains elevated (pulmonic valve closed)
    pa_mask = active_mask & (df['p_min_decay'] >= p_dia_thresh)
    
    # Apply PA classification
    df.loc[pa_mask, 'anatomical_loc'] = LOC_PA
    
    # Log summary
    n_pa = pa_mask.sum()
    n_uncertain = (df['anatomical_loc'] == LOC_UNCERTAIN).sum()
    
    logger.info(f"Beat classification (Pre-adjacency): {n_pa} PA, {n_uncertain} UNCERTAIN")
    
    # -------------------------------------------------------------------------
    # Phase C: Adjacency Check (Remove isolated PA beats)
    # -------------------------------------------------------------------------
    df = apply_adjacency_filter(df)

    n_pa_final = (df['anatomical_loc'] == LOC_PA).sum()
    n_uncertain_final = (df['anatomical_loc'] == LOC_UNCERTAIN).sum()
    
    if n_pa_final < n_pa:
        logger.info(f"  → Adjacency filter removed {n_pa - n_pa_final} isolated PA beats")

    logger.info(f"Final classification: {n_pa_final} PA, {n_uncertain_final} UNCERTAIN")

    return df


def apply_adjacency_filter(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply adjacency filter to remove isolated PA beats.
    
    Rule: A PA beat must be adjacent to at least one other PA beat.
    Isolated PA beats (sequences of length 1) are reclassified as UNCERTAIN.
    
    Args:
        df: DataFrame with 'anatomical_loc' column.
        
    Returns:
        DataFrame with filtered 'anatomical_loc' column.
    """
    if 'anatomical_loc' not in df.columns:
        return df
    
    df = df.copy()
    locs = df['anatomical_loc'].values
    n = len(locs)
    
    if n < 3:
        # Cannot determine isolation reliably for tiny segments, 
        # or strict rule: if n=1 and PA -> isolated -> UNCERTAIN
        # For safety/consistency, strict rule:
        if n == 1 and locs[0] == LOC_PA:
            locs[0] = LOC_UNCERTAIN
        elif n == 2:
            # If both PA, keep. If one PA one UNCERTAIN, the PA is isolated -> UNCERTAIN
            if locs[0] == LOC_PA and locs[1] != LOC_PA:
                locs[0] = LOC_UNCERTAIN
            if locs[1] == LOC_PA and locs[0] != LOC_PA:
                locs[1] = LOC_UNCERTAIN
        df['anatomical_loc'] = locs
        return df

    # We need to find runs of 'PA' and check their length.
    # An efficient way is to find differences.
    
    # Create a boolean mask for PA
    is_pa = (locs == LOC_PA)
    
    # Identify run starts and ends
    # Values changes when diff != 0
    # Append False at ends to capture boundary changes cleanly
    padded = np.concatenate(([False], is_pa, [False]))
    diff = padded[1:] != padded[:-1]
    indices = np.where(diff)[0]
    
    # Current implementation: indices come in pairs (start, end) because we padded with False
    # is_pa[start:end] are all True (PA beats)
    
    for i in range(0, len(indices), 2):
        start = indices[i]
        end = indices[i+1]
        length = end - start
        
        # If run length is 1, it's an isolated beat
        if length == 1:
            locs[start] = LOC_UNCERTAIN
            
    df['anatomical_loc'] = locs
    return df
