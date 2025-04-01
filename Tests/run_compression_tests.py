#!/usr/bin/env python
# Tests/run_compression_tests.py
"""
Script to run the comprehensive compression/decompression test suite.
This can be used to validate that compression and decompression are working 
correctly during development or as part of CI/CD pipelines.

Usage:
    python run_compression_tests.py [--generate-only] [--no-cleanup]
    
Options:
    --generate-only: Only generate test data without running tests
    --no-cleanup: Do not clean up test data after tests complete
"""
import os
import sys
import logging
import argparse
import tempfile
from pathlib import Path
import pytest

# Add the parent directory to the Python path so we can import test modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from Tests import test_data_generator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run compression and decompression tests with various file types."
    )
    parser.add_argument(
        "--generate-only", 
        action="store_true", 
        help="Only generate test data without running tests"
    )
    parser.add_argument(
        "--no-cleanup", 
        action="store_true", 
        help="Do not clean up test data after tests complete"
    )
    parser.add_argument(
        "--test-dir",
        type=str,
        default=None,
        help="Directory to store test data (defaults to a temporary directory)"
    )
    return parser.parse_args()

def main():
    """Main entry point."""
    args = parse_args()
    
    # Create test directory
    if args.test_dir:
        test_dir = Path(args.test_dir)
        test_dir.mkdir(parents=True, exist_ok=True)
    else:
        test_dir_parent = tempfile.mkdtemp(prefix="zippy_test_")
        test_dir = Path(test_dir_parent) / "test_data"
        
    test_dir = test_dir.resolve()  # Get absolute path
    logger.info(f"Using test directory: {test_dir}")
    
    # Generate test data
    logger.info("Generating test data...")
    test_files = test_data_generator.generate_all_test_files(test_dir, cleanup=True)
    logger.info(f"Generated {len(test_files)} test files and directories")
    
    if args.generate_only:
        logger.info("Test data generation complete. Skipping tests.")
        logger.info(f"Test data is available at: {test_dir}")
        return 0
    
    # Run the tests
    logger.info("Running compression tests...")
    test_module = str(Path(__file__).parent / "test_compression.py")
    
    # Use pytest to run the tests
    exit_code = pytest.main([
        "-v",
        test_module,
        "--no-header",
    ])
    
    # Clean up test data if requested
    if not args.no_cleanup and not args.test_dir:
        logger.info(f"Cleaning up test data at {test_dir_parent}")
        import shutil
        try:
            shutil.rmtree(test_dir_parent)
        except Exception as e:
            logger.warning(f"Failed to clean up test data: {e}")
    else:
        logger.info(f"Test data is available at: {test_dir}")
    
    return exit_code

if __name__ == "__main__":
    sys.exit(main())