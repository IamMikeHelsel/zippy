# tests/test_core.py
import pytest
import zipfile
from pathlib import Path
import os
import shutil
import tempfile
import threading
import time
from unittest.mock import patch, MagicMock

# Make sure core can be imported: Requires 'src' in pythonpath (configured in pyproject.toml)
from src import core
from src.feature_flags import FeatureFlag


@pytest.fixture
def test_files(tmp_path):
    """Create some test files and directories in a temporary location."""
    base_dir = tmp_path / "test_source"
    base_dir.mkdir()
    file1 = base_dir / "file1.txt"
    file1.write_text("This is file 1.")
    sub_dir = base_dir / "subdir"
    sub_dir.mkdir()
    file2 = sub_dir / "file2.log"
    file2.write_text("Log message.")
    empty_dir = base_dir / "empty_subdir"
    empty_dir.mkdir()
    file3 = base_dir / "toplevel.dat"
    file3.write_text("Data file")

    # Single file outside the main test dir
    single_file = tmp_path / "single.txt"
    single_file.write_text("A single file.")

    return {
        "base_dir": base_dir,
        "file1": file1,
        "sub_dir": sub_dir,
        "file2": file2,
        "empty_dir": empty_dir,
        "file3": file3,
        "single_file": single_file,
        "output_dir": tmp_path / "output",
        "extract_dir": tmp_path / "extracted",
    }


def test_compress_single_file(test_files, tmp_path):
    """Test compressing a single file."""
    source_file = test_files["single_file"]
    output_zip = test_files["output_dir"] / "single_file.zip"
    extract_dir = test_files["extract_dir"]

    core.compress_item(str(source_file), str(output_zip))

    assert output_zip.exists()
    assert zipfile.is_zipfile(output_zip)

    # Verify contents
    with zipfile.ZipFile(output_zip, "r") as zipf:
        assert len(zipf.namelist()) == 1
        assert zipf.namelist()[0] == source_file.name
        zipf.extractall(extract_dir)

    extracted_file = extract_dir / source_file.name
    assert extracted_file.exists()
    assert extracted_file.read_text() == source_file.read_text()


def test_compress_directory(test_files, tmp_path):
    """Test compressing a directory with subdirectories."""
    source_dir = test_files["base_dir"]
    output_zip = test_files["output_dir"] / "directory.zip"
    extract_dir = test_files["extract_dir"]

    core.compress_item(str(source_dir), str(output_zip))

    assert output_zip.exists()
    assert zipfile.is_zipfile(output_zip)

    # Verify contents
    with zipfile.ZipFile(output_zip, "r") as zipf:
        # Check relative paths in zip - normalize path separators for cross-platform compatibility
        zip_names = set(name.replace("/", os.sep) for name in zipf.namelist())
        expected_names = {
            "file1.txt",
            "toplevel.dat",
            os.path.join("subdir", "file2.log"),
            # Note: zipfile typically doesn't store empty directories explicitly
            # unless specifically added. os.walk based approach won't add empty_subdir
        }
        assert zip_names == expected_names
        zipf.extractall(extract_dir)

    # Check extracted structure and content
    extracted_base = extract_dir  # Files are extracted directly into the target
    assert (extracted_base / "file1.txt").read_text() == test_files["file1"].read_text()
    assert (extracted_base / "toplevel.dat").read_text() == test_files[
        "file3"
    ].read_text()
    assert (extracted_base / "subdir" / "file2.log").read_text() == test_files[
        "file2"
    ].read_text()
    # Check if subdir exists
    assert (extracted_base / "subdir").is_dir()
    # The empty dir won't be recreated by extractall unless it contained a file or was explicitly added
    assert not (extracted_base / "empty_subdir").exists()


def test_uncompress_archive(test_files, tmp_path):
    """Test uncompressing an archive."""
    # First, create an archive to test with
    source_dir = test_files["base_dir"]
    zip_path = test_files["output_dir"] / "test_uncompress.zip"
    core.compress_item(str(source_dir), str(zip_path))

    # Now, uncompress it
    extract_dir = test_files["extract_dir"]
    core.uncompress_archive(str(zip_path), str(extract_dir))

    # Verify extracted content (similar to test_compress_directory)
    assert (extract_dir / "file1.txt").exists()
    assert (extract_dir / "toplevel.dat").exists()
    assert (extract_dir / "subdir" / "file2.log").exists()
    assert (extract_dir / "file1.txt").read_text() == test_files["file1"].read_text()


