from PyQt6.QtCore import QRunnable, pyqtSignal, QObject
from PyQt6.QtGui import QImageReader, QImageIOHandler

class InfoSignals(QObject):
    finished = pyqtSignal(str, int, int) # path, width, height
    error = pyqtSignal(str, str)

class ImageInfoLoader(QRunnable):
    """Fast worker to just get image dimensions without loading full pixels."""
    def __init__(self, path):
        super().__init__()
        self.path = path
        self.signals = InfoSignals()

    def run(self):
        try:
            reader = QImageReader(self.path)
            reader.setAutoTransform(True)
            size = reader.size()
            
            # Manually ensure size accounts for rotation if reader.size() didn't
            trans = reader.transformation()
            if trans in (QImageIOHandler.Transformation.TransformationRotate90, 
                         QImageIOHandler.Transformation.TransformationRotate270,
                         QImageIOHandler.Transformation.TransformationMirrorAndRotate90,
                         QImageIOHandler.Transformation.TransformationFlipAndRotate90):
                w, h = size.height(), size.width()
            else:
                w, h = size.width(), size.height()

            if size.isValid():
                self.signals.finished.emit(self.path, w, h)
            else:
                self.signals.error.emit(self.path, "Invalid image size")
        except Exception as e:
            self.signals.error.emit(self.path, str(e))
