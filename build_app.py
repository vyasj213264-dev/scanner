import os
import shutil

def build_capacitor():
    print("Building Capacitor web directory...")
    
    www_dir = "www"
    
    # Clean previous build
    if os.path.exists(www_dir):
        shutil.rmtree(www_dir)
    os.makedirs(www_dir)
    
    # Files needed for the mobile frontend
    frontend_files = [
        "index.html",
        "manifest.json",
        "sw.js",
    ]
    
    # Optional assets directory if it exists (e.g. logos, icons)
    if os.path.exists("assets"):
        shutil.copytree("assets", os.path.join(www_dir, "assets"))
        print("Copied assets directory")
        
    for file in frontend_files:
        if os.path.exists(file):
            shutil.copy2(file, www_dir)
            print(f"Copied {file} to {www_dir}/")
        else:
            print(f"Warning: {file} not found.")

    print("\n✅ Build complete! Next steps:")
    print("1. npx cap sync")
    print("2. npx cap open android / npx cap open ios")

if __name__ == "__main__":
    build_capacitor()
