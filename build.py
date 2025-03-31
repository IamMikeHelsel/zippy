#!/usr/bin/env python
"""
Build script for compiling the zippy application to C++ using Nuitka.

This script provides options for compiling the application into a standalone
executable with optimized performance.

Usage:
    python build.py [options]

Options:
    --standalone      Create a standalone executable (default)
    --onefile         Create a single executable file that contains all dependencies
    --no-console      Hide the console window when running the application
    --icon=FILE       Specify an icon file for the executable
    --code-sign       Sign the Windows executable with a code signing certificate
    --certificate     Path to the code signing certificate (required with --code-sign)
    --password        Password for the certificate (if needed)
    --test            Run tests before building
    --clean           Clean build directory before starting
    --help            Show this help message
"""

import os
import sys
import subprocess
import argparse
import platform
import shutil
import tempfile
import time
from pathlib import Path


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Build the zippy application with Nuitka"
    )
    parser.add_argument(
        "--standalone",
        action="store_true",
        default=True,
        help="Create a standalone executable (default)",
    )
    parser.add_argument(
        "--onefile",
        action="store_true",
        help="Create a single executable file that contains all dependencies",
    )
    parser.add_argument(
        "--no-console",
        action="store_true",
        help="Hide the console window when running the application",
    )
    parser.add_argument(
        "--icon",
        type=str,
        help="Specify an icon file for the executable",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="dist",
        help="Specify the output directory for the build",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=0,  # 0 means auto-detect
        help="Number of parallel jobs to use for the build (0 for auto)",
    )
    parser.add_argument(
        "--show-progress",
        action="store_true",
        default=True,
        help="Show build progress",
    )
    # Add the new arguments
    parser.add_argument(
        "--code-sign",
        action="store_true",
        help="Sign the Windows executable with a code signing certificate",
    )
    parser.add_argument(
        "--certificate",
        type=str,
        help="Path to the code signing certificate (required with --code-sign)",
    )
    parser.add_argument(
        "--password",
        type=str,
        help="Password for the certificate (if needed)",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run tests before building",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean build directory before starting",
    )
    parser.add_argument(
        "--optimizations",
        choices=["size", "speed", "balanced"],
        default="balanced",
        help="Optimization strategy: size, speed, or balanced (default)",
    )

    return parser.parse_args()


def run_tests():
    """Run the test suite before building.

    Returns:
        bool: True if tests passed, False otherwise.
    """
    print("Running tests before building...")
    try:
        # Run pytest with minimal output but showing test failures
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-xvs", "Tests/"],
            check=False,  # Don't raise exception on test failure, handle manually
        )

        if result.returncode != 0:
            print("❌ Tests failed! Build aborted.")
            return False

        print("✅ All tests passed!")
        return True
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        return False


def clean_build_directory(output_dir):
    """Clean the build directory before starting.

    Args:
        output_dir: Path to the output directory to clean.
    """
    print(f"Cleaning build directory: {output_dir}")

    try:
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
            print(f"✅ Successfully removed {output_dir}")
    except Exception as e:
        print(f"⚠️ Warning: Could not clean directory: {e}")


def sign_windows_executable(executable_path, certificate_path, password=None):
    """Sign a Windows executable with a code signing certificate.

    Args:
        executable_path: Path to the executable to sign.
        certificate_path: Path to the certificate file (.pfx).
        password: Optional password for the certificate.

    Returns:
        bool: True if signing succeeded, False otherwise.
    """
    print(f"Signing executable: {executable_path}")

    if not os.path.exists(executable_path):
        print(f"❌ Error: Executable not found: {executable_path}")
        return False

    if not os.path.exists(certificate_path):
        print(f"❌ Error: Certificate not found: {certificate_path}")
        return False

    # Build signtool command
    signtool = "signtool.exe"  # Assume in PATH, or provide full path

    cmd = [
        signtool,
        "sign",
        "/f",
        certificate_path,
        "/tr",
        "http://timestamp.digicert.com",
        "/td",
        "sha256",
        "/fd",
        "sha256",
    ]

    # Add password if provided
    if password:
        cmd.extend(["/p", password])

    # Add the executable to sign
    cmd.append(executable_path)

    try:
        result = subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        print("✅ Executable signed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Signing failed: {e}")
        print(f"Output: {e.stdout}")
        print(f"Error: {e.stderr}")
        return False
    except Exception as e:
        print(f"❌ Error during signing: {e}")
        return False


