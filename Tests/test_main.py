# tests/test_main.py
import pytest
import os
import shutil
import zipfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

# Import the main module from src
from src import app
from src import utils
from src import core

@pytest.fixture
def test_files(tmp_path):
    """Create test files and directories for testing."""
    base_dir = tmp_path / "test_source"
    base_dir.mkdir()
    
    # Create test files
    file1 = base_dir / "file1.txt"
    file1.write_text("This is file 1 content")
    
    file2 = base_dir / "file2.log"
    file2.write_text("This is file 2 content")
    
    # Create subdirectory with files
    subdir = base_dir / "subdir"
    subdir.mkdir()
    
    file3 = subdir / "file3.dat"
    file3.write_text("This is file 3 in subdirectory")
    
    # Create an empty directory
    empty_dir = base_dir / "empty_dir"
    empty_dir.mkdir()
    
    # Create a zip file for testing extraction
    zip_path = tmp_path / "test.zip"
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        zipf.writestr("test_file1.txt", "Test content 1")
        zipf.writestr("test_file2.log", "Test content 2")
        zipf.writestr("test_subdir/test_file3.dat", "Test content 3")
    
    return {
        "base_dir": base_dir,
        "file1": file1,
        "file2": file2,
        "subdir": subdir,
        "file3": file3,
        "empty_dir": empty_dir,
        "zip_path": zip_path,
        "tmp_path": tmp_path,
        "output_dir": tmp_path / "output",
        "extract_dir": tmp_path / "extract"
    }

@pytest.fixture
def app_instance():
    """Create an instance of the ZipApp for testing."""
    with patch('customtkinter.CTk'):
        app = app.ZipApp()
        # Mock the UI elements to avoid actual UI operations
        app.update_status = MagicMock()
        app.update_progress = MagicMock()
        app.after = MagicMock()
        yield app

# Test utility functions
def test_merge_zip_files(test_files, app_instance):
    """Test the _merge_zip_files function."""
    # Create multiple test zip files
    zip1 = test_files["tmp_path"] / "test1.zip"
    zip2 = test_files["tmp_path"] / "test2.zip"
    merged_zip = test_files["tmp_path"] / "merged.zip"
    
    # Create zip files with different content
    with zipfile.ZipFile(zip1, 'w') as zipf:
        zipf.writestr("file1.txt", "Content 1")
    
    with zipfile.ZipFile(zip2, 'w') as zipf:
        zipf.writestr("file2.txt", "Content 2")
    
    # Merge the zip files
    app_instance.cancel_event = threading.Event()
    app_instance._merge_zip_files([zip1, zip2], merged_zip)
    
    # Verify the merged zip file contains all files
    assert merged_zip.exists()
    with zipfile.ZipFile(merged_zip, 'r') as zipf:
        files = zipf.namelist()
        assert "file1.txt" in files
        assert "file2.txt" in files
        assert zipf.read("file1.txt").decode('utf-8') == "Content 1"
        assert zipf.read("file2.txt").decode('utf-8') == "Content 2"

def test_update_output_label(app_instance):
    """Test the update_output_label function."""
    app_instance.output_label = MagicMock()
    app_instance.target_zip_path = MagicMock()
    
    # Test with a valid path
    test_path = "/path/to/source/file.txt"
    
    with patch('src.utils.get_default_zip_path') as mock_get_default_path:
        # Setup the mock to return a Path object
        mock_path = MagicMock()
        mock_path.name = "file.zip"
        mock_get_default_path.return_value = mock_path
        
        # Call the function
        app_instance.update_output_label(test_path)
        
        # Check the function behavior
        mock_get_default_path.assert_called_once_with(test_path)
        app_instance.target_zip_path.set.assert_called_once_with(str(mock_path))
        app_instance.output_label.set.assert_called_once_with(f"Desktop/{mock_path.name}")
    
    # Test with no path (reset)
    app_instance.output_label.set.reset_mock()
    app_instance.target_zip_path.set.reset_mock()
    
    app_instance.update_output_label()
    app_instance.target_zip_path.set.assert_called_once_with("")
    app_instance.output_label.set.assert_called_once_with("")

