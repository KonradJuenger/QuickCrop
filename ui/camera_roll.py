from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QScroller, QStyledItemDelegate, QStyleOptionViewItem, QStyle
from PyQt6.QtCore import pyqtSignal, QSize, QThreadPool, Qt, QRect, QPoint
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen


class CameraRollDelegate(QStyledItemDelegate):
    """Minimal delegate: draws icon + custom selection border only."""

    def paint(self, painter, option, index):
        is_hidden = index.data(101) or False

        if is_hidden:
            # Draw grayscale version
            icon = index.data(Qt.ItemDataRole.DecorationRole)
            if isinstance(icon, QIcon) and not icon.isNull():
                pixmap = icon.pixmap(option.decorationSize)
                from PyQt6.QtGui import QImage
                image = pixmap.toImage().convertToFormat(QImage.Format.Format_Grayscale8)

                painter.save()
                target_rect = QStyle.alignedRect(
                    option.direction, Qt.AlignmentFlag.AlignCenter,
                    option.decorationSize, option.rect
                )
                painter.setOpacity(0.4)
                painter.drawImage(target_rect, image)
                painter.restore()
            else:
                clean_option = QStyleOptionViewItem(option)
                clean_option.state &= ~QStyle.StateFlag.State_Selected
                clean_option.state &= ~QStyle.StateFlag.State_HasFocus
                super().paint(painter, clean_option, index)
        else:
            # Strip all system selection/focus indicators
            clean_option = QStyleOptionViewItem(option)
            clean_option.state &= ~QStyle.StateFlag.State_Selected
            clean_option.state &= ~QStyle.StateFlag.State_HasFocus
            super().paint(painter, clean_option, index)

        if option.state & QStyle.StateFlag.State_Selected:
            icon = index.data(Qt.ItemDataRole.DecorationRole)
            if isinstance(icon, QIcon) and not icon.isNull():
                painter.save()
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                
                # Rect to draw the selection around
                # We use decorationSize to ensure it follows the actual image bounds
                icon_rect = QStyle.alignedRect(
                    option.direction, Qt.AlignmentFlag.AlignCenter,
                    option.decorationSize, option.rect
                )
                
                # Adjusted to wrap the icon tightly but with NO intersection
                # icon_rect is the ACTUAL pixel rect of the icon
                border_rect = icon_rect.adjusted(-2, -2, 1, 1)
                
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor("#0078d4"), 2))
                painter.drawRoundedRect(border_rect, 2, 2)
                painter.restore()


class CameraRoll(QListWidget):
    image_selected = pyqtSignal(str)
    hide_requested = pyqtSignal(str)
    remove_requested = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setFlow(QListWidget.Flow.LeftToRight)
        self.setWrapping(False)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setSpacing(0)
        self.setMovement(QListWidget.Movement.Static)
        self.setMouseTracking(True)

        # Scrolling
        self.setHorizontalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        QScroller.grabGesture(self.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)

        self.itemClicked.connect(self._on_item_clicked)
        self.currentItemChanged.connect(self._on_current_item_changed)

        self.setStyleSheet("""
            QListWidget {
                background-color: #f8f9fa;
                border: none;
                padding: 0px;
            }
            QListWidget::item {
                margin: 0px;
                padding: 0px;
                background: transparent;
                border: none;
                outline: none;
            }
            QListWidget::item:selected,
            QListWidget::item:selected:active,
            QListWidget::item:selected:!active {
                background: transparent;
                border: none;
                outline: none;
            }
            QListWidget::item:focus {
                outline: none;
                border: none;
            }
        """)

        self.delegate = CameraRollDelegate(self)
        self.setItemDelegate(self.delegate)

        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(4)

        self.path_to_item = {}
        self.aspect_ratio = 4 / 5
        self.set_aspect_ratio("4:5")

    def add_image(self, filename: str, path: str, crop_rect=None):
        item = QListWidgetItem("")
        item.setData(100, path)
        item.setData(101, False)  # hidden
        item.setToolTip(filename)
        self.addItem(item)
        self.path_to_item[path] = item

        if crop_rect:
            self.update_thumbnail(path, crop_rect)
        else:
            self.refresh_thumbnail(path)

    def set_aspect_ratio(self, ratio_str):
        if ratio_str == "1:1":
            self.aspect_ratio = 1.0
        elif ratio_str == "4:5":
            self.aspect_ratio = 4 / 5
        elif ratio_str == "9:16":
            self.aspect_ratio = 9 / 16

        base_h = 100
        base_w = int(base_h * self.aspect_ratio)

        # Grid dimensions - significantly reduced padding
        grid_h = base_h + 8
        grid_w = base_w + 8
        self.setGridSize(QSize(grid_w, grid_h))
        self.setFixedHeight(grid_h)
        self.setIconSize(QSize(base_w, base_h))

        for path in self.path_to_item:
            self.refresh_thumbnail(path)

    def refresh_thumbnail(self, path):
        if path in self.path_to_item:
            from ui.thumbnail_loader import ThumbnailLoader
            loader = ThumbnailLoader(path, size=(self.iconSize().width(), self.iconSize().height()))
            loader.signals.finished.connect(self._on_thumbnail_loaded)
            self.thread_pool.start(loader)

    def update_thumbnail(self, path, crop_rect):
        if path in self.path_to_item:
            from ui.thumbnail_loader import ThumbnailLoader
            loader = ThumbnailLoader(path, size=(self.iconSize().width(), self.iconSize().height()), crop_rect=crop_rect)
            loader.signals.finished.connect(self._on_thumbnail_loaded)
            self.thread_pool.start(loader)

    def _on_thumbnail_loaded(self, path, image):
        if path in self.path_to_item:
            item = self.path_to_item[path]
            item.setIcon(QIcon(QPixmap.fromImage(image)))

    def _on_item_clicked(self, item):
        if item:
            path = item.data(100)
            self.image_selected.emit(path)

    def _on_current_item_changed(self, current, previous):
        # Force full repaint to prevent selection border "splitting"
        self.viewport().update()
        if current:
            path = current.data(100)
            self.image_selected.emit(path)

    def set_hidden(self, path, hidden: bool):
        if path in self.path_to_item:
            item = self.path_to_item[path]
            item.setData(101, hidden)
            self.viewport().update()

    def remove_path(self, path):
        if path in self.path_to_item:
            item = self.path_to_item[path]
            row = self.row(item)
            self.takeItem(row)
            del self.path_to_item[path]

    def clear(self):
        self.thread_pool.clear()
        self.path_to_item.clear()
        super().clear()
