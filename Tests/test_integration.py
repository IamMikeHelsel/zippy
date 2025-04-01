#!/usr/bin/env python
# Tests/test_integration.py
"""
Integration tests for the zippy application.
Tests interactions between multiple components.
"""

import os
import sys
import pytest
import tempfile
import shutil
from pathlib import Path
import zipfile
import concurrent.futures
import threading
import time

# Import the necessary modules
from src import core
from src import utils
from src.config import AppConfig
from src.feature_flags import FeatureFlags, FeatureFlag


class TestCoreConfigIntegration:
    """Test integration between core compression and configuration."""

    @pytest.fixture
    def test_environment(self):
        """Set up a test environment with files and directories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test files
            test_file1 = temp_path / "test1.txt"
            test_file1.write_text("Test content 1")

            test_file2 = temp_path / "test2.dat"
            test_file2.write_text("Binary data" * 100)  # Some larger content

            # Create a subdirectory with files
            sub_dir = temp_path / "subdir"
            sub_dir.mkdir()

            test_file3 = sub_dir / "test3.log"
            test_file3.write_text("Log data\n" * 10)

            # Create output directory
            output_dir = temp_path / "output"
            output_dir.mkdir()

            # Create a config directory
            config_dir = temp_path / "config"
            config_dir.mkdir()

            # Set up a test config
            test_config = AppConfig(config_dir)

            yield {
                "temp_dir": temp_dir,
                "test_file1": test_file1,
                "test_file2": test_file2,
                "sub_dir": sub_dir,
                "test_file3": test_file3,
                "output_dir": output_dir,
                "config_dir": config_dir,
                "config": test_config,
            }

    def test_compression_with_config_settings(self, test_environment, monkeypatch):
        """Test that compression uses settings from the config."""
        # Set a custom compression level in the config
        test_environment["config"].set("compression", "default_level", 9)

        # Mock the config in the core module
        original_config = sys.modules["src.core"].__dict__.get("config", None)
        sys.modules["src.core"].__dict__["config"] = test_environment["config"]

        try:
            # Test file path for output
            output_zip = test_environment["output_dir"] / "output_with_config.zip"

            # Use compress_with_feature_flags which reads from config
            core.compress_with_feature_flags(
                str(test_environment["test_file1"]), str(output_zip)
            )

            # Verify the zip was created
            assert output_zip.exists()
            assert zipfile.is_zipfile(output_zip)

        finally:
            # Restore original config
            if original_config is not None:
                sys.modules["src.core"].__dict__["config"] = original_config
            else:
                del sys.modules["src.core"].__dict__["config"]

    def test_default_output_path_from_config(self, test_environment, monkeypatch):
        """Test that default output path uses config settings."""
        # Set a custom output directory in the config
        custom_output_dir = test_environment["output_dir"] / "custom"
        custom_output_dir.mkdir()
        test_environment["config"].set(
            "compression", "default_output_dir", str(custom_output_dir)
        )

        # Mock the config in the utils module
        original_config = sys.modules["src.utils"].__dict__.get("config", None)
        sys.modules["src.utils"].__dict__["config"] = test_environment["config"]

        try:
            # Get default path for a test file
            default_path = utils.get_default_zip_path(
                str(test_environment["test_file1"])
            )

            # Verify the path uses the custom output directory
            assert str(custom_output_dir) in default_path

        finally:
            # Restore original config
            if original_config is not None:
                sys.modules["src.utils"].__dict__["config"] = original_config
            else:
                del sys.modules["src.utils"].__dict__["config"]


class TestCoreFeatureFlagsIntegration:
    """Test integration between core compression and feature flags."""

    @pytest.fixture
    def test_environment(self):
        """Set up a test environment with files and directories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test files and directories similar to previous fixture
            source_dir = temp_path / "source"
            source_dir.mkdir()

            # Create multiple test files
            for i in range(5):
                test_file = source_dir / f"test_file_{i}.txt"
                test_file.write_text(f"Test content for file {i}\n" * 100)

            # Create output directory
            output_dir = temp_path / "output"
            output_dir.mkdir()

            # Create and initialize feature flags
            feature_flags = FeatureFlags()

            yield {
                "temp_dir": temp_dir,
                "source_dir": source_dir,
                "output_dir": output_dir,
                "feature_flags": feature_flags,
            }

    def test_parallel_compression(self, test_environment, monkeypatch):
        """Test that parallel compression feature flag works."""
        # Enable parallel compression
        feature_flags = test_environment["feature_flags"]
        feature_flags.set_enabled(FeatureFlag.PARALLEL_COMPRESSION, True)

        # Mock the feature flags in the core module
        original_feature_flags = sys.modules["src.core"].__dict__.get(
            "feature_flags", None
        )
        sys.modules["src.core"].__dict__["feature_flags"] = feature_flags

        try:
            # Get all files in the source directory
            source_files = list(
                map(str, Path(test_environment["source_dir"]).glob("*.txt"))
            )
            assert len(source_files) > 1  # Ensure we have multiple files for testing

            # Output path for the zip
            output_zip = test_environment["output_dir"] / "parallel_test.zip"

            # Track progress calls to verify parallel execution
            progress_calls = []

            def track_progress(current, total):
                progress_calls.append((current, total))

            # Use compress_with_feature_flags which should use parallel compression
            core.compress_with_feature_flags(
                source_files, str(output_zip), progress_callback=track_progress
            )

            # Verify the zip was created
            assert output_zip.exists()
            assert zipfile.is_zipfile(output_zip)

            # Check contents of the zip
            with zipfile.ZipFile(output_zip, "r") as zipf:
                # Should contain entries for each file
                file_names = [Path(f).name for f in source_files]
                zip_names = zipf.namelist()
                for name in file_names:
                    assert any(name in entry for entry in zip_names)

        finally:
            # Restore original feature flags
            if original_feature_flags is not None:
                sys.modules["src.core"].__dict__["feature_flags"] = (
                    original_feature_flags
                )
            else:
                del sys.modules["src.core"].__dict__["feature_flags"]

    def test_memory_optimized_compression(self, test_environment, monkeypatch):
        """Test that memory optimization feature flag works."""
        # Enable memory optimization
        feature_flags = test_environment["feature_flags"]
        feature_flags.set_enabled(FeatureFlag.MEMORY_OPTIMIZED, True)

        # Save original constants
        original_max_file_size = core.MAX_FILE_SIZE_IN_MEMORY
        original_chunk_size = core.CHUNK_SIZE

        # Mock the feature flags in the core module
        original_feature_flags = sys.modules["src.core"].__dict__.get(
            "feature_flags", None
        )
        sys.modules["src.core"].__dict__["feature_flags"] = feature_flags

        try:
            # Create a larger test file
            large_file = test_environment["temp_dir"] / "large_file.bin"
            with open(large_file, "wb") as f:
                f.write(b"0" * 1024 * 1024)  # 1MB of zeros

            # Output path for the zip
            output_zip = test_environment["output_dir"] / "memory_optimized_test.zip"

            # Use compress_with_feature_flags which should apply memory optimization
            core.compress_with_feature_flags(str(large_file), str(output_zip))

            # Verify the memory optimization was applied
            assert core.MAX_FILE_SIZE_IN_MEMORY < original_max_file_size
            assert core.CHUNK_SIZE < original_chunk_size

            # Verify the zip was created
            assert output_zip.exists()
            assert zipfile.is_zipfile(output_zip)

        finally:
            # Restore original feature flags and constants
            if original_feature_flags is not None:
                sys.modules["src.core"].__dict__["feature_flags"] = (
                    original_feature_flags
                )
            else:
                del sys.modules["src.core"].__dict__["feature_flags"]

            core.MAX_FILE_SIZE_IN_MEMORY = original_max_file_size
            core.CHUNK_SIZE = original_chunk_size


