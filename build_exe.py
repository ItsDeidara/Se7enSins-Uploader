import os
import subprocess
import shutil
from PIL import Image

def main():
    print("Installing PyInstaller and Pillow...")
    subprocess.run(["python", "-m", "pip", "install", "pyinstaller", "pillow"], check=True)

    print("Checking for icon file...")
    icon_flag = []
    if os.path.exists("icon.ico"):
        print("Processing icon.ico to multi-size ICO...")
        img = Image.open("icon.ico")
        icon_sizes = [(16,16), (24,24), (32,32), (48,48), (64,64), (128,128), (256,256)]
        processed_icon = "processed_icon.ico"
        img.save(processed_icon, sizes=icon_sizes)
        icon_path = os.path.abspath(processed_icon)
        icon_flag = ["--icon", icon_path]
        print(f"Using processed icon: {icon_path}")
    else:
        icon_path = input("Icon file not found. Please enter the path to an icon file (or press Enter to skip): ").strip()
        if icon_path:
            icon_flag = ["--icon", icon_path]
            print(f"Using icon: {icon_path}")
        else:
            print("No icon selected.")

    print("Building standalone exe...")
    cmd = ["python", "-m", "PyInstaller", "--onefile", "--windowed"] + icon_flag + ["gui.py"]
    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)

    print("Copying config and categories files...")
    dist_dir = "dist"
    os.makedirs(dist_dir, exist_ok=True)
    shutil.copy("config.json", dist_dir)
    shutil.copy("categories.json", dist_dir)

    print("Build complete. Check the dist folder for the exe and config files.")

if __name__ == "__main__":
    main()