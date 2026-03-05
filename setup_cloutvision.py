# setup_cloutvision.py

import os
import subprocess
import sys

def install_dependencies():
    # List of required dependencies
    dependencies = [
        'numpy',
        'pandas',
        'scikit-learn',
        'matplotlib',
        'tensorflow',
        'flask'
    ]
    
    # Iterate through each dependency and install it
    for package in dependencies:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])

if __name__ == "__main__":
    install_dependencies()
    print("All dependencies have been installed.")