class TestRoundtripCompression:
    """Test full roundtrip compression and decompression across components."""

    @pytest.fixture
    def complex_test_directory(self):
        """Create a complex directory structure for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir) / "test_data"
            base_dir.mkdir()

            # Create various files with different content types

            # Text files
            text_dir = base_dir / "text_files"
            text_dir.mkdir()
            for i in range(3):
                file = text_dir / f"document_{i}.txt"
                file.write_text(f"This is document {i} with some text content.\n" * 20)

            # "Binary" files
            binary_dir = base_dir / "binary_files"
            binary_dir.mkdir()
            for i in range(2):
                file = binary_dir / f"data_{i}.dat"
                with open(file, "wb") as f:
                    f.write(os.urandom(10 * 1024))  # 10KB of random data

            # Empty directory
            empty_dir = base_dir / "empty_dir"
            empty_dir.mkdir()

            # Nested directory structure
            nested_dir = base_dir / "nested"
            nested_dir.mkdir()
            for i in range(2):
                subdir = nested_dir / f"subdir_{i}"
                subdir.mkdir()
                for j in range(2):
                    file = subdir / f"nested_file_{i}_{j}.txt"
                    file.write_text(f"Nested file {i}-{j} content")

            # Create output and extract directories
            output_dir = Path(temp_dir) / "output"
            output_dir.mkdir()

            extract_dir = Path(temp_dir) / "extract"
            extract_dir.mkdir()

            yield {
                "temp_dir": temp_dir,
                "base_dir": base_dir,
                "text_dir": text_dir,
                "binary_dir": binary_dir,
                "empty_dir": empty_dir,
                "nested_dir": nested_dir,
                "output_dir": output_dir,
                "extract_dir": extract_dir,
            }

    def test_compress_and_uncompress_roundtrip(self, complex_test_directory):
        """Test full roundtrip compression and decompression of a complex directory."""
        # Define paths
        source_dir = complex_test_directory["base_dir"]
        zip_path = complex_test_directory["output_dir"] / "full_test.zip"
        extract_dir = complex_test_directory["extract_dir"]

        # Track progress
        compress_progress = []
        extract_progress = []

        def track_compress_progress(current, total):
            compress_progress.append((current, total))

        def track_extract_progress(current, total):
            extract_progress.append((current, total))

        # Step 1: Compress the directory
        core.compress_item(
            str(source_dir), str(zip_path), progress_callback=track_compress_progress
        )

        # Verify the zip was created
        assert zip_path.exists()
        assert zipfile.is_zipfile(zip_path)

        # Check that progress was tracked
        assert len(compress_progress) > 0
        assert (
            compress_progress[-1][0] == compress_progress[-1][1]
        )  # Final progress should be 100%

        # Step 2: Uncompress the archive
        core.uncompress_archive(
            str(zip_path), str(extract_dir), progress_callback=track_extract_progress
        )

        # Check that progress was tracked for extraction
        assert len(extract_progress) > 0
        assert (
            extract_progress[-1][0] == extract_progress[-1][1]
        )  # Final progress should be 100%

        # Step 3: Verify the extracted contents match the original
        self._verify_directories_match(source_dir, extract_dir)

    def _verify_directories_match(self, source_dir, extract_dir):
        """Verify that the contents of two directories match."""
        source_files = sorted(
            p.relative_to(source_dir)
            for p in Path(source_dir).glob("**/*")
            if p.is_file()
        )
        extract_files = sorted(
            p.relative_to(extract_dir)
            for p in Path(extract_dir).glob("**/*")
            if p.is_file()
        )

        # Check that we have the same set of files
        assert len(source_files) == len(extract_files)

        # Check that the paths match
        for src_path, ext_path in zip(source_files, extract_files):
            assert str(src_path) == str(ext_path)

            # Check file contents
            with (
                open(source_dir / src_path, "rb") as src_file,
                open(extract_dir / ext_path, "rb") as ext_file,
            ):
                src_content = src_file.read()
                ext_content = ext_file.read()
                assert src_content == ext_content, (
                    f"Contents don't match for {src_path}"
                )


if __name__ == "__main__":
    pytest.main(["-v", __file__])
