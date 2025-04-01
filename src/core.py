# src/core.py
import zipfile
import os
import logging
import psutil  # type: ignore
import time
import threading
import io
import sys
import concurrent.futures
import shutil
from pathlib import Path
from typing import Callable, Optional, List, Dict, Any, Union

# Import 7z support
import py7zr

# Import feature flags
from .feature_flags import feature_flags, FeatureFlag

# Configure a module-level logger
logger = logging.getLogger(__name__)

# Constants for resource management
MAX_MEMORY_PERCENT = 75  # Maximum memory usage percentage
MAX_FILE_SIZE_IN_MEMORY = 500 * 1024 * 1024  # 500MB max file size to process at once
CHUNK_SIZE = 8 * 1024 * 1024  # 8MB chunks for large file processing
PROGRESS_UPDATE_INTERVAL = 0.5  # Seconds between progress updates
DEFAULT_COMPRESSION_LEVEL = (
    6  # Balanced compression (0-9, with 0 being no compression and 9 maximum)
)


# Supported archive formats
class ArchiveFormat:
    ZIP = "zip"
    SEVEN_ZIP = "7z"


def detect_archive_format(file_path: str) -> str:
    """
    Detect the archive format based on file extension and validation.

    Args:
        file_path: Path to the archive file

    Returns:
        Format string (one of ArchiveFormat constants)

    Raises:
        ValueError: If the file format is not supported or cannot be detected
    """
    path = Path(file_path)
    ext = path.suffix.lower()

    # Check by extension first
    if ext == ".zip":
        if zipfile.is_zipfile(file_path):
            return ArchiveFormat.ZIP

    elif ext == ".7z":
        try:
            with py7zr.SevenZipFile(file_path, mode="r"):
                return ArchiveFormat.SEVEN_ZIP
        except py7zr.exceptions.Bad7zFile:
            pass
        except Exception as e:
            logger.warning(f"Error checking 7z format: {e}")

    # If we get here, try more invasive checks regardless of extension
    try:
        if zipfile.is_zipfile(file_path):
            return ArchiveFormat.ZIP
    except:
        pass

    try:
        with py7zr.SevenZipFile(file_path, mode="r"):
            return ArchiveFormat.SEVEN_ZIP
    except:
        pass

    # If we get here, format is not supported
    raise ValueError(f"Unsupported or invalid archive format: {file_path}")


