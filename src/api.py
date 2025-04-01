#!/usr/bin/env python
# src/api.py
"""
API interface for the zippy application.
Provides HTTP API access to the core compression and decompression functionality.

This module serves as the bridge between the core functionality and any UI,
including web interfaces or desktop GUIs that might use it as a backend.
"""

import os
import logging
import tempfile
import shutil
from pathlib import Path
import threading
import time
import uuid
from typing import List, Dict, Any, Optional, Union
import asyncio

import uvicorn
from fastapi import FastAPI, File, UploadFile, BackgroundTasks, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from src import core
from src import utils

# Configure module logger
logger = logging.getLogger(__name__)

# Create FastAPI application
app = FastAPI(
    title="Zippy API",
    description="API for compressing and extracting files",
    version="0.1.0"
)

# Create a temp directory for file operations
TEMP_DIR = Path(tempfile.gettempdir()) / "zippy_api"
TEMP_DIR.mkdir(exist_ok=True)

# Store active tasks with their status
active_tasks: Dict[str, Dict[str, Any]] = {}

# Task cleanup time (in seconds, default 1 hour)
TASK_CLEANUP_TIME = 3600

class Task(BaseModel):
    """Model for task information and status"""
    id: str
    status: str  # "pending", "processing", "completed", "failed", "cancelled"
    operation: str  # "compress" or "extract"
    progress: int = 0
    total: int = 100
    message: Optional[str] = None
    result_path: Optional[str] = None
    created_at: float

class ProgressTracker:
    """Track progress for background operations"""
    def __init__(self, task_id: str):
        self.task_id = task_id
        
    def update(self, current: int, total: int) -> None:
        """Update progress status for a task"""
        if self.task_id in active_tasks:
            active_tasks[self.task_id]["progress"] = current
            active_tasks[self.task_id]["total"] = max(1, total)  # Avoid division by zero

async def cleanup_old_tasks():
    """Remove old tasks and their files periodically"""
    while True:
        try:
            current_time = time.time()
            tasks_to_remove = []
            
            for task_id, task in active_tasks.items():
                # Remove tasks older than cleanup time
                if current_time - task.get("created_at", current_time) > TASK_CLEANUP_TIME:
                    tasks_to_remove.append(task_id)
                    # Clean up task directory if it exists
                    task_dir = TEMP_DIR / task_id
                    if task_dir.exists():
                        shutil.rmtree(task_dir, ignore_errors=True)
            
            # Remove old tasks from active tasks
            for task_id in tasks_to_remove:
                del active_tasks[task_id]
                
            await asyncio.sleep(300)  # Check every 5 minutes
        except Exception as e:
            logger.error(f"Error in cleanup task: {e}")
            await asyncio.sleep(600)  # On error, wait 10 minutes before retry

@app.on_event("startup")
async def startup_event():
    """Start background tasks on application startup"""
    # Start cleanup task
    asyncio.create_task(cleanup_old_tasks())

@app.get("/")
async def root():
    """API health check endpoint"""
    return {"status": "ok", "message": "Zippy API is running"}

@app.get("/api/v1/tasks", response_model=List[Task])
async def get_tasks():
    """Get list of active tasks"""
    return [
        Task(
            id=task_id,
            status=task["status"],
            operation=task["operation"],
            progress=task["progress"],
            total=task["total"],
            message=task.get("message"),
            result_path=task.get("result_path"),
            created_at=task["created_at"]
        )
        for task_id, task in active_tasks.items()
    ]

@app.get("/api/v1/tasks/{task_id}", response_model=Task)
async def get_task(task_id: str):
    """Get status of a specific task"""
    if task_id not in active_tasks:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
    task = active_tasks[task_id]
    return Task(
        id=task_id,
        status=task["status"],
        operation=task["operation"],
        progress=task["progress"],
        total=task["total"],
        message=task.get("message"),
        result_path=task.get("result_path"),
        created_at=task["created_at"]
    )

@app.delete("/api/v1/tasks/{task_id}")
async def cancel_task(task_id: str):
    """Cancel a running task"""
    if task_id not in active_tasks:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
    task = active_tasks[task_id]
    
    # Only cancel if the task is still running
    if task["status"] in ["pending", "processing"]:
        if "cancel_event" in task and isinstance(task["cancel_event"], threading.Event):
            task["cancel_event"].set()
        
        task["status"] = "cancelled"
        task["message"] = "Task cancelled by user"
        
        return {"status": "cancelled", "message": f"Task {task_id} cancelled"}
    else:
        return {
            "status": task["status"], 
            "message": f"Task {task_id} is already in {task['status']} state and cannot be cancelled"
        }

