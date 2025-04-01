# Tests/test_compression.py
"""
Unit tests for compression functionality.
"""

import os
import sys
import unittest
import tempfile
from pathlib import Path
import zipfile
import threading
import time
import random
import shutil

# Ensure src is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core import compress_item, compress_with_feature_flags, uncompress_archive
from src.feature_flags import FeatureFlag, FeatureFlags
from src.config import AppConfig


class TestCompression(unittest.TestCase):
    """Test the compression and decompression functionality."""

    def setUp(self):
        """Set up test environment before each test."""
        # Create a temporary directory for test files
        self.test_dir = tempfile.mkdtemp()

        # Create test files of various sizes for compression tests
        self.test_files = self.create_test_files()

        # Create a directory for compression outputs
        self.output_dir = os.path.join(self.test_dir, "output")
        os.makedirs(self.output_dir, exist_ok=True)

        # Create a directory for extraction outputs
        self.extract_dir = os.path.join(self.test_dir, "extract")
        os.makedirs(self.extract_dir, exist_ok=True)

        # Set up temporary config and feature flags for testing
        self.test_config_dir = os.path.join(self.test_dir, "config")
        os.makedirs(self.test_config_dir, exist_ok=True)

        # Save original instances
        self._original_config = sys.modules["src.config"].config

        # Create and inject test instances
        self.test_config = AppConfig(self.test_config_dir)
        sys.modules["src.config"].config = self.test_config

        # Create a fresh feature flags instance
        self._original_feature_flags = sys.modules["src.feature_flags"].feature_flags
        self.feature_flags = FeatureFlags()
        sys.modules["src.feature_flags"].feature_flags = self.feature_flags

    def tearDown(self):
        """Clean up after each test."""
        # Restore original instances
        sys.modules["src.config"].config = self._original_config
        sys.modules["src.feature_flags"].feature_flags = self._original_feature_flags

        # Remove temporary directory and all its contents
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def create_test_files(self):
        """Create test files of various sizes for compression tests."""
        test_files = []

        # Create small test file (10KB)
        small_file = os.path.join(self.test_dir, "small.txt")
        with open(small_file, "wb") as f:
            f.write(b"A" * 10 * 1024)
        test_files.append(small_file)

        # Create medium test file (1MB)
        medium_file = os.path.join(self.test_dir, "medium.dat")
        with open(medium_file, "wb") as f:
            f.write(b"B" * 1024 * 1024)
        test_files.append(medium_file)

        # Create test directory with multiple files
        test_dir = os.path.join(self.test_dir, "testdir")
        os.makedirs(test_dir, exist_ok=True)

        # Add 5 small files to the directory
        for i in range(5):
            file_path = os.path.join(test_dir, f"file_{i}.txt")
            with open(file_path, "wb") as f:
                # Each file is 5-15KB with different content
                size = random.randint(5, 15) * 1024
                f.write((chr(65 + i) * 100).encode() * (size // 100))

        test_files.append(test_dir)

        return test_files

    def test_basic_compression(self):
        """Test basic compression of a single file."""
        test_file = self.test_files[0]  # Small test file
        zip_file = os.path.join(self.output_dir, "basic.zip")

        # Compress the file
        compress_item(test_file, zip_file)

        # Verify the zip file exists and is valid
        self.assertTrue(os.path.exists(zip_file))
        self.assertTrue(zipfile.is_zipfile(zip_file))

        # Verify the contents
        with zipfile.ZipFile(zip_file) as zf:
            file_list = zf.namelist()
            self.assertEqual(len(file_list), 1)
            self.assertEqual(file_list[0], os.path.basename(test_file))

    def test_directory_compression(self):
        """Test compression of a directory."""
        test_dir = self.test_files[2]  # Test directory
        zip_file = os.path.join(self.output_dir, "directory.zip")

        # Compress the directory
        compress_item(test_dir, zip_file)

        # Verify the zip file exists and is valid
        self.assertTrue(os.path.exists(zip_file))
        self.assertTrue(zipfile.is_zipfile(zip_file))

        # Verify the contents (should be 5 files)
        with zipfile.ZipFile(zip_file) as zf:
            file_list = zf.namelist()
            self.assertEqual(len(file_list), 5)

            # All files should be in the file listing
            for i in range(5):
                self.assertIn(f"file_{i}.txt", "\n".join(file_list))

    def test_compress_with_feature_flags_parallel(self):
        """Test compression with parallel compression feature flag enabled."""
        # Enable parallel compression
        self.feature_flags.set_enabled(FeatureFlag.PARALLEL_COMPRESSION, True)

        # Use all test files as sources
        zip_file = os.path.join(self.output_dir, "parallel.zip")

        # Define a simple progress callback for testing
        progress_values = []

        def progress_callback(current, total):
            progress_values.append((current, total))

        # Compress using the feature flags method
        compress_with_feature_flags(
            self.test_files, zip_file, progress_callback=progress_callback
        )

        # Verify the zip file exists and is valid
        self.assertTrue(os.path.exists(zip_file))
        self.assertTrue(zipfile.is_zipfile(zip_file))

        # Verify progress was reported (at least start and end)
        self.assertGreater(len(progress_values), 1)
        # Last progress should show 100% completion (current == total)
        self.assertEqual(progress_values[-1][0], progress_values[-1][1])

        # Verify the contents
        with zipfile.ZipFile(zip_file) as zf:
            # Check that all files are included
            file_list = zf.namelist()
            # We should have all the test files
            self.assertGreaterEqual(len(file_list), len(self.test_files))

    def test_compress_with_feature_flags_sequential(self):
        """Test compression with parallel compression feature flag disabled."""
        # Disable parallel compression
        self.feature_flags.set_enabled(FeatureFlag.PARALLEL_COMPRESSION, False)

        # Use all test files as sources
        zip_file = os.path.join(self.output_dir, "sequential.zip")

        # Compress using the feature flags method
        compress_with_feature_flags(self.test_files, zip_file)

        # Verify the zip file exists and is valid
        self.assertTrue(os.path.exists(zip_file))
        self.assertTrue(zipfile.is_zipfile(zip_file))

        # Verify the contents
        with zipfile.ZipFile(zip_file) as zf:
            # Check that all files are included
            file_list = zf.namelist()
            # There should be entries for each file
            self.assertGreaterEqual(len(file_list), len(self.test_files) - 1)
            # -1 because directory is expanded into individual files

    def test_compress_with_memory_optimization(self):
        """Test compression with memory optimization feature flag enabled."""
        # Enable memory optimization
        self.feature_flags.set_enabled(FeatureFlag.MEMORY_OPTIMIZED, True)

        # Compress a larger file
        test_file = self.test_files[1]  # Medium test file
        zip_file = os.path.join(self.output_dir, "memory_optimized.zip")

        # Compress using the feature flags method
        compress_with_feature_flags(test_file, zip_file)

        # Verify the zip file exists and is valid
        self.assertTrue(os.path.exists(zip_file))
        self.assertTrue(zipfile.is_zipfile(zip_file))

        # Verify the contents
        with zipfile.ZipFile(zip_file) as zf:
            file_list = zf.namelist()
            self.assertEqual(len(file_list), 1)
            self.assertEqual(file_list[0], os.path.basename(test_file))

    def test_compression_and_extraction(self):
        """Test full roundtrip of compression and extraction."""
        test_dir = self.test_files[2]  # Test directory
        zip_file = os.path.join(self.output_dir, "roundtrip.zip")
        extract_to = os.path.join(self.extract_dir, "roundtrip")

        # Compress the directory
        compress_item(test_dir, zip_file)

        # Verify the zip file exists and is valid
        self.assertTrue(os.path.exists(zip_file))
        self.assertTrue(zipfile.is_zipfile(zip_file))

        # Extract the zip file
        uncompress_archive(zip_file, extract_to)

        # Verify extraction worked - all files should be present
        for i in range(5):
            extracted_file = os.path.join(extract_to, f"file_{i}.txt")
            self.assertTrue(os.path.exists(extracted_file))

            # Verify file contents
            with open(os.path.join(test_dir, f"file_{i}.txt"), "rb") as original:
                original_data = original.read()

            with open(extracted_file, "rb") as extracted:
                extracted_data = extracted.read()

            self.assertEqual(original_data, extracted_data)

    def test_cancellation(self):
        """Test cancelling a compression operation."""
        test_dir = self.test_files[2]  # Test directory
        zip_file = os.path.join(self.output_dir, "cancelled.zip")

        # Create a cancellation event
        cancel_event = threading.Event()

        # Define a progress callback that cancels after first update
        def cancel_callback(current, total):
            cancel_event.set()

        # Start compression in a separate thread so we can cancel it
        compression_thread = threading.Thread(
            target=lambda: self.compress_and_catch_interruption(
                test_dir, zip_file, cancel_callback, cancel_event
            )
        )
        compression_thread.start()

        # Wait for thread to complete
        compression_thread.join(timeout=5.0)

        # Verify cancellation was triggered
        self.assertTrue(cancel_event.is_set())

        # File shouldn't exist or should be cleaned up after cancellation
        # (Note: There's a small race condition where the file might still exist temporarily)
        # Wait a short time to allow cleanup to complete
        time.sleep(0.1)
        self.assertFalse(os.path.exists(zip_file))

    def compress_and_catch_interruption(
        self, source, dest, progress_callback, cancel_event
    ):
        """Helper method to run compression and handle expected interruption exception."""
        try:
            compress_item(source, dest, progress_callback, cancel_event)
            self.fail("Expected InterruptedError was not raised")
        except InterruptedError:
            # This is expected
            pass
        except Exception as e:
            self.fail(f"Unexpected exception: {e}")


if __name__ == "__main__":
    unittest.main()
