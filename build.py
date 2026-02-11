import os
import sys
import subprocess
import platform


def generate_icons():
    cmd = [
        "uv",
        "run",
        "python",
        "scripts/generate_icons.py",
        "--source",
        "resources/quickcrop_icon.svg",
        "--assets-dir",
        "assets",
    ]
    try:
        subprocess.run(cmd, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise RuntimeError(f"Icon generation failed: {e}") from e


def build():
    # Configuration
    app_name = "QuickCrop"
    main_script = "main.py"
    dist_dir = "dist"
    build_dir = "build"
    
    # Platform specific settings
    system = platform.system()
    icon_file = None
    bundle_flag = "--onefile"

    generate_icons()
    
    if system == "Windows":
        icon_file = "assets/icon.ico"
        if not os.path.exists(icon_file):
             raise FileNotFoundError(
                 f"{icon_file} not found after icon generation. "
                 "Expected to generate it from resources/quickcrop_icon.svg."
             )
    elif system == "Darwin": # macOS
        icon_file = "assets/icon.icns"
        bundle_flag = "--onedir"
        if not os.path.exists(icon_file):
             print(f"Warning: {icon_file} not found. Build will proceed without icon.")
             icon_file = None
    
    print(f"Building {app_name} for {system}...")

    data_sep = ";" if system == "Windows" else ":"
    
    # Base command
    # --onefile / --onedir: packaging mode by platform
    # --windowed: No console window
    # --noconfirm: Overwrite existing dist folder
    # --clean: Clean cache before build
    cmd = [
        "uv", "run", "pyinstaller",
        bundle_flag,
        "--windowed",
        "--noconfirm",
        "--clean",
        "--name", app_name,
        "--hidden-import", "PySide6.QtSvg",
        main_script
    ]

    data_dirs = [
        ("resources", "resources"),
        ("styles", "styles"),
    ]
    for src, dst in data_dirs:
        if os.path.exists(src):
            cmd.extend(["--add-data", f"{src}{data_sep}{dst}"])
    
    if icon_file:
        cmd.extend(["--icon", icon_file])
    else:
        if system == "Windows":
            print("Warning: Windows build has no .ico icon; executable icon will be missing.")
    
    # Execute build
    try:
        subprocess.run(cmd, check=True)
        print(f"\nSuccessfully built {app_name}!")
        if system == "Windows":
            print(f"Executable location: {os.path.abspath(os.path.join(dist_dir, app_name + '.exe'))}")
        elif system == "Darwin":
            print(f"App location: {os.path.abspath(os.path.join(dist_dir, app_name + '.app'))}")
        else:
            print(f"Output location: {os.path.abspath(dist_dir)}")
            
    except subprocess.CalledProcessError as e:
        print(f"\nBuild failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Create assets dir if it doesn't exist
    if not os.path.exists("assets"):
        os.makedirs("assets")
        
    build()
