"""
Plotting Theme Module

Provides consistent styling across all pipeline figures.
"""

import logging
from typing import Optional

import matplotlib.pyplot as plt
import matplotlib as mpl

logger = logging.getLogger(__name__)

# Default theme configuration
DEFAULT_THEME = {
    'style': 'seaborn-v0_8-whitegrid',
    'font_family': 'sans-serif',
    'title_fontsize': 14,
    'label_fontsize': 11,
    'tick_fontsize': 9,
    'legend_fontsize': 9,
    'figure_width': 12,
}

DEFAULT_COLORS = {
    'raw': '#888888',
    'cleaned': '#2E86AB',
    'filtered': '#2E86AB',
    'r_peaks': '#E63946',
    'accepted': '#2A9D8F',
    'rejected': '#E63946',
    'rv': '#457B9D',
    'pa': '#E9C46A',
    'uncertain': '#AAAAAA',
    'p_max': '#E63946',
    'p_min_onset': '#2A9D8F',
    'p_min_decay': '#457B9D',
    'dpdt_max': '#F4A261',
    'dpdt_min': '#9B5DE5',
    't_zpoint': '#00F5D4',
    # Autonomic indices
    'lf_band': '#E9C46A',
    'hf_band': '#457B9D',
    'brs_up': '#2A9D8F',
    'brs_down': '#E63946',
    'epoch_boundary': '#666666',
    'welch': '#2E86AB',
    'lomb_scargle': '#F4A261',
}


def apply_theme(config: Optional[dict] = None) -> dict:
    """
    Apply consistent theme to matplotlib and return colour palette.
    
    Args:
        config: Plotting config dict (from plotting_config.yaml).
                Expected structure: {'theme': {...}, 'colors': {...}}
        
    Returns:
        Dictionary of named colours for use in plots.
    """
    if config is None:
        config = {}
    
    theme_config = config.get('theme', {})
    
    # Get theme settings with defaults
    style = theme_config.get('style', DEFAULT_THEME['style'])
    font_family = theme_config.get('font_family', DEFAULT_THEME['font_family'])
    title_fontsize = theme_config.get('title_fontsize', DEFAULT_THEME['title_fontsize'])
    label_fontsize = theme_config.get('label_fontsize', DEFAULT_THEME['label_fontsize'])
    tick_fontsize = theme_config.get('tick_fontsize', DEFAULT_THEME['tick_fontsize'])
    legend_fontsize = theme_config.get('legend_fontsize', DEFAULT_THEME['legend_fontsize'])
    
    # Apply matplotlib style
    try:
        plt.style.use(style)
    except OSError:
        logger.warning(f"Style '{style}' not found, falling back to default")
        plt.style.use('seaborn-v0_8-whitegrid')
    
    # Set font properties
    mpl.rcParams['font.family'] = font_family
    mpl.rcParams['axes.titlesize'] = title_fontsize
    mpl.rcParams['axes.labelsize'] = label_fontsize
    mpl.rcParams['xtick.labelsize'] = tick_fontsize
    mpl.rcParams['ytick.labelsize'] = tick_fontsize
    mpl.rcParams['legend.fontsize'] = legend_fontsize
    
    # Additional styling for publication-quality figures
    mpl.rcParams['axes.spines.top'] = False
    mpl.rcParams['axes.spines.right'] = False
    mpl.rcParams['figure.dpi'] = 100
    mpl.rcParams['savefig.dpi'] = 150
    mpl.rcParams['savefig.bbox'] = 'tight'
    mpl.rcParams['savefig.pad_inches'] = 0.1
    
    logger.debug(f"Applied theme: {style}")
    
    return get_colors(config)


def get_colors(config: Optional[dict] = None) -> dict:
    """
    Get colour palette from config or defaults.
    
    Args:
        config: Plotting config dict.
        
    Returns:
        Dictionary of named colours.
    """
    if config is None:
        return DEFAULT_COLORS.copy()
    
    theme_config = config.get('theme', {})
    color_config = theme_config.get('colors', {})
    
    # Merge with defaults
    colors = DEFAULT_COLORS.copy()
    colors.update(color_config)
    
    return colors


def get_figure_width(config: Optional[dict] = None) -> float:
    """
    Get standard figure width from config.
    
    Args:
        config: Plotting config dict.
        
    Returns:
        Figure width in inches.
    """
    if config is None:
        return DEFAULT_THEME['figure_width']
    
    theme_config = config.get('theme', {})
    return theme_config.get('figure_width', DEFAULT_THEME['figure_width'])


def create_figure(
    n_subplots: int,
    config: Optional[dict] = None,
    sharex: bool = True,
    height_ratios: Optional[list] = None
) -> tuple:
    """
    Create a figure with consistent sizing.
    
    Args:
        n_subplots: Number of subplots (stacked vertically).
        config: Plotting config dict.
        sharex: Whether to share x-axis across subplots.
        height_ratios: Optional list of height ratios for subplots.
        
    Returns:
        Tuple of (fig, axes) where axes is an array of Axes objects.
    """
    width = get_figure_width(config)
    height_per_subplot = 2.5  # inches per subplot
    total_height = height_per_subplot * n_subplots
    
    gridspec_kw = {}
    if height_ratios is not None:
        gridspec_kw['height_ratios'] = height_ratios
    
    fig, axes = plt.subplots(
        n_subplots, 1,
        figsize=(width, total_height),
        sharex=sharex,
        gridspec_kw=gridspec_kw if gridspec_kw else None
    )
    
    # Ensure axes is always an array
    if n_subplots == 1:
        axes = [axes]
    
    fig.tight_layout()
    
    return fig, axes
