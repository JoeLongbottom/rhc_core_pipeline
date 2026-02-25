#!/usr/bin/env python3
"""
Analysis Pipeline Runner

Runs the full RHC analysis pipeline (ECG features → Pressure features → 
Beat gating → Beat classification) and preserves all data for plotting.

Usage:
    python run_analysis.py --input output/ingested/recording.csv \
                           --output output/analysis \
                           --config config/pipeline_config.yaml
"""

import argparse
import json
import logging
import pickle
import sys
from pathlib import Path

import yaml

# Add project root to path (for src.* imports)
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np

from src.ecg_features import extract_ecg_features, get_r_peak_indices
from src.pressure_features import extract_pressure_features
from src.beat_gating import apply_beat_gating
from src.beat_classification import classify_beats
from src.clinical_indices import calculate_clinical_indices
try:
    from src.autonomic_indices import calculate_autonomic_indices
    _HAS_AUTONOMIC = True
except ImportError:
    _HAS_AUTONOMIC = False
from src.utils import get_git_revision_hash

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config(config_path: Path) -> dict:
    """Load pipeline configuration from YAML file."""
    if config_path.exists():
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    logger.warning(f"Config file not found: {config_path}, using defaults")
    return {}


def run_full_analysis(
    waveform_df: pd.DataFrame,
    sampling_rate: float,
    config: dict
) -> dict:
    """
    Run complete analysis pipeline and return all data for plotting.
    
    Args:
        waveform_df: DataFrame with 'ecg' and 'pressure' columns.
        sampling_rate: Sampling rate in Hz.
        config: Pipeline configuration dict.
        
    Returns:
        Dictionary with all signals and DataFrames needed for plotting:
            - ecg_signals
            - ecg_features
            - pressure_signals
            - pressure_features
            - gated_beats
            - classified_beats
            - sampling_rate
    """
    logger.info("Starting full analysis pipeline...")
    
    # Normalise column names to lowercase
    waveform_df.columns = waveform_df.columns.str.lower()
    
    # Extract signals
    ecg_signal = waveform_df['ecg'].values
    pressure_signal = waveform_df['pressure'].values
    
    # -------------------------------------------------------------------------
    # Step 1: ECG Features
    # -------------------------------------------------------------------------
    logger.info("Step 1: Extracting ECG features...")
    ecg_features, ecg_signals = extract_ecg_features(
        ecg_signal=ecg_signal,
        sampling_rate=sampling_rate,
        config=config
    )
    logger.info(f"  → Detected {len(ecg_features)} beats")
    
    if len(ecg_features) == 0:
        logger.error("No beats detected, cannot continue analysis")
        return {
            'ecg_signals': ecg_signals,
            'ecg_features': ecg_features,
            'pressure_signals': {},
            'pressure_features': None,
            'gated_beats': None,
            'classified_beats': None,
            'sampling_rate': sampling_rate
        }
    
    # -------------------------------------------------------------------------
    # Step 2: Pressure Features
    # -------------------------------------------------------------------------
    logger.info("Step 2: Extracting pressure features...")
    r_peak_indices = get_r_peak_indices(ecg_features)
    
    pressure_features, pressure_signals = extract_pressure_features(
        pressure_signal=pressure_signal,
        r_peak_indices=r_peak_indices,
        sampling_rate=sampling_rate,
        config=config
    )
    logger.info(f"  → Extracted features for {len(pressure_features)} beats")
    
    # -------------------------------------------------------------------------
    # Step 3: Beat Gating
    # -------------------------------------------------------------------------
    logger.info("Step 3: Applying beat gating...")
    gated_beats = apply_beat_gating(
        ecg_features=ecg_features,
        pressure_features=pressure_features,
        config=config
    )
    
    n_accepted = (gated_beats['interval_status'] == 'ACCEPTED').sum()
    logger.info(f"  → {n_accepted}/{len(gated_beats)} beats accepted")
    
    # -------------------------------------------------------------------------
    # Step 4: Beat Classification
    # -------------------------------------------------------------------------
    logger.info("Step 4: Classifying beats...")
    classified_beats = classify_beats(
        validated_beats=gated_beats,
        config=config
    )
    
    n_rv = (classified_beats['anatomical_loc'] == 'RV').sum()
    n_pa = (classified_beats['anatomical_loc'] == 'PA').sum()
    logger.info(f"  → Classification: {n_rv} RV, {n_pa} PA")
    
    # -------------------------------------------------------------------------
    # Compile Results
    # -------------------------------------------------------------------------
    # Note: Clinical indices are calculated in process_analysis() rather than
    # here, because they require patient metadata which is loaded separately.
    results = {
        'ecg_signals': ecg_signals,
        'ecg_features': ecg_features,
        'pressure_signals': pressure_signals,
        'pressure_features': pressure_features,
        'gated_beats': gated_beats,
        'classified_beats': classified_beats,
        'sampling_rate': sampling_rate
    }
    
    logger.info("Analysis pipeline complete!")
    
    return results


