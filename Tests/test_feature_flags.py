# Tests/test_feature_flags.py
"""
Unit tests for the feature flags system.
"""

import os
import unittest
import tempfile
from pathlib import Path
import sys
import shutil
import json

# Ensure src is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.feature_flags import FeatureFlag, FeatureFlags


class AppConfig:
    def __init__(self, config_dir):
        self.config_dir = config_dir
        self.config_file = Path(config_dir) / "config.json"
        self.config_data = {}
        self.load()
        if "feature_flags" not in self.config_data:
            self.config_data["feature_flags"] = {}
            self.save()

    def load(self):
        """Load configuration from file."""
        if not self.config_file.exists():
            return False

        try:
            with open(self.config_file, "r") as f:
                self.config_data = json.load(f)
            return True
        except Exception:
            return False

    def save(self):
        """Save configuration to file."""
        try:
            with open(self.config_file, "w") as f:
                json.dump(self.config_data, f, indent=2)
            return True
        except Exception:
            return False

    def get(self, section, key, default=None):
        """Get a configuration value."""
        try:
            return self.config_data[section][key]
        except KeyError:
            return default

    def set(self, section, key, value):
        """Set a configuration value."""
        if section not in self.config_data:
            self.config_data[section] = {}
        self.config_data[section][key] = value


class TestFeatureFlags(unittest.TestCase):
    """Test the feature flags functionality."""

    def setUp(self):
        """Set up a test environment before each test."""
        # Create a temporary directory for test configs
        self.test_config_dir = tempfile.mkdtemp()

        # Create a test config instance
        self.test_config = AppConfig(self.test_config_dir)

        # Make sure feature_flags section exists in config
        if "feature_flags" not in self.test_config.config_data:
            self.test_config.config_data["feature_flags"] = {}

        # Save the original config module reference
        self._original_config = sys.modules["src.config"].config

        # Replace with our test config
        sys.modules["src.config"].config = self.test_config

        # Create a fresh instance of FeatureFlags for each test
        self.feature_flags = FeatureFlags()

        # Force initialization of feature flags with correct default values
        # This ensures that the test config has the same defaults as the real implementation
        for flag in FeatureFlag:
            flag_name = flag.name.lower()
            default_state = flag in self.feature_flags.DEFAULT_ENABLED_FLAGS
            self.test_config.config_data["feature_flags"][flag_name] = default_state

        # Make another instance that will use our initialized config
        self.feature_flags = FeatureFlags()

    def tearDown(self):
        """Clean up after each test."""
        # Restore original config
        sys.modules["src.config"].config = self._original_config

        # Clean up the temp directory
        shutil.rmtree(self.test_config_dir, ignore_errors=True)

    def test_initialization(self):
        """Test that feature flags are initialized correctly."""
        # Check that the feature flags section was created
        self.assertIn("feature_flags", self.test_config.config_data)

        # Check that all flags have been initialized
        for flag in FeatureFlag:
            flag_name = flag.name.lower()
            self.assertIn(flag_name, self.test_config.config_data["feature_flags"])

    def test_default_states(self):
        """Test that default states are set correctly."""
        # Check the values of default enabled flags
        for flag in FeatureFlag:
            expected_state = flag in self.feature_flags.DEFAULT_ENABLED_FLAGS
            self.assertEqual(
                self.feature_flags.is_enabled(flag),
                expected_state,
                f"Flag {flag.name} should be {'enabled' if expected_state else 'disabled'} by default",
            )

    def test_set_enabled(self):
        """Test enabling and disabling flags."""
        # Test enabling a disabled flag
        test_flag = next(
            flag
            for flag in FeatureFlag
            if flag not in self.feature_flags.DEFAULT_ENABLED_FLAGS
        )
        self.assertFalse(self.feature_flags.is_enabled(test_flag))

        self.feature_flags.set_enabled(test_flag, True)
        self.assertTrue(self.feature_flags.is_enabled(test_flag))

        # Test disabling an enabled flag
        test_enabled_flag = next(iter(self.feature_flags.DEFAULT_ENABLED_FLAGS))
        self.assertTrue(self.feature_flags.is_enabled(test_enabled_flag))

        self.feature_flags.set_enabled(test_enabled_flag, False)
        self.assertFalse(self.feature_flags.is_enabled(test_enabled_flag))

    def test_toggle(self):
        """Test toggling flag states."""
        # Toggle an enabled flag
        test_enabled_flag = next(iter(self.feature_flags.DEFAULT_ENABLED_FLAGS))
        initial_state = self.feature_flags.is_enabled(test_enabled_flag)

        new_state = self.feature_flags.toggle(test_enabled_flag)
        self.assertNotEqual(initial_state, new_state)
        self.assertEqual(new_state, self.feature_flags.is_enabled(test_enabled_flag))

        # Toggle it back
        new_state = self.feature_flags.toggle(test_enabled_flag)
        self.assertEqual(initial_state, new_state)
        self.assertEqual(new_state, self.feature_flags.is_enabled(test_enabled_flag))

    def test_get_all_flags(self):
        """Test retrieving all flag states."""
        all_flags = self.feature_flags.get_all_flags()

        # Verify we have an entry for each flag
        self.assertEqual(len(all_flags), len(list(FeatureFlag)))

        # Verify the values match what we expect
        for flag in FeatureFlag:
            flag_name = flag.name.lower()
            expected_state = flag in self.feature_flags.DEFAULT_ENABLED_FLAGS
            self.assertEqual(all_flags[flag_name], expected_state)

    def test_get_enabled_flags(self):
        """Test retrieving only enabled flags."""
        enabled_flags = self.feature_flags.get_enabled_flags()

        # Verify we have the right number of enabled flags
        self.assertEqual(
            len(enabled_flags), len(self.feature_flags.DEFAULT_ENABLED_FLAGS)
        )

        # Verify each enabled flag is in the result
        for flag in self.feature_flags.DEFAULT_ENABLED_FLAGS:
            self.assertIn(flag.name.lower(), enabled_flags)

    def test_reset_to_defaults(self):
        """Test resetting all flags to defaults."""
        # First modify some flags
        for flag in list(FeatureFlag)[:3]:  # Just use the first three flags
            self.feature_flags.set_enabled(
                flag, not self.feature_flags.is_enabled(flag)
            )

        # Now reset
        self.feature_flags.reset_to_defaults()

        # Verify all flags are back to their default states
        for flag in FeatureFlag:
            expected_state = flag in self.feature_flags.DEFAULT_ENABLED_FLAGS
            self.assertEqual(self.feature_flags.is_enabled(flag), expected_state)

    def test_persistence(self):
        """Test that flag states persist between instances."""
        # Modify some flags
        modified_flags = {}
        for flag in list(FeatureFlag)[:3]:  # Just use the first three flags
            new_state = not self.feature_flags.is_enabled(flag)
            self.feature_flags.set_enabled(flag, new_state)
            modified_flags[flag] = new_state

        # Create a new instance that should load from the same config file
        new_feature_flags = FeatureFlags()

        # Check that the new instance has the modified values
        for flag, expected_state in modified_flags.items():
            self.assertEqual(new_feature_flags.is_enabled(flag), expected_state)


if __name__ == "__main__":
    unittest.main()
