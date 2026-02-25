#!/usr/bin/env python3
"""
Ingestion CLI

Command-line interface for processing LabChart files.

Usage:
    python run_ingestion.py --mat file.mat --adicht file.adicht --output-dir ./output
"""

import argparse
import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from ingestion.waveform_ingestion import ingest_waveform
from ingestion.clinical_extraction import extract_clinical_metadata, merge_with_metadata


def process_single_file(mat_path: Path, adicht_path: Path, output_dir: Path, skip_clinical: bool, verbose: bool):
    """Process a single file pair."""
    recording_id = mat_path.stem
    
    if verbose:
        print(f"[{recording_id}] Processing...")

    # Step 1: Waveform ingestion
    try:
        df, metadata = ingest_waveform(
            mat_path=mat_path,
            adicht_path=adicht_path,
            config={} # Uses default config loading inside ingest_waveform
        )
        if verbose:
            print(f"  Waveforms: {len(df)} samples, {metadata['waveform']['sample_rate_hz']} Hz")
    except Exception as e:
        print(f"[{recording_id}] Error during waveform ingestion: {e}", file=sys.stderr)
        return False

    # Step 2: Clinical metadata extraction
    extraction_status = "SKIPPED"
    if not skip_clinical:
        try:
            hemodynamics, extraction = extract_clinical_metadata(adicht_path)
            metadata = merge_with_metadata(metadata, hemodynamics, extraction)
            extraction_status = extraction['status']
            
            if verbose and extraction['warnings']:
                for w in extraction['warnings']:
                    print(f"    Warning: {w}")
        except Exception as e:
            print(f"[{recording_id}] Error during clinical extraction: {e}", file=sys.stderr)
            metadata['hemodynamics'] = {}
            metadata['extraction'] = {'status': 'FAILED', 'warnings': [str(e)]}
            extraction_status = "FAILED"

    # Save outputs to per-recording directory
    recording_dir = output_dir / recording_id
    recording_dir.mkdir(parents=True, exist_ok=True)
    
    csv_path = recording_dir / "waveform.csv"
    json_path = recording_dir / "metadata.json"

    df.to_csv(csv_path, index=False)
    
    with open(json_path, 'w') as f:
        json.dump(metadata, f, indent=2, default=str)

    print(f"[{recording_id}] Done ({extraction_status})")
    return True


def main():
    parser = argparse.ArgumentParser(
        description='Ingest LabChart files into standard CSV/JSON format'
    )
    
    # Input group: either single file pair OR directory modes
    input_group = parser.add_mutually_exclusive_group(required=True)
    
    # Mode 1: Single directory (colocated files)
    input_group.add_argument('--input-dir', type=Path, help='Input directory containing BOTH .mat and .adicht files')
    
    # Mode 2: Split directories
    input_group.add_argument('--mat-dir', type=Path, help='Directory containing .mat files')
    
    # Mode 3: Single file
    input_group.add_argument('--mat', type=Path, help='Path to single .mat file')

    # Adicht options
    parser.add_argument('--adicht', type=Path, help='Path to .adicht file (required if --mat is used)')
    parser.add_argument('--adicht-dir', type=Path, help='Directory containing .adicht files (required if --mat-dir is used)')
    
    parser.add_argument(
        '--output-dir',
        type=Path,
        required=True,
        help='Output directory for CSV and JSON files'
    )
    parser.add_argument(
        '--skip-clinical',
        action='store_true',
        help='Skip clinical metadata extraction'
    )
    parser.add_argument(
        '--verbose',
        '-v',
        action='store_true',
        help='Print verbose output'
    )
    
    args = parser.parse_args()
    
    # Validation
    if args.mat and not args.adicht:
        parser.error("--adicht is required when --mat is specified")
        
    if args.mat_dir and not args.adicht_dir:
        parser.error("--adicht-dir is required when --mat-dir is specified")

    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    files_to_process = []
    
    # --- Mode 1: Single Directory ---
    if args.input_dir:
        if not args.input_dir.exists():
            print(f"Error: Input directory not found: {args.input_dir}", file=sys.stderr)
            sys.exit(1)
            
        mat_files = list(args.input_dir.rglob('*.mat'))
        if not mat_files:
            print(f"No .mat files found in {args.input_dir}", file=sys.stderr)
            sys.exit(1)
            
        print(f"Found {len(mat_files)} .mat files in {args.input_dir}")
        
        for mat_path in mat_files:
            adicht_path = mat_path.with_suffix('.adicht')
            if not adicht_path.exists():
                print(f"Warning: Skipping {mat_path.name} - corresponding .adicht not found", file=sys.stderr)
                continue
            files_to_process.append((mat_path, adicht_path))

    # --- Mode 2: Split Directories ---
    elif args.mat_dir:
        if not args.mat_dir.exists():
            print(f"Error: MAT directory not found: {args.mat_dir}", file=sys.stderr)
            sys.exit(1)
        if not args.adicht_dir.exists():
            print(f"Error: ADICHT directory not found: {args.adicht_dir}", file=sys.stderr)
            sys.exit(1)
            
        mat_files = list(args.mat_dir.rglob('*.mat'))
        if not mat_files:
            print(f"No .mat files found in {args.mat_dir}", file=sys.stderr)
            sys.exit(1)
            
        print(f"Found {len(mat_files)} .mat files in {args.mat_dir}")
        
        for mat_path in mat_files:
            # Look for adicht with same stem in adicht_dir (recursive?) - assume flat structure for matching efficiency
            # Or assume same relative path? Let's just assume simple filename matching for now.
            adicht_path = args.adicht_dir / f"{mat_path.stem}.adicht"
            
            # If not found flat, try recursive search? No, keep it simple.
            if not adicht_path.exists():
                # Try recursive match if simple fails
                candidates = list(args.adicht_dir.rglob(f"{mat_path.stem}.adicht"))
                if len(candidates) == 1:
                    adicht_path = candidates[0]
                elif len(candidates) > 1:
                    print(f"Warning: Multiple .adicht files found for {mat_path.stem}, skipping to avoid ambiguity", file=sys.stderr)
                    continue
                else:
                    print(f"Warning: Skipping {mat_path.name} - .adicht not found in {args.adicht_dir}", file=sys.stderr)
                    continue
            
            files_to_process.append((mat_path, adicht_path))

    # --- Mode 3: Single File ---
    else:
        if not args.mat.exists():
            print(f"Error: MAT file not found: {args.mat}", file=sys.stderr)
            sys.exit(1)
        if not args.adicht.exists():
            print(f"Error: ADICHT file not found: {args.adicht}", file=sys.stderr)
            sys.exit(1)
            
        files_to_process.append((args.mat, args.adicht))

    # Process files
    success_count = 0
    fail_count = 0
    
    print(f"Processing {len(files_to_process)} recordings...")
    print("-" * 40)
    
    for mat_path, adicht_path in files_to_process:
        if process_single_file(mat_path, adicht_path, args.output_dir, args.skip_clinical, args.verbose):
            success_count += 1
        else:
            fail_count += 1
            
    print("-" * 40)
    print(f"Completed: {success_count} successful, {fail_count} failed")


if __name__ == '__main__':
    main()
