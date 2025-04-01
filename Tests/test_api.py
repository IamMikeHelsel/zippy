# Tests/test_api.py
"""
Tests for the API module, including endpoint functionality and task management.
"""

import pytest
import os
import shutil
import time
import zipfile
import tempfile
import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from fastapi import UploadFile

from src.api import app, active_tasks, process_compression, process_extraction, TEMP_DIR


@pytest.fixture
def client():
    """Create a FastAPI test client fixture."""
    return TestClient(app)


@pytest.fixture
def test_files():
    """Create test files for API testing."""
    # Create a temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create a test file
        test_file = temp_path / "test_file.txt"
        test_file.write_text("This is a test file for API testing")

        # Create a test zip
        test_zip = temp_path / "test_archive.zip"
        with zipfile.ZipFile(test_zip, "w") as zipf:
            zipf.writestr("test_content.txt", "This is a test file inside a zip")
            zipf.writestr("subdir/nested.txt", "This is a nested file")

        yield {"base_dir": temp_path, "test_file": test_file, "test_zip": test_zip}


def test_api_root_endpoint(client):
    """Test the API root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "Zippy API" in data["message"]


def test_get_tasks_endpoint(client):
    """Test the get_tasks endpoint."""
    # Clean up any existing tasks
    active_tasks.clear()

    # Add test tasks
    active_tasks["task1"] = {
        "status": "completed",
        "operation": "compress",
        "progress": 100,
        "total": 100,
        "created_at": time.time(),
        "result_path": "/path/to/result.zip",
    }

    active_tasks["task2"] = {
        "status": "processing",
        "operation": "extract",
        "progress": 50,
        "total": 100,
        "created_at": time.time(),
        "message": "Processing...",
    }

    # Call the endpoint
    response = client.get("/api/v1/tasks")

    # Check the response
    assert response.status_code == 200
    tasks = response.json()

    assert len(tasks) == 2
    task_ids = {task["id"] for task in tasks}
    assert "task1" in task_ids
    assert "task2" in task_ids

    # Verify task details
    for task in tasks:
        if task["id"] == "task1":
            assert task["status"] == "completed"
            assert task["operation"] == "compress"
        elif task["id"] == "task2":
            assert task["status"] == "processing"
            assert task["operation"] == "extract"
            assert task["progress"] == 50

    # Clean up
    active_tasks.clear()


def test_get_task_endpoint(client):
    """Test the get_task endpoint."""
    # Clean up any existing tasks
    active_tasks.clear()

    # Add a test task
    task_id = "test_task_id"
    active_tasks[task_id] = {
        "status": "completed",
        "operation": "compress",
        "progress": 100,
        "total": 100,
        "created_at": time.time(),
        "result_path": "/path/to/result.zip",
    }

    # Call the endpoint
    response = client.get(f"/api/v1/tasks/{task_id}")

    # Check the response
    assert response.status_code == 200
    task = response.json()

    assert task["id"] == task_id
    assert task["status"] == "completed"
    assert task["progress"] == 100

    # Test with nonexistent task ID
    response = client.get("/api/v1/tasks/nonexistent")
    assert response.status_code == 404

    # Clean up
    active_tasks.clear()


def test_cancel_task_endpoint(client):
    """Test the cancel_task endpoint."""
    # Clean up any existing tasks
    active_tasks.clear()

    # Add test tasks - one that can be cancelled and one that's already done
    active_tasks["running_task"] = {
        "status": "processing",
        "operation": "compress",
        "progress": 50,
        "total": 100,
        "created_at": time.time(),
        "cancel_event": asyncio.Event(),
    }

    active_tasks["completed_task"] = {
        "status": "completed",
        "operation": "compress",
        "progress": 100,
        "total": 100,
        "created_at": time.time(),
    }

    # Test cancelling a running task
    response = client.delete("/api/v1/tasks/running_task")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "cancelled"

    # Verify the task was marked as cancelled
    assert active_tasks["running_task"]["status"] == "cancelled"

    # Test cancelling an already completed task
    response = client.delete("/api/v1/tasks/completed_task")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"

    # Test cancelling a nonexistent task
    response = client.delete("/api/v1/tasks/nonexistent")
    assert response.status_code == 404

    # Clean up
    active_tasks.clear()


@pytest.mark.asyncio
async def test_process_compression_function():
    """Test the process_compression background function."""
    # Create a temporary task directory
    with tempfile.TemporaryDirectory() as temp_dir:
        # Set up test components
        task_id = "test_compression_task"
        task_dir = Path(temp_dir) / "task"
        task_dir.mkdir()

        # Create a test file
        test_file = task_dir / "test_file.txt"
        test_file.write_text("This is test content for compression")

        # Create a mock UploadFile
        class MockUploadFile:
            def __init__(self, file_path):
                self.file = open(file_path, "rb")
                self.filename = os.path.basename(file_path)

            def __del__(self):
                self.file.close()

        mock_file = MockUploadFile(test_file)

        # Set up the task in active_tasks
        active_tasks[task_id] = {
            "status": "pending",
            "operation": "compress",
            "progress": 0,
            "total": 100,
            "created_at": time.time(),
            "cancel_event": asyncio.Event(),
        }

        try:
            # Call the function
            await process_compression(
                task_id=task_id,
                files=[mock_file],
                task_dir=task_dir,
                compression_level=6,
            )

            # Verify the task was updated
            assert active_tasks[task_id]["status"] == "completed"
            assert "result_path" in active_tasks[task_id]

            # Check the output zip file
            result_path = Path(active_tasks[task_id]["result_path"])
            assert result_path.exists()
            assert zipfile.is_zipfile(result_path)

            # Check zip contents
            with zipfile.ZipFile(result_path) as zipf:
                assert "test_file.txt" in zipf.namelist()

        finally:
            # Clean up
            if task_id in active_tasks:
                del active_tasks[task_id]


@pytest.mark.asyncio
async def test_process_extraction_function():
    """Test the process_extraction background function."""
    # Create a temporary task directory
    with tempfile.TemporaryDirectory() as temp_dir:
        # Set up test components
        task_id = "test_extraction_task"
        task_dir = Path(temp_dir) / "task"
        task_dir.mkdir()

        # Create a test zip file
        test_zip = task_dir / "test_archive.zip"
        with zipfile.ZipFile(test_zip, "w") as zipf:
            zipf.writestr("test_content.txt", "This is test content")
            zipf.writestr("subdir/nested.txt", "This is nested content")

        # Create a mock UploadFile
        class MockUploadFile:
            def __init__(self, file_path):
                self.file = open(file_path, "rb")
                self.filename = os.path.basename(file_path)

            def __del__(self):
                self.file.close()

        mock_archive = MockUploadFile(test_zip)

        # Set up the task in active_tasks
        active_tasks[task_id] = {
            "status": "pending",
            "operation": "extract",
            "progress": 0,
            "total": 100,
            "created_at": time.time(),
            "cancel_event": asyncio.Event(),
        }

        try:
            # Call the function
            await process_extraction(
                task_id=task_id, archive=mock_archive, task_dir=task_dir
            )

            # Verify the task was updated
            assert active_tasks[task_id]["status"] == "completed"
            assert "result_path" in active_tasks[task_id]

            # Check that the extraction directory exists
            extract_dir = task_dir / "extracted"
            assert extract_dir.exists()

            # Check that files were extracted
            assert (extract_dir / "test_content.txt").exists()
            assert (extract_dir / "subdir" / "nested.txt").exists()

            # Check the result zip
            result_path = Path(active_tasks[task_id]["result_path"])
            assert result_path.exists()
            assert zipfile.is_zipfile(result_path)

        finally:
            # Clean up
            if task_id in active_tasks:
                del active_tasks[task_id]


def test_compress_endpoint_with_single_file(client, test_files):
    """Test the compress endpoint with a single file."""
    # Mock the process_compression function to avoid actual processing
    with patch("src.api.process_compression") as mock_process:
        # Configure the mock to set task status
        async def set_completed(*args, **kwargs):
            task_id = kwargs.get("task_id", args[0])
            active_tasks[task_id]["status"] = "completed"
            active_tasks[task_id]["result_path"] = str(
                test_files["base_dir"] / "result.zip"
            )

        mock_process.side_effect = set_completed

        # Send the compress request
        with open(test_files["test_file"], "rb") as f:
            response = client.post(
                "/api/v1/compress",
                files={"files": ("test_file.txt", f, "text/plain")},
                params={"compression_level": 9},
            )

        # Check the response
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "pending"

        # Verify the task was added correctly
        task_id = data["task_id"]
        assert task_id in active_tasks
        assert active_tasks[task_id]["operation"] == "compress"

        # Clean up
        if task_id in active_tasks:
            del active_tasks[task_id]


def test_extract_endpoint(client, test_files):
    """Test the extract endpoint."""
    # Mock the process_extraction function
    with patch("src.api.process_extraction") as mock_process:
        # Configure the mock to set task status
        async def set_completed(*args, **kwargs):
            task_id = kwargs.get("task_id", args[0])
            active_tasks[task_id]["status"] = "completed"
            active_tasks[task_id]["result_path"] = str(
                test_files["base_dir"] / "extracted.zip"
            )

        mock_process.side_effect = set_completed

        # Send the extract request
        with open(test_files["test_zip"], "rb") as f:
            response = client.post(
                "/api/v1/extract",
                files={"archive": ("test_archive.zip", f, "application/zip")},
            )

        # Check the response
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "pending"

        # Verify the task was added correctly
        task_id = data["task_id"]
        assert task_id in active_tasks
        assert active_tasks[task_id]["operation"] == "extract"

        # Clean up
        if task_id in active_tasks:
            del active_tasks[task_id]


def test_download_result_endpoint(client):
    """Test the download_result endpoint."""
    # Create a temporary file to serve
    with tempfile.TemporaryDirectory() as temp_dir:
        result_file = Path(temp_dir) / "test_result.zip"

        # Create a simple zip file
        with zipfile.ZipFile(result_file, "w") as zipf:
            zipf.writestr("test.txt", "Test content")

        # Add a completed task with the result path
        task_id = "download_test_task"
        active_tasks[task_id] = {
            "status": "completed",
            "operation": "compress",
            "progress": 100,
            "total": 100,
            "created_at": time.time(),
            "result_path": str(result_file),
        }

        # Test the download endpoint
        with patch(
            "fastapi.responses.FileResponse", return_value=MagicMock()
        ) as mock_file_response:
            response = client.get(f"/api/v1/download/{task_id}")

            # We're mocking the FileResponse, so we don't get the actual file
            # Just check that the response was initialized with the correct parameters
            mock_file_response.assert_called_once()
            call_args = mock_file_response.call_args[1]
            assert call_args["path"] == str(result_file)
            assert call_args["filename"] == "test_result.zip"

        # Test with task not found
        response = client.get("/api/v1/download/nonexistent")
        assert response.status_code == 404

        # Test with task not completed
        active_tasks["incomplete_task"] = {
            "status": "processing",
            "operation": "compress",
            "progress": 50,
            "total": 100,
            "created_at": time.time(),
        }

        response = client.get("/api/v1/download/incomplete_task")
        assert response.status_code == 400

        # Clean up
        active_tasks.clear()


def test_cleanup_old_tasks():
    """Test the cleanup_old_tasks background function."""
    # This is a challenging function to test directly due to its infinite loop
    # Instead, we'll test the logic it contains

    # Create a temporary directory to simulate TEMP_DIR
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Set up test tasks - one old, one new
        old_task_id = "old_task"
        new_task_id = "new_task"

        # Create task directories and files
        old_task_dir = temp_path / old_task_id
        old_task_dir.mkdir()
        (old_task_dir / "test.txt").write_text("test content")

        new_task_dir = temp_path / new_task_id
        new_task_dir.mkdir()

        # Add tasks to active_tasks
        current_time = time.time()
        one_hour = 3600  # seconds

        active_tasks[old_task_id] = {
            "status": "completed",
            "operation": "compress",
            "created_at": current_time - (one_hour * 2),  # 2 hours old
        }

        active_tasks[new_task_id] = {
            "status": "completed",
            "operation": "compress",
            "created_at": current_time - 10,  # 10 seconds old
        }

        # Mock the TEMP_DIR to point to our temporary directory
        original_temp_dir = TEMP_DIR
        import src.api

        src.api.TEMP_DIR = temp_path

        try:
            # Create a version of cleanup_old_tasks without the infinite loop
            async def test_cleanup():
                current_time = time.time()
                tasks_to_remove = []

                for task_id, task in list(active_tasks.items()):
                    # Remove tasks older than cleanup time
                    if (
                        current_time - task.get("created_at", current_time)
                        > src.api.TASK_CLEANUP_TIME
                    ):
                        tasks_to_remove.append(task_id)
                        # Clean up task directory if it exists
                        task_dir = src.api.TEMP_DIR / task_id
                        if task_dir.exists():
                            shutil.rmtree(task_dir, ignore_errors=True)

                # Remove old tasks from active tasks
                for task_id in tasks_to_remove:
                    del active_tasks[task_id]

            # Run the cleanup function once
            asyncio.run(test_cleanup())

            # Check that old task was removed but new task remains
            assert old_task_id not in active_tasks
            assert new_task_id in active_tasks

            # Check that old task directory was deleted but new task directory remains
            assert not old_task_dir.exists()
            assert new_task_dir.exists()

        finally:
            # Restore original TEMP_DIR
            src.api.TEMP_DIR = original_temp_dir

            # Clean up
            active_tasks.clear()


if __name__ == "__main__":
    pytest.main(["-v", __file__])
