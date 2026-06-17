#!/usr/bin/env python3
"""
Build script for creating the Stock Scanner desktop executable.
"""

import subprocess
import sys
from pathlib import Path

def main():
    """Build the executable using PyInstaller."""
    print("Building Stock Scanner Desktop Application")
    print("=" * 50)

    # Check if PyInstaller is installed
    try:
        import PyInstaller
    except ImportError:
        print("PyInstaller not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller>=6.0.0"])

    # Run PyInstaller
    print("Running PyInstaller...")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--clean",
        "--noconfirm",
        "build.spec"
    ]

    try:
        subprocess.check_call(cmd)
        print("\n✅ Build completed successfully!")
        print("Executable created: dist/StockScanner.exe")
        print("\nTo run the application:")
        print("1. Double-click StockScanner.exe")
        print("2. Or run: .\\dist\\StockScanner.exe")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Build failed: {e}")
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())