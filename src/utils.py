# src/utils.py
import random
import datetime
from pathlib import Path
import os

# List of nouns for random filename generation
NOUNS = [
    "apple", "balloon", "camera", "diamond", "elephant", "forest", "guitar", 
    "horizon", "island", "journey", "keyboard", "lighthouse", "mountain", 
    "notebook", "ocean", "pyramid", "quilt", "rainbow", "sunset", "treasure",
    "umbrella", "volcano", "waterfall", "xylophone", "yacht", "zebra", "archive",
    "backup", "collection", "data", "folder", "gallery", "library", "project",
    "record", "storage", "document", "file", "package", "bundle", "set"
]

def get_desktop_path() -> Path:
    """Returns the path to the user's desktop directory."""
    return Path(os.path.expanduser("~/Desktop"))

def generate_filename(source_path: str = None, use_random: bool = True) -> str:
    """
    Generates a filename for the zip archive based on source path or random noun.
    
    Args:
        source_path: Optional path to the source being zipped.
        use_random: Whether to use a random noun (True) or source name (False).
        
    Returns:
        A string containing the generated filename (without extension).
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if use_random or not source_path:
        # Use a random noun
        noun = random.choice(NOUNS)
        return f"{noun}_{timestamp}"
    else:
        # Use the source name if available
        source_name = Path(source_path).stem
        return f"{source_name}_{timestamp}"

def get_default_zip_path(source_path: str = None) -> Path:
    """
    Creates a default path for saving a zip file on the desktop.
    
    Args:
        source_path: Optional path to the source being zipped.
        
    Returns:
        A Path object for the default zip location.
    """
    desktop = get_desktop_path()
    filename = generate_filename(source_path, use_random=source_path is None)
    
    return desktop / f"{filename}.zip"