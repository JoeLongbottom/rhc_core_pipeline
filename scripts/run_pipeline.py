#!/usr/bin/env python3
"""
Pipeline Orchestrator

Runs the full RHC analysis pipeline (Ingestion -> Analysis -> Plotting)
in parallel using multiple CPU cores.

Output structure (per-recording):
    output/{recording_id}/
    ├── waveform.csv
    ├── metadata.json
    ├── beats.xlsx
    ├── analysis.pkl
    ├── intermediates/*.csv
    └── plots/*.png

Usage:
    # Files co-located in the same directory:
    python scripts/run_pipeline.py --input-dir data/raw --output-dir output --workers -1

    # Files in separate directories:
    python scripts/run_pipeline.py --mat-dir data/mat --adicht-dir data/adicht --output-dir output --workers -1
"""

import argparse
import logging
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import processing functions from sibling scripts
sys.path.insert(0, str(Path(__file__).parent))

from run_ingestion import process_single_file
from run_analysis import process_analysis, load_config
from run_plotting import process_plotting
from src.utils import resolve_workers

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_ingestion_parallel(
    files: list[tuple[Path, Path]],
    output_dir: Path,
    skip_clinical: bool,
    max_workers: int
) -> list[Path]:
    """
    Run ingestion in parallel.
    
    Each file pair is ingested to output_dir/{recording_id}/.
    Returns list of waveform.csv paths.
    """
    logger.info(f"Starting INGESTION on {len(files)} files via {max_workers} workers...")
    
    generated_csvs = []
    
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {
            executor.submit(
                process_single_file, 
                mat_path, 
                adicht_path, 
                output_dir,  # Base output dir; function creates per-recording subdir
                skip_clinical, 
                False  # verbose
            ): mat_path 
            for mat_path, adicht_path in files
        }
        
        for future in as_completed(future_to_file):
            mat_path = future_to_file[future]
            try:
                success = future.result()
                if success:
                    # Output is now at output_dir/{recording_id}/waveform.csv
                    csv_path = output_dir / mat_path.stem / "waveform.csv"
                    if csv_path.exists():
                        generated_csvs.append(csv_path)
                    logger.info(f"  ✓ Ingested: {mat_path.name}")
                else:
                    logger.error(f"  ✗ Failed: {mat_path.name}")
            except Exception as e:
                logger.error(f"  ✗ Exception for {mat_path.name}: {e}")
                
    return generated_csvs


def run_analysis_parallel(
    input_files: list[Path],
    config_path: Path,
    sampling_rate: float,
    max_workers: int
) -> list[Path]:
    """
    Run analysis in parallel.
    
    Each waveform.csv is analyzed; output goes to same recording directory.
    Returns list of analysis.pkl paths.
    """
    logger.info(f"Starting ANALYSIS on {len(input_files)} files via {max_workers} workers...")
    
    generated_pkls = []
    
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {
            executor.submit(
                process_analysis,
                csv_path,
                csv_path.parent,  # output_dir = same directory as input
                config_path,
                sampling_rate,
                None,  # metadata path (inferred from sibling)
                False  # verbose
            ): csv_path
            for csv_path in input_files
        }
        
        for future in as_completed(future_to_file):
            csv_path = future_to_file[future]
            try:
                success = future.result()
                if success:
                    pkl_path = csv_path.parent / "analysis.pkl"
                    if pkl_path.exists():
                        generated_pkls.append(pkl_path)
                    logger.info(f"  ✓ Analyzed: {csv_path.parent.name}")
                else:
                    logger.error(f"  ✗ Analysis Failed: {csv_path.parent.name}")
            except Exception as e:
                logger.error(f"  ✗ Analysis Exception {csv_path.parent.name}: {e}")
                
    return generated_pkls


def run_plotting_parallel(
    input_files: list[Path],
    config: dict,
    max_workers: int
) -> int:
    """
    Run plotting in parallel.
    
    Each analysis.pkl generates plots in sibling plots/ directory.
    """
    # Memory optimisation: Use available workers as configured
    plot_workers = max_workers
    logger.info(
        f"Starting PLOTTING on {len(input_files)} files "
        f"({plot_workers} workers)"
    )
    
    total_figures = 0
    
    with ProcessPoolExecutor(max_workers=plot_workers) as executor:
        future_to_file = {
            executor.submit(
                process_plotting,
                pkl_path,
                None,  # output_dir inferred from pkl_path location
                config,
                False
            ): pkl_path
            for pkl_path in input_files
        }
        
        for future in as_completed(future_to_file):
            pkl_path = future_to_file[future]
            try:
                figs = future.result()
                total_figures += len(figs)
                logger.info(f"  ✓ Plotted: {pkl_path.parent.name} ({len(figs)} figures)")
            except Exception as e:
                logger.error(f"  ✗ Plotting Exception {pkl_path.parent.name}: {e}")
                
    return total_figures


