# setup_cloutvision.py

import subprocess
import sys

def install(package):
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])

if __name__ == "__main__":
    # List of dependencies to install
    dependencies = [
        'numpy',  # Example dependency
        'pandas',  # Example dependency
        # Add more dependencies as needed
    ]
    
    for package in dependencies:
        print(f'Installing {package}...')
        install(package)

    print('All dependencies installed!')
