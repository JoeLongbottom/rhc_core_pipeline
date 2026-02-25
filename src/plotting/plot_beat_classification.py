"""
Beat Classification Plot Module

Figure 4: Visualise anatomical location classification (RV vs PA).

Subplots:
1. Pressure timeseries with beats coloured by classification
2. ECG timeseries with same colouring
3+. Feature timeseries with classification thresholds
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from .theme import apply_theme, get_colors, create_figure

logger = logging.getLogger(__name__)


def plot_beat_classification(
    ecg_signals: dict,
    pressure_signals: dict,
    classified_beats: pd.DataFrame,
    sampling_rate: float,
    config: Optional[dict] = None
) -> plt.Figure:
    """
    Generate beat classification figure.
    
    Args:
        ecg_signals: Dictionary containing:
            - 'ecg_cleaned': Cleaned ECG waveform
        pressure_signals: Dictionary containing:
            - 'pressure_filtered': Filtered pressure waveform
        classified_beats: DataFrame from classify_beats() containing:
            - 'global_sample_idx': Closing R-peak indices
            - 'period_start_sample_idx': Opening R-peak indices
            - 'anatomical_loc': 'RV', 'PA', or 'UNCERTAIN'
            - 'p_max', 'p_min_decay': Features used for classification
        sampling_rate: Sampling rate in Hz
        config: Plotting configuration dict
        
    Returns:
        Matplotlib Figure object.
    """
    colors = apply_theme(config)
    
    fig_config = config.get('figures', {}).get('beat_classification', {}) if config else {}
    feature_subplots = fig_config.get('feature_subplots', ['p_max', 'p_min_decay'])
    
    # Determine number of subplots: 2 waveforms + N features
    n_feature_plots = len(feature_subplots)
    n_subplots = 2 + n_feature_plots
    
    # Height ratios: larger for waveforms, smaller for feature timeseries
    height_ratios = [2, 2] + [1] * n_feature_plots
    
    fig, axes = create_figure(n_subplots, config, sharex=True, height_ratios=height_ratios)
    
    # Get signals
    ecg_cleaned = ecg_signals.get('ecg_cleaned', np.array([]))
    pressure_filtered = pressure_signals.get('pressure_filtered', np.array([]))
    
    if len(ecg_cleaned) == 0 or len(pressure_filtered) == 0:
        logger.warning("No signal data available for classification plot")
        return fig
    
    time_ecg = np.arange(len(ecg_cleaned)) / sampling_rate
    time_pres = np.arange(len(pressure_filtered)) / sampling_rate
    
    # Get classification thresholds from config
    class_config = config.get('beat_classification', {}) if config else {}
    dia_separator = class_config.get('dia_separator', 10)
    min_valid_pressure = class_config.get('min_valid_pressure', -10)
    
    # Calculate adaptive threshold (P_active) from data if possible
    sys_hard_floor = class_config.get('sys_hard_floor', 25)
    sys_ref_percentile = class_config.get('sys_ref_percentile', 75)
    sys_tolerance = class_config.get('sys_tolerance', 0.25)
    
    p_active = None
    if 'p_max' in classified_beats.columns:
        valid_p_max = classified_beats.loc[classified_beats['p_max'] > sys_hard_floor, 'p_max']
        if len(valid_p_max) > 0:
            p_ref = np.percentile(valid_p_max, sys_ref_percentile)
            p_active = p_ref * (1 - sys_tolerance)
    
    # -------------------------------------------------------------------------
    # Helper: Colour beats by classification
    # -------------------------------------------------------------------------
    def colour_beats(ax, y_min, y_max):
        """Shade beat intervals based on anatomical classification."""
        for idx, row in classified_beats.iterrows():
            start_idx = int(row.get('period_start_sample_idx', 0))
            end_idx = int(row.get('global_sample_idx', 0))
            loc = row.get('anatomical_loc', 'UNCERTAIN')
            
            if start_idx < 0:
                continue
            
            t_start = start_idx / sampling_rate
            t_end = end_idx / sampling_rate
            
            # Determine colour
            if loc == 'RV':
                color = colors['rv']
            elif loc == 'PA':
                color = colors['pa']
            else:
                color = colors['uncertain']
            
            ax.axvspan(t_start, t_end, color=color, alpha=0.25, zorder=0)
    
    # -------------------------------------------------------------------------
    # Subplot 1: Pressure with classification
    # -------------------------------------------------------------------------
    ax1 = axes[0]
    ax1.plot(time_pres, pressure_filtered, color=colors['filtered'], linewidth=0.8)
    
    pres_min, pres_max = pressure_filtered.min(), pressure_filtered.max()
    colour_beats(ax1, pres_min, pres_max)
    
    ax1.set_ylabel('Pressure (mmHg)')
    ax1.set_title('Pressure: Anatomical Classification')
    
    # -------------------------------------------------------------------------
    # Subplot 2: ECG with classification
    # -------------------------------------------------------------------------
    ax2 = axes[1]
    ax2.plot(time_ecg, ecg_cleaned, color=colors['cleaned'], linewidth=0.8)
    
    ecg_min, ecg_max = ecg_cleaned.min(), ecg_cleaned.max()
    colour_beats(ax2, ecg_min, ecg_max)
    
    ax2.set_ylabel('Amplitude (mV)')
    ax2.set_title('ECG: Anatomical Classification')
    
    # Add legend
    rv_patch = mpatches.Patch(color=colors['rv'], alpha=0.3, label='RV')
    pa_patch = mpatches.Patch(color=colors['pa'], alpha=0.3, label='PA')
    unc_patch = mpatches.Patch(color=colors['uncertain'], alpha=0.3, label='Uncertain')
    ax1.legend(handles=[rv_patch, pa_patch, unc_patch], loc='upper right', ncol=3)
    
    # -------------------------------------------------------------------------
    # Feature Subplots (3+): Timeseries with thresholds
    # -------------------------------------------------------------------------
    beat_times = classified_beats['global_sample_idx'].values / sampling_rate
    
    for i, feature_name in enumerate(feature_subplots):
        ax = axes[2 + i]
        
        if feature_name not in classified_beats.columns:
            ax.set_title(f'{feature_name}: Data not available')
            continue
        
        feature_values = classified_beats[feature_name].values
        
        # Colour points by classification
        loc_colors = []
        for loc in classified_beats['anatomical_loc']:
            if loc == 'RV':
                loc_colors.append(colors['rv'])
            elif loc == 'PA':
                loc_colors.append(colors['pa'])
            else:
                loc_colors.append(colors['uncertain'])
        
        ax.scatter(beat_times, feature_values, c=loc_colors, s=20, zorder=5)
        ax.plot(beat_times, feature_values, color='grey', linewidth=0.5, alpha=0.5, zorder=1)
        
        # Add threshold lines based on feature
        if feature_name == 'p_max' and p_active is not None:
            ax.axhline(y=p_active, color=colors['rejected'], linestyle='--', 
                      linewidth=1.5, label=f'P_active ({p_active:.1f})')
            ax.legend(loc='lower right')
        
        elif feature_name == 'p_min_decay':
            # Adaptive Diastolic Threshold
            if p_active is not None:
                dia_factor = class_config.get('dia_factor', 0.33)
                dia_floor = class_config.get('dia_floor', 8.0)
                p_dia_thresh = max(p_active * dia_factor, dia_floor)
                
                ax.axhline(y=p_dia_thresh, color=colors['pa'], linestyle='--', 
                          linewidth=1.5, label=f'PA threshold ({p_dia_thresh:.1f})')
            else:
                 # Fallback if no active pressure
                 dia_floor = class_config.get('dia_floor', 8.0)
                 ax.axhline(y=dia_floor, color=colors['pa'], linestyle='--', 
                           linewidth=1.5, label=f'PA floor ({dia_floor})')

            ax.axhline(y=min_valid_pressure, color=colors['rejected'], linestyle=':', 
                      linewidth=1, label=f'Min valid ({min_valid_pressure})')
            ax.legend(loc='upper right')
        
        ax.set_ylabel(f'{feature_name}')
        ax.set_title(f'{feature_name} per Beat (Coloured by Classification)')
    
    # X-axis label on bottom subplot
    axes[-1].set_xlabel('Time (s)')
    
    # Summary statistics
    n_rv = (classified_beats['anatomical_loc'] == 'RV').sum()
    n_pa = (classified_beats['anatomical_loc'] == 'PA').sum()
    n_unc = (classified_beats['anatomical_loc'] == 'UNCERTAIN').sum()
    
    fig.suptitle(
        f'Beat Classification: {n_rv} RV, {n_pa} PA, {n_unc} Uncertain',
        fontsize=14, y=1.02
    )
    fig.tight_layout()
    
    return fig
