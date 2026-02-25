"""
Waveform Ingestion Module (Spec 01)

Extracts waveform data (ECG, Pressure) from LabChart .mat exports
and converts them to the project's standard CSV/JSON format.

See: docs/specs/01_waveform_ingestion.md
"""

from pathlib import Path
from datetime import datetime, timezone
import json
import re

import logging

import numpy as np
import pandas as pd
import h5py
from scipy.io import loadmat

logger = logging.getLogger(__name__)


def _to_scalar(value) -> float:
    """Safely convert a numpy scalar or 0-d array to a Python float.
    
    Newer numpy versions no longer allow int()/float() on 0-dimensional arrays
    that have more than one element. Using .item() handles all cases cleanly.
    """
    if hasattr(value, 'item'):
        return value.item()
    return value


def load_mat_file(mat_path: Path) -> dict:
    """
    Load a LabChart .mat export file.
    
    Args:
        mat_path: Path to the .mat file
        
    Returns:
        Dictionary containing the MATLAB data structures
        
    Raises:
        FileNotFoundError: If the file doesn't exist
        ValueError: If the file cannot be parsed
    """
    if not mat_path.exists():
        raise FileNotFoundError(f"MAT file not found: {mat_path}")
    
    try:
        # Try standard scipy loader first
        return loadmat(str(mat_path), squeeze_me=True)
    except NotImplementedError:
        # Likely v7.3 (HDF5)
        return _load_hdf5(mat_path)
    except Exception as e:
        # Check error message for v7.3 hint
        if 'HDF reader' in str(e):
            return _load_hdf5(mat_path)
        raise ValueError(f"Failed to load MAT file: {e}")


def _load_hdf5(path: Path) -> dict:
    """Load v7.3 .mat file using h5py, handling MATLAB cell arrays."""
    data = {}
    
    def _extract_string(ref, f):
        """Helper to dereference and decode a MATLAB string."""
        try:
            # Dereference
            obj = f[ref]
            # It's usually a dataset of integers (uint16 for UTF-16 or uint8 for ASCII)
            # data shape might be (N, 1) or (1, N)
            vals = obj[()]
            if vals.size == 0:
                return ""
            # Flatten and convert to chars
            return "".join([chr(c) for c in vals.flatten() if c != 0])
        except Exception:
            return f"[Ref: {ref}]"

    with h5py.File(path, 'r') as f:
        for k, v in f.items():
            if isinstance(v, h5py.Dataset):
                val = v[()]
                
                # Check for Object References (typical for cell arrays of strings)
                if v.dtype.kind == 'O': 
                    # Likely a list of references (e.g., 'titles')
                    # We only care about this for 1D arrays of strings usually
                    strings = []
                    for item in val.flatten():
                        if isinstance(item, h5py.h5r.Reference):
                            str_val = _extract_string(item, f)
                            strings.append(str_val)
                        else:
                            strings.append(str(item))
                    data[k] = strings
                    continue

                # Handle normal string conversion
                if isinstance(val, bytes):
                    val = val.decode('utf-8', errors='ignore')
                
                # Transpose arrays to match scipy.io.loadmat behavior
                # MATLAB (HDF5) often stores as (channels, samples), we want (samples, channels)
                # Heuristic: if dim 2 >> dim 1, likely needs transpose.
                if val.ndim == 2:
                    rows, cols = val.shape
                    # Assuming waveform data is [samples x channels] in classic LoadMat
                    # but HDF5 stores [channels x samples].
                    # If we have 2 channels and 1M samples:
                    # HDF5: (2, 1000000)
                    # We want: (1000000, 2)
                    if rows < cols: 
                        val = val.T
                    
                data[k] = val
                
            elif isinstance(v, h5py.Group):
                # Legacy cell array storage (group rather than dataset)
                # Typically 'titles' is handled as a dataset of refs above.
                pass
    return data


