#!/usr/bin/env python
# src/cli.py
"""
Command Line Interface for the zippy application.
Provides command-line access to the core compression and decompression functionality.

Usage:
    zippy compress <source_path> [options]
    zippy uncompress <zip_path> [options]
    zippy --help

Examples:
    zippy compress file.txt                     # Compress a file to the default location
    zippy compress folder/ --output=folder.zip  # Compress a folder to a specific zip file
    zippy uncompress archive.zip                # Extract to a folder with the archive name
    zippy uncompress archive.zip --output=dir/  # Extract to a specific directory
"""

import argparse
import sys
import os
import logging
import time
from pathlib import Path
from typing import Optional, List, Tuple
import threading

from src import core
from src import utils

# Configure module logger
logger = logging.getLogger(__name__)

class ProgressReporter:
    """
    Reports progress for CLI operations with a real-time console progress bar.
    
    This class handles formatting and displaying progress information during
    compression and extraction operations, including time estimates and data rates.
    
    Attributes:
        quiet (bool): If True, suppresses all progress output
        no_progress (bool): If True, disables progress bar but allows other messages
        start_time (float): Timestamp when progress reporting started
        last_update_time (float): Timestamp of the last progress update
        last_percentage (int): Previously reported progress percentage
    """
    
    def __init__(self, quiet: bool = False, no_progress: bool = False):
        """
        Initialize a new progress reporter.
        
        Args:
            quiet: If True, suppresses all progress output
            no_progress: If True, disables progress bar but allows other messages
        """
        self.quiet = quiet
        self.no_progress = no_progress
        self.start_time = time.time()
        self.last_update_time = 0
        self.last_percentage = -1
    
    def update(self, current: int, total: int) -> None:
        """
        Update progress display with the current status.
        
        Displays a progress bar, percentage completion, data size information,
        processing speed, and estimated time remaining.
        
        Args:
            current: Current progress value (typically bytes processed)
            total: Total expected progress value (typically total bytes)
        
        Returns:
            None
        """
        if self.quiet or self.no_progress:
            return
            
        # Limit update frequency to avoid console flickering
        current_time = time.time()
        if (current_time - self.last_update_time < 0.1) and (current < total):
            return
            
        self.last_update_time = current_time
        
        # Calculate percentage
        percentage = int((current / max(1, total)) * 100)
        
        # Only update if percentage changed or complete
        if percentage == self.last_percentage and percentage < 100:
            return
            
        self.last_percentage = percentage
        
        # Calculate time elapsed
        elapsed = current_time - self.start_time
        
        # Calculate speed and ETA
        if elapsed > 0 and current > 0:
            speed = current / elapsed  # bytes per second
            eta = (total - current) / speed if speed > 0 else 0
            
            # Format units for display
            if current < 1024:
                current_str = f"{current} B"
                total_str = f"{total} B"
                speed_str = f"{speed:.1f} B/s"
            elif current < 1024*1024:
                current_str = f"{current/1024:.1f} KB"
                total_str = f"{total/1024:.1f} KB"
                speed_str = f"{speed/1024:.1f} KB/s"
            else:
                current_str = f"{current/(1024*1024):.1f} MB"
                total_str = f"{total/(1024*1024):.1f} MB"
                speed_str = f"{speed/(1024*1024):.1f} MB/s"
                
            # Format time remaining
            if eta > 60:
                eta_str = f"{int(eta/60)}m {int(eta%60)}s"
            else:
                eta_str = f"{int(eta)}s"
                
            # Create progress bar (50 chars wide)
            bar_width = 40
            filled_width = int(percentage / 100 * bar_width)
            bar = "█" * filled_width + "░" * (bar_width - filled_width)
            
            # Print progress
            sys.stdout.write(f"\r[{bar}] {percentage}% | {current_str}/{total_str} | {speed_str} | ETA: {eta_str}")
            
            # Clear the line if complete
            if current >= total:
                sys.stdout.write(" - Done!")
                
            sys.stdout.flush()
            
            # Print newline if complete
            if current >= total:
                print()
        else:
            # Simpler output if we can't calculate meaningful stats
            sys.stdout.write(f"\r[{'█' * int(percentage/2)}{'░' * (50-int(percentage/2))}] {percentage}%")
            sys.stdout.flush()
            if current >= total:
                print(" - Done!")


def setup_logging(verbose: bool, quiet: bool) -> None:
    """Configure logging level based on verbosity."""
    log_level = logging.WARNING  # Default level
    
    if verbose:
        log_level = logging.DEBUG
    elif quiet:
        log_level = logging.ERROR
    
    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Set up specific logger for this module
    logger.setLevel(log_level)


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    # Create main parser
    parser = argparse.ArgumentParser(
        description="Command line interface for zippy - a high-performance file compression utility",
        epilog="For more information, visit the GitHub repository."
    )
    
    # Add common arguments
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose output'
    )
    parser.add_argument(
        '-q', '--quiet',
        action='store_true',
        help='Suppress all output except errors'
    )
    parser.add_argument(
        '--no-progress',
        action='store_true',
        help='Disable progress bar'
    )
    
    # Create subparsers for commands
    subparsers = parser.add_subparsers(
        dest='command',
        title='commands',
        help='Command to execute'
    )
    
    # Create the compress command parser
    compress_parser = subparsers.add_parser(
        'compress',
        help='Compress a file or directory'
    )
    compress_parser.add_argument(
        'source',
        help='Path to the file or directory to compress'
    )
    compress_parser.add_argument(
        '-o', '--output',
        help='Path for the output zip file (default: auto-generated from source)'
    )
    compress_parser.add_argument(
        '-l', '--level',
        type=int,
        choices=range(0, 10),
        default=9,
        help='Compression level (0-9, where 9 is maximum compression)'
    )
    
    # Create the uncompress command parser
    uncompress_parser = subparsers.add_parser(
        'uncompress',
        help='Extract a zip archive'
    )
    uncompress_parser.add_argument(
        'archive',
        help='Path to the zip archive to extract'
    )
    uncompress_parser.add_argument(
        '-o', '--output',
        help='Directory to extract files to (default: directory named after the archive)'
    )
    
    # Parse arguments
    return parser.parse_args()


