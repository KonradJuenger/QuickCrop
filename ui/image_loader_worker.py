from PyQt6.QtCore import QRunnable, pyqtSignal, QObject, QSize
from PyQt6.QtGui import QImage, QImageReader, QImageIOHandler

class LoaderSignals(QObject):
    finished = pyqtSignal(str, QImage, bool) # path, image, is_full_quality
    error = pyqtSignal(str, str)

class ImageLoaderWorker(QRunnable):
    def __init__(self, path, max_dim=None):
        super().__init__()
        self.path = path
        self.max_dim = max_dim
        self.signals = LoaderSignals()

    def run(self):
        try:
            reader = QImageReader(self.path)
            reader.setAutoTransform(True)
            
            orig_size = reader.size()
            
            # Get transformed logical size
            trans = reader.transformation()
            if trans in (QImageIOHandler.Transformation.TransformationRotate90, 
                         QImageIOHandler.Transformation.TransformationRotate270,
                         QImageIOHandler.Transformation.TransformationMirrorAndRotate90,
                         QImageIOHandler.Transformation.TransformationFlipAndRotate90):
                logical_size = QSize(orig_size.height(), orig_size.width())
                is_swapped = True
            else:
                logical_size = orig_size
                is_swapped = False

            is_full = True
            
            if self.max_dim and logical_size.isValid():
                if logical_size.width() > self.max_dim or logical_size.height() > self.max_dim:
                    scale = self.max_dim / max(logical_size.width(), logical_size.height())
                    
                    # setScaledSize applies to RAW data, so we scale orig_size
                    new_raw_size = orig_size * scale
                    reader.setScaledSize(new_raw_size)
                    is_full = False
            
            image = reader.read()
            
            if not image.isNull():
                self.signals.finished.emit(self.path, image, is_full)
            else:
                self.signals.error.emit(self.path, "Failed to load image")
        except Exception as e:
            self.signals.error.emit(self.path, str(e))
