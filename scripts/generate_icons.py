import argparse
import shutil
import subprocess
from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


WINDOWS_ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
MAC_ICONSET_FILES = {
    "icon_16x16.png": 16,
    "icon_16x16@2x.png": 32,
    "icon_32x32.png": 32,
    "icon_32x32@2x.png": 64,
    "icon_128x128.png": 128,
    "icon_128x128@2x.png": 256,
    "icon_256x256.png": 256,
    "icon_256x256@2x.png": 512,
    "icon_512x512.png": 512,
    "icon_512x512@2x.png": 1024,
}


def render_svg_to_png(svg_path: Path, png_path: Path, size: int) -> None:
    renderer = QSvgRenderer(str(svg_path))
    if not renderer.isValid():
        raise RuntimeError(f"Invalid SVG: {svg_path}")

    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()

    png_path.parent.mkdir(parents=True, exist_ok=True)
    if not image.save(str(png_path), "PNG"):
        raise RuntimeError(f"Failed to save PNG: {png_path}")


def generate_ico(svg_path: Path, assets_dir: Path) -> Path:
    max_size = max(WINDOWS_ICO_SIZES)
    base_png = assets_dir / "_icon_base_256.png"
    render_svg_to_png(svg_path, base_png, max_size)

    ico_path = assets_dir / "icon.ico"
    with Image.open(base_png) as img:
        img.save(str(ico_path), format="ICO", sizes=[(s, s) for s in WINDOWS_ICO_SIZES])

    base_png.unlink(missing_ok=True)
    return ico_path


def generate_icns(svg_path: Path, assets_dir: Path) -> Path | None:
    iconutil = shutil.which("iconutil")
    if not iconutil:
        return None

    iconset_dir = assets_dir / "icon.iconset"
    if iconset_dir.exists():
        shutil.rmtree(iconset_dir)
    iconset_dir.mkdir(parents=True, exist_ok=True)

    for filename, size in MAC_ICONSET_FILES.items():
        render_svg_to_png(svg_path, iconset_dir / filename, size)

    icns_path = assets_dir / "icon.icns"
    subprocess.run(
        [iconutil, "-c", "icns", str(iconset_dir), "-o", str(icns_path)],
        check=True,
    )
    shutil.rmtree(iconset_dir)
    return icns_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate app icons from an SVG source.")
    parser.add_argument(
        "--source",
        default="resources/quickcrop_icon.svg",
        help="Path to source SVG.",
    )
    parser.add_argument(
        "--assets-dir",
        default="assets",
        help="Directory where icon files are written.",
    )
    args = parser.parse_args()

    source = Path(args.source).resolve()
    assets_dir = Path(args.assets_dir).resolve()
    assets_dir.mkdir(parents=True, exist_ok=True)

    if not source.exists():
        raise FileNotFoundError(f"Source SVG not found: {source}")

    ico_path = generate_ico(source, assets_dir)
    print(f"Generated: {ico_path}")

    icns_path = generate_icns(source, assets_dir)
    if icns_path:
        print(f"Generated: {icns_path}")
    else:
        print("Skipped .icns generation (iconutil not available on this platform).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
