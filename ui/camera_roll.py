from PySide6.QtWidgets import QListWidget, QListWidgetItem, QScroller, QStyledItemDelegate, QStyleOptionViewItem, QStyle
from PySide6.QtCore import Signal, QSize, QThreadPool, Qt, QRect, QPoint, QTimer
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen


class CameraRollDelegate(QStyledItemDelegate):
    """Custom delegate: draws icon centered at iconSize within the cell, with selection indicator."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._grid_mode = False

    def set_grid_mode(self, enabled):
        self._grid_mode = enabled

    def paint(self, painter, option, index):
        is_hidden = index.data(101) or False
        icon = index.data(Qt.ItemDataRole.DecorationRole)

        if not isinstance(icon, QIcon) or icon.isNull():
            return

        # Center the icon within the cell
        icon_size = option.decorationSize
        cell_rect = option.rect
        
        target_w = icon_size.width()
        if is_hidden and not self._grid_mode:
            target_w = int(icon_size.width() * 0.15)
        
        # Center the icon within the cell
        x = cell_rect.x() + (cell_rect.width() - target_w) // 2
        y = cell_rect.y() + (cell_rect.height() - icon_size.height()) // 2
        draw_rect = QRect(x, y, target_w, icon_size.height())

        pixmap = icon.pixmap(icon_size)

        if is_hidden:
            from PySide6.QtGui import QImage
            # Stretch the pixmap if we are shrinking
            if not self._grid_mode:
                pixmap = pixmap.scaled(target_w, icon_size.height(), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
            
            image = pixmap.toImage().convertToFormat(QImage.Format.Format_Grayscale8)
            painter.save()
            painter.setOpacity(0.4)
            painter.drawImage(draw_rect, image)
            painter.restore()
        else:
            painter.drawPixmap(draw_rect, pixmap)

        # Selection indicator: thick blue line below the image (normal mode only)
        if (option.state & QStyle.StateFlag.State_Selected) and not self._grid_mode:
            painter.save()
            pen = QPen(QColor("#2979FF"))
            pen.setWidth(3)
            painter.setPen(pen)
            y_line = draw_rect.bottom() + 10
            painter.drawLine(draw_rect.left(), y_line, draw_rect.right(), y_line)
            painter.restore()

    def sizeHint(self, option, index):
        parent = self.parent()
        is_hidden = index.data(101) or False
        
        if parent and hasattr(parent, 'grid_mode') and parent.grid_mode:
            gap = parent.GRID_GAP
            icon_size = parent.iconSize()
            return QSize(icon_size.width() + gap, icon_size.height() + gap)
        
        # In normal mode (IconMode)
        icon_size = option.decorationSize
        w = icon_size.width()
        if is_hidden:
            w = int(w * 0.15)
        
        # Add a bit of gap for normal mode too
        return QSize(w + 10, icon_size.height() + 22)


class CameraRoll(QListWidget):
    image_selected = Signal(str)
    hide_requested = Signal(str)
    remove_requested = Signal(str)
    items_reordered = Signal(list)

    GRID_GAP = 8  # px gap between items in grid mode

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
        self.setDragDropOverwriteMode(False)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)

        # Scrolling
        self.setHorizontalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        QScroller.grabGesture(self.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)

        self.itemClicked.connect(self._on_item_clicked)
        self.currentItemChanged.connect(self._on_current_item_changed)
        # Note: PySide6 uses Signal/Slot behavior. rowsMoved is a signal on the model.
        self.model().rowsMoved.connect(self._on_rows_moved)

        self.grid_mode = False
        self.columns = 6
        self._last_grid_icon_w = 0
        self._updating_layout = False

        # Debounce layout updates to prevent flickering
        self._layout_timer = QTimer()
        self._layout_timer.setSingleShot(True)
        self._layout_timer.setInterval(50)
        self._layout_timer.timeout.connect(self._do_update_grid_layout)

        self.setStyleSheet("""
            QListWidget {
                background-color: white;
                border: none;
            }
            QListWidget::item {
                margin: 0px;
                padding: 0px;
                background: transparent;
                border: none;
                outline: none;
            }
            QListWidget::item:selected {
                background: transparent;
                border: none;
                outline: none;
            }
            QScrollBar:horizontal, QScrollBar:vertical {
                border: none;
                background: transparent;
                height: 4px;
                width: 4px;
                margin: 0px;
            }
            QScrollBar::handle {
                background: #ddd;
                border-radius: 2px;
            }
            QScrollBar::handle:hover {
                background: #ccc;
            }
            QScrollBar::add-line, QScrollBar::sub-line {
                width: 0px;
                height: 0px;
                background: none;
                border: none;
            }
        """)

        self.delegate = CameraRollDelegate(self)
        self.setItemDelegate(self.delegate)

        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(4)

        self.path_to_item = {}
        self.active_workers = {} # (type, path) -> worker
        self.aspect_ratio = 4 / 5
        self.set_aspect_ratio("4:5")

    # ── Item management ─────────────────────────────────────────

    def add_image(self, filename: str, path: str, crop_rect=None):
        item = QListWidgetItem("")
        item.setData(100, path)
        item.setData(101, False)
        item.setToolTip(filename)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsSelectable)
        self.addItem(item)
        self.path_to_item[path] = item

        if crop_rect:
            self.update_thumbnail(path, crop_rect)
        else:
            self.refresh_thumbnail(path)

    # ── Normal mode (horizontal strip) ──────────────────────────

    def set_aspect_ratio(self, ratio_str):
        self._current_ratio_str = ratio_str
        if ":" in ratio_str:
            try:
                w_str, h_str = ratio_str.split(":")
                self.aspect_ratio = float(w_str) / float(h_str)
            except (ValueError, ZeroDivisionError):
                self.aspect_ratio = 4/5

        base_h = 100
        base_w = int(base_h * self.aspect_ratio)

        # IconMode supports variable width items via gridSize(0, 0) or by not setting it
        # and relying on sizeHint if we use IconMode + Flow::LeftToRight + Wrapping::False
        self.setIconSize(QSize(base_w, base_h))
        self.setGridSize(QSize()) # Disable fixed grid size to allow variable width
        self.setFixedHeight(base_h + 23)

        for path in self.path_to_item:
            self.refresh_thumbnail(path)

    # ── Grid mode (arrange) ─────────────────────────────────────

    def set_grid_mode(self, enabled):
        self.grid_mode = enabled
        if enabled:
            # Kill QScroller so it doesn't eat mouse-down events
            QScroller.ungrabGesture(self.viewport())
            QScroller.ungrabGesture(self)

            # ListMode supports proper drag-and-drop reordering with reflow.
            # gridSize is IGNORED in ListMode — item size comes from delegate sizeHint.
            self.setViewMode(QListWidget.ViewMode.ListMode)
            self.setFlow(QListWidget.Flow.LeftToRight)
            self.setWrapping(True)
            self.setMovement(QListWidget.Movement.Static)
            self.setResizeMode(QListWidget.ResizeMode.Adjust)
            self.setSpacing(0)  # Gaps handled by delegate sizeHint

            self.setDragDropMode(QListWidget.DragDropMode.InternalMove)
            self.setDragEnabled(True)
            self.setAcceptDrops(True)
            self.viewport().setAcceptDrops(True)
            self.setDropIndicatorShown(True)
            self.setDragDropOverwriteMode(False)
            self.setDefaultDropAction(Qt.DropAction.MoveAction)

            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.setMinimumHeight(200)
            self.setMaximumHeight(16777215)

            for path, item in self.path_to_item.items():
                is_hidden = item.data(101) or False
                item.setHidden(is_hidden)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsSelectable)

            self.delegate.set_grid_mode(True)
            self._update_grid_layout()
        else:
            QScroller.grabGesture(self.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)

            self.delegate.set_grid_mode(False)
            self.setViewMode(QListWidget.ViewMode.IconMode)
            self.setFlow(QListWidget.Flow.LeftToRight)
            self.setWrapping(False)
            self.setSpacing(0)
            self.setDragDropMode(QListWidget.DragDropMode.NoDragDrop)
            self.setMovement(QListWidget.Movement.Static)

            for item in self.path_to_item.values():
                item.setHidden(False)

            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.set_aspect_ratio(self._current_ratio_str if hasattr(self, '_current_ratio_str') else "4:5")

    def set_grid_size(self, columns):
        self.columns = columns
        self._last_grid_icon_w = 0
        if self.grid_mode:
            self._update_grid_layout()

    def _update_grid_layout(self):
        """Schedule a layout update."""
        if self.grid_mode:
            self._layout_timer.start()

    def _do_update_grid_layout(self):
        """Actually perform the layout update."""
        if not self.grid_mode or self._updating_layout:
            return
            
        self._updating_layout = True
        try:
            # Use width minus a safe margin for scrollbar if ScrollBarAlwaysOn
            # viewport().width() already accounts for the scrollbar if it's AlwaysOn
            vw = self.viewport().width()
            if vw <= 0:
                return

            gap = self.GRID_GAP
            # Calculate icon width based on available viewport width
            icon_w = (vw // self.columns) - gap
            if icon_w < 20:
                icon_w = 20

            # Only update if change is significant to avoid tiny oscillation loops
            if abs(icon_w - self._last_grid_icon_w) < 1:
                return
                
            self._last_grid_icon_w = icon_w
            icon_h = int(icon_w / self.aspect_ratio)

            # setIconSize and setGridSize trigger layout changes in QListWidget
            self.setIconSize(QSize(icon_w, icon_h))
            self.setGridSize(QSize(icon_w + gap, icon_h + gap))

            # Hidden items update
            for item in self.path_to_item.values():
                is_hidden = item.data(101) or False
                item.setHidden(self.grid_mode and is_hidden)
                
        finally:
            self._updating_layout = False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.grid_mode:
            self._update_grid_layout()

    # ── Drag & drop event overrides ─────────────────────────────

    def dragEnterEvent(self, event):
        super().dragEnterEvent(event)
        if event.source() == self:
            event.accept()

    def dragMoveEvent(self, event):
        super().dragMoveEvent(event)
        if event.source() == self:
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()

    def dropEvent(self, event):
        super().dropEvent(event)

    def startDrag(self, supportedActions):
        super().startDrag(supportedActions)

    def _on_rows_moved(self, parent, start, end, destination, row):
        new_paths = []
        for i in range(self.count()):
            new_paths.append(self.item(i).data(100))
        self.items_reordered.emit(new_paths)

    # ── Thumbnail loading ───────────────────────────────────────

    def refresh_thumbnail(self, path, rotation=0, flip_h=False, flip_v=False):
        if path in self.path_to_item:
            from ui.thumbnail_loader import ThumbnailLoader
            loader = ThumbnailLoader(
                path, 
                size=(self.iconSize().width(), self.iconSize().height()),
                rotation=rotation,
                flip_h=flip_h,
                flip_v=flip_v
            )
            loader.signals.finished.connect(self._on_thumbnail_loaded)
            
            # Keep reference to prevent GC in PySide6
            self.active_workers[('thumb', path)] = loader
            self.thread_pool.start(loader)

    def update_thumbnail(self, path, crop_rect, rotation=0, flip_h=False, flip_v=False):
        if path in self.path_to_item:
            from ui.thumbnail_loader import ThumbnailLoader
            loader = ThumbnailLoader(
                path, 
                size=(self.iconSize().width(), self.iconSize().height()), 
                crop_rect=crop_rect,
                rotation=rotation,
                flip_h=flip_h,
                flip_v=flip_v
            )
            loader.signals.finished.connect(self._on_thumbnail_loaded)
            
            # Keep reference to prevent GC in PySide6
            self.active_workers[('thumb', path)] = loader
            self.thread_pool.start(loader)

    def _on_thumbnail_loaded(self, path, image):
        # Cleanup worker reference
        if ('thumb', path) in self.active_workers:
            del self.active_workers[('thumb', path)]
            
        if path in self.path_to_item:
            item = self.path_to_item[path]
            item.setIcon(QIcon(QPixmap.fromImage(image)))

    # ── Selection / visibility ──────────────────────────────────

    def _on_item_clicked(self, item):
        if item:
            path = item.data(100)
            self.image_selected.emit(path)

    def _on_current_item_changed(self, current, previous):
        self.viewport().update()
        if current:
            path = current.data(100)
            self.image_selected.emit(path)

    def set_hidden(self, path, hidden: bool):
        if path in self.path_to_item:
            item = self.path_to_item[path]
            item.setData(101, hidden)
            
            # Use item.setHidden for Arrange Mode (makes them invisible/skipped in layout)
            # In Normal Mode, items stay visible but shrink via delegate
            item.setHidden(self.grid_mode and hidden)
            
            # Force re-layout
            self.doItemsLayout()
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
