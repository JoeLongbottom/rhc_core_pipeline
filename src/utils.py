"""
Shared Utility Functions

Common utilities used across the RHC pipeline modules.
"""

from pathlib import Path
from typing import Union
import yaml
import numpy as np
import subprocess


def get_git_revision_hash(short=True) -> str:
    """
    Return the current git revision hash.
    
    Args:
        short: If True, return short (7-char) hash.
        
    Returns:
        Git hash string or 'unknown' if git command fails.
    """
    try:
        cmd = ['git', 'rev-parse', '--short', 'HEAD'] if short else ['git', 'rev-parse', 'HEAD']
        return subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode('ascii').strip()
    except Exception:
        return "unknown"


def load_config(config_path: Union[str, Path]) -> dict:
    """
    Load pipeline configuration from a YAML file.
    
    Args:
        config_path: Path to the YAML configuration file.
        
    Returns:
        Configuration dictionary.
        
    Raises:
        FileNotFoundError: If config file doesn't exist.
        yaml.YAMLError: If config file is invalid YAML.
    """
    config_path = Path(config_path)
    
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def samples_to_time(samples: Union[int, np.ndarray], sampling_rate: float) -> Union[float, np.ndarray]:
    """
    Convert sample indices to time in seconds.
    
    Args:
        samples: Sample index or array of sample indices.
        sampling_rate: Sampling rate in Hz.
        
    Returns:
        Time in seconds.
    """
    return samples / sampling_rate


def time_to_samples(time: Union[float, np.ndarray], sampling_rate: float) -> Union[int, np.ndarray]:
    """
    Convert time in seconds to sample indices.
    
    Args:
        time: Time in seconds or array of times.
        sampling_rate: Sampling rate in Hz.
        
    Returns:
        Sample index (rounded to nearest integer).
    """
    samples = time * sampling_rate
    if isinstance(samples, np.ndarray):
        return samples.astype(int)
    return int(round(samples))


def make_odd(n: int) -> int:
    """
    Ensure a number is odd (required for Savitzky-Golay window).
    
    Args:
        n: Input number.
        
    Returns:
        Odd number (n if already odd, n+1 if even).
    """
    return n if n % 2 == 1 else n + 1


def resolve_workers(n: int) -> int:
    """
    Resolve worker count for parallel processing.
    
    Handles the convention where -1 means "use all available CPU cores".
    
    Args:
        n: Number of workers. Use -1 for auto-detection.
        
    Returns:
        Positive integer worker count.
        
    Raises:
        ValueError: If n is 0 or negative (other than -1).
    """
    import os
    if n == -1:
        return os.cpu_count() or 4
    if n <= 0:
        raise ValueError("workers must be positive or -1 for auto-detection")
    return n

