import sys
import os
import platform
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow
from core.paths import get_resource_path


def _load_platform_stylesheet() -> str:
    system = platform.system()
    if system == "Darwin":
        style_path = get_resource_path("styles/macos.qss")
    elif system == "Windows":
        style_path = get_resource_path("styles/windows.qss")
    else:
        style_path = get_resource_path("styles/windows.qss")

    if not os.path.exists(style_path):
        return ""

    with open(style_path, "r", encoding="utf-8") as f:
        return f.read()

def main():
    app = QApplication(sys.argv)
    stylesheet = _load_platform_stylesheet()
    if stylesheet:
        app.setStyleSheet(stylesheet)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