def compress_files(args: argparse.Namespace) -> int:
    """Compress files based on command line arguments."""
    source_path = args.source
    
    # Validate source path
    if not os.path.exists(source_path):
        logger.error(f"Source path does not exist: {source_path}")
        return 1
    
    # Determine output path
    if args.output:
        output_path = args.output
        # Ensure it has .zip extension
        if not output_path.lower().endswith('.zip'):
            output_path += '.zip'
    else:
        # Auto-generate output path based on source
        output_path = str(utils.get_default_zip_path(source_path))
    
    # Ensure output directory exists
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Set up progress reporter and cancellation
    progress_reporter = ProgressReporter(quiet=args.quiet, no_progress=args.no_progress)
    cancel_event = threading.Event()
    
    # Register signal handlers for graceful termination
    def signal_handler(sig, frame):
        logger.info("Received interrupt signal, cancelling operation...")
        cancel_event.set()
    
    try:
        import signal
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    except (ImportError, AttributeError):
        # Signal module might not be available on all platforms
        pass
    
    try:
        # Display compression info
        if not args.quiet:
            if os.path.isfile(source_path):
                file_size = os.path.getsize(source_path)
                source_type = "file"
            else:
                file_size = sum(
                    os.path.getsize(os.path.join(root, file))
                    for root, _, files in os.walk(source_path)
                    for file in files
                )
                source_type = "directory"
            
            print(f"Compressing {source_type} ({file_size/1024/1024:.1f} MB) to '{output_path}'")
            print(f"Compression level: {args.level}")
        
        # Start compression
        core.compress_item(
            source_path,
            output_path,
            progress_callback=progress_reporter.update,
            cancel_event=cancel_event,
            compression_level=args.level
        )
        
        # Report success
        if not args.quiet:
            if os.path.exists(output_path):
                zip_size = os.path.getsize(output_path)
                compression_ratio = (1 - (zip_size / max(1, file_size))) * 100
                print(f"Successfully created '{output_path}' ({zip_size/1024/1024:.1f} MB)")
                print(f"Compression ratio: {compression_ratio:.1f}%")
            else:
                print(f"Operation completed, but output file was not created: {output_path}")
        
        return 0
    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        cancel_event.set()
        return 130  # Standard exit code for SIGINT
    except Exception as e:
        logger.error(f"Compression failed: {e}", exc_info=args.verbose)
        if not args.quiet:
            print(f"Error: {e}")
        return 1


def uncompress_files(args: argparse.Namespace) -> int:
    """Extract files from an archive based on command line arguments."""
    archive_path = args.archive
    
    # Validate archive path
    if not os.path.isfile(archive_path):
        logger.error(f"Archive file does not exist: {archive_path}")
        return 1
    
    # Determine output directory
    if args.output:
        extract_dir = args.output
    else:
        # Use archive name as directory name
        extract_dir = os.path.splitext(os.path.basename(archive_path))[0]
    
    # Set up progress reporter and cancellation
    progress_reporter = ProgressReporter(quiet=args.quiet, no_progress=args.no_progress)
    cancel_event = threading.Event()
    
    # Register signal handlers for graceful termination
    def signal_handler(sig, frame):
        logger.info("Received interrupt signal, cancelling operation...")
        cancel_event.set()
    
    try:
        import signal
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    except (ImportError, AttributeError):
        # Signal module might not be available on all platforms
        pass
    
    try:
        # Display extraction info
        if not args.quiet:
            archive_size = os.path.getsize(archive_path)
            print(f"Extracting '{archive_path}' ({archive_size/1024/1024:.1f} MB) to '{extract_dir}'")
        
        # Start extraction
        core.uncompress_archive(
            archive_path,
            extract_dir,
            progress_callback=progress_reporter.update,
            cancel_event=cancel_event
        )
        
        # Report success
        if not args.quiet:
            print(f"Successfully extracted files to '{extract_dir}'")
        
        return 0
    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        cancel_event.set()
        return 130  # Standard exit code for SIGINT
    except Exception as e:
        logger.error(f"Extraction failed: {e}", exc_info=args.verbose)
        if not args.quiet:
            print(f"Error: {e}")
        return 1


def main() -> int:
    """Main entry point for the CLI."""
    args = parse_arguments()
    
    # Set up logging based on verbosity level
    setup_logging(args.verbose, args.quiet)
    
    # Handle commands
    if args.command == 'compress':
        return compress_files(args)
    elif args.command == 'uncompress':
        return uncompress_files(args)
    else:
        print("Please specify a command: compress or uncompress")
        print("Use --help for more information")
        return 1


if __name__ == "__main__":
    sys.exit(main())