class ResourceMonitor:
    """Monitor system resources during operations."""

    def __init__(self):
        self._stop_event = threading.Event()
        self._monitor_thread = None
        self._critical_usage = False
        self._last_values = {"memory_percent": 0, "cpu_percent": 0}

    def start(self):
        """Start the resource monitoring thread."""
        self._stop_event.clear()
        self._critical_usage = False
        self._monitor_thread = threading.Thread(
            target=self._monitor_resources, daemon=True
        )
        self._monitor_thread.start()
        logger.debug("Resource monitoring started")

    def stop(self):
        """Stop the resource monitoring thread."""
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._stop_event.set()
            self._monitor_thread.join(
                timeout=2.0
            )  # Increased timeout for reliable joining
            if self._monitor_thread.is_alive():
                logger.warning("Resource monitor thread did not terminate properly")
            else:
                logger.debug("Resource monitoring stopped")

    def _monitor_resources(self):
        """Monitor CPU and memory usage in a separate thread."""
        process = psutil.Process()

        while not self._stop_event.is_set():
            try:
                # Get current resource usage
                memory_percent = psutil.virtual_memory().percent
                cpu_percent = process.cpu_percent(interval=0.1)

                self._last_values["memory_percent"] = memory_percent
                self._last_values["cpu_percent"] = cpu_percent

                if memory_percent > MAX_MEMORY_PERCENT:
                    logger.warning(f"Memory usage critical: {memory_percent}%")
                    self._critical_usage = True

                # Log at debug level to avoid overwhelming the log file
                logger.debug(f"Memory: {memory_percent}%, CPU: {cpu_percent}%")

                # Sleep for a short interval
                # Use a loop with small sleeps to check for stop event more frequently
                for _ in range(10):
                    if self._stop_event.is_set():
                        break
                    time.sleep(0.1)  # Sleep in smaller increments to be more responsive

            except Exception as e:
                logger.error(f"Error in resource monitor: {e}")
                # Sleep shorter on error and check for stop event
                for _ in range(10):
                    if self._stop_event.is_set():
                        break
                    time.sleep(0.2)

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
    cancel_event: Optional[threading.Event] = None,
    compression_level: int = DEFAULT_COMPRESSION_LEVEL,
) -> None:
    """
    Compresses a single file or a directory into a zip archive.

    Args:
        source_path_str: Path to the file or directory to compress.
        output_zip_str: Path where the output zip file should be saved.
        progress_callback: Optional function to report progress (current_file_index, total_files).
        cancel_event: Optional event to signal cancellation of the operation.
        compression_level: Compression level (0-9, with 0 being no compression and 9 maximum compression)

    Raises:
        FileNotFoundError: If the source path doesn't exist
        PermissionError: If access to source or destination is denied
        MemoryError: If system resources are exhausted during operation
        InterruptedError: If the operation was canceled by the user
        ValueError: If the source path is invalid or not supported
        OSError: For filesystem-related errors (disk full, etc.)
        zipfile.BadZipFile: If there's an issue with the zip format
    """
    source_path = Path(source_path_str).resolve()
    output_zip = Path(output_zip_str).resolve()
    last_progress_time = 0

    # Source validation with specific error messages
    if not source_path.exists():
        raise FileNotFoundError(f"Source path not found: {source_path}")

    # Check write permissions for the output directory
    try:
        if not output_zip.parent.exists():
            output_zip.parent.mkdir(parents=True, exist_ok=True)
        # Test write permissions by creating and removing a test file
        test_file = output_zip.parent / f".test_write_{int(time.time())}"
        test_file.touch()
        test_file.unlink()
    except PermissionError:
        raise PermissionError(
            f"No permission to write to output directory: {output_zip.parent}"
        )
    except OSError as e:
        raise OSError(
            f"Cannot create output directory: {output_zip.parent}. Error: {e}"
        )

    # Check if output file already exists and is not writable
    if output_zip.exists():
        try:
            # Try to open the file for writing to check permissions
            with open(output_zip, "a"):
                pass
        except PermissionError:
            raise PermissionError(
                f"Cannot write to existing output file: {output_zip}. File may be in use by another program."
            )

    # Check disk space before starting
    try:
        # Estimate required space - source size + buffer (conservative)
        required_space = 0
        if source_path.is_file():
            required_space = source_path.stat().st_size
        elif source_path.is_dir():
            for root, _, files in os.walk(source_path):
                for file in files:
                    try:
                        file_path = Path(root) / file
                        required_space += file_path.stat().st_size
                    except (PermissionError, OSError):
                        # Skip files we can't access
                        continue

        # Check available space (with 10% buffer)
        free_space = psutil.disk_usage(output_zip.parent.as_posix()).free
        if required_space * 0.9 > free_space:  # Allow for some compression
            raise OSError(
                f"Not enough disk space. Need approximately {required_space / (1024 * 1024):.1f} MB but only {free_space / (1024 * 1024):.1f} MB available."
            )
    except Exception as e:
        logger.warning(f"Could not perform disk space check: {e}")
        # Continue anyway, the actual operation will fail if there's truly not enough space

    # Start monitoring system resources
    resource_monitor.start()

    try:
        # Create zipfile with the specified compression level
        with zipfile.ZipFile(
            output_zip,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=compression_level,
        ) as zipf:
            if source_path.is_file():
                logger.info(
                    f"Compressing file: {source_path} to {output_zip} (level {compression_level})"
                )

                # Report starting progress
                if progress_callback:
                    progress_callback(0, 1)

                # Handle large files specially
                file_size = source_path.stat().st_size
                if file_size > MAX_FILE_SIZE_IN_MEMORY:
                    logger.info(
                        f"Large file detected ({file_size / 1024 / 1024:.1f} MB), processing in chunks"
                    )
                    _compress_large_file(
                        zipf,
                        source_path,
                        progress_callback,
                        cancel_event,
                        compression_level,
                    )
                else:
                    # Try to access file before adding to zip
                    try:
                        with open(source_path, "rb") as _:
                            pass
                    except PermissionError:
                        raise PermissionError(
                            f"Cannot read source file: {source_path}. Check file permissions."
                        )
                    except OSError as e:
                        raise OSError(
                            f"Error accessing source file: {source_path}. Error: {e}"
                        )

                    # Process small file normally
                    try:
                        zipf.write(source_path, arcname=source_path.name)
                    except zipfile.LargeZipFile:
                        raise ValueError(
                            "File too large for the ZIP format. Try splitting the file into smaller parts."
                        )

                    # Report completion
                    if progress_callback:
                        progress_callback(1, 1)

                logger.info("File compression complete.")

            elif source_path.is_dir():
                logger.info(
                    f"Compressing directory: {source_path} to {output_zip} (level {compression_level})"
                )

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
                logger.info(
                    f"Found {total_files} files to compress. Total size: {dir_size / 1024 / 1024:.1f} MB"
                )

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
                        logger.warning(
                            "System resources critical, interrupting operation"
                        )
                        raise MemoryError(
                            "System memory usage is too high, operation aborted"
                        )

                    # Calculate the relative path for storing in the zip file
                    relative_path = file_path.relative_to(source_path)

                    try:
                        # For large files, use chunked processing
                        if file_size > MAX_FILE_SIZE_IN_MEMORY:
                            logger.debug(
                                f"Adding large file {file_path} as {relative_path}"
                            )
                            _add_large_file_to_zip(
                                zipf, file_path, str(relative_path), compression_level
                            )
                        else:
                            logger.debug(f"Adding {file_path} as {relative_path}")
                            zipf.write(file_path, arcname=relative_path)

                        processed_bytes += file_size
                        processed_files += 1

                        # Update progress, but not too frequently to avoid UI freezing
                        current_time = time.time()
                        if progress_callback and (
                            current_time - last_progress_time > PROGRESS_UPDATE_INTERVAL
                        ):
                            progress_callback(processed_bytes, total_bytes)
                            last_progress_time = current_time

                    except (PermissionError, OSError) as e:
                        logger.error(f"Error compressing {file_path}: {e}")
                        # Continue with other files instead of aborting

                # Ensure final progress update
                if progress_callback:
                    progress_callback(processed_bytes, total_bytes)

                logger.info(
                    f"Directory compression complete. Processed {processed_files}/{total_files} files."
                )
            else:
                raise ValueError(
                    f"Source path is neither a file nor a directory: {source_path}"
                )

    except (MemoryError, InterruptedError) as e:
        # Handle special exceptions
        logger.error(f"Compression aborted: {e}")

        # Try to cleanly handle partial files
        if output_zip.exists():
            try:
                output_zip.unlink()
                logger.info(f"Removed incomplete zip file: {output_zip}")
            except OSError as unlink_err:
                logger.error(
                    f"Failed to remove partial zip file {output_zip}: {unlink_err}"
                )

        raise
    except zipfile.BadZipFile as e:
        logger.error(f"ZIP format error: {e}")
        _cleanup_output_file(output_zip)
        raise zipfile.BadZipFile(f"Failed to create valid ZIP file: {e}")
    except ValueError as e:
        logger.error(f"Value error: {e}")
        _cleanup_output_file(output_zip)
        raise
    except PermissionError as e:
        logger.error(f"Permission error: {e}")
        _cleanup_output_file(output_zip)
        raise PermissionError(f"Permission denied: {e}")
    except OSError as e:
        logger.error(f"OS error: {e}")
        _cleanup_output_file(output_zip)
        if "disk full" in str(e).lower() or "no space" in str(e).lower():
            raise OSError(f"Disk full: {e}")
        raise
    except Exception as e:
        logger.error(f"Compression failed: {e}", exc_info=True)
        _cleanup_output_file(output_zip)
        raise  # Re-raise the original exception
    finally:
        # Stop resource monitoring
        resource_monitor.stop()