@app.post("/api/v1/compress")
async def compress_files(
    background_tasks: BackgroundTasks, 
    files: List[UploadFile] = File(...),
    compression_level: int = Query(6, ge=0, le=9)
):
    """
    Compress uploaded files into a ZIP archive
    
    - **files**: One or more files to compress
    - **compression_level**: Compression level (0-9, where 9 is maximum compression)
    
    Returns a task ID that can be used to check status and download the result
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    
    # Create a unique task ID
    task_id = str(uuid.uuid4())
    
    # Create a directory for this task
    task_dir = TEMP_DIR / task_id
    task_dir.mkdir(exist_ok=True)
    
    # Initialize task status
    active_tasks[task_id] = {
        "status": "pending",
        "operation": "compress",
        "progress": 0,
        "total": 100,
        "created_at": time.time(),
        "cancel_event": threading.Event()
    }
    
    # Schedule the compression task
    background_tasks.add_task(
        process_compression,
        task_id=task_id,
        files=files,
        task_dir=task_dir,
        compression_level=compression_level
    )
    
    return {"task_id": task_id, "status": "pending"}

@app.post("/api/v1/extract")
async def extract_archive(
    background_tasks: BackgroundTasks, 
    archive: UploadFile = File(...)
):
    """
    Extract a ZIP archive
    
    - **archive**: The ZIP archive file to extract
    
    Returns a task ID that can be used to check status and download the result
    """
    if not archive.filename or not archive.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Uploaded file must be a ZIP archive")
    
    # Create a unique task ID
    task_id = str(uuid.uuid4())
    
    # Create a directory for this task
    task_dir = TEMP_DIR / task_id
    task_dir.mkdir(exist_ok=True)
    
    # Initialize task status
    active_tasks[task_id] = {
        "status": "pending",
        "operation": "extract",
        "progress": 0,
        "total": 100,
        "created_at": time.time(),
        "cancel_event": threading.Event()
    }
    
    # Schedule the extraction task
    background_tasks.add_task(
        process_extraction,
        task_id=task_id,
        archive=archive,
        task_dir=task_dir
    )
    
    return {"task_id": task_id, "status": "pending"}

@app.get("/api/v1/download/{task_id}")
async def download_result(task_id: str):
    """
    Download the result of a completed task
    
    - **task_id**: The ID of the task to download the result for
    """
    if task_id not in active_tasks:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
    task = active_tasks[task_id]
    
    if task["status"] != "completed":
        raise HTTPException(status_code=400, detail=f"Task {task_id} is not completed")
    
    if "result_path" not in task or not os.path.exists(task["result_path"]):
        raise HTTPException(status_code=404, detail=f"Result file not found for task {task_id}")
    
    return FileResponse(
        path=task["result_path"],
        filename=os.path.basename(task["result_path"]),
        media_type="application/zip"
    )

async def process_compression(
    task_id: str,
    files: List[UploadFile],
    task_dir: Path,
    compression_level: int
):
    """Process file compression in the background"""
    # Update task status
    task = active_tasks[task_id]
    task["status"] = "processing"
    
    try:
        # Save uploaded files
        saved_files = []
        for file in files:
            file_path = task_dir / file.filename
            with open(file_path, "wb") as f:
                shutil.copyfileobj(file.file, f)
            saved_files.append(file_path)
        
        # Determine output path
        if len(saved_files) == 1:
            output_filename = f"{saved_files[0].stem}.zip"
        else:
            output_filename = "compressed_files.zip"
        
        output_path = task_dir / output_filename
        
        # Set up progress tracking and cancellation
        progress_tracker = ProgressTracker(task_id)
        cancel_event = task["cancel_event"]
        
        # For multiple files, create a source string with paths separated by semicolons
        if len(saved_files) > 1:
            source_paths = ";".join(str(path) for path in saved_files)
            # Call core.compress_item with multiple files
            core.compress_item(
                source_paths,
                str(output_path),
                progress_callback=progress_tracker.update,
                cancel_event=cancel_event,
                compression_level=compression_level
            )
        else:
            # Call core.compress_item with a single file
            core.compress_item(
                str(saved_files[0]),
                str(output_path),
                progress_callback=progress_tracker.update,
                cancel_event=cancel_event,
                compression_level=compression_level
            )
        
        # Update task status on completion
        if not cancel_event.is_set():
            task["status"] = "completed"
            task["result_path"] = str(output_path)
            task["message"] = f"Compression completed: {output_filename}"
            # Set progress to 100%
            task["progress"] = task["total"]
    except Exception as e:
        logger.error(f"Error in compression task {task_id}: {e}")
        task["status"] = "failed"
        task["message"] = f"Error: {str(e)}"

async def process_extraction(task_id: str, archive: UploadFile, task_dir: Path):
    """Process archive extraction in the background"""
    # Update task status
    task = active_tasks[task_id]
    task["status"] = "processing"
    
    try:
        # Save the uploaded archive
        archive_path = task_dir / archive.filename
        with open(archive_path, "wb") as f:
            shutil.copyfileobj(archive.file, f)
        
        # Create extraction directory
        extract_dir = task_dir / "extracted"
        extract_dir.mkdir(exist_ok=True)
        
        # Set up progress tracking and cancellation
        progress_tracker = ProgressTracker(task_id)
        cancel_event = task["cancel_event"]
        
        # Extract the archive
        core.uncompress_archive(
            str(archive_path),
            str(extract_dir),
            progress_callback=progress_tracker.update,
            cancel_event=cancel_event
        )
        
        # After extraction, create a zip of the results for download
        result_zip = task_dir / "extracted_files.zip"
        
        # Only if not cancelled
        if not cancel_event.is_set():
            # Compress the extracted files so they can be downloaded as a single file
            core.compress_item(
                str(extract_dir),
                str(result_zip),
                cancel_event=cancel_event
            )
            
            # Update task status on completion
            if not cancel_event.is_set():
                task["status"] = "completed"
                task["result_path"] = str(result_zip)
                task["message"] = "Extraction completed"
                # Set progress to 100%
                task["progress"] = task["total"]
    except Exception as e:
        logger.error(f"Error in extraction task {task_id}: {e}")
        task["status"] = "failed"
        task["message"] = f"Error: {str(e)}"

def run_api_server(host: str = "0.0.0.0", port: int = 8000):
    """Run the FastAPI server"""
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    run_api_server()