def test_compress_nonexistent_source(test_files):
    """Test compressing a source that doesn't exist."""
    source = test_files["base_dir"] / "nonexistent.file"
    output_zip = test_files["output_dir"] / "error.zip"
    with pytest.raises(FileNotFoundError):
        core.compress_item(str(source), str(output_zip))
    assert not output_zip.exists()  # Ensure no partial zip is left


def test_uncompress_nonexistent_archive(test_files):
    """Test uncompressing a zip file that doesn't exist."""
    zip_path = test_files["output_dir"] / "nonexistent.zip"
    extract_dir = test_files["extract_dir"]
    with pytest.raises(FileNotFoundError):
        core.uncompress_archive(str(zip_path), str(extract_dir))


def test_uncompress_invalid_file(test_files):
    """Test uncompressing a file that is not a zip archive."""
    invalid_file = test_files["single_file"]  # Use a regular text file
    extract_dir = test_files["extract_dir"]

    # The function now raises a ValueError for invalid archives, not BadZipFile
    with pytest.raises(ValueError):
        core.uncompress_archive(str(invalid_file), str(extract_dir))


# Test progress callback (basic check)
def test_progress_callback(test_files, tmp_path):
    """Test if the progress callback is called."""
    source_dir = test_files["base_dir"]
    output_zip = test_files["output_dir"] / "progress_test.zip"
    extract_dir = test_files["extract_dir"]
    zip_path = output_zip  # Use the same path for consistency

    compress_calls = []
    uncompress_calls = []

    def mock_compress_progress(current, total):
        compress_calls.append((current, total))

    def mock_uncompress_progress(current, total):
        uncompress_calls.append((current, total))

    # Test compression progress
    core.compress_item(
        str(source_dir), str(output_zip), progress_callback=mock_compress_progress
    )
    assert len(compress_calls) > 0  # Should have been called
    assert (
        compress_calls[-1][0] == compress_calls[-1][1]
    )  # Last call should show completion

    # Test uncompression progress
    core.uncompress_archive(
        str(zip_path), str(extract_dir), progress_callback=mock_uncompress_progress
    )
    assert len(uncompress_calls) > 0  # Should have been called
    # Our improved implementation reports progress at start, during, and end
    assert len(uncompress_calls) >= 2
    assert uncompress_calls[0][0] == 0  # First call shows 0 progress
    assert (
        uncompress_calls[-1][0] == uncompress_calls[-1][1]
    )  # Last call shows completion


def test_detect_archive_format_zip(test_files, tmp_path):
    """Test detecting a ZIP archive format."""
    # Create a test zip file
    zip_file = tmp_path / "test.zip"
    source_file = test_files["single_file"]
    with zipfile.ZipFile(zip_file, "w") as zf:
        zf.write(source_file, arcname=source_file.name)

    # Test detection
    format = core.detect_archive_format(str(zip_file))
    assert format == core.ArchiveFormat.ZIP


def test_detect_archive_format_invalid(test_files):
    """Test detecting an invalid archive format."""
    # Use a text file as an invalid archive
    invalid_file = test_files["single_file"]

    # Test detection of invalid format should raise ValueError
    with pytest.raises(ValueError):
        core.detect_archive_format(str(invalid_file))


def test_resource_monitor():
    """Test the ResourceMonitor class."""
    # Initialize monitor
    monitor = core.ResourceMonitor()

    # Start monitoring
    monitor.start()

    # Check that the monitor thread is running
    assert monitor._monitor_thread is not None
    assert monitor._monitor_thread.is_alive()

    # Check resource usage properties
    usage = monitor.current_usage
    assert isinstance(usage, dict)
    assert "memory_percent" in usage
    assert "cpu_percent" in usage

    # Check critical resource flag (should be False initially)
    assert monitor.is_resource_critical is False

    # Stop monitoring
    monitor.stop()

    # Wait for thread to terminate
    time.sleep(0.1)

    # Verify thread stopped
    assert not monitor._monitor_thread.is_alive()