def _cleanup_output_file(output_zip: Path) -> None:
    """
    Clean up a partially created zip file after an error.

    Args:
        output_zip: Path to the zip file to clean up
    """
    # Attempt to remove partially created zip file on error
    if output_zip.exists():
        try:
            output_zip.unlink()
            logger.info(f"Removed partially created zip file: {output_zip}")
        except OSError as unlink_err:
            logger.error(
                f"Failed to remove partial zip file {output_zip}: {unlink_err}"
            )


def _compress_large_file(
    zipf: zipfile.ZipFile,
    file_path: Path,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    cancel_event: Optional[threading.Event] = None,
    compression_level: int = DEFAULT_COMPRESSION_LEVEL,
) -> None:
    """Handle compression of a large file in chunks to avoid memory issues."""
    file_size = file_path.stat().st_size
    arcname = file_path.name

    # Create the file entry in the zip file
    zinfo = zipfile.ZipInfo.from_file(file_path, arcname=arcname)
    zinfo.compress_type = zipfile.ZIP_DEFLATED
    # Note: compression level is set at the ZipFile level, not individual ZipInfo level

    # Process the file in chunks
    processed_bytes = 0
    last_progress_time = 0

    with zipf.open(zinfo, "w") as dest, open(file_path, "rb") as source:
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
            if progress_callback and (
                current_time - last_progress_time > PROGRESS_UPDATE_INTERVAL
            ):
                progress_callback(processed_bytes, file_size)
                last_progress_time = current_time

    # Ensure final progress update
    if progress_callback:
        progress_callback(file_size, file_size)


