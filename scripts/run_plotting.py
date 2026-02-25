#!/usr/bin/env python3
"""
Plotting Pipeline Runner

Generate figures from RHC analysis results.

Usage:
    python run_plotting.py --input output/analysis/recording_analysis.pkl \
                           --config config/plotting_config.yaml \
                           --output-dir output/plots \
                           --show
"""

import argparse
import logging
import pickle
import sys
from pathlib import Path

import yaml

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from plotting import run_plotting_pipeline

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config(config_path: Path) -> dict:
    """Load plotting configuration from YAML file."""
    if config_path.exists():
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    logger.warning(f"Config file not found: {config_path}, using defaults")
    return {}


def process_plotting(
    input_path: Path,
    output_dir: Path = None,
    config: dict = None,
    verbose: bool = False
) -> list[str]:
    """
    Process a single plotting task.
    
    Args:
        input_path: Path to analysis results pickle.
        output_dir: Optional override for output directory.
        config: Full configuration dictionary (merged).
        verbose: Enable verbose logging.
        
    Returns:
        List of generated figure names.
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        
    logger.info(f"Loading analysis results from: {input_path}")
    
    if not input_path.exists():
        logger.error(f"Input file not found: {input_path}")
        return []
    
    try:
        with open(input_path, 'rb') as f:
            pipeline_data = pickle.load(f)
        
        logger.info(f"Loaded data with {len(pipeline_data.get('ecg_features', []))} beats")
        
        # Determine output directory from input path if not overridden
        if output_dir:
            config.setdefault('output', {})['output_dir'] = str(output_dir)
        elif input_path.name == 'analysis.pkl':
            # Per-recording structure: output to {recording_id}/plots/
            plots_dir = input_path.parent / 'plots'
            config.setdefault('output', {})['output_dir'] = str(plots_dir)
            
        # Ensure output directory exists
        out_path = Path(config.get('output', {}).get('output_dir', 'output/plots'))
        out_path.mkdir(parents=True, exist_ok=True)
        
        # Run plotting pipeline
        figures = run_plotting_pipeline(pipeline_data, config)
        
        return figures
        
    except Exception as e:
        logger.error(f"Plotting failed for {input_path.name}: {e}")
        return []


def main():
    parser = argparse.ArgumentParser(
        description='Generate plots from RHC analysis results'
    )
    
    parser.add_argument(
        '--input', type=Path, required=True,
        help='Path to analysis results pickle file'
    )
    parser.add_argument(
        '--config', type=Path,
        default=Path('config/plotting_config.yaml'),
        help='Path to plotting config YAML'
    )
    parser.add_argument(
        '--pipeline-config', type=Path,
        default=Path('config/pipeline_config.yaml'),
        help='Path to pipeline config YAML (for thresholds)'
    )
    parser.add_argument(
        '--output-dir', type=Path,
        help='Output directory for figures (overrides config)'
    )
    parser.add_argument(
        '--format', type=str, choices=['png', 'pdf', 'svg'],
        help='Output format (overrides config)'
    )
    parser.add_argument(
        '--show', action='store_true',
        help='Display figures interactively'
    )
    parser.add_argument(
        '--no-save', action='store_true',
        help='Do not save figures to disk'
    )
    parser.add_argument(
        '--figures', type=str,
        help='Comma-separated list of figures to generate (e.g., "ecg_features,beat_gating")'
    )
    parser.add_argument(
        '-v', '--verbose', action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    # Load configurations
    plotting_config = load_config(args.config)
    pipeline_config = load_config(args.pipeline_config)
    
    # Merge pipeline config into plotting config for threshold access
    config = {**pipeline_config, **plotting_config}
    
    # Apply command-line overrides
    # Determine recording_id from path (handle both old and new structures)
    if args.input.name == 'analysis.pkl':
        recording_id = args.input.parent.name
    else:
        recording_id = args.input.stem.replace('_analysis', '')
    config['recording_id'] = recording_id
    
    if args.format:
        config.setdefault('output', {})['format'] = args.format
    
    if args.show:
        config.setdefault('output', {})['show_figures'] = True
    
    if args.no_save:
        config.setdefault('output', {})['save_figures'] = False
    
    # Filter figures if specified
    if args.figures:
        requested_figures = set(args.figures.split(','))
        figures_config = config.setdefault('figures', {})
        for fig_name in ['ecg_features', 'pressure_features', 'beat_gating', 'beat_classification']:
            figures_config.setdefault(fig_name, {})['enabled'] = fig_name in requested_figures
            
    figures = process_plotting(
        input_path=args.input,
        output_dir=args.output_dir, # Pass explicitly if None
        config=config,
        verbose=args.verbose
    )
    
    # Summary
    output_dir = config.get('output', {}).get('output_dir', 'output/plots')
    fig_format = config.get('output', {}).get('format', 'png')
    
    print(f"\n✓ Generated {len(figures)} figures")
    
    if not args.no_save:
        for name in figures:
            print(f"  → {output_dir}/{name}.{fig_format}")
    


if __name__ == '__main__':
    main()
