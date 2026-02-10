# Quick Crop

Quick Crop is a powerful and lightweight desktop application designed for fast, interactive image cropping, specifically optimized for Instagram's aspect ratios. It features a modern, responsive UI and efficient batch processing capabilities.

## Features

- **Interactive Cropping**: Precise control over crop areas with real-time preview.
- **Instagram Optimized**: Pre-set aspect ratios (1:1, 4:5, 16:9) to match Instagram's requirements.
- **Batch Processing**: Easily switch between multiple images in a folder.
- **Modern UI**: Built with PyQt6 for a sleek and responsive experience.
- **Fast Performance**: Optimized image loading and processing using Pillow.

## Installation

### Using [uv](https://github.com/astral-sh/uv) (Recommended)

```bash
# Clone the repository
git clone https://github.com/yourusername/quick-crop.git
cd quick-crop

# Run the application (uv will handle dependencies)
uv run main.py
```

### Using pip

```bash
# Clone the repository
git clone https://github.com/yourusername/quick-crop.git
cd quick-crop

# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py
```

## Usage

1. **Launch**: Run `main.py`.
2. **Load Images**: Use the "Load Images" button to select files.
3. **Select Ratio**: Choose between 1:1, 4:5, or 9:16.
4. **Crop**: Drag and resize the crop rectangle. Use the spacebar to toggle between the edit view and the final preview.
5. **Process**: Click "Process All" to export all non-skipped images to the output folder.

## Distribution

To compile the application into a standalone executable (Windows) or app bundle (macOS):

### Using the build script (Recommended)

```bash
# This will use PyInstaller via uv to create a standalone build
uv run python build.py
```

The output will be located in the `dist/` directory:
- **Windows**: `dist/QuickCrop.exe`
- **macOS**: `dist/QuickCrop.app`

## License

- **QuickCrop Code**: Licensed under the MIT License.
- **Dependencies**: 
    - **PyQt6**: Licensed under [GPL v3](https://www.riverbankcomputing.com/software/pyqt/license).
    - **Pillow**: Licensed under [HPND](https://github.com/python-pillow/Pillow/blob/main/LICENSE).

*Note: When distributing binaries, ensure compliance with the GPL v3 license regarding the availability of source code.*