def _add_large_file_to_zip(
    zipf: zipfile.ZipFile,
    file_path: Path,
    arcname: str,
    compression_level: int = DEFAULT_COMPRESSION_LEVEL,
) -> None:
    """Add a large file to a zip archive in chunks."""
    with open(file_path, "rb") as f:
        # Create a ZipInfo object
        zinfo = zipfile.ZipInfo.from_file(file_path, arcname=arcname)
        zinfo.compress_type = zipfile.ZIP_DEFLATED
        # Compression level is set at the ZipFile level, not individual ZipInfo level

        # Open the entry for writing
        with zipf.open(zinfo, "w") as dest:
            while True:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break
                dest.write(chunk)


def uncompress_archive(
    archive_path_str: str,
    extract_to_str: str,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> None:
    """
    Uncompresses an archive (ZIP or 7z) to a specified directory.

    Args:
        archive_path_str: Path to the archive file to uncompress.
        extract_to_str: Path to the directory where files should be extracted.
        progress_callback: Optional function to report progress (current_file_index, total_files).
        cancel_event: Optional event to signal cancellation of the operation.

    Raises:
        FileNotFoundError: If the archive file doesn't exist
        PermissionError: If access to archive or destination is denied
        MemoryError: If system resources are exhausted during operation
        InterruptedError: If the operation was canceled by the user
        ValueError: If the archive format is not supported
        OSError: For filesystem-related errors (disk full, etc.)
        zipfile.BadZipFile: If there's an issue with the zip format
        py7zr.exceptions.Bad7zFile: If there's an issue with the 7z format
    """
    archive_path = Path(archive_path_str).resolve()
    extract_to = Path(extract_to_str).resolve()
    last_progress_time = 0

    if not archive_path.is_file():
        raise FileNotFoundError(f"Archive file not found: {archive_path}")

    # Detect archive format
    try:
        archive_format = detect_archive_format(str(archive_path))
        logger.info(f"Detected archive format: {archive_format}")
    except ValueError as e:
        raise ValueError(f"Invalid or unsupported archive format: {e}")

    # Create extraction directory if it doesn't exist
    extract_to.mkdir(parents=True, exist_ok=True)

    # Start monitoring system resources
    resource_monitor.start()

    try:
        if archive_format == ArchiveFormat.ZIP:
            _uncompress_zip(archive_path, extract_to, progress_callback, cancel_event)
        elif archive_format == ArchiveFormat.SEVEN_ZIP:
            _uncompress_7z(archive_path, extract_to, progress_callback, cancel_event)
        else:
            raise ValueError(f"Unsupported archive format: {archive_format}")

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


def _uncompress_zip(
    zip_path: Path,
    extract_to: Path,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> None:
    """Internal function to handle ZIP extraction."""
    last_progress_time = 0

    if not zipfile.is_zipfile(zip_path):
        raise zipfile.BadZipFile(f"File is not a valid zip archive: {zip_path}")

    # Check archive size before opening
    archive_size = zip_path.stat().st_size
    logger.info(f"Archive size: {archive_size / 1024 / 1024:.1f} MB")

    with zipfile.ZipFile(zip_path, "r") as zipf:
        members = zipf.infolist()
        total_files = len(members)
        logger.info(f"Found {total_files} members in archive")

        # Calculate total uncompressed size
        total_uncompressed = 0
        for member in members:
            total_uncompressed += member.file_size

        logger.info(
            f"Total uncompressed size: {total_uncompressed / 1024 / 1024:.1f} MB"
        )

        # Early check for available disk space
        free_space = psutil.disk_usage(extract_to.as_posix()).free
        if total_uncompressed > free_space:
            raise OSError(
                f"Not enough disk space. Need {total_uncompressed / 1024 / 1024:.1f} MB, "
                f"but only {free_space / 1024 / 1024:.1f} MB available"
            )

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
                        logger.debug(
                            f"Extracting large file {member.filename} ({member.file_size / 1024 / 1024:.1f} MB)"
                        )
                        _extract_large_file(zipf, member, extract_to)
                    else:
                        # Process small file normally
                        zipf.extract(member, path=extract_to)

                extracted_bytes += member.file_size

                # Update progress, but not too frequently
                current_time = time.time()
                if progress_callback and (
                    current_time - last_progress_time > PROGRESS_UPDATE_INTERVAL
                ):
                    progress_callback(extracted_bytes, total_uncompressed)
                    last_progress_time = current_time

            except (PermissionError, OSError) as e:
                logger.error(f"Error extracting {member.filename}: {e}")
                # Continue with other files instead of aborting

        # Ensure final progress update
        if progress_callback:
            progress_callback(extracted_bytes, total_uncompressed)


def _uncompress_7z(
    seven_zip_path: Path,
    extract_to: Path,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> None:
    """Internal function to handle 7z extraction."""
    last_progress_time = 0

    # Check archive size
    archive_size = seven_zip_path.stat().st_size
    logger.info(f"7z archive size: {archive_size / 1024 / 1024:.1f} MB")

    try:
        with py7zr.SevenZipFile(seven_zip_path, mode="r") as z:
            # Get archive information
            archive_info = z.archiveinfo()
            total_uncompressed = archive_info.uncompressed

            logger.info(
                f"7z archive: {len(z.files)} files, "
                f"uncompressed size: {total_uncompressed / 1024 / 1024:.1f} MB"
            )

            # Early check for available disk space
            free_space = psutil.disk_usage(extract_to.as_posix()).free
            if total_uncompressed > free_space:
                raise OSError(
                    f"Not enough disk space. Need {total_uncompressed / 1024 / 1024:.1f} MB, "
                    f"but only {free_space / 1024 / 1024:.1f} MB available"
                )

            # Report initial progress
            if progress_callback:
                progress_callback(0, total_uncompressed)

            # The py7zr doesn't provide a way to extract file by file with progress
            # We need to extract everything at once and then monitor the progress by checking
            # the extracted files' sizes periodically

            # We'll extract to a temporary directory first, to handle progress reporting
            with tempfile.TemporaryDirectory() as temp_dir:
                extract_thread = threading.Thread(
                    target=lambda: z.extractall(path=temp_dir)
                )
                extract_thread.start()

                # Monitor extraction progress
                while extract_thread.is_alive():
                    # Check for cancellation
                    if cancel_event and cancel_event.is_set():
                        # We can't directly cancel extraction, so we'll have to let it finish
                        # and then not copy the files over
                        logger.info(
                            "7z extraction cancellation requested, waiting for extract thread"
                        )
                        extract_thread.join()
                        raise InterruptedError("Operation cancelled by user")

                    # Check resource usage
                    if resource_monitor.is_resource_critical:
                        # Same issue as above, we'll wait for the thread to finish
                        logger.warning(
                            "System resources critical, waiting for extract thread"
                        )
                        extract_thread.join()
                        raise MemoryError(
                            "System memory usage is too high, operation aborted"
                        )

                    # Estimate progress by checking extracted files
                    current_extracted_size = 0
                    for root, _, files in os.walk(temp_dir):
                        for file in files:
                            try:
                                current_extracted_size += os.path.getsize(
                                    os.path.join(root, file)
                                )
                            except (OSError, FileNotFoundError):
                                pass

                    # Update progress
                    current_time = time.time()
                    if progress_callback and (
                        current_time - last_progress_time > PROGRESS_UPDATE_INTERVAL
                    ):
                        # Cap at total_uncompressed to avoid showing >100%
                        current_extracted_size = min(
                            current_extracted_size, total_uncompressed
                        )
                        progress_callback(current_extracted_size, total_uncompressed)
                        last_progress_time = current_time

                    # Sleep briefly before checking again
                    time.sleep(0.1)

                # Extraction complete, copy files to final destination
                for item in os.listdir(temp_dir):
                    src_path = os.path.join(temp_dir, item)
                    dst_path = os.path.join(extract_to, item)

                    if os.path.isdir(src_path):
                        if os.path.exists(dst_path):
                            shutil.rmtree(dst_path)
                        shutil.copytree(src_path, dst_path)
                    else:
                        shutil.copy2(src_path, dst_path)

            # Ensure final progress update
            if progress_callback:
                progress_callback(total_uncompressed, total_uncompressed)

    except py7zr.exceptions.Bad7zFile as e:
        raise e
    except Exception as e:
        logger.error(f"Error extracting 7z archive: {e}")
        raise


def _extract_large_file(
    zipf: zipfile.ZipFile,
    member: zipfile.ZipInfo,
    extract_to: Path,
) -> None:
    """Extract a large file from a zip archive in chunks."""
    # Create parent directories as needed
    output_path = extract_to / member.filename
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Extract the file in chunks
    with zipf.open(member) as source, open(output_path, "wb") as target:
        shutil.copyfileobj(source, target, CHUNK_SIZE)


def compress_items_parallel(
    source_paths: List[str],
    output_zip_str: str,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    cancel_event: Optional[threading.Event] = None,
    compression_level: int = DEFAULT_COMPRESSION_LEVEL,
    max_workers: int = None,
) -> None:
    """
    Compress multiple items in parallel using feature flag-controlled parallel compression.

    This function is used when the PARALLEL_COMPRESSION feature flag is enabled.
    It compresses multiple files or directories in parallel for better performance.

    Args:
        source_paths: List of paths to files or directories to compress
        output_zip_str: Path where the output zip file should be saved
        progress_callback: Optional function to report progress
        cancel_event: Optional event to signal cancellation
        compression_level: Compression level (0-9)
        max_workers: Maximum number of worker threads (None = CPU count)

    Raises:
        Various exceptions as in compress_item()
    """
    output_zip = Path(output_zip_str).resolve()
    total_size = 0
    files_to_compress = []

    # First, gather information about all files to compress
    logger.info(f"Scanning {len(source_paths)} source paths for parallel compression")

    for source_path_str in source_paths:
        source_path = Path(source_path_str).resolve()

        if not source_path.exists():
            logger.warning(f"Source path not found, skipping: {source_path}")
            continue

        if source_path.is_file():
            try:
                file_size = source_path.stat().st_size
                total_size += file_size
                files_to_compress.append((source_path, source_path.name, file_size))
            except (PermissionError, OSError) as e:
                logger.warning(f"Could not access file {source_path}: {e}")

        elif source_path.is_dir():
            # Scan directory recursively
            for root, _, files in os.walk(source_path):
                for file in files:
                    file_path = Path(root) / file
                    try:
                        file_size = file_path.stat().st_size
                        # Calculate path relative to the source directory
                        rel_path = file_path.relative_to(source_path)
                        total_size += file_size
                        files_to_compress.append((file_path, rel_path, file_size))
                    except (PermissionError, OSError) as e:
                        logger.warning(f"Could not access file {file_path}: {e}")

    if not files_to_compress:
        logger.warning("No files to compress")
        if progress_callback:
            progress_callback(0, 0)
        return

    logger.info(
        f"Found {len(files_to_compress)} files to compress. Total size: {total_size / 1024 / 1024:.1f} MB"
    )

    # Determine the number of workers
    if max_workers is None:
        max_workers = min(
            32, os.cpu_count() + 4
        )  # Standard formula for I/O-bound tasks

    # Start monitoring system resources
    resource_monitor.start()

    try:
        # Create zipfile with the specified compression level
        with zipfile.ZipFile(
            output_zip,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=compression_level,
        ) as zipf:
            # Use a lock to synchronize access to the zip file
            zip_lock = threading.Lock()
            processed_bytes = 0
            processed_lock = threading.Lock()

            def compress_file(file_info):
                nonlocal processed_bytes
                file_path, arc_name, file_size = file_info

                # Check for cancellation
                if cancel_event and cancel_event.is_set():
                    return False

                try:
                    with zip_lock:
                        # Add the file to the zip
                        if file_size > MAX_FILE_SIZE_IN_MEMORY:
                            # For large files, use the chunked approach
                            with open(file_path, "rb") as f:
                                # Create a ZipInfo object
                                zinfo = zipfile.ZipInfo.from_file(
                                    file_path, arcname=str(arc_name)
                                )
                                zinfo.compress_type = zipfile.ZIP_DEFLATED

                                # Open the entry for writing
                                with zipf.open(zinfo, "w") as dest:
                                    while True:
                                        chunk = f.read(CHUNK_SIZE)
                                        if not chunk:
                                            break
                                        dest.write(chunk)
                        else:
                            # For small files, add directly
                            zipf.write(file_path, arcname=str(arc_name))

                    # Update progress
                    with processed_lock:
                        processed_bytes += file_size
                        if progress_callback:
                            progress_callback(processed_bytes, total_size)

                    return True

                except Exception as e:
                    logger.error(f"Error compressing {file_path}: {e}")
                    return False

            # Report initial progress
            if progress_callback:
                progress_callback(0, total_size)

            # Use a thread pool to compress files in parallel
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=max_workers
            ) as executor:
                # Submit all tasks
                future_to_file = {
                    executor.submit(compress_file, file_info): file_info
                    for file_info in files_to_compress
                }

                # Process results as they complete
                for future in concurrent.futures.as_completed(future_to_file):
                    if cancel_event and cancel_event.is_set():
                        # Cancel all remaining tasks
                        for f in future_to_file:
                            f.cancel()
                        raise InterruptedError("Operation cancelled by user")

                    file_path = future_to_file[future][0]
                    try:
                        success = future.result()
                        if not success:
                            logger.warning(f"Failed to compress {file_path}")
                    except Exception as e:
                        logger.error(f"Exception while compressing {file_path}: {e}")

                if cancel_event and cancel_event.is_set():
                    raise InterruptedError("Operation cancelled by user")

                # Ensure final progress update
                if progress_callback:
                    progress_callback(total_size, total_size)

            logger.info(
                f"Parallel compression complete. Processed {len(files_to_compress)} files."
            )

    except (MemoryError, InterruptedError) as e:
        # Handle special exceptions
        logger.error(f"Compression aborted: {e}")
        _cleanup_output_file(output_zip)
        raise
    except Exception as e:
        logger.error(f"Parallel compression failed: {e}", exc_info=True)
        _cleanup_output_file(output_zip)
        raise
    finally:
        # Stop resource monitoring
        resource_monitor.stop()


def compress_with_feature_flags(
    source_paths: Union[str, List[str]],
    output_zip: str,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    cancel_event: Optional[threading.Event] = None,
    compression_level: Optional[int] = None,
) -> None:
    """
    Compress files/directories using the appropriate compression method based on feature flags.

    This function delegates to either the standard compression or parallel compression
    based on enabled feature flags and configuration.

    Args:
        source_paths: Path or list of paths to compress
        output_zip: Output zip file path
        progress_callback: Optional function to report progress
        cancel_event: Optional event to signal cancellation
        compression_level: Optional compression level (uses config value if None)
    """
    # If compression_level is not specified, use the one from config
    if compression_level is None:
        from .config import config

        compression_level = config.get(
            "compression", "default_level", DEFAULT_COMPRESSION_LEVEL
        )

    # Convert single path to list
    if isinstance(source_paths, str):
        source_paths = [source_paths]

    # Check if deep inspection feature is enabled
    if feature_flags.is_enabled(FeatureFlag.DEEP_INSPECTION):
        logger.info("Deep inspection feature enabled, performing additional validation")
        # Validate paths more thoroughly
        validated_paths = []
        for path in source_paths:
            try:
                test_path = Path(path)
                if not test_path.exists():
                    logger.warning(f"Path not found, skipping: {path}")
                    continue

                # Additional validations could be added here
                validated_paths.append(path)
            except Exception as e:
                logger.error(f"Error validating path {path}: {e}")

        # Update source_paths to only include valid paths
        source_paths = validated_paths

    # Use memory-optimized settings if enabled
    if feature_flags.is_enabled(FeatureFlag.MEMORY_OPTIMIZED):
        logger.info("Memory optimization feature enabled")
        global MAX_FILE_SIZE_IN_MEMORY, CHUNK_SIZE
        # Use more conservative memory limits when memory optimization is enabled
        MAX_FILE_SIZE_IN_MEMORY = 100 * 1024 * 1024  # 100MB instead of 500MB
        CHUNK_SIZE = 4 * 1024 * 1024  # 4MB chunks instead of 8MB

    # Check if parallel compression should be used
    if (
        feature_flags.is_enabled(FeatureFlag.PARALLEL_COMPRESSION)
        and len(source_paths) > 1
    ):
        logger.info("Using parallel compression for multiple items")
        compress_items_parallel(
            source_paths, output_zip, progress_callback, cancel_event, compression_level
        )
    else:
        # Use regular compression for single items or when parallel compression is disabled
        if len(source_paths) == 1:
            logger.info("Compressing single item using standard compression")
            compress_item(
                source_paths[0],
                output_zip,
                progress_callback,
                cancel_event,
                compression_level,
            )
        else:
            logger.info("Compressing multiple items sequentially")
            # Process multiple paths sequentially
            from tempfile import TemporaryDirectory
            import shutil

            # Create a temporary directory for flattening sources
            with TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)

                # Copy all source paths to temp directory
                for i, source_path in enumerate(source_paths):
                    src_path = Path(source_path)
                    if src_path.is_dir():
                        # Copy directory with unique name
                        dst_path = temp_path / src_path.name
                        # If path already exists, add a unique suffix
                        if dst_path.exists():
                            dst_path = temp_path / f"{src_path.name}_{i}"
                        shutil.copytree(src_path, dst_path)
                    else:
                        # Copy file, ensuring unique name
                        dst_path = temp_path / src_path.name
                        if dst_path.exists():
                            dst_path = (
                                temp_path / f"{src_path.stem}_{i}{src_path.suffix}"
                            )
                        shutil.copy2(src_path, dst_path)

                # Compress the temporary directory
                compress_item(
                    str(temp_path),
                    output_zip,
                    progress_callback,
                    cancel_event,
                    compression_level,
                )
