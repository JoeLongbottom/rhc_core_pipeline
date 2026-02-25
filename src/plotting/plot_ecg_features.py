"""
ECG Features Plot Module

Figure 1: Visualise ECG processing pipeline stages.

Subplots:
1. Raw + Cleaned ECG (overlaid)
2. Cleaned ECG with R-peak markers
3. Per-beat SQI (average QRS score)
4. PQRST timing markers (conditional on data availability)
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from .theme import apply_theme, get_colors, create_figure

logger = logging.getLogger(__name__)


def plot_ecg_features(
    ecg_signals: dict,
    ecg_features: pd.DataFrame,
    sampling_rate: float,
    config: Optional[dict] = None
) -> plt.Figure:
    """
    Generate ECG features figure with 3-4 subplots.
    
    Args:
        ecg_signals: Dictionary from extract_ecg_features() containing:
            - 'ecg_raw': Original ECG waveform
            - 'ecg_cleaned': Filtered ECG waveform
            - 'ecg_quality': Continuous SQI array
            - 'pqrst_features': (Optional) NeuroKit2 DataFrame
        ecg_features: DataFrame from extract_ecg_features() containing:
            - 'global_sample_idx': R-peak sample indices
            - 'sqi_average_qrs': Per-beat quality scores
            - 'timestamp': R-peak times in seconds
        sampling_rate: Sampling rate in Hz
        config: Plotting configuration dict
        
    Returns:
        Matplotlib Figure object.
    """
    colors = apply_theme(config)
    
    # Determine if PQRST subplot should be shown
    fig_config = config.get('figures', {}).get('ecg_features', {}) if config else {}
    show_pqrst = fig_config.get('show_pqrst', True)
    has_pqrst = 'pqrst_features' in ecg_signals and ecg_signals['pqrst_features'] is not None
    
    n_subplots = 4 if (show_pqrst and has_pqrst) else 3
    fig, axes = create_figure(n_subplots, config, sharex=True)
    
    # Create time axis
    ecg_raw = ecg_signals.get('ecg_raw', np.array([]))
    ecg_cleaned = ecg_signals.get('ecg_cleaned', np.array([]))
    
    if len(ecg_raw) == 0:
        logger.warning("No ECG data available for plotting")
        return fig
    
    time = np.arange(len(ecg_raw)) / sampling_rate
    
    # Get R-peak indices (local, not global)
    r_peak_indices = ecg_features['global_sample_idx'].values
    # Ensure indices are within bounds
    r_peak_indices = r_peak_indices[r_peak_indices < len(ecg_raw)]
    
    # -------------------------------------------------------------------------
    # Subplot 1: Raw + Cleaned ECG
    # -------------------------------------------------------------------------
    ax1 = axes[0]
    ax1.plot(time, ecg_raw, color=colors['raw'], alpha=0.5, linewidth=0.5, label='Raw ECG')
    ax1.plot(time, ecg_cleaned, color=colors['cleaned'], linewidth=0.8, label='Cleaned ECG')
    ax1.set_ylabel('Amplitude (mV)')
    ax1.set_title('ECG Signal: Raw vs Cleaned')
    ax1.legend(loc='upper right')
    
    # -------------------------------------------------------------------------
    # Subplot 2: Cleaned ECG with R-peaks
    # -------------------------------------------------------------------------
    ax2 = axes[1]
    ax2.plot(time, ecg_cleaned, color=colors['cleaned'], linewidth=0.8)
    
    # Plot R-peak markers
    if len(r_peak_indices) > 0:
        r_peak_times = r_peak_indices / sampling_rate
        r_peak_amplitudes = ecg_cleaned[r_peak_indices]
        ax2.scatter(
            r_peak_times, r_peak_amplitudes,
            color=colors['r_peaks'], s=30, zorder=5, label=f'R-peaks (n={len(r_peak_indices)})'
        )
    
    ax2.set_ylabel('Amplitude (mV)')
    ax2.set_title('R-Peak Detection')
    ax2.legend(loc='upper right')
    
    # -------------------------------------------------------------------------
    # Subplot 3: Per-beat SQI (Average QRS Score)
    # -------------------------------------------------------------------------
    ax3 = axes[2]
    
    sqi_scores = ecg_features['sqi_average_qrs'].values
    beat_times = ecg_features['timestamp'].values
    
    if len(sqi_scores) > 0:
        # Use stem plot for discrete per-beat values
        markerline, stemlines, baseline = ax3.stem(
            beat_times, sqi_scores,
            linefmt=colors['cleaned'], markerfmt='o',
            basefmt=' '
        )
        markerline.set_markersize(4)
        stemlines.set_linewidth(0.8)
        
        # Add threshold line (default 0.7)
        sqi_threshold = 0.7
        if config:
            sqi_threshold = config.get('beat_gating', {}).get('sqi_threshold', 0.7)
        ax3.axhline(y=sqi_threshold, color=colors['rejected'], linestyle='--', 
                    linewidth=1, label=f'Threshold ({sqi_threshold})')
    
    ax3.set_ylabel('SQI Score')
    ax3.set_ylim(0, 1.1)
    ax3.set_title('Average QRS Quality Score per Beat')
    ax3.legend(loc='lower right')
    
    # -------------------------------------------------------------------------
    # Subplot 4: PQRST Features (Conditional)
    # -------------------------------------------------------------------------
    if n_subplots == 4:
        ax4 = axes[3]
        pqrst_df = ecg_signals['pqrst_features']
        
        # Plot cleaned ECG as background
        ax4.plot(time, ecg_cleaned, color=colors['cleaned'], linewidth=0.5, alpha=0.5)
        
        # Define PQRST marker columns and colours
        pqrst_markers = {
            'ECG_P_Peaks': ('#2A9D8F', 'P'),
            'ECG_Q_Peaks': ('#457B9D', 'Q'),
            'ECG_R_Peaks': (colors['r_peaks'], 'R'),
            'ECG_S_Peaks': ('#9B5DE5', 'S'),
            'ECG_T_Peaks': ('#F4A261', 'T'),
        }
        
        for col, (color, label) in pqrst_markers.items():
            if col in pqrst_df.columns:
                # PQRST DataFrame contains sample indices (one per beat), not binary markers
                peak_indices = pqrst_df[col].dropna().astype(int).values
                
                if len(peak_indices) > 0:
                    # Ensure indices are within ECG signal bounds
                    peak_indices = peak_indices[peak_indices < len(ecg_cleaned)]
                    
                    if len(peak_indices) > 0:
                        peak_times = peak_indices / sampling_rate
                        peak_amplitudes = ecg_cleaned[peak_indices]
                        ax4.scatter(
                            peak_times, peak_amplitudes,
                            color=color, s=15, marker='o', label=label, alpha=0.8
                        )
        
        ax4.set_ylabel('Amplitude (mV)')
        ax4.set_title('PQRST Feature Detection')
        ax4.legend(loc='upper right', ncol=5)
    
    # Common x-axis label
    axes[-1].set_xlabel('Time (s)')
    
    fig.suptitle('ECG Features Analysis', fontsize=14, y=1.02)
    fig.tight_layout()
    
    return fig
