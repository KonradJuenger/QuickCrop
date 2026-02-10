from PyQt6.QtCore import Qt, QRectF, QPoint, QPointF, QSize, pyqtSignal, QTimer
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QPainterPath, QTransform
from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QFrame

class Canvas(QGraphicsView):
    crop_changed = pyqtSignal()
    preview_toggled = pyqtSignal(bool)
    navigation_requested = pyqtSignal(int)  # -1 for prev, 1 for next
    
    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        
        # White background
        self.setBackgroundBrush(QBrush(Qt.GlobalColor.white))
        self.setStyleSheet("background-color: white; border: none;")
        self.scene.setBackgroundBrush(QBrush(Qt.GlobalColor.white))
        
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.aspect_ratio = 0.8  # 4:5 default
        self.pixmap_item = None
        
        self.norm_crop_rect = (0, 0, 1, 1) # (nx, ny, nw, nh)
        self.crop_rect = QRectF()
        self.handles = {}
        self.interaction_mode = "NONE"  # "NONE", "RESIZE", "MOVE_CROP"
        self.active_handle = None
        self.last_mouse_pos = QPoint()
        
        self.overlay_color = QColor(0, 0, 0, 150)
        self.handle_size = 12
        
        self.preview_mode = True
        self.scene_crop_rect_for_preview = QRectF()
        
        # Hover navigation indicators
        self.hover_side = None  # None, "LEFT", "RIGHT"
        self._potential_hover = None
        self._hover_timer = QTimer()
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(200)
        self._hover_timer.timeout.connect(self._on_hover_timer)

    # ---- Image rect in viewport coordinates (cached after fit) ----
    def _image_rect_in_viewport(self):
        """Returns the image's bounding rect mapped to viewport pixel coordinates."""
        if not self.pixmap_item:
            return QRectF()
        return QRectF(self.mapFromScene(self.pixmap_item.sceneBoundingRect()).boundingRect())

    def _update_scene_rect(self):
        if not self.pixmap_item:
            return
        rect = self.pixmap_item.sceneBoundingRect()
        padding = 5000
        self.setSceneRect(rect.adjusted(-padding, -padding, padding, padding))

    # ---- Loading ----
    def load_image(self, pixmap):
        self.scene.clear()
        self.pixmap_item = QGraphicsPixmapItem(pixmap)
        self.scene.addItem(self.pixmap_item)
        
        self._update_scene_rect()
        
        if self.preview_mode:
            self.preview_mode = False
        
        old_blocked = self.blockSignals(True)
        try:
            self.resetTransform()
            self._fit_to_viewport()
            if self.norm_crop_rect == (0, 0, 1, 1):
                self.reset_crop_rect()
            else:
                self.sync_crop_to_viewport()
        finally:
            self.blockSignals(old_blocked)
        
        self.crop_changed.emit()
        self.viewport().update()

    def clear(self):
        self.scene.clear()
        self.pixmap_item = None
        self.preview_mode = False
        self.interaction_mode = "NONE"
        self.viewport().update()

    # ---- Fitting: fills 95% of viewport ----
    def _fit_to_viewport(self, rect=None):
        """Scale and center the given rect (or the image if None) so it fills 95% of the viewport."""
        if rect is None:
            if not self.pixmap_item: return
            # Use sceneBoundingRect instead of boundingRect to account for rotation/transform
            rect = self.pixmap_item.sceneBoundingRect()
        
        if rect.width() == 0 or rect.height() == 0:
            return
            
        self.resetTransform()
        
        vp = self.viewport().rect()
        # Use 0.95 to make the border half as wide as the previous 0.90
        scale_factor = 0.95
        target_w = vp.width() * scale_factor
        target_h = vp.height() * scale_factor
        
        scale_w = target_w / rect.width()
        scale_h = target_h / rect.height()
        scale = min(scale_w, scale_h)
        
        self.scale(scale, scale)
        
        # Center on the rect in scene coordinates
        self.centerOn(rect.center())

    # ---- State Synchronization ----
    def sync_crop_to_viewport(self):
        """Update self.crop_rect (viewport pixels) from self.norm_crop_rect."""
        if not self.pixmap_item: return
        img_vp = self._image_rect_in_viewport()
        nx, ny, nw, nh = self.norm_crop_rect
        self.crop_rect = QRectF(
            img_vp.x() + nx * img_vp.width(),
            img_vp.y() + ny * img_vp.height(),
            nw * img_vp.width(),
            nh * img_vp.height()
        )
        self._update_handles()

    def sync_crop_from_viewport(self):
        """Update self.norm_crop_rect from self.crop_rect."""
        if not self.pixmap_item: return
        img_vp = self._image_rect_in_viewport()
        if img_vp.width() == 0 or img_vp.height() == 0: return
        
        nx = (self.crop_rect.x() - img_vp.x()) / img_vp.width()
        ny = (self.crop_rect.y() - img_vp.y()) / img_vp.height()
        nw = self.crop_rect.width() / img_vp.width()
        nh = self.crop_rect.height() / img_vp.height()
        self.norm_crop_rect = (nx, ny, nw, nh)

    # ---- Crop rect ----
    def reset_crop_rect(self):
        """Reset crop to center of image at current aspect ratio."""
        if not self.pixmap_item: return
        # Use sceneBoundingRect to get the "visible" dimensions after rotation/flipping
        rect = self.pixmap_item.sceneBoundingRect()
        w, h = rect.width(), rect.height()
        img_ratio = w / h
        if img_ratio > self.aspect_ratio:
            nw = self.aspect_ratio / img_ratio
            nh = 1.0
        else:
            nw = 1.0
            nh = img_ratio / self.aspect_ratio
        nx = (1.0 - nw) / 2
        ny = (1.0 - nh) / 2
        self.norm_crop_rect = (nx, ny, nw, nh)
        self.sync_crop_to_viewport()
        self.crop_changed.emit()

    def set_aspect_ratio(self, ratio_str):
        old_blocked = self.blockSignals(True)
        try:
            if ratio_str == "1:1":
                self.aspect_ratio = 1.0
            elif ratio_str == "4:5":
                self.aspect_ratio = 4 / 5
            elif ratio_str == "9:16":
                self.aspect_ratio = 9 / 16
            
            self.preview_mode = False
            
            self._fit_to_viewport()
            self.reset_crop_rect()
        finally:
            self.blockSignals(old_blocked)
        
        self.crop_changed.emit()
        self.viewport().update()

    def _on_hover_timer(self):
        self.hover_side = self._potential_hover
        self.viewport().update()

    def _update_handles(self):
        r = self.crop_rect
        hs = self.handle_size
        self.handles = {
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft: QRectF(r.left() - hs/2, r.top() - hs/2, hs, hs),
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight: QRectF(r.right() - hs/2, r.top() - hs/2, hs, hs),
            Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft: QRectF(r.left() - hs/2, r.bottom() - hs/2, hs, hs),
            Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight: QRectF(r.right() - hs/2, r.bottom() - hs/2, hs, hs),
        }

    # ---- Drawing ----
    def paintEvent(self, event):
        super().paintEvent(event)

    def drawForeground(self, painter, rect):
        vp = QRectF(self.viewport().rect())
        painter.save()
        painter.resetTransform()
        
        if self.preview_mode:
            if not self.scene_crop_rect_for_preview.isValid():
                painter.restore()
                return
            # Map crop from scene to viewport
            crop_poly = self.mapFromScene(self.scene_crop_rect_for_preview)
            crop_vp = QRectF(crop_poly.boundingRect())
            
            # Paint 4 white rectangles around the crop (with tiny overlap to prevent peeking)
            painter.setBrush(Qt.GlobalColor.white)
            painter.setPen(Qt.PenStyle.NoPen)
            eps = 0.5
            # Top
            painter.drawRect(QRectF(vp.left(), vp.top(), vp.width(), (crop_vp.top() - vp.top()) + eps))
            # Bottom
            painter.drawRect(QRectF(vp.left(), crop_vp.bottom() - eps, vp.width(), (vp.bottom() - crop_vp.bottom()) + eps))
            # Left
            painter.drawRect(QRectF(vp.left(), crop_vp.top(), (crop_vp.left() - vp.left()) + eps, crop_vp.height()))
            # Right
            painter.drawRect(QRectF(crop_vp.right() - eps, crop_vp.top(), (vp.right() - crop_vp.right()) + eps, crop_vp.height()))
            
            painter.restore()
            self._draw_nav_indicators(painter, vp)
            return

        # Edit mode: dark overlay with crop cutout
        # Paint 4 dark rectangles around the crop rect (avoids subpixel gap issues)
        painter.setBrush(self.overlay_color)
        painter.setPen(Qt.PenStyle.NoPen)
        cr = self.crop_rect
        # Top
        painter.drawRect(QRectF(vp.left(), vp.top(), vp.width(), cr.top() - vp.top()))
        # Bottom
        painter.drawRect(QRectF(vp.left(), cr.bottom(), vp.width(), vp.bottom() - cr.bottom()))
        # Left
        painter.drawRect(QRectF(vp.left(), cr.top(), cr.left() - vp.left(), cr.height()))
        # Right
        painter.drawRect(QRectF(cr.right(), cr.top(), vp.right() - cr.right(), cr.height()))
        
        # Crop border
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(Qt.GlobalColor.white, 1, Qt.PenStyle.SolidLine))
        painter.drawRect(self.crop_rect)
        
        # Handles
        painter.setBrush(QBrush(QColor(255, 255, 255, 200)))
        painter.setPen(QPen(QColor(0, 0, 0, 100), 1))
        for align, h_rect in self.handles.items():
            painter.drawRect(h_rect)
        
        painter.restore()
        self._draw_nav_indicators(painter, vp)

    def _draw_nav_indicators(self, painter, vp):
        if not self.hover_side:
            return
            
        painter.save()
        painter.resetTransform()
        
        # Indicator area (15%)
        w = vp.width() * 0.15
        if self.hover_side == "LEFT":
            rect = QRectF(vp.left(), vp.top(), w, vp.height())
            arrow_points = [
                QPointF(vp.left() + w/2 + 5, vp.center().y() - 10),
                QPointF(vp.left() + w/2 - 5, vp.center().y()),
                QPointF(vp.left() + w/2 + 5, vp.center().y() + 10)
            ]
        else:
            rect = QRectF(vp.right() - w, vp.top(), w, vp.height())
            arrow_points = [
                QPointF(vp.right() - w/2 - 5, vp.center().y() - 10),
                QPointF(vp.right() - w/2 + 5, vp.center().y()),
                QPointF(vp.right() - w/2 - 5, vp.center().y() + 10)
            ]
            
        # Draw soft overlay
        painter.setBrush(QColor(150, 150, 150, 40))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(rect)
        
        # Draw arrow
        painter.setPen(QPen(QColor(100, 100, 100, 180), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolyline(arrow_points)
        
        painter.restore()

    # ---- Transforms: rotate / mirror ----
    def rotate_image(self, angle):
        if not self.pixmap_item:
            return
        center = self.pixmap_item.boundingRect().center()
        self.pixmap_item.setTransformOriginPoint(center)
        current = self.pixmap_item.rotation()
        self.pixmap_item.setRotation(current + angle)
        
        self._update_scene_rect()
        self._fit_to_viewport()
        self.reset_crop_rect()
        self.crop_changed.emit()
        self.viewport().update()

    def get_transform_state(self):
        """Returns (rotation, flip_h, flip_v) state."""
        if not self.pixmap_item:
            return 0, False, False
        
        rot = self.pixmap_item.rotation()
        
        # Check transform for flips
        t = self.pixmap_item.transform()
        # This is a bit simplistic but works for our set_transform usage
        flip_h = t.m11() < 0
        flip_v = t.m22() < 0
        
        return rot, flip_h, flip_v

    def set_transform_state(self, rotation, flip_h, flip_v):
        """Restore (rotation, flip_h, flip_v) state."""
        if not self.pixmap_item:
            return
            
        center = self.pixmap_item.boundingRect().center()
        self.pixmap_item.setTransformOriginPoint(center)
        self.pixmap_item.setRotation(rotation)
        
        t = QTransform()
        t.translate(center.x(), center.y())
        t.scale(-1 if flip_h else 1, -1 if flip_v else 1)
        t.translate(-center.x(), -center.y())
        self.pixmap_item.setTransform(t)
        
        self._update_scene_rect()
        self._fit_to_viewport()
        # Note: caller should restore crop rect after this

    def mirror_image(self, horz, vert):
        if not self.pixmap_item:
            return
        center = self.pixmap_item.boundingRect().center()
        t = QTransform()
        t.translate(center.x(), center.y())
        t.scale(-1 if horz else 1, -1 if vert else 1)
        t.translate(-center.x(), -center.y())
        self.pixmap_item.setTransform(t, True)
        
        self._update_scene_rect()
        self.viewport().update()

    # ---- Preview toggle ----
    def toggle_preview(self):
        if not self.pixmap_item:
            self.preview_mode = not self.preview_mode
            self.preview_toggled.emit(self.preview_mode)
            return
        
        self.preview_mode = not self.preview_mode
        if self.preview_mode:
            img_scene_rect = self.pixmap_item.sceneBoundingRect()
            nx, ny, nw, nh = self.norm_crop_rect
            self.scene_crop_rect_for_preview = QRectF(
                img_scene_rect.x() + nx * img_scene_rect.width(),
                img_scene_rect.y() + ny * img_scene_rect.height(),
                nw * img_scene_rect.width(),
                nh * img_scene_rect.height()
            )
            self._fit_to_viewport(self.scene_crop_rect_for_preview)
        else:
            self._fit_to_viewport()
            self.sync_crop_to_viewport()
        
        self.viewport().update()
        self.preview_toggled.emit(self.preview_mode)

    # ---- Normalized crop <-> viewport ----
    def get_normalized_crop_rect(self):
        return self.norm_crop_rect

    def restore_crop_rect(self, norm_rect):
        self.preview_mode = False
        self.norm_crop_rect = norm_rect
        if self.pixmap_item:
            self._fit_to_viewport()
            self.sync_crop_to_viewport()
        self.crop_changed.emit()

    # ---- Mouse interaction: crop rect only ----
    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Only toggle if clicking inside the crop area
            pos_f = event.pos().toPointF()
            if self.preview_mode:
                active_crop = QRectF(self.mapFromScene(self.scene_crop_rect_for_preview).boundingRect())
            else:
                active_crop = QRectF(self.crop_rect)
            
            if active_crop.contains(pos_f):
                self.toggle_preview()
        else:
            super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
            event.ignore()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event):
        # No zooming allowed
        event.accept()

    def mousePressEvent(self, event):
        if not self.pixmap_item:
            return
        
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.pos()
            pos_f = pos.toPointF()
            
            # Use appropriate crop rect for bounds checking
            if self.preview_mode:
                active_crop = QRectF(self.mapFromScene(self.scene_crop_rect_for_preview).boundingRect())
            else:
                active_crop = QRectF(self.crop_rect)
            
            # 1. Check handles first (if in edit mode)
            if not self.preview_mode:
                active_h = None
                for align, rect in self.handles.items():
                    if QRectF(rect).contains(pos_f):
                        active_h = align
                        break
                
                if active_h:
                    self.interaction_mode = "RESIZE"
                    self.active_handle = active_h
                    self.last_mouse_pos = pos
                    return
            
            # 2. Check inside crop rect (Move in edit mode, Toggle-ready in preview)
            if active_crop.contains(pos_f):
                if not self.preview_mode:
                    self.interaction_mode = "MOVE_CROP"
                    self.setCursor(Qt.CursorShape.SizeAllCursor)
                self.last_mouse_pos = pos
                # We do NOT navigate if clicking inside the crop area
                return

            # 3. Navigation click (clicked in gutters)
            viewport_width = self.viewport().width()
            if pos.x() < viewport_width * 0.15:
                self.navigation_requested.emit(-1)
            elif pos.x() > viewport_width * 0.85:
                self.navigation_requested.emit(1)
            
            self.last_mouse_pos = pos
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        pos = event.pos()
        
        # Navigation hover detection
        vp_w = self.viewport().width()
        new_potential = None
        if pos.x() < vp_w * 0.15:
            new_potential = "LEFT"
        elif pos.x() > vp_w * 0.85:
            new_potential = "RIGHT"
            
        if new_potential != self._potential_hover:
            self._potential_hover = new_potential
            if new_potential:
                self._hover_timer.start()
            else:
                self._hover_timer.stop()
                if self.hover_side:
                    self.hover_side = None
                    self.viewport().update()

        if self.preview_mode or not self.pixmap_item:
            return
        pos = event.pos()
        
        if self.interaction_mode == "RESIZE":
            self.resize_crop(pos)
            self.sync_crop_from_viewport()
            self.viewport().update()
        elif self.interaction_mode == "MOVE_CROP":
            self._move_crop(pos)
            self.sync_crop_from_viewport()
            self.viewport().update()
        else:
            # Hover cursor
            hover = False
            for align, rect in self.handles.items():
                if QRectF(rect).contains(pos.toPointF()):
                    self.setCursor(self._get_cursor_for_align(align))
                    hover = True
                    break
            if not hover:
                if QRectF(self.crop_rect).contains(pos.toPointF()):
                    self.setCursor(Qt.CursorShape.SizeAllCursor)
                else:
                    self.setCursor(Qt.CursorShape.ArrowCursor)
        
        self.last_mouse_pos = pos

    def mouseReleaseEvent(self, event):
        if self.preview_mode:
            return
        self.interaction_mode = "NONE"
        self.active_handle = None
        self.setCursor(Qt.CursorShape.ArrowCursor)
        super().mouseReleaseEvent(event)

    def _get_cursor_for_align(self, align):
        if align == (Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft) or \
           align == (Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight):
            return Qt.CursorShape.SizeFDiagCursor
        return Qt.CursorShape.SizeBDiagCursor

    # ---- Crop movement (drag the crop rect, not the image) ----
    def _move_crop(self, pos):
        if not self.pixmap_item:
            return
        delta = QPointF(pos.x() - self.last_mouse_pos.x(), pos.y() - self.last_mouse_pos.y())
        
        new_rect = self.crop_rect.translated(delta)
        
        # Clamp to image bounds
        img_vp = self._image_rect_in_viewport()
        
        if new_rect.left() < img_vp.left():
            new_rect.moveLeft(img_vp.left())
        if new_rect.right() > img_vp.right():
            new_rect.moveRight(img_vp.right())
        if new_rect.top() < img_vp.top():
            new_rect.moveTop(img_vp.top())
        if new_rect.bottom() > img_vp.bottom():
            new_rect.moveBottom(img_vp.bottom())
        
        self.crop_rect = new_rect
        self._update_handles()
        self.crop_changed.emit()

    # ---- Crop resize ----
    def resize_crop(self, pos):
        if not self.pixmap_item:
            return
        img_vp = self._image_rect_in_viewport()
        
        align = self.active_handle
        r = self.crop_rect
        
        fixed = QPointF()
        if align == (Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft):
            fixed = r.bottomRight()
        elif align == (Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight):
            fixed = r.bottomLeft()
        elif align == (Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft):
            fixed = r.topRight()
        elif align == (Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight):
            fixed = r.topLeft()
        else:
            return
        
        dx = pos.x() - fixed.x()
        dy = pos.y() - fixed.y()
        
        dir_x = 1 if (align & Qt.AlignmentFlag.AlignRight) else -1
        dir_y = 1 if (align & Qt.AlignmentFlag.AlignBottom) else -1
        
        # Max available from fixed to image edge
        if dir_x > 0:
            max_w = img_vp.right() - fixed.x()
        else:
            max_w = fixed.x() - img_vp.left()
        
        if dir_y > 0:
            max_h = img_vp.bottom() - fixed.y()
        else:
            max_h = fixed.y() - img_vp.top()
        
        hard_max_w = min(max_w, max_h * self.aspect_ratio)
        if hard_max_w < 10:
            hard_max_w = 10
        
        new_w = min(abs(dx), hard_max_w)
        new_h = new_w / self.aspect_ratio
        
        final_x = fixed.x() + (new_w * dir_x)
        final_y = fixed.y() + (new_h * dir_y)
        
        self.crop_rect = QRectF(QPointF(fixed.x(), fixed.y()), QPointF(final_x, final_y)).normalized()
        self._update_handles()
        self.crop_changed.emit()

    # ---- Resize event: re-fit when window resizes ----
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.pixmap_item:
            if self.preview_mode:
                self._fit_to_viewport(self.scene_crop_rect_for_preview)
            else:
                self._fit_to_viewport()
                self.sync_crop_to_viewport()
            self.crop_changed.emit()

    def leaveEvent(self, event):
        self._hover_timer.stop()
        self._potential_hover = None
        if self.hover_side:
            self.hover_side = None
            self.viewport().update()
        super().leaveEvent(event)