def test_compress_with_feature_flags(test_files, tmp_path):
    """Test the compress_with_feature_flags function."""
    source_path = test_files["single_file"]
    output_zip = tmp_path / "feature_test.zip"

    # Mock feature flags
    with patch("src.feature_flags.feature_flags.is_enabled") as mock_is_enabled:
        # Configure mock to return False for all feature flags
        mock_is_enabled.return_value = False

        # Call the function
        core.compress_with_feature_flags(str(source_path), str(output_zip))

        # Verify the output
        assert output_zip.exists()
        assert zipfile.is_zipfile(output_zip)

        # Verify the mock was called
        mock_is_enabled.assert_any_call(FeatureFlag.DEEP_INSPECTION)
        mock_is_enabled.assert_any_call(FeatureFlag.MEMORY_OPTIMIZED)
        mock_is_enabled.assert_any_call(FeatureFlag.PARALLEL_COMPRESSION)


def test_compress_with_feature_flags_multi_paths(test_files, tmp_path):
    """Test compress_with_feature_flags with multiple paths."""
    # Prepare multiple source paths
    source_paths = [str(test_files["file1"]), str(test_files["file3"])]
    output_zip = tmp_path / "multi_paths.zip"

    # Test with parallel compression disabled
    with patch("src.feature_flags.feature_flags.is_enabled") as mock_is_enabled:
        # Return False for PARALLEL_COMPRESSION
        def side_effect(flag):
            return flag != FeatureFlag.PARALLEL_COMPRESSION

        mock_is_enabled.side_effect = side_effect

        # Call the function
        core.compress_with_feature_flags(source_paths, str(output_zip))

        # Verify the output
        assert output_zip.exists()
        assert zipfile.is_zipfile(output_zip)

        # Check that both files are in the zip
        with zipfile.ZipFile(output_zip, "r") as zf:
            file_names = set(zf.namelist())
            assert len(file_names) >= 2  # Should contain at least the two source files


def test_compress_items_parallel(test_files, tmp_path):
    """Test parallel compression of multiple items."""
    # Prepare source paths
    source_paths = [str(test_files["file1"]), str(test_files["file3"])]
    output_zip = tmp_path / "parallel.zip"

    # Create a mock progress callback
    progress_calls = []

    def mock_progress(current, total):
        progress_calls.append((current, total))

    # Create a mock cancel event
    cancel_event = threading.Event()

    # Call the function
    core.compress_items_parallel(
        source_paths,
        str(output_zip),
        progress_callback=mock_progress,
        cancel_event=cancel_event,
        compression_level=6,
        max_workers=2,
    )

    # Verify the output
    assert output_zip.exists()
    assert zipfile.is_zipfile(output_zip)

    # Check progress was reported
    assert len(progress_calls) > 0

    # Check the files are in the zip
    with zipfile.ZipFile(output_zip, "r") as zf:
        file_names = set(zf.namelist())
        assert os.path.basename(test_files["file1"]) in file_names
        assert os.path.basename(test_files["file3"]) in file_names


def test_cleanup_output_file(tmp_path):
    """Test the _cleanup_output_file function."""
    # Create a test file
    test_file = tmp_path / "test_cleanup.txt"
    test_file.write_text("Test cleanup")

    # Call the function
    core._cleanup_output_file(test_file)

    # Verify file was deleted
    assert not test_file.exists()


def test_cancel_compression(test_files, tmp_path):
    """Test canceling a compression operation."""
    source_dir = test_files["base_dir"]
    output_zip = tmp_path / "cancel_test.zip"

    # Create a cancel event and set it
    cancel_event = threading.Event()
    cancel_event.set()

    # Attempt to compress with cancel event set
    with pytest.raises(InterruptedError):
        core.compress_item(str(source_dir), str(output_zip), cancel_event=cancel_event)

    # Verify no output file was created
    assert not output_zip.exists()


def test_tempdir_import():
    """Test that tempfile is properly imported and working."""
    # This is a simple test to verify tempfile is available
    temp_dir = tempfile.mkdtemp()
    try:
        assert os.path.exists(temp_dir)
        assert os.path.isdir(temp_dir)
    finally:
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)


def test_import_dependencies():
    """Test that all required dependencies are importable."""
    # This tests that all imports in core.py are available
    import zipfile
    import py7zr
    import psutil
    import concurrent.futures

    # Try accessing key attributes/methods to verify modules work
    assert hasattr(zipfile, "ZipFile")
    assert hasattr(py7zr, "SevenZipFile")
    assert hasattr(psutil, "Process")
    assert hasattr(concurrent.futures, "ThreadPoolExecutor")
