from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QDockWidget, QToolBar, QComboBox, QPushButton, QFileDialog)
from PyQt6.QtCore import Qt, QSize, QTimer
from ui.image_list import ImageList
from ui.camera_roll import CameraRoll
from ui.canvas import Canvas
from core.image_cache import ImageCache

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Instagram Crop Tool")
        self.resize(1200, 800)

        # Central Widget (Sort of, actually using Layouts)
        self.central_widget = QWidget()
        self.central_widget.setStyleSheet("background-color: white;")
        self.setCentralWidget(self.central_widget)
        
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(15)
        
        # Toolbar (Custom Layout)
        self.create_toolbar_layout()
        
        self.content_layout = QHBoxLayout()
        self.content_layout.setSpacing(20)
        self.main_layout.addLayout(self.content_layout)
        
        # Left Panel - Image List
        left_panel_layout = QVBoxLayout()
        self.content_layout.addLayout(left_panel_layout)
        
        self.image_list = ImageList()
        left_panel_layout.addWidget(self.image_list)
        
        # Clear Images Button
        self.clear_btn = QPushButton("Clear Images")
        self.clear_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.clear_btn.clicked.connect(self.clear_images)
        left_panel_layout.addWidget(self.clear_btn)
        
        # Center - Canvas
        self.canvas = Canvas()
        self.content_layout.addWidget(self.canvas, stretch=1)
        
        # Right Panel - Tools
        right_panel = QVBoxLayout()
        self.content_layout.addLayout(right_panel)
        
        self.rotate_l_btn = QPushButton("Rot L")
        self.rotate_l_btn.setFixedSize(60, 40)
        self.rotate_l_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.rotate_l_btn.clicked.connect(lambda: self.canvas.rotate_image(-90))
        right_panel.addWidget(self.rotate_l_btn)
        
        self.rotate_r_btn = QPushButton("Rot R")
        self.rotate_r_btn.setFixedSize(60, 40)
        self.rotate_r_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.rotate_r_btn.clicked.connect(lambda: self.canvas.rotate_image(90))
        right_panel.addWidget(self.rotate_r_btn)
        
        right_panel.addSpacing(20)
        
        self.mirror_h_btn = QPushButton("Flip H")
        self.mirror_h_btn.setFixedSize(60, 40)
        self.mirror_h_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.mirror_h_btn.clicked.connect(lambda: self.canvas.mirror_image(True, False))
        right_panel.addWidget(self.mirror_h_btn)
        
        self.mirror_v_btn = QPushButton("Flip V")
        self.mirror_v_btn.setFixedSize(60, 40)
        self.mirror_v_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.mirror_v_btn.clicked.connect(lambda: self.canvas.mirror_image(False, True))
        right_panel.addWidget(self.mirror_v_btn)
        
        right_panel.addSpacing(20)
        
        self.skip_btn = QPushButton("Skip")
        self.skip_btn.setFixedSize(60, 40)
        self.skip_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.skip_btn.clicked.connect(self._toggle_skip_current)
        right_panel.addWidget(self.skip_btn)
        
        self.remove_btn = QPushButton("Remove")
        self.remove_btn.setFixedSize(60, 40)
        self.remove_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.remove_btn.clicked.connect(self._remove_current)
        right_panel.addWidget(self.remove_btn)
        
        right_panel.addStretch()

        
        # Bottom - Camera Roll
        self.camera_roll = CameraRoll()
        self.main_layout.addWidget(self.camera_roll)
        
        # Connect signals
        self.image_list.image_selected.connect(self.display_image)
        self.camera_roll.image_selected.connect(self.display_image)
        self.canvas.crop_changed.connect(self._on_crop_changed)
        self.canvas.preview_toggled.connect(self.preview_btn.setChecked)
        self.canvas.navigation_requested.connect(self.navigate)
        self.camera_roll.itemDoubleClicked.connect(self._on_camera_roll_double_clicked)
        
        # Debounce timer for thumbnail updates
        self.thumb_update_timer = QTimer()
        self.thumb_update_timer.setSingleShot(True)
        self.thumb_update_timer.timeout.connect(self._refresh_thumbnail)
        
        # State tracking
        self.current_image_path = None
        self.all_paths = []
        self.path_to_index = {} # path -> index
        self.path_to_dims = {}  # path -> (w, h)

        self.image_data = {} # path -> {'crop': (nx, ny, nw, nh), 'ratio': str, 'touched': bool}
        self.hidden_paths = set()
        
        # Timer for marking image as touched
        self.touch_timer = QTimer()
        self.touch_timer.setSingleShot(True)
        self.touch_timer.setInterval(1000)
        self.touch_timer.timeout.connect(self._mark_current_as_touched)
        
        # Settings
        from PyQt6.QtCore import QSettings
        self.settings = QSettings("Konrad", "InstagramCropTool")
        self.output_dir = self.settings.value("output_dir", "")
        
        # Navigation buffering
        self._pending_nav_direction = 0
        self._nav_timer = QTimer()
        self._nav_timer.setSingleShot(True)
        self._nav_timer.setInterval(20)  # 20ms window to batch clicks
        self._nav_timer.timeout.connect(self._process_pending_nav)
        
        # Performance: Image Cache
        self.image_cache = ImageCache(proxy_window=15)
        self.image_cache.image_ready.connect(self._on_image_cached)
        
        # Global Event Filter for Arrow Keys
        from PyQt6.QtWidgets import QApplication
        QApplication.instance().installEventFilter(self)
        
    def create_toolbar_layout(self):
        toolbar_layout = QHBoxLayout()
        self.main_layout.addLayout(toolbar_layout)
        
        # Load Images Action
        self.load_btn = QPushButton("Load Images")
        self.load_btn.setFixedSize(100, 30)
        self.load_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.load_btn.clicked.connect(self.load_images_dialog)
        toolbar_layout.addWidget(self.load_btn)
        
        # Set Output Folder
        self.out_btn = QPushButton("Set Output")
        self.out_btn.setFixedSize(100, 30)
        self.out_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.out_btn.clicked.connect(self.set_output_folder)
        toolbar_layout.addWidget(self.out_btn)

        # Preview All Toggle
        self.preview_btn = QPushButton("Preview Mode")
        self.preview_btn.setCheckable(True)
        self.preview_btn.setChecked(True)
        self.preview_btn.setFixedSize(100, 30)
        self.preview_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.preview_btn.setStyleSheet("""
            QPushButton:checked {
                background-color: #0078d7;
                color: white;
                font-weight: bold;
            }
        """)
        self.preview_btn.clicked.connect(self.toggle_preview_mode)
        toolbar_layout.addWidget(self.preview_btn)

        
        # Vertical Separator logic (frame)
        from PyQt6.QtWidgets import QFrame
        line1 = QFrame()
        line1.setFrameShape(QFrame.Shape.VLine)
        line1.setFrameShadow(QFrame.Shadow.Sunken)
        toolbar_layout.addWidget(line1)
        
        # Aspect Ratio Combo
        self.aspect_combo = QComboBox()
        self.aspect_combo.addItems(["1:1", "4:5", "9:16"])
        self.aspect_combo.setCurrentText("4:5")
        self.aspect_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.aspect_combo.currentTextChanged.connect(self.update_aspect_ratio)

        toolbar_layout.addWidget(self.aspect_combo)
        
        line2 = QFrame()
        line2.setFrameShape(QFrame.Shape.VLine)
        line2.setFrameShadow(QFrame.Shadow.Sunken)
        toolbar_layout.addWidget(line2)
        
        # Output Resolution
        from PyQt6.QtWidgets import QSpinBox, QLabel
        toolbar_layout.addWidget(QLabel(" Width: "))
        self.res_spin = QSpinBox()
        self.res_spin.setRange(100, 10000)
        self.res_spin.setValue(1080)
        self.res_spin.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        toolbar_layout.addWidget(self.res_spin)
        
        line3 = QFrame()
        line3.setFrameShape(QFrame.Shape.VLine)
        line3.setFrameShadow(QFrame.Shadow.Sunken)
        toolbar_layout.addWidget(line3)
        
        # Process All Action
        self.process_btn = QPushButton("Process All")
        self.process_btn.setFixedSize(100, 30)
        self.process_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.process_btn.clicked.connect(self.process_all)
        toolbar_layout.addWidget(self.process_btn)
        
        # Spacer
        toolbar_layout.addStretch()

    def load_images_dialog(self):
        last_dir = self.settings.value("last_input_dir", "")
        files, _ = QFileDialog.getOpenFileNames(self, "Select Images", last_dir, "Images (*.jpg *.jpeg *.png *.tif *.tiff)")
        if files:
            import os
            self.settings.setValue("last_input_dir", os.path.dirname(files[0]))
            self.load_images_list(files)

    def set_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder", self.output_dir)
        if folder:
            self.output_dir = folder
            self.settings.setValue("output_dir", folder)

    def load_images_list(self, images):
        import os
        from ui.image_info_loader import ImageInfoLoader
        
        # Don't reset state if we have existing images
        if not self.all_paths:
             self.image_data = {}
             self.current_image_path = None

        # Determine which images are actually new
        new_images = [img for img in images if img not in self.path_to_index]
        if not new_images:
            return

        # Start background info loading for and set up placeholder state
        for img_path in new_images:
            filename = os.path.basename(img_path)
            
            # Immediately add to list with "Loading..." or similar if desired
            # But for now just add to internal tracking
            self.path_to_index[img_path] = len(self.all_paths)
            self.all_paths.append(img_path)
            
            # Add to UI components immediately (placeholders)
            self.image_list.add_image(filename, img_path)
            self.camera_roll.add_image(filename, img_path) # No crop yet
            
            # Start background dimension fetch
            info_worker = ImageInfoLoader(img_path)
            info_worker.signals.finished.connect(self._on_image_info_loaded)
            self.camera_roll.thread_pool.start(info_worker)
            
        # Display the first of the newly added images if nothing is selected
        if not self.current_image_path:
            self.display_image(new_images[0])

    def _on_image_info_loaded(self, path, w, h):
        from core.processor import calculate_default_crop
        
        self.path_to_dims[path] = (w, h)
        
        # Calculate initial crop now that we have dimensions
        ratio_str = self.aspect_combo.currentText()
        default_crop = calculate_default_crop(w, h, ratio_str)
        
        if path not in self.image_data:
            self.image_data[path] = {
                'crop': default_crop,
                'ratio': ratio_str,
                'touched': True # Default to touched for initial auto-crop
            }
        
        # Update camera roll thumbnail with the correct default crop
        self.camera_roll.update_thumbnail(path, default_crop)
        
        # If this is the current image, update canvas too
        if path == self.current_image_path:
            self.canvas.set_aspect_ratio(ratio_str)
            self.canvas.restore_crop_rect(default_crop)

    def save_current_state(self):
        if self.current_image_path:
            norm_rect = self.canvas.get_normalized_crop_rect()
            ratio = self.aspect_combo.currentText()
            touched = self.image_data.get(self.current_image_path, {}).get('touched', False)
            
            rot, fh, fv = self.canvas.get_transform_state()
            
            self.image_data[self.current_image_path] = {
                'crop': norm_rect,
                'ratio': ratio,
                'touched': touched,
                'rotation': rot,
                'flip_h': fh,
                'flip_v': fv
            }

    def display_image(self, path):
        if self.current_image_path == path:
            return
            
        # Save previous
        self.save_current_state()
        
        self.current_image_path = path

        # Sync selection in lists
        self.sync_selection(path)
        
        # Try Cache
        cached_image, is_full = self.image_cache.get_image(path)
        
        if cached_image:
            from PyQt6.QtGui import QPixmap
            pixmap = QPixmap.fromImage(cached_image)
            self.canvas.load_image(pixmap)
        else:
            # NO synchronous fallback. Clear canvas and wait for cache signal.
            self.canvas.clear()
        
        # Update Cache Window
        self.image_cache.update_window(path, self.all_paths)
            
        # Restore state or default
        if path in self.image_data:
            data = self.image_data[path]
            self.aspect_combo.setCurrentText(data['ratio'])
            # Force update canvas ratio immediately before restoring rect
            self.canvas.set_aspect_ratio(data['ratio'])
            
            # Restore Transform
            rot = data.get('rotation', 0)
            fh = data.get('flip_h', False)
            fv = data.get('flip_v', False)
            self.canvas.set_transform_state(rot, fh, fv)
            
            self.canvas.restore_crop_rect(data['crop'])
        else:
            # Default: just set aspect ratio, canvas center it by default
            self.canvas.set_aspect_ratio(self.aspect_combo.currentText())
            # Initialize image data WITHOUT a crop rect yet - let canvas set default
            self.image_data[path] = {
                'touched': False, 
                'ratio': self.aspect_combo.currentText()
            }
            
        # Refresh thumbnail based on touched state
        if self.image_data[path].get('touched', False):
            self._refresh_thumbnail()
        else:
            self.camera_roll.refresh_thumbnail(path)

        # Start timer to mark as touched
        if not self.image_data[path].get('touched', False):
            self.touch_timer.start()

        # Global Preview Persistence
        if self.preview_btn.isChecked():
            if not self.canvas.preview_mode:
                self.canvas.toggle_preview()
        else:
            if self.canvas.preview_mode:
                self.canvas.toggle_preview()

        # Sync Skip button text
        if path in self.hidden_paths:
            self.skip_btn.setText("Unskip")
        else:
            self.skip_btn.setText("Skip")

    def update_aspect_ratio(self, text):
        self.canvas.set_aspect_ratio(text)
        self.camera_roll.set_aspect_ratio(text)
        
        from core.processor import calculate_default_crop
        
        for path in self.all_paths:
            if path in self.path_to_dims:
                w, h = self.path_to_dims[path]
                new_crop = calculate_default_crop(w, h, text)
                
                if path not in self.image_data:
                    self.image_data[path] = {}
                self.image_data[path]['crop'] = new_crop
                self.image_data[path]['ratio'] = text
                
                self.camera_roll.update_thumbnail(path, new_crop)
            else:
                # If dimensions not loaded yet, the _on_image_info_loaded signal will handle it
                if path not in self.image_data:
                    self.image_data[path] = {}
                self.image_data[path]['ratio'] = text
        
    def eventFilter(self, watched, event):
        from PyQt6.QtCore import QEvent, Qt
        if event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_J, Qt.Key.Key_K):
                # Navigate image list
                direction = 1
                if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_J):
                    direction = -1
                
                self.navigate(direction)
                return True # Stop event here
            
            elif event.key() in (Qt.Key.Key_Up, Qt.Key.Key_I):
                self._toggle_skip_current()
                return True
            
            elif event.key() in (Qt.Key.Key_O, Qt.Key.Key_Backspace):
                self._remove_current()
                return True
            
            elif event.key() == Qt.Key.Key_L:
                self.canvas.reset_crop_rect()
                self.canvas.viewport().update()
                self._on_crop_changed()
                return True
            
            elif event.key() == Qt.Key.Key_Space:
                self.preview_btn.setChecked(not self.preview_btn.isChecked())
                self.toggle_preview_mode(self.preview_btn.isChecked())
                return True
                
        return super().eventFilter(watched, event)

    def navigate(self, direction):
        """Buffer navigation requests to handle rapid clicks."""
        self._pending_nav_direction += direction
        self._nav_timer.start()

    def _process_pending_nav(self):
        """Apply aggregated navigation requests."""
        direction = self._pending_nav_direction
        self._pending_nav_direction = 0
        
        if direction == 0:
            return

        current_row = self.image_list.currentRow()
        if current_row == -1:
            if self.image_list.count() > 0:
                current_row = 0
            else:
                return

        # Find target row by stepping one by one to handle skips correctly
        target_row = current_row
        steps_to_take = abs(direction)
        step = 1 if direction > 0 else -1
        count = self.image_list.count()
        
        # Avoid infinite loop if all images are hidden or only one remains
        non_hidden_count = count - len(self.hidden_paths)
        if non_hidden_count <= 0:
            return

        # Cap steps to take to avoid multiple unnecessary loops
        # (Though with 20ms buffer it's unlikely to be huge)
        steps_to_take %= non_hidden_count
        if steps_to_take == 0 and abs(direction) > 0:
            # If we navigated exactly one full circle of visible images, just stay here.
            # But usually we at least want to move if it's a single click.
            if abs(direction) < non_hidden_count:
                steps_to_take = abs(direction)
            else:
                return

        while steps_to_take > 0:
            target_row = (target_row + step) % count
            # If this image is skipped, we don't count it as a "step"
            path = self.image_list.item(target_row).data(100)
            if path not in self.hidden_paths:
                steps_to_take -= 1
        
        if target_row != current_row:
            self.image_list.setCurrentRow(target_row)
            item = self.image_list.item(target_row)
            path = item.data(100)
            self.display_image(path)

    def keyPressEvent(self, event):
        # This is now mostly a fallback as eventFilter should catch the main keys
        super().keyPressEvent(event)
                
    def process_all(self):
        # Save current first
        self.save_current_state()
        
        from core.processor import process_image
        import os
        from PyQt6.QtWidgets import QMessageBox
        
        count = self.image_list.count()
        if count == 0: return

        # Output folder logic
        out_dir = self.output_dir
        if not out_dir:
            # Fallback to source dir / cropped if not set
            first_item = self.image_list.item(0)
            first_path = first_item.data(100)
            source_dir = os.path.dirname(first_path)
            out_dir = os.path.join(source_dir, "cropped")
            
        if not os.path.exists(out_dir):
            try:
                os.makedirs(out_dir)
            except OSError:
                QMessageBox.critical(self, "Error", f"Could not create output directory: {out_dir}")
                return
        
        width = self.res_spin.value()
        
        print("Starting processing...")
        processed_count = 0
        for i in range(count):
            item = self.image_list.item(i)
            path = item.data(100)
            
            if path in self.hidden_paths:
                continue

            # Get crop data
            if path in self.image_data and 'crop' in self.image_data[path]:
                crop = self.image_data[path]['crop']
            else:
                # Use centralized helper for default
                try:
                    from PIL import Image, ImageOps
                    from core.processor import calculate_default_crop
                    with Image.open(path) as img:
                        img = ImageOps.exif_transpose(img)
                        w, h = img.size
                        ratio_str = self.aspect_combo.currentText()
                        
                        # Note: calculate_default_crop assumes original orientation
                        # If we had rotation saved, we might need a more complex default
                        crop = calculate_default_crop(w, h, ratio_str)
                except Exception as e:
                    print(f"Error calculating default crop for processing {path}: {e}")
                    continue
            
            filename = os.path.basename(path)
            out_path = os.path.join(out_dir, filename)
            
            # Get transform state
            rot = self.image_data.get(path, {}).get('rotation', 0)
            fh = self.image_data.get(path, {}).get('flip_h', False)
            fv = self.image_data.get(path, {}).get('flip_v', False)
            
            success = process_image(path, crop, out_path, width, rotation=rot, flip_h=fh, flip_v=fv)
            if success:
                print(f"Processed {filename}")
                processed_count += 1
            else:
                print(f"Failed {filename}")
                
        QMessageBox.information(self, "Processing Complete", f"Processed {processed_count} images to {out_dir}")



    def clear_images(self):
        self.image_list.clear()
        self.camera_roll.clear()
        self.image_cache.clear()
        self.image_data = {}
        self.current_image_path = None
        self.all_paths = []
        self.path_to_index = {}
        self.hidden_paths = set()
        self.canvas.clear()
        
    def toggle_preview_mode(self, checked):
        # Update Canvas state to match the global toggle
        if checked != self.canvas.preview_mode:
            self.canvas.toggle_preview()
        self.canvas.viewport().update()

    def sync_selection(self, path):
        if path not in self.path_to_index:
            return
            
        idx = self.path_to_index[path]
        
        # Sync Image List
        if 0 <= idx < self.image_list.count():
            item = self.image_list.item(idx)
            self.image_list.setCurrentItem(item)
            self.image_list.scrollToItem(item)
                
        # Sync Camera Roll
        if 0 <= idx < self.camera_roll.count():
            item = self.camera_roll.item(idx)
            self.camera_roll.setCurrentItem(item)
            self.camera_roll.scrollToItem(item)

    def _on_camera_roll_double_clicked(self, item):
        path = item.data(100)
        self.toggle_hide(path)
        # Update Skip button if current image changed state
        if path == self.current_image_path:
            self.skip_btn.setText("Unskip" if path in self.hidden_paths else "Skip")

    def _on_image_cached(self, path, image, is_full):
        # If the newly cached image is the one we are currently trying to display, update canvas
        if path == self.current_image_path:
            # If we already have a full image, don't downgrade to a proxy
            if not is_full:
                existing_img, existing_is_full = self.image_cache.get_image(path)
                if existing_is_full and existing_img:
                    return

            from PyQt6.QtGui import QPixmap
            pixmap = QPixmap.fromImage(image)
            self.canvas.load_image(pixmap)
            
            # Restore state (since display_image might have been called but skipped load_image)
            if path in self.image_data:
                data = self.image_data[path]
                ratio = data.get('ratio', self.aspect_combo.currentText())
                self.canvas.set_aspect_ratio(ratio)
                
                # Restore Transform
                rot = data.get('rotation', 0)
                fh = data.get('flip_h', False)
                fv = data.get('flip_v', False)
                self.canvas.set_transform_state(rot, fh, fv)

                # Only restore if we have valid crop data AND the image was already touched/saved
                # This prevents "stub" crops from being applied to fresh images
                if 'crop' in data and data.get('touched', False):
                    self.canvas.restore_crop_rect(data['crop'])
                
                # Update thumbnail if touched
                if data.get('touched', False):
                    self._refresh_thumbnail()
            else:
                self.canvas.set_aspect_ratio(self.aspect_combo.currentText())

            # Respect global preview mode
            if self.preview_btn.isChecked() and not self.canvas.preview_mode:
                self.canvas.toggle_preview()

    def _on_crop_changed(self):
        # Mark as touched if not already
        if self.current_image_path:
            if self.current_image_path not in self.image_data:
                 self.image_data[self.current_image_path] = {
                    'touched': True,
                    'crop': self.canvas.get_normalized_crop_rect(),
                    'ratio': self.aspect_combo.currentText()
                }
            else:
                self.image_data[self.current_image_path]['touched'] = True
        
        # Debounce to avoid too many updates while dragging
        self.thumb_update_timer.start(300)

    def _mark_current_as_touched(self):
        if self.current_image_path and self.canvas.pixmap_item:
            # Only act if the canvas actually has an image loaded
            # (prevents capturing stub crop from an empty/initializing canvas)
            
            # Ensure path exists in data
            if self.current_image_path not in self.image_data:
                 self.image_data[self.current_image_path] = {
                    'ratio': self.aspect_combo.currentText()
                }
            
            # NOW capture the crop rect (canvas is guaranteed to be ready after 1s)
            self.image_data[self.current_image_path]['crop'] = self.canvas.get_normalized_crop_rect()
            rot, fh, fv = self.canvas.get_transform_state()
            self.image_data[self.current_image_path]['rotation'] = rot
            self.image_data[self.current_image_path]['flip_h'] = fh
            self.image_data[self.current_image_path]['flip_v'] = fv
            self.image_data[self.current_image_path]['touched'] = True
            
            # Refresh thumbnail to switch to crop AR
            self._refresh_thumbnail()

    def _refresh_thumbnail(self):
        if self.current_image_path:
            norm_rect = self.canvas.get_normalized_crop_rect()
            self.camera_roll.update_thumbnail(self.current_image_path, norm_rect)

    def _toggle_skip_current(self):
        if self.current_image_path:
            self.toggle_hide(self.current_image_path)
            # Update button text
            if self.current_image_path in self.hidden_paths:
                self.skip_btn.setText("Unskip")
            else:
                self.skip_btn.setText("Skip")

    def _remove_current(self):
        if self.current_image_path:
            self.remove_image(self.current_image_path)

    def toggle_hide(self, path):
        if path in self.hidden_paths:
            self.hidden_paths.remove(path)
            hidden = False
        else:
            self.hidden_paths.add(path)
            hidden = True
        
        # Update Camera Roll Visuals
        self.camera_roll.set_hidden(path, hidden)
        
        # Update Image List Visuals
        if path in self.path_to_index:
            idx = self.path_to_index[path]
            item = self.image_list.item(idx)
            if hidden:
                font = item.font()
                font.setStrikeOut(True)
                item.setFont(font)
                item.setForeground(Qt.GlobalColor.gray)
            else:
                font = item.font()
                font.setStrikeOut(False)
                item.setFont(font)
                item.setForeground(Qt.GlobalColor.black)

    def remove_image(self, path):
        if path not in self.path_to_index:
            return
            
        # Is it the current image?
        if self.current_image_path == path:
            # Try to select next image
            idx = self.path_to_index[path]
            next_path = None
            if idx + 1 < len(self.all_paths):
                next_path = self.all_paths[idx + 1]
            elif idx - 1 >= 0:
                next_path = self.all_paths[idx - 1]
                
            if next_path:
                self.display_image(next_path)
            else:
                self.canvas.clear()
                self.current_image_path = None

        # Remove from internal lists
        old_idx = self.path_to_index[path]
        self.all_paths.pop(old_idx)
        if path in self.hidden_paths:
            self.hidden_paths.remove(path)
        if path in self.image_data:
            del self.image_data[path]
            
        # Rebuild path_to_index
        self.path_to_index = {p: i for i, p in enumerate(self.all_paths)}
        
        # Update UI components
        # Image list
        item = self.image_list.takeItem(old_idx)
        del item
        
        # Camera roll
        self.camera_roll.remove_path(path)
        
        # Sync selection if we moved to next
        if self.current_image_path:
            self.sync_selection(self.current_image_path)
