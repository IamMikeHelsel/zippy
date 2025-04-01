#!/usr/bin/env python
# Tests/test_config.py
"""
Tests for the configuration management in the zippy application.
"""

import os
import pytest
import tempfile
import json
import shutil
from pathlib import Path
import sys

# Make sure config module can be imported
from src.config import AppConfig


class TestAppConfig:
    """Test the AppConfig class functionality."""

    @pytest.fixture
    def temp_config_dir(self):
        """Create a temporary directory for configuration files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def config(self, temp_config_dir):
        """Create an AppConfig instance with a temporary directory."""
        return AppConfig(temp_config_dir)

    def test_init_creates_config_file(self, temp_config_dir):
        """Test that initializing AppConfig creates a config file if it doesn't exist."""
        # Initialize a new config
        config = AppConfig(temp_config_dir)

        # Check that the config file was created
        config_file = Path(temp_config_dir) / "config.json"
        assert config_file.exists()

        # Verify the file contains valid JSON with default values
        with open(config_file, "r") as f:
            config_data = json.load(f)

        assert "ui" in config_data
        assert "theme" in config_data["ui"]
        assert "compression" in config_data
        assert "default_level" in config_data["compression"]

    def test_get_values(self, config):
        """Test retrieving configuration values."""
        # Test getting values at different levels
        ui_theme = config.get("ui", "theme")
        compression_level = config.get("compression", "default_level")

        # Check default values
        assert ui_theme == "dark"  # Default theme should be dark
        assert (
            0 <= compression_level <= 9
        )  # Default compression level should be between 0-9

        # Test getting a value with a default for a nonexistent key
        nonexistent = config.get("nonexistent", "key", "default_value")
        assert nonexistent == "default_value"

    def test_set_values(self, config):
        """Test setting configuration values."""
        # Set new values
        config.set("ui", "theme", "light")
        config.set("compression", "default_level", 9)

        # Verify values were changed
        assert config.get("ui", "theme") == "light"
        assert config.get("compression", "default_level") == 9

        # Create a new config instance to test persistence
        new_config = AppConfig(config.config_dir)

        # Values should be preserved
        assert new_config.get("ui", "theme") == "light"
        assert new_config.get("compression", "default_level") == 9

    def test_set_nested_values(self, config):
        """Test setting nested configuration values that didn't exist before."""
        # Set a nested value that doesn't exist
        config.set("new_section", "new_key", "new_value")

        # Verify the value was set
        assert config.get("new_section", "new_key") == "new_value"

        # Set a deeply nested value
        config.set("deep", "nested", "very_nested", "nested_value")

        # Verify the deeply nested value
        assert config.get("deep", "nested", "very_nested") == "nested_value"

    def test_save_and_load(self, config, temp_config_dir):
        """Test saving and loading configuration."""
        # Modify config
        config.set("test", "key1", "value1")

        # Save explicitly
        config.save()

        # Verify file content
        config_file = Path(temp_config_dir) / "config.json"
        with open(config_file, "r") as f:
            config_data = json.load(f)

        assert "test" in config_data
        assert "key1" in config_data["test"]
        assert config_data["test"]["key1"] == "value1"

        # Modify the file directly
        config_data["test"]["key1"] = "modified"
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        # Load the configuration
        config.load()

        # Verify the modified value was loaded
        assert config.get("test", "key1") == "modified"

    def test_invalid_json(self, config, temp_config_dir):
        """Test handling of invalid JSON in the config file."""
        # Write invalid JSON to config file
        config_file = Path(temp_config_dir) / "config.json"
        with open(config_file, "w") as f:
            f.write("This is not valid JSON")

        # Loading should fail but not raise an exception
        result = config.load()
        assert result is False

        # Default values should be used
        assert config.get("ui", "theme") in ["dark", "light", "system"]

    def test_recent_files(self, config):
        """Test the recent files functionality."""
        # Add some recent source files
        config.add_recent_file("/path/to/file1.txt", is_source=True)
        config.add_recent_file("/path/to/file2.txt", is_source=True)

        # Get recent source files
        recent_sources = config.get_recent_files(is_source=True)
        assert len(recent_sources) == 2
        assert "/path/to/file1.txt" in recent_sources
        assert "/path/to/file2.txt" in recent_sources

        # Add a recent destination
        config.add_recent_file("/path/to/output.zip", is_source=False)

        # Get recent destinations
        recent_destinations = config.get_recent_files(is_source=False)
        assert len(recent_destinations) == 1
        assert "/path/to/output.zip" in recent_destinations

        # Clear recent sources
        config.clear_recent_files(is_source=True)
        assert len(config.get_recent_files(is_source=True)) == 0

        # Destination files should still exist
        assert len(config.get_recent_files(is_source=False)) == 1

    def test_max_recent_files(self, config):
        """Test that the max_recent setting is respected."""
        # Get the max_recent value
        max_recent = config.get("recent_files", "max_recent")

        # Add more files than the max
        for i in range(max_recent + 5):
            config.add_recent_file(f"/path/to/file{i}.txt", is_source=True)

        # Check that only max_recent files are kept
        recent_files = config.get_recent_files(is_source=True)
        assert len(recent_files) == max_recent


if __name__ == "__main__":
    pytest.main(["-v", __file__])
