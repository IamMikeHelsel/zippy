#!/usr/bin/env python
# Tests/test_cli.py
"""
Tests for the CLI module of the zippy application.
"""

import os
import sys
import pytest
import tempfile
import shutil
from pathlib import Path
import subprocess
import threading
import time
import zipfile

# Make sure CLI can be imported
from src import cli
from src.cli import (
    ProgressReporter,
    parse_arguments,
    compress_files,
    uncompress_files,
    main,
)


class TestCLIArgumentParser:
    """Test the CLI argument parser functionality."""

    def test_compress_command_parsing(self):
        """Test parsing compress command arguments."""
        # Test with minimal arguments
        args = parse_arguments(["compress", "file.txt"])
        assert args.command == "compress"
        assert args.source == "file.txt"
        assert not args.verbose
        assert not args.quiet
        assert args.level == 6  # Default compression level

        # Test with all options
        args = parse_arguments(
            [
                "compress",
                "folder/",
                "--output=archive.zip",
                "--level=9",
                "--verbose",
                "--no-progress",
            ]
        )
        assert args.command == "compress"
        assert args.source == "folder/"
        assert args.output == "archive.zip"
        assert args.level == 9
        assert args.verbose
        assert args.no_progress

    def test_uncompress_command_parsing(self):
        """Test parsing uncompress command arguments."""
        # Test with minimal arguments
        args = parse_arguments(["uncompress", "archive.zip"])
        assert args.command == "uncompress"
        assert args.archive == "archive.zip"

        # Test with all options
        args = parse_arguments(
            [
                "uncompress",
                "archive.zip",
                "--output=extracted_dir/",
                "--verbose",
                "--quiet",
            ]
        )
        assert args.command == "uncompress"
        assert args.archive == "archive.zip"
        assert args.output == "extracted_dir/"
        assert args.verbose
        assert args.quiet


class TestProgressReporter:
    """Test the progress reporter functionality."""

    def test_init_with_defaults(self):
        """Test initializing with default values."""
        reporter = ProgressReporter()
        assert not reporter.quiet
        assert not reporter.no_progress

    def test_init_with_custom_values(self):
        """Test initializing with custom values."""
        reporter = ProgressReporter(quiet=True, no_progress=True)
        assert reporter.quiet
        assert reporter.no_progress

    def test_update_progress(self, capsys):
        """Test that progress updates print to stdout."""
        # Test with quiet mode (nothing should be printed)
        reporter_quiet = ProgressReporter(quiet=True)
        reporter_quiet.update(50, 100)
        captured = capsys.readouterr()
        assert not captured.out

        # Test with no_progress flag (should print simple messages only)
        reporter_no_progress = ProgressReporter(no_progress=True)
        reporter_no_progress.update(0, 100)  # Start
        captured = capsys.readouterr()
        assert "Processing" in captured.out

        reporter_no_progress.update(100, 100)  # Complete
        captured = capsys.readouterr()
        assert "Complete" in captured.out

        # Test normal operation (should print progress bar)
        reporter = ProgressReporter()
        reporter.update(25, 100)
        captured = capsys.readouterr()
        assert "%" in captured.out  # Should contain percentage
        assert "█" in captured.out  # Should contain progress bar character


@pytest.fixture
def test_files():
    """Create test files and directories for CLI testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a source directory with files
        source_dir = Path(temp_dir) / "source"
        source_dir.mkdir()

        # Create test files
        file1 = source_dir / "file1.txt"
        file1.write_text("This is test file 1")

        file2 = source_dir / "file2.txt"
        file2.write_text("This is test file 2")

        # Create a subdirectory with a file
        subdir = source_dir / "subdir"
        subdir.mkdir()
        file3 = subdir / "file3.txt"
        file3.write_text("This is test file 3 in a subdirectory")

        # Create output and extract directories
        output_dir = Path(temp_dir) / "output"
        output_dir.mkdir()

        extract_dir = Path(temp_dir) / "extract"
        extract_dir.mkdir()

        # Create a test zip file
        test_zip = output_dir / "test.zip"
        with zipfile.ZipFile(test_zip, "w") as zipf:
            zipf.writestr("test1.txt", "Test content 1")
            zipf.writestr("test2.txt", "Test content 2")
            zipf.writestr("subdir/test3.txt", "Test content 3 in subdir")

        yield {
            "temp_dir": temp_dir,
            "source_dir": source_dir,
            "file1": file1,
            "file2": file2,
            "subdir": subdir,
            "file3": file3,
            "output_dir": output_dir,
            "extract_dir": extract_dir,
            "test_zip": test_zip,
        }


class TestCLIExecution:
    """Test executing CLI commands through entry points."""

    def test_compress_command_execution(self, test_files):
        """Test executing the compress command."""
        # Use a threading.Event to handle cancellation in tests
        cancel_event = threading.Event()
        args = parse_arguments(
            [
                "compress",
                str(test_files["file1"]),
                f"--output={test_files['output_dir']}/compressed.zip",
            ]
        )

        # Mock setup for non-interactive environment
        args.quiet = True  # Suppress output

        # Execute the compress command
        result = compress_files(args)

        # Verify the result
        assert result == 0  # Success exit code
        assert os.path.exists(os.path.join(test_files["output_dir"], "compressed.zip"))

        # Verify the contents of the zip
        with zipfile.ZipFile(
            os.path.join(test_files["output_dir"], "compressed.zip")
        ) as zipf:
            assert "file1.txt" in zipf.namelist()
            assert zipf.read("file1.txt").decode() == "This is test file 1"

    def test_uncompress_command_execution(self, test_files):
        """Test executing the uncompress command."""
        args = parse_arguments(
            [
                "uncompress",
                str(test_files["test_zip"]),
                f"--output={test_files['extract_dir']}",
            ]
        )

        # Mock setup for non-interactive environment
        args.quiet = True  # Suppress output

        # Execute the uncompress command
        result = uncompress_files(args)

        # Verify the result
        assert result == 0  # Success exit code
        assert os.path.exists(os.path.join(test_files["extract_dir"], "test1.txt"))
        assert os.path.exists(os.path.join(test_files["extract_dir"], "test2.txt"))
        assert os.path.exists(
            os.path.join(test_files["extract_dir"], "subdir/test3.txt")
        )

        # Verify the contents of the extracted files
        with open(os.path.join(test_files["extract_dir"], "test1.txt")) as f:
            assert f.read() == "Test content 1"

    def test_error_handling(self, test_files):
        """Test error handling in CLI commands."""
        # Test with nonexistent source
        args = parse_arguments(
            [
                "compress",
                "nonexistent_file.txt",
                f"--output={test_files['output_dir']}/nonexistent.zip",
            ]
        )
        args.quiet = True

        # Should return non-zero exit code for error
        result = compress_files(args)
        assert result != 0

        # Test with nonexistent archive
        args = parse_arguments(
            [
                "uncompress",
                "nonexistent_archive.zip",
                f"--output={test_files['extract_dir']}",
            ]
        )
        args.quiet = True

        # Should return non-zero exit code for error
        result = uncompress_files(args)
        assert result != 0


if __name__ == "__main__":
    pytest.main(["-v", __file__])
