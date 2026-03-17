#!/usr/bin/env python3
"""
Diagnostic test for color sampling. Run: python test_color_sampling.py
Tests HSV->name mapping and region sampling.
Requires: opencv and cloutvision_core (full deps). If you applied fix_sdl_duplicate.sh,
cv2 may fail to load; run the full app instead and use SPOOKY MODE + COL:ON to test live.
"""
import numpy as np
import os
import sys

try:
    import cv2
except ImportError as e:
    print("cv2 not available:", e)
    sys.exit(1)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cloutvision_core import CloutVision

def main():
    app = CloutVision()
    win_w, win_h = 1280, 720
    # Create a test image: strips of known BGR colors
    strip_h = 80
    # BGR order: red, green, blue, white, black, yellow, purple, orange
    strips_bgr = [
        ((0, 0, 255), "RED"),
        ((0, 255, 0), "GREEN"),
        ((255, 0, 0), "BLUE"),
        ((255, 255, 255), "WHITE"),
        ((30, 30, 30), "BLACK"),
        ((0, 255, 255), "YELLOW"),
        ((255, 0, 255), "PURPLE"),
        ((0, 165, 255), "ORANGE"),
    ]
    frame = np.zeros((win_h, win_w, 3), dtype=np.uint8)
    for i, (bgr, label) in enumerate(strips_bgr):
        y1, y2 = i * strip_h, (i + 1) * strip_h
        frame[y1:y2, :] = bgr
        # Add a bit of noise to simulate real fabric
        noise = np.random.randint(-8, 9, frame[y1:y2, :].shape, dtype=np.int16)
        frame[y1:y2, :] = np.clip(frame[y1:y2, :].astype(np.int16) + noise, 0, 255).astype(np.uint8)

    print("Color sampling diagnostic (center of each strip):")
    print("-" * 50)
    for i, (bgr, expected) in enumerate(strips_bgr):
        cx, cy = win_w // 2, i * strip_h + strip_h // 2
        detected_bgr, detected_name = app.sample_hsv_color(frame, cx, cy)
        ok = "OK" if expected.lower() in detected_name.upper() or detected_name.upper() in expected.upper() else "??"
        print(f"  {expected:8} -> {detected_name:18} {ok}")

    # Test region sampling (shirt-like and pants-like rectangles)
    print("-" * 50)
    print("Region sampling (shirt = top strip, pants = bottom strip):")
    shirt_rect = (100, 10, 400, 70)
    pants_rect = (100, strip_h * 6 + 10, 400, strip_h * 7 - 10)
    s_bgr, s_name = app.sample_region_color(frame, *shirt_rect)
    p_bgr, p_name = app.sample_region_color(frame, *pants_rect)
    print(f"  SHIRT region -> {s_name}")
    print(f"  PANTS region -> {p_name}")
    print("Done. Run the full app and use SPOOKY MODE + COL:ON for live shirt/pants detection.")

if __name__ == "__main__":
    main()