def process_analysis(
    input_path: Path,
    output_dir: Path,
    config_path: Path,
    sampling_rate_override: float = None,
    metadata_path: Path = None,
    verbose: bool = False
) -> bool:
    """
    Process a single analysis file.
    
    Args:
        input_path: Path to input CSV file.
        output_dir: Output directory.
        config_path: Path to config YAML.
        sampling_rate_override: Optional manual sampling rate.
        metadata_path: Optional path to metadata JSON.
        verbose: Enable verbose logging.
        
    Returns:
        True if successful, False otherwise.
    """
    # Setup logging for this process
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        # Load config
        config = load_config(config_path)
        
        # Load waveform data
        logger.info(f"Loading waveform data from: {input_path}")
        waveform_df = pd.read_csv(input_path)
        
        # Determine sampling rate
        sampling_rate = 1000.0
        metadata = {}
        
        if sampling_rate_override:
            sampling_rate = sampling_rate_override
        else:
            # Try to find metadata
            meta_source = None
            if metadata_path and metadata_path.exists():
                meta_source = metadata_path
            else:
                # Try inferring from input path (now expect input at {id}/waveform.csv)
                # Check if file is named waveform.csv and parent has metadata.json
                if input_path.name == 'waveform.csv':
                    inferred_meta = input_path.parent / 'metadata.json'
                else:
                    inferred_meta = input_path.with_suffix('.json')
                if inferred_meta.exists():
                    meta_source = inferred_meta
            
            if meta_source:
                with open(meta_source, 'r') as f:
                    metadata = json.load(f)
                sampling_rate = metadata.get('waveform', {}).get('sample_rate_hz', 1000.0)
            else:
                logger.warning(f"Using default sampling rate: {sampling_rate} Hz")
        
        logger.info(f"Sampling rate: {sampling_rate} Hz")
        
        # Run analysis
        results = run_full_analysis(waveform_df, sampling_rate, config)
        
        # Determine output directory (use same folder as input for per-recording structure)
        if input_path.name == 'waveform.csv':
            recording_dir = input_path.parent
            recording_id = recording_dir.name
        else:
            # Legacy: flat structure
            recording_dir = output_dir
            recording_id = input_path.stem
        
        # Create subdirectories
        intermediates_dir = recording_dir / 'intermediates'
        intermediates_dir.mkdir(parents=True, exist_ok=True)
        
        # Save as pickle
        pickle_path = recording_dir / "analysis.pkl"
        with open(pickle_path, 'wb') as f:
            pickle.dump(results, f)
        logger.info(f"Saved pickle: {pickle_path}")
        
        # Save individual CSVs
        csv_mapping = {
            'ecg_features': 'ecg_features',
            'pressure_features': 'pressure_features',
            'gated_beats': 'gated_beats',
        }
        for key, filename in csv_mapping.items():
            df = results.get(key)
            if df is not None and len(df) > 0:
                csv_path = intermediates_dir / f"{filename}.csv"
                df.to_csv(csv_path, index=False)
        
        # Calculate Clinical Indices
        classified_df = results.get('classified_beats')
        logger.info("Calculating clinical indices...")
        clinical_indices = calculate_clinical_indices(classified_df, metadata=metadata)
        
        # Log key indices
        if 'waveform' in clinical_indices:
            wf = clinical_indices['waveform']
            logger.info(f"  → sPAP: {wf.get('sPAP', 0):.1f} mmHg")
            logger.info(f"  → mPAP: {wf.get('mPAP', 0):.1f} mmHg")
        
        # Calculate Autonomic Indices (if module is available)
        autonomic_results = {}
        if _HAS_AUTONOMIC:
            logger.info("Calculating autonomic indices...")
            autonomic_results = calculate_autonomic_indices(classified_df, config=config)
            
            # Merge epoch_id into classified beats
            if autonomic_results.get('beat_epoch_ids') is not None:
                classified_df['epoch_id'] = autonomic_results['beat_epoch_ids'].values
        else:
            logger.info("Autonomic indices module not available — skipping.")
        
        # Add to results pickle
        results['clinical_indices'] = clinical_indices
        results['autonomic_results'] = autonomic_results
        with open(pickle_path, 'wb') as f:
            pickle.dump(results, f)
        
        # Save autonomic indices JSON (non-critical — wrapped in own try/except)
        if autonomic_results.get('autonomic_indices'):
            try:
                import json as json_mod

                def _json_default(x):
                    """Handle NaN, numpy types, and other non-serialisables."""
                    try:
                        if isinstance(x, float) and np.isnan(x):
                            return None
                    except (TypeError, ValueError):
                        pass
                    if hasattr(x, 'item'):  # numpy scalar
                        return x.item()
                    return str(x)

                auto_json_path = recording_dir / 'autonomic_indices.json'
                with open(auto_json_path, 'w') as f:
                    json_mod.dump(
                        autonomic_results['autonomic_indices'], f,
                        indent=2, default=_json_default
                    )
                logger.info(f"Saved autonomic JSON: {auto_json_path}")
            except Exception as e:
                logger.warning(f"Autonomic JSON save failed (non-critical): {e}")

        # Save Excel — this is the primary output
        if classified_df is not None and len(classified_df) > 0:
            try:
                from src.data_dictionary import save_combined_excel
                from datetime import datetime
                
                xlsx_path = recording_dir / "beats.xlsx"
                run_metadata = {
                    'recording_id': recording_id,
                    'run_timestamp': datetime.now().isoformat(),
                    'sampling_rate_hz': sampling_rate,
                    'total_beats': len(classified_df),
                    'accepted_beats': (classified_df['interval_status'] == 'ACCEPTED').sum(),
                    'pipeline_version': get_git_revision_hash(),
                    'pqrst_features_enabled': config.get('ecg_features', {}).get('return_pqrst_features', False)
                }
                
                # Get PQRST features if available
                pqrst_df = None
                ecg_signals = results.get('ecg_signals', {})
                if 'pqrst_features' in ecg_signals and ecg_signals['pqrst_features'] is not None:
                     pqrst_df = ecg_signals['pqrst_features']
                     run_metadata['pqrst_features_enabled'] = True
                
                save_combined_excel(
                    classified_df,
                    xlsx_path,
                    run_metadata=run_metadata,
                    pqrst_df=pqrst_df,
                    clinical_indices=clinical_indices,
                    autonomic_results=autonomic_results
                )
                logger.info(f"Saved Excel: {xlsx_path}")
            except Exception as e:
                logger.error(f"Excel save failed for {recording_id}: {e}")
                logger.error("(Data preserved in analysis.pkl)")
            
        return True
        
    except Exception as e:
        logger.error(f"Analysis failed for {input_path.name}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Run full RHC analysis pipeline'
    )
    
    parser.add_argument(
        '--input', type=Path, required=True,
        help='Path to input CSV file (from ingestion)'
    )
    parser.add_argument(
        '--metadata', type=Path,
        help='Path to metadata JSON file (optional, used for sampling rate)'
    )
    parser.add_argument(
        '--output', type=Path, required=True,
        help='Output directory for analysis results'
    )
    parser.add_argument(
        '--config', type=Path,
        default=Path('config/pipeline_config.yaml'),
        help='Path to pipeline config YAML'
    )
    parser.add_argument(
        '--sampling-rate', type=float,
        help='Override sampling rate (Hz)'
    )
    parser.add_argument(
        '-v', '--verbose', action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    success = process_analysis(
        input_path=args.input,
        output_dir=args.output,
        config_path=args.config,
        sampling_rate_override=args.sampling_rate,
        metadata_path=args.metadata,
        verbose=args.verbose
    )
    
    if success:
        print(f"\n✓ Analysis complete: {args.output}")
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()
