from PyQt6.QtCore import QRunnable, pyqtSignal, QObject, QMetaObject, Qt, QSize, QRect
from PyQt6.QtGui import QImage, QImageReader, QColor, QPainter, QImageIOHandler

class LoaderSignals(QObject):
    finished = pyqtSignal(str, QImage)

class ThumbnailLoader(QRunnable):
    def __init__(self, path, size=(100, 100), crop_rect=None):
        super().__init__()
        self.path = path
        self.size = size
        self.crop_rect = crop_rect # (nx, ny, nw, nh)
        self.signals = LoaderSignals()

    def run(self):
        try:
            reader = QImageReader(self.path)
            reader.setAutoTransform(True)
            
            orig_size = reader.size()
            
            trans = reader.transformation()
            if trans in (QImageIOHandler.Transformation.TransformationRotate90, 
                         QImageIOHandler.Transformation.TransformationRotate270,
                         QImageIOHandler.Transformation.TransformationMirrorAndRotate90,
                         QImageIOHandler.Transformation.TransformationFlipAndRotate90):
                logical_size = QSize(orig_size.height(), orig_size.width())
            else:
                logical_size = orig_size

            if not orig_size.isValid():
                # Fallback to reading full image if size header fails
                image = reader.read()
            else:
                image = None

            if self.crop_rect:
                # If we have a crop, we must read the full image or a region
                if image is None:
                    image = reader.read()
                
                if not image.isNull():
                    w, h = image.width(), image.height()
                    nx, ny, nw, nh = self.crop_rect
                    
                    rect = QRect(
                        int(nx * w),
                        int(ny * h),
                        int(nw * w),
                        int(nh * h)
                    )
                    image = image.copy(rect)
                
            elif image is None:
                # Normal thumbnail path: use setScaledSize for efficiency
                if logical_size.isValid():
                    scale_w = self.size[0] / logical_size.width()
                    scale_h = self.size[1] / logical_size.height()
                    scale = min(scale_w, scale_h)
                    
                    target_raw_w = int(orig_size.width() * scale)
                    target_raw_h = int(orig_size.height() * scale)
                    reader.setScaledSize(QSize(target_raw_w, target_raw_h))
                
                image = reader.read()

            if image and not image.isNull():
                # Final scale to fit the requested thumbnail size
                target_qsize = QSize(*self.size)
                
                # If we have a specific crop, we want to scale to fill the thumbnail area
                if self.crop_rect:
                    scaled_img = image.scaled(target_qsize, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                    
                    # Center crop the expanded image to the target size
                    final_image = scaled_img.copy(
                        (scaled_img.width() - target_qsize.width()) // 2,
                        (scaled_img.height() - target_qsize.height()) // 2,
                        target_qsize.width(),
                        target_qsize.height()
                    )
                else:
                    # Full image mode: scale to fit within the thumbnail area
                    scaled_img = image.scaled(target_qsize, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    
                    # Fill base with background color to keep AR consistent in grid
                    final_image = QImage(target_qsize, QImage.Format.Format_ARGB32)
                    final_image.fill(QColor("#f8f9fa")) 
                    
                    painter = QPainter(final_image)
                    x = (target_qsize.width() - scaled_img.width()) // 2
                    y = (target_qsize.height() - scaled_img.height()) // 2
                    painter.drawImage(x, y, scaled_img)
                    painter.end()
                
                try:
                    self.signals.finished.emit(self.path, final_image)
                except RuntimeError:
                    # Occurs if the object was deleted during threading
                    pass
                
        except Exception as e:
            print(f"Thumbnail error: {e}")