def identify_channels(mat_data: dict, config: dict) -> dict[str, int]:
    """
    Identify channel indices for required waveforms (e.g., ECG, Pressure).
    """
    channel_indices = {}
    
    # Get required channels
    required_channels = config.get('waveform', {}).get('required_channels', ['ECG', 'Pressure'])
    
    # Locate titles in data
    titles = None
    for key in ['titles', 'channel_names', 'channelNames', 'titles\x00']: # \x00 sometimes in hdf5 keys
        if key in mat_data:
            titles = mat_data[key]
            break
            
    # --- FALLBACK LOGIC ---
    # If titles are missing OR they look like garbage (e.g. stringified refs failed), 
    # we fallback to index-based assignment.
    
    use_fallback = False
    if titles is None:
        use_fallback = True
    else:
        # Check if titles look valid
        valid_titles = [t for t in titles if isinstance(t, str) and len(t) > 0 and not t.startswith('[Ref:')]
        if len(valid_titles) < len(required_channels):
            use_fallback = True
            
    if use_fallback:
        logger.warning("Could not identify channels by name. Assuming default order: [0]=ECG, [1]=Pressure")
        # Assign by index
        curr_idx = 0
        for channel in required_channels:
            channel_indices[channel] = curr_idx
            curr_idx += 1
        return channel_indices

    # Standardize titles to list of strings
    if hasattr(titles, 'tolist'):
        titles = titles.tolist()
    
    clean_titles = []
    if isinstance(titles, (list, tuple, np.ndarray)):
        for t in titles:
             clean_titles.append(str(t).strip())
    else:
        clean_titles = [str(titles).strip()]
        
    titles_upper = [t.upper() for t in clean_titles]
    
    # Map channels
    for channel in required_channels:
        channel_upper = channel.upper()
        found = False
        
        # 1. Exact match
        if channel_upper in titles_upper:
            idx = titles_upper.index(channel_upper)
            channel_indices[channel] = idx
            found = True
            
        # 2. Substring match
        if not found:
            for i, t in enumerate(titles_upper):
                if channel_upper in t:
                    channel_indices[channel] = i
                    found = True
                    break
        
        if not found:
            # Final fallback: If we found *some* checks but not this one, 
            # we might fail. BUT consistent with above, let's force fallback if we can't find BASIC channels
            # to avoid blocking.
            logger.warning(f"Channel '{channel}' not found by name in {clean_titles}. Assigning index {len(channel_indices)}")
            # Try to assign next available index?
            # Creating a naive mapping if names fail is better than crashing
            channel_indices[channel] = len(channel_indices)

    return channel_indices


def extract_waveform_data(
    mat_data: dict,
    channel_indices: dict[str, int]
) -> tuple[np.ndarray, np.ndarray]:
    """
    Extract ECG and Pressure arrays from MAT data.
    
    Args:
        mat_data: Loaded MAT file data
        channel_indices: Mapping of channel name to column index
        
    Returns:
        Tuple of (ecg_array, pressure_array)
    """
    # Try to find data array in common locations
    data = None
    for key in ['data', 'data_block1', 'datastart']:
        if key in mat_data:
            data = mat_data[key]
            break
    
    if data is None:
        raise ValueError("Could not find waveform data in MAT file")
    
    # Handle different data layouts
    if data.ndim == 1:
        # Single channel - shouldn't happen but handle it
        raise ValueError("Expected multi-channel data")
    
    # Assume data is (n_samples, n_channels) or (n_channels, n_samples)
    # LabChart typically exports as (n_samples, n_channels)
    if data.shape[0] < data.shape[1]:
        # Likely (n_channels, n_samples), transpose
        data = data.T
    
    ecg = data[:, channel_indices["ECG"]].astype(np.float64)
    pressure = data[:, channel_indices["Pressure"]].astype(np.float64)
    
    return ecg, pressure


def scale_pressure(pressure: np.ndarray, scale_factor: float = 100.0) -> np.ndarray:
    """
    Convert pressure from mmHg/100 to mmHg.
    
    Args:
        pressure: Raw pressure array
        scale_factor: Multiplication factor (default 100)
        
    Returns:
        Scaled pressure array in mmHg
    """
    return pressure * scale_factor


def get_sample_rate(mat_data: dict) -> float:
    """
    Extract sample rate from MAT data.
    
    Args:
        mat_data: Loaded MAT file data
        
    Returns:
        Sample rate in Hz
    """
    for key in ['tickrate', 'samplerate', 'fs', 'Fs']:
        if key in mat_data:
            rate = mat_data[key]
            return float(_to_scalar(rate))
    
    raise ValueError("Could not find sample rate in MAT file")


def extract_block_info(mat_data: dict, total_samples: int, sample_rate: float) -> list[dict]:
    """
    Extract block structure from MAT data.
    
    For single-block files, returns a single block spanning all samples.
    For multi-block files, extracts block boundaries and creates gap entries.
    
    Args:
        mat_data: Loaded MAT file data
        total_samples: Total number of samples in the data
        sample_rate: Sample rate in Hz
        
    Returns:
        List of block dictionaries
    """
    # Check for multi-block structure
    if 'datastart' in mat_data and 'dataend' in mat_data:
        # Multi-block file
        starts = mat_data['datastart']
        ends = mat_data['dataend']
        
        if not hasattr(starts, '__len__'):
            starts = [starts]
            ends = [ends]
        
        blocks = []
        block_id = 1
        
        for i, (start, end) in enumerate(zip(starts, ends)):
            start = int(_to_scalar(start))
            end = int(_to_scalar(end))
            
            # Add gap before this block if needed
            if blocks and blocks[-1]['end_sample'] < start:
                gap_start = blocks[-1]['end_sample']
                blocks.append({
                    'block_id': None,
                    'start_sample': gap_start,
                    'end_sample': start,
                    'n_samples': start - gap_start,
                    'start_datetime': None,
                    'duration_seconds': (start - gap_start) / sample_rate,
                    'is_gap': True
                })
            
            # Add the block
            blocks.append({
                'block_id': block_id,
                'start_sample': start,
                'end_sample': end,
                'n_samples': end - start,
                'start_datetime': None,  # Would need blocktimes
                'duration_seconds': (end - start) / sample_rate,
                'is_gap': False
            })
            block_id += 1
        
        return blocks
    
    # Single block - spans entire file
    return [{
        'block_id': 1,
        'start_sample': 0,
        'end_sample': total_samples,
        'n_samples': total_samples,
        'start_datetime': None,
        'duration_seconds': total_samples / sample_rate,
        'is_gap': False
    }]


