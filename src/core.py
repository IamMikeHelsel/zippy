# src/zip_utility/core.py
import zipfile
import os
import logging
import psutil
import time
import threading
import io
import sys
import concurrent.futures
from pathlib import Path
from typing import Callable, Optional, List, Dict, Any, Union

# Configure a module-level logger
logger = logging.getLogger(__name__)

# Constants for resource management
MAX_MEMORY_PERCENT = 75  # Maximum memory usage percentage
MAX_FILE_SIZE_IN_MEMORY = 500 * 1024 * 1024  # 500MB max file size to process at once
CHUNK_SIZE = 8 * 1024 * 1024  # 8MB chunks for large file processing
PROGRESS_UPDATE_INTERVAL = 0.5  # Seconds between progress updates

class ResourceMonitor:
    """Monitor system resources during operations."""
    
    def __init__(self):
        self._stop_event = threading.Event()
        self._monitor_thread = None
        self._critical_usage = False
        self._last_values = {
            'memory_percent': 0,
            'cpu_percent': 0
        }
    
    def start(self):
        """Start the resource monitoring thread."""
        self._stop_event.clear()
        self._critical_usage = False
        self._monitor_thread = threading.Thread(
            target=self._monitor_resources, 
            daemon=True
        )
        self._monitor_thread.start()
        logger.debug("Resource monitoring started")
    
    def stop(self):
        """Stop the resource monitoring thread."""
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._stop_event.set()
            self._monitor_thread.join(timeout=1.0)
            logger.debug("Resource monitoring stopped")
    
    def _monitor_resources(self):
        """Monitor CPU and memory usage in a separate thread."""
        process = psutil.Process()
        
        while not self._stop_event.is_set():
            try:
                # Get current resource usage
                memory_percent = psutil.virtual_memory().percent
                cpu_percent = process.cpu_percent(interval=0.1)
                
                self._last_values['memory_percent'] = memory_percent
                self._last_values['cpu_percent'] = cpu_percent
                
                if memory_percent > MAX_MEMORY_PERCENT:
                    logger.warning(f"Memory usage critical: {memory_percent}%")
                    self._critical_usage = True
                
                # Log at debug level to avoid overwhelming the log file
                logger.debug(f"Memory: {memory_percent}%, CPU: {cpu_percent}%")
                
                # Sleep for a short interval
                time.sleep(1.0)
                
            except Exception as e:
                logger.error(f"Error in resource monitor: {e}")
                time.sleep(2.0)  # Sleep longer on error
    
    @property
    def is_resource_critical(self) -> bool:
        """Check if system resources are critically low."""
        return self._critical_usage
    
    @property
    def current_usage(self) -> Dict[str, float]:
        """Get the current resource usage values."""
        return self._last_values.copy()

# Create a global resource monitor
resource_monitor = ResourceMonitor()

