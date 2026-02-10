from PyQt6.QtCore import QRunnable, pyqtSignal, QObject, QMetaObject, Qt, QSize, QRect, QRectF
from PyQt6.QtGui import QImage, QImageReader, QColor, QPainter, QImageIOHandler, QTransform

class LoaderSignals(QObject):
    finished = pyqtSignal(str, QImage)

class ThumbnailLoader(QRunnable):
    def __init__(self, path, size=(100, 100), crop_rect=None, rotation=0, flip_h=False, flip_v=False):
        super().__init__()
        self.path = path
        self.size = size
        self.crop_rect = crop_rect # (nx, ny, nw, nh)
        self.rotation = rotation
        self.flip_h = flip_h
        self.flip_v = flip_v
        self.signals = LoaderSignals()

    def run(self):
        try:
            reader = QImageReader(self.path)
            reader.setAutoTransform(True)
            
            orig_size = reader.size()
            
            # For thumbnails, we want them to be crisp. 
            # We'll load at 2x the requested size for high-DPI/sharper look.
            quality_multiplier = 2
            target_w = self.size[0] * quality_multiplier
            target_h = self.size[1] * quality_multiplier

            # If we have complex transformations (rotation, crop), load a reasonably large version
            # or the full image if it's not too massive.
            needs_full = self.crop_rect is not None or self.rotation != 0 or self.flip_h or self.flip_v
            
            if needs_full:
                image = reader.read()
                if image.isNull():
                    return

                # 1. Apply Flips and Rotation
                if self.flip_h or self.flip_v or self.rotation != 0:
                    t = QTransform()
                    # Flips
                    t.scale(-1 if self.flip_h else 1, -1 if self.flip_v else 1)
                    # Rotation (Qt is clockwise)
                    t.rotate(self.rotation)
                    
                    image = image.transformed(t, Qt.TransformationMode.SmoothTransformation)

                # 2. Apply Crop if specified
                if self.crop_rect:
                    w, h = image.width(), image.height()
                    nx, ny, nw, nh = self.crop_rect
                    
                    # Clamp crop to image bounds
                    rect = QRect(
                        int(max(0, nx * w)),
                        int(max(0, ny * h)),
                        int(min(w, nw * w)),
                        int(min(h, nh * h))
                    )
                    if rect.isValid():
                        image = image.copy(rect)

            else:
                # Optimized path for un-transformed thumbnails
                if orig_size.isValid():
                    scale_w = target_w / orig_size.width()
                    scale_h = target_h / orig_size.height()
                    scale = max(scale_w, scale_h) # Ensure we cover target size
                    
                    reader.setScaledSize(QSize(int(orig_size.width() * scale), int(orig_size.height() * scale)))
                image = reader.read()

            if image and not image.isNull():
                target_qsize = QSize(target_w, target_h)
                
                # Always scale to FILL (crop-to-fill)
                scaled_img = image.scaled(
                    target_qsize, 
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding, 
                    Qt.TransformationMode.SmoothTransformation
                )
                
                # Center crop to exact target size
                final_image = scaled_img.copy(
                    (scaled_img.width() - target_qsize.width()) // 2,
                    (scaled_img.height() - target_qsize.height()) // 2,
                    target_qsize.width(),
                    target_qsize.height()
                )
                
                try:
                    self.signals.finished.emit(self.path, final_image)
                except RuntimeError:
                    pass
                
        except Exception as e:
            print(f"Thumbnail error: {e}")