def test_update_button_states(app_instance):
    """Test the update_button_states function."""
    # Mock button objects
    app_instance.compress_button = MagicMock()
    app_instance.uncompress_button = MagicMock()
    app_instance.cancel_compress_button = MagicMock()
    app_instance.cancel_uncompress_button = MagicMock()
    
    # Test with no paths set
    app_instance.source_path = MagicMock()
    app_instance.source_path.get.return_value = ""
    app_instance.source_zip_path = MagicMock()
    app_instance.source_zip_path.get.return_value = ""
    app_instance.extract_path = MagicMock()
    app_instance.extract_path.get.return_value = ""
    
    app_instance.update_button_states()
    
    # Compression and uncompression buttons should be disabled
    app_instance.compress_button.configure.assert_called_with(state="disabled")
    app_instance.uncompress_button.configure.assert_called_with(state="disabled")
    app_instance.cancel_compress_button.configure.assert_called_with(state="disabled")
    app_instance.cancel_uncompress_button.configure.assert_called_with(state="disabled")
    
    # Test with source path set
    app_instance.compress_button.configure.reset_mock()
    app_instance.source_path.get.return_value = "/path/to/source"
    
    app_instance.update_button_states()
    
    # Compression button should be enabled, but uncompression still disabled
    app_instance.compress_button.configure.assert_called_with(state="normal")
    
    # Test with operation running
    app_instance.compress_button.configure.reset_mock()
    app_instance.uncompress_button.configure.reset_mock()
    app_instance.cancel_compress_button.configure.reset_mock()
    app_instance.cancel_uncompress_button.configure.reset_mock()
    
    app_instance.update_button_states(operation_running=True)
    
    # Action buttons should be disabled, cancel buttons enabled
    app_instance.compress_button.configure.assert_called_with(state="disabled")
    app_instance.uncompress_button.configure.assert_called_with(state="disabled")
    app_instance.cancel_compress_button.configure.assert_called_with(state="normal")
    app_instance.cancel_uncompress_button.configure.assert_called_with(state="normal")

# Test compression and extraction functionality
def test_start_compression_default_path(app_instance, test_files, monkeypatch):
    """Test the start_compression function with default output path."""
    output_dir = test_files["output_dir"]
    source_file = test_files["file1"]
    
    # Mock necessary methods
    app_instance.source_path = MagicMock()
    app_instance.source_path.get.return_value = str(source_file)
    app_instance.output_label = MagicMock()
    app_instance.output_label.get.return_value = ""  # Use default path
    app_instance.target_zip_path = MagicMock()
    app_instance._run_task = MagicMock()
    
    # Patch the utils.get_default_zip_path to return a predictable path
    default_zip_path = output_dir / "file1.zip"
    monkeypatch.setattr(utils, "get_default_zip_path", lambda _: default_zip_path)
    
    # Create the output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Run the test
    app_instance.start_compression()
    
    # Check that the correct methods were called
    app_instance.source_path.get.assert_called_once()
    app_instance.target_zip_path.set.assert_called_once_with(str(default_zip_path))
    app_instance._run_task.assert_called_once()
    
    # Verify the first argument to _run_task is core.compress_item
    assert app_instance._run_task.call_args[0][0] == core.compress_item
    # Verify the second argument is the source path
    assert app_instance._run_task.call_args[0][1] == str(source_file)
    # Verify the third argument is the target path
    assert app_instance._run_task.call_args[0][2] == str(default_zip_path)

def test_start_compression_custom_path(app_instance, test_files):
    """Test the start_compression function with custom output path."""
    output_dir = test_files["output_dir"]
    source_file = test_files["file1"]
    custom_output = output_dir / "custom.zip"
    
    # Create the output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Mock necessary methods
    app_instance.source_path = MagicMock()
    app_instance.source_path.get.return_value = str(source_file)
    app_instance.output_label = MagicMock()
    app_instance.output_label.get.return_value = str(custom_output)
    app_instance.target_zip_path = MagicMock()
    app_instance._run_task = MagicMock()
    
    # Run the test
    app_instance.start_compression()
    
    # Check that the correct methods were called
    app_instance.source_path.get.assert_called_once()
    app_instance.target_zip_path.set.assert_called_once_with(str(custom_output))
    app_instance._run_task.assert_called_once()
    
    # Verify the arguments to _run_task
    assert app_instance._run_task.call_args[0][0] == core.compress_item
    assert app_instance._run_task.call_args[0][1] == str(source_file)
    assert app_instance._run_task.call_args[0][2] == str(custom_output)

