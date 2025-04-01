# src/feature_flags.py
"""
Feature flag system for Zippy.

This module provides functionality for controlling the availability of features
in the application through flags that can be enabled or disabled. It integrates
with the configuration system to persist feature flag states.
"""

import logging
from enum import Enum, auto
from typing import Dict, Any, Optional, List, Set
from .config import config

# Configure module logger
logger = logging.getLogger(__name__)


class FeatureFlag(Enum):
    """
    Enumeration of available feature flags in the application.

    Add new features here as they are implemented. Each flag represents
    a feature that can be enabled or disabled.
    """

    # Core features
    PARALLEL_COMPRESSION = auto()  # Enable parallel compression for better performance
    DEEP_INSPECTION = (
        auto()
    )  # Enable deeper archive inspection (slower but more accurate)
    MEMORY_OPTIMIZED = auto()  # Enable memory optimization for large files

    # UI Features
    DARK_MODE = auto()  # Enable dark mode in the UI
    DETAILED_PROGRESS = auto()  # Show detailed progress information
    PREVIEW_CONTENT = auto()  # Enable archive content preview
    DRAG_DROP = auto()  # Enable drag and drop support

    # Advanced features
    PASSWORD_PROTECTION = auto()  # Enable password protection for archives
    COMPRESSION_PRESETS = (
        auto()
    )  # Enable compression presets (fastest, balanced, smallest)
    SPLIT_ARCHIVES = auto()  # Enable creating multi-part archives

    # Experimental features
    CLOUD_SYNC = auto()  # Cloud storage sync integration
    AI_COMPRESSION = auto()  # Smart compression using content analysis
    INTEGRITY_VERIFICATION = auto()  # Advanced integrity verification


class FeatureFlags:
    """
    Manages feature flags for controlling feature availability.

    This class provides methods to check if features are enabled,
    and to enable or disable features. The state of feature flags
    is persisted in the configuration system.
    """

    # Configuration section name for feature flags
    SECTION_NAME = "feature_flags"

    # Default flag states - features that are enabled by default
    DEFAULT_ENABLED_FLAGS = {
        FeatureFlag.PARALLEL_COMPRESSION,
        FeatureFlag.DARK_MODE,
        FeatureFlag.DETAILED_PROGRESS,
        FeatureFlag.MEMORY_OPTIMIZED,
    }

    # Features that are considered experimental and should warn when enabled
    EXPERIMENTAL_FLAGS = {
        FeatureFlag.CLOUD_SYNC,
        FeatureFlag.AI_COMPRESSION,
        FeatureFlag.INTEGRITY_VERIFICATION,
    }

    def __init__(self):
        """Initialize feature flags system."""
        # Ensure feature flags section exists in config
        if self.SECTION_NAME not in config.config_data:
            config.config_data[self.SECTION_NAME] = {}
            self._initialize_default_flags()
            config.save()

    def _initialize_default_flags(self):
        """Initialize default flag states in the configuration."""
        for flag in FeatureFlag:
            default_state = flag in self.DEFAULT_ENABLED_FLAGS
            flag_name = flag.name.lower()
            config.config_data[self.SECTION_NAME][flag_name] = default_state

        logger.info("Initialized default feature flag states")

    def is_enabled(self, feature: FeatureFlag) -> bool:
        """
        Check if a feature flag is enabled.

        Args:
            feature: The feature flag to check

        Returns:
            True if the feature is enabled, False otherwise
        """
        flag_name = feature.name.lower()

        # If flag doesn't exist in config, initialize it with default state
        if flag_name not in config.config_data.get(self.SECTION_NAME, {}):
            default_state = feature in self.DEFAULT_ENABLED_FLAGS
            self.set_enabled(feature, default_state)
            return default_state

        return config.get(
            self.SECTION_NAME, flag_name, default=feature in self.DEFAULT_ENABLED_FLAGS
        )

    def set_enabled(self, feature: FeatureFlag, enabled: bool) -> None:
        """
        Enable or disable a feature flag.

        Args:
            feature: The feature flag to modify
            enabled: Whether to enable (True) or disable (False) the feature
        """
        flag_name = feature.name.lower()

        # Log when enabling experimental features
        if enabled and feature in self.EXPERIMENTAL_FLAGS:
            logger.warning(f"Enabling experimental feature: {feature.name}")

        config.set(self.SECTION_NAME, flag_name, enabled)
        config.save()

        logger.info(
            f"Feature flag {feature.name} {'enabled' if enabled else 'disabled'}"
        )

    def toggle(self, feature: FeatureFlag) -> bool:
        """
        Toggle a feature flag's state.

        Args:
            feature: The feature flag to toggle

        Returns:
            The new state (True for enabled, False for disabled)
        """
        new_state = not self.is_enabled(feature)
        self.set_enabled(feature, new_state)
        return new_state

    def get_all_flags(self) -> Dict[str, bool]:
        """
        Get the state of all feature flags.

        Returns:
            A dictionary mapping flag names to their enabled state
        """
        result = {}
        for flag in FeatureFlag:
            flag_name = flag.name.lower()
            result[flag_name] = self.is_enabled(flag)
        return result

    def get_enabled_flags(self) -> List[str]:
        """
        Get a list of all enabled feature flags.

        Returns:
            A list of names of all enabled feature flags
        """
        return [flag.name.lower() for flag in FeatureFlag if self.is_enabled(flag)]

    def reset_to_defaults(self) -> None:
        """Reset all feature flags to their default states."""
        for flag in FeatureFlag:
            default_state = flag in self.DEFAULT_ENABLED_FLAGS
            self.set_enabled(flag, default_state)

        logger.info("All feature flags reset to default values")


# Create a global instance for easy access
feature_flags = FeatureFlags()