def main():
    parser = argparse.ArgumentParser(description='RHC Parallel Pipeline Orchestrator')
    
    # Input/Output
    parser.add_argument('--input-dir', type=Path, default=None,
                        help='Input directory containing co-located MAT and ADICHT files')
    parser.add_argument('--mat-dir', type=Path, default=None,
                        help='Directory containing .mat files (use with --adicht-dir when files are in separate folders)')
    parser.add_argument('--adicht-dir', type=Path, default=None,
                        help='Directory containing .adicht files (use with --mat-dir when files are in separate folders)')
    parser.add_argument('--output-dir', type=Path, required=True, help='Root output directory')
    
    # Config
    parser.add_argument('--config', type=Path, default=Path('config/pipeline_config.yaml'), help='Pipeline config')
    parser.add_argument('--plotting-config', type=Path, default=Path('config/plotting_config.yaml'), help='Plotting config')
    
    # Execution Control
    parser.add_argument('--steps', choices=['all', 'ingestion', 'analysis', 'plotting'], default='all', help='Steps to run')
    parser.add_argument('--workers', type=int, default=4, help='Number of parallel workers (-1 = use all available cores)')
    parser.add_argument('--sampling-rate', type=float, help='Override sampling rate during analysis')
    parser.add_argument('--skip-clinical', action='store_true', help='Skip clinical metadata extraction during ingestion')
    parser.add_argument('--show', action='store_true', help='Show plots interactively (forces single worker)')
    
    args = parser.parse_args()
    
    # --- Validate input arguments ---
    has_input_dir = args.input_dir is not None
    has_split_dirs = args.mat_dir is not None or args.adicht_dir is not None
    
    if has_input_dir and has_split_dirs:
        parser.error("Cannot use --input-dir together with --mat-dir/--adicht-dir. Use one or the other.")
    
    if has_split_dirs and (args.mat_dir is None or args.adicht_dir is None):
        parser.error("--mat-dir and --adicht-dir must both be provided when files are in separate directories.")
    
    # For analysis/plotting-only runs, --input-dir defaults to --output-dir
    if not has_input_dir and not has_split_dirs:
        if args.steps in ['analysis', 'plotting']:
            args.input_dir = args.output_dir
        else:
            parser.error("Either --input-dir or --mat-dir/--adicht-dir is required.")
    
    # Resolve worker count (-1 = auto-detect all cores)
    try:
        args.workers = resolve_workers(args.workers)
        logger.info(f"Using {args.workers} parallel workers")
    except ValueError as e:
        parser.error(str(e))
    
    # Ensure output directory exists
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    # --- PHASE 1: INGESTION ---
    csv_files = []
    
    if args.steps in ['all', 'ingestion']:
        raw_files = []
        
        if has_split_dirs:
            # Files in separate directories — pair by stem
            mat_files = {p.stem: p for p in args.mat_dir.rglob('*.mat')}
            adicht_files = {p.stem: p for p in args.adicht_dir.rglob('*.adicht')}
            
            matched_stems = set(mat_files.keys()) & set(adicht_files.keys())
            unmatched_mat = set(mat_files.keys()) - matched_stems
            unmatched_adicht = set(adicht_files.keys()) - matched_stems
            
            for stem in sorted(matched_stems):
                raw_files.append((mat_files[stem], adicht_files[stem]))
            
            for stem in sorted(unmatched_mat):
                logger.warning(f"Skipping {stem}.mat: No matching ADICHT file in {args.adicht_dir}")
            for stem in sorted(unmatched_adicht):
                logger.warning(f"Skipping {stem}.adicht: No matching MAT file in {args.mat_dir}")
        else:
            # Files co-located in the same directory
            mat_files = list(args.input_dir.rglob('*.mat'))
            for mat_path in mat_files:
                adicht_path = mat_path.with_suffix('.adicht')
                if adicht_path.exists():
                    raw_files.append((mat_path, adicht_path))
                else:
                    logger.warning(f"Skipping {mat_path.name}: No ADICHT file found")
        
        if not raw_files:
            logger.error("No valid .mat/.adicht pairs found.")
            if args.steps == 'ingestion':
                sys.exit(1)
        else:
            csv_files = run_ingestion_parallel(raw_files, args.output_dir, args.skip_clinical, args.workers)
            
    # If we skipped ingestion phase, discover existing waveform files
    if args.steps in ['all', 'analysis'] and not csv_files:
        search_root = args.input_dir if has_input_dir else args.output_dir
        csv_files = list(search_root.rglob("waveform.csv"))
        if not csv_files:
            logger.error(f"No waveform.csv files found in {search_root}")
            
    # --- PHASE 2: ANALYSIS ---
    pkl_files = []
    
    if args.steps in ['all', 'analysis']:
        if not csv_files:
            logger.error("No CSV files found for analysis.")
            if args.steps == 'analysis':
                sys.exit(1)
        else:
            pkl_files = run_analysis_parallel(csv_files, args.config, args.sampling_rate, args.workers)

    # If we skipped analysis phase, discover pkls for plotting
    if args.steps in ['all', 'plotting'] and not pkl_files:
        search_root = args.input_dir if has_input_dir else args.output_dir
        pkl_files = list(search_root.rglob("analysis.pkl"))
        if not pkl_files:
            logger.error(f"No analysis.pkl files found in {search_root}")

    # --- PHASE 3: PLOTTING ---
    if args.steps in ['all', 'plotting']:
        if not pkl_files:
            logger.error("No analysis pickle files found for plotting.")
            sys.exit(1)
        
        # Load merged config
        from run_plotting import load_config as load_plot_config
        pipeline_cfg = load_config(args.config)
        plot_cfg = load_plot_config(args.plotting_config)
        merged_config = {**pipeline_cfg, **plot_cfg}
        
        # Apply --show flag
        if args.show:
            merged_config.setdefault('output', {})['show_figures'] = True
        
        # Interactive display requires single worker
        plot_workers = 1 if args.show else args.workers
        run_plotting_parallel(pkl_files, merged_config, plot_workers)
        
    logger.info("Pipeline run complete.")


if __name__ == '__main__':
    start_time = time.time()
    main()
    duration = time.time() - start_time
    print(f"\nTotal runtime: {duration:.1f} seconds")