def test_start_uncompression(app_instance, test_files):
    """Test the start_uncompression function."""
    zip_path = test_files["zip_path"]
    extract_dir = test_files["extract_dir"]
    
    # Mock necessary methods
    app_instance.source_zip_path = MagicMock()
    app_instance.source_zip_path.get.return_value = str(zip_path)
    app_instance.extract_path = MagicMock()
    app_instance.extract_path.get.return_value = str(extract_dir)
    app_instance._run_task = MagicMock()
    
    # Run the test
    app_instance.start_uncompression()
    
    # Check that the correct methods were called
    app_instance.source_zip_path.get.assert_called_once()
    app_instance.extract_path.get.assert_called_once()
    app_instance._run_task.assert_called_once()
    
    # Verify the arguments to _run_task
    assert app_instance._run_task.call_args[0][0] == core.uncompress_archive
    assert app_instance._run_task.call_args[0][1] == str(zip_path)
    assert app_instance._run_task.call_args[0][2] == str(extract_dir)

# Test UI update functions
def test_update_status(app_instance):
    """Test the update_status function."""
    # Mock status_label for testing
    app_instance.status_label = MagicMock()
    app_instance.progress_bar = MagicMock()
    
    # Test with message only
    app_instance.update_status("Test message")
    
    # Verify after() was called to schedule update
    app_instance.after.assert_called_once()
    
    # Get the function that would be executed
    scheduled_func = app_instance.after.call_args[0][1]
    
    # Call the scheduled function and verify it updates the label
    scheduled_func()
    app_instance.status_label.configure.assert_called_once_with(text="Test message")
    app_instance.progress_bar.set.assert_not_called()
    
    # Reset mocks
    app_instance.after.reset_mock()
    app_instance.status_label.configure.reset_mock()
    app_instance.progress_bar.set.reset_mock()
    
    # Test with clear_progress=True
    app_instance.update_status("Another message", clear_progress=True)
    
    # Get and call the scheduled function
    scheduled_func = app_instance.after.call_args[0][1]
    scheduled_func()
    
    app_instance.status_label.configure.assert_called_once_with(text="Another message")
    app_instance.progress_bar.set.assert_called_once_with(0)

def test_update_progress(app_instance):
    """Test the update_progress function."""
    # Mock necessary UI components
    app_instance.progress_bar = MagicMock()
    app_instance.status_label = MagicMock()
    
    # Test with normal progress values
    app_instance.update_progress(50, 100)
    
    # Verify after() was called
    app_instance.after.assert_called_once()
    
    # Get and call the scheduled function
    scheduled_func = app_instance.after.call_args[0][1]
    scheduled_func()
    
    # Verify progress was set correctly (50/100 = 0.5)
    app_instance.progress_bar.set.assert_called_once_with(0.5)
    app_instance.status_label.configure.assert_called_once()
    
    # Reset mocks
    app_instance.after.reset_mock()
    app_instance.progress_bar.set.reset_mock()
    app_instance.status_label.configure.reset_mock()
    
    # Test with MB values that should trigger MB display
    app_instance.update_progress(2*1024*1024, 10*1024*1024)  # 2MB of 10MB
    
    # Get and call the scheduled function
    scheduled_func = app_instance.after.call_args[0][1]
    scheduled_func()
    
    # Verify progress was set correctly
    app_instance.progress_bar.set.assert_called_once_with(0.2)  # 2/10 = 0.2
    
    # Status should show MB information
    status_text = app_instance.status_label.configure.call_args[1]['text']
    assert "MB" in status_text
    assert "20%" in status_text
    
    # Test with zero total (edge case)
    app_instance.after.reset_mock()
    app_instance.progress_bar.set.reset_mock()
    app_instance.status_label.configure.reset_mock()
    
    app_instance.update_progress(10, 0)
    scheduled_func = app_instance.after.call_args[0][1]
    scheduled_func()
    
    app_instance.progress_bar.set.assert_called_once_with(0)
    app_instance.status_label.configure.assert_called_once_with(text="Processing...")

