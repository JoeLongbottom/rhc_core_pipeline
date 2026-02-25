"""
Plotting Orchestrator Module

Central coordinator for all pipeline visualisation figures.

Memory strategy: save and close each figure immediately after generating it.
Figures are never all held in RAM simultaneously.
"""

import logging
from pathlib import Path
from typing import Optional

import matplotlib
import matplotlib.pyplot as plt

from .theme import apply_theme
from .plot_ecg_features import plot_ecg_features
from .plot_pressure_features import plot_pressure_features
from .plot_beat_gating import plot_beat_gating
from .plot_beat_classification import plot_beat_classification
try:
    from .plot_spectral_analysis import plot_spectral_analysis
    from .plot_brs import plot_brs
    from .plot_epoch_overview import plot_epoch_overview
    _HAS_AUTONOMIC_PLOTS = True
except ImportError:
    _HAS_AUTONOMIC_PLOTS = False

logger = logging.getLogger(__name__)


def run_plotting_pipeline(
    pipeline_data: dict,
    config: Optional[dict] = None
) -> list:
    """
    Generate all enabled figures from pipeline data.

    Each figure is saved to disk and immediately freed from memory.
    Figures are never all held in RAM simultaneously.

    Args:
        pipeline_data: Dictionary containing all signals and DataFrames from analysis.
        config: Plotting configuration dict (from plotting_config.yaml).

    Returns:
        List of saved figure names.
    """
    if config is None:
        config = {}

    # Apply global theme
    apply_theme(config)

    # Get output settings
    output_config = config.get('output', {})
    save_figures = output_config.get('save_figures', True)
    show_figures = output_config.get('show_figures', False)
    output_dir = Path(output_config.get('output_dir', 'output/plots'))
    fig_format = output_config.get('format', 'png')
    dpi = output_config.get('dpi', 150)
    recording_id = config.get('recording_id', '')
    prefix = f"{recording_id}_" if recording_id else ""

    if save_figures:
        output_dir.mkdir(parents=True, exist_ok=True)
        if not show_figures:
            # Memory optimisation: force non-interactive backend
            matplotlib.use('Agg')

    # Get figure toggles
    figures_config = config.get('figures', {})

    # Extract common data
    sampling_rate = pipeline_data.get('sampling_rate', 1000.0)
    ecg_signals = pipeline_data.get('ecg_signals', {})
    ecg_features = pipeline_data.get('ecg_features')
    pressure_signals = pipeline_data.get('pressure_signals', {})
    pressure_features = pipeline_data.get('pressure_features')
    gated_beats = pipeline_data.get('gated_beats')
    classified_beats = pipeline_data.get('classified_beats')
    autonomic_results = pipeline_data.get('autonomic_results', {})

    saved_names = []

    def _save_close(name: str, fig) -> None:
        """Save figure to disk and free its memory (unless showing interactively)."""
        if save_figures:
            filepath = output_dir / f"{prefix}{name}.{fig_format}"
            fig.savefig(filepath, dpi=dpi, bbox_inches='tight')
            logger.info(f"Saved: {filepath}")
        if not show_figures:
            plt.close(fig)
        saved_names.append(name)

    # -------------------------------------------------------------------------
    # Figure 1: ECG Features
    # -------------------------------------------------------------------------
    if figures_config.get('ecg_features', {}).get('enabled', True):
        if ecg_features is not None and len(ecg_features) > 0:
            logger.info("Generating ECG features figure...")
            try:
                fig = plot_ecg_features(
                    ecg_signals=ecg_signals,
                    ecg_features=ecg_features,
                    sampling_rate=sampling_rate,
                    config=config
                )
                _save_close('ecg_features', fig)
            except Exception as e:
                logger.error(f"ECG features figure failed: {e}")
        else:
            logger.warning("Skipping ECG features figure: no data available")

    # -------------------------------------------------------------------------
    # Figure 2: Pressure Features
    # -------------------------------------------------------------------------
    if figures_config.get('pressure_features', {}).get('enabled', True):
        if pressure_features is not None and len(pressure_features) > 0:
            logger.info("Generating pressure features figure...")
            try:
                r_peak_indices = (ecg_features['global_sample_idx'].values
                                  if ecg_features is not None else [])
                fig = plot_pressure_features(
                    pressure_signals=pressure_signals,
                    pressure_features=pressure_features,
                    r_peak_indices=r_peak_indices,
                    sampling_rate=sampling_rate,
                    config=config
                )
                _save_close('pressure_features', fig)
            except Exception as e:
                logger.error(f"Pressure features figure failed: {e}")
        else:
            logger.warning("Skipping pressure features figure: no data available")

    # -------------------------------------------------------------------------
    # Figure 3: Beat Gating
    # -------------------------------------------------------------------------
    if figures_config.get('beat_gating', {}).get('enabled', True):
        if gated_beats is not None and len(gated_beats) > 0:
            logger.info("Generating beat gating figure...")
            try:
                fig = plot_beat_gating(
                    ecg_signals=ecg_signals,
                    pressure_signals=pressure_signals,
                    gated_beats=gated_beats,
                    sampling_rate=sampling_rate,
                    config=config
                )
                _save_close('beat_gating', fig)
            except Exception as e:
                logger.error(f"Beat gating figure failed: {e}")
        else:
            logger.warning("Skipping beat gating figure: no data available")

    # -------------------------------------------------------------------------
    # Figure 4: Beat Classification
    # -------------------------------------------------------------------------
    if figures_config.get('beat_classification', {}).get('enabled', True):
        if classified_beats is not None and len(classified_beats) > 0:
            logger.info("Generating beat classification figure...")
            try:
                fig = plot_beat_classification(
                    ecg_signals=ecg_signals,
                    pressure_signals=pressure_signals,
                    classified_beats=classified_beats,
                    sampling_rate=sampling_rate,
                    config=config
                )
                _save_close('beat_classification', fig)
            except Exception as e:
                logger.error(f"Beat classification figure failed: {e}")
        else:
            logger.warning("Skipping beat classification figure: no data available")

    # -------------------------------------------------------------------------
    # Autonomic Figures (5–7)
    # -------------------------------------------------------------------------
    has_autonomic = _HAS_AUTONOMIC_PLOTS and bool(
        autonomic_results
        and len(autonomic_results.get('epoch_results', [])) > 0
    )

    # Figure 5: Spectral Analysis
    if figures_config.get('spectral_analysis', {}).get('enabled', True):
        if has_autonomic:
            logger.info("Generating spectral analysis figure...")
            try:
                figs = plot_spectral_analysis(
                    autonomic_results=autonomic_results,
                    config=config
                )
                for suffix, fig in figs.items():
                    name = f"spectral_analysis_{suffix}" if suffix != "None" else "spectral_analysis"
                    _save_close(name, fig)
            except Exception as e:
                logger.error(f"Spectral analysis figure failed: {e}")
        else:
            logger.warning("Skipping spectral analysis figure: no autonomic data")

    # Figure 6: BRS
    if figures_config.get('brs', figures_config.get('brs_coherence', {})).get('enabled', True):
        if has_autonomic:
            logger.info("Generating BRS figure...")
            try:
                figs = plot_brs(
                    autonomic_results=autonomic_results,
                    config=config
                )
                for suffix, fig in figs.items():
                    name = f"brs_{suffix}" if suffix != "None" else "brs"
                    _save_close(name, fig)
            except Exception as e:
                logger.error(f"BRS figure failed: {e}")
        else:
            logger.warning("Skipping BRS figure: no autonomic data")

    # Figure 7: Epoch Overview
    if figures_config.get('epoch_overview', {}).get('enabled', True):
        if has_autonomic and classified_beats is not None:
            logger.info("Generating epoch overview figure...")
            try:
                fig = plot_epoch_overview(
                    autonomic_results=autonomic_results,
                    classified_beats=classified_beats,
                    pressure_signals=pressure_signals,
                    sampling_rate=sampling_rate,
                    config=config
                )
                _save_close('epoch_overview', fig)
            except Exception as e:
                logger.error(f"Epoch overview figure failed: {e}")
        else:
            logger.warning("Skipping epoch overview figure: no autonomic data")

    if show_figures:
        print("\n(Close all figure windows to continue...)\n")
        plt.show()

    logger.info(f"Generated {len(saved_names)} figures")
    return saved_names
