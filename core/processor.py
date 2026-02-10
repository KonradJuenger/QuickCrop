from PIL import Image, ImageOps
import os

def process_image(source_path: str, normalized_crop: tuple, output_path: str, output_width: int, 
                  rotation: float = 0, flip_h: bool = False, flip_v: bool = False):
    """
    Process image: Transform (Rotate/Flip), Crop, Resize, Save with Metadata.
    normalized_crop: (x, y, w, h) as float 0.0-1.0 relative to image size.
    """
    try:
        # Load Image
        image = Image.open(source_path)
        
        # Handle EXIF orientation (this returns a copy, so metadata might be lost)
        # We need to preserve original info
        original_info = image.info
        exif = original_info.get('exif')
        icc_profile = original_info.get('icc_profile')
        
        # Transpose based on EXIF tag 274
        image = ImageOps.exif_transpose(image)
        
        # Apply Custom Transformations
        # Order: Flip then Rotate (to match QGraphicsItem behavior if possible, 
        # but in our case simplified: we just want it to match the view)
        if flip_h:
            image = image.transpose(Image.FLIP_LEFT_RIGHT)
        if flip_v:
            image = image.transpose(Image.FLIP_TOP_BOTTOM)
            
        if rotation != 0:
            # Qt is clockwise, PIL is counter-clockwise
            image = image.rotate(-rotation, expand=True)

        # Calculate crop pixels
        orig_w, orig_h = image.size
        nx, ny, nw, nh = normalized_crop
        
        left = int(nx * orig_w)
        top = int(ny * orig_h)
        right = int((nx + nw) * orig_w)
        bottom = int((ny + nh) * orig_h)
        
        # Clamp
        left = max(0, left)
        top = max(0, top)
        right = min(orig_w, right)
        bottom = min(orig_h, bottom)
        
        # Crop
        cropped_img = image.crop((left, top, right, bottom))
        
        # Resize - Calculate height to maintain crop aspect ratio
        crop_w = right - left
        crop_h = bottom - top
        
        if crop_w <= 0 or crop_h <= 0:
            print(f"Invalid crop dimensions for {source_path}")
            return False
            
        target_w = int(output_width)
        target_h = int(target_w * (crop_h / crop_w))
        
        resized_img = cropped_img.resize((target_w, target_h), Image.Resampling.LANCZOS)
        
        # Save
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        save_kwargs = {'quality': 95}
        if icc_profile:
            save_kwargs['icc_profile'] = icc_profile
        if exif:
            save_kwargs['exif'] = exif
            
        resized_img.save(output_path, **save_kwargs)
        return True
            
    except Exception as e:
        print(f"Error processing {source_path}: {e}")
        return False


def calculate_default_crop(image_width: int, image_height: int, target_ratio_str: str) -> tuple:
    """
    Calculate default normalized crop rect (x, y, w, h) for a given aspect ratio.
    """
    if target_ratio_str == "1:1":
        target_aspect = 1.0
    elif target_ratio_str == "4:5":
        target_aspect = 0.8
    elif target_ratio_str == "9:16":
        target_aspect = 9 / 16
    else:
        target_aspect = 1.0

    img_ratio = image_width / image_height

    draw_w = 1.0
    draw_h = 1.0

    if img_ratio > target_aspect:
        # Image is wider than target: fit height, crop width
        draw_w = target_aspect / img_ratio
    else:
        # Image is taller than target: fit width, crop height
        draw_h = img_ratio / target_aspect

    dx = (1.0 - draw_w) / 2
    dy = (1.0 - draw_h) / 2
    
    return (dx, dy, draw_w, draw_h)
