from PyQt6.QtCore import QObject, pyqtSignal, QThreadPool
from PyQt6.QtGui import QImage
from ui.image_loader_worker import ImageLoaderWorker

class ImageCache(QObject):
    image_ready = pyqtSignal(str, QImage, bool) # path, image, is_full
    
    def __init__(self, proxy_window=10, proxy_size=2560):
        super().__init__()
        self.proxy_window = proxy_window
        self.proxy_size = proxy_size
        
        self.proxies = {}  # path -> QImage
        self.full_images = {} # path -> QImage
        
        self.thread_pool = QThreadPool.globalInstance()
        self.loading_paths = set() # (path, is_proxy)
        
    def get_image(self, path):
        """Returns (image, is_full) if cached, otherwise (None, False)."""
        if path in self.full_images:
            return self.full_images[path], True
        if path in self.proxies:
            return self.proxies[path], False
        return None, False
        
    def update_window(self, current_path, all_paths):
        """Updates the pre-loading window and evicts old images."""
        if current_path not in all_paths:
            return
            
        idx = all_paths.index(current_path)
        
        # 1. Full Image Window (Current + Next)
        full_needed = {current_path}
        if idx + 1 < len(all_paths):
            full_needed.add(all_paths[idx+1])
            
        # 2. Proxy Window (Larger)
        start = max(0, idx - self.proxy_window)
        end = min(len(all_paths), idx + self.proxy_window + 1)
        proxies_needed = set(all_paths[start:end])
        
        # Evict old full images
        to_evict_full = [p for p in self.full_images if p not in full_needed]
        for p in to_evict_full:
            del self.full_images[p]
            
        # Evict old proxies
        to_evict_proxy = [p for p in self.proxies if p not in proxies_needed]
        for p in to_evict_proxy:
            del self.proxies[p]
            
        # Trigger Loads
        # Prioritize current full image
        if current_path not in self.full_images:
            self._load_image(current_path, is_proxy=False)
            
        # Load next full image
        if idx + 1 < len(all_paths):
            next_path = all_paths[idx+1]
            if next_path not in self.full_images:
                self._load_image(next_path, is_proxy=False)

        # Load proxies
        for path in proxies_needed:
            if path not in self.proxies:
                self._load_image(path, is_proxy=True)

    def _load_image(self, path, is_proxy=True):
        load_key = (path, is_proxy)
        if load_key in self.loading_paths:
            return
            
        self.loading_paths.add(load_key)
        
        max_dim = self.proxy_size if is_proxy else None
        worker = ImageLoaderWorker(path, max_dim=max_dim)
        
        # Capture is_proxy in the signal handler via lambda
        worker.signals.finished.connect(lambda p, img, full, ip=is_proxy: self._on_load_finished(p, img, full, ip))
        worker.signals.error.connect(lambda p, err, ip=is_proxy: self._on_load_error(p, err, ip))
        
        self.thread_pool.start(worker)

    def _on_load_finished(self, path, image, is_full_quality, requested_proxy):
        load_key = (path, requested_proxy)
        if load_key in self.loading_paths:
            self.loading_paths.remove(load_key)
            
        if is_full_quality:
            self.full_images[path] = image
        else:
            self.proxies[path] = image
            
        self.image_ready.emit(path, image, is_full_quality)

    def _on_load_error(self, path, error_msg, requested_proxy):
        print(f"Error loading {path} (proxy={requested_proxy}): {error_msg}")
        load_key = (path, requested_proxy)
        if load_key in self.loading_paths:
            self.loading_paths.remove(load_key)

    def clear(self):
        self.proxies.clear()
        self.full_images.clear()
        self.loading_paths.clear()
