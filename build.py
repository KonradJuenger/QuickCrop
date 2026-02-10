import os
import sys
import subprocess
import platform

def build():
    # Configuration
    app_name = "QuickCrop"
    main_script = "main.py"
    dist_dir = "dist"
    build_dir = "build"
    
    # Platform specific settings
    system = platform.system()
    icon_file = None
    
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
        main_script
    ]
    
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
