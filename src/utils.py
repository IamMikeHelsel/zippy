# src/utils.py
import random
import datetime
from pathlib import Path
import os
from typing import Optional, Union, List, Dict, Any, Tuple

# List of nouns for random filename generation
NOUNS: List[str] = [
    "apple",
    "balloon",
    "camera",
    "diamond",
    "elephant",
    "forest",
    "guitar",
    "horizon",
    "island",
    "journey",
    "keyboard",
    "lighthouse",
    "mountain",
    "notebook",
    "ocean",
    "pyramid",
    "quilt",
    "rainbow",
    "sunset",
    "treasure",
    "umbrella",
    "volcano",
    "waterfall",
    "xylophone",
    "yacht",
    "zebra",
    "archive",
    "backup",
    "collection",
    "data",
    "folder",
    "gallery",
    "library",
    "project",
    "record",
    "storage",
    "document",
    "file",
    "package",
    "bundle",
    "set",
]


def get_desktop_path() -> Path:
    """Returns the path to the user's desktop directory."""
    return Path(os.path.expanduser("~/Desktop"))


def generate_filename(
    source_path: Optional[str] = None, use_random: bool = True
) -> str:
    """
    Generates a filename for the zip archive based on source path or random noun.

    Args:
        source_path: Optional path to the source being zipped.
        use_random: Whether to use a random noun (True) or source name (False).

    Returns:
        A string containing the generated filename (without extension).
    """
    timestamp: str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    if use_random or not source_path:
        # Use a random noun
        noun: str = random.choice(NOUNS)
        return f"{noun}_{timestamp}"
    else:
        # Use the source name if available
        source_name: str = Path(source_path).stem
        return f"{source_name}_{timestamp}"


def get_default_zip_path(source_path: Optional[str] = None) -> Path:
    """
    Creates a default path for saving a zip file on the desktop.

    Args:
        source_path: Optional path to the source being zipped.

    Returns:
        A Path object for the default zip location.
    """
    desktop: Path = get_desktop_path()
    filename: str = generate_filename(source_path, use_random=source_path is None)

    return desktop / f"{filename}.zip"


def format_file_size(size_bytes: int) -> str:
    """
    Format a file size in bytes to a human-readable string.

    Args:
        size_bytes: File size in bytes

    Returns:
        Formatted string with appropriate units (B, KB, MB, GB)
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes/1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes/(1024*1024):.1f} MB"
    else:
        return f"{size_bytes/(1024*1024*1024):.2f} GB"


def split_path_list(path_str: str) -> List[str]:
    """
    Split a semicolon-separated path string into a list of paths.

    Args:
        path_str: Semicolon-separated string of file paths

    Returns:
        List of individual path strings
    """
    if not path_str:
        return []
    return [p.strip() for p in path_str.split(";") if p.strip()]


def ensure_dir_exists(path: Union[str, Path]) -> Path:
    """
    Ensure a directory exists, creating it if necessary.

    Args:
        path: Directory path to check/create

    Returns:
        Path object for the directory

    Raises:
        PermissionError: If the directory cannot be created due to permissions
        OSError: If the directory cannot be created for other reasons
    """
    dir_path = Path(path)
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


def is_path_valid(path: Union[str, Path]) -> bool:
    """
    Check if a path is valid and accessible.

    Args:
        path: Path to check

    Returns:
        True if path exists and is accessible, False otherwise
    """
    try:
        Path(path).resolve(strict=False)
        return True
    except (OSError, RuntimeError):
        return False
