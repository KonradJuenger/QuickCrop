import os
import sys
import subprocess
import platform


def generate_icons():
    cmd = ["uv", "run", "python", "scripts/generate_icons.py"]
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Warning: icon generation failed: {e}")


def build():
    # Configuration
    app_name = "QuickCrop"
    main_script = "main.py"
    dist_dir = "dist"
    build_dir = "build"
    
    # Platform specific settings
    system = platform.system()
    icon_file = None

    generate_icons()
    
    if system == "Windows":
        icon_file = "assets/icon.ico"
        # Create dummy icon if it doesn't exist for demonstration
        if not os.path.exists(icon_file):
             print(f"Warning: {icon_file} not found. Build will proceed without icon.")
             icon_file = None
    elif system == "Darwin": # macOS
        icon_file = "assets/icon.icns"
        if not os.path.exists(icon_file):
             print(f"Warning: {icon_file} not found. Build will proceed without icon.")
             icon_file = None
    
    print(f"Building {app_name} for {system}...")

    data_sep = ";" if system == "Windows" else ":"
    
    # Base command
    # --onefile: Create a single executable
    # --windowed: No console window
    # --noconfirm: Overwrite existing dist folder
    # --clean: Clean cache before build
    cmd = [
        "uv", "run", "pyinstaller",
        "--onefile",
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
    
    # Execute build
    try:
        subprocess.run(cmd, check=True)
        print(f"\nSuccessfully built {app_name}!")
        if system == "Windows":
            print(f"Executable location: {os.path.abspath(os.path.join(dist_dir, app_name + '.exe'))}")
        else:
            print(f"App location: {os.path.abspath(os.path.join(dist_dir, app_name + '.app'))}")
            
    except subprocess.CalledProcessError as e:
        print(f"\nBuild failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Create assets dir if it doesn't exist
    if not os.path.exists("assets"):
        os.makedirs("assets")
        
    build()
