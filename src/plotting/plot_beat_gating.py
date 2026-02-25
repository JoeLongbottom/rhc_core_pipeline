"""
Beat Gating Plot Module

Figure 3: Visualise beat acceptance/rejection with clear reason labels.

Subplots:
1. ECG timeseries with beat regions shaded by status
2. Pressure timeseries with same shading
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from .theme import apply_theme, get_colors, create_figure

logger = logging.getLogger(__name__)


def plot_beat_gating(
    ecg_signals: dict,
    pressure_signals: dict,
    gated_beats: pd.DataFrame,
    sampling_rate: float,
    config: Optional[dict] = None
) -> plt.Figure:
    """
    Generate beat gating figure with accepted/rejected regions.
    
    Args:
        ecg_signals: Dictionary containing:
            - 'ecg_cleaned': Cleaned ECG waveform
        pressure_signals: Dictionary containing:
            - 'pressure_filtered': Filtered pressure waveform
        gated_beats: DataFrame from apply_beat_gating() containing:
            - 'global_sample_idx': Closing R-peak indices
            - 'period_start_sample_idx': Opening R-peak indices
            - 'interval_status': 'ACCEPTED' or 'REJECT_*'
            - 'ecg_status': ECG quality status
            - 'pressure_status': Pressure quality status
        sampling_rate: Sampling rate in Hz
        config: Plotting configuration dict
        
    Returns:
        Matplotlib Figure object.
    """
    colors = apply_theme(config)
    
    fig_config = config.get('figures', {}).get('beat_gating', {}) if config else {}
    
    # Create figure with 2 subplots
    fig, axes = create_figure(2, config, sharex=True)
    
    # Get signals
    ecg_cleaned = ecg_signals.get('ecg_cleaned', np.array([]))
    pressure_filtered = pressure_signals.get('pressure_filtered', np.array([]))
    
    if len(ecg_cleaned) == 0 or len(pressure_filtered) == 0:
        logger.warning("No signal data available for beat gating plot")
        return fig
    
    time_ecg = np.arange(len(ecg_cleaned)) / sampling_rate
    time_pres = np.arange(len(pressure_filtered)) / sampling_rate
    
    # -------------------------------------------------------------------------
    # Colour palette for rejection reasons
    # -------------------------------------------------------------------------
    REJECTION_COLORS = {
        'ACCEPTED': colors['accepted'],
        # ECG failures (red/orange tones)
        'NOISE_ECG': '#E63946',           # Red
        'LOW_SQI': '#E63946',              # Red
        'ECTOPIC_PREMATURE': '#F4A261',    # Orange
        # Pressure failures (distinct tones for visibility)
        'WHIP_ARTIFACT': '#9B5DE5',        # Purple
        'PHANTOM': '#06D6A0',              # Teal
        'OUTLIER_JUMP': '#F72585',         # Pink
        'OUTLIER_MEDIAN': '#FFB703',       # Amber
        'OUTLIER_PHYSIO': '#3A0CA3',       # Indigo
        # Other
        'GAP': '#6C757D',                  # Grey
        'UNKNOWN': '#ADB5BD',              # Light grey
    }
    
    def get_rejection_color(row):
        """Get colour based on rejection reason."""
        reason = _get_rejection_reason(row)
        # Handle PREV: prefix
        if reason.startswith('PREV:'):
            reason = reason[5:]
        return REJECTION_COLORS.get(reason, REJECTION_COLORS['UNKNOWN'])
    
    # Track which rejection types are present for legend
    rejection_types_present = set()
    
    # -------------------------------------------------------------------------
    # Helper: Shade beat regions with colour-coded rejection
    # -------------------------------------------------------------------------
    def shade_beats(ax, y_min, y_max):
        """Shade beat intervals with colour based on rejection reason."""
        for idx, row in gated_beats.iterrows():
            start_idx = int(row.get('period_start_sample_idx', 0))
            end_idx = int(row.get('global_sample_idx', 0))
            interval_status = row.get('interval_status', 'UNKNOWN')
            
            # Skip beats without valid start pillar
            if start_idx < 0:
                continue
            
            t_start = start_idx / sampling_rate
            t_end = end_idx / sampling_rate
            
            # Get colour based on status
            if interval_status == 'ACCEPTED':
                color = REJECTION_COLORS['ACCEPTED']
                alpha = 0.2
            else:
                color = get_rejection_color(row)
                alpha = 0.4
                # Track this rejection type for legend
                reason = _get_rejection_reason(row)
                if reason.startswith('PREV:'):
                    reason = reason[5:]
                rejection_types_present.add(reason)
            
            # Shade the region
            ax.axvspan(t_start, t_end, color=color, alpha=alpha, zorder=0)
    
    # -------------------------------------------------------------------------
    # Subplot 1: ECG with beat gating
    # -------------------------------------------------------------------------
    ax1 = axes[0]
    ax1.plot(time_ecg, ecg_cleaned, color=colors['cleaned'], linewidth=0.8)
    
    ecg_min, ecg_max = ecg_cleaned.min(), ecg_cleaned.max()
    ecg_range = ecg_max - ecg_min
    shade_beats(ax1, ecg_min - 0.1 * ecg_range, ecg_max + 0.1 * ecg_range)
    
    ax1.set_ylabel('Amplitude (mV)')
    ax1.set_title('ECG: Beat Gating Results')
    
    # -------------------------------------------------------------------------
    # Subplot 2: Pressure with beat gating
    # -------------------------------------------------------------------------
    ax2 = axes[1]
    ax2.plot(time_pres, pressure_filtered, color=colors['filtered'], linewidth=0.8)
    
    pres_min, pres_max = pressure_filtered.min(), pressure_filtered.max()
    pres_range = pres_max - pres_min
    shade_beats(ax2, pres_min - 0.1 * pres_range, pres_max + 0.1 * pres_range)
    
    ax2.set_ylabel('Pressure (mmHg)')
    ax2.set_xlabel('Time (s)')
    ax2.set_title('Pressure: Beat Gating Results')
    
    # -------------------------------------------------------------------------
    # Build colour-coded legend
    # -------------------------------------------------------------------------
    # Short labels for legend
    REASON_LABELS = {
        'NOISE_ECG': 'ECG: Low SQI',
        'LOW_SQI': 'ECG: Low SQI',
        'ECTOPIC_PREMATURE': 'ECG: Ectopic',
        'WHIP_ARTIFACT': 'Pres: Whip',
        'PHANTOM': 'Pres: Phantom',
        'OUTLIER_JUMP': 'Pres: Jump',
        'OUTLIER_MEDIAN': 'Pres: Median',
        'OUTLIER_PHYSIO': 'Pres: Physio',
        'GAP': 'Gap',
    }
    
    legend_handles = [
        mpatches.Patch(color=REJECTION_COLORS['ACCEPTED'], alpha=0.3, label='Accepted')
    ]
    
    # Add patches for each rejection type present in the data
    for reason in sorted(rejection_types_present):
        if reason in REJECTION_COLORS:
            label = REASON_LABELS.get(reason, reason)
            legend_handles.append(
                mpatches.Patch(color=REJECTION_COLORS[reason], alpha=0.5, label=label)
            )
    
    ax1.legend(handles=legend_handles, loc='upper right', fontsize=8, ncol=2)
    
    # Summary statistics
    n_total = len(gated_beats)
    n_accepted = (gated_beats['interval_status'] == 'ACCEPTED').sum()
    
    fig.suptitle(
        f'Beat Gating Analysis: {n_accepted}/{n_total} Accepted ({n_accepted/n_total*100:.1f}%)',
        fontsize=14, y=1.02
    )
    fig.tight_layout()
    
    return fig


def _get_rejection_reason(row: pd.Series) -> str:
    """
    Determine the primary rejection reason from beat status columns.
    
    Args:
        row: DataFrame row with status columns.
        
    Returns:
        Short rejection reason string.
    """
    interval_status = row.get('interval_status', '')
    
    if interval_status == 'REJECT_ECG':
        ecg_status = row.get('ecg_status', 'UNKNOWN')
        prev_ecg_status = row.get('prev_ecg_status', 'UNKNOWN')
        
        # Return the more specific status
        if ecg_status != 'VALID':
            return ecg_status
        elif prev_ecg_status not in ['VALID', 'NO_PREDECESSOR']:
            return f"PREV:{prev_ecg_status}"
        return 'ECG'
    
    elif interval_status == 'REJECT_PRESSURE':
        pressure_status = row.get('pressure_status', 'UNKNOWN')
        return pressure_status
    
    elif interval_status == 'REJECT_GAP':
        return 'GAP'
    
    return interval_status


def _get_rejection_reason_short(row: pd.Series) -> str:
    """
    Get abbreviated rejection reason for per-beat labels.
    
    Returns very short codes to fit in limited space.
    """
    # Map full reasons to abbreviated codes
    ABBREV = {
        'NOISE_ECG': 'E:SQI',
        'LOW_SQI': 'E:SQI', 
        'TECH_ECTOPIC': 'E:ECT',
        'PRES_WHIP': 'P:WHP',
        'PRES_PHANTOM': 'P:PHA',
        'PRES_JUMP': 'P:JMP',
        'PRES_OUTLIER_MEDIAN': 'P:MED',
        'PRES_OUTLIER_PHYSIO': 'P:PHY',
        'VALID': 'OK',
        'GAP': 'GAP',
        'UNKNOWN': '?',
    }
    
    reason = _get_rejection_reason(row)
    
    # Handle PREV: prefix
    if reason.startswith('PREV:'):
        inner = reason[5:]
        return 'E:P.' + ABBREV.get(inner, inner[:3])
    
    return ABBREV.get(reason, reason[:5])

