#!/usr/bin/env python
# Main entry point for the zippy application
import sys
import logging
import os
import traceback
from pathlib import Path
from datetime import datetime

# Configure logging before importing any other modules
def setup_logging():
    """Set up logging to both console and file."""
    log_dir = Path.home() / "zippy_logs"
    log_dir.mkdir(exist_ok=True)
    
    # Create a unique log file name with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"zippy_{timestamp}.log"
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # File handler with detailed formatting
    file_handler = logging.FileHandler(log_file)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)
    
    # Console handler with simpler formatting
    console_handler = logging.StreamHandler(sys.stdout)
    console_formatter = logging.Formatter('%(levelname)s: %(message)s')
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    return log_file

# Set up exception hook to log unhandled exceptions
def handle_exception(exc_type, exc_value, exc_traceback):
    """Log unhandled exceptions."""
    if issubclass(exc_type, KeyboardInterrupt):
        # Don't log keyboard interrupt
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    
    logging.critical("Unhandled exception:", exc_info=(exc_type, exc_value, exc_traceback))
    
    # Also log to stderr
    print("Critical error occurred. Check log file for details.", file=sys.stderr)

# Install exception handler
sys.excepthook = handle_exception

# Initialize logging
log_file = setup_logging()
logging.info(f"Application starting. Log file: {log_file}")

try:
    from src.main import run_app

    def main():
        try:
            logging.info("Starting main application")
            run_app()
        except Exception as e:
            logging.error(f"Error in main application: {e}", exc_info=True)
            raise

    if __name__ == "__main__":
        main()
except Exception as e:
    logging.critical(f"Failed to start application: {e}", exc_info=True)
    print(f"Critical error: {e}. See log file: {log_file}", file=sys.stderr)
    sys.exit(1)
