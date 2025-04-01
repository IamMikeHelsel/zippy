#!/usr/bin/env python
# Main entry point for the zippy application
import sys
import logging
import os  # noqa: F401
import traceback  # noqa: F401
from pathlib import Path
from datetime import datetime
import argparse

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

def main():
    parser = argparse.ArgumentParser(description="Zippy - A compression utility")
    parser.add_argument("--api", action="store_true", help="Run as API server")
    parser.add_argument("--port", type=int, default=8000, help="Port for API server")
    parser.add_argument("--gui", action="store_true", help="Run as GUI application")
    
    # Parse only known args to handle the mode selection
    # This allows the rest of the args to be passed to the CLI module
    args, remaining_args = parser.parse_known_args()
    
    # Initialize logging
    log_file = setup_logging()
    logging.info(f"Application starting. Log file: {log_file}")
    
    try:
        if args.api:
            # Run as API server (to be implemented)
            from src.api import run_api_server
            logging.info(f"Starting API server on port {args.port}")
            run_api_server(port=args.port)
        elif args.gui:
            # Run as GUI application (existing functionality)
            from src.app import run_app
            logging.info("Starting GUI application")
            run_app()
        else:
            # Default: Run as CLI application
            from src.cli import main as cli_main
            # Reset sys.argv to only the remaining args for the CLI parser
            sys.argv = [sys.argv[0]] + remaining_args
            logging.info("Starting CLI application")
            return cli_main()
    except Exception as e:
        logging.critical(f"Failed to start application: {e}", exc_info=True)
        print(f"Critical error: {e}. See log file: {log_file}", file=sys.stderr)
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
