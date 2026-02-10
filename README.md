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
2. **Load Images**: Use the "Open Folder" button to select a directory containing your images.
3. **Select Ratio**: Choose between 1:1, 4:5, or other Instagram-ready ratios.
4. **Crop**: Drag and resize the crop rectangle. Use the spacebar to toggle between the edit view and the final preview.
5. **Save**: Click "Save" to export your cropped image.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
