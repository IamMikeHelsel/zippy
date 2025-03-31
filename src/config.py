# src/config.py
"""
Configuration management for zippy application.

This module handles loading, saving, and accessing user preferences
that persist between application runs.
"""

import json
import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Union, List

# Configure module logger
logger = logging.getLogger(__name__)

# Default configuration values
DEFAULT_CONFIG = {
    "ui": {
        "theme": "dark",  # 'dark', 'light', or 'system'
        "accent_color": "blue",  # 'blue', 'green', 'purple', etc.
        "window_size": [600, 550],  # Width, height in pixels
        "window_position": None,  # [x, y] position (None = center)
        "remember_last_dirs": True,  # Remember last used directories
    },
    "compression": {
        "default_level": 9,  # 0-9, with 9 being maximum compression
        "default_output_dir": "",  # Custom output directory (empty = desktop)
        "use_source_name": True,  # Use source name for output file
        "create_parent_dirs": True,  # Create parent directories if needed
    },
    "extraction": {
        "default_extract_dir": "",  # Default extraction directory (empty = source dir)
        "use_archive_name": True,  # Create subfolder named after archive
        "overwrite_existing": False,  # Overwrite existing files
    },
    "performance": {
        "max_memory_percent": 75,  # Maximum memory usage percentage
        "thread_count": 0,  # Thread count (0 = auto)
        "chunk_size_mb": 8,  # Size of chunks for processing large files (MB)
    },
    "recent_files": {
        "max_recent": 10,  # Maximum number of recent files to remember
        "recent_sources": [],  # List of recently used source paths
        "recent_destinations": [],  # List of recently used destination paths
    },
}


class AppConfig:
    """
    Manages application configuration and user preferences.

    This class handles loading, saving, and accessing user preferences
    that persist between application runs. It supports default values
    and automatic creation of the config file if it doesn't exist.
    """

    def __init__(self, config_dir: Optional[str] = None):
        """
        Initialize the configuration manager.

        Args:
            config_dir: Optional custom configuration directory.
                If None, uses platform-specific user config location.
        """
        self.config_data = DEFAULT_CONFIG.copy()

        # Determine config directory and file path
        if config_dir:
            self.config_dir = Path(config_dir)
        else:
            # Use platform-specific location
            self.config_dir = self._get_default_config_dir()

        self.config_file = self.config_dir / "zippy_config.json"
        self._ensure_config_dir_exists()

        # Load existing configuration if available
        self.load()

    def _get_default_config_dir(self) -> Path:
        """
        Get the default configuration directory based on the platform.

        Returns:
            Path to the platform-specific config directory
        """
        if os.name == "nt":  # Windows
            app_data = os.environ.get("APPDATA", "")
            return Path(app_data) / "ZippyApp"
        else:  # macOS/Linux
            home = Path.home()
            return home / ".config" / "zippy"

    def _ensure_config_dir_exists(self) -> None:
        """Create the configuration directory if it doesn't exist."""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"Failed to create config directory: {e}")

    def load(self) -> bool:
        """
        Load configuration from file.

        Returns:
            True if configuration was loaded successfully, False otherwise
        """
        if not self.config_file.exists():
            logger.info(
                f"Configuration file not found at {self.config_file}. Using defaults."
            )
            self.save()  # Create default config file
            return False

        try:
            with open(self.config_file, "r") as f:
                loaded_config = json.load(f)

            # Update our config with loaded values, preserving defaults for missing keys
            self._update_config_recursive(self.config_data, loaded_config)
            logger.info(f"Configuration loaded from {self.config_file}")
            return True
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON in configuration file {self.config_file}")
            return False
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            return False

    def _update_config_recursive(
        self, target: Dict[str, Any], source: Dict[str, Any]
    ) -> None:
        """
        Recursively update configuration, preserving defaults for missing keys.

        Args:
            target: Target dictionary to update
            source: Source dictionary with new values
        """
        for key, value in source.items():
            if key in target:
                if isinstance(value, dict) and isinstance(target[key], dict):
                    # Recursively update nested dictionaries
                    self._update_config_recursive(target[key], value)
                else:
                    # Update value if key exists in target
                    target[key] = value

    def save(self) -> bool:
        """
        Save current configuration to file.

        Returns:
            True if configuration was saved successfully, False otherwise
        """
        try:
            with open(self.config_file, "w") as f:
                json.dump(self.config_data, f, indent=2)
            logger.info(f"Configuration saved to {self.config_file}")
            return True
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
            return False

    def get(self, section: str, key: str, default: Any = None) -> Any:
        """
        Get a configuration value.

        Args:
            section: Configuration section (e.g., 'ui', 'compression')
            key: Configuration key within section
            default: Default value if key is not found

        Returns:
            Configuration value or default if not found
        """
        try:
            return self.config_data[section][key]
        except KeyError:
            logger.warning(
                f"Configuration key {section}.{key} not found, using default: {default}"
            )
            return default

    def set(self, section: str, key: str, value: Any) -> None:
        """
        Set a configuration value.

        Args:
            section: Configuration section (e.g., 'ui', 'compression')
            key: Configuration key within section
            value: Value to set
        """
        try:
            if section not in self.config_data:
                self.config_data[section] = {}

            self.config_data[section][key] = value
        except Exception as e:
            logger.error(f"Error setting configuration {section}.{key}: {e}")

    def add_recent_file(self, file_path: str, is_source: bool = True) -> None:
        """
        Add a file to the recent files list.

        Args:
            file_path: Path to the file to add
            is_source: True if this is a source file, False for destination
        """
        try:
            list_key = "recent_sources" if is_source else "recent_destinations"
            recent_list = self.config_data["recent_files"][list_key]

            # Remove if already in list (to move to top)
            if file_path in recent_list:
                recent_list.remove(file_path)

            # Add to beginning of list
            recent_list.insert(0, file_path)

            # Trim list to max size
            max_recent = self.config_data["recent_files"]["max_recent"]
            self.config_data["recent_files"][list_key] = recent_list[:max_recent]

        except Exception as e:
            logger.error(f"Error adding recent file: {e}")

    def get_recent_files(self, is_source: bool = True) -> List[str]:
        """
        Get the list of recent files.

        Args:
            is_source: True to get source files, False for destinations

        Returns:
            List of recent file paths
        """
        list_key = "recent_sources" if is_source else "recent_destinations"
        return self.config_data["recent_files"].get(list_key, [])

    def clear_recent_files(self, is_source: bool = True) -> None:
        """
        Clear the list of recent files.

        Args:
            is_source: True to clear source files, False for destinations
        """
        list_key = "recent_sources" if is_source else "recent_destinations"
        self.config_data["recent_files"][list_key] = []


# Create a global configuration instance for easy access
config = AppConfig()
