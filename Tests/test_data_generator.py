# Tests/test_data_generator.py
"""
Utility module for generating test data for zippy compression/decompression tests.
This module creates specialized test files with various characteristics to ensure
thorough testing of the compression and decompression functionality.
"""
import os
import random
import string
import struct
from pathlib import Path
import logging
import shutil

logger = logging.getLogger(__name__)

# File size constants
KB = 1024
MB = 1024 * KB

def create_text_file(path, size_bytes, compressibility="medium"):
    """
    Create a text file with specified size and compressibility characteristics.
    
    Args:
        path: Path where the file should be created
        size_bytes: Size of the file in bytes
        compressibility: How compressible the content should be
            "high" - very repetitive content, easily compressed
            "medium" - somewhat repetitive, averagely compressed
            "low" - random content, difficult to compress
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Creating {size_bytes/KB:.1f} KB text file at {path} with {compressibility} compressibility")
    
    with open(path, "w") as f:
        remaining = size_bytes
        chunk_size = min(10 * KB, size_bytes)
        
        if compressibility == "high":
            # Very compressible: repeat the same pattern
            pattern = "".join(random.choices(string.ascii_letters, k=100))
            while remaining > 0:
                write_size = min(chunk_size, remaining)
                repetitions = write_size // len(pattern) + 1
                f.write(pattern * repetitions)
                remaining -= write_size
                
        elif compressibility == "medium":
            # Medium compressibility: some repeated words with variations
            word_list = ["".join(random.choices(string.ascii_letters, k=random.randint(3, 10))) 
                        for _ in range(100)]
            
            while remaining > 0:
                write_size = min(chunk_size, remaining)
                text = ""
                while len(text) < write_size:
                    text += random.choice(word_list) + " "
                f.write(text[:write_size])
                remaining -= write_size
                
        else:  # low compressibility
            # Generate random content that's hard to compress
            while remaining > 0:
                write_size = min(chunk_size, remaining)
                chars = random.choices(string.printable, k=write_size)
                f.write("".join(chars))
                remaining -= write_size

def create_binary_file(path, size_bytes, pattern_type="random"):
    """
    Create a binary file with the specified size and pattern type.
    
    Args:
        path: Path where the file should be created
        size_bytes: Size of the file in bytes
        pattern_type: Type of binary data
            "random" - random binary data
            "structured" - structured binary data with patterns
            "zeros" - all zeros (highly compressible)
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Creating {size_bytes/KB:.1f} KB binary file at {path} with {pattern_type} pattern")
    
    with open(path, "wb") as f:
        remaining = size_bytes
        chunk_size = min(10 * KB, size_bytes)
        
        if pattern_type == "zeros":
            # All zeros - extremely compressible
            while remaining > 0:
                write_size = min(chunk_size, remaining)
                f.write(b'\x00' * write_size)
                remaining -= write_size
                
        elif pattern_type == "structured":
            # Structured data that resembles file formats
            while remaining > 0:
                if remaining < 8:
                    f.write(b'\x00' * remaining)
                    break
                    
                # Write some structured data with headers and repeating patterns
                header = struct.pack(">I", random.randint(0, 0xFFFFFFFF))
                size = min(remaining - 8, random.randint(20, chunk_size))
                size_bytes = struct.pack(">I", size)
                
                f.write(header)
                f.write(size_bytes)
                
                # Write the data section with some pattern
                pattern = bytes([random.randint(0, 255) for _ in range(min(20, size))])
                repetitions = (size // len(pattern)) + 1
                f.write((pattern * repetitions)[:size])
                
                remaining -= (8 + size)
        else:
            # Random binary data - not very compressible
            while remaining > 0:
                write_size = min(chunk_size, remaining)
                f.write(bytes([random.randint(0, 255) for _ in range(write_size)]))
                remaining -= write_size

def create_nested_directory_structure(base_path, max_depth=5, files_per_dir=3, 
                                     max_file_size_kb=10, include_empty_dirs=True):
    """
    Create a nested directory structure with files.
    
    Args:
        base_path: Base directory path
        max_depth: Maximum directory nesting depth
        files_per_dir: Number of files to create per directory
        max_file_size_kb: Maximum file size in KB
        include_empty_dirs: Whether to include empty directories
    
    Returns:
        Path to the created directory structure
    """
    base_path = Path(base_path)
    base_path.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Creating nested directory structure at {base_path}")
    
    def _create_level(current_path, current_depth):
        # Create files in this directory
        for i in range(files_per_dir):
            file_name = f"file_{current_depth}_{i}.txt"
            file_size = random.randint(1, max_file_size_kb) * KB
            create_text_file(
                current_path / file_name,
                file_size,
                compressibility=random.choice(["high", "medium", "low"])
            )
        
        # Create an empty file occasionally
        if random.random() < 0.3:
            empty_file = current_path / f"empty_{current_depth}.txt"
            empty_file.touch()
        
        # Don't go deeper than max_depth
        if current_depth >= max_depth:
            return
            
        # Create subdirectories at this level
        num_subdirs = random.randint(1, 3)
        for i in range(num_subdirs):
            subdir_path = current_path / f"level_{current_depth}_dir_{i}"
            subdir_path.mkdir(exist_ok=True)
            
            # Recursively populate subdirectory
            _create_level(subdir_path, current_depth + 1)
        
        # Create an empty directory occasionally
        if include_empty_dirs and random.random() < 0.3:
            empty_dir = current_path / f"empty_dir_{current_depth}"
            empty_dir.mkdir(exist_ok=True)

    # Start the recursive creation
    _create_level(base_path, 1)
    return base_path

def create_special_filename_files(base_path):
    """
    Create files with special characters in names.
    
    Args:
        base_path: Base directory path
    
    Returns:
        Dictionary mapping description to file path
    """
    base_path = Path(base_path)
    base_path.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Creating files with special names at {base_path}")
    
    files = {}
    
    # File with spaces
    space_file = base_path / "file with spaces.txt"
    space_file.write_text("This file has spaces in its name")
    files["spaces"] = space_file
    
    # File with unicode characters
    unicode_file = base_path / "üñíçødê_file_名前.txt"
    unicode_file.write_text("This file has unicode characters in its name")
    files["unicode"] = unicode_file
    
    # File with special chars
    special_file = base_path / "special_$#@!%^&()_file.txt"
    special_file.write_text("This file has special characters in its name")
    files["special"] = special_file
    
    # Very long filename
    long_name = "very_" + "long_" * 20 + "filename.txt"
    long_file = base_path / long_name
    long_file.write_text("This file has a very long name")
    files["long"] = long_file
    
    return files

def create_large_test_file(path, size_mb=10):
    """
    Create a large text file for testing chunked processing.
    
    Args:
        path: Path where the file should be created
        size_mb: Size of the file in MB
    
    Returns:
        Path to the created file
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    size_bytes = size_mb * MB
    logger.info(f"Creating large {size_mb}MB test file at {path}")
    
    # Create a file with a mix of random and repeating patterns
    # This makes it somewhat compressible but still large enough to test chunking
    with open(path, "w") as f:
        remaining = size_bytes
        chunk_size = 1 * MB
        
        # Generate some base patterns to repeat
        patterns = [
            "".join(random.choices(string.ascii_letters + string.digits, k=1000))
            for _ in range(10)
        ]
        
        while remaining > 0:
            # Use a mix of patterns and random data
            if random.random() < 0.7:
                # Use repeating pattern (more compressible)
                pattern = random.choice(patterns)
                repetitions = min(chunk_size, remaining) // len(pattern) + 1
                data = pattern * repetitions
            else:
                # Use random data (less compressible)
                chars = random.choices(string.printable, k=min(chunk_size, remaining))
                data = "".join(chars)
                
            f.write(data[:min(chunk_size, remaining)])
            remaining -= min(chunk_size, remaining)
    
    return path

def generate_all_test_files(base_dir, cleanup=True):
    """
    Generate all test files in the specified directory.
    
    Args:
        base_dir: Directory where test files should be created
        cleanup: Whether to clean up any existing files first
    
    Returns:
        Dictionary with paths to all test files and directories
    """
    base_path = Path(base_dir)
    
    if cleanup and base_path.exists():
        logger.info(f"Cleaning up existing test data at {base_path}")
        shutil.rmtree(base_path, ignore_errors=True)
    
    base_path.mkdir(parents=True, exist_ok=True)
    
    # Dictionary to store all test file references
    test_files = {}
    
    # Create text files with different compressibility
    text_files_dir = base_path / "text_files"
    text_files_dir.mkdir(exist_ok=True)
    
    test_files["high_compress_1k"] = create_text_file(text_files_dir / "high_compress_1k.txt", 1 * KB, "high")
    test_files["medium_compress_10k"] = create_text_file(text_files_dir / "medium_compress_10k.txt", 10 * KB, "medium")
    test_files["low_compress_100k"] = create_text_file(text_files_dir / "low_compress_100k.txt", 100 * KB, "low")
    
    # Create binary files
    binary_files_dir = base_path / "binary_files"
    binary_files_dir.mkdir(exist_ok=True)
    
    test_files["zeros_1mb"] = create_binary_file(binary_files_dir / "zeros_1mb.bin", 1 * MB, "zeros")
    test_files["structured_binary_50k"] = create_binary_file(binary_files_dir / "structured_50k.bin", 50 * KB, "structured")
    test_files["random_binary_100k"] = create_binary_file(binary_files_dir / "random_100k.bin", 100 * KB, "random")
    
    # Create a large file for testing chunking
    large_file_dir = base_path / "large_files"
    large_file_dir.mkdir(exist_ok=True)
    test_files["large_file_10mb"] = create_large_test_file(large_file_dir / "large_10mb.txt", 10)
    
    # Create nested directory structure
    nested_dir = base_path / "nested_directory"
    test_files["nested_directory"] = create_nested_directory_structure(nested_dir)
    
    # Create files with special names
    special_names_dir = base_path / "special_names"
    special_name_files = create_special_filename_files(special_names_dir)
    test_files.update({f"special_name_{k}": v for k, v in special_name_files.items()})
    
    # Create a few tiny files
    tiny_files_dir = base_path / "tiny_files"
    tiny_files_dir.mkdir(exist_ok=True)
    
    empty_file = tiny_files_dir / "empty.txt"
    empty_file.touch()
    test_files["empty_file"] = empty_file
    
    one_byte_file = tiny_files_dir / "one_byte.txt"
    with open(one_byte_file, "w") as f:
        f.write("A")
    test_files["one_byte_file"] = one_byte_file
    
    return test_files

if __name__ == "__main__":
    # When run directly, this will generate test data in the current directory
    logging.basicConfig(level=logging.INFO)
    test_files = generate_all_test_files("./test_data")
    logger.info(f"Generated {len(test_files)} test files and directories")