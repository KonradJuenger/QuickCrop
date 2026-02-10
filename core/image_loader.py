import os

VALID_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.tiff', '.tif')

def scan_directory(directory: str):
    images = []
    if not os.path.isdir(directory):
        return images
        
    for entry in os.scandir(directory):
        if entry.is_file() and entry.name.lower().endswith(VALID_EXTENSIONS):
            images.append(entry.path)
            
    return sorted(images)
