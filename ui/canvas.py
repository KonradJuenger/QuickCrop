import math

from PySide6.QtCore import Qt, QRectF, QPoint, QPointF, QSize, Signal, QTimer
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QPainterPath, QTransform
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QFrame

class Canvas(QGraphicsView):
    crop_changed = Signal()
    preview_toggled = Signal(bool)
    navigation_requested = Signal(int)  # -1 for prev, 1 for next
    
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
        self.rotation_handle_rect = QRectF()
        self.rotation_angle = 0.0
        self.interaction_mode = "NONE"  # "NONE", "RESIZE", "MOVE_CROP", "ROTATE"
        self.active_handle = None
        self.last_mouse_pos = QPoint()
        self.rotation_start_angle = 0.0
        self.rotation_start_mouse_angle = 0.0
        self._rotation_pivot_local = None  # Fixed pivot in pixmap-local coords during drag
        self._rotation_pre_drag_crop_w = None  # Crop pixel width at drag start (for grow-back)
        
        self.overlay_color = QColor(0, 0, 0, 150)
        self.handle_size = 12
        
        self.preview_mode = True
        self.scene_crop_rect_for_preview = QRectF()
        self.navigation_enabled = False
        
        # Hover navigation indicators
        self.hover_side = None  # None, "LEFT", "RIGHT"
        self._potential_hover = None
        self._hover_timer = QTimer()
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(200)
        self._hover_timer.timeout.connect(self._on_hover_timer)
        
        # Enable mouse tracking for hover effects
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)

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

    @staticmethod
    def _normalize_angle(angle):
        return ((float(angle) + 180.0) % 360.0) - 180.0

    def _set_rotation_origin_keep_scene_point(self, pivot_local):
        """Set transform origin while keeping that local point fixed in scene coords."""
        if not self.pixmap_item:
            return
        scene_before = self.pixmap_item.mapToScene(pivot_local)
        self.pixmap_item.setTransformOriginPoint(pivot_local)
        scene_after = self.pixmap_item.mapToScene(pivot_local)
        delta = scene_before - scene_after
        if abs(delta.x()) > 1e-6 or abs(delta.y()) > 1e-6:
            self.pixmap_item.setPos(self.pixmap_item.pos() + delta)

    # ---- Loading ----
    def load_image(self, pixmap):
        self.scene.clear()
        self.pixmap_item = QGraphicsPixmapItem(pixmap)
        self.scene.addItem(self.pixmap_item)
        self.rotation_angle = 0.0
        self.interaction_mode = "NONE"
        self.active_handle = None
        self.last_mouse_pos = QPoint()
        self.rotation_start_angle = 0.0
        self.rotation_start_mouse_angle = 0.0
        self._rotation_pivot_local = None
        self._rotation_pre_drag_crop_w = None
        self.pixmap_item.setTransform(QTransform())
        self.pixmap_item.setRotation(0.0)
        self.pixmap_item.setTransformOriginPoint(self.pixmap_item.boundingRect().center())
        
        self._update_scene_rect()
        
        old_blocked = self.blockSignals(True)
        try:
            self.resetTransform()
            if self.norm_crop_rect == (0, 0, 1, 1):
                self.reset_crop_rect()
            self.update_fitting()
        finally:
            self.blockSignals(old_blocked)
        
        self.crop_changed.emit()
        self.viewport().update()

    def clear(self):
        self.scene.clear()
        self.pixmap_item = None
        self.preview_mode = False
        self.interaction_mode = "NONE"
        self.active_handle = None
        self.handles = {}
        self.rotation_handle_rect = QRectF()
        self.crop_rect = QRectF()
        self.rotation_angle = 0.0
        self.rotation_start_angle = 0.0
        self.rotation_start_mouse_angle = 0.0
        self._rotation_pivot_local = None
        self._rotation_pre_drag_crop_w = None
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
        if vp.width() <= 10 or vp.height() <= 10: # Minimum reasonable viewport
            return

        # Use 0.95 to make the border half as wide as the previous 0.90
        scale_factor = 0.95
        target_w = vp.width() * scale_factor
        target_h = vp.height() * scale_factor
        
        scale_w = target_w / max(1.0, rect.width())
        scale_h = target_h / max(1.0, rect.height())
        scale = min(scale_w, scale_h)
        
        # Prevent extreme scaling that could lead to floating point issues
        scale = max(1e-6, min(1e6, scale))
        
        self.scale(scale, scale)
        
        # Center on the rect in scene coordinates
        self.centerOn(rect.center())

    def update_fitting(self):
        """Refresh the scale and center based on current preview_mode."""
        if not self.pixmap_item:
            return
            
        vp = self.viewport().rect()
        if vp.width() <= 10 or vp.height() <= 10:
            return
            
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
            # Force viewport transform update before syncing crop
            self.sync_crop_to_viewport()
        
        self.viewport().update()

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
        if img_vp.width() < 1.0 or img_vp.height() < 1.0: return
        
        nx = (self.crop_rect.x() - img_vp.x()) / img_vp.width()
        ny = (self.crop_rect.y() - img_vp.y()) / img_vp.height()
        nw = self.crop_rect.width() / img_vp.width()
        nh = self.crop_rect.height() / img_vp.height()
        
        # Clamp normalized coordinates to reasonable range to prevent overflow in loader
        import math
        def clamp_norm(v):
            if not math.isfinite(v): return 0.0
            return max(-10.0, min(10.0, float(v)))
            
        self.norm_crop_rect = (clamp_norm(nx), clamp_norm(ny), clamp_norm(nw), clamp_norm(nh))

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
        self._shrink_crop_to_fit()
        self.sync_crop_from_viewport()
        self.crop_changed.emit()

    def set_aspect_ratio(self, ratio_str):
        old_blocked = self.blockSignals(True)
        try:
            if ":" in ratio_str:
                try:
                    w_str, h_str = ratio_str.split(":")
                    self.aspect_ratio = float(w_str) / float(h_str)
                except (ValueError, ZeroDivisionError):
                    self.aspect_ratio = 4/5
            
            self.reset_crop_rect()
            self.update_fitting()
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
        
        # Rotation handle at the long side
        is_vertical = r.height() > r.width()
        if is_vertical:
            # Right side
            handle_x = r.right() + 30
            self.rotation_handle_rect = QRectF(handle_x - hs/2, r.center().y() - hs/2, hs, hs)
        else:
            # Bottom side
            handle_y = r.bottom() + 30
            self.rotation_handle_rect = QRectF(r.center().x() - hs/2, handle_y - hs/2, hs, hs)

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
        for align, h_rect in self.handles.items():
            if self._is_handle_colliding(align):
                painter.setBrush(QBrush(QColor(60, 60, 60, 220)))
            else:
                painter.setBrush(QBrush(QColor(255, 255, 255, 200)))
            painter.setPen(QPen(QColor(0, 0, 0, 100), 1))
            painter.drawRect(h_rect)
            
        # Rotation handle - Dot only
        if not self.rotation_handle_rect.isNull():
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            is_vertical = cr.height() > cr.width()
            
            if is_vertical:
                # Connector line on right side
                painter.setPen(QPen(QColor(255, 255, 255, 100), 1))
                painter.drawLine(QPointF(cr.right(), cr.center().y()), self.rotation_handle_rect.center())
            else:
                # Connector line on bottom side
                painter.setPen(QPen(QColor(255, 255, 255, 100), 1))
                painter.drawLine(QPointF(cr.center().x(), cr.bottom()), self.rotation_handle_rect.center())
            
            # Handle Dot
            painter.setBrush(QBrush(QColor(255, 255, 255, 255)))
            painter.setPen(QPen(QColor(0, 0, 0, 150), 1))
            painter.drawEllipse(self.rotation_handle_rect)
        
        painter.restore()
        self._draw_nav_indicators(painter, vp)

    def _draw_nav_indicators(self, painter, vp):
        if not self.navigation_enabled:
            return
        if not self.hover_side:
            return
            
        painter.save()
        painter.resetTransform()
        
        # Indicator area width depends on mode (preview 20%, edit 5%).
        nav_w_ratio = self._nav_zone_ratio()
        w = vp.width() * nav_w_ratio
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
            
        # Custom colors based on mode
        if self.preview_mode:
            brush_color = QColor(150, 150, 150, 120)
            pen_color = QColor(100, 100, 100, 220)
        else:
            # Edit mode: Much darker overlay area and white arrow
            brush_color = QColor(0, 0, 0, 120)
            pen_color = QColor(255, 255, 255, 200)

        # Draw soft overlay
        painter.setBrush(brush_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(rect)
        
        # Draw arrow
        painter.setPen(QPen(pen_color, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolyline(arrow_points)
        
        painter.restore()

    def _nav_zone_ratio(self):
        return 0.2 if self.preview_mode else 0.05

    def set_navigation_enabled(self, enabled):
        enabled = bool(enabled)
        if self.navigation_enabled == enabled:
            return
        self.navigation_enabled = enabled
        if not enabled:
            self._hover_timer.stop()
            self._potential_hover = None
            self.hover_side = None
        self.viewport().update()
    
    def _try_navigation_click(self, pos):
        if not self.navigation_enabled:
            return False
        viewport_width = self.viewport().width()
        if viewport_width <= 0:
            return False
        zone = self._nav_zone_ratio()
        if pos.x() < viewport_width * zone:
            self.navigation_requested.emit(-1)
            return True
        elif pos.x() > viewport_width * (1 - zone):
            self.navigation_requested.emit(1)
            return True
        return False

    # ---- Transforms: rotate / mirror ----
    def rotate_image(self, angle, mouse_pos=None, absolute=False, snap_to_largest=False):
        """Rotate the image.
        
        If absolute=True, `angle` is the target rotation_angle directly.
        If absolute=False (default, used by 90° buttons), `angle` is a delta.
        """
        if not self.pixmap_item:
            return

        interactive_rotate = absolute and self.interaction_mode == "ROTATE"
        if absolute:
            target_angle = self._normalize_angle(angle)
        else:
            target_angle = self._normalize_angle(self.rotation_angle + angle)
        
        # Determine the pivot in local (pixmap) coordinates.
        # During interactive drag, use the locked local pivot directly;
        # otherwise recompute from the current crop center.
        if self._rotation_pivot_local is not None:
            pivot_local = self._rotation_pivot_local
        else:
            vt_inv = self.viewportTransform().inverted()[0]
            cr_center_s = vt_inv.map(self.crop_rect.center())
            pivot_local = self.pixmap_item.mapFromScene(cr_center_s)
        
        self._set_rotation_origin_keep_scene_point(pivot_local)
        self.rotation_angle = target_angle
        self.pixmap_item.setRotation(self.rotation_angle)
        
        # Update scene rect (base for fitting)
        self._update_scene_rect()
        
        # Fit / shrink crop to remain inside the rotated image.
        if snap_to_largest:
            self.reset_crop_rect()
        else:
            self._shrink_crop_to_fit()
        
        self.sync_crop_from_viewport()
        self._update_handles()

        # Keep the viewport transform fixed during drag-rotation.
        # Re-fitting while the cursor is moving changes coordinate space and causes jumpiness.
        if not interactive_rotate:
            self.update_fitting()
        self.crop_changed.emit()
        self.viewport().update()
    
    def _shrink_crop_to_fit(self):
        """Uniformly scale the crop rect around its center to fit within the rotated image.
        
        This can both *shrink* (if the crop overflows) and *grow back* (if the
        pre-drag crop size would now fit, e.g. when rotating back toward 0°).
        """
        if not self.pixmap_item:
            return
        
        center = self.crop_rect.center()
        
        # Determine the "goal" width: pre-drag pixel width if available,
        # otherwise the current crop width. Always derive height from
        # aspect_ratio to avoid distortion.
        if self._rotation_pre_drag_crop_w is not None:
            goal_w = self._rotation_pre_drag_crop_w
        else:
            goal_w = self.crop_rect.width()
        goal_w = max(20.0, goal_w)
        goal_h = goal_w / self.aspect_ratio
        
        # If the center is outside the image polygon, slide it towards
        # the polygon centroid just enough to be inside.
        center_probe = QRectF(center.x() - 1.0, center.y() - 1.0, 2.0, 2.0)
        if not self._is_crop_valid(center_probe):
            vt = self.viewportTransform()
            img_poly_s = self.pixmap_item.mapToScene(self.pixmap_item.boundingRect())
            img_poly_vp = vt.map(img_poly_s)
            poly_center = img_poly_vp.boundingRect().center()
            
            # Binary-search along center→poly_center for the first valid point
            lo_t, hi_t = 0.0, 1.0
            for _ in range(20):
                mid_t = (lo_t + hi_t) / 2
                test_pt = QPointF(
                    center.x() + (poly_center.x() - center.x()) * mid_t,
                    center.y() + (poly_center.y() - center.y()) * mid_t,
                )
                if self._is_crop_valid(QRectF(test_pt.x() - 1.0, test_pt.y() - 1.0, 2.0, 2.0)):
                    hi_t = mid_t
                else:
                    lo_t = mid_t
            center = QPointF(
                center.x() + (poly_center.x() - center.x()) * hi_t,
                center.y() + (poly_center.y() - center.y()) * hi_t,
            )
        
        # If the goal size already fits, just use it directly
        goal_rect = QRectF(center.x() - goal_w/2, center.y() - goal_h/2, goal_w, goal_h)
        if self._is_crop_valid(goal_rect):
            self.crop_rect = goal_rect
            return
        
        # Binary search for the largest scale ∈ (0, 1] of goal_size that fits
        low = 0.0
        high = 1.0
        best = low
        
        for _ in range(20):
            mid = (low + high) / 2
            test_w = max(20.0, goal_w * mid)
            test_h = test_w / self.aspect_ratio  # Always maintain AR
            test_rect = QRectF(center.x() - test_w/2, center.y() - test_h/2, test_w, test_h)
            if self._is_crop_valid(test_rect):
                best = mid
                low = mid
            else:
                high = mid
        
        final_w = max(20.0, goal_w * best)
        final_h = final_w / self.aspect_ratio  # Always maintain AR
        self.crop_rect = QRectF(center.x() - final_w/2, center.y() - final_h/2, final_w, final_h)

    def get_transform_state(self):
        """Returns (rotation, flip_h, flip_v) state."""
        if not self.pixmap_item:
            return 0, False, False
        
        rot = self.rotation_angle
        
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
            
        self.rotation_angle = self._normalize_angle(rotation)
        center = self.pixmap_item.boundingRect().center()
        self._set_rotation_origin_keep_scene_point(center)
        self.pixmap_item.setRotation(self.rotation_angle)
        
        t = QTransform()
        t.translate(center.x(), center.y())
        t.scale(-1 if flip_h else 1, -1 if flip_v else 1)
        t.translate(-center.x(), -center.y())
        self.pixmap_item.setTransform(t)
        self._rotation_pivot_local = None
        self._rotation_pre_drag_crop_w = None
        
        self._update_scene_rect()
        self._fit_to_viewport()
        # Note: caller should restore crop rect after this

    def reset_transforms(self):
        """Reset rotation to 0 and remove all flips."""
        if not self.pixmap_item:
            return
            
        self.rotation_angle = 0.0
        center = self.pixmap_item.boundingRect().center()
        self._set_rotation_origin_keep_scene_point(center)
        self.pixmap_item.setRotation(0.0)
        self.pixmap_item.setTransform(QTransform())
        self._rotation_pivot_local = None
        self._rotation_pre_drag_crop_w = None
        
        self._update_scene_rect()
        self.update_fitting()
        self.viewport().update()
        self.sync_crop_from_viewport()
        self.crop_changed.emit()

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
        self.update_fitting()
        self.preview_toggled.emit(self.preview_mode)

    # ---- Normalized crop <-> viewport ----
    def get_normalized_crop_rect(self):
        return self.norm_crop_rect

    def restore_crop_rect(self, norm_rect):
        self.norm_crop_rect = norm_rect
        self.update_fitting()
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
            
            if self._try_navigation_click(pos):
                self.last_mouse_pos = pos
                return
            
            # Use appropriate crop rect for bounds checking
            if self.preview_mode:
                active_crop = QRectF(self.mapFromScene(self.scene_crop_rect_for_preview).boundingRect())
            else:
                active_crop = QRectF(self.crop_rect)
            
            if not self.preview_mode:
                # 1. Check handles
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
                    
                # 2. Check rotation handle
                if self.rotation_handle_rect.contains(pos_f):
                    self.interaction_mode = "ROTATE"
                    self.rotation_start_angle = self.rotation_angle
                    
                    # Calculate initial mouse angle in SCENE coordinates for stability
                    vt_inv = self.viewportTransform().inverted()[0]
                    mouse_scene = vt_inv.map(pos_f)
                    cr_center_s = vt_inv.map(self.crop_rect.center())
                    dp_s = mouse_scene - cr_center_s
                    
                    self.rotation_start_mouse_angle = math.degrees(math.atan2(dp_s.y(), dp_s.x()))
                    
                    # Lock the pivot in pixmap-LOCAL coords so it's stable under rotation
                    self._rotation_pivot_local = self.pixmap_item.mapFromScene(cr_center_s)
                    # Remember pre-drag crop pixel width so we can grow back
                    self._rotation_pre_drag_crop_w = self.crop_rect.width()
                    self.last_mouse_pos = pos
                    return
            
            # 3. Check inside crop rect (Move)
            if active_crop.contains(pos_f):
                if not self.preview_mode:
                    self.interaction_mode = "MOVE_CROP"
                    self.setCursor(Qt.CursorShape.SizeAllCursor)
                self.last_mouse_pos = pos
                return

        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        pos = event.pos()
        pos_f = pos.toPointF()

        # Navigation hover detection
        vp_w = self.viewport().width()
        new_potential = None
        if self.navigation_enabled:
            nav_zone = self._nav_zone_ratio()
            if pos.x() < vp_w * nav_zone:
                new_potential = "LEFT"
            elif pos.x() > vp_w * (1 - nav_zone):
                new_potential = "RIGHT"
        else:
            self._hover_timer.stop()
            if self.hover_side:
                self.hover_side = None
                self.viewport().update()

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
        
        if self.interaction_mode == "RESIZE":
            self.resize_crop(pos)
            self.sync_crop_from_viewport()
            self.viewport().update()
        elif self.interaction_mode == "MOVE_CROP":
            self._move_crop(pos)
            self.sync_crop_from_viewport()
            self.viewport().update()
        elif self.interaction_mode == "ROTATE":
            # Calculate angles in stable SCENE coordinates
            vt_inv = self.viewportTransform().inverted()[0]
            mouse_scene = vt_inv.map(pos_f)
            
            # Use the LOCKED local pivot mapped to scene
            if self._rotation_pivot_local is not None:
                pivot_scene = self.pixmap_item.mapToScene(self._rotation_pivot_local)
                dp_s = mouse_scene - pivot_scene
            else:
                cr_center_s = vt_inv.map(self.crop_rect.center())
                dp_s = mouse_scene - cr_center_s
            
            current_mouse_angle = math.degrees(math.atan2(dp_s.y(), dp_s.x()))
            diff = current_mouse_angle - self.rotation_start_mouse_angle
            
            # Handle atan2 wrap-around at ±180
            if diff > 180: diff -= 360
            elif diff < -180: diff += 360
            
            target_angle = self.rotation_start_angle - diff
            self.rotate_image(target_angle, mouse_pos=pos, absolute=True)
            
            self.viewport().update()
        else:
            # Hover cursor
            hover = False
            for align, rect in self.handles.items():
                if QRectF(rect).contains(pos_f):
                    self.setCursor(self._get_cursor_for_align(align))
                    hover = True
                    break
            if not hover:
                if self.rotation_handle_rect.contains(pos_f):
                    self.setCursor(Qt.CursorShape.CrossCursor)
                    hover = True
                elif QRectF(self.crop_rect).contains(pos_f):
                    self.setCursor(Qt.CursorShape.SizeAllCursor)
                else:
                    self.setCursor(Qt.CursorShape.ArrowCursor)
        
        self.last_mouse_pos = pos

    def mouseReleaseEvent(self, event):
        if self.preview_mode:
            return
        was_rotating = self.interaction_mode == "ROTATE"
        self.interaction_mode = "NONE"
        self.active_handle = None
        # Clear drag-local rotation state
        self._rotation_pivot_local = None
        self._rotation_pre_drag_crop_w = None
        if was_rotating and self.pixmap_item:
            # Refit once at drag end (instead of every frame) to keep interaction stable.
            self.update_fitting()
            self.sync_crop_from_viewport()
            self._update_handles()
            self.crop_changed.emit()
        self.setCursor(Qt.CursorShape.ArrowCursor)
        super().mouseReleaseEvent(event)

    def _is_crop_valid(self, rect_vp):
        """Check if the given crop rect in viewport is within the rotated image path."""
        if not self.pixmap_item:
            return True
        if rect_vp.width() <= 0.0 or rect_vp.height() <= 0.0:
            return False
            
        # Get image boundary in scene coordinates as a QPainterPath for robustness
        img_poly_s = self.pixmap_item.mapToScene(self.pixmap_item.boundingRect())
        path = QPainterPath()
        path.addPolygon(img_poly_s)
        
        # Add a tiny 0.1 pixel buffer to the image path to handle float precision near 90/180/270
        # Actually, let's just use the path as is but ensure points are mapped correctly
        
        # Inset the crop rect by a small margin to avoid edge precision issues
        margin = min(1.0, rect_vp.width() * 0.25, rect_vp.height() * 0.25)
        if margin > 0.0 and rect_vp.width() > (2.0 * margin) and rect_vp.height() > (2.0 * margin):
            inset_rect = rect_vp.adjusted(margin, margin, -margin, -margin)
        else:
            inset_rect = QRectF(rect_vp)
        inset_rect = inset_rect.normalized()
        
        # Map each corner individually using the full viewport transform
        corners_vp = [
            inset_rect.topLeft(),
            inset_rect.topRight(),
            inset_rect.bottomRight(),
            inset_rect.bottomLeft(),
            inset_rect.center() # Definitely check the center too
        ]
        
        vt_inv = self.viewportTransform().inverted()[0]
        
        for corner in corners_vp:
            scene_pt = vt_inv.map(corner)
            if not path.contains(scene_pt):
                return False
        return True

    def _get_corner_probe_data(self, align):
        """Return corner point and outward axis directions for the given handle."""
        if not self.pixmap_item or self.crop_rect.isNull():
            return None
        r = self.crop_rect
        if align == (Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft):
            return r.topLeft(), -1.0, -1.0
        elif align == (Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight):
            return r.topRight(), 1.0, -1.0
        elif align == (Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft):
            return r.bottomLeft(), -1.0, 1.0
        elif align == (Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight):
            return r.bottomRight(), 1.0, 1.0
        return None

    def _is_point_inside_image(self, point_vp):
        if not self.pixmap_item:
            return True
        img_poly_s = self.pixmap_item.mapToScene(self.pixmap_item.boundingRect())
        path = QPainterPath()
        path.addPolygon(img_poly_s)
        vt_inv = self.viewportTransform().inverted()[0]
        return path.contains(vt_inv.map(point_vp))

    def _is_handle_colliding(self, align):
        """Corner is colliding if both outward axis probes are blocked."""
        probe = self._get_corner_probe_data(align)
        if probe is None:
            return False

        epsilon = 0.35
        corner, dir_x, dir_y = probe
        probe_x = QPointF(corner.x() + (epsilon * dir_x), corner.y())
        probe_y = QPointF(corner.x(), corner.y() + (epsilon * dir_y))
        x_blocked = not self._is_point_inside_image(probe_x)
        y_blocked = not self._is_point_inside_image(probe_y)
        colliding = x_blocked and y_blocked

        return colliding

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
        
        # Check if new position is valid
        if self._is_crop_valid(new_rect):
            self.crop_rect = new_rect
        else:
            # Try moving only X or Y
            rect_x = self.crop_rect.translated(delta.x(), 0)
            if self._is_crop_valid(rect_x):
                self.crop_rect = rect_x
            else:
                rect_y = self.crop_rect.translated(0, delta.y())
                if self._is_crop_valid(rect_y):
                    self.crop_rect = rect_y
        
        self._update_handles()
        self.crop_changed.emit()

    # ---- Crop resize ----
    def resize_crop(self, pos):
        if not self.pixmap_item:
            return
        
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
        
        # Desired width from mouse position, maintaining aspect ratio
        desired_w = max(abs(dx), 10.0)
        desired_h = desired_w / self.aspect_ratio
        
        # Build desired rect
        test_x = fixed.x() + (desired_w * dir_x)
        test_y = fixed.y() + (desired_h * dir_y)
        desired_rect = QRectF(fixed, QPointF(test_x, test_y)).normalized()
        
        if self._is_crop_valid(desired_rect):
            self.crop_rect = desired_rect
        else:
            # Binary search for the largest valid size
            low = 10.0
            high = desired_w
            best_w = low
            
            for _ in range(15):
                mid = (low + high) / 2
                test_h = mid / self.aspect_ratio
                test_x = fixed.x() + (mid * dir_x)
                test_y = fixed.y() + (test_h * dir_y)
                test_rect = QRectF(fixed, QPointF(test_x, test_y)).normalized()
                
                if self._is_crop_valid(test_rect):
                    best_w = mid
                    low = mid
                else:
                    high = mid
            
            final_w = best_w
            final_h = final_w / self.aspect_ratio
            final_x = fixed.x() + (final_w * dir_x)
            final_y = fixed.y() + (final_h * dir_y)
            self.crop_rect = QRectF(fixed, QPointF(final_x, final_y)).normalized()
        
        self._update_handles()
        self.crop_changed.emit()

    # ---- Resize event: re-fit when window resizes ----
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_fitting()
        self.crop_changed.emit()

    def leaveEvent(self, event):
        self._hover_timer.stop()
        self._potential_hover = None
        if self.hover_side:
            self.hover_side = None
            self.viewport().update()
        super().leaveEvent(event)
