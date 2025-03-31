# zippy

A simple utility application built with Python and CustomTkinter to compress files/folders into `.zip` archives and uncompress existing `.zip` archives.

## Features

* Modern, dark user interface.
* Compress single files or entire directories.
* Uncompress `.zip` archives.
* Progress bar for operations.
* Status updates.

## Setup and Installation (using uv)

This project uses [uv](https://github.com/astral-sh/uv) as the package manager and requires **Python >= 3.13**.

1. **Install uv:**
    Follow the instructions on the [uv installation guide](https://github.com/astral-sh/uv#installation).

2. **Clone the repository:**

    ```bash
    git clone <your-repo-url>
    cd your_project_name
    ```

3. **Create a virtual environment:**

    ```bash
    uv venv
    ```

    *(This creates a `.venv` directory)*

4. **Activate the virtual environment:**
    * Linux/macOS: `source .venv/bin/activate`
    * Windows (Powershell): `.venv\Scripts\Activate.ps1`
    * Windows (CMD): `.venv\Scripts\activate.bat`

5. **Install dependencies (including test dependencies):**

    ```bash
    uv pip install -e ".[test]"
    ```

    *(`-e .` installs the project in editable mode)*

## Running the Application

With the virtual environment activated, run:

```bash
python -m src.main
```

Or use the console script (after installation):

```bash
zip-app
```

## Building a High-Performance Executable

The application can be compiled to C++ for better performance using Nuitka. This creates a standalone executable that doesn't require Python to be installed.

1. **Install build dependencies:**

   ```bash
   uv pip install -e ".[build]"
   ```

2. **Build the executable:**

   ```bash
   python build.py
   ```

   This will create a standalone distribution in the `dist` folder.

3. **Build options:**
   The build script supports several options:

   ```bash
   python build.py --onefile      # Create a single executable file
   python build.py --no-console   # Hide console window when running
   python build.py --icon=my_icon.ico  # Add a custom icon
   ```

4. **Using the compiled version:**
   After building, you can distribute the executable folder or single file (if `--onefile` was used) to users. They don't need to have Python installed to run your application.
