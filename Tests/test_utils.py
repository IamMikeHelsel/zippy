#!/usr/bin/env python
# Tests/test_utils.py
"""
Tests for the utilities module of the zippy application.
"""

import os
import pytest
import tempfile
import platform
from pathlib import Path
import datetime

# Import utilities module
from src import utils


class TestPathUtilities:
    """Test path-related utility functions."""

    def test_get_default_zip_path(self):
        """Test generating default zip path based on source path."""
        # Test with a file
        file_path = "/path/to/file.txt"
        zip_path = utils.get_default_zip_path(file_path)
        assert zip_path.endswith(".zip")
        assert "file" in zip_path

        # Test with a directory
        dir_path = "/path/to/directory"
        zip_path = utils.get_default_zip_path(dir_path)
        assert zip_path.endswith(".zip")
        assert "directory" in zip_path

        # Test with a path that already ends with .zip
        zip_file = "/path/to/archive.zip"
        zip_path = utils.get_default_zip_path(zip_file)
        assert zip_path.endswith(".zip")
        assert (
            zip_path != zip_file
        )  # Should create a new path, not return the same path

    def test_generate_filename(self):
        """Test generating filename from source path."""
        # Test with a single file
        file_path = "/path/to/file.txt"
        filename = utils.generate_filename(file_path)
        assert "file" in filename
        assert ".zip" not in filename  # Should not include extension

        # Test with a directory
        dir_path = "/path/to/directory"
        filename = utils.generate_filename(dir_path)
        assert "directory" in filename

        # Test with multiple files (semicolon-separated)
        multi_path = "/path/to/file1.txt;/path/to/file2.txt"
        filename = utils.generate_filename(multi_path)
        assert filename  # Should return something non-empty
        assert "files" in filename.lower()  # Should indicate multiple files


class TestFileSystemUtilities:
    """Test file system utility functions."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for file operations."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    def test_ensure_dir_exists(self, temp_dir):
        """Test ensuring a directory exists."""
        # Test with a new directory
        new_dir = os.path.join(temp_dir, "new_directory")
        utils.ensure_dir_exists(new_dir)
        assert os.path.exists(new_dir)
        assert os.path.isdir(new_dir)

        # Test with an existing directory (should not raise exception)
        utils.ensure_dir_exists(new_dir)
        assert os.path.exists(new_dir)

    def test_safe_delete(self, temp_dir):
        """Test safely deleting a file."""
        # Create a test file
        test_file = os.path.join(temp_dir, "test_file.txt")
        with open(test_file, "w") as f:
            f.write("Test content")

        # Delete the file
        result = utils.safe_delete(test_file)
        assert result is True
        assert not os.path.exists(test_file)

        # Test with nonexistent file
        result = utils.safe_delete("nonexistent_file.txt")
        assert result is False

    def test_get_free_disk_space(self, temp_dir):
        """Test getting free disk space."""
        # Just check that it returns a reasonable value
        free_space = utils.get_free_disk_space(temp_dir)
        assert isinstance(free_space, (int, float))
        assert free_space > 0  # Should be positive


class TestTimeUtilities:
    """Test time-related utility functions."""

    def test_format_timestamp(self):
        """Test formatting a timestamp."""
        # Create a specific timestamp
        timestamp = datetime.datetime(2023, 5, 15, 10, 30, 45)
        formatted = utils.format_timestamp(timestamp)

        # Check that the formatted string contains expected elements
        assert "2023" in formatted
        assert "05" in formatted or "5" in formatted  # Month
        assert "15" in formatted  # Day

        # Test with current time
        formatted_now = utils.format_timestamp()
        assert formatted_now  # Should return a non-empty string

    def test_format_duration(self):
        """Test formatting a duration in seconds."""
        # Test with seconds only
        assert utils.format_duration(30) == "30 seconds"

        # Test with minutes and seconds
        assert utils.format_duration(90) in ["1 minute 30 seconds", "1m 30s"]

        # Test with hours, minutes, seconds
        assert "hour" in utils.format_duration(3665).lower()
        assert "minute" in utils.format_duration(3665).lower()


class TestFormatUtilities:
    """Test formatting utility functions."""

    def test_format_size(self):
        """Test formatting a size in bytes to human-readable format."""
        # Test bytes
        assert utils.format_size(500) == "500 B"

        # Test kilobytes
        assert utils.format_size(1024) in ["1.0 KB", "1 KB"]

        # Test megabytes
        assert utils.format_size(1048576) in ["1.0 MB", "1 MB"]  # 1 MiB in bytes

        # Test gigabytes
        assert utils.format_size(1073741824) in ["1.0 GB", "1 GB"]  # 1 GiB in bytes

    def test_get_compression_level_name(self):
        """Test getting a descriptive name for a compression level."""
        # Test known levels
        assert utils.get_compression_level_name(0).lower() == "none"
        assert utils.get_compression_level_name(1).lower() == "fastest"
        assert utils.get_compression_level_name(9).lower() == "maximum"

        # Test middle level
        assert utils.get_compression_level_name(5)  # Should return something non-empty


if __name__ == "__main__":
    pytest.main(["-v", __file__])
