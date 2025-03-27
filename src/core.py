# src/zip_utility/core.py
import zipfile
import os
import logging
from pathlib import Path
from typing import Callable, Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def compress_item(
    source_path_str: str,
    output_zip_str: str,
    progress_callback: Optional[Callable[[int, int], None]] = None
) -> None:
    """
    Compresses a single file or a directory into a zip archive.

    Args:
        source_path_str: Path to the file or directory to compress.
        output_zip_str: Path where the output zip file should be saved.
        progress_callback: Optional function to report progress (current_file_index, total_files).
    """
    source_path = Path(source_path_str).resolve()
    output_zip = Path(output_zip_str).resolve()

    if not source_path.exists():
        raise FileNotFoundError(f"Source path not found: {source_path}")

    output_zip.parent.mkdir(parents=True, exist_ok=True) # Ensure output directory exists

    try:
        with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
            if source_path.is_file():
                logging.info(f"Compressing file: {source_path} to {output_zip}")
                if progress_callback:
                    progress_callback(0, 1) # Report start for single file
                zipf.write(source_path, arcname=source_path.name)
                if progress_callback:
                    progress_callback(1, 1) # Report end for single file
                logging.info("File compression complete.")
            elif source_path.is_dir():
                logging.info(f"Compressing directory: {source_path} to {output_zip}")
                # Collect all files to compress for progress reporting
                files_to_compress = [
                    p for p in source_path.rglob('*') if p.is_file()
                ]
                total_files = len(files_to_compress)
                logging.info(f"Found {total_files} files to compress.")

                for i, file_path in enumerate(files_to_compress):
                    # Calculate the relative path for storing in the zip file
                    relative_path = file_path.relative_to(source_path)
                    logging.debug(f"Adding {file_path} as {relative_path}")
                    zipf.write(file_path, arcname=relative_path)
                    if progress_callback:
                        progress_callback(i + 1, total_files) # Report progress

                # Optionally add the root directory itself if it was empty or just for structure
                # if not files_to_compress:
                #    zip_info = zipfile.ZipInfo(f"{source_path.name}/")
                #    zip_info.external_attr = 0o40775 << 16 # drwxrwxr-x
                #    zipf.writestr(zip_info, '')

                logging.info("Directory compression complete.")
            else:
                raise ValueError(f"Source path is neither a file nor a directory: {source_path}")

    except Exception as e:
        logging.error(f"Compression failed: {e}", exc_info=True)
        # Attempt to remove partially created zip file on error
        if output_zip.exists():
            try:
                output_zip.unlink()
                logging.info(f"Removed partially created zip file: {output_zip}")
            except OSError as unlink_err:
                logging.error(f"Failed to remove partial zip file {output_zip}: {unlink_err}")
        raise # Re-raise the original exception


def uncompress_archive(
    zip_path_str: str,
    extract_to_str: str,
    progress_callback: Optional[Callable[[int, int], None]] = None
) -> None:
    """
    Uncompresses a zip archive to a specified directory.

    Args:
        zip_path_str: Path to the zip file to uncompress.
        extract_to_str: Path to the directory where files should be extracted.
        progress_callback: Optional function to report progress (current_file_index, total_files).
    """
    zip_path = Path(zip_path_str).resolve()
    extract_to = Path(extract_to_str).resolve()

    if not zip_path.is_file():
        raise FileNotFoundError(f"Zip archive not found: {zip_path}")
    if not zipfile.is_zipfile(zip_path):
        raise zipfile.BadZipFile(f"File is not a valid zip archive: {zip_path}")

    extract_to.mkdir(parents=True, exist_ok=True) # Ensure extraction directory exists

    try:
        with zipfile.ZipFile(zip_path, 'r') as zipf:
            members = zipf.infolist()
            total_files = len(members)
            logging.info(f"Extracting {total_files} members from {zip_path} to {extract_to}")

            if progress_callback:
                 # Extract all at once, only report start/end for simplicity here.
                 # For member-by-member progress, iterate and call zipf.extract()
                 progress_callback(0, total_files)

            zipf.extractall(path=extract_to)

            if progress_callback:
                progress_callback(total_files, total_files) # Report completion

            logging.info("Extraction complete.")

    except Exception as e:
        logging.error(f"Extraction failed: {e}", exc_info=True)
        # Note: Partially extracted files are not automatically cleaned up.
        raise # Re-raise the original exception