def get_platform_optimizations(platform_name, optimization_strategy):
    """Get platform-specific optimization flags.

    Args:
        platform_name: The platform name (Windows, Darwin, Linux).
        optimization_strategy: Optimization strategy (size, speed, balanced).

    Returns:
        list: List of platform-specific optimization flags.
    """
    common_flags = []

    # Common optimization flags based on strategy
    if optimization_strategy == "size":
        common_flags.extend(
            [
                "--noinclude-default-mode=nofollow",  # Don't include unused modules
                "--lto=yes",  # Link-time optimization
                "--static-libpython=no",  # Don't statically link Python (smaller)
                "--disable-console",  # Disable console (Windows)
                "--python-flag=no_site",  # Don't include site.py
                "--python-flag=no_warnings",  # Don't include warnings
                "--remove-output",  # Remove output if exists
            ]
        )
    elif optimization_strategy == "speed":
        common_flags.extend(
            [
                "--lto=yes",  # Link-time optimization
                "--static-libpython=yes",  # Statically link Python (faster)
                "--python-flag=no_asserts",  # Disable assertions (speed)
                "--remove-output",  # Remove output if exists
            ]
        )
    else:  # balanced (default)
        common_flags.extend(
            [
                "--lto=yes",  # Link-time optimization
                "--static-libpython=no",  # Don't statically link Python
                "--remove-output",  # Remove output if exists
            ]
        )

    # Platform-specific flags
    if platform_name == "Windows":
        common_flags.append("--msvc=latest")  # Use MSVC on Windows

        # Add company information
        common_flags.extend(
            [
                "--windows-company-name=ZippyApp",
                "--windows-product-name=Zippy",
                "--windows-file-description=File compression utility",
                "--windows-file-version=1.0.0.0",
                "--windows-product-version=1.0.0.0",
            ]
        )

    elif platform_name == "Darwin":  # macOS
        common_flags.extend(
            [
                "--macos-create-app-bundle",  # Create .app bundle on macOS
                "--macos-app-name=Zippy",  # App name in the bundle
                "--macos-app-icon=resources/zippy.icns",  # App icon (if available)
            ]
        )

    elif platform_name == "Linux":
        common_flags.extend(
            [
                "--linux-onefile-icon=resources/zippy.png",  # Icon for Linux
            ]
        )

    return common_flags


def build_application(args):
    """Build the zippy application with Nuitka."""
    # Run tests if requested
    if args.test:
        if not run_tests():
            sys.exit(1)  # Exit if tests failed

    # Clean build directory if requested
    if args.clean:
        clean_build_directory(args.output_dir)

    print(f"Building zippy with Nuitka...")

    # Base directory
    base_dir = Path(__file__).parent
    src_dir = base_dir / "src"
    main_script = src_dir / "main.py"  # Use the actual file path
    output_dir = base_dir / args.output_dir

    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # Build the Nuitka command
    cmd = [
        sys.executable,
        "-m",
        "nuitka",
        "--follow-imports",
    ]

    # Add options based on arguments
    if args.standalone:
        cmd.append("--standalone")

    if args.onefile:
        cmd.append("--onefile")

    if args.no_console:
        cmd.append("--windows-disable-console")

    if args.icon:
        cmd.append(f"--windows-icon-from-ico={args.icon}")

    if args.jobs != 0:
        cmd.append(f"--jobs={args.jobs}")

    if args.show_progress:
        cmd.append("--show-progress")

    # Add optimization flags
    cmd.extend(
        [
            "--assume-yes-for-downloads",  # Auto-download needed components
            "--enable-plugin=tk-inter",  # Optimize Tkinter usage
            "--enable-plugin=numpy",  # Support NumPy if used
            "--include-package=src",  # Include our source code
            "--include-package=customtkinter",  # Include CustomTkinter
            "--include-package-data=customtkinter",  # Include CustomTkinter resources
            "--include-package=psutil",  # Include psutil
            "--output-dir=" + str(output_dir),
            "--remove-output",  # Remove output if exists
            f"--output-filename=zippy{'_onefile' if args.onefile else ''}",
        ]
    )

    # Add platform-specific optimizations
    platform_name = platform.system()
    platform_flags = get_platform_optimizations(platform_name, args.optimizations)
    cmd.extend(platform_flags)

    # Add entry point (main script file)
    cmd.append(str(main_script))  # Pass the path to the main script file

    # Run the Nuitka compiler
    print(f"Running command: {' '.join(cmd)}")
    try:
        start_time = time.time()

        # Run the build process
        subprocess.run(cmd, check=True)

        build_time = time.time() - start_time
        print(
            f"✅ Build completed successfully in {build_time:.1f} seconds! Output in {output_dir}"
        )

        # Code signing (Windows only)
        if args.code_sign and platform_name == "Windows":
            if not args.certificate:
                print("❌ Error: Certificate path required for code signing")
                return

            # Find the executable to sign (differs between onefile and standalone)
            if args.onefile:
                executable_path = output_dir / "zippy_onefile.exe"
            else:
                executable_path = output_dir / "zippy.dist" / "zippy.exe"

            if not executable_path.exists():
                print(f"❌ Error: Cannot find executable to sign at {executable_path}")
                return

            # Sign the executable
            sign_windows_executable(executable_path, args.certificate, args.password)

    except subprocess.CalledProcessError as e:
        print(f"❌ Build failed with error: {e}")
        sys.exit(1)


def main():
    """Main entry point."""
    print(f"Zippy Build Tool (Python {sys.version.split()[0]} on {platform.system()})")

    args = parse_args()
    build_application(args)


if __name__ == "__main__":
    main()
