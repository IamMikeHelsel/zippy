# tests/test_core.py
import pytest
import zipfile
from pathlib import Path
import os
import shutil

# Make sure core can be imported: Requires 'src' in pythonpath (configured in pyproject.toml)
from src import core

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
        "extract_dir": tmp_path / "extracted"
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
    with zipfile.ZipFile(output_zip, 'r') as zipf:
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
    with zipfile.ZipFile(output_zip, 'r') as zipf:
        # Check relative paths in zip - normalize path separators for cross-platform compatibility
        zip_names = set(name.replace('/', os.sep) for name in zipf.namelist())
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
    extracted_base = extract_dir # Files are extracted directly into the target
    assert (extracted_base / "file1.txt").read_text() == test_files["file1"].read_text()
    assert (extracted_base / "toplevel.dat").read_text() == test_files["file3"].read_text()
    assert (extracted_base / "subdir" / "file2.log").read_text() == test_files["file2"].read_text()
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
    assert not output_zip.exists() # Ensure no partial zip is left

def test_uncompress_nonexistent_archive(test_files):
    """Test uncompressing a zip file that doesn't exist."""
    zip_path = test_files["output_dir"] / "nonexistent.zip"
    extract_dir = test_files["extract_dir"]
    with pytest.raises(FileNotFoundError):
        core.uncompress_archive(str(zip_path), str(extract_dir))

def test_uncompress_invalid_file(test_files):
    """Test uncompressing a file that is not a zip archive."""
    invalid_file = test_files["single_file"] # Use a regular text file
    extract_dir = test_files["extract_dir"]
    with pytest.raises(zipfile.BadZipFile):
        core.uncompress_archive(str(invalid_file), str(extract_dir))

# Test progress callback (basic check)
def test_progress_callback(test_files, tmp_path):
    """Test if the progress callback is called."""
    source_dir = test_files["base_dir"]
    output_zip = test_files["output_dir"] / "progress_test.zip"
    extract_dir = test_files["extract_dir"]
    zip_path = output_zip # Use the same path for consistency

    compress_calls = []
    uncompress_calls = []

    def mock_compress_progress(current, total):
        compress_calls.append((current, total))

    def mock_uncompress_progress(current, total):
        uncompress_calls.append((current, total))

    # Test compression progress
    core.compress_item(str(source_dir), str(output_zip), progress_callback=mock_compress_progress)
    assert len(compress_calls) > 0 # Should have been called
    assert compress_calls[-1][0] == compress_calls[-1][1] # Last call should show completion

    # Test uncompression progress
    core.uncompress_archive(str(zip_path), str(extract_dir), progress_callback=mock_uncompress_progress)
    assert len(uncompress_calls) > 0 # Should have been called
    # Basic extractall only gives start/end for this implementation
    assert len(uncompress_calls) == 2
    assert uncompress_calls[0] == (0, uncompress_calls[1][1]) # Start
    assert uncompress_calls[1][0] == uncompress_calls[1][1] # End