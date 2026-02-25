"""
Pressure Features Plot Module

Figure 2: Visualise pressure waveform analysis.

Subplots:
1. Raw + Filtered pressure (overlaid)
2. Filtered pressure with feature markers
3. Mean pressure timeseries
4. Pulse pressure timeseries
5. R-peak vertical lines (shared across all subplots)
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from .theme import apply_theme, get_colors, create_figure

logger = logging.getLogger(__name__)


def plot_pressure_features(
    pressure_signals: dict,
    pressure_features: pd.DataFrame,
    r_peak_indices: np.ndarray,
    sampling_rate: float,
    config: Optional[dict] = None
) -> plt.Figure:
    """
    Generate pressure features figure with 5 subplots.
    
    Args:
        pressure_signals: Dictionary from extract_pressure_features() containing:
            - 'pressure_raw': Original pressure waveform
            - 'pressure_filtered': Low-pass filtered waveform
            - 'dpdt': Derivative signal in mmHg/s
        pressure_features: DataFrame from extract_pressure_features() containing:
            - 'global_sample_idx': Closing R-peak indices
            - 'p_max', 'p_min_onset', 'p_min_decay': Pressure features
            - 'dpdt_max', 'dpdt_min': Derivative features
            - 't_zpoint': Z-point timing
            - 'p_mean', 'pulse_pressure': Derived features
        r_peak_indices: Array of R-peak sample indices
        sampling_rate: Sampling rate in Hz
        config: Plotting configuration dict
        
    Returns:
        Matplotlib Figure object.
    """
    colors = apply_theme(config)
    
    fig_config = config.get('figures', {}).get('pressure_features', {}) if config else {}
    show_r_peak_lines = fig_config.get('show_r_peak_lines', True)
    
    # Create figure with 5 subplots
    fig, axes = create_figure(5, config, sharex=True, height_ratios=[2, 2, 1, 1, 0.5])
    
    # Get signals
    pressure_raw = pressure_signals.get('pressure_raw', np.array([]))
    pressure_filtered = pressure_signals.get('pressure_filtered', np.array([]))
    dpdt = pressure_signals.get('dpdt', np.array([]))
    
    if len(pressure_raw) == 0:
        logger.warning("No pressure data available for plotting")
        return fig
    
    time = np.arange(len(pressure_raw)) / sampling_rate
    # Downsample raw signals for plotting to avoid memory hangs (~5000 points is plenty for display)
    target_pts = 5000
    n_pts = len(pressure_raw)
    ds = max(1, n_pts // target_pts)
    
    time_ds = time[::ds]
    pressure_raw_ds = pressure_raw[::ds]
    pressure_filtered_ds = pressure_filtered[::ds]
    
    # -------------------------------------------------------------------------
    # Subplot 1: Raw + Filtered Pressure
    # -------------------------------------------------------------------------
    ax1 = axes[0]
    ax1.plot(time_ds, pressure_raw_ds, color=colors['raw'], alpha=0.5, linewidth=0.5, label='Raw')
    ax1.plot(time_ds, pressure_filtered_ds, color=colors['filtered'], linewidth=0.8, label='Filtered')
    ax1.set_ylabel('Pressure (mmHg)')
    ax1.set_title('Pressure Signal: Raw vs Filtered')
    ax1.legend(loc='upper right')
    
    # -------------------------------------------------------------------------
    # Subplot 2: Filtered Pressure with Feature Markers
    # -------------------------------------------------------------------------
    ax2 = axes[1]
    ax2.plot(time_ds, pressure_filtered_ds, color=colors['filtered'], linewidth=0.8)
    
    # Downsample features for plotting markers (max 1000 beats to avoid hanging)
    if len(pressure_features) > 1000:
        step = len(pressure_features) // 1000
        feat_df_plot = pressure_features.iloc[::step].copy()
    else:
        feat_df_plot = pressure_features.copy()
        
    # Plot feature markers for each beat
    if len(feat_df_plot) > 0:
        # Get feature values at their sample locations
        for idx, row in feat_df_plot.iterrows():
            beat_start = int(row.get('period_start_sample_idx', 0))
            beat_end = int(row.get('global_sample_idx', 0))
            
            if beat_start < 0 or beat_end <= beat_start:
                continue
            if beat_end >= len(pressure_filtered):
                continue
                
            # Find p_max location (maximum in the beat window)
            beat_window = pressure_filtered[beat_start:beat_end]
            if len(beat_window) == 0:
                continue
            
            p_max_rel = np.argmax(beat_window)
            p_max_abs = beat_start + p_max_rel
            t_p_max = p_max_abs / sampling_rate
            
            # Plot p_max marker
            ax2.scatter(t_p_max, row['p_max'], color=colors['p_max'], s=20, marker='v', zorder=5)
            
            # Plot p_min_onset (in upstroke corridor)
            upstroke = beat_window[:p_max_rel + 1] if p_max_rel > 0 else beat_window[:1]
            if len(upstroke) > 0:
                p_min_onset_rel = np.argmin(upstroke)
                p_min_onset_abs = beat_start + p_min_onset_rel
                t_p_min_onset = p_min_onset_abs / sampling_rate
                ax2.scatter(t_p_min_onset, row['p_min_onset'], color=colors['p_min_onset'], 
                           s=20, marker='^', zorder=5)
            
            # Plot p_min_decay (in descent phase)
            descent = beat_window[p_max_rel:] if p_max_rel < len(beat_window) else beat_window[-1:]
            if len(descent) > 0:
                p_min_decay_rel = np.argmin(descent)
                p_min_decay_abs = beat_start + p_max_rel + p_min_decay_rel
                t_p_min_decay = p_min_decay_abs / sampling_rate
                ax2.scatter(t_p_min_decay, row['p_min_decay'], color=colors['p_min_decay'], 
                           s=20, marker='s', zorder=5)
    
    # Add legend for feature markers (only need one of each)
    ax2.scatter([], [], color=colors['p_max'], s=20, marker='v', label='P_max')
    ax2.scatter([], [], color=colors['p_min_onset'], s=20, marker='^', label='P_min_onset')
    ax2.scatter([], [], color=colors['p_min_decay'], s=20, marker='s', label='P_min_decay')
    ax2.set_ylabel('Pressure (mmHg)')
    ax2.set_title('Pressure Features')
    ax2.legend(loc='upper right', ncol=3)
    
    # -------------------------------------------------------------------------
    # Subplot 3: Mean Pressure Timeseries
    # -------------------------------------------------------------------------
    ax3 = axes[2]
    
    if len(pressure_features) > 0 and 'p_mean' in pressure_features.columns:
        beat_times = pressure_features['global_sample_idx'].values / sampling_rate
        ax3.plot(beat_times, pressure_features['p_mean'].values, 
                color=colors['filtered'], linewidth=1.5, marker='o', markersize=3)
    
    ax3.set_ylabel('P_mean (mmHg)')
    ax3.set_title('Mean Pressure per Beat')
    
    # -------------------------------------------------------------------------
    # Subplot 4: Pulse Pressure Timeseries
    # -------------------------------------------------------------------------
    ax4 = axes[3]
    
    if len(pressure_features) > 0 and 'pulse_pressure' in pressure_features.columns:
        beat_times = pressure_features['global_sample_idx'].values / sampling_rate
        ax4.plot(beat_times, pressure_features['pulse_pressure'].values, 
                color=colors['p_max'], linewidth=1.5, marker='o', markersize=3)
    
    ax4.set_ylabel('PP (mmHg)')
    ax4.set_title('Pulse Pressure per Beat')
    
    # -------------------------------------------------------------------------
    # Subplot 5: R-peak Markers (visual reference for all above)
    # -------------------------------------------------------------------------
    ax5 = axes[4]
    
    # R-peak markers as vertical lines
    if len(r_peak_indices) > 0:
        # Limit to 2000 features max
        step = max(1, len(r_peak_indices) // 2000)
        r_peak_times = r_peak_indices[::step] / sampling_rate
        ax5.eventplot([r_peak_times], colors=[colors['r_peaks']], lineoffsets=0.5, 
                      linelengths=0.8, linewidths=0.5)
        ax5.set_ylim(0, 1)
        ax5.set_yticks([])
    
    ax5.set_xlabel('Time (s)')
    ax5.set_title('R-Peak Markers')
    
    # -------------------------------------------------------------------------
    # Add vertical R-peak lines across all subplots (if enabled)
    # -------------------------------------------------------------------------
    if show_r_peak_lines and len(r_peak_indices) > 0:
        step = max(1, len(r_peak_indices) // 2000)
        r_peak_times = r_peak_indices[::step] / sampling_rate
        for ax in axes[:-1]:  # Exclude the R-peak marker subplot itself
            for t in r_peak_times:
                ax.axvline(x=t, color=colors['r_peaks'], alpha=0.2, linewidth=0.5, linestyle=':')
    
    fig.suptitle('Pressure Features Analysis', fontsize=14, y=1.02)
    fig.tight_layout()
    
    return fig
