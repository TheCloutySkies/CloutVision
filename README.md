# Welcome to CloutVision
A free OSINT forensic media analysis suite for macOS.
And yes, before you ask this app was vibe coded. I was bored. At least it's free :)

## Features
- **Neural Entity Tracking:** Real-time YOLOv8 skeleton mapping.
- **Forensic Suite:** Frame-by-frame video scrubbing and spectrogram audio analysis.
- **NLP Engine:** Mathematical text summarization for TXT, PDFs and native Clipboard.
- **Dumb Visual Effects:** Thermal, Ghost Trails, Haar Face Masking, and more because why not i guess.

## Installation
1. Clone the repo: `git clone https://github.com/TheCloutySkies/CloutVision.git`
2. Create environment: `python3 -m venv venv && source venv/bin/activate`
3. Install dependencies: `pip install -r requirements.txt`
4. Run:
   - **PyQt6 (recommended):** `python cloutvision_qt.py` — native window, smoother UI, resizable.
   - **OpenCV window:** `python cloutvision_core.py` — original HighGUI-based UI.
