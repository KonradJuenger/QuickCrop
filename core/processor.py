from PIL import Image, ImageOps
import os

def process_image(source_path: str, normalized_crop: tuple, output_path: str, 
                  downsample: bool = True, target_res: int = 1080, res_mode: str = "Width",
                  rotation: float = 0, flip_h: bool = False, flip_v: bool = False):
    """
    Process image: Transform (Rotate/Flip), Crop, Resize, Save with Metadata.
    normalized_crop: (x, y, w, h) as float 0.0-1.0 relative to image size.
    """
    try:
        # Load Image
        image = Image.open(source_path)
        
        # Handle EXIF orientation and metadata preservation
        exif_obj = image.getexif()
        icc_profile = image.info.get('icc_profile')
        
        # Transpose based on EXIF tag (rotates pixels to upright)
        image = ImageOps.exif_transpose(image)
        
        # Strip orientation tag from EXIF object so it's not saved back.
        # Orientation is tag 274 (0x0112).
        if exif_obj and 0x0112 in exif_obj:
            del exif_obj[0x0112]
        
        # Apply Custom Transformations
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
        final_img = image.crop((left, top, right, bottom))
        
        # Final Dimensions calculation
        crop_w = right - left
        crop_h = bottom - top
        
        if crop_w <= 0 or crop_h <= 0:
            print(f"Invalid crop dimensions for {source_path}")
            return False
            
        if downsample:
            if res_mode == "Width":
                tw = int(target_res)
                th = int(tw * (crop_h / crop_w))
            else: # Height
                th = int(target_res)
                tw = int(th * (crop_w / crop_h))
            
            final_img = final_img.resize((tw, th), Image.Resampling.LANCZOS)
        
        # Save
        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        
        save_kwargs = {'quality': 100}
        if icc_profile:
            save_kwargs['icc_profile'] = icc_profile
        if exif_obj:
            save_kwargs['exif'] = exif_obj.tobytes()
            
        final_img.save(output_path, **save_kwargs)
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
    elif target_ratio_str == "4:3":
        target_aspect = 4 / 3
    elif target_ratio_str == "3:4":
        target_aspect = 3 / 4
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