# Test resource monitoring
def test_update_resource_display(app_instance, monkeypatch):
    """Test the update_resource_display function."""
    # Mock psutil functions
    memory_mock = MagicMock()
    memory_mock.percent = 50.5
    
    cpu_mock = MagicMock()
    cpu_mock.cpu_percent.return_value = 25.3
    
    monkeypatch.setattr(app.psutil, "virtual_memory", lambda: memory_mock)
    monkeypatch.setattr(app.psutil, "Process", lambda: cpu_mock)
    
    # Mock necessary variables
    app_instance.resource_label = MagicMock()
    app_instance.resource_monitor_label = MagicMock()
    app_instance.cancel_event = threading.Event()
    
    # Call the function
    app_instance.update_resource_display()
    
    # Verify the resource label was updated
    app_instance.resource_label.set.assert_called_once()
    label_text = app_instance.resource_label.set.call_args[0][0]
    assert "Memory: 50.5%" in label_text
    assert "CPU: 25.3%" in label_text
    
    # Verify after() was called to schedule next update
    app_instance.after.assert_called_once()
    
    # Test with high memory usage (>85%)
    app_instance.after.reset_mock()
    app_instance.resource_label.set.reset_mock()
    app_instance.resource_monitor_label.configure.reset_mock()
    
    memory_mock.percent = 90.0
    app_instance.update_resource_display()
    
    # Verify label color was changed to red
    app_instance.resource_monitor_label.configure.assert_called_once_with(text_color="#FF5252")

# Test the parallel processing functions
def test_run_parallel_compression(app_instance, test_files):
    """Test the _run_parallel_compression function."""
    # Setup test files
    file1 = test_files["file1"]
    file2 = test_files["file2"]
    output_zip = test_files["output_dir"] / "parallel_test.zip"
    
    # Create output directory
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    
    # Prepare semicolon-separated path string
    source_paths = f"{file1};{file2}"
    
    # Mock necessary methods and properties
    app_instance.cancel_event = threading.Event()
    app_instance.update_status = MagicMock()
    app_instance.update_progress = MagicMock()
    
    # Run the function with patched core.compress_item
    with patch('src.core.compress_item') as mock_compress:
        app_instance._run_parallel_compression(source_paths, str(output_zip))
        
        # Verify compress_item was called at least twice (once for each file)
        assert mock_compress.call_count >= 2

# Integration test for the _run_task function
def test_run_task(app_instance, test_files):
    """Test the _run_task function with a simple task."""
    # Create a mock task function
    mock_task = MagicMock()
    task_args = ("arg1", "arg2")
    
    # Mock UI update methods
    app_instance.update_button_states = MagicMock()
    app_instance.progress_bar = MagicMock()
    app_instance.update_resource_display = MagicMock()
    app_instance.cancel_resource_monitoring = MagicMock()
    app_instance.cancel_event = threading.Event()
    
    # Call _run_task
    app_instance._run_task(mock_task, *task_args)
    
    # Allow the thread to complete
    time.sleep(0.1)
    
    # Verify the task was called with the correct arguments
    # Note: progress_callback and cancel_event are added automatically
    assert mock_task.call_args[0][:2] == task_args
    assert 'progress_callback' in mock_task.call_args[1]
    assert 'cancel_event' in mock_task.call_args[1]

# Test cancel operation
def test_cancel_operation(app_instance):
    """Test the cancel_operation function."""
    # Mock necessary methods and objects
    app_instance.update_status = MagicMock()
    app_instance.cancel_event = threading.Event()
    app_instance.current_task_thread = MagicMock()
    app_instance.current_task_thread.is_alive.return_value = True
    
    # Call cancel_operation
    app_instance.cancel_operation()
    
    # Verify cancel_event was set
    assert app_instance.cancel_event.is_set()
    
    # Verify update_status was called with cancellation message
    app_instance.update_status.assert_called_once()
    assert "Cancelling" in app_instance.update_status.call_args[0][0]
    
    # Test when no operation is running
    app_instance.update_status.reset_mock()
    app_instance.cancel_event.clear()
    app_instance.current_task_thread.is_alive.return_value = False
    
    app_instance.cancel_operation()
    
    # Verify message indicates no operation is running
    app_instance.update_status.assert_called_once()
    assert "No operation" in app_instance.update_status.call_args[0][0]

# Test application initialization
def test_app_initialization():
    """Test that the ZipApp initializes properly."""
    with patch('customtkinter.CTk'), \
         patch('customtkinter.CTkFrame'), \
         patch('customtkinter.CTkLabel'), \
         patch('customtkinter.CTkButton'), \
         patch('customtkinter.CTkEntry'), \
         patch('customtkinter.CTkProgressBar'), \
         patch('customtkinter.StringVar'):
        
        app = app.ZipApp()
        
        # Verify basic properties were initialized
        assert hasattr(app, 'source_path')
        assert hasattr(app, 'target_zip_path')
        assert hasattr(app, 'source_zip_path')
        assert hasattr(app, 'extract_path')
        assert hasattr(app, 'cancel_event')
        assert isinstance(app.cancel_event, threading.Event)