def compress_item(
    source_path_str: str,
    output_zip_str: str,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    cancel_event: Optional[threading.Event] = None
) -> None:
    """
    Compresses a single file or a directory into a zip archive.

    Args:
        source_path_str: Path to the file or directory to compress.
        output_zip_str: Path where the output zip file should be saved.
        progress_callback: Optional function to report progress (current_file_index, total_files).
        cancel_event: Optional event to signal cancellation of the operation.
    """
    source_path = Path(source_path_str).resolve()
    output_zip = Path(output_zip_str).resolve()
    last_progress_time = 0
    
    if not source_path.exists():
        raise FileNotFoundError(f"Source path not found: {source_path}")

    output_zip.parent.mkdir(parents=True, exist_ok=True)  # Ensure output directory exists
    
    # Start monitoring system resources
    resource_monitor.start()
    
    try:
        with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
            if source_path.is_file():
                logger.info(f"Compressing file: {source_path} to {output_zip}")
                
                # Report starting progress
                if progress_callback:
                    progress_callback(0, 1)
                
                # Handle large files specially
                file_size = source_path.stat().st_size
                if file_size > MAX_FILE_SIZE_IN_MEMORY:
                    logger.info(f"Large file detected ({file_size/1024/1024:.1f} MB), processing in chunks")
                    _compress_large_file(zipf, source_path, progress_callback, cancel_event)
                else:
                    # Process small file normally
                    zipf.write(source_path, arcname=source_path.name)
                    
                    # Report completion
                    if progress_callback:
                        progress_callback(1, 1)
                
                logger.info("File compression complete.")
                
            elif source_path.is_dir():
                logger.info(f"Compressing directory: {source_path} to {output_zip}")
                
                # Collect all files to compress for progress reporting
                files_to_compress = []
                dir_size = 0
                
                # Scan directory with size calculation
                for root, _, files in os.walk(source_path):
                    for file in files:
                        file_path = Path(root) / file
                        try:
                            file_size = file_path.stat().st_size
                            dir_size += file_size
                            files_to_compress.append((file_path, file_size))
                        except (PermissionError, OSError) as e:
                            logger.warning(f"Could not access file {file_path}: {e}")
                
                total_files = len(files_to_compress)
                logger.info(f"Found {total_files} files to compress. Total size: {dir_size/1024/1024:.1f} MB")
                
                # Early return if no files to compress
                if not files_to_compress:
                    logger.warning("No files to compress in directory")
                    if progress_callback:
                        progress_callback(0, 0)
                    return
                
                # Process the files
                processed_files = 0
                processed_bytes = 0
                total_bytes = max(1, dir_size)  # Avoid division by zero
                
                for i, (file_path, file_size) in enumerate(files_to_compress):
                    # Check for cancellation
                    if cancel_event and cancel_event.is_set():
                        logger.info("Compression cancelled by user")
                        raise InterruptedError("Operation cancelled by user")
                    
                    # Check resource usage
                    if resource_monitor.is_resource_critical:
                        logger.warning("System resources critical, interrupting operation")
                        raise MemoryError("System memory usage is too high, operation aborted")
                    
                    # Calculate the relative path for storing in the zip file
                    relative_path = file_path.relative_to(source_path)
                    
                    try:
                        # For large files, use chunked processing
                        if file_size > MAX_FILE_SIZE_IN_MEMORY:
                            logger.debug(f"Adding large file {file_path} as {relative_path}")
                            _add_large_file_to_zip(zipf, file_path, str(relative_path))
                        else:
                            logger.debug(f"Adding {file_path} as {relative_path}")
                            zipf.write(file_path, arcname=relative_path)
                        
                        processed_bytes += file_size
                        processed_files += 1
                        
                        # Update progress, but not too frequently to avoid UI freezing
                        current_time = time.time()
                        if progress_callback and (current_time - last_progress_time > PROGRESS_UPDATE_INTERVAL):
                            progress_callback(processed_bytes, total_bytes)
                            last_progress_time = current_time
                            
                    except (PermissionError, OSError) as e:
                        logger.error(f"Error compressing {file_path}: {e}")
                        # Continue with other files instead of aborting
                
                # Ensure final progress update
                if progress_callback:
                    progress_callback(processed_bytes, total_bytes)
                
                logger.info(f"Directory compression complete. Processed {processed_files}/{total_files} files.")
            else:
                raise ValueError(f"Source path is neither a file nor a directory: {source_path}")
                
    except (MemoryError, InterruptedError) as e:
        # Handle special exceptions
        logger.error(f"Compression aborted: {e}")
        
        # Try to cleanly handle partial files
        if output_zip.exists():
            try:
                output_zip.unlink()
                logger.info(f"Removed incomplete zip file: {output_zip}")
            except OSError as unlink_err:
                logger.error(f"Failed to remove partial zip file {output_zip}: {unlink_err}")
        
        raise
    except Exception as e:
        logger.error(f"Compression failed: {e}", exc_info=True)
        
        # Attempt to remove partially created zip file on error
        if output_zip.exists():
            try:
                output_zip.unlink()
                logger.info(f"Removed partially created zip file: {output_zip}")
            except OSError as unlink_err:
                logger.error(f"Failed to remove partial zip file {output_zip}: {unlink_err}")
        
        raise  # Re-raise the original exception
    finally:
        # Stop resource monitoring
        resource_monitor.stop()


def _compress_large_file(
    zipf: zipfile.ZipFile,
    file_path: Path,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    cancel_event: Optional[threading.Event] = None
) -> None:
    """Handle compression of a large file in chunks to avoid memory issues."""
    file_size = file_path.stat().st_size
    arcname = file_path.name
    
    # Create the file entry in the zip file
    zinfo = zipfile.ZipInfo.from_file(file_path, arcname=arcname)
    zinfo.compress_type = zipfile.ZIP_DEFLATED
    
    # Process the file in chunks
    processed_bytes = 0
    last_progress_time = 0
    
    with zipf.open(zinfo, 'w') as dest, open(file_path, 'rb') as source:
        while True:
            # Check for cancellation
            if cancel_event and cancel_event.is_set():
                logger.info("Compression cancelled by user")
                raise InterruptedError("Operation cancelled by user")
                
            # Read a chunk of data
            chunk = source.read(CHUNK_SIZE)
            if not chunk:
                break
                
            dest.write(chunk)
            processed_bytes += len(chunk)
            
            # Update progress, but not too frequently
            current_time = time.time()
            if progress_callback and (current_time - last_progress_time > PROGRESS_UPDATE_INTERVAL):
                progress_callback(processed_bytes, file_size)
                last_progress_time = current_time
    
    # Ensure final progress update
    if progress_callback:
        progress_callback(file_size, file_size)


def _add_large_file_to_zip(
    zipf: zipfile.ZipFile,
    file_path: Path,
    arcname: str
) -> None:
    """Add a large file to a zip archive in chunks."""
    with open(file_path, 'rb') as f:
        # Create a ZipInfo object
        zinfo = zipfile.ZipInfo.from_file(file_path, arcname=arcname)
        zinfo.compress_type = zipfile.ZIP_DEFLATED
        
        # Open the entry for writing
        with zipf.open(zinfo, 'w') as dest:
            while True:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break
                dest.write(chunk)


def uncompress_archive(
    zip_path_str: str,
    extract_to_str: str,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    cancel_event: Optional[threading.Event] = None
) -> None:
    """
    Uncompresses a zip archive to a specified directory.

    Args:
        zip_path_str: Path to the zip file to uncompress.
        extract_to_str: Path to the directory where files should be extracted.
        progress_callback: Optional function to report progress (current_file_index, total_files).
        cancel_event: Optional event to signal cancellation of the operation.
    """
    zip_path = Path(zip_path_str).resolve()
    extract_to = Path(extract_to_str).resolve()
    last_progress_time = 0
    
    if not zip_path.is_file():
        raise FileNotFoundError(f"Zip archive not found: {zip_path}")
    if not zipfile.is_zipfile(zip_path):
        raise zipfile.BadZipFile(f"File is not a valid zip archive: {zip_path}")
        
    # Check archive size before opening
    archive_size = zip_path.stat().st_size
    logger.info(f"Archive size: {archive_size/1024/1024:.1f} MB")
    
    extract_to.mkdir(parents=True, exist_ok=True)  # Ensure extraction directory exists
    
    # Start monitoring system resources
    resource_monitor.start()
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zipf:
            members = zipf.infolist()
            total_files = len(members)
            logger.info(f"Found {total_files} members in archive")
            
            # Calculate total uncompressed size
            total_uncompressed = 0
            for member in members:
                total_uncompressed += member.file_size
            
            logger.info(f"Total uncompressed size: {total_uncompressed/1024/1024:.1f} MB")
            
            # Early check for available disk space
            free_space = psutil.disk_usage(extract_to.as_posix()).free
            if total_uncompressed > free_space:
                raise OSError(f"Not enough disk space. Need {total_uncompressed/1024/1024:.1f} MB, "
                              f"but only {free_space/1024/1024:.1f} MB available")
                              
            # Report initial progress
            if progress_callback:
                progress_callback(0, total_uncompressed)
            
            # Extract file by file for better progress tracking and resource management
            extracted_bytes = 0
            for i, member in enumerate(members):
                # Check for cancellation
                if cancel_event and cancel_event.is_set():
                    logger.info("Extraction cancelled by user")
                    raise InterruptedError("Operation cancelled by user")
                
                # Check resource usage
                if resource_monitor.is_resource_critical:
                    logger.warning("System resources critical, interrupting operation")
                    raise MemoryError("System memory usage is too high, operation aborted")
                
                try:
                    # Extract the file
                    if member.is_dir():
                        # Create directory if it doesn't exist
                        dir_path = extract_to / member.filename
                        dir_path.mkdir(parents=True, exist_ok=True)
                    else:
                        # Process large files specially
                        if member.file_size > MAX_FILE_SIZE_IN_MEMORY:
                            logger.debug(f"Extracting large file {member.filename} ({member.file_size/1024/1024:.1f} MB)")
                            _extract_large_file(zipf, member, extract_to)
                        else:
                            # Process small file normally
                            zipf.extract(member, path=extract_to)
                    
                    extracted_bytes += member.file_size
                    
                    # Update progress, but not too frequently
                    current_time = time.time()
                    if progress_callback and (current_time - last_progress_time > PROGRESS_UPDATE_INTERVAL):
                        progress_callback(extracted_bytes, total_uncompressed)
                        last_progress_time = current_time
                        
                except (PermissionError, OSError) as e:
                    logger.error(f"Error extracting {member.filename}: {e}")
                    # Continue with other files instead of aborting
            
            # Ensure final progress update
            if progress_callback:
                progress_callback(extracted_bytes, total_uncompressed)
                
            logger.info("Extraction complete.")
            
    except (MemoryError, InterruptedError) as e:
        # Handle special exceptions
        logger.error(f"Extraction aborted: {e}")
        # Note: We don't clean up partially extracted files
        raise
    except Exception as e:
        logger.error(f"Extraction failed: {e}", exc_info=True)
        # Note: We don't clean up partially extracted files
        raise  # Re-raise the original exception
    finally:
        # Stop resource monitoring
        resource_monitor.stop()


def _extract_large_file(zipf: zipfile.ZipFile, member: zipfile.ZipInfo, extract_to: Path) -> None:
    """Extract a large file in chunks to avoid memory issues."""
    target_path = extract_to / member.filename
    
    # Create parent directories if they don't exist
    target_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Extract the file in chunks
    with zipf.open(member) as source, open(target_path, 'wb') as target:
        while True:
            chunk = source.read(CHUNK_SIZE)
            if not chunk:
                break
            target.write(chunk)