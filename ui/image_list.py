from PySide6.QtWidgets import QListWidget, QListWidgetItem
from PySide6.QtCore import Signal

class ImageList(QListWidget):
    image_selected = Signal(str)

    def __init__(self):
        super().__init__()
        from PySide6.QtCore import Qt
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedWidth(200)
        self.itemClicked.connect(self._on_item_clicked)

    def add_image(self, filename: str, path: str):
        item = QListWidgetItem(filename)
        item.setData(100, path)  # Store full path in user role
        self.addItem(item)

    def _on_item_clicked(self, item):
        path = item.data(100)
        self.image_selected.emit(path)
