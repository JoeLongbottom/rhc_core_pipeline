"""
Plotting Package

Centralised visualisation pipeline for RHC analysis.
All figures share consistent theming and are configured via plotting_config.yaml.

Key constraint: NO CALCULATIONS in plotting code. All data comes from pipeline outputs.
"""

from .theme import apply_theme, get_colors
from .plotter import run_plotting_pipeline

__all__ = [
    'apply_theme',
    'get_colors',
    'run_plotting_pipeline',
]
