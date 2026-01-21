# Ship Port Distance Helper

Tkinter tool to analyze missing distances between load and discharge ports.

## Features

-   Load Ports CSV and Complete Distances CSV
-   Optional inclusion of inactive ports
-   Progress bar for analysis
-   Summary + missing distances output
-   Copy to clipboard or export as TSV

## Requirements

-   Python 3.10+ (3.11+ recommended)

## Run locally

```bash
python distances-analyzer-gui.py
```

## Generate an EXE (Windows)

The most reliable way is to build on Windows.

1. Create a virtual environment and install PyInstaller:

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install --upgrade pip
pip install pyinstaller
```

2. Build the EXE (console hidden):

```bash
# Windows (PowerShell / CMD - use ; as separator)
pyinstaller --noconsole --onefile --icon danalyser-icon.png --add-data "simple-distances-analyzer.py;." --add-data "complex-distances-analyzer.py;." --hidden-import tkinter.filedialog --hidden-import tkinter.messagebox --hidden-import tkinter.ttk distances-analyzer-gui.py
```

3. The EXE will be at:

```
dist/main.exe
```

### Notes

-   Building a Windows `.exe` from macOS is not supported by PyInstaller.
-   If you want a macOS `.app`, you can run:

```bash
# macOS (zsh - use : as separator)
pyinstaller --windowed --onefile --icon danalyser-icon.png --add-data "simple-distances-analyzer.py:." --add-data "complex-distances-analyzer.py:." --hidden-import tkinter.filedialog --hidden-import tkinter.messagebox --hidden-import tkinter.ttk distances-analyzer-gui.py
```

This will generate a macOS app bundle in `dist/`.

- Inside ressources folder, we can find some files that helped us build complex analyzer; the code behind our real distance generator found, typescript version that we translated to py.