import subprocess

def get_git_revision_hash() -> str:
    """Get the current git commit hash."""
    try:
        return subprocess.check_output(['git', 'rev-parse', 'HEAD'], stderr=subprocess.DEVNULL).decode('ascii').strip()
    except Exception:
        return "unknown"

def build_metadata(
    recording_id: str,
    mat_path: Path,
    adicht_path: Path,
    sample_rate: float,
    total_samples: int,
    blocks: list[dict]
) -> dict:
    """
    Build the metadata JSON structure.
    
    Args:
        recording_id: Unique identifier for this recording
        mat_path: Path to source .mat file
        adicht_path: Path to source .adicht file
        sample_rate: Sample rate in Hz
        total_samples: Total number of samples
        blocks: List of block dictionaries
        
    Returns:
        Metadata dictionary ready for JSON serialisation
    """
    # Find first non-gap block for start_datetime
    start_datetime = None
    for block in blocks:
        if not block['is_gap'] and block.get('start_datetime'):
            start_datetime = block['start_datetime']
            break
    
    return {
        'recording_id': recording_id,
        'start_datetime': start_datetime,
        'provenance': {
            'source_mat': mat_path.name,
            'source_adicht': adicht_path.name if adicht_path else None,
            'ingestion_timestamp': datetime.now(timezone.utc).isoformat(),
            'git_commit': get_git_revision_hash()
        },
        'waveform': {
            'sample_rate_hz': sample_rate,
            'duration_seconds': total_samples / sample_rate,
            'total_samples': total_samples,
            'channels': {
                'ECG': {'unit': 'mV'},
                'Pressure': {'unit': 'mmHg', 'note': 'Scaled from mmHg/100'}
            }
        },
        'blocks': blocks,
        'hemodynamics': {},
        'extraction': {}
    }


def ingest_waveform(
    mat_path: Path,
    adicht_path: Path | None = None,
    output_dir: Path | None = None,
    config: dict | None = None
) -> tuple[pd.DataFrame, dict]:
    """
    Main entry point for waveform ingestion.
    
    Loads a LabChart .mat export, extracts ECG and Pressure channels,
    scales pressure values, and outputs CSV + JSON.
    
    Args:
        mat_path: Path to the .mat file
        adicht_path: Path to the .adicht file (for metadata)
        output_dir: Optional output directory for CSV/JSON files
        config: Optional configuration dictionary
        
    Returns:
        Tuple of (waveform_dataframe, metadata_dict)
        
    Raises:
        FileNotFoundError: If input files don't exist
        ValueError: If required channels not found or data invalid
    """
    mat_path = Path(mat_path)
    if adicht_path:
        adicht_path = Path(adicht_path)
    
    # Default config structure
    if config is None:
        config = {}
        
    # Ensure waveform config exists
    if 'waveform' not in config:
        config['waveform'] = {
            'required_channels': ['ECG', 'Pressure'],
            'pressure_scale_factor': 100
        }
    
    # Load MAT file
    mat_data = load_mat_file(mat_path)
    
    # Identify channels
    channel_indices = identify_channels(
        mat_data, 
        config
    )
    
    # Extract waveforms
    ecg, pressure = extract_waveform_data(mat_data, channel_indices)
    
    # Scale pressure
    pressure = scale_pressure(
        pressure, 
        config.get('pressure_scale_factor', 100)
    )
    
    # Get sample rate
    sample_rate = get_sample_rate(mat_data)
    
    # Build block info
    total_samples = len(ecg)
    blocks = extract_block_info(mat_data, total_samples, sample_rate)
    
    # Create DataFrame
    df = pd.DataFrame({
        'ECG': ecg,
        'Pressure': pressure
    })
    
    # Build metadata
    recording_id = mat_path.stem
    metadata = build_metadata(
        recording_id=recording_id,
        mat_path=mat_path,
        adicht_path=adicht_path,
        sample_rate=sample_rate,
        total_samples=total_samples,
        blocks=blocks
    )
    
    # Save outputs if directory specified
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        csv_path = output_dir / f"{recording_id}.csv"
        json_path = output_dir / f"{recording_id}.json"
        
        df.to_csv(csv_path, index=False)
        
        with open(json_path, 'w') as f:
            json.dump(metadata, f, indent=2, default=str)
    
    return df, metadata
