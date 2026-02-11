from PySide6.QtWidgets import (QDialog, QVBoxLayout, QProgressBar, QLabel,
                             QPushButton, QHBoxLayout)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
import os
from core.processor import process_image

class ProcessingWorker(QThread):
    progress = Signal(int, str)  # current index, filename
    finished = Signal(int, str)  # total processed, output directory
    error = Signal(str)          # error message

    def __init__(self, tasks, downsample, target_res, res_mode):
        super().__init__()
        self.tasks = tasks
        self.downsample = downsample
        self.target_res = target_res
        self.res_mode = res_mode
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        processed_count = 0
        output_dir = ""
        
        for i, task in enumerate(self.tasks):
            if self._is_cancelled:
                break
                
            path = task['path']
            crop = task['crop']
            out_path = task['out_path']
            rot = task.get('rotation', 0)
            fh = task.get('flip_h', False)
            fv = task.get('flip_v', False)
            
            filename = os.path.basename(path)
            self.progress.emit(i, filename)
            
            success = process_image(path, crop, out_path, 
                                   downsample=self.downsample, 
                                   target_res=self.target_res, 
                                   res_mode=self.res_mode,
                                   rotation=rot, flip_h=fh, flip_v=fv)
            
            if success:
                processed_count += 1
                output_dir = os.path.dirname(out_path)
            
        if not self._is_cancelled:
            self.finished.emit(processed_count, output_dir)

class ProcessingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Processing Images")
        self.setFixedSize(520, 220)
        self.setModal(True)
        # Prevent closing with X during processing
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint)

        layout = QVBoxLayout(self)
        
        self.label = QLabel("Starting...")
        layout.addWidget(self.label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        
        self.btn_layout = QHBoxLayout()
        layout.addLayout(self.btn_layout)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        self.btn_layout.addWidget(self.cancel_btn)

        self.instagram_btn = QPushButton("Take a look")
        self.instagram_btn.setFixedHeight(24)
        self.instagram_btn.hide()
        self.instagram_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://www.instagram.com/juengerkuehn/"))
        )
        self.btn_layout.addWidget(self.instagram_btn)
        
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        self.close_btn.setEnabled(False)
        self.close_btn.hide()
        self.btn_layout.addWidget(self.close_btn)
        
        self.worker = None

    def start_processing(self, tasks, downsample, target_res, res_mode):
        self.progress_bar.setMaximum(len(tasks))
        self.progress_bar.setValue(0)
        
        self.worker = ProcessingWorker(tasks, downsample, target_res, res_mode)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.on_finished)
        self.worker.error.connect(self.on_error)
        self.worker.start()

    def update_progress(self, index, filename):
        self.progress_bar.setValue(index + 1)
        self.label.setText(f"Processing: {filename}")
        self.status_label.setText(f"Image {index + 1} of {self.progress_bar.maximum()}")

    def on_finished(self, count, out_dir):
        self.label.setText("Processing Complete!")
        self.status_label.setText(
            f"Processed {count} images to:\n{out_dir}\n\n"
            "Thanks for using QuickCrop. We also design objects and explore digital craft: @juengerkuehn"
        )
        self.cancel_btn.hide()
        self.instagram_btn.show()
        self.close_btn.show()
        self.close_btn.setEnabled(True)
        # Enable X button again if needed, or just let them use Close button
        # self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowCloseButtonHint)
        # self.show() # To apply flags change

    def on_error(self, message):
        self.label.setText("Error during processing")
        self.status_label.setText(message)
        self.cancel_btn.setText("Close")
        
    def reject(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait()
        super().reject()
