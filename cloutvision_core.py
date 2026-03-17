import os
import sys

# --- Suppress PyGame/OpenCV Terminal Spam ---
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "hide"
os.environ["PATH"] += os.pathsep + "/usr/local/bin" + os.pathsep + "/opt/homebrew/bin"
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

import pygame 
import cv2
import numpy as np
import subprocess
import time
from datetime import datetime
from collections import Counter
import fitz   
import re
import shutil
import warnings
import threading
import math
import urllib.request
import json
from pathlib import Path
import importlib
import importlib.util
import piexif

HAS_HEIF = importlib.util.find_spec("pillow_heif") is not None

warnings.filterwarnings("ignore")

# ============================================================================
# LAYOUT & THEME — PS2 boot + Animus (AC2) design language
# ============================================================================
WIN_W, WIN_H = 1280, 720
THEME = {
    "bg_dark": (6, 6, 14),
    "bg_card": (14, 14, 24),
    "bg_card_raised": (22, 20, 34),
    "panel": (28, 26, 42),
    "panel_hover": (42, 36, 58),
    "accent": (255, 160, 50),
    "accent_dim": (200, 120, 40),
    "accent_glow": (255, 200, 100),
    "hover": (255, 180, 70),
    "text_light": (255, 245, 220),
    "text_dim": (220, 200, 160),
    "text_muted": (140, 120, 90),
    "error": (255, 70, 70),
    "success": (120, 220, 100),
    "border": (90, 70, 45),
    "border_light": (140, 110, 60),
    "font_title": 1.6,
    "font_subtitle": 0.68,
    "font_body": 0.54,
    "font_small": 0.42,
    "thickness": 1,
    "thickness_heavy": 2,
    "radius": 4,
    "padding": 14,
    "bar_height": 0.058,
}
# Single source of truth for button/touch targets (relative: x, y, w, h)
def _menu_btn_boxes():
    m = {"btn_w": 0.36, "btn_h": 0.058, "btn_gap": 0.012, "btn_start_x": 0.32, "btn_start_y": 0.22}
    items = ["LIVE HUD", "SPOOKY MODE", "VISUAL EFFECTS", "MEDIA ANALYSIS", "CONTROL CENTER"]
    boxes = []
    for i in range(len(items)):
        y = m["btn_start_y"] + i * (m["btn_h"] + m["btn_gap"])
        boxes.append((m["btn_start_x"], y, m["btn_w"], m["btn_h"]))
    return boxes

LAYOUT = {
    "menu": {
        "title_y": 0.14,
        "tagline_y": 0.195,
        "btn_w": 0.36, "btn_h": 0.058, "btn_gap": 0.012,
        "btn_start_x": 0.32, "btn_start_y": 0.22,
        "items": ["LIVE HUD", "SPOOKY MODE", "VISUAL EFFECTS", "MEDIA ANALYSIS", "CONTROL CENTER"],
        "shutdown": (0.32, 0.72, 0.36, 0.058),
        "tip_y": 0.935,
    },
    "menu_buttons": _menu_btn_boxes(),
    "top_bar": {"height": 0.062, "back": (0.855, 0.012, 0.11, 0.042), "help": (0.735, 0.012, 0.11, 0.042)},
    "settings": {
        "title_y": 0.10,
        "col1": [(0.12, 0.20, 0.34, 0.056), (0.12, 0.28, 0.34, 0.056), (0.12, 0.36, 0.34, 0.056), (0.12, 0.44, 0.34, 0.056)],
        "col2": [
            (0.50, 0.20, 0.34, 0.056),
            (0.50, 0.28, 0.34, 0.056),
            (0.50, 0.36, 0.34, 0.056),
            (0.50, 0.44, 0.34, 0.056),
            (0.50, 0.52, 0.34, 0.056),
            (0.50, 0.60, 0.34, 0.056),
            (0.50, 0.68, 0.34, 0.056),
            (0.50, 0.76, 0.34, 0.056),
        ],
        "slider_box": (0.50, 0.78, 0.34, 0.040),
    },
    "media_menu": {
        "title_y": 0.10,
        "buttons": [
            (0.32, 0.20, 0.36, 0.058),
            (0.32, 0.28, 0.36, 0.058),
            (0.32, 0.36, 0.36, 0.058),
            (0.32, 0.44, 0.36, 0.058),
            (0.32, 0.52, 0.36, 0.058),
            (0.32, 0.60, 0.36, 0.058),
        ],
    },
    "live_toolbar": {"y": 0.070, "h": 0.052, "slider_bar_y": 0.128},
    "transport": {
        # Kept above analysis toolbar (y=0.90) to prevent overlap.
        "track_y": 0.790, "track_h": 0.020, "track_x1": 0.10, "track_x2": 0.90,
        "track_ry": (0.782, 0.818),
        "btn_y": 0.830, "btn_h": 0.048,
        "rw": (0.40, 0.830, 0.058, 0.048), "play": (0.468, 0.830, 0.072, 0.048), "ff": (0.548, 0.830, 0.058, 0.048), "stop": (0.614, 0.830, 0.068, 0.048),
    },
    # Bottom toolbar for Photo/Video analysis — keeps buttons off the image (y ~0.90)
    "analysis_toolbar": {
        "y": 0.90, "h": 0.052,
        "photo": {"mdls": (0.02, 0.90, 0.10, 0.048), "ocr": (0.13, 0.90, 0.10, 0.048), "copy_all": (0.24, 0.90, 0.12, 0.048)},
        "video": {"mdls": (0.02, 0.90, 0.10, 0.048), "ocr": (0.13, 0.90, 0.10, 0.048), "copy_frame": (0.24, 0.90, 0.12, 0.048)},
    },
}

# ============================================================================
# UNBREAKABLE DEPENDENCY LOADERS
# ============================================================================
try:
    import pytesseract
    _tesseract_path = shutil.which("tesseract") or "/opt/homebrew/bin/tesseract"
    if not _tesseract_path or not os.path.isfile(_tesseract_path):
        _tesseract_path = "tesseract"
    pytesseract.pytesseract.tesseract_cmd = _tesseract_path
    try:
        pytesseract.get_tesseract_version()
        HAS_OCR = True
    except Exception:
        HAS_OCR = False
except (ImportError, NameError):
    HAS_OCR = False

# Heavy OCR backends are detected cheaply and imported lazily on demand.
HAS_PADDLE_OCR = importlib.util.find_spec("paddleocr") is not None
HAS_EASY_OCR = importlib.util.find_spec("easyocr") is not None
PaddleOCRReader = None
easyocr = None

try:
    import argostranslate.translate as argos_translate
    HAS_ARGOS = True
except Exception:
    HAS_ARGOS = False

# MediaPipe is also loaded lazily to keep startup fast.
HAS_MP = importlib.util.find_spec("mediapipe") is not None
mp_face_mesh = None
mp_pose = None
mp_drawing = None
mp_drawing_styles = None
face_mesh_engine = None
mp_pose_engine = None

class CloutVision:
    def __init__(self, use_qt=False):
        # --- Lightweight init: window first (unless Qt owns the window), heavy work in loading screen ---
        self.use_qt = use_qt
        self.audio_enabled = True
        try:
            pygame.mixer.init()
        except Exception as e:
            self.audio_enabled = False
            print(f"[CloutVision] Audio init disabled: {e}")
        self.model_obj = None
        self.model_pose = None
        self.face_cascade = None
        self.eye_cascade = None
        self.app_state = "LOADING"
        self.loading_progress = 0.0
        self.loading_step = 0
        self.loading_messages = ["Loading memory...", "Synchronizing...", "Initializing sequence...", "Ready"]
        self.mode = "CLOUTVISION"
        self.effect_list = ["NEON_EDGES", "THERMAL", "GHOST_TRAILS", "PENCIL_SKETCH", "HAAR_FACES", "BLINK_TRACKER", "FINGER_DRAW"]
        self.effect_idx = 0
        self.show_help = False
        self.show_exif_hud = False
        self.ui_colors = [(0, 255, 0), (255, 255, 0), (0, 150, 255), (255, 0, 255)]
        self.ui_color_names = ["Green", "Yellow", "Blue", "Magenta"]
        self.ui_color_idx = 0
        self.yolo_conf = 0.3
        self.zoom, self.exposure = 1.0, 1.0
        # Floating image controls (LIVE/PHOTO/VIDEO), collapsible.
        self.img_ctrl_collapsed = False
        self.img_ctrl_vals = {
            "contrast": 1.00,   # 0.6..1.8
            "saturation": 1.00, # 0.0..2.0
            "brightness": 0.0,  # -60..60
            "sharpen": 0.0,     # 0.0..1.5
            "structure": 0.0,   # 0.0..1.5
            "gamma": 1.00,      # 0.7..1.6
            "warmth": 0.0,      # -40..40
            "denoise": 0.0,     # 0.0..1.0
        }
        self.img_ctrl_specs = [
            ("contrast", "Contrast", 0.6, 1.8),
            ("saturation", "Saturation", 0.0, 2.0),
            ("brightness", "Brightness", -60.0, 60.0),
            ("sharpen", "Sharpen", 0.0, 1.5),
            ("structure", "Structure", 0.0, 1.5),
            ("gamma", "Gamma", 0.7, 1.6),
            ("warmth", "Warmth", -40.0, 40.0),
            ("denoise", "Denoise", 0.0, 1.0),
        ]
        self.run_ocr = False
        self.ocr_profile = "AUTO"  # AUTO | FAST | ACCURATE
        self.ocr_last_engine = "NONE"
        self.ocr_engine_paddle = None
        self.ocr_engine_easy = None
        self._librosa = None
        self.toggle_skeleton = True
        self.toggle_emotion = True
        self.toggle_color = True
        self.toggle_focus = False
        self.last_mouse_pos = (0, 0)
        self.color_sample_pos = None
        self.hover_active = False
        self.dragging_slider = None
        self.dragging_timeline = False
        self.frame_counter = 0
        self.cached_dets = []
        self.cached_pose = None
        self.cached_mesh = []
        self.tips = [
            "TIP: Use Control Center to set Skeleton, Emotion, Color before going Live.",
            "TIP: In SPOOKY MODE, SHIRT and PANTS colors use pose keypoints.",
            "TIP: Click on the image for the Color Picker crosshair.",
        ]
        self.cam_index = 0
        self.cap = None
        self.export_target = "PHOTOS"
        self.show_clock = True
        self.custom_face_text = "SUBJECT"
        self.recording = False
        self.out = None
        self.flash_frames = 0
        self.ghost_acc = None
        self.draw_points = []
        self.blinks = 0
        self.eyes_closed_frames = 0
        self.emotion_history = []  # recent raw emotion labels for temporal consensus
        self.emotion_label = "NEUTRAL"
        self.emotion_last_change_ts = 0.0
        self.cached_dets_prev = []  # for YOLO temporal smoothing
        self.pose_prev = None       # for pose smoothing
        self.pose_backend = "YOLO"  # 'YOLO' or 'BLAZE'
        self.analysis_file = None
        self.clipboard_cache = None
        self.audio_data = None
        self.text_data = None
        self.summary_length = "SHORT"
        self.extracted_exif = []
        self.ocr_cache = None
        self.ocr_boxes = []  # list of {"x","y","w","h","text"} for hit-test and copy (pixel coords)
        self.ocr_letterbox_scale = 1.0  # photo: scale from orig image to display
        self.ocr_letterbox_xoff = 0
        self.ocr_letterbox_yoff = 0
        self.ocr_copied_at = 0  # time when last copy happened (for "Copied" toast)
        self.video_run_ocr = False
        self.video_ocr_frame_index = -1  # vid_current when we last ran video OCR (invalidate on change)
        self.text_block_rects = []  # list of (x,y,w,h,text) filled each frame in ANALYZE_TEXT for click-to-copy
        self.ocr_text_rects = []  # list of (x,y,w,h,text) for side-panel OCR selections
        self.face_mask = None
        self.error_message = None
        self.vid_cap = None
        self.vid_total = 1
        self.vid_current = 0
        self.is_playing = True
        self.error_log = []  # rolling error log for Settings -> Error Log
        self.show_error_log = False
        self.photo_gps = None
        self.photo_map_tile = None
        self.copy_coords_rel = None
        self.day_route_points = []   # [{'lat','lon','ts','path'}]
        self.nearby_shots = []       # precomputed nearby entries for HUD
        self.nearby_rects = []       # clickable nearby-shot rows in EXIF HUD
        self.current_person_metrics = {}
        self.current_posture = "UNKNOWN"
        self.current_action = "NONE"
        self.hip_x_hist = []
        self.wrist_x_hist = []
        self.wrist_trails = []       # list of points for AR trails
        self.toggle_doc_mode = False
        self.doc_text_blocks = []    # OCR blocks [{'text','bbox'}]
        self.doc_translate_on = False
        self.last_selected_text = ""
        self.forensics_tools = ["MAGNIFIER", "ELA", "NOISE", "SWEEP", "GRADIENT", "PCA", "CLONE"]
        self.forensics_tool_idx = 0
        self.forensics_enhance_opts = ["NONE", "HIST_EQ", "AUTO", "AUTO_RGB"]
        self.forensics_enhance_idx = 0
        self.forensics_opacity = 0.78
        self.forensics_ela_quality = 90
        self.forensics_ela_scale = 14.0
        self.forensics_noise_amp = 2.2
        self.forensics_sweep = 0.50
        self.forensics_sweep_width = 36.0
        self.forensics_pca_component = 1
        self.forensics_invert = False
        self.forensics_clone_sim = 0.92
        self.forensics_clone_detail = 10.0
        self.forensics_mag_zoom = 6
        self.forensics_cache = {}
        self.forensics_jpeg_lines = []
        self.forensics_thumb = None
        self.forensics_thumb_diff = None
        self.forensics_tool_menu_open = False
        self.forensics_jpeg_panel_minimized = False
        self.forensics_jpeg_panel_drag = False
        self.forensics_jpeg_panel_rect = None  # (x1,y1,x2,y2) in window coords
        self.forensics_jpeg_panel_full_h = None
        self.forensics_render_cache = {}
        self.forensics_help = {
            "tool": {
                "MAGNIFIER": "Magnifier: inspect pixels under cursor (no processing).",
                "ELA": "ELA: highlights JPEG recompression inconsistencies (tamper/edits can pop).",
                "NOISE": "Noise: shows noise residue (splicing/denoise patterns can appear).",
                "SWEEP": "Level sweep: isolates a narrow luminance band to reveal hidden edits.",
                "GRADIENT": "Gradient: edge/gradient magnitude & direction visualization.",
                "PCA": "PCA: color-space component projection; can separate manipulations/stains.",
                "CLONE": "Clone: finds repeated textured blocks (copy-move/clone hints).",
            },
            "enh": {
                "NONE": "Enh NONE: raw output.",
                "HIST_EQ": "Enh HIST_EQ: equalize luminance for contrasty detail.",
                "AUTO": "Enh AUTO: normalize overall min/max (can exaggerate subtle signals).",
                "AUTO_RGB": "Enh AUTO_RGB: normalize each channel separately (color artifacts pop).",
            },
            "settings": {
                "OPACITY": "Opacity: blend amount between base image and tool overlay.",
                "INVERT": "Invert: invert certain tool outputs (best for PCA/levels).",
            },
        }
        self.session_active = False
        self.session_last_ts = 0.0
        self.session_stats = {
            "live_seconds": 0.0,
            "in_frame_seconds": 0.0,
            "posture_seconds": {"STANDING": 0.0, "SITTING": 0.0, "PACED": 0.0, "SLOUCHING": 0.0, "UNKNOWN": 0.0},
            "emotion_counts": {},
            "action_counts": {},
            "blinks": 0,
        }
        self.session_logs = []
        self.last_vid_frame = None
        self.audio_length = 0
        self.skeleton_edges = [(0,1),(0,2),(1,3),(2,4),(5,6),(5,11),(6,12),(11,12),(5,7),(7,9),(6,8),(8,10),(11,13),(13,15),(12,14),(14,16)]
        running_pytest = "PYTEST_CURRENT_TEST" in os.environ
        if not self.use_qt and not running_pytest:
            try:
                cv2.namedWindow('CloutVision')
                cv2.setMouseCallback('CloutVision', self.mouse_event)
            except Exception as e:
                self._log_error("ui", f"Headless window init: {e}")
        self._loading_done = threading.Event()
        self._display_buf = np.zeros((WIN_H, WIN_W, 3), dtype=np.uint8)
        self._letterbox_canvas = np.zeros((WIN_H, WIN_W, 3), dtype=np.uint8)
        self._menu_bg = None  # reused blurred frame for menu/settings
        self._menu_bg_fresh = False
        threading.Thread(target=self._loading_worker, daemon=True).start()

    def _loading_worker(self):
        """Background: load object model + cascades first (fast to menu), then pose in second thread."""
        try:
            self.loading_progress = 0.05
            from ultralytics import YOLO
            # Upgrade to a slightly larger YOLOv8s model for better accuracy on small/occluded objects
            self.model_obj = YOLO('yolov8s.pt')
            self.loading_step, self.loading_progress = 1, 0.55
            self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            self.eye_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_eye.xml')
            self.loading_step, self.loading_progress = 2, 0.85
            self._loading_done.set()
            # Pose model in background so menu is usable immediately
            def _load_pose():
                try:
                    # Use a stronger but still lightweight YOLOv8s-pose backbone for smoother skeletons
                    self.model_pose = YOLO('yolov8s-pose.pt')
                except Exception as e:
                    print(f"[CloutVision] Pose model: {e}")
            threading.Thread(target=_load_pose, daemon=True).start()
            self.loading_step, self.loading_progress = 3, 1.0
        except Exception as e:
            print(f"[CloutVision] Loading error: {e}")
            self.loading_progress = 1.0
            self.loading_step = 3
            self._loading_done.set()

    def _scanline_overlay(self, img, step=4, dim=0.12):
        """Subtle CRT/PS2 scanlines: darken every step-th row (vectorized)."""
        img[::step] = np.clip(img[::step].astype(np.float32) * (1.0 - dim), 0, 255).astype(np.uint8)

    def _img_ctrl_panel_boxes(self):
        """Relative boxes for image-controls panel and interactive elements."""
        px, py, pw = 0.015, 0.145, 0.285
        header_h = 0.045
        row_h = 0.040
        footer_h = 0.050
        expanded_h = header_h + len(self.img_ctrl_specs) * row_h + footer_h + 0.012
        ph = 0.062 if self.img_ctrl_collapsed else expanded_h
        panel = (px, py, pw, ph)
        collapse_btn = (px + pw - 0.050, py + 0.007, 0.040, 0.030)
        reset_btn = (px + 0.012, py + ph - 0.040, 0.072, 0.028)
        sx1 = px + 0.12
        sx2 = px + pw - 0.016
        rows = []
        if not self.img_ctrl_collapsed:
            y0 = py + header_h + 0.004
            for i, (k, label, vmin, vmax) in enumerate(self.img_ctrl_specs):
                ry = y0 + i * row_h
                rows.append({
                    "key": k, "label": label, "vmin": vmin, "vmax": vmax,
                    "bar": (sx1, ry + 0.017, sx2 - sx1, 0.012),
                    "row_box": (px + 0.006, ry, pw - 0.012, row_h - 0.002),
                })
        return panel, collapse_btn, reset_btn, rows

    def _point_in_rel_box(self, rx, ry, box):
        bx, by, bw, bh = box
        return (bx <= rx <= bx + bw) and (by <= ry <= by + bh)

    def _is_over_img_controls(self, rx, ry):
        if self.app_state not in ("LIVE", "ANALYZE_PHOTO", "ANALYZE_VIDEO"):
            return False
        panel, _, _, _ = self._img_ctrl_panel_boxes()
        return self._point_in_rel_box(rx, ry, panel)

    def _set_img_ctrl_from_rx(self, key, rx):
        for k, _, vmin, vmax in self.img_ctrl_specs:
            if k != key:
                continue
            _, _, _, rows = self._img_ctrl_panel_boxes()
            row = next((r for r in rows if r["key"] == key), None)
            if row is None:
                return
            sx, sy, sw, sh = row["bar"]
            t = float(np.clip((rx - sx) / max(1e-6, sw), 0.0, 1.0))
            self.img_ctrl_vals[key] = vmin + t * (vmax - vmin)
            return

    def _reset_img_controls(self):
        self.img_ctrl_vals.update({
            "contrast": 1.00, "saturation": 1.00, "brightness": 0.0,
            "sharpen": 0.0, "structure": 0.0, "gamma": 1.00, "warmth": 0.0, "denoise": 0.0
        })

    def _apply_image_controls(self, frame):
        """Apply user image controls to a frame (display-only adjustments)."""
        if frame is None:
            return frame
        out = frame.copy()
        v = self.img_ctrl_vals
        contrast = float(v["contrast"]); brightness = float(v["brightness"])
        if abs(contrast - 1.0) > 1e-3 or abs(brightness) > 1e-3:
            out = np.clip(out.astype(np.float32) * contrast + brightness, 0, 255).astype(np.uint8)
        warmth = float(v["warmth"])
        if abs(warmth) > 0.5:
            b = out[:, :, 0].astype(np.int16) - int(warmth)
            r = out[:, :, 2].astype(np.int16) + int(warmth)
            out[:, :, 0] = np.clip(b, 0, 255).astype(np.uint8)
            out[:, :, 2] = np.clip(r, 0, 255).astype(np.uint8)
        sat = float(v["saturation"])
        if abs(sat - 1.0) > 1e-3:
            hsv = cv2.cvtColor(out, cv2.COLOR_BGR2HSV).astype(np.float32)
            hsv[:, :, 1] = np.clip(hsv[:, :, 1] * sat, 0, 255)
            out = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
        gamma = float(v["gamma"])
        if abs(gamma - 1.0) > 0.02:
            inv = 1.0 / max(0.1, gamma)
            lut = np.array([((i / 255.0) ** inv) * 255 for i in range(256)], dtype=np.uint8)
            out = cv2.LUT(out, lut)
        structure = float(v["structure"])
        if structure > 0.01:
            blur = cv2.GaussianBlur(out, (0, 0), 3.0)
            out = cv2.addWeighted(out, 1.0 + 0.55 * structure, blur, -0.55 * structure, 0)
        sharpen = float(v["sharpen"])
        if sharpen > 0.01:
            blur = cv2.GaussianBlur(out, (0, 0), 1.0)
            out = cv2.addWeighted(out, 1.0 + sharpen, blur, -sharpen, 0)
        denoise = float(v["denoise"])
        if denoise > 0.02:
            d = 5 if denoise < 0.5 else 7
            sigma = 20 + 45 * denoise
            out = cv2.bilateralFilter(out, d, sigma, sigma)
        return out

    def _forensics_enhance(self, img_bgr):
        mode = self.forensics_enhance_opts[self.forensics_enhance_idx]
        if mode == "NONE":
            return img_bgr
        out = img_bgr.copy()
        if mode == "HIST_EQ":
            ycc = cv2.cvtColor(out, cv2.COLOR_BGR2YCrCb)
            ycc[:, :, 0] = cv2.equalizeHist(ycc[:, :, 0])
            return cv2.cvtColor(ycc, cv2.COLOR_YCrCb2BGR)
        if mode == "AUTO":
            return cv2.normalize(out, None, 0, 255, cv2.NORM_MINMAX)
        if mode == "AUTO_RGB":
            chans = cv2.split(out)
            chans = [cv2.normalize(c, None, 0, 255, cv2.NORM_MINMAX) for c in chans]
            return cv2.merge(chans)
        return out

    def _forensics_apply(self, base_bgr):
        tool = self.forensics_tools[self.forensics_tool_idx]
        base = base_bgr.copy()
        op = float(np.clip(self.forensics_opacity, 0.0, 1.0))
        h, w = base.shape[:2]
        # Lightweight caching for smoother slider tweaks (skip magnifier since it's cursor-dependent).
        if tool != "MAGNIFIER":
            k = (
                "render",
                tool,
                self.forensics_enhance_idx,
                bool(self.forensics_invert),
                round(self.forensics_opacity, 3),
                int(self.forensics_ela_quality),
                round(self.forensics_ela_scale, 2),
                round(self.forensics_noise_amp, 2),
                round(self.forensics_sweep, 3),
                round(self.forensics_sweep_width, 2),
                int(self.forensics_pca_component),
                round(self.forensics_clone_sim, 3),
                round(self.forensics_clone_detail, 2),
                base.shape,
                int(np.sum(base[::32, ::32, :]) % 1000003),
            )
            cached = self.forensics_render_cache.get(k)
            if cached is not None:
                return cached.copy()
        if tool == "MAGNIFIER":
            out = base.copy()
            mx, my = self.last_mouse_pos
            mx = int(np.clip(mx, 0, w - 1)); my = int(np.clip(my, 0, h - 1))
            zoom = max(2, int(self.forensics_mag_zoom))
            win = 140
            r = max(8, win // zoom)
            x1, y1 = max(0, mx - r), max(0, my - r)
            x2, y2 = min(w, mx + r), min(h, my + r)
            roi = base[y1:y2, x1:x2]
            if roi.size > 0:
                roi = self._forensics_enhance(cv2.resize(roi, (win, win), interpolation=cv2.INTER_NEAREST))
                px, py = w - win - 18, 90
                out[py:py + win, px:px + win] = roi
                cv2.rectangle(out, (px, py), (px + win, py + win), THEME["accent"], 1)
                cv2.rectangle(out, (x1, y1), (x2, y2), THEME["accent"], 1)
            return out
        if tool == "ELA":
            ok, enc = cv2.imencode(".jpg", base, [int(cv2.IMWRITE_JPEG_QUALITY), int(self.forensics_ela_quality)])
            if ok:
                dec = cv2.imdecode(enc, cv2.IMREAD_COLOR)
                diff = cv2.absdiff(base, dec)
                diff = np.clip(diff.astype(np.float32) * self.forensics_ela_scale, 0, 255).astype(np.uint8)
                diff = self._forensics_enhance(diff)
                out = cv2.addWeighted(base, 1.0 - op, diff, op, 0)
                if tool != "MAGNIFIER":
                    self.forensics_render_cache[k] = out.copy()
                return out
            return base
        if tool == "NOISE":
            gray = cv2.cvtColor(base, cv2.COLOR_BGR2GRAY)
            den = cv2.medianBlur(gray, 3)
            n = cv2.absdiff(gray, den).astype(np.float32) * (self.forensics_noise_amp * 8.0)
            n = np.clip(n, 0, 255).astype(np.uint8)
            layer = cv2.cvtColor(n, cv2.COLOR_GRAY2BGR)
            layer = self._forensics_enhance(layer)
            out = cv2.addWeighted(base, 1.0 - op, layer, op, 0)
            if tool != "MAGNIFIER":
                self.forensics_render_cache[k] = out.copy()
            return out
        if tool == "SWEEP":
            gray = cv2.cvtColor(base, cv2.COLOR_BGR2GRAY).astype(np.float32)
            c = self.forensics_sweep * 255.0
            wid = max(4.0, self.forensics_sweep_width)
            lo, hi = c - wid * 0.5, c + wid * 0.5
            swept = np.clip((gray - lo) * (255.0 / max(1.0, hi - lo)), 0, 255).astype(np.uint8)
            layer = cv2.applyColorMap(swept, cv2.COLORMAP_TURBO)
            layer = self._forensics_enhance(layer)
            out = cv2.addWeighted(base, 1.0 - op, layer, op, 0)
            if tool != "MAGNIFIER":
                self.forensics_render_cache[k] = out.copy()
            return out
        if tool == "GRADIENT":
            gray = cv2.cvtColor(base, cv2.COLOR_BGR2GRAY).astype(np.float32)
            gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
            gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
            mag, ang = cv2.cartToPolar(gx, gy, angleInDegrees=True)
            hsv = np.zeros((h, w, 3), np.uint8)
            hsv[:, :, 0] = ((ang % 180)).astype(np.uint8)
            hsv[:, :, 1] = 255
            hsv[:, :, 2] = cv2.normalize(mag, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
            layer = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
            layer = self._forensics_enhance(layer)
            out = cv2.addWeighted(base, 1.0 - op, layer, op, 0)
            if tool != "MAGNIFIER":
                self.forensics_render_cache[k] = out.copy()
            return out
        if tool == "PCA":
            x = base.reshape((-1, 3)).astype(np.float32)
            mean, ev = cv2.PCACompute(x, mean=None, maxComponents=3)
            comp = int(np.clip(self.forensics_pca_component, 1, 3) - 1)
            centered = x - mean
            proj = centered @ ev[comp].reshape(3, 1)
            p = proj.reshape((h, w))
            p = cv2.normalize(p, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
            if self.forensics_invert:
                p = 255 - p
            layer = cv2.cvtColor(p, cv2.COLOR_GRAY2BGR)
            layer = self._forensics_enhance(layer)
            out = cv2.addWeighted(base, 1.0 - op, layer, op, 0)
            if tool != "MAGNIFIER":
                self.forensics_render_cache[k] = out.copy()
            return out
        if tool == "CLONE":
            key = ("clone", base.shape[0], base.shape[1], round(self.forensics_clone_sim, 3), int(self.forensics_clone_detail))
            lines = self.forensics_cache.get(key)
            if lines is None:
                gray = cv2.cvtColor(base, cv2.COLOR_BGR2GRAY)
                small = gray
                scale = 1.0
                if max(h, w) > 560:
                    scale = 560.0 / max(h, w)
                    small = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
                sh, sw = small.shape[:2]
                bs = 14
                step = 7
                q = max(2, int((1.0 - self.forensics_clone_sim) * 40))
                buckets = {}
                for yy in range(0, sh - bs, step):
                    for xx in range(0, sw - bs, step):
                        blk = small[yy:yy + bs, xx:xx + bs]
                        if float(np.std(blk)) < self.forensics_clone_detail:
                            continue
                        tiny = cv2.resize(blk, (6, 6), interpolation=cv2.INTER_AREA)
                        sig = tuple(((tiny.flatten() // q)).tolist())
                        buckets.setdefault(sig, []).append((xx, yy))
                lines = []
                for pts in buckets.values():
                    if len(pts) < 2 or len(pts) > 7:
                        continue
                    a = pts[0]
                    for b in pts[1:]:
                        if abs(a[0] - b[0]) + abs(a[1] - b[1]) < bs * 2:
                            continue
                        ax, ay = int((a[0] + bs // 2) / scale), int((a[1] + bs // 2) / scale)
                        bx, by = int((b[0] + bs // 2) / scale), int((b[1] + bs // 2) / scale)
                        lines.append(((ax, ay), (bx, by)))
                        if len(lines) > 180:
                            break
                    if len(lines) > 180:
                        break
                self.forensics_cache[key] = lines
            out = base.copy()
            for (a, b) in lines[:180]:
                cv2.circle(out, a, 4, (255, 120, 20), 1)
                cv2.circle(out, b, 4, (255, 120, 20), 1)
                cv2.line(out, a, b, (20, 20, 255), 1)
            out2 = out if np.any(out) else base
            if tool != "MAGNIFIER":
                self.forensics_render_cache[k] = out2.copy()
            return out2
        return base

    def _forensics_nudge(self, which, direction):
        """Nudge forensics slider params by tool-specific step sizes."""
        d = 1 if direction >= 0 else -1
        tool = self.forensics_tools[self.forensics_tool_idx]
        if which == "OPACITY":
            self.forensics_opacity = float(np.clip(self.forensics_opacity + d * 0.02, 0.0, 1.0))
            return
        if which == "P1":
            if tool == "ELA":
                self.forensics_ela_quality = int(np.clip(self.forensics_ela_quality + d * 2, 65, 99))
            elif tool == "NOISE":
                self.forensics_noise_amp = float(np.clip(self.forensics_noise_amp + d * 0.1, 0.6, 5.0))
            elif tool == "SWEEP":
                self.forensics_sweep = float(np.clip(self.forensics_sweep + d * 0.02, 0.0, 1.0))
            elif tool == "PCA":
                self.forensics_pca_component = int(np.clip(self.forensics_pca_component + d * 1, 1, 3))
            elif tool == "CLONE":
                self.forensics_clone_sim = float(np.clip(self.forensics_clone_sim + d * 0.01, 0.75, 0.99))
            elif tool == "MAGNIFIER":
                self.forensics_mag_zoom = int(np.clip(self.forensics_mag_zoom + d * 1, 2, 12))
            return
        if which == "P2":
            if tool == "ELA":
                self.forensics_ela_scale = float(np.clip(self.forensics_ela_scale + d * 1.0, 4.0, 40.0))
            elif tool == "SWEEP":
                self.forensics_sweep_width = float(np.clip(self.forensics_sweep_width + d * 2.0, 8.0, 100.0))
            elif tool == "CLONE":
                self.forensics_clone_detail = float(np.clip(self.forensics_clone_detail + d * 0.5, 2.0, 30.0))
            return

    def _draw_image_controls(self, img):
        """Draw collapsible image-controls panel."""
        if self.app_state not in ("LIVE", "ANALYZE_PHOTO", "ANALYZE_VIDEO"):
            return
        panel, collapse_btn, reset_btn, rows = self._img_ctrl_panel_boxes()
        self.draw_card(img, panel)
        self.draw_button(img, "-" if not self.img_ctrl_collapsed else "+", collapse_btn, bg=THEME["panel"])
        cv2.putText(
            img, "Image Controls",
            (int((panel[0] + 0.012) * WIN_W), int((panel[1] + 0.030) * WIN_H)),
            cv2.FONT_HERSHEY_SIMPLEX, THEME["font_small"], THEME["accent"], 1
        )
        if self.img_ctrl_collapsed:
            return
        for row in rows:
            key = row["key"]; label = row["label"]; vmin = row["vmin"]; vmax = row["vmax"]
            rx, ry, rw, rh = row["bar"]
            x1, y1, x2, y2 = int(rx * WIN_W), int(ry * WIN_H), int((rx + rw) * WIN_W), int((ry + rh) * WIN_H)
            cv2.rectangle(img, (x1, y1), (x2, y2), THEME["bg_card_raised"], -1)
            cv2.rectangle(img, (x1, y1), (x2, y2), THEME["border"], 1)
            val = float(self.img_ctrl_vals[key])
            t = 0.0 if vmax <= vmin else (val - vmin) / (vmax - vmin)
            tx = int(x1 + np.clip(t, 0, 1) * max(1, x2 - x1))
            cv2.circle(img, (tx, (y1 + y2) // 2), 4, THEME["accent"], -1)
            cv2.putText(
                img, f"{label}: {val:.2f}",
                (int((panel[0] + 0.012) * WIN_W), int((ry + 0.010) * WIN_H)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.40, THEME["text_light"], 1
            )
        self.draw_button(img, "Reset", reset_btn, bg=THEME["panel"])

    def _draw_loading_screen(self, display):
        """PS2 boot + Animus: dark field, sync bar, angular frame."""
        win_w, win_h = WIN_W, WIN_H
        display[:] = THEME["bg_dark"]
        # Angular frame corners (Animus-style brackets)
        m = 80
        acc = THEME["accent"]
        cv2.line(display, (m, 60), (m + 120, 60), acc, 2)
        cv2.line(display, (m, 60), (m, 180), acc, 2)
        cv2.line(display, (win_w - m, 60), (win_w - m - 120, 60), acc, 2)
        cv2.line(display, (win_w - m, 60), (win_w - m, 180), acc, 2)
        cv2.line(display, (m, win_h - 80), (m + 100, win_h - 80), acc, 2)
        cv2.line(display, (m, win_h - 80), (m, win_h - 200), acc, 2)
        cv2.line(display, (win_w - m, win_h - 80), (win_w - m - 100, win_h - 80), acc, 2)
        cv2.line(display, (win_w - m, win_h - 80), (win_w - m, win_h - 200), acc, 2)
        # Title — Animus typography
        cv2.putText(display, "CLOUTVISION", (int(win_w*0.30), int(win_h*0.38)), cv2.FONT_HERSHEY_SIMPLEX, THEME["font_title"], THEME["accent"], THEME["thickness_heavy"])
        cv2.putText(display, "SYSTEM INIT", (int(win_w*0.395), int(win_h*0.44)), cv2.FONT_HERSHEY_SIMPLEX, THEME["font_small"], THEME["text_muted"], THEME["thickness"])
        # Sync bar — double-line Animus style
        bar_margin = int(win_w * 0.20)
        bar_x1, bar_x2 = bar_margin, win_w - bar_margin
        bar_y = int(win_h * 0.52)
        bar_h = 6
        cv2.rectangle(display, (bar_x1, bar_y - 2), (bar_x2, bar_y + bar_h), THEME["border"], 1)
        fill_w = int((bar_x2 - bar_x1 - 4) * max(0, min(1, self.loading_progress)))
        if fill_w > 0:
            cv2.rectangle(display, (bar_x1 + 2, bar_y), (bar_x1 + 2 + fill_w, bar_y + bar_h - 2), THEME["accent"], -1)
        cv2.putText(display, "SYNC", (bar_x1, bar_y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.38, THEME["text_muted"], 1)
        idx = min(self.loading_step, len(self.loading_messages) - 1)
        msg = self.loading_messages[idx]
        cv2.putText(display, msg.upper(), (bar_x1, bar_y + bar_h + 24), cv2.FONT_HERSHEY_SIMPLEX, THEME["font_small"], THEME["text_dim"], THEME["thickness"])
        pct = int(self.loading_progress * 100)
        cv2.putText(display, f"{pct}%", (bar_x2 - 44, bar_y + bar_h + 24), cv2.FONT_HERSHEY_SIMPLEX, THEME["font_small"], THEME["accent"], THEME["thickness"])
        self._scanline_overlay(display, step=4, dim=0.08)

    # ---------------------------------------------------------
    # MAC BRIDGES & MEDIA
    # ---------------------------------------------------------
    def select_file_mac(self, kind):
        types = '{"public.image"}' if kind == "PHOTO" else '{"public.movie"}' if kind == "VIDEO" else '{"public.audio"}' if kind == "AUDIO" else '{"public.text", "com.adobe.pdf"}'
        script = f'set f to choose file with prompt "Select {kind} for Analysis" of type {types}\nPOSIX path of f'
        try:
            return subprocess.check_output(['osascript', '-e', script]).decode('utf-8').strip()
        except (subprocess.CalledProcessError, FileNotFoundError, OSError) as e:
            print(f"[CloutVision] File picker: {e}")
            return None

    def _get_available_camera_indices(self, max_try=3):
        """Return list of camera indices that open successfully (0, 1, 2...)."""
        available = []
        for i in range(max_try):
            cap = cv2.VideoCapture(i)
            if cap and cap.isOpened():
                available.append(i)
                cap.release()
        return available

    def _webcam_first_order(self, available):
        """Order indices so built-in webcam is preferred. On many Macs with Continuity, 0=iPhone and 1=built-in."""
        order = [1, 0, 2]  # try 1 (built-in) first, then 0, then 2
        return [i for i in order if i in available] or available

    def _webcam_only_order(self, available):
        """Prefer non-phone webcams only (skip likely iPhone continuity index 0)."""
        preferred = [1, 2, 3, 4]
        webcams = [i for i in preferred if i in available and i != 0]
        if webcams:
            return webcams
        return [i for i in available if i != 0]

    def _open_camera_at(self, index):
        """Open camera at given index; set resolution. Returns True if opened."""
        if self.cap:
            self.cap.release()
            self.cap = None
        try:
            self.cap = cv2.VideoCapture(index)
        except Exception as e:
            self._log_error("camera", f"cv2.VideoCapture({index}) failed: {e}")
            self.cap = None
            return False
        if not self.cap or not self.cap.isOpened():
            self._log_error("camera", f"Camera index {index} could not be opened")
            return False
        self.cam_index = index
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 960)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 540)
        self.error_message = None
        return True

    def set_camera_for_spooky(self):
        """Use built-in webcam first (skip Continuity/phone when possible)."""
        available = self._get_available_camera_indices()
        for idx in self._webcam_only_order(available):
            if self._open_camera_at(idx):
                return
        self.error_message = "Camera could not be opened."
        self._log_error("camera", "set_camera_for_spooky: no camera opened")

    def cycle_camera(self, allow_phone=False):
        """Cycle camera; default path skips iPhone until explicitly allowed."""
        available = self._get_available_camera_indices()
        if not available:
            self.error_message = "No camera found."
            self._log_error("camera", "No camera found in cycle_camera()")
            return
        candidates = available if allow_phone else self._webcam_only_order(available)
        if not candidates:
            self.error_message = "No webcam found. Use Camera button in Settings for iPhone."
            self._log_error("camera", "No webcam candidate found (phone-only devices present)")
            return
        # First time or no cap: open built-in webcam first (index 1 then 0 then 2)
        if not self.cap or not self.cap.isOpened():
            for idx in (self._webcam_first_order(candidates) if allow_phone else candidates):
                if self._open_camera_at(idx):
                    return
            self.error_message = "Camera could not be opened."
            return
        # Already have a camera: cycle to next in list
        try:
            current_list = candidates
            next_idx = (current_list.index(self.cam_index) + 1) % len(current_list)
        except ValueError:
            next_idx = 0
        if not self._open_camera_at(candidates[next_idx]):
            self.error_message = "Camera could not be opened."
            self._log_error("camera", f"cycle_camera: index {candidates[next_idx]} failed")

    def close_all_media(self):
        if self.cap: self.cap.release(); self.cap = None
        if self.vid_cap: self.vid_cap.release(); self.vid_cap = None
        if self.audio_enabled:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass

    def sync_media(self):
        if self.vid_cap: self.vid_cap.set(cv2.CAP_PROP_POS_FRAMES, self.vid_current)
        if self.audio_enabled and self.app_state == "ANALYZE_AUDIO" and self.audio_length > 0:
            scrub_time = (self.vid_current / max(1, self.vid_total)) * self.audio_length
            try:
                pygame.mixer.music.play(0, start=scrub_time)
            except Exception as e:
                print(f"[CloutVision] Audio sync: {e}")

    def letterbox(self, img, expected_w=None, expected_h=None):
        if expected_w is None: expected_w = WIN_W
        if expected_h is None: expected_h = WIN_H
        h, w = img.shape[:2]
        scale = min(expected_w/w, expected_h/h)
        new_w, new_h = int(w * scale), int(h * scale)
        resized = cv2.resize(img, (new_w, new_h))
        self._letterbox_canvas.fill(0)
        y_off, x_off = (expected_h - new_h) // 2, (expected_w - new_w) // 2
        self._letterbox_canvas[y_off:y_off+new_h, x_off:x_off+new_w] = resized
        return self._letterbox_canvas.copy()

    def _imread_any(self, filepath):
        """
        Robust image loader:
        - First try cv2.imread (fast path for JPEG/PNG, etc.)
        - If that fails and the file is HEIF/HEIC, try pillow-heif + Pillow.
        """
        if not filepath:
            return None
        img = cv2.imread(filepath, cv2.IMREAD_COLOR)
        if img is not None:
            return img

        ext = Path(filepath).suffix.lower()
        if ext in (".heif", ".heic") and HAS_HEIF:
            try:
                from pillow_heif import read_heif  # type: ignore
                from PIL import Image  # Pillow is already a dependency
                heif_file = read_heif(filepath)
                pil_img = Image.frombytes(heif_file.mode, heif_file.size, heif_file.data, "raw")
                arr = np.array(pil_img)
                if arr.ndim == 2:
                    return cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
                if arr.shape[2] == 3:
                    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
                if arr.shape[2] == 4:
                    return cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
                return arr
            except Exception as e:
                self._log_error("imageio", f"HEIF decode failed: {e}")
                return None
        elif ext in (".heif", ".heic") and not HAS_HEIF:
            self._log_error("imageio", "pillow-heif not installed; cannot decode HEIF/HEIC. Install with `pip install pillow-heif`.")
        return None

    def load_metadata_mac(self, filepath):
        """Pull as much metadata as mdls exposes, plus GPS if present, and reset cached map tile."""
        self.extracted_exif = []
        self.photo_gps = None
        self.photo_map_tile = None
        try:
            out = subprocess.check_output(['mdls', filepath], stderr=subprocess.STDOUT).decode('utf-8', errors='replace')
        except Exception as e:
            self.extracted_exif = [f"Metadata Error: {e}"]
            self._log_error("metadata", f"mdls failed: {e}")
            return
        try:
            for raw in out.splitlines():
                if ' = ' not in raw or 'kMDItem' not in raw:
                    continue
                key_raw, val_raw = raw.split('=', 1)
                key = key_raw.strip().replace('kMDItem', '')
                val = val_raw.strip()
                # Strip outer quotes for simple strings
                if val.startswith('"') and val.endswith('"'):
                    val = val[1:-1]
                # Normalize arrays/dicts into compact one-line strings
                val_clean = ' '.join(val.split())
                self.extracted_exif.append(f"{key}: {val_clean}"[:90])
                # GPS extraction for Latitude / Longitude
                k_lower = key.lower()
                if "latitude" in k_lower or "longitude" in k_lower:
                    try:
                        # mdls often prints like "37.7749" or "37.7749 (approx)"
                        num = float(val_clean.split()[0])
                        if "latitude" in k_lower:
                            lat = num
                            lon = None if not self.photo_gps else self.photo_gps[1]
                            self.photo_gps = (lat, lon)
                        else:
                            lon = num
                            lat = None if not self.photo_gps else self.photo_gps[0]
                            self.photo_gps = (lat, lon)
                    except Exception:
                        continue
            if not self.extracted_exif:
                self.extracted_exif = ["No MDLS data found."]
            self._build_day_route_and_nearby(filepath)
        except Exception as e:
            self.extracted_exif = [f"Metadata Error: {e}"]
            self._log_error("metadata", f"parse error: {e}")

    def _build_day_route_and_nearby(self, filepath):
        """Build same-day GPS route + nearby shots from files in same directory."""
        self.day_route_points = []
        self.nearby_shots = []
        if not self.photo_gps or self.photo_gps[0] is None or self.photo_gps[1] is None:
            return
        try:
            p = Path(filepath)
            if not p.exists():
                return
            day = datetime.fromtimestamp(p.stat().st_mtime).date()
            exts = {".jpg", ".jpeg", ".png", ".heic", ".mov", ".mp4"}
            items = sorted([x for x in p.parent.iterdir() if x.suffix.lower() in exts], key=lambda q: q.stat().st_mtime)[:300]
            cur_lat, cur_lon = self.photo_gps
            for item in items:
                try:
                    d = datetime.fromtimestamp(item.stat().st_mtime)
                    if d.date() != day:
                        continue
                    out = subprocess.check_output(["mdls", str(item)], stderr=subprocess.STDOUT).decode("utf-8", errors="replace")
                    lat, lon = None, None
                    for ln in out.splitlines():
                        if "Latitude" in ln and "=" in ln:
                            try: lat = float(ln.split("=")[1].strip().split()[0])
                            except Exception: pass
                        if "Longitude" in ln and "=" in ln:
                            try: lon = float(ln.split("=")[1].strip().split()[0])
                            except Exception: pass
                    if lat is None or lon is None:
                        continue
                    self.day_route_points.append({"lat": lat, "lon": lon, "ts": d.timestamp(), "path": str(item)})
                    # nearby within ~300m (very rough degree conversion)
                    dlat = (lat - cur_lat) * 111000.0
                    dlon = (lon - cur_lon) * 111000.0 * math.cos(math.radians(cur_lat))
                    dist_m = (dlat**2 + dlon**2) ** 0.5
                    dt_min = abs(d.timestamp() - p.stat().st_mtime) / 60.0
                    if dist_m <= 300 and dt_min <= 180:
                        self.nearby_shots.append((dist_m, dt_min, item.name, str(item)))
                except Exception:
                    continue
            self.nearby_shots.sort(key=lambda t: (t[0], t[1]))
        except Exception as e:
            self._log_error("geo", str(e))

    def _copy_to_clipboard(self, text):
        """Copy text to system clipboard (Mac: pbcopy). Sets ocr_copied_at for toast."""
        if not text or not str(text).strip():
            return
        try:
            proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE, universal_newlines=True)
            proc.communicate(input=str(text).strip())
            self.ocr_copied_at = time.time()
        except Exception as e:
            print(f"[CloutVision] Clipboard: {e}")
            self._log_error("clipboard", str(e))

    def _log_error(self, source, msg):
        """Append an entry to the rolling error log (also print to console)."""
        try:
            ts = datetime.now().strftime("%H:%M:%S")
        except Exception:
            ts = "??:??:??"
        line = f"[{ts}] {source}: {msg}"
        print(f"[CloutVision] {line}")
        self.error_log.append(line)
        if len(self.error_log) > 200:
            self.error_log.pop(0)

    def _compute_focus_saliency(self, frame):
        """Fast, local saliency map: brighter where edges/contrast are strong."""
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            small = cv2.resize(gray, (0, 0), fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
            blur = cv2.GaussianBlur(small, (7, 7), 0)
            lap = cv2.Laplacian(blur, cv2.CV_32F)
            sal = np.abs(lap)
            sal = cv2.GaussianBlur(sal, (9, 9), 0)
            sal = cv2.resize(sal, (frame.shape[1], frame.shape[0]))
            sal = cv2.normalize(sal, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
            return sal
        except Exception as e:
            self._log_error("focus", str(e))
            return None

    def _analyze_jpeg_file(self, filepath):
        """Populate JPEG forensics info: quant tables, markers, strings, thumbnail, C2PA hints."""
        self.forensics_jpeg_lines = []
        self.forensics_thumb = None
        self.forensics_thumb_diff = None
        try:
            p = Path(filepath)
            if not p.exists():
                self.forensics_jpeg_lines = ["File missing on disk."]
                return
            data = p.read_bytes()
        except Exception as e:
            self.forensics_jpeg_lines = [f"Read error: {e}"]
            return

        lines = []
        if not (len(data) > 4 and data[0] == 0xFF and data[1] == 0xD8):
            self.forensics_jpeg_lines = ["Not a JPEG file (no SOI marker)."]
            return

        # Marker scan
        markers = []
        qt_hashes = []
        i = 2
        try:
            while i + 3 < len(data):
                if data[i] != 0xFF:
                    i += 1
                    continue
                while i < len(data) and data[i] == 0xFF:
                    i += 1
                if i >= len(data):
                    break
                marker = data[i]
                i += 1
                if marker in (0xD8, 0xD9):  # SOI/EOI
                    markers.append(f"{i:06d}: FF{marker:02X}")
                    continue
                if i + 2 > len(data):
                    break
                seg_len = int.from_bytes(data[i:i+2], "big")
                seg_start = i - 2
                seg_end = i + seg_len
                markers.append(f"{seg_start:06d}: FF{marker:02X} len={seg_len}")
                if marker == 0xDB and seg_start + seg_len <= len(data):
                    # DQT
                    payload = data[i+2:seg_start+seg_len]
                    if payload:
                        qt_hashes.append(hash(payload[:64]))
                i = seg_end
        except Exception:
            pass

        if qt_hashes:
            uniq = len(set(qt_hashes))
            lines.append(f"Quant tables: {len(qt_hashes)} (unique: {uniq})")
        else:
            lines.append("Quant tables: none parsed (non-standard or missing).")
        lines.append(f"Markers: {len(markers)} segments")
        for m in markers[:12]:
            lines.append(f"  {m}")
        if len(markers) > 12:
            lines.append(f"  ... {len(markers)-12} more")

        # String extraction
        try:
            ascii_bytes = [b for b in data if 32 <= b <= 126]
            text = bytes(ascii_bytes).decode("ascii", errors="ignore")
            found = []
            cur = ""
            for ch in text:
                if ch.isprintable():
                    cur += ch
                else:
                    if len(cur) >= 8:
                        found.append(cur.strip())
                    cur = ""
            if len(cur) >= 8:
                found.append(cur.strip())
            uniq = []
            for s in found:
                if any(c < " " for c in s):
                    continue
                if s in uniq:
                    continue
                uniq.append(s)
            if uniq:
                lines.append("Strings:")
                for s in uniq[:6]:
                    tag = ""
                    if "FBMD" in s:
                        tag = " (Facebook bFBMD)"
                    if "c2pa" in s.lower():
                        tag = (tag + " " if tag else "") + "(C2PA hint)"
                    lines.append(f"  {s[:80]}{tag}")
                if len(uniq) > 6:
                    lines.append(f"  ... {len(uniq)-6} more")
        except Exception:
            pass

        # C2PA presence (very lightweight)
        try:
            idx = data.find(b"c2pa")
            if idx >= 0:
                slice_end = min(len(data), idx + 96)
                snippet = data[idx:slice_end].decode("ascii", errors="ignore")
                lines.append(f"C2PA: signature-like block at offset {idx}")
                lines.append(f"  Snippet: {snippet[:80]}")
            else:
                lines.append("C2PA: no obvious c2pa JUMBF marker found.")
        except Exception:
            pass

        # Thumbnail extraction & diff via piexif
        try:
            exif = piexif.load(data)
            thumb_bytes = exif.get("thumbnail") or exif.get("1st", {}).get(piexif.ThumbnailIFD.JPEGInterchangeFormat, None)
            if thumb_bytes:
                arr = np.frombuffer(thumb_bytes, np.uint8)
                thumb = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if thumb is not None:
                    self.forensics_thumb = thumb
                    lines.append(f"Thumbnail: {thumb.shape[1]}x{thumb.shape[0]}")
                    try:
                        main = cv2.imread(filepath)
                        if main is not None:
                            main_small = cv2.resize(main, (thumb.shape[1], thumb.shape[0]), interpolation=cv2.INTER_AREA)
                            diff = cv2.absdiff(main_small, thumb)
                            diff = cv2.normalize(diff, None, 0, 255, cv2.NORM_MINMAX)
                            self.forensics_thumb_diff = diff
                            lines.append("Thumbnail diff: computed (preview vs main).")
                    except Exception:
                        pass
        except Exception as e:
            self._log_error("jpeg", f"thumbnail parse failed: {e}")

        self.forensics_jpeg_lines = lines or ["No JPEG-specific info extracted."]

    def _fetch_osm_tile(self, lat, lon, zoom=14):
        """Fetch a small OpenStreetMap tile for given lat/lon. Returns BGR image or None."""
        if lat is None or lon is None:
            return None
        try:
            # Slippy map tiling
            lat_rad = math.radians(lat)
            n = 2.0 ** zoom
            xtile = int((lon + 180.0) / 360.0 * n)
            ytile = int((1.0 - math.log(math.tan(lat_rad) + (1 / math.cos(lat_rad))) / math.pi) / 2.0 * n)
            url = f"https://tile.openstreetmap.org/{zoom}/{xtile}/{ytile}.png"
            with urllib.request.urlopen(url, timeout=3) as resp:
                data = resp.read()
            arr = np.frombuffer(data, np.uint8)
            tile = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            return tile
        except Exception as e:
            self._log_error("map", str(e))
            return None

    def _angle_deg(self, a, b, c):
        """Angle ABC in degrees for 2D points."""
        try:
            ba = np.array([a[0]-b[0], a[1]-b[1]], dtype=np.float32)
            bc = np.array([c[0]-b[0], c[1]-b[1]], dtype=np.float32)
            nba = np.linalg.norm(ba); nbc = np.linalg.norm(bc)
            if nba < 1e-6 or nbc < 1e-6:
                return 0.0
            cosang = float(np.clip(np.dot(ba, bc) / (nba * nbc), -1.0, 1.0))
            return float(np.degrees(np.arccos(cosang)))
        except Exception:
            return 0.0

    def _translate_text_local(self, text):
        """Offline translation via argos-translate if available; fallback original."""
        if not text or not text.strip():
            return text
        if not HAS_ARGOS:
            return text
        try:
            langs = argos_translate.get_installed_languages()
            from_lang = next((l for l in langs if l.code == "en"), None)
            to_lang = next((l for l in langs if l.code == "es"), None)
            if from_lang is None or to_lang is None:
                return text
            tr = from_lang.get_translation(to_lang)
            return tr.translate(text)
        except Exception as e:
            self._log_error("translate", str(e))
            return text

    def _build_doc_blocks(self, boxes):
        """Group OCR word boxes into line-like blocks for smart document mode."""
        if not boxes:
            return []
        # sort by y then x
        words = sorted(boxes, key=lambda b: (b["y"], b["x"]))
        lines = []
        for b in words:
            placed = False
            for ln in lines:
                if abs(b["y"] - ln["y"]) < max(10, int(0.5 * ln["h"])):
                    ln["words"].append(b)
                    ln["y"] = int((ln["y"] + b["y"]) / 2)
                    ln["h"] = max(ln["h"], b["h"])
                    placed = True
                    break
            if not placed:
                lines.append({"y": b["y"], "h": b["h"], "words": [b]})
        blocks = []
        for ln in lines:
            ws = sorted(ln["words"], key=lambda w: w["x"])
            text = " ".join(w["text"] for w in ws if w["text"].strip())
            if not text:
                continue
            x1 = min(w["x"] for w in ws); y1 = min(w["y"] for w in ws)
            x2 = max(w["x"] + w["w"] for w in ws); y2 = max(w["y"] + w["h"] for w in ws)
            blocks.append({"text": text, "bbox": (x1, y1, x2-x1, y2-y1)})
        return blocks

    def _doc_suggestion(self, text):
        t = text.strip()
        if re.search(r"\b[A-Z0-9]{6,}\b", t):
            return "Copy code"
        if re.search(r"\b\d{10,22}\b", t):
            return "Copy tracking number"
        if re.search(r"\d+\s+\w+.*\b(ST|AVE|RD|BLVD|DR|LN)\b", t, re.IGNORECASE):
            return "Copy address"
        return "Copy text"

    def _export_clean_scan_pdf(self, img_bgr):
        """Deskew + binarize and save as high-contrast PDF."""
        try:
            gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
            blur = cv2.GaussianBlur(gray, (5, 5), 0)
            th = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 35, 11)
            coords = np.column_stack(np.where(th < 255))
            angle = 0.0
            if len(coords) > 100:
                rect = cv2.minAreaRect(coords)
                angle = rect[-1]
                if angle < -45:
                    angle = -(90 + angle)
                else:
                    angle = -angle
            (h, w) = th.shape[:2]
            M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
            deskew = cv2.warpAffine(th, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
            ts = int(time.time())
            png_path = f"clean_scan_{ts}.png"
            pdf_path = f"clean_scan_{ts}.pdf"
            cv2.imwrite(png_path, deskew)
            doc = fitz.open()
            rect = fitz.Rect(0, 0, w, h)
            page = doc.new_page(width=w, height=h)
            page.insert_image(rect, filename=png_path)
            doc.save(pdf_path)
            doc.close()
            self._log_error("doc", f"Clean scan exported: {pdf_path}")
            return pdf_path
        except Exception as e:
            self._log_error("doc", str(e))
            return None

    def _analyze_pose_intel(self, frame, person_box=None):
        """Action/posture + body metrics + pseudo-depth estimates from cached pose."""
        self.current_posture = "UNKNOWN"
        self.current_action = "NONE"
        self.current_person_metrics = {}
        if self.cached_pose is None or len(self.cached_pose) < 17:
            return
        k = self.cached_pose
        l_sh, r_sh = k[5], k[6]
        l_hip, r_hip = k[11], k[12]
        l_knee, r_knee = k[13], k[14]
        l_ank, r_ank = k[15], k[16]
        l_el, r_el = k[7], k[8]
        l_wr, r_wr = k[9], k[10]
        # posture
        hip_y = (l_hip[1] + r_hip[1]) / 2.0
        knee_y = (l_knee[1] + r_knee[1]) / 2.0
        ank_y = (l_ank[1] + r_ank[1]) / 2.0
        hip_x = (l_hip[0] + r_hip[0]) / 2.0
        self.hip_x_hist.append(hip_x)
        if len(self.hip_x_hist) > 20:
            self.hip_x_hist.pop(0)
        paced = (max(self.hip_x_hist) - min(self.hip_x_hist)) > 35 if len(self.hip_x_hist) > 5 else False
        if abs(hip_y - knee_y) < 35:
            self.current_posture = "SITTING"
        elif paced:
            self.current_posture = "PACED"
        elif (ank_y - hip_y) > 80:
            self.current_posture = "STANDING"
        shoulder_mid = ((l_sh[0] + r_sh[0]) / 2.0, (l_sh[1] + r_sh[1]) / 2.0)
        hip_mid = ((l_hip[0] + r_hip[0]) / 2.0, (l_hip[1] + r_hip[1]) / 2.0)
        # action
        hand_up = (l_wr[1] < l_sh[1] and abs(l_el[0] - l_wr[0]) < 80) or (r_wr[1] < r_sh[1] and abs(r_el[0] - r_wr[0]) < 80)
        point = (abs(l_wr[0] - l_sh[0]) > 120 and self._angle_deg(l_sh, l_el, l_wr) > 150) or (abs(r_wr[0] - r_sh[0]) > 120 and self._angle_deg(r_sh, r_el, r_wr) > 150)
        # Simple wave detection via raised wrist horizontal oscillation
        active_wx = l_wr[0] if l_wr[1] < l_sh[1] else (r_wr[0] if r_wr[1] < r_sh[1] else None)
        if active_wx is not None:
            self.wrist_x_hist.append(float(active_wx))
            if len(self.wrist_x_hist) > 12:
                self.wrist_x_hist.pop(0)
        else:
            self.wrist_x_hist = []
        wave = (len(self.wrist_x_hist) >= 6 and (max(self.wrist_x_hist) - min(self.wrist_x_hist)) > 55)
        # Squat/push-up first pass heuristics
        squat = self.current_posture == "SITTING" and ((self._angle_deg(l_hip, l_knee, l_ank) + self._angle_deg(r_hip, r_knee, r_ank)) * 0.5) < 115
        pushup = (hip_y > shoulder_mid[1] + 30) and (abs(l_el[1] - l_sh[1]) < 35 or abs(r_el[1] - r_sh[1]) < 35)
        thumbs_up = ((l_wr[1] < l_el[1] < l_sh[1]) and abs(l_wr[0] - l_el[0]) < 25) or ((r_wr[1] < r_el[1] < r_sh[1]) and abs(r_wr[0] - r_el[0]) < 25)
        if wave:
            self.current_action = "WAVE"
        elif thumbs_up:
            self.current_action = "THUMBS-UP"
        elif pushup:
            self.current_action = "PUSH-UP"
        elif squat:
            self.current_action = "SQUAT"
        elif point:
            self.current_action = "POINT"
        elif hand_up:
            self.current_action = "HAND UP"
        elif self.current_posture == "PACED":
            self.current_action = "WALKING"
        # metrics
        back_vec = np.array([shoulder_mid[0] - hip_mid[0], shoulder_mid[1] - hip_mid[1]], dtype=np.float32)
        back_angle = float(abs(np.degrees(np.arctan2(back_vec[0], -back_vec[1]))))  # lean from vertical
        if self.current_posture == "STANDING" and back_angle > 20:
            self.current_posture = "SLOUCHING"
        knee_l = self._angle_deg(l_hip, l_knee, l_ank)
        knee_r = self._angle_deg(r_hip, r_knee, r_ank)
        shoulder_sym_px = float(l_sh[1] - r_sh[1])
        # rough scale using person height pixels (if box available)
        step_px = abs(l_ank[0] - r_ank[0])
        person_h_px = (person_box[3] - person_box[1]) if person_box is not None else max(1.0, abs(ank_y - shoulder_mid[1]))
        step_m = float((step_px / max(1.0, person_h_px)) * 1.75)
        self.current_person_metrics = {
            "back_angle": back_angle,
            "knee": (knee_l + knee_r) / 2.0,
            "shoulder_sym_px": shoulder_sym_px,
            "step_m": step_m,
        }
        # wrist trail for AR effect
        self.wrist_trails.append((int((l_wr[0] + r_wr[0]) * 0.5), int((l_wr[1] + r_wr[1]) * 0.5)))
        if len(self.wrist_trails) > 30:
            self.wrist_trails.pop(0)

    def _update_session(self, person_detected):
        now = time.time()
        if not self.session_active:
            self.session_active = True
            self.session_last_ts = now
            return
        dt = max(0.0, min(1.0, now - self.session_last_ts))
        self.session_last_ts = now
        self.session_stats["live_seconds"] += dt
        if person_detected:
            self.session_stats["in_frame_seconds"] += dt
        p = self.current_posture if self.current_posture in self.session_stats["posture_seconds"] else "UNKNOWN"
        self.session_stats["posture_seconds"][p] += dt
        emo = self.emotion_label or "NEUTRAL"
        self.session_stats["emotion_counts"][emo] = self.session_stats["emotion_counts"].get(emo, 0) + 1
        act = self.current_action or "NONE"
        self.session_stats["action_counts"][act] = self.session_stats["action_counts"].get(act, 0) + 1
        self.session_stats["blinks"] = int(self.blinks)

    def _persist_session_summary(self):
        try:
            Path("session_logs").mkdir(exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            out = dict(self.session_stats)
            out["timestamp"] = ts
            path = Path("session_logs") / f"session-{ts}.json"
            path.write_text(json.dumps(out, indent=2), encoding="utf-8")
            self.session_logs.append(out)
        except Exception as e:
            self._log_error("session", str(e))

    def _ensure_mediapipe(self, need_face=False, need_pose=False):
        """Lazy-load mediapipe modules/engines only when a feature needs them."""
        global mp_face_mesh, mp_pose, mp_drawing, mp_drawing_styles, face_mesh_engine, mp_pose_engine
        if not HAS_MP:
            return False
        try:
            if mp_pose is None or mp_face_mesh is None or mp_drawing is None:
                mp = importlib.import_module("mediapipe")
                try:
                    mp_face_mesh = mp.solutions.face_mesh
                    mp_pose = mp.solutions.pose
                    mp_drawing = mp.solutions.drawing_utils
                    mp_drawing_styles = mp.solutions.drawing_styles
                except AttributeError:
                    mp_face_mesh = importlib.import_module("mediapipe.python.solutions.face_mesh")
                    mp_pose = importlib.import_module("mediapipe.python.solutions.pose")
                    mp_drawing = importlib.import_module("mediapipe.python.solutions.drawing_utils")
                    mp_drawing_styles = importlib.import_module("mediapipe.python.solutions.drawing_styles")
            if need_face and face_mesh_engine is None and mp_face_mesh is not None:
                face_mesh_engine = mp_face_mesh.FaceMesh(
                    max_num_faces=3, refine_landmarks=True, min_detection_confidence=0.5
                )
            if need_pose and mp_pose_engine is None and mp_pose is not None:
                mp_pose_engine = mp_pose.Pose(
                    static_image_mode=False,
                    model_complexity=1,
                    enable_segmentation=False,
                    min_detection_confidence=0.5,
                    min_tracking_confidence=0.5,
                )
            return True
        except Exception as e:
            self._log_error("mediapipe", str(e))
            return False

    def _run_ocr_tesseract(self, img_bgr):
        """Tesseract OCR backend (multi-pass preprocessing)."""
        if not HAS_OCR or img_bgr is None:
            return []
        try:
            min_conf = 28  # balanced confidence with stronger text-quality filtering
            candidates = []
            h0, w0 = img_bgr.shape[:2]
            # Downscale large images for much faster OCR; keep coords in original scale
            max_side = 1600
            scale_down = 1.0
            if max(h0, w0) > max_side:
                scale_down = max_side / float(max(h0, w0))
                img_proc = cv2.resize(img_bgr, (int(w0 * scale_down), int(h0 * scale_down)), interpolation=cv2.INTER_AREA)
            else:
                img_proc = img_bgr
            gray = cv2.cvtColor(img_proc, cv2.COLOR_BGR2GRAY)
            global_scale_back = 1.0 / scale_down
            max_boxes = 200

            def normalize_text(t):
                t = re.sub(r"\s+", " ", (t or "").strip())
                return t

            def with_lang(cfg):
                return f"{cfg} -l eng -c preserve_interword_spaces=1"

            def rotate_gray(src, ang_deg):
                if abs(ang_deg) < 1e-3:
                    return src
                h, w = src.shape[:2]
                M = cv2.getRotationMatrix2D((w * 0.5, h * 0.5), ang_deg, 1.0)
                return cv2.warpAffine(src, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

            def text_quality(t):
                # 0..1 quality score: prefer alnum-heavy, readable strings
                t = normalize_text(t)
                if len(t) < 2:
                    return 0.0
                alnum = sum(ch.isalnum() for ch in t)
                if alnum < 2:
                    return 0.0
                weird = sum(ch in "?|~`^<>[]" for ch in t)
                if weird / max(1, len(t)) > 0.22:
                    return 0.0
                printable = sum((32 <= ord(ch) <= 126) for ch in t)
                printable_ratio = printable / max(1, len(t))
                alnum_ratio = alnum / max(1, len(t))
                return float(0.55 * printable_ratio + 0.45 * alnum_ratio)

            def add_from_data(data, scale_back=1.0):
                for i in range(len(data.get("text", []))):
                    if len(candidates) >= max_boxes * 2:
                        break
                    txt = normalize_text(data["text"][i] or "")
                    if not txt or len(txt) < 2:
                        continue
                    conf_raw = (data["conf"][i] or "").strip()
                    conf = float(conf_raw) if conf_raw and conf_raw != "-1" else 0.0
                    if conf < min_conf:
                        continue
                    q = text_quality(txt)
                    if q < 0.45:
                        continue
                    x = int(round(data["left"][i] * scale_back))
                    y = int(round(data["top"][i] * scale_back))
                    w = max(1, int(round(data["width"][i] * scale_back)))
                    h = max(1, int(round(data["height"][i] * scale_back)))
                    # Remove tiny OCR noise fragments
                    if (w * h) < 36:
                        continue
                    score = conf * q
                    candidates.append({"x": x, "y": y, "w": w, "h": h, "text": txt, "conf": conf, "score": score})

            configs = [
                "--oem 3 --psm 6",   # block of text
                "--oem 3 --psm 3",   # fully automatic
                "--oem 3 --psm 11",  # sparse text (labels, logos)
                "--oem 3 --psm 7",   # single text line (signs)
            ]

            # 1) Plain grayscale — multiple PSM modes
            for cfg in configs:
                try:
                    data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT, config=with_lang(cfg))
                    add_from_data(data, scale_back=global_scale_back)
                except Exception:
                    pass

            # 2) CLAHE — improves contrast on product photos
            try:
                clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                gray_clahe = clahe.apply(gray)
                data = pytesseract.image_to_data(gray_clahe, output_type=pytesseract.Output.DICT, config=with_lang("--oem 3 --psm 6"))
                add_from_data(data, scale_back=global_scale_back)
            except Exception:
                pass

            # 3) Adaptive threshold — good for labels on colored background
            try:
                thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
                data = pytesseract.image_to_data(thresh, output_type=pytesseract.Output.DICT, config=with_lang("--oem 3 --psm 6"))
                add_from_data(data, scale_back=global_scale_back)
            except Exception:
                pass

            # 4) Otsu
            try:
                _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                data = pytesseract.image_to_data(otsu, output_type=pytesseract.Output.DICT, config=with_lang("--oem 3 --psm 6"))
                add_from_data(data, scale_back=global_scale_back)
            except Exception:
                pass

            # 5) Slight sharpen — helps small text on cans/bottles
            try:
                kernel = np.array([[-0.5, -0.5, -0.5], [-0.5, 5.0, -0.5], [-0.5, -0.5, -0.5]])
                sharp = cv2.filter2D(gray, -1, kernel)
                data = pytesseract.image_to_data(sharp, output_type=pytesseract.Output.DICT, config=with_lang("--oem 3 --psm 11"))
                add_from_data(data, scale_back=global_scale_back)
            except Exception:
                pass

            # 6) Scaled up 1.5x — critical for small text after letterbox shrink
            try:
                scale_up = 1.5
                scaled = cv2.resize(gray, None, fx=scale_up, fy=scale_up, interpolation=cv2.INTER_CUBIC)
                data = pytesseract.image_to_data(scaled, output_type=pytesseract.Output.DICT, config=with_lang("--oem 3 --psm 6"))
                add_from_data(data, scale_back=(global_scale_back / scale_up))
            except Exception:
                pass

            # 7) Inverted — light text on dark background (screenshots, dark mode, recovery codes)
            inv = 255 - gray
            for cfg in configs:
                try:
                    data = pytesseract.image_to_data(inv, output_type=pytesseract.Output.DICT, config=with_lang(cfg))
                    add_from_data(data, scale_back=global_scale_back)
                except Exception:
                    pass
            try:
                _, inv_thresh = cv2.threshold(inv, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                data = pytesseract.image_to_data(inv_thresh, output_type=pytesseract.Output.DICT, config=with_lang("--oem 3 --psm 6"))
                add_from_data(data, scale_back=global_scale_back)
            except Exception:
                pass

            # Optional extra pass for outdoor signs: denoise + local contrast
            try:
                den = cv2.bilateralFilter(gray, 7, 45, 45)
                clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8))
                den2 = clahe.apply(den)
                data = pytesseract.image_to_data(den2, output_type=pytesseract.Output.DICT, config=with_lang("--oem 3 --psm 7"))
                add_from_data(data, scale_back=global_scale_back)
            except Exception:
                pass

            # Scene-text boost: detect likely text strips/signs and run line OCR with mild angle sweep.
            try:
                grad = cv2.morphologyEx(gray, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8))
                _, bw = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, np.ones((17, 3), np.uint8), iterations=1)
                cnts, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                rois = []
                for c in cnts:
                    x, y, w, h = cv2.boundingRect(c)
                    if w < 50 or h < 14:
                        continue
                    ratio = w / max(1.0, float(h))
                    area = w * h
                    if ratio < 1.5 or area < 450:
                        continue
                    # Keep likely text regions near meaningful sizes
                    if h > int(gray.shape[0] * 0.35) or w > int(gray.shape[1] * 0.95):
                        continue
                    rois.append((area, x, y, w, h))
                rois.sort(reverse=True)
                rois = rois[:24]

                for _, x, y, w, h in rois:
                    pad_x = max(2, int(0.06 * w))
                    pad_y = max(2, int(0.25 * h))
                    x1 = max(0, x - pad_x); y1 = max(0, y - pad_y)
                    x2 = min(gray.shape[1], x + w + pad_x); y2 = min(gray.shape[0], y + h + pad_y)
                    roi = gray[y1:y2, x1:x2]
                    if roi.size == 0:
                        continue
                    roi = cv2.resize(roi, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
                    roi = cv2.bilateralFilter(roi, 5, 35, 35)

                    best_txt, best_q = "", 0.0
                    for ang in (-10, -6, -3, 0, 3, 6, 10):
                        rr = rotate_gray(roi, ang)
                        for cfg in ("--oem 3 --psm 7", "--oem 3 --psm 8", "--oem 3 --psm 6"):
                            try:
                                txt = normalize_text(pytesseract.image_to_string(rr, config=with_lang(cfg)))
                            except Exception:
                                txt = ""
                            q = text_quality(txt)
                            if q > best_q:
                                best_q, best_txt = q, txt
                    if best_q >= 0.58 and len(best_txt) >= 4:
                        candidates.append({
                            "x": int(round(x1 * global_scale_back)),
                            "y": int(round(y1 * global_scale_back)),
                            "w": int(round((x2 - x1) * global_scale_back)),
                            "h": int(round((y2 - y1) * global_scale_back)),
                            "text": best_txt,
                            "conf": 70.0,
                            "score": 70.0 * best_q
                        })
            except Exception:
                pass

            # NMS by IoU + score to remove duplicate noisy boxes from multi-pass OCR
            if candidates:
                candidates.sort(key=lambda c: c.get("score", 0), reverse=True)
                picked = []
                for c in candidates:
                    cb = (c["x"], c["y"], c["x"] + c["w"], c["y"] + c["h"])
                    keep = True
                    for p in picked:
                        pb = (p["x"], p["y"], p["x"] + p["w"], p["y"] + p["h"])
                        if self._box_iou(cb, pb) > 0.55:
                            keep = False
                            break
                    if keep:
                        picked.append(c)
                    if len(picked) >= max_boxes:
                        break
                results = [{"x": p["x"], "y": p["y"], "w": p["w"], "h": p["h"], "text": p["text"]} for p in picked]
            else:
                results = []

            # 8) Fallback: if no boxes, try get_string and only keep readable lines
            if not results:
                for src, cfg in [(inv, "--oem 3 --psm 6"), (gray, "--oem 3 --psm 6")]:
                    try:
                        raw = pytesseract.image_to_string(src, config=with_lang(cfg))
                        lines = [normalize_text(ln) for ln in raw.splitlines() if normalize_text(ln)]
                        lines = [ln for ln in lines if text_quality(ln) >= 0.50]
                        clean = "\n".join(lines).strip()
                        block_q = (sum(text_quality(ln) for ln in lines) / max(1, len(lines))) if lines else 0.0
                        if len(clean) > 1 and block_q >= 0.62 and len(lines) <= 8:
                            h, w = img_bgr.shape[:2]
                            results.append({"x": 0, "y": 0, "w": w, "h": h, "text": clean})
                            break
                    except Exception:
                        pass

            return results
        except Exception as e:
            print(f"[CloutVision] OCR: {e}")
            self._log_error("ocr", str(e))
            return []

    def _ocr_text_quality(self, text):
        t = re.sub(r"\s+", " ", (text or "").strip())
        if len(t) < 2:
            return 0.0
        alnum = sum(ch.isalnum() for ch in t)
        if alnum < 2:
            return 0.0
        weird = sum(ch in "?|~`^<>[]{}" for ch in t)
        if weird / max(1, len(t)) > 0.22:
            return 0.0
        printable = sum(32 <= ord(ch) <= 126 for ch in t)
        return float(0.55 * (printable / max(1, len(t))) + 0.45 * (alnum / max(1, len(t))))

    def _ocr_available(self):
        return bool(HAS_OCR or HAS_PADDLE_OCR or HAS_EASY_OCR)

    def _ensure_ocr_backends(self, need_paddle=False, need_easy=False):
        global PaddleOCRReader, easyocr
        if need_paddle and self.ocr_engine_paddle is None and HAS_PADDLE_OCR:
            try:
                if PaddleOCRReader is None:
                    paddle_mod = importlib.import_module("paddleocr")
                    PaddleOCRReader = getattr(paddle_mod, "PaddleOCR", None)
                if PaddleOCRReader is None:
                    raise RuntimeError("PaddleOCR class unavailable")
                self.ocr_engine_paddle = PaddleOCRReader(use_angle_cls=True, lang="en", show_log=False)
            except Exception as e:
                self._log_error("ocr", f"paddle init failed: {e}")
                self.ocr_engine_paddle = None
        if need_easy and self.ocr_engine_easy is None and HAS_EASY_OCR:
            try:
                if easyocr is None:
                    easyocr = importlib.import_module("easyocr")
                self.ocr_engine_easy = easyocr.Reader(["en"], gpu=False)
            except Exception as e:
                self._log_error("ocr", f"easyocr init failed: {e}")
                self.ocr_engine_easy = None

    def _run_ocr_paddle(self, img_bgr):
        if self.ocr_engine_paddle is None:
            return []
        try:
            out = self.ocr_engine_paddle.ocr(img_bgr, cls=True)
            lines = out[0] if isinstance(out, list) and out else []
            results = []
            for ln in lines:
                if not ln or len(ln) < 2:
                    continue
                pts, rec = ln[0], ln[1]
                if not pts or not rec or len(rec) < 2:
                    continue
                txt = re.sub(r"\s+", " ", str(rec[0]).strip())
                conf = float(rec[1]) if rec[1] is not None else 0.0
                if conf < 0.40 or self._ocr_text_quality(txt) < 0.48:
                    continue
                xs = [int(p[0]) for p in pts]
                ys = [int(p[1]) for p in pts]
                x, y = max(0, min(xs)), max(0, min(ys))
                w, h = max(1, max(xs) - x), max(1, max(ys) - y)
                results.append({"x": x, "y": y, "w": w, "h": h, "text": txt, "score": conf * 100.0})
            return results
        except Exception as e:
            self._log_error("ocr", f"paddle run failed: {e}")
            return []

    def _run_ocr_easy(self, img_bgr):
        if self.ocr_engine_easy is None:
            return []
        try:
            rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            out = self.ocr_engine_easy.readtext(rgb, detail=1, paragraph=False)
            results = []
            for item in out:
                if not item or len(item) < 3:
                    continue
                pts, txt, conf = item[0], str(item[1]).strip(), float(item[2])
                if conf < 0.30 or self._ocr_text_quality(txt) < 0.46:
                    continue
                xs = [int(p[0]) for p in pts]
                ys = [int(p[1]) for p in pts]
                x, y = max(0, min(xs)), max(0, min(ys))
                w, h = max(1, max(xs) - x), max(1, max(ys) - y)
                results.append({"x": x, "y": y, "w": w, "h": h, "text": txt, "score": conf * 100.0})
            return results
        except Exception as e:
            self._log_error("ocr", f"easyocr run failed: {e}")
            return []

    def _merge_ocr_results(self, groups, max_boxes=220):
        flat = []
        for gi, grp in enumerate(groups):
            base_weight = 1.10 if gi == 0 else (1.00 if gi == 1 else 0.92)
            for b in grp:
                txt = re.sub(r"\s+", " ", (b.get("text") or "").strip())
                if len(txt) < 2 or self._ocr_text_quality(txt) < 0.45:
                    continue
                score = float(b.get("score", 50.0)) * base_weight
                flat.append({
                    "x": int(b["x"]), "y": int(b["y"]), "w": int(b["w"]), "h": int(b["h"]),
                    "text": txt, "score": score
                })
        if not flat:
            return []
        flat.sort(key=lambda x: x["score"], reverse=True)
        picked = []
        for c in flat:
            cb = (c["x"], c["y"], c["x"] + c["w"], c["y"] + c["h"])
            keep = True
            for p in picked:
                pb = (p["x"], p["y"], p["x"] + p["w"], p["y"] + p["h"])
                if self._box_iou(cb, pb) > 0.52:
                    keep = False
                    break
                # Also dedupe near-identical strings that overlap mildly
                if c["text"].lower() == p["text"].lower() and self._box_iou(cb, pb) > 0.18:
                    keep = False
                    break
            if keep:
                picked.append(c)
            if len(picked) >= max_boxes:
                break
        return [{"x": p["x"], "y": p["y"], "w": p["w"], "h": p["h"], "text": p["text"]} for p in picked]

    def _run_ocr_image(self, img_bgr):
        """Multi-tool OCR pipeline: Paddle/Easy/Tesseract with AUTO/FAST/ACCURATE profiles."""
        if img_bgr is None:
            return []
        # Lazy init only what each profile needs, so default runs stay lightweight.
        if self.ocr_profile == "ACCURATE":
            self._ensure_ocr_backends(need_paddle=True, need_easy=True)
        elif self.ocr_profile == "FAST":
            self._ensure_ocr_backends(need_easy=True)
        else:  # AUTO: initialize fast path first; paddle only if needed later.
            self._ensure_ocr_backends(need_easy=True)

        has_tess = HAS_OCR
        has_easy = self.ocr_engine_easy is not None
        has_paddle = self.ocr_engine_paddle is not None

        groups = []
        used = []
        if self.ocr_profile == "FAST":
            order = [("EASY", has_easy), ("TESS", has_tess)]
        elif self.ocr_profile == "ACCURATE":
            order = [("PADDLE", has_paddle), ("EASY", has_easy), ("TESS", has_tess)]
        else:
            # AUTO: prefer easy-to-run backends first.
            order = [("EASY", has_easy), ("TESS", has_tess)]

        for name, ok in order:
            if not ok:
                continue
            if name == "PADDLE":
                out = self._run_ocr_paddle(img_bgr)
            elif name == "EASY":
                out = self._run_ocr_easy(img_bgr)
            else:
                out = self._run_ocr_tesseract(img_bgr)
                # Normalize score field for merger
                out = [{**b, "score": 55.0} for b in out]
            if out:
                groups.append(out)
                used.append(name)
                # In FAST mode, stop early after first useful backend.
                if self.ocr_profile == "FAST":
                    break

        # AUTO escalation: if fast path is weak/noisy, try Paddle as an intelligence boost.
        if self.ocr_profile == "AUTO":
            merged_fast = self._merge_ocr_results(groups)
            avg_len = (sum(len(b["text"]) for b in merged_fast) / max(1, len(merged_fast))) if merged_fast else 0.0
            need_escalate = (len(merged_fast) < 3) or (avg_len < 4.0)
            if need_escalate and HAS_PADDLE_OCR:
                self._ensure_ocr_backends(need_paddle=True)
                if self.ocr_engine_paddle is not None:
                    pad = self._run_ocr_paddle(img_bgr)
                    if pad:
                        groups.insert(0, pad)
                        used.insert(0, "PADDLE")

        merged = self._merge_ocr_results(groups)
        self.ocr_last_engine = "+".join(used) if used else "NONE"
        return merged

    def capture_media(self, display):
        timestamp = int(time.time())
        cv2.imwrite(f"cv_export_{timestamp}.png", display)
        if self.export_target == "PHOTOS": subprocess.run(["osascript", "-e", f'tell application "Photos" to import POSIX file "{os.path.abspath(f"cv_export_{timestamp}.png")}"'])
        else: subprocess.run(["open", "-R", os.path.abspath(f"cv_export_{timestamp}.png")])
        self.flash_frames = 3

    # ---------------------------------------------------------
    # AI ANALYTICS & MATH ENGINES
    # ---------------------------------------------------------
    def extract_and_summarize_text(self):
        self.error_message = None
        if not self.analysis_file:
            self.app_state = "MEDIA_MENU"
            self.error_message = "No file selected."
            return
        text = ""
        mod_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            if self.clipboard_cache:
                text = self.clipboard_cache
                mod_date = "Pasted from Clipboard"
            elif self.analysis_file.endswith(".pdf"):
                doc = fitz.open(self.analysis_file)
                # Limit to first N pages to keep very large PDFs fast
                max_pages = 12
                for i, page in enumerate(doc):
                    if i >= max_pages:
                        break
                    text += page.get_text()
            else:
                try:
                    text = subprocess.check_output(['textutil', '-stdout', '-convert', 'txt', self.analysis_file]).decode('utf-8')
                except (subprocess.CalledProcessError, FileNotFoundError, OSError):
                    with open(self.analysis_file, 'r', encoding='utf-8', errors='replace') as f:
                        text = f.read()
            if not text or not text.strip():
                self.error_message = "No text content found."
                self.app_state = "MEDIA_MENU"
                return
            # Hard cap text length to avoid pathological O(n) costs on massive docs
            max_chars = 60000
            if len(text) > max_chars:
                text = text[:max_chars]
            text = re.sub(r'[^a-zA-Z0-9\s.,!?\'"-]', '', text)
            text = re.sub(r'\s+', ' ', text).strip()
            words = text.lower().split()
            # Faster word frequency using Counter instead of repeated list.count
            freq = Counter(words)
            sentences = [s.strip() for s in text.replace('!', '.').replace('?', '.').split('.') if s.strip()]
            scores = {}
            for s in sentences:
                scores[s] = sum(freq.get(w, 0) for w in s.lower().split())
            top_n = 3 if self.summary_length == "SHORT" else 8
            best = [s for s, _ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:top_n]]
            summary = ". ".join(best).strip()
            if summary and not summary.endswith('.'):
                summary += "."
            blocks = [p.strip() for p in text.split("\n\n") if p.strip()] or [text.strip()]
            self.text_data = {"date": mod_date, "words": len(words), "chars": len(text), "summary": summary, "raw": text, "blocks": blocks}
            self.app_state = "ANALYZE_TEXT"
        except (OSError, ValueError, RuntimeError) as e:
            self.app_state = "MEDIA_MENU"
            self.error_message = f"Could not load or summarize text: {e}"
            print(f"[CloutVision] extract_and_summarize_text: {e}")
        except Exception as e:
            self.app_state = "MEDIA_MENU"
            self.error_message = "Could not load or summarize text."
            print(f"[CloutVision] extract_and_summarize_text: {e}")

    def generate_audio_visuals(self, filepath):
        """Load audio file, build spectrogram, set ANALYZE_AUDIO state and start playback."""
        self.error_message = None
        self.audio_data = None
        if not self.audio_enabled:
            self.app_state = "MEDIA_MENU"
            self.error_message = "Audio device unavailable on this system."
            return
        try:
            if self._librosa is None:
                self._librosa = importlib.import_module("librosa")
            librosa_mod = self._librosa
            pygame.mixer.music.load(filepath)
            duration = librosa_mod.get_duration(path=filepath)
            self.audio_length = float(duration)
            self.vid_total = max(1, int(self.audio_length * 30))
            self.vid_current = 0
            self.is_playing = True
            y, sr = librosa_mod.load(filepath, sr=22050, duration=min(60, self.audio_length))
            S = librosa_mod.feature.melspectrogram(y=y, sr=sr, n_mels=128, fmax=8000)
            S_db = librosa_mod.power_to_db(S, ref=np.max)
            S_norm = (S_db - S_db.min()) / max(S_db.max() - S_db.min(), 1e-8)
            S_img = (S_norm * 255).astype(np.uint8)
            S_img = np.flipud(S_img)
            S_bgr = cv2.applyColorMap(S_img, cv2.COLORMAP_VIRIDIS)
            self.audio_data = cv2.resize(S_bgr, (WIN_W, 500))
            self.app_state = "ANALYZE_AUDIO"
            pygame.mixer.music.play()
        except Exception as e:
            self.app_state = "MEDIA_MENU"
            self.audio_data = None
            self.audio_length = 0
            self.error_message = f"Could not load audio: {e}"
            print(f"[CloutVision] generate_audio_visuals: {e}")

    def analyze_emotion(self, mesh):
        """Landmark-based emotion: scale-invariant EAR/MAR, brow, smile. Returns instantaneous best guess."""
        n = len(mesh)
        def y_(i): return mesh[i].y if i < n and hasattr(mesh[i], 'y') else 0.0
        def x_(i): return mesh[i].x if i < n and hasattr(mesh[i], 'x') else 0.0
        eye_w = max(1e-5, abs(x_(133) - x_(362)))
        left_h = abs(y_(159) - y_(145)); left_w = max(1e-5, abs(x_(33) - x_(133)))
        right_h = abs(y_(386) - y_(374)); right_w = max(1e-5, abs(x_(263) - x_(362)))
        ear = (left_h / left_w + right_h / right_w) / 2.0
        mar = abs(y_(13) - y_(14)) / eye_w
        smile_w = abs(x_(61) - x_(291)) / eye_w
        brow_avg = (y_(70) + y_(300)) / 2.0
        nose_y = y_(1)
        brow_lowered = brow_avg > nose_y + 0.02
        brow_raised = brow_avg < nose_y - 0.03
        # Auxiliary states (do not necessarily represent long-term emotion)
        if ear < 0.035: return "BLINKING"
        if mar > 0.26 and ear > 0.08: return "SURPRISED"
        if mar > 0.18 and smile_w <= 0.5: return "TALKING"
        # Primary valence/arousal buckets
        if smile_w > 0.60 and mar < 0.16: return "HAPPY"
        if brow_lowered and smile_w < 0.4: return "ANGRY"
        if brow_lowered and mar < 0.12: return "SAD"
        if brow_raised and mar > 0.12: return "FEARFUL"
        if mar > 0.12 and smile_w < 0.35: return "CONCENTRATING"
        if brow_raised: return "INTERESTED"
        return "NEUTRAL"

    def _bgr_to_hex(self, b, g, r):
        """Convert BGR to #RRGGBB hex string."""
        return "#{:02X}{:02X}{:02X}".format(r, g, b)

    def _hsv_to_color_name(self, hue, sat, val, bgr_tuple):
        """Map OpenCV HSV (H 0-180, S/V 0-255) to a readable color name. Expanded set for design/UI use."""
        b, g, r = bgr_tuple
        # Achromatic / neutrals (check first)
        if val < 30: return bgr_tuple, "BLACK"
        if val < 55 and sat < 60: return bgr_tuple, "CHARCOAL"
        if val < 85 and sat < 50: return bgr_tuple, "DARK GRAY"
        if val < 140 and sat < 45: return bgr_tuple, "GRAY"
        if val < 200 and sat < 45: return bgr_tuple, "SILVER"
        if sat < 40 and val >= 200: return bgr_tuple, "WHITE"
        if sat < 55 and val >= 180: return bgr_tuple, "OFF-WHITE"
        if sat < 70 and 140 <= val < 220 and 8 <= hue < 25: return bgr_tuple, "CREAM"
        if sat < 70 and 100 <= val < 180 and 18 <= hue < 35: return bgr_tuple, "BEIGE"
        if sat < 85 and 80 <= val < 160 and 15 <= hue < 35: return bgr_tuple, "TAN"
        if sat < 90 and val < 120 and (hue < 15 or hue > 165): return bgr_tuple, "BROWN"
        if sat < 90 and val < 100 and 15 <= hue < 28: return bgr_tuple, "DARK BROWN"
        if sat >= 40 and val < 100 and (hue < 12 or hue > 168): return bgr_tuple, "MAROON"
        # Chromatic: OpenCV H 0-180 (red 0 & ~176)
        if hue < 5 or hue > 175: return bgr_tuple, "RED"
        if 5 <= hue < 10: return bgr_tuple, "CRIMSON"
        if 10 <= hue < 18: return bgr_tuple, "RED-ORANGE"
        if 18 <= hue < 25: return bgr_tuple, "ORANGE"
        if 25 <= hue < 32: return bgr_tuple, "AMBER"
        if 32 <= hue < 42: return bgr_tuple, "YELLOW"
        if 42 <= hue < 48: return bgr_tuple, "GOLD"
        if 48 <= hue < 55: return bgr_tuple, "YELLOW-GREEN"
        if 55 <= hue < 65: return bgr_tuple, "LIME"
        if 65 <= hue < 78: return bgr_tuple, "GREEN"
        if 78 <= hue < 88: return bgr_tuple, "MINT"
        if 88 <= hue < 98: return bgr_tuple, "TEAL"
        if 98 <= hue < 108: return bgr_tuple, "CYAN"
        if 108 <= hue < 118: return bgr_tuple, "BLUE"
        if 118 <= hue < 128: return bgr_tuple, "ROYAL BLUE"
        if 128 <= hue < 138: return bgr_tuple, "INDIGO"
        if 138 <= hue < 148: return bgr_tuple, "PURPLE"
        if 148 <= hue < 158: return bgr_tuple, "VIOLET"
        if 158 <= hue < 168: return bgr_tuple, "MAGENTA"
        if 168 <= hue <= 175: return bgr_tuple, "PINK"
        if 145 <= hue < 168 and sat > 80: return bgr_tuple, "ROSE"
        if 8 <= hue < 22 and sat > 120 and val > 150: return bgr_tuple, "CORAL"
        if 8 <= hue < 22 and sat > 80 and val > 180: return bgr_tuple, "SALMON"
        if 95 <= hue < 115 and val < 140: return bgr_tuple, "NAVY"
        return bgr_tuple, "UNKNOWN"

    def sample_hsv_color(self, frame, x, y, radius=8):
        """Sample color at (x,y) using median over a small disk/box for stability. Returns (BGR, name)."""
        h, w = frame.shape[:2]
        x1 = max(0, x - radius)
        x2 = min(w, x + radius + 1)
        y1 = max(0, y - radius)
        y2 = min(h, y + radius + 1)
        region = frame[y1:y2, x1:x2]
        if region.size == 0: return (0, 255, 0), "UNKNOWN"
        hsv_region = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
        # Median is more robust to shadows and fabric texture than mean
        hue = int(np.median(hsv_region[:, :, 0]))
        sat = int(np.median(hsv_region[:, :, 1]))
        val = int(np.median(hsv_region[:, :, 2]))
        b = int(np.median(region[:, :, 0]))
        g = int(np.median(region[:, :, 1]))
        r = int(np.median(region[:, :, 2]))
        return self._hsv_to_color_name(hue, sat, val, (b, g, r))

    def sample_region_color(self, frame, x1, y1, x2, y2):
        """Sample dominant color over a rectangle (e.g. shirt or pants region). Returns (BGR, name)."""
        h, w = frame.shape[:2]
        x1, x2 = max(0, int(x1)), min(w, int(x2))
        y1, y2 = max(0, int(y1)), min(h, int(y2))
        if x2 <= x1 or y2 <= y1: return (0, 255, 0), "UNKNOWN"
        region = frame[y1:y2, x1:x2]
        if region.size == 0: return (0, 255, 0), "UNKNOWN"
        hsv_region = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
        # Use median over the whole region for stable clothing color
        hue = int(np.median(hsv_region[:, :, 0]))
        sat = int(np.median(hsv_region[:, :, 1]))
        val = int(np.median(hsv_region[:, :, 2]))
        b = int(np.median(region[:, :, 0]))
        g = int(np.median(region[:, :, 1]))
        r = int(np.median(region[:, :, 2]))
        return self._hsv_to_color_name(hue, sat, val, (b, g, r))

    def _person_shirt_pants_rois(self, frame, x1, y1, x2, y2):
        """Get (shirt_rect, pants_rect) as (x1,y1,x2,y2) for a person bbox. Uses pose if available else bbox thirds."""
        h, w = frame.shape[:2]
        height = y2 - y1
        width = x2 - x1
        # Fallback: upper ~40% = shirt, lower ~50% = pants (skip waist band)
        shirt_fallback = (x1, y1, x2, y1 + int(height * 0.42))
        pants_fallback = (x1, y1 + int(height * 0.48), x2, y2)
        if self.cached_pose is None or len(self.cached_pose) < 17:
            return shirt_fallback, pants_fallback
        # COCO pose: 5 left_shoulder, 6 right_shoulder, 11 left_hip, 12 right_hip, 15 left_ankle, 16 right_ankle
        k = self.cached_pose
        def valid(pt): return pt[0] > 0 and pt[1] > 0
        left_sh = k[5]; right_sh = k[6]; left_hip = k[11]; right_hip = k[12]; left_ank = k[15]; right_ank = k[16]
        if not all(valid(p) for p in (left_sh, right_sh, left_hip, right_hip)):
            return shirt_fallback, pants_fallback
        shoulder_y = min(left_sh[1], right_sh[1])
        shoulder_x_min = min(left_sh[0], right_sh[0])
        shoulder_x_max = max(left_sh[0], right_sh[0])
        hip_y = max(left_hip[1], right_hip[1])
        hip_x_min = min(left_hip[0], right_hip[0])
        hip_x_max = max(left_hip[0], right_hip[0])
        # Shirt: shoulders down to hips, with horizontal margin from bbox
        pad_w = max(4, int(width * 0.05))
        shirt_x1 = max(0, int(shoulder_x_min) - pad_w)
        shirt_x2 = min(w, int(shoulder_x_max) + pad_w)
        shirt_y1 = max(0, int(shoulder_y) - 4)
        shirt_y2 = min(h, int(hip_y) + 8)
        if shirt_y2 <= shirt_y1 + 5: shirt_y1, shirt_y2 = shirt_fallback[1], shirt_fallback[3]
        shirt_rect = (shirt_x1, shirt_y1, shirt_x2, shirt_y2)
        # Pants: hips down to ankles (or bbox bottom)
        ankle_y = max(left_ank[1], right_ank[1]) if valid(left_ank) and valid(right_ank) else y2
        pants_x1 = max(0, int(hip_x_min) - pad_w)
        pants_x2 = min(w, int(hip_x_max) + pad_w)
        pants_y1 = max(0, int(hip_y) - 4)
        pants_y2 = min(h, int(ankle_y) + 4) if ankle_y > 0 else y2
        if pants_y2 <= pants_y1 + 5: pants_y1, pants_y2 = pants_fallback[1], pants_fallback[3]
        pants_rect = (pants_x1, pants_y1, pants_x2, pants_y2)
        return shirt_rect, pants_rect

    def _box_iou(self, box_a, box_b):
        """IoU between two boxes (x1,y1,x2,y2)."""
        ax1, ay1, ax2, ay2 = box_a
        bx1, by1, bx2, by2 = box_b
        inter_x1 = max(ax1, bx1)
        inter_y1 = max(ay1, by1)
        inter_x2 = min(ax2, bx2)
        inter_y2 = min(ay2, by2)
        if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
            return 0.0
        inter = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
        area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
        area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
        denom = area_a + area_b - inter
        if denom <= 0:
            return 0.0
        return inter / denom

    def apply_visual_effects(self, frame):
        fx = self.effect_list[self.effect_idx]
        display = frame.copy()
        
        if fx == "PENCIL_SKETCH": display = cv2.pencilSketch(frame, sigma_s=60, sigma_r=0.07, shade_factor=0.05)[1]
        elif fx == "GHOST_TRAILS":
            if self.ghost_acc is None or self.ghost_acc.shape != frame.shape: self.ghost_acc = np.float32(frame)
            cv2.accumulateWeighted(frame, self.ghost_acc, 0.2); display = cv2.convertScaleAbs(self.ghost_acc)
        elif fx == "BLINK_TRACKER":
            if self.face_cascade is None or self.eye_cascade is None: pass
            else:
                gray = cv2.cvtColor(display, cv2.COLOR_BGR2GRAY)
                for (x,y,wf,hf) in self.face_cascade.detectMultiScale(gray, 1.3, 5):
                    eyes = self.eye_cascade.detectMultiScale(gray[y:y+hf, x:x+wf])
                    if len(eyes) == 0: self.eyes_closed_frames += 1
                    else:
                        if self.eyes_closed_frames > 2: self.blinks += 1
                        self.eyes_closed_frames = 0
                cv2.putText(display, f"BLINKS: {self.blinks}", (40, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0,0,255), 3)
        elif fx == "FINGER_DRAW":
            if self.model_pose is None: pass
            else:
                for r in self.model_pose(frame, verbose=False, conf=0.5):
                    if r.keypoints is not None and len(r.keypoints.xy) > 0:
                        wrist = r.keypoints.xy[0][10]
                        if wrist[0] > 0: self.draw_points.append((int(wrist[0]), int(wrist[1])))
                if len(self.draw_points) > 100: self.draw_points.pop(0)
                for i in range(1, len(self.draw_points)): cv2.line(display, self.draw_points[i-1], self.draw_points[i], (0,255,255), 4)
        elif fx == "HAAR_FACES" or fx == "FACE_TEXT":
            if self.face_cascade is not None:
                for (xf,yf,wf,hf) in self.face_cascade.detectMultiScale(cv2.cvtColor(display, cv2.COLOR_BGR2GRAY), 1.3, 5):
                    cv2.putText(display, self.custom_face_text, (xf, yf-10), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,0), 2)
                    cv2.rectangle(display,(xf,yf),(xf+wf,yf+hf),(255,255,0),2)
        elif fx == "THERMAL": display = cv2.applyColorMap(cv2.bitwise_not(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)), cv2.COLORMAP_JET)
        elif fx == "NEON_EDGES":
            neon = np.zeros_like(frame); neon[cv2.dilate(cv2.Canny(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), 50, 150), None) > 0] = [255, 0, 255]
            display = cv2.addWeighted(frame, 0.4, neon, 0.8, 0)
            
        cv2.putText(display, f"ACTIVE FX: {fx}", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,255), 2)
        return display

    def draw_yolo_analytics(self, frame):
        if self.model_obj is None:
            return frame
        self.frame_counter += 1
        h, w = frame.shape[:2]
        ui_col = self.ui_colors[self.ui_color_idx]
        # --- Inference throttle: object every 3 frames, pose every 2 when needed (faster UI) ---
        run_obj = (self.frame_counter % 3 == 0)
        need_pose = (self.toggle_skeleton or self.mode == "SPOOKY_MODE") and self.model_pose is not None
        run_pose = need_pose and (self.frame_counter % 2 == 0)
        if run_obj:
            # Slightly larger inference size to help with small objects
            res = self.model_obj(frame, verbose=False, conf=self.yolo_conf, imgsz=640)
            new_dets = []
            if len(res) > 0:
                for i, box in enumerate(res[0].boxes):
                    coords = tuple(map(int, box.xyxy[0]))
                    conf = float(box.conf[0])
                    cls_id = int(box.cls[0])
                    # Class-wise threshold: be slightly more lenient on persons, stricter on others
                    cls_bias = -0.05 if cls_id == 0 else 0.0
                    eff_thresh = max(0.05, self.yolo_conf + cls_bias)
                    if conf < eff_thresh:
                        continue
                    new_dets.append({"box": coords, "id": i, "conf": conf, "cls": cls_id})
            # Temporal smoothing vs previous frame (simple IoU-based EMA)
            smoothed = []
            for det in new_dets:
                box = det["box"]; cls_id = det["cls"]; conf = det["conf"]
                best_iou, best_prev = 0.0, None
                for prev in self.cached_dets_prev:
                    if prev["cls"] != cls_id:
                        continue
                    iou = self._box_iou(box, prev["box"])
                    if iou > best_iou:
                        best_iou, best_prev = iou, prev
                if best_prev and best_iou > 0.4:
                    px1, py1, px2, py2 = best_prev["box"]
                    x1, y1, x2, y2 = box
                    alpha = 0.6  # weight previous more for stability
                    sx1 = int(alpha * px1 + (1-alpha) * x1)
                    sy1 = int(alpha * py1 + (1-alpha) * y1)
                    sx2 = int(alpha * px2 + (1-alpha) * x2)
                    sy2 = int(alpha * py2 + (1-alpha) * y2)
                    sconf = alpha * best_prev["conf"] + (1-alpha) * conf
                    smoothed.append({"box": (sx1, sy1, sx2, sy2), "id": det["id"], "conf": sconf, "cls": cls_id})
                else:
                    smoothed.append(det)
            self.cached_dets = smoothed
            self.cached_dets_prev = smoothed.copy()
        if run_pose:
            new_pose = None
            try:
                if self.pose_backend == "YOLO" and self.model_pose is not None:
                    pose_res = self.model_pose(frame, verbose=False, conf=self.yolo_conf, imgsz=640)
                    if len(pose_res) > 0 and pose_res[0].keypoints is not None and len(pose_res[0].keypoints.xy) > 0:
                        new_pose = pose_res[0].keypoints.xy[0]
                elif self.pose_backend == "BLAZE" and self._ensure_mediapipe(need_pose=True) and mp_pose_engine is not None:
                    # BlazePose expects RGB input
                    pr = mp_pose_engine.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                    if pr.pose_landmarks and pr.pose_landmarks.landmark:
                        h, w = frame.shape[:2]
                        pts = []
                        for lm in pr.pose_landmarks.landmark:
                            pts.append((lm.x * w, lm.y * h))
                        new_pose = np.array(pts)
            except Exception as e:
                self._log_error("pose", f"{self.pose_backend} error: {e}")
            if new_pose is not None:
                # Smooth pose over time to stabilize skeleton
                if self.pose_prev is not None and len(self.pose_prev) == len(new_pose):
                    smoothed = []
                    for (px, py), (nx, ny) in zip(self.pose_prev, new_pose):
                        if px > 0 and py > 0 and nx > 0 and ny > 0:
                            if abs(nx - px) > 50 or abs(ny - py) > 50:
                                smoothed.append((nx, ny))
                            else:
                                alpha = 0.6
                                smoothed.append((alpha * px + (1-alpha) * nx, alpha * py + (1-alpha) * ny))
                        else:
                            smoothed.append((nx, ny))
                    self.cached_pose = np.array(smoothed)
                else:
                    self.cached_pose = new_pose
                self.pose_prev = self.cached_pose
            else:
                self.cached_pose = None
        if run_obj and self.toggle_emotion and self.mode == "SPOOKY_MODE" and self._ensure_mediapipe(need_face=True) and face_mesh_engine is not None:
                fm_res = face_mesh_engine.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                self.cached_mesh = fm_res.multi_face_landmarks if fm_res and fm_res.multi_face_landmarks else []

        # --- Visual Effects Override Protection ---
        if self.mode == "EFFECTS" and self.app_state == "LIVE":
            return self.apply_visual_effects(frame)

        # --- Face Mesh Render ---
        if self.toggle_emotion and self.mode == "SPOOKY_MODE" and self.cached_mesh and self._ensure_mediapipe(need_face=False) and mp_drawing is not None:
            for face_landmarks in self.cached_mesh:
                mp_drawing.draw_landmarks(
                    image=frame, landmark_list=face_landmarks, connections=mp_face_mesh.FACEMESH_TESSELATION,
                    landmark_drawing_spec=None, connection_drawing_spec=mp_drawing_styles.get_default_face_mesh_tesselation_style()
                )
                # AR visor: simple cyberpunk mask strip across eyes
                try:
                    lm = face_landmarks.landmark
                    h, w = frame.shape[:2]
                    lx, ly = int(lm[33].x * w), int(lm[33].y * h)
                    rx, ry = int(lm[263].x * w), int(lm[263].y * h)
                    cy = int((ly + ry) * 0.5)
                    x1, x2 = min(lx, rx) - 20, max(lx, rx) + 20
                    y1, y2 = cy - 12, cy + 12
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (220, 120, 255), -1)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 220, 80), 1)
                except Exception:
                    pass

        # --- Interactive Crosshair ---
        if self.color_sample_pos is not None:
            cx, cy = self.color_sample_pos
            cv2.circle(frame, (cx, cy), 15, (0, 255, 255), 2)
            cv2.drawMarker(frame, (cx, cy), (0, 0, 255), markerType=cv2.MARKER_CROSS, markerSize=20, thickness=2)
            col_bgr, col_name = self.sample_hsv_color(frame, cx, cy)
            b, g, r = col_bgr
            hex_str = self._bgr_to_hex(b, g, r)
            tx, ty = cx + 20, cy - 10
            line1 = f"SAMPLED: {col_name}"
            line2 = hex_str
            for dx, dy in [(-1,-1),(-1,1),(1,-1),(1,1),(-1,0),(1,0),(0,-1),(0,1)]:
                cv2.putText(frame, line1, (tx + dx, ty + dy), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
                cv2.putText(frame, line2, (tx + dx, ty + 14 + dy), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2)
            cv2.putText(frame, line1, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.6, col_bgr, 2)
            cv2.putText(frame, line2, (tx, ty + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.55, col_bgr, 2)
            rx1, ry1, rx2, ry2 = cx + 20, cy + 20, cx + 150, cy + 40
            cv2.rectangle(frame, (rx1, ry1), (rx2, ry2), col_bgr, -1)
            cv2.rectangle(frame, (rx1, ry1), (rx2, ry2), (0, 0, 0), 1)

        # --- HUD RENDER LOOP ---
        person_detected = False
        main_person_box = None
        for det in self.cached_dets:
            x1, y1, x2, y2 = det["box"]
            box_id, conf, cls_id = det["id"], det["conf"], det["cls"]
            
            if cls_id == 0:
                person_detected = True
                if main_person_box is None:
                    main_person_box = (x1, y1, x2, y2)

            # Smarter label: person -> SUBJECT + confidence tier; others -> class + tier
            raw_name = self.model_obj.names[cls_id].upper()
            if cls_id == 0: display_name = "SUBJECT"
            else: display_name = raw_name
            conf_tier = "HIGH" if conf >= 0.7 else ("CONFIDENT" if conf >= 0.45 else "LOW")
            label_text = f"{display_name} {conf:.0%} [{conf_tier}]"

            if self.mode == "SPOOKY_MODE":
                y_off = y1 + 20
                
                # Full Biometrics only run on People (cls == 0)
                if cls_id == 0:
                    if self.cached_pose is not None and len(self.cached_pose) > 14:
                        hips_y = (self.cached_pose[11][1] + self.cached_pose[12][1]) / 2
                        knees_y = (self.cached_pose[13][1] + self.cached_pose[14][1]) / 2
                        stance = "SITTING" if abs(hips_y - knees_y) < ((y2-y1)*0.15) else "STANDING"
                        cv2.putText(frame, f"STANCE: {stance}", (x2+10, y_off), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,255), 1)
                        y_off += 20
                    
                    if self.toggle_color:
                        shirt_rect, pants_rect = self._person_shirt_pants_rois(frame, x1, y1, x2, y2)
                        shirt_bgr, shirt_name = self.sample_region_color(frame, *shirt_rect)
                        pants_bgr, pants_name = self.sample_region_color(frame, *pants_rect)
                        cv2.rectangle(frame, (shirt_rect[0], shirt_rect[1]), (shirt_rect[2], shirt_rect[3]), shirt_bgr, 1)
                        cv2.rectangle(frame, (pants_rect[0], pants_rect[1]), (pants_rect[2], pants_rect[3]), pants_bgr, 1)
                        sb, sg, sr = shirt_bgr
                        pb, pg, pr = pants_bgr
                        cv2.putText(frame, f"SHIRT: {shirt_name}  {self._bgr_to_hex(sb, sg, sr)}", (x2+10, y_off), cv2.FONT_HERSHEY_SIMPLEX, 0.5, shirt_bgr, 1)
                        y_off += 20
                        cv2.putText(frame, f"PANTS: {pants_name}  {self._bgr_to_hex(pb, pg, pr)}", (x2+10, y_off), cv2.FONT_HERSHEY_SIMPLEX, 0.5, pants_bgr, 1)
                        y_off += 20

                    if HAS_MP and self.toggle_emotion and self.cached_mesh:
                        raw_emo = self.analyze_emotion(self.cached_mesh[0].landmark)
                        aux_tag = None
                        base_emo = raw_emo
                        # Treat BLINKING / TALKING as auxiliary states layered on top of a slower emotion
                        if raw_emo in ("BLINKING", "TALKING"):
                            aux_tag = raw_emo
                            base_emo = "NEUTRAL"
                        now = time.time()
                        # Update history for temporal consensus (keep last ~30 raw labels)
                        self.emotion_history.append(base_emo)
                        if len(self.emotion_history) > 30:
                            self.emotion_history.pop(0)
                        if self.emotion_history:
                            cand = Counter(self.emotion_history).most_common(1)[0][0]
                            if cand != self.emotion_label and (now - self.emotion_last_change_ts) > 0.6:
                                self.emotion_label = cand
                                self.emotion_last_change_ts = now
                        # Draw aux state (e.g. BLINKING/TALKING) if present
                        if aux_tag:
                            cv2.putText(frame, aux_tag, (x2+10, y_off), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,255), 2)
                            y_off += 18
                        cv2.putText(frame, f"EMOTION: {self.emotion_label}", (x2+10, y_off), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 2)
                        y_off += 20

                # Universal Spooky Tracking for ALL Objects
                cv2.rectangle(frame, (x1, y1), (x2, y2), ui_col, 1)
                cv2.putText(frame, label_text, (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, ui_col, 2)
                cv2.line(frame, ((x1+x2)//2, (y1+y2)//2), (x2+5, y1+20), ui_col, 1)

            else:
                # Basic Vision Mode
                cv2.rectangle(frame, (x1, y1), (x2, y2), ui_col, 2)
                cv2.putText(frame, label_text, (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, ui_col, 2)

        # Draw Skeletons (Live HUD + Spooky share this; FX mode never draws skeleton)
        if person_detected and self.toggle_skeleton and self.cached_pose is not None and self.mode != "EFFECTS":
            for e in self.skeleton_edges:
                p1, p2 = (int(self.cached_pose[e[0]][0]), int(self.cached_pose[e[0]][1])), (int(self.cached_pose[e[1]][0]), int(self.cached_pose[e[1]][1]))
                if p1[0] > 0 and p2[0] > 0: cv2.line(frame, p1, p2, (0, 255, 255), 2)

        # Action/posture + metrics + pseudo-3D annotations
        if person_detected and self.cached_pose is not None and self.mode != "EFFECTS":
            self._analyze_pose_intel(frame, main_person_box)
            # Pose text overlays near person
            if main_person_box is not None:
                x1, y1, x2, y2 = main_person_box
                cv2.putText(frame, f"POSTURE: {self.current_posture}", (x2 + 10, y2 - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 255, 150), 1)
                cv2.putText(frame, f"ACTION: {self.current_action}", (x2 + 10, y2 - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 220, 255), 1)
                m = self.current_person_metrics
                if m:
                    back = m.get("back_angle", 0.0)
                    knee = m.get("knee", 0.0)
                    step = m.get("step_m", 0.0)
                    sh = m.get("shoulder_sym_px", 0.0)
                    back_col = (100, 220, 100) if back < 10 else ((0, 220, 255) if back < 20 else (0, 80, 255))
                    knee_col = (100, 220, 100) if 80 <= knee <= 120 else (0, 180, 255)
                    cv2.putText(frame, f"BACK: {back:.1f} deg", (x1, max(22, y1 - 56)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, back_col, 1)
                    cv2.putText(frame, f"KNEE: {knee:.1f} deg", (x1, max(22, y1 - 40)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, knee_col, 1)
                    cv2.putText(frame, f"STEP: {step:.2f} m", (x1, max(22, y1 - 24)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 220, 220), 1)
                    cv2.putText(frame, f"SHOULDERS: {sh:+.1f}px", (x1, max(22, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 220, 220), 1)
                    # Pseudo-3D depth estimate + ground grid
                    ph = max(1.0, float(y2 - y1))
                    est_dist_m = (1.75 * frame.shape[1]) / max(1.0, ph)  # rough
                    foot_y = int((self.cached_pose[15][1] + self.cached_pose[16][1]) * 0.5) if len(self.cached_pose) > 16 else y2
                    center_x = int((x1 + x2) * 0.5)
                    for gx in range(-3, 4):
                        x_base = center_x + gx * 26
                        cv2.line(frame, (x_base, foot_y), (int(center_x + gx * 12), min(frame.shape[0]-1, foot_y + 80)), (70, 90, 120), 1)
                    for gy in range(1, 5):
                        yy = min(frame.shape[0]-1, foot_y + gy * 20)
                        cv2.line(frame, (center_x - 90 + gy*5, yy), (center_x + 90 - gy*5, yy), (60, 80, 110), 1)
                    cv2.putText(frame, f"~1.8m, ~{est_dist_m:.1f}m away", (x1, y2 + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (140, 180, 220), 1)
            # AR wrist trail
            for i in range(1, len(self.wrist_trails)):
                p1 = self.wrist_trails[i-1]; p2 = self.wrist_trails[i]
                if p1 and p2:
                    cv2.line(frame, p1, p2, (255, 180, 40), 2)

        # Session analytics
        self._update_session(person_detected)

        # Optional focus saliency overlay
        if self.toggle_focus and self.mode != "EFFECTS":
            sal = self._compute_focus_saliency(frame)
            if sal is not None:
                heat = cv2.applyColorMap(sal, cv2.COLORMAP_HOT)
                frame = cv2.addWeighted(frame, 0.65, heat, 0.35, 0)

        # Emotion-reactive visuals (subtle)
        if self.mode in ("SPOOKY_MODE", "EFFECTS"):
            if self.emotion_label == "HAPPY":
                warm = np.full_like(frame, (10, 35, 55))
                frame = cv2.addWeighted(frame, 0.9, warm, 0.1, 0)
                # subtle vignette
                h, w = frame.shape[:2]
                yy, xx = np.ogrid[:h, :w]
                cx, cy = w / 2.0, h / 2.0
                dist = np.sqrt((xx-cx)**2 + (yy-cy)**2)
                vign = np.clip(1.0 - (dist / max(cx, cy)) * 0.25, 0.75, 1.0)
                frame = np.clip(frame.astype(np.float32) * vign[..., None], 0, 255).astype(np.uint8)
            elif self.emotion_label == "ANGRY":
                red = np.full_like(frame, (0, 0, 70))
                frame = cv2.addWeighted(frame, 0.88, red, 0.12, 0)
                if (self.frame_counter % 6) == 0:
                    y = int((self.frame_counter * 13) % max(1, frame.shape[0]-1))
                    cv2.line(frame, (0, y), (frame.shape[1]-1, y), (20, 20, 220), 1)
            elif self.emotion_label == "CONCENTRATING":
                edges = cv2.Canny(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), 70, 140)
                edge_rgb = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)
                frame = cv2.addWeighted(frame, 0.9, edge_rgb, 0.2, 0)

        # Lightweight diagnostics strip (bottom-left)
        status_yolo = "OK" if self.model_obj is not None else "OFF"
        status_pose = "OK" if self.model_pose is not None else "OFF"
        status_mp = "ON" if (face_mesh_engine is not None or mp_pose_engine is not None) else ("READY" if HAS_MP else "OFF")
        mode_tag = self.mode
        diag = f"YOLO:{status_yolo}  POSE:{status_pose}  MP:{status_mp}  OCR:{self.ocr_profile}/{self.ocr_last_engine}  MODE:{mode_tag}"
        cv2.putText(frame, diag, (16, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1)

        return frame

    # ---------------------------------------------------------
    # INPUT ROUTING & UI
    # ---------------------------------------------------------
    def mouse_event(self, event, x, y, flags, param):
        win_w, win_h = WIN_W, WIN_H
        rx, ry = x / win_w, y / win_h
        self.last_mouse_pos = (x, y)
        tr = LAYOUT["transport"]
        is_timeline_area = (tr["track_x1"] <= rx <= tr["track_x2"] and tr["track_ry"][0] <= ry <= tr["track_ry"][1])

        if event == cv2.EVENT_MOUSEMOVE:
            self.hover_active = True
            if self.dragging_slider == "ZOOM" and self.app_state == "LIVE":
                self.zoom = 1.0 + (np.clip((rx - 0.52) / 0.16, 0, 1) * 3.0)
            elif self.dragging_slider == "EXPOSURE" and self.app_state == "LIVE":
                self.exposure = 0.2 + (np.clip((rx - 0.70) / 0.16, 0, 1) * 2.8)
            elif self.dragging_slider == "CONF":
                s = LAYOUT["settings"]; sx, sw = s["slider_box"][0], s["slider_box"][2]
                self.yolo_conf = 0.1 + (np.clip((rx - sx) / sw, 0, 1) * 0.8)
            elif isinstance(self.dragging_slider, str) and self.dragging_slider.startswith("IMG_"):
                self._set_img_ctrl_from_rx(self.dragging_slider[4:], rx)
            elif self.dragging_slider == "F_OPACITY":
                self.forensics_opacity = float(np.clip((rx - 0.10) / 0.24, 0, 1))
            elif self.dragging_slider == "F_P1":
                tool = self.forensics_tools[self.forensics_tool_idx]
                t = float(np.clip((rx - 0.38) / 0.24, 0, 1))
                if tool == "ELA":
                    self.forensics_ela_quality = int(65 + t * 34)
                elif tool == "NOISE":
                    self.forensics_noise_amp = 0.6 + t * 4.4
                elif tool == "SWEEP":
                    self.forensics_sweep = t
                elif tool == "PCA":
                    self.forensics_pca_component = int(1 + t * 2.99)
                elif tool == "CLONE":
                    self.forensics_clone_sim = 0.75 + t * 0.24
                elif tool == "MAGNIFIER":
                    self.forensics_mag_zoom = int(2 + t * 10)
            elif self.dragging_slider == "F_P2":
                tool = self.forensics_tools[self.forensics_tool_idx]
                t = float(np.clip((rx - 0.66) / 0.24, 0, 1))
                if tool == "ELA":
                    self.forensics_ela_scale = 4.0 + t * 36.0
                elif tool == "SWEEP":
                    self.forensics_sweep_width = 8.0 + t * 92.0
                elif tool == "CLONE":
                    self.forensics_clone_detail = 2.0 + t * 28.0
            elif self.dragging_timeline and self.app_state in ["ANALYZE_VIDEO", "ANALYZE_AUDIO"]:
                self.vid_current = int(np.clip((rx - 0.1) / 0.8, 0, 1) * self.vid_total)
                self.sync_media()
            elif self.forensics_jpeg_panel_drag and self.forensics_jpeg_panel_rect:
                # Drag JPEG forensics panel with the mouse.
                x1, y1, x2, y2 = self.forensics_jpeg_panel_rect
                w = x2 - x1
                h = y2 - y1
                cx = int(rx * WIN_W)
                cy = int(ry * WIN_H)
                nx1 = int(np.clip(cx - w // 2, 0, WIN_W - w))
                ny1 = int(np.clip(cy - 12, 0, WIN_H - h))
                self.forensics_jpeg_panel_rect = (nx1, ny1, nx1 + w, ny1 + h)

        elif event == cv2.EVENT_LBUTTONDOWN:
            if is_timeline_area and self.app_state in ["ANALYZE_VIDEO", "ANALYZE_AUDIO"]:
                self.dragging_timeline = True
                self.vid_current = int(np.clip((rx - 0.1) / 0.8, 0, 1) * self.vid_total)
                self.sync_media()
            elif self.app_state in ["LIVE", "ANALYZE_PHOTO", "ANALYZE_VIDEO"] and ry < 0.8 and not self._is_over_img_controls(rx, ry):
                self.color_sample_pos = (x, y)
            self.handle_clicks(rx, ry)
            
        elif event == cv2.EVENT_RBUTTONDOWN:
            self.color_sample_pos = None
        elif event == cv2.EVENT_LBUTTONUP:
            self.dragging_slider = None
            self.dragging_timeline = False
            self.forensics_jpeg_panel_drag = False

    def handle_clicks(self, rx, ry):
        bar = LAYOUT["top_bar"]
        if self.app_state != "MENU":
            if self._in_button(bar["back"]):
                if self.app_state == "LIVE":
                    self._persist_session_summary()
                    self.session_active = False
                self.close_all_media(); self.app_state = "MENU"; self.ocr_cache = None; self.ocr_boxes = []; self.video_run_ocr = False; self.error_message = None
            if self._in_button(bar["help"]): self.show_help = not self.show_help

        # Floating image controls panel (LIVE/PHOTO/VIDEO)
        if self.app_state in ("LIVE", "ANALYZE_PHOTO", "ANALYZE_VIDEO"):
            panel, collapse_btn, reset_btn, rows = self._img_ctrl_panel_boxes()
            if self._in_button(collapse_btn):
                self.img_ctrl_collapsed = not self.img_ctrl_collapsed
            elif (not self.img_ctrl_collapsed) and self._in_button(reset_btn):
                self._reset_img_controls()
            elif not self.img_ctrl_collapsed:
                for row in rows:
                    if self._in_button(row["row_box"]) or self._in_button(row["bar"]):
                        self.dragging_slider = f"IMG_{row['key']}"
                        self._set_img_ctrl_from_rx(row["key"], rx)
                        break

        if self.app_state == "MENU":
            for i, box in enumerate(LAYOUT["menu_buttons"]):
                if self._in_button(box):
                    # Do NOT auto-open any camera here; user must press Lens/FX to start a camera.
                    if i in (0, 1, 2):
                        self.app_state = "LIVE"
                        self.mode = "CLOUTVISION" if i == 0 else ("SPOOKY_MODE" if i == 1 else "EFFECTS")
                        self.session_stats = {
                            "live_seconds": 0.0,
                            "in_frame_seconds": 0.0,
                            "posture_seconds": {"STANDING": 0.0, "SITTING": 0.0, "PACED": 0.0, "SLOUCHING": 0.0, "UNKNOWN": 0.0},
                            "emotion_counts": {},
                            "action_counts": {},
                            "blinks": int(self.blinks),
                        }
                        self.session_active = False
                        self.session_last_ts = 0.0
                        self.hip_x_hist = []
                        self.wrist_x_hist = []
                        self.wrist_trails = []
                    elif i == 3: self.app_state = "MEDIA_MENU"
                    elif i == 4: self.app_state = "SETTINGS"
                    break
            if self._in_button(LAYOUT["menu"]["shutdown"]): exit()

        elif self.app_state == "SETTINGS":
            s = LAYOUT["settings"]
            for i, box in enumerate(s["col1"]):
                if self._in_button(box):
                    if i == 0: self.cycle_camera(allow_phone=True)
                    elif i == 1: p = self.select_file_mac("PHOTO"); self.face_mask = cv2.imread(p, cv2.IMREAD_UNCHANGED) if p else None
                    elif i == 2:
                        try: self.custom_face_text = subprocess.check_output(['osascript', '-e', 'set T to text returned of (display dialog "Enter text to stick to Face:" default answer "SUBJECT")\nreturn T']).decode('utf-8').strip()
                        except (subprocess.CalledProcessError, FileNotFoundError, OSError): pass
                    elif i == 3:
                        modes = ["AUTO", "FAST", "ACCURATE"]
                        self.ocr_profile = modes[(modes.index(self.ocr_profile) + 1) % len(modes)]
                        self.ocr_cache = None
                        self.ocr_boxes = []
                        self.video_ocr_frame_index = -1
                    break
            for i, box in enumerate(s["col2"]):
                if self._in_button(box):
                    if i == 0: self.export_target = "FINDER" if self.export_target == "PHOTOS" else "PHOTOS"
                    elif i == 1: self.show_clock = not self.show_clock
                    elif i == 2: self.ui_color_idx = (self.ui_color_idx + 1) % len(self.ui_colors)
                    elif i == 3: self.zoom = 1.0; self.exposure = 1.0; self.yolo_conf = 0.4
                    elif i == 4: self.toggle_skeleton = not self.toggle_skeleton
                    elif i == 5: self.toggle_emotion = not self.toggle_emotion
                    elif i == 6: self.toggle_color = not self.toggle_color
                    elif i == 7: self.pose_backend = "BLAZE" if self.pose_backend == "YOLO" else "YOLO"
                    break
            # Error log toggle / copy area
            if self._in_button((0.50, 0.84, 0.34, 0.056)):
                self.show_error_log = not self.show_error_log
            if self.show_error_log and self._in_button((0.72, 0.745, 0.16, 0.045)):
                self._copy_to_clipboard("\n".join(self.error_log))
            if self._in_button(s["slider_box"]): self.dragging_slider = "CONF"

        elif self.app_state == "MEDIA_MENU":
            for i, box in enumerate(LAYOUT["media_menu"]["buttons"]):
                if not self._in_button(box): continue
                if i == 0:
                    f = self.select_file_mac("PHOTO")
                    if f: self.analysis_file = f; self.load_metadata_mac(f); self.app_state = "ANALYZE_PHOTO"; self.ocr_cache = None
                elif i == 1:
                    f = self.select_file_mac("VIDEO")
                    if f: self.analysis_file = f; self.vid_cap = cv2.VideoCapture(f); self.load_metadata_mac(f); self.vid_total = max(1, int(self.vid_cap.get(cv2.CAP_PROP_FRAME_COUNT))); self.vid_current = 0; self.is_playing = True; self.app_state = "ANALYZE_VIDEO"
                elif i == 2:
                    f = self.select_file_mac("AUDIO")
                    if f: self.analysis_file = f; self.generate_audio_visuals(f)
                elif i == 3:
                    f = self.select_file_mac("TEXT")
                    if f: self.clipboard_cache = None; self.analysis_file = f; self.extract_and_summarize_text()
                elif i == 4:
                    self.app_state = "ANALYZE_TEXT"
                    # Render in-memory session summary as text_data blocks
                    live_s = self.session_stats.get("live_seconds", 0.0)
                    in_frame = self.session_stats.get("in_frame_seconds", 0.0)
                    post = self.session_stats.get("posture_seconds", {})
                    emo = self.session_stats.get("emotion_counts", {})
                    act = self.session_stats.get("action_counts", {})
                    dom_emo = max(emo.items(), key=lambda kv: kv[1])[0] if emo else "N/A"
                    top_actions = ", ".join([f"{k} x{v}" for k, v in sorted(act.items(), key=lambda kv: kv[1], reverse=True)[:3]]) or "N/A"
                    ptotal = max(1e-6, sum(post.values()))
                    block = (
                        f"Session Summary\n"
                        f"Time in LIVE: {live_s:.1f}s\n"
                        f"Time in frame: {in_frame:.1f}s\n"
                        f"Standing: {100.0*post.get('STANDING',0.0)/ptotal:.1f}%  "
                        f"Sitting: {100.0*post.get('SITTING',0.0)/ptotal:.1f}%  "
                        f"Paced: {100.0*post.get('PACED',0.0)/ptotal:.1f}%  "
                        f"Slouching: {100.0*post.get('SLOUCHING',0.0)/ptotal:.1f}%\n"
                        f"Blinks: {self.blinks}\n"
                        f"Dominant emotion: {dom_emo}\n"
                        f"Top actions: {top_actions}"
                    )
                    self.text_data = {"date": datetime.now().strftime('%Y-%m-%d %H:%M:%S'), "words": len(block.split()), "chars": len(block), "summary": block, "raw": block, "blocks": [block]}
                elif i == 5:
                    f = self.select_file_mac("PHOTO")
                    if f:
                        self.analysis_file = f
                        self.load_metadata_mac(f)
                        self.app_state = "FORENSICS"
                        self.forensics_cache = {}
                        self._analyze_jpeg_file(f)
                break

        if self.app_state == "LIVE":
            lt, lh = LAYOUT["live_toolbar"]["y"], LAYOUT["live_toolbar"]["h"]
            if self._in_button((0.28, lt, 0.072, lh)): self.toggle_skeleton = not self.toggle_skeleton
            if self._in_button((0.36, lt, 0.072, lh)): self.toggle_emotion = not self.toggle_emotion
            if self._in_button((0.44, lt, 0.072, lh)): self.toggle_color = not self.toggle_color
            if self._in_button((0.86, lt, 0.085, lh)): self.cycle_camera(allow_phone=False)
            if self._in_button((0.18, lt, 0.082, lh)):
                # FX button: if not already in FX mode, switch; otherwise cycle effect
                if self.mode != "EFFECTS":
                    self.mode = "EFFECTS"
                else:
                    self.effect_idx = (self.effect_idx + 1) % len(self.effect_list)
            if LAYOUT["live_toolbar"]["slider_bar_y"] - 0.02 <= ry <= LAYOUT["live_toolbar"]["slider_bar_y"] + 0.05:
                if 0.52 <= rx <= 0.68: self.dragging_slider = "ZOOM"
                elif 0.70 <= rx <= 0.86: self.dragging_slider = "EXPOSURE"

        elif self.app_state == "ANALYZE_PHOTO":
            tb = LAYOUT["analysis_toolbar"]["photo"]
            if self._in_button(tb["mdls"]): self.show_exif_hud = not self.show_exif_hud
            if self.show_exif_hud and self.copy_coords_rel and self._in_button(self.copy_coords_rel) and self.photo_gps and all(v is not None for v in self.photo_gps):
                self._copy_to_clipboard(f"{self.photo_gps[0]:.6f},{self.photo_gps[1]:.6f}")
            if self.show_exif_hud and self.nearby_rects:
                mx, my = self.last_mouse_pos
                for (x, y, w, h, pth) in self.nearby_rects:
                    if x <= mx <= x + w and y <= my <= y + h and os.path.isfile(pth):
                        self.analysis_file = pth
                        self.load_metadata_mac(pth)
                        self.ocr_cache = None
                        break
            if self._ocr_available() and self._in_button(tb["ocr"]): self.run_ocr = not self.run_ocr; self.ocr_cache = None; self.ocr_boxes = []
            # Focus toggle button
            if self._in_button((0.50, 0.90, 0.10, 0.048)): self.toggle_focus = not self.toggle_focus
            if self._in_button((0.62, 0.90, 0.08, 0.048)): self.toggle_doc_mode = not self.toggle_doc_mode
            if self._in_button((0.84, 0.90, 0.12, 0.048)): self.doc_translate_on = not self.doc_translate_on
            if self._in_button((0.71, 0.90, 0.12, 0.048)) and self.analysis_file and os.path.isfile(self.analysis_file):
                img = self._imread_any(self.analysis_file)
                if img is not None:
                    out_pdf = self._export_clean_scan_pdf(img)
                    if out_pdf:
                        self.error_message = f"Exported {out_pdf}"
            if self.run_ocr and self._ocr_available() and self.ocr_boxes and self._in_button(tb["copy_all"]):
                self._copy_to_clipboard(" ".join(b["text"] for b in self.ocr_boxes))
            elif self.run_ocr and self.ocr_boxes:
                mx_d, my_d = self.last_mouse_pos[0], self.last_mouse_pos[1]
                scale = self.ocr_letterbox_scale
                x_off, y_off = self.ocr_letterbox_xoff, self.ocr_letterbox_yoff
                mx_orig = (mx_d - x_off) / scale if scale > 0 else mx_d
                my_orig = (my_d - y_off) / scale if scale > 0 else my_d
                for box in self.ocr_boxes:
                    x, y, w, h = box["x"], box["y"], box["w"], box["h"]
                    if x <= mx_orig <= x + w and y <= my_orig <= y + h:
                        self._copy_to_clipboard(box["text"])
                        break
                # Side-panel selection
                if not self.ocr_text_rects:
                    return
                mx, my = self.last_mouse_pos
                for (rx, ry, rw, rh, txt) in self.ocr_text_rects:
                    if rx <= mx <= rx + rw and ry <= my <= ry + rh:
                        self._copy_to_clipboard(txt)
                        break

        elif self.app_state == "ANALYZE_TEXT":
            if self._in_button((0.02, 0.12, 0.10, 0.05)): self.summary_length = "LONG" if self.summary_length == "SHORT" else "SHORT"
            if self.text_data and self._in_button((0.14, 0.12, 0.10, 0.05)):
                raw = self.text_data.get("raw") or " ".join(self.text_data.get("blocks", []))
                self._copy_to_clipboard(raw)
            elif self.text_block_rects:
                mx, my = self.last_mouse_pos[0], self.last_mouse_pos[1]
                for (x, y, w, h, txt) in self.text_block_rects:
                    if x <= mx <= x + w and y <= my <= y + h:
                        self._copy_to_clipboard(txt)
                        break

        elif self.app_state == "FORENSICS":
            # Toolbox controls
            if self._in_button((0.02, 0.90, 0.16, 0.048)):
                # Toggle slide-up tool menu
                self.forensics_tool_menu_open = not self.forensics_tool_menu_open
            if self._in_button((0.19, 0.90, 0.16, 0.048)):
                self.forensics_enhance_idx = (self.forensics_enhance_idx + 1) % len(self.forensics_enhance_opts)
            if self._in_button((0.36, 0.90, 0.10, 0.048)):
                self.forensics_invert = not self.forensics_invert
            if self._in_button((0.47, 0.90, 0.14, 0.048)):
                f = self.select_file_mac("PHOTO")
                if f:
                    self.analysis_file = f
                    self.load_metadata_mac(f)
                    self.forensics_cache = {}
                    self._analyze_jpeg_file(f)

            # Slide-up tool picker hit-test (simple vertical list above Tool button)
            if self.forensics_tool_menu_open:
                # Anchor menu ABOVE sliders so it never overlaps slider UI (sliders start at y=0.84).
                base_x, base_y, bw, bh = 0.02, 0.84, 0.16, 0.048
                item_h = 0.045
                for i, name in enumerate(self.forensics_tools):
                    iy1 = base_y - (i + 1) * item_h
                    iy2 = iy1 + item_h
                    if base_x <= rx <= base_x + bw and iy1 <= ry <= iy2:
                        self.forensics_tool_idx = i
                        self.forensics_tool_menu_open = False
                        break

            # JPEG panel header: minimize + drag area
            if self.forensics_jpeg_panel_rect:
                x1, y1, x2, y2 = self.forensics_jpeg_panel_rect
                header_y2 = y1 + 32
                if x1 <= self.last_mouse_pos[0] <= x2 and y1 <= self.last_mouse_pos[1] <= header_y2:
                    # Tiny minimize button at top-right of panel header
                    btn_w = 24
                    if x2 - btn_w <= self.last_mouse_pos[0] <= x2 and y1 <= self.last_mouse_pos[1] <= header_y2:
                        self.forensics_jpeg_panel_minimized = not self.forensics_jpeg_panel_minimized
                        # Actually collapse/restore the panel height.
                        if self.forensics_jpeg_panel_rect:
                            px1, py1, px2, py2 = self.forensics_jpeg_panel_rect
                            if self.forensics_jpeg_panel_minimized:
                                self.forensics_jpeg_panel_full_h = max(40, py2 - py1)
                                self.forensics_jpeg_panel_rect = (px1, py1, px2, py1 + 36)
                            else:
                                full_h = self.forensics_jpeg_panel_full_h or max(40, int(0.70 * WIN_H))
                                self.forensics_jpeg_panel_rect = (px1, py1, px2, min(WIN_H, py1 + full_h))
                    else:
                        self.forensics_jpeg_panel_drag = True

            # Slider +/- buttons (nudge by tool-specific step sizes)
            btn_y = 0.838
            btn_w = 0.028
            btn_h = 0.034
            gap = 0.006
            # Opacity bar: x=[0.10,0.34]
            if self._in_button((0.10 - btn_w - gap, btn_y, btn_w, btn_h)):
                self._forensics_nudge("OPACITY", -1)
            elif self._in_button((0.34 + gap, btn_y, btn_w, btn_h)):
                self._forensics_nudge("OPACITY", +1)
            # Param1 bar: x=[0.38,0.62]
            elif self._in_button((0.38 - btn_w - gap, btn_y, btn_w, btn_h)):
                self._forensics_nudge("P1", -1)
            elif self._in_button((0.62 + gap, btn_y, btn_w, btn_h)):
                self._forensics_nudge("P1", +1)
            # Param2 bar: x=[0.66,0.90]
            elif self._in_button((0.66 - btn_w - gap, btn_y, btn_w, btn_h)):
                self._forensics_nudge("P2", -1)
            elif self._in_button((0.90 + gap, btn_y, btn_w, btn_h)):
                self._forensics_nudge("P2", +1)

            # Sliders – click anywhere on bar to jump value and start dragging
            if 0.10 <= rx <= 0.34 and 0.84 <= ry <= 0.87:
                self.dragging_slider = "F_OPACITY"
                self.forensics_opacity = float(np.clip((rx - 0.10) / 0.24, 0, 1))
            if 0.38 <= rx <= 0.62 and 0.84 <= ry <= 0.87:
                self.dragging_slider = "F_P1"
                tool = self.forensics_tools[self.forensics_tool_idx]
                t = float(np.clip((rx - 0.38) / 0.24, 0, 1))
                if tool == "ELA":
                    self.forensics_ela_quality = int(65 + t * 34)
                elif tool == "NOISE":
                    self.forensics_noise_amp = 0.6 + t * 4.4
                elif tool == "SWEEP":
                    self.forensics_sweep = t
                elif tool == "PCA":
                    self.forensics_pca_component = int(1 + t * 2.99)
                elif tool == "CLONE":
                    self.forensics_clone_sim = 0.75 + t * 0.24
                elif tool == "MAGNIFIER":
                    self.forensics_mag_zoom = int(2 + t * 10)
            if 0.66 <= rx <= 0.90 and 0.84 <= ry <= 0.87:
                self.dragging_slider = "F_P2"
                tool = self.forensics_tools[self.forensics_tool_idx]
                t = float(np.clip((rx - 0.66) / 0.24, 0, 1))
                if tool == "ELA":
                    self.forensics_ela_scale = 4.0 + t * 36.0
                elif tool == "SWEEP":
                    self.forensics_sweep_width = 8.0 + t * 92.0
                elif tool == "CLONE":
                    self.forensics_clone_detail = 2.0 + t * 28.0

        if self.app_state in ["ANALYZE_VIDEO", "ANALYZE_AUDIO"]:
            if self.app_state == "ANALYZE_VIDEO":
                tb = LAYOUT["analysis_toolbar"]["video"]
                if self._in_button(tb["mdls"]): self.show_exif_hud = not self.show_exif_hud
                if self.show_exif_hud and self.copy_coords_rel and self._in_button(self.copy_coords_rel) and self.photo_gps and all(v is not None for v in self.photo_gps):
                    self._copy_to_clipboard(f"{self.photo_gps[0]:.6f},{self.photo_gps[1]:.6f}")
                if self.show_exif_hud and self.nearby_rects:
                    mx, my = self.last_mouse_pos
                    for (x, y, w, h, pth) in self.nearby_rects:
                        if x <= mx <= x + w and y <= my <= y + h and os.path.isfile(pth):
                            self.analysis_file = pth
                            self.load_metadata_mac(pth)
                            break
                if self._ocr_available() and self._in_button(tb["ocr"]):
                    self.video_run_ocr = not self.video_run_ocr
                    self.ocr_boxes = []
                    self.video_ocr_frame_index = -1
                # Focus toggle button
                if self._in_button((0.37, 0.90, 0.10, 0.048)):
                    self.toggle_focus = not self.toggle_focus
                if self.video_run_ocr and self.ocr_boxes and self._in_button(tb["copy_frame"]):
                    self._copy_to_clipboard(" ".join(b["text"] for b in self.ocr_boxes))
                elif self.video_run_ocr and self.ocr_boxes:
                    mx, my = self.last_mouse_pos[0], self.last_mouse_pos[1]
                    for box in self.ocr_boxes:
                        x, y, w, h = box["x"], box["y"], box["w"], box["h"]
                        if x <= mx <= x + w and y <= my <= y + h:
                            self._copy_to_clipboard(box["text"])
                            break
                    # Side-panel selection
                    if self.ocr_text_rects:
                        for (rx, ry, rw, rh, txt) in self.ocr_text_rects:
                            if rx <= mx <= rx + rw and ry <= my <= ry + rh:
                                self._copy_to_clipboard(txt)
                                break
            else:
                if self._in_button((0.02, 0.072, 0.08, 0.048)):
                    self.show_exif_hud = not self.show_exif_hud
            tr = LAYOUT["transport"]
            if self._in_button(tr["play"]): self.is_playing = not self.is_playing
            elif self._in_button(tr["ff"]): self.vid_current = min(self.vid_total, self.vid_current + 100); self.sync_media()
            elif self._in_button(tr["rw"]): self.vid_current = max(0, self.vid_current - 100); self.sync_media()
            elif self._in_button(tr["stop"]): self.is_playing = False; self.vid_current = 0; self.sync_media()

    # ---------------------------------------------------------
    # UI RENDERERS
    # ---------------------------------------------------------
    def _in_button(self, rel_box):
        """True if last mouse pos is inside rel_box (x,y,w,h)."""
        win_w, win_h = WIN_W, WIN_H
        rx, ry, rw, rh = rel_box
        x, y = int(rx*win_w), int(ry*win_h)
        bw, bh = int(rw*win_w), int(rh*win_h)
        return x <= self.last_mouse_pos[0] <= x+bw and y <= self.last_mouse_pos[1] <= y+bh

    def _draw_animus_corner(self, img, cx, cy, w, h, accent_col, is_tl=True, is_br=True):
        """Draw L-shaped Animus-style corners at (cx,cy) with size w,h. is_tl=top-left L, is_br=bottom-right L."""
        if is_tl:
            cv2.line(img, (cx, cy), (cx + w, cy), accent_col, 2)
            cv2.line(img, (cx, cy), (cx, cy + h), accent_col, 2)
        if is_br:
            cv2.line(img, (cx + w, cy + h), (cx, cy + h), accent_col, 2)
            cv2.line(img, (cx + w, cy + h), (cx + w, cy), accent_col, 2)

    def draw_card(self, img, rel_rect, fill=True):
        """Animus-style card: dark fill, accent top edge, corner brackets."""
        win_w, win_h = WIN_W, WIN_H
        x = int(rel_rect[0]*win_w); y = int(rel_rect[1]*win_h)
        w = int(rel_rect[2]*win_w); h = int(rel_rect[3]*win_h)
        acc = THEME["accent"]
        if fill:
            cv2.rectangle(img, (x, y), (x+w, y+h), THEME["bg_card"], -1)
            cv2.line(img, (x, y), (x+w, y), acc, 2)
        cv2.rectangle(img, (x, y), (x+w, y+h), THEME["border"], 1)
        bracket = 24
        self._draw_animus_corner(img, x, y, bracket, bracket, acc, is_tl=True, is_br=False)
        self._draw_animus_corner(img, x + w - bracket, y, bracket, bracket, acc, is_tl=True, is_br=False)
        self._draw_animus_corner(img, x, y + h - bracket, bracket, bracket, acc, is_tl=False, is_br=True)
        self._draw_animus_corner(img, x + w - bracket, y + h - bracket, bracket, bracket, acc, is_tl=False, is_br=True)

    def draw_top_bar(self, img, title=None):
        """Animus-style bar: accent line under, title in amber."""
        win_w, win_h = WIN_W, WIN_H
        bar_h = int(LAYOUT["top_bar"]["height"] * win_h)
        cv2.rectangle(img, (0, 0), (win_w, bar_h), THEME["bg_card"], -1)
        cv2.line(img, (0, bar_h), (win_w, bar_h), THEME["accent"], 2)
        if title:
            cv2.putText(img, title.upper(), (int(win_w*0.024), int(bar_h*0.62)), cv2.FONT_HERSHEY_SIMPLEX, THEME["font_subtitle"], THEME["text_dim"], THEME["thickness"])
        self.draw_button(img, "HELP", LAYOUT["top_bar"]["help"], bg=THEME["panel"])
        self.draw_button(img, "BACK", LAYOUT["top_bar"]["back"], bg=THEME["bg_card_raised"])

    def draw_button(self, img, text, rel_box, bg=None, style="default"):
        """Animus-style button: dark panel, amber border on hover/primary."""
        if bg is None: bg = THEME["panel"]
        if style == "primary": bg = THEME["accent_dim"]
        if style == "danger": bg = (60, 32, 32)
        win_w, win_h = WIN_W, WIN_H
        rx, ry, rw, rh = rel_box
        x, y = int(rx*win_w), int(ry*win_h)
        bw, bh = int(rw*win_w), int(rh*win_h)
        is_hover = self._in_button(rel_box)
        fill = THEME["panel_hover"] if is_hover and style == "default" else (THEME["accent_dim"] if is_hover and style == "primary" else bg)
        cv2.rectangle(img, (x, y), (x+bw, y+bh), fill, -1)
        border_col = THEME["accent"] if (is_hover or style == "primary") else THEME["border"]
        cv2.rectangle(img, (x, y), (x+bw, y+bh), border_col, 1)
        txt_col = THEME["accent_glow"] if (style == "primary" and not is_hover) else THEME["text_light"]
        pad = 10
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, THEME["font_small"], THEME["thickness"])
        tx = x + max(pad, (bw - tw) // 2)
        ty = y + (bh + th) // 2 - 2
        cv2.putText(img, text, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, THEME["font_small"], txt_col, THEME["thickness"])

    def draw_transport(self, img):
        win_w, win_h = WIN_W, WIN_H
        t = LAYOUT["transport"]
        y1 = int(t["track_y"]*win_h); y2 = int((t["track_y"]+t["track_h"])*win_h)
        x1 = int(t["track_x1"]*win_w); x2 = int(t["track_x2"]*win_w)
        cv2.rectangle(img, (x1, y1), (x2, y2), THEME["bg_card"], -1)
        cv2.rectangle(img, (x1, y1), (x2, y2), THEME["border"], 1)
        if self.vid_total > 0:
            px = x1 + int((x2 - x1) * (self.vid_current / self.vid_total))
            r = 6 if self.dragging_timeline else 5
            cv2.circle(img, (px, (y1+y2)//2), r, THEME["accent"], -1)
        self.draw_button(img, "|<<", t["rw"])
        self.draw_button(img, "||" if self.is_playing else ">", t["play"])
        self.draw_button(img, ">>|", t["ff"])
        self.draw_button(img, "Stop", t["stop"])

    def inject_mouse(self, event_type, x, y):
        """Called by Qt (or other host) to feed mouse events. x,y in pixel coords (0..WIN_W, 0..WIN_H). event_type: 'move', 'press', 'release', 'rpress'."""
        win_w, win_h = WIN_W, WIN_H
        rx, ry = x / win_w, y / win_h
        self.last_mouse_pos = (x, y)
        tr = LAYOUT["transport"]
        is_timeline_area = (tr["track_x1"] <= rx <= tr["track_x2"] and tr["track_ry"][0] <= ry <= tr["track_ry"][1])
        if event_type == "move":
            self.hover_active = True
            if self.dragging_slider == "ZOOM" and self.app_state == "LIVE":
                self.zoom = 1.0 + (np.clip((rx - 0.52) / 0.16, 0, 1) * 3.0)
            elif self.dragging_slider == "EXPOSURE" and self.app_state == "LIVE":
                self.exposure = 0.2 + (np.clip((rx - 0.70) / 0.16, 0, 1) * 2.8)
            elif self.dragging_slider == "CONF":
                s = LAYOUT["settings"]; sx, sw = s["slider_box"][0], s["slider_box"][2]
                self.yolo_conf = 0.1 + (np.clip((rx - sx) / sw, 0, 1) * 0.8)
            elif isinstance(self.dragging_slider, str) and self.dragging_slider.startswith("IMG_"):
                self._set_img_ctrl_from_rx(self.dragging_slider[4:], rx)
            elif self.dragging_slider == "F_OPACITY":
                self.forensics_opacity = float(np.clip((rx - 0.10) / 0.24, 0, 1))
            elif self.dragging_slider == "F_P1":
                tool = self.forensics_tools[self.forensics_tool_idx]
                t = float(np.clip((rx - 0.38) / 0.24, 0, 1))
                if tool == "ELA":
                    self.forensics_ela_quality = int(65 + t * 34)
                elif tool == "NOISE":
                    self.forensics_noise_amp = 0.6 + t * 4.4
                elif tool == "SWEEP":
                    self.forensics_sweep = t
                elif tool == "PCA":
                    self.forensics_pca_component = int(1 + t * 2.99)
                elif tool == "CLONE":
                    self.forensics_clone_sim = 0.75 + t * 0.24
                elif tool == "MAGNIFIER":
                    self.forensics_mag_zoom = int(2 + t * 10)
            elif self.dragging_slider == "F_P2":
                tool = self.forensics_tools[self.forensics_tool_idx]
                t = float(np.clip((rx - 0.66) / 0.24, 0, 1))
                if tool == "ELA":
                    self.forensics_ela_scale = 4.0 + t * 36.0
                elif tool == "SWEEP":
                    self.forensics_sweep_width = 8.0 + t * 92.0
                elif tool == "CLONE":
                    self.forensics_clone_detail = 2.0 + t * 28.0
            elif self.dragging_timeline and self.app_state in ["ANALYZE_VIDEO", "ANALYZE_AUDIO"]:
                self.vid_current = int(np.clip((rx - 0.1) / 0.8, 0, 1) * self.vid_total)
                self.sync_media()
        elif event_type == "press":
            if is_timeline_area and self.app_state in ["ANALYZE_VIDEO", "ANALYZE_AUDIO"]:
                self.dragging_timeline = True
                self.vid_current = int(np.clip((rx - 0.1) / 0.8, 0, 1) * self.vid_total)
                self.sync_media()
            elif self.app_state in ["LIVE", "ANALYZE_PHOTO", "ANALYZE_VIDEO"] and ry < 0.8 and not self._is_over_img_controls(rx, ry):
                self.color_sample_pos = (x, y)
            self.handle_clicks(rx, ry)
        elif event_type == "rpress":
            self.color_sample_pos = None
        elif event_type == "release":
            self.dragging_slider = None
            self.dragging_timeline = False

    def paint_frame(self):
        """Build one frame of the UI into a numpy array (BGR, WIN_H x WIN_W). Reuses buffer for speed."""
        win_w, win_h = WIN_W, WIN_H
        display = self._display_buf
        display[:] = THEME["bg_dark"]

        if self.app_state == "LOADING":
            self._draw_loading_screen(display)
            if self.loading_progress >= 1.0:
                self.app_state = "MENU"
            return display.copy()

        if self.app_state in ["MENU", "SETTINGS", "MEDIA_MENU", "LIVE", "ANALYZE_PHOTO", "ANALYZE_VIDEO", "ANALYZE_AUDIO", "ANALYZE_TEXT", "FORENSICS"]:
            if self.cap and self.cap.isOpened() and self.app_state in ["MENU", "SETTINGS", "MEDIA_MENU"]:
                ret, bg_frame = self.cap.read()
                if ret:
                    lb = self.letterbox(cv2.flip(bg_frame, 1))
                    self._menu_bg = cv2.GaussianBlur(lb, (31, 31), 0)
                    display[:] = cv2.addWeighted(self._menu_bg, 0.4, display, 0.6, 0)

            if self.app_state == "MENU":
                self.draw_card(display, (0.28, 0.06, 0.44, 0.78))
                cv2.putText(display, "CLOUTVISION", (int(win_w*0.335), int(win_h*LAYOUT["menu"]["title_y"])), cv2.FONT_HERSHEY_SIMPLEX, THEME["font_title"], THEME["accent"], THEME["thickness_heavy"])
                cv2.putText(display, "SELECT SEQUENCE", (int(win_w*0.355), int(win_h*LAYOUT["menu"]["tagline_y"])), cv2.FONT_HERSHEY_SIMPLEX, THEME["font_small"], THEME["text_muted"], THEME["thickness"])
                for i, (box, label) in enumerate(zip(LAYOUT["menu_buttons"], LAYOUT["menu"]["items"])):
                    self.draw_button(display, label, box, style="primary" if i == 0 else "default")
                self.draw_button(display, "SHUTDOWN", LAYOUT["menu"]["shutdown"], style="danger")
                tip = self.tips[int(time.time() / 5) % len(self.tips)]
                cv2.putText(display, tip, (int(win_w*0.16), int(win_h*LAYOUT["menu"]["tip_y"])), cv2.FONT_HERSHEY_SIMPLEX, THEME["font_body"], THEME["text_muted"], THEME["thickness"])
                self._scanline_overlay(display, step=5, dim=0.06)

            elif self.app_state == "SETTINGS":
                self.draw_top_bar(display, "Control Center")
                self.draw_card(display, (0.08, 0.12, 0.84, 0.74))
                s = LAYOUT["settings"]
                self.draw_button(display, f"Camera: {self.cam_index}", s["col1"][0])
                self.draw_button(display, f"Face mask: {'On' if self.face_mask is not None else '…'}", s["col1"][1])
                face_label_short = (self.custom_face_text[:14] + "…") if len(self.custom_face_text) > 14 else self.custom_face_text
                self.draw_button(display, f"Face label: {face_label_short or '…'}", s["col1"][2])
                self.draw_button(display, f"OCR Profile: {self.ocr_profile}", s["col1"][3])
                self.draw_button(display, f"Export: {self.export_target}", s["col2"][0])
                self.draw_button(display, f"Clock: {'On' if self.show_clock else 'Off'}", s["col2"][1])
                self.draw_button(display, f"UI color: {self.ui_color_names[self.ui_color_idx % len(self.ui_color_names)]}", s["col2"][2])
                self.draw_button(display, "Reset sliders", s["col2"][3])
                self.draw_button(display, f"Skeleton: {'On' if self.toggle_skeleton else 'Off'}", s["col2"][4], bg=THEME["success"] if self.toggle_skeleton else THEME["panel"])
                self.draw_button(display, f"Emotion: {'On' if self.toggle_emotion else 'Off'}", s["col2"][5], bg=THEME["success"] if self.toggle_emotion else THEME["panel"])
                self.draw_button(display, f"Color: {'On' if self.toggle_color else 'Off'}", s["col2"][6], bg=THEME["success"] if self.toggle_color else THEME["panel"])
                self.draw_button(display, f"Pose backend: {self.pose_backend}", s["col2"][7])
                sx = int(s["slider_box"][0]*win_w); sy = int(s["slider_box"][1]*win_h); sw = int(s["slider_box"][2]*win_w); sh = int(s["slider_box"][3]*win_h)
                cv2.putText(display, f"AI confidence: {round(self.yolo_conf,2)}", (sx, sy - 4), cv2.FONT_HERSHEY_SIMPLEX, THEME["font_small"], THEME["text_dim"], 1)
                cv2.rectangle(display, (sx, sy), (sx+sw, sy+sh), THEME["panel"], -1)
                cv2.rectangle(display, (sx, sy), (sx+sw, sy+sh), THEME["border"], 1)
                thumb_x = sx + int(((self.yolo_conf - 0.1) / 0.8) * sw)
                cv2.circle(display, (thumb_x, sy + sh//2), 6, THEME["accent"], -1)

                # Error Log toggle and panel
                self.draw_button(display, f"Error Log ({len(self.error_log)})", (0.50, 0.84, 0.34, 0.056), bg=THEME["panel"])
                if self.show_error_log:
                    self.draw_card(display, (0.10, 0.72, 0.80, 0.22))
                    cv2.putText(display, "ERROR LOG (latest first)", (int(0.12*win_w), int(0.76*win_h)), cv2.FONT_HERSHEY_SIMPLEX, THEME["font_small"], THEME["accent"], 1)
                    # Copy Log button inside panel
                    copy_rel = (0.72, 0.745, 0.16, 0.045)
                    self.draw_button(display, "Copy log", copy_rel, bg=THEME["panel"])
                    start_y = int(0.80 * win_h)
                    max_lines = 5
                    for i, line in enumerate(reversed(self.error_log[-max_lines:])):
                        cv2.putText(display, line, (int(0.12*win_w), start_y + i*18), cv2.FONT_HERSHEY_SIMPLEX, THEME["font_small"], THEME["text_light"], 1)

            elif self.app_state == "MEDIA_MENU":
                self.draw_top_bar(display, "Analysis Suite")
                self.draw_card(display, (0.28, 0.12, 0.44, 0.58))
                labels = ["Import Photo", "Import Video", "Import Audio", "Import Text / PDF", "Session Summary", "Forensics Mode"]
                for box, label in zip(LAYOUT["media_menu"]["buttons"], labels):
                    self.draw_button(display, label, box, style="primary")

            elif self.app_state == "LIVE":
                if self.cap and self.cap.isOpened():
                    try:
                        ret, raw = self.cap.read()
                        if ret and raw is not None:
                            frame = cv2.flip(raw, 1)
                            if self.zoom > 1.0:
                                h, w = frame.shape[:2]; cx, cy = w // 2, h // 2
                                rx, ry = int(w / (2 * self.zoom)), int(h / (2 * self.zoom))
                                frame = cv2.resize(frame[cy - ry:cy + ry, cx - rx:cx + rx], (w, h))
                            if self.exposure != 1.0: frame = cv2.convertScaleAbs(frame, alpha=self.exposure, beta=0)
                            display = self.draw_yolo_analytics(self.letterbox(frame))
                            display = self._apply_image_controls(display)
                    except Exception as e:
                        print(f"Camera Error: {e}")
                        self._log_error("camera", f"read error: {e}")
                else:
                    cv2.putText(display, "NO CAMERA ACTIVE", (int(0.32*win_w), int(0.45*win_h)), cv2.FONT_HERSHEY_SIMPLEX, 0.8, THEME["text_dim"], 2)
                    cv2.putText(display, "Press LENS to select a camera.", (int(0.24*win_w), int(0.52*win_h)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, THEME["text_muted"], 1)
                # In-LIVE toolbar: below top bar so buttons aren't covered. Skel, Emo, Color, Zoom, Exp, Lens, Next FX
                lt, lh = LAYOUT["live_toolbar"]["y"], LAYOUT["live_toolbar"]["h"]
                ly = LAYOUT["live_toolbar"]["slider_bar_y"]
                self.draw_button(display, "Skel", (0.28, lt, 0.072, lh), bg=THEME["success"] if self.toggle_skeleton else THEME["panel"])
                # Emo/Color are fully active only in SPOOKY_MODE; in other modes they are dimmed but still clickable
                emo_bg = THEME["success"] if (self.toggle_emotion and self.mode == "SPOOKY_MODE") else THEME["panel"]
                col_bg = THEME["success"] if (self.toggle_color and self.mode == "SPOOKY_MODE") else THEME["panel"]
                self.draw_button(display, "Emo", (0.36, lt, 0.072, lh), bg=emo_bg)
                self.draw_button(display, "Color", (0.44, lt, 0.072, lh), bg=col_bg)
                cv2.putText(display, f"Zoom {self.zoom:.1f}x", (int(0.52*win_w), int(win_h*ly - 6)), cv2.FONT_HERSHEY_SIMPLEX, THEME["font_small"], THEME["text_dim"], 1)
                cv2.rectangle(display, (int(0.52*win_w), int(win_h*ly)), (int(0.68*win_w), int(win_h*ly + 16)), THEME["bg_card"], -1)
                cv2.rectangle(display, (int(0.52*win_w), int(win_h*ly)), (int(0.68*win_w), int(win_h*ly + 16)), THEME["border"], 1)
                cv2.circle(display, (int(0.52*win_w + ((self.zoom-1.0)/3.0)*0.16*win_w), int(win_h*ly + 8)), 5, THEME["accent"], -1)
                cv2.putText(display, f"Exp {self.exposure:.1f}x", (int(0.70*win_w), int(win_h*ly - 6)), cv2.FONT_HERSHEY_SIMPLEX, THEME["font_small"], THEME["text_dim"], 1)
                cv2.rectangle(display, (int(0.70*win_w), int(win_h*ly)), (int(0.86*win_w), int(win_h*ly + 16)), THEME["bg_card"], -1)
                cv2.rectangle(display, (int(0.70*win_w), int(win_h*ly)), (int(0.86*win_w), int(win_h*ly + 16)), THEME["border"], 1)
                cv2.circle(display, (int(0.70*win_w + ((self.exposure-0.2)/2.8)*0.16*win_w), int(win_h*ly + 8)), 5, THEME["accent"], -1)
                self.draw_button(display, "Lens", (0.86, lt, 0.085, lh))
                fx_label = "Next FX" if self.mode == "EFFECTS" else "FX Mode"
                fx_bg = THEME["accent_dim"] if self.mode == "EFFECTS" else THEME["panel"]
                self.draw_button(display, fx_label, (0.18, lt, 0.082, lh), bg=fx_bg)

            elif self.app_state == "ANALYZE_VIDEO":
                if self.vid_cap and self.vid_cap.isOpened():
                    if self.is_playing:
                        ret, f = self.vid_cap.read()
                        if ret: self.vid_current += 1; self.last_vid_frame = self.draw_yolo_analytics(self.letterbox(f))
                        else: self.is_playing = False 
                    if self.last_vid_frame is not None:
                        display = self._apply_image_controls(self.last_vid_frame.copy())
                self.draw_transport(display)
                tb = LAYOUT["analysis_toolbar"]["video"]
                self.draw_button(display, "MDLS", tb["mdls"])
                # Focus saliency toggle
                self.draw_button(display, "FOCUS", (0.37, 0.90, 0.10, 0.048), style="primary" if self.toggle_focus else "default")
                if self._ocr_available():
                    self.draw_button(display, "Live Text", tb["ocr"], style="primary" if self.video_run_ocr else "default")
                    if self.video_run_ocr and self.last_vid_frame is not None:
                        if self.video_ocr_frame_index != self.vid_current:
                            self.video_ocr_frame_index = self.vid_current
                            self.ocr_boxes = self._run_ocr_image(self.last_vid_frame)
                        self.ocr_text_rects = []
                        # Draw boxes on frame
                        for box in self.ocr_boxes:
                            x, y, w, h = box["x"], box["y"], box["w"], box["h"]
                            txt = box["text"]
                            cv2.rectangle(display, (x, y), (x + w, y + h), THEME["accent"], 2)
                            (tw, th), _ = cv2.getTextSize(txt[:24], cv2.FONT_HERSHEY_SIMPLEX, THEME["font_small"], 1)
                            cv2.rectangle(display, (x, max(0, y - th - 4)), (x + tw + 4, y), THEME["bg_card"], -1)
                            cv2.putText(display, txt[:24] + ("..." if len(txt) > 24 else ""), (x + 2, y - 4), cv2.FONT_HERSHEY_SIMPLEX, THEME["font_small"], THEME["text_light"], 1)
                        # Side text panel with selectable lines
                        if self.ocr_boxes:
                            panel_x1, panel_y1 = int(0.72 * win_w), int(0.18 * win_h)
                            panel_w, panel_h = int(0.26 * win_w), int(0.56 * win_h)
                            cv2.rectangle(display, (panel_x1, panel_y1), (panel_x1 + panel_w, panel_y1 + panel_h), THEME["bg_card"], -1)
                            cv2.rectangle(display, (panel_x1, panel_y1), (panel_x1 + panel_w, panel_y1 + panel_h), THEME["border"], 1)
                            cv2.putText(display, f"Detected text [{self.ocr_last_engine}]", (panel_x1 + 10, panel_y1 + 20), cv2.FONT_HERSHEY_SIMPLEX, THEME["font_small"], THEME["accent"], 1)
                            ty = panel_y1 + 40
                            line_h = 20
                            max_lines = int((panel_h - 40) / line_h)
                            for i, box in enumerate(self.ocr_boxes[:max_lines]):
                                txt = box["text"]
                                line = txt if len(txt) <= 34 else txt[:31] + "..."
                                cv2.putText(display, line, (panel_x1 + 10, ty), cv2.FONT_HERSHEY_SIMPLEX, THEME["font_small"], THEME["text_light"], 1)
                                self.ocr_text_rects.append((panel_x1 + 6, ty - 16, panel_w - 12, line_h, txt))
                                ty += line_h
                        if self.ocr_boxes:
                            self.draw_button(display, "Copy frame", tb["copy_frame"], style="primary")
                        if time.time() - self.ocr_copied_at < 2.0:
                            cv2.rectangle(display, (win_w // 2 - 80, win_h - 52), (win_w // 2 + 80, win_h - 24), THEME["success"], -1)
                            cv2.putText(display, "Copied", (win_w // 2 - 36, win_h - 32), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
                    else:
                        self.ocr_boxes = []

            elif self.app_state == "ANALYZE_PHOTO":
                if self.analysis_file and os.path.isfile(self.analysis_file):
                    img_full = self._imread_any(self.analysis_file)
                    if img_full is not None:
                        # Letterbox params: same as letterbox() so we can transform OCR boxes (orig coords) to display
                        h_orig, w_orig = img_full.shape[:2]
                        scale = min(WIN_W / w_orig, WIN_H / h_orig)
                        new_w, new_h = int(w_orig * scale), int(h_orig * scale)
                        x_off = (WIN_W - new_w) // 2
                        y_off = (WIN_H - new_h) // 2
                        img = self.letterbox(img_full)
                        display = self.draw_yolo_analytics(img)
                        display = self._apply_image_controls(display)
                        tb = LAYOUT["analysis_toolbar"]["photo"]
                        self.draw_button(display, "MDLS", tb["mdls"])
                        # Focus saliency toggle
                        self.draw_button(display, "FOCUS", (0.50, 0.90, 0.10, 0.048), style="primary" if self.toggle_focus else "default")
                        self.draw_button(display, "DOC", (0.62, 0.90, 0.08, 0.048), style="primary" if self.toggle_doc_mode else "default")
                        self.draw_button(display, "Clean Scan", (0.71, 0.90, 0.12, 0.048))
                        self.draw_button(display, "Translate", (0.84, 0.90, 0.12, 0.048), style="primary" if self.doc_translate_on else "default")
                        if self._ocr_available():
                            self.draw_button(display, "Live Text", tb["ocr"], style="primary" if self.run_ocr else "default")
                            if self.run_ocr:
                                if self.ocr_cache is None:
                                    # Run OCR on full-resolution image so product text (e.g. can labels) is readable
                                    self.ocr_boxes = self._run_ocr_image(img_full)
                                    self.ocr_letterbox_scale = scale
                                    self.ocr_letterbox_xoff = x_off
                                    self.ocr_letterbox_yoff = y_off
                                    self.ocr_cache = True
                                self.ocr_text_rects = []
                                for box in self.ocr_boxes:
                                    # Transform from original image coords to display coords
                                    x = int(box["x"] * scale + x_off)
                                    y = int(box["y"] * scale + y_off)
                                    w = max(2, int(box["w"] * scale))
                                    h = max(2, int(box["h"] * scale))
                                    txt = box["text"]
                                    cv2.rectangle(display, (x, y), (x + w, y + h), THEME["accent"], 2)
                                    (tw, th), _ = cv2.getTextSize(txt[:24], cv2.FONT_HERSHEY_SIMPLEX, THEME["font_small"], 1)
                                    cv2.rectangle(display, (x, max(0, y - th - 4)), (x + tw + 4, y), THEME["bg_card"], -1)
                                    cv2.rectangle(display, (x, max(0, y - th - 4)), (x + tw + 4, y), THEME["accent"], 1)
                                    cv2.putText(display, txt[:24] + ("..." if len(txt) > 24 else ""), (x + 2, y - 4), cv2.FONT_HERSHEY_SIMPLEX, THEME["font_small"], THEME["text_light"], 1)
                                # Side panel with detected text lines (clickable to copy)
                                if self.ocr_boxes:
                                    panel_x1, panel_y1 = int(0.72 * win_w), int(0.18 * win_h)
                                    panel_w, panel_h = int(0.26 * win_w), int(0.56 * win_h)
                                    cv2.rectangle(display, (panel_x1, panel_y1), (panel_x1 + panel_w, panel_y1 + panel_h), THEME["bg_card"], -1)
                                    cv2.rectangle(display, (panel_x1, panel_y1), (panel_x1 + panel_w, panel_y1 + panel_h), THEME["border"], 1)
                                    cv2.putText(display, f"Detected text [{self.ocr_last_engine}]", (panel_x1 + 10, panel_y1 + 20), cv2.FONT_HERSHEY_SIMPLEX, THEME["font_small"], THEME["accent"], 1)
                                    ty = panel_y1 + 40
                                    line_h = 20
                                    max_lines = int((panel_h - 40) / line_h)
                                    for i, box in enumerate(self.ocr_boxes[:max_lines]):
                                        txt = box["text"]
                                        if self.doc_translate_on:
                                            txt = self._translate_text_local(txt)
                                        line = txt if len(txt) <= 34 else txt[:31] + "..."
                                        cv2.putText(display, line, (panel_x1 + 10, ty), cv2.FONT_HERSHEY_SIMPLEX, THEME["font_small"], THEME["text_light"], 1)
                                        self.ocr_text_rects.append((panel_x1 + 6, ty - 16, panel_w - 12, line_h, txt))
                                        ty += line_h
                                # Smart document mode: line blocks + action suggestions
                                if self.toggle_doc_mode and self.ocr_boxes:
                                    self.doc_text_blocks = self._build_doc_blocks(self.ocr_boxes)
                                    for blk in self.doc_text_blocks[:10]:
                                        x, y, w, h = blk["bbox"]
                                        x = int(x * scale + x_off); y = int(y * scale + y_off)
                                        w = int(w * scale); h = int(h * scale)
                                        cv2.rectangle(display, (x, y), (x + w, y + h), (255, 220, 80), 2)
                                        sug = self._doc_suggestion(blk["text"])
                                        cv2.putText(display, sug, (x, max(16, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 220, 80), 1)
                                if self.ocr_boxes:
                                    self.draw_button(display, "Copy all", tb["copy_all"], style="primary")
                                else:
                                    cv2.putText(display, "No text detected", (int(win_w * 0.38), int(win_h * 0.92)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, THEME["text_muted"], 1)
                                if time.time() - self.ocr_copied_at < 2.0:
                                    cv2.rectangle(display, (win_w // 2 - 80, win_h - 52), (win_w // 2 + 80, win_h - 24), THEME["success"], -1)
                                    cv2.putText(display, "Copied", (win_w // 2 - 36, win_h - 32), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
                            else:
                                self.ocr_boxes = []
                    else:
                        self.error_message = "Could not load image file."
                else:
                    self.error_message = "No photo selected or file missing."

            elif self.app_state == "ANALYZE_AUDIO":
                cv2.putText(display, "AUDIO ANALYSIS HUD", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,0), 2)
                if self.audio_enabled:
                    if self.is_playing and not pygame.mixer.music.get_busy(): pygame.mixer.music.unpause()
                    elif not self.is_playing and pygame.mixer.music.get_busy(): pygame.mixer.music.pause()
                    if self.audio_length > 0:
                        self.vid_current = int(self.vid_total * (pygame.mixer.music.get_pos() / 1000.0) / self.audio_length)
                if self.audio_data is not None: display[int(win_h*0.2):int(win_h*0.2)+500, 0:WIN_W] = self.audio_data
                self.draw_transport(display)

            elif self.app_state == "ANALYZE_TEXT":
                cv2.putText(display, "TEXT ANALYSIS & SUMMARIZATION", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, THEME["font_title"], (255, 255, 0), THEME["thickness_heavy"])
                self.draw_button(display, f"SIZE: {self.summary_length}", (0.02, 0.12, 0.1, 0.05))
                self.text_block_rects = []
                if self.text_data:
                    if self.text_data.get("raw") or self.text_data.get("blocks"):
                        self.draw_button(display, "Copy all", (0.14, 0.12, 0.10, 0.05), style="primary")
                    cv2.putText(display, f"Modified: {self.text_data['date']} | Words: {self.text_data['words']} | Chars: {self.text_data['chars']}", (20, 160), cv2.FONT_HERSHEY_SIMPLEX, THEME["font_body"], THEME["text_dim"], THEME["thickness"])
                    blocks = self.text_data.get("blocks")
                    if not blocks:
                        blocks = [self.text_data["summary"]] if self.text_data.get("summary") else []
                    pad, line_h, card_margin = 12, 22, 16
                    y_start = 200
                    max_w = win_w - 80
                    for blk in blocks[:20]:
                        blk = (blk or "").strip()
                        if not blk:
                            continue
                        lines = []
                        current = ""
                        for word in blk.split():
                            test = current + word + " "
                            (tw, _), _ = cv2.getTextSize(test, cv2.FONT_HERSHEY_SIMPLEX, THEME["font_body"], 1)
                            if tw > max_w and current:
                                lines.append(current.strip())
                                current = word + " "
                            else:
                                current = test
                        if current.strip():
                            lines.append(current.strip())
                        box_h = max(1, len(lines)) * line_h + pad * 2
                        box_w = min(max_w + pad * 2, win_w - 40)
                        x_box, y_box = 20, y_start
                        cv2.rectangle(display, (x_box, y_box), (x_box + box_w, y_box + box_h), THEME["bg_card"], -1)
                        cv2.rectangle(display, (x_box, y_box), (x_box + box_w, y_box + box_h), THEME["accent"], 1)
                        for li, line in enumerate(lines):
                            cv2.putText(display, line, (x_box + pad, y_box + pad + (li + 1) * line_h), cv2.FONT_HERSHEY_SIMPLEX, THEME["font_body"], THEME["text_light"], THEME["thickness"])
                        self.text_block_rects.append((x_box, y_box, box_w, box_h, blk))
                        y_start += box_h + card_margin
                    if time.time() - self.ocr_copied_at < 2.0:
                        cv2.rectangle(display, (win_w // 2 - 80, win_h - 52), (win_w // 2 + 80, win_h - 24), THEME["success"], -1)
                        cv2.putText(display, "Copied", (win_w // 2 - 36, win_h - 32), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
                else:
                    cv2.putText(display, "No text data. Try importing again.", (20, 200), cv2.FONT_HERSHEY_SIMPLEX, THEME["font_body"], THEME["text_dim"], THEME["thickness"])

            elif self.app_state == "FORENSICS":
                if self.analysis_file and os.path.isfile(self.analysis_file):
                    try:
                        img_full = self._imread_any(self.analysis_file)
                        if img_full is not None:
                            base = self.letterbox(img_full)
                            try:
                                display = self._forensics_apply(base)
                            except Exception as e:
                                # Never let a forensics tool blank the screen; fall back to plain letterboxed image.
                                self._log_error("forensics", f"tool error: {e}")
                                display = base
                        else:
                            cv2.putText(display, "Could not load image.", (30, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.8, THEME["error"], 2)
                    except Exception as e:
                        self._log_error("forensics", f"load/letterbox error: {e}")
                        cv2.putText(display, "Forensics render error.", (30, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.8, THEME["error"], 2)
                else:
                    cv2.putText(display, "No forensic image selected.", (30, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.8, THEME["text_dim"], 2)

                tool = self.forensics_tools[self.forensics_tool_idx]
                enh = self.forensics_enhance_opts[self.forensics_enhance_idx]
                # Tool button with slide-up menu
                self.draw_button(display, f"Tool: {tool}", (0.02, 0.90, 0.16, 0.048), style="primary")
                if self.forensics_tool_menu_open:
                    # Draw menu ABOVE slider region (sliders start at y=0.84).
                    bx, by, bw, bh = 0.02, 0.84, 0.16, 0.048
                    item_h = 0.045
                    for i, name in enumerate(self.forensics_tools):
                        iy1 = by - (i + 1) * item_h
                        rect = (bx, iy1, bw, item_h)
                        self.draw_button(display, name, rect, style="secondary" if i == self.forensics_tool_idx else "default")
                self.draw_button(display, f"Enh: {enh}", (0.19, 0.90, 0.16, 0.048))
                self.draw_button(display, f"Invert: {'On' if self.forensics_invert else 'Off'}", (0.36, 0.90, 0.10, 0.048))
                self.draw_button(display, "Open Image", (0.47, 0.90, 0.14, 0.048))

                # Hover tooltips (only show relevant line for hovered control)
                tooltip = None
                mx, my = self.last_mouse_pos
                def _hover(rel_box):
                    x, y, w, h = rel_box
                    x1 = int(x * win_w); y1 = int(y * win_h)
                    x2 = x1 + int(w * win_w); y2 = y1 + int(h * win_h)
                    return x1 <= mx <= x2 and y1 <= my <= y2

                btn_y = 0.838
                btn_w = 0.028
                btn_h = 0.034
                gap = 0.006

                # Buttons
                if _hover((0.02, 0.90, 0.16, 0.048)):
                    tooltip = self.forensics_help["tool"].get(tool, "")
                elif _hover((0.19, 0.90, 0.16, 0.048)):
                    tooltip = self.forensics_help["enh"].get(enh, "")
                elif _hover((0.36, 0.90, 0.10, 0.048)):
                    tooltip = self.forensics_help["settings"]["INVERT"]

                # Slider bars and +/- buttons
                elif _hover((0.10, 0.84, 0.24, 0.03)) or _hover((0.10 - btn_w - gap, btn_y, btn_w, btn_h)) or _hover((0.34 + gap, btn_y, btn_w, btn_h)):
                    tooltip = self.forensics_help["settings"]["OPACITY"]
                elif _hover((0.38, 0.84, 0.24, 0.03)) or _hover((0.38 - btn_w - gap, btn_y, btn_w, btn_h)) or _hover((0.62 + gap, btn_y, btn_w, btn_h)):
                    if tool == "ELA":
                        tooltip = "Param1 (ELA): JPEG quality for recompression pass."
                    elif tool == "NOISE":
                        tooltip = "Param1 (Noise): amplification for noise residue layer."
                    elif tool == "SWEEP":
                        tooltip = "Param1 (Sweep): center luminance level to isolate."
                    elif tool == "PCA":
                        tooltip = "Param1 (PCA): which principal component to display."
                    elif tool == "CLONE":
                        tooltip = "Param1 (Clone): similarity threshold (higher = stricter matches)."
                    elif tool == "MAGNIFIER":
                        tooltip = "Param1 (Magnifier): zoom factor."
                    else:
                        tooltip = "Param1: tool-specific parameter."
                elif _hover((0.66, 0.84, 0.24, 0.03)) or _hover((0.66 - btn_w - gap, btn_y, btn_w, btn_h)) or _hover((0.90 + gap, btn_y, btn_w, btn_h)):
                    if tool == "ELA":
                        tooltip = "Param2 (ELA): scale multiplier for ELA differences."
                    elif tool == "SWEEP":
                        tooltip = "Param2 (Sweep): width of the luminance band."
                    elif tool == "CLONE":
                        tooltip = "Param2 (Clone): minimum texture/detail required."
                    elif tool == "MAGNIFIER":
                        tooltip = "Param2: not used (move mouse over image)."
                    else:
                        tooltip = "Param2: not used for this tool."

                if tooltip:
                    # Draw tooltip card near cursor but clamped on-screen
                    pad = 10
                    (tw, th), _ = cv2.getTextSize(tooltip[:120], cv2.FONT_HERSHEY_SIMPLEX, 0.44, 1)
                    w_box = tw + pad * 2
                    h_box = th + pad * 2 + 2
                    x0 = int(np.clip(mx + 16, 10, win_w - w_box - 10))
                    y0 = int(np.clip(my - h_box - 12, int(LAYOUT["top_bar"]["height"] * win_h) + 8, win_h - h_box - 10))
                    cv2.rectangle(display, (x0, y0), (x0 + w_box, y0 + h_box), THEME["bg_card_raised"], -1)
                    cv2.rectangle(display, (x0, y0), (x0 + w_box, y0 + h_box), THEME["border_light"], 1)
                    cv2.putText(display, tooltip[:120], (x0 + pad, y0 + h_box - pad), cv2.FONT_HERSHEY_SIMPLEX, 0.44, THEME["text_light"], 1)

                # Opacity slider
                cv2.putText(display, f"Opacity {self.forensics_opacity:.2f}", (int(0.10*win_w), int(0.835*win_h)), cv2.FONT_HERSHEY_SIMPLEX, 0.42, THEME["text_dim"], 1)
                # +/- buttons
                self.draw_button(display, "-", (0.10 - btn_w - gap, btn_y, btn_w, btn_h), style="secondary")
                self.draw_button(display, "+", (0.34 + gap, btn_y, btn_w, btn_h), style="secondary")
                cv2.rectangle(display, (int(0.10*win_w), int(0.84*win_h)), (int(0.34*win_w), int(0.87*win_h)), THEME["bg_card"], -1)
                cv2.rectangle(display, (int(0.10*win_w), int(0.84*win_h)), (int(0.34*win_w), int(0.87*win_h)), THEME["border"], 1)
                tx = int(0.10*win_w + self.forensics_opacity * (0.24*win_w))
                cv2.circle(display, (tx, int(0.855*win_h)), 5, THEME["accent"], -1)

                # Tool parameter sliders
                p1_label, p2_label = "Param1", "Param2"
                p1_t, p2_t = 0.5, 0.5
                if tool == "ELA":
                    p1_label = f"JPEG Q {self.forensics_ela_quality:d}"
                    p1_t = (self.forensics_ela_quality - 65) / 34.0
                    p2_label = f"Scale {self.forensics_ela_scale:.1f}"
                    p2_t = (self.forensics_ela_scale - 4.0) / 36.0
                elif tool == "NOISE":
                    p1_label = f"Noise Amp {self.forensics_noise_amp:.1f}"
                    p1_t = (self.forensics_noise_amp - 0.6) / 4.4
                    p2_label = "N/A"
                    p2_t = 0.0
                elif tool == "SWEEP":
                    p1_label = f"Sweep {self.forensics_sweep:.2f}"
                    p1_t = self.forensics_sweep
                    p2_label = f"Width {self.forensics_sweep_width:.0f}"
                    p2_t = (self.forensics_sweep_width - 8.0) / 92.0
                elif tool == "PCA":
                    p1_label = f"Component {self.forensics_pca_component:d}"
                    p1_t = (self.forensics_pca_component - 1) / 2.0
                    p2_label = "N/A"
                    p2_t = 0.0
                elif tool == "CLONE":
                    p1_label = f"Similarity {self.forensics_clone_sim:.2f}"
                    p1_t = (self.forensics_clone_sim - 0.75) / 0.24
                    p2_label = f"Min Detail {self.forensics_clone_detail:.1f}"
                    p2_t = (self.forensics_clone_detail - 2.0) / 28.0
                elif tool == "MAGNIFIER":
                    p1_label = f"Zoom {self.forensics_mag_zoom:d}x"
                    p1_t = (self.forensics_mag_zoom - 2) / 10.0
                    p2_label = "Move mouse over image"
                    p2_t = 0.0

                cv2.putText(display, p1_label, (int(0.38*win_w), int(0.835*win_h)), cv2.FONT_HERSHEY_SIMPLEX, 0.42, THEME["text_dim"], 1)
                self.draw_button(display, "-", (0.38 - btn_w - gap, btn_y, btn_w, btn_h), style="secondary")
                self.draw_button(display, "+", (0.62 + gap, btn_y, btn_w, btn_h), style="secondary")
                cv2.rectangle(display, (int(0.38*win_w), int(0.84*win_h)), (int(0.62*win_w), int(0.87*win_h)), THEME["bg_card"], -1)
                cv2.rectangle(display, (int(0.38*win_w), int(0.84*win_h)), (int(0.62*win_w), int(0.87*win_h)), THEME["border"], 1)
                cv2.circle(display, (int(0.38*win_w + np.clip(p1_t,0,1)*(0.24*win_w)), int(0.855*win_h)), 5, THEME["accent"], -1)

                cv2.putText(display, p2_label, (int(0.66*win_w), int(0.835*win_h)), cv2.FONT_HERSHEY_SIMPLEX, 0.42, THEME["text_dim"], 1)
                p2_enabled = p2_label not in ("N/A", "Move mouse over image")
                self.draw_button(display, "-", (0.66 - btn_w - gap, btn_y, btn_w, btn_h), style="secondary" if p2_enabled else "default")
                self.draw_button(display, "+", (0.90 + gap, btn_y, btn_w, btn_h), style="secondary" if p2_enabled else "default")
                cv2.rectangle(display, (int(0.66*win_w), int(0.84*win_h)), (int(0.90*win_w), int(0.87*win_h)), THEME["bg_card"], -1)
                cv2.rectangle(display, (int(0.66*win_w), int(0.84*win_h)), (int(0.90*win_w), int(0.87*win_h)), THEME["border"], 1)
                cv2.circle(display, (int(0.66*win_w + np.clip(p2_t,0,1)*(0.24*win_w)), int(0.855*win_h)), 5, THEME["accent"], -1)

                # Right-hand JPEG forensics panel (draggable + minimizable).
                if self.forensics_jpeg_panel_rect is None:
                    px1, py1 = int(0.64 * win_w), int(0.12 * win_h)
                    pw, ph = int(0.34 * win_w), int(0.70 * win_h)
                    self.forensics_jpeg_panel_rect = (px1, py1, px1 + pw, py1 + ph)

                panel_x1, panel_y1, panel_x2, panel_y2 = self.forensics_jpeg_panel_rect
                if self.forensics_jpeg_panel_minimized:
                    panel_y2 = panel_y1 + 36
                    self.forensics_jpeg_panel_rect = (panel_x1, panel_y1, panel_x2, panel_y2)
                cv2.rectangle(display, (panel_x1, panel_y1), (panel_x2, panel_y2), THEME["bg_card"], -1)
                cv2.rectangle(display, (panel_x1, panel_y1), (panel_x2, panel_y2), THEME["border"], 1)

                # Header with title and minimize box.
                cv2.putText(display, "JPEG Forensics", (panel_x1 + 14, panel_y1 + 26), cv2.FONT_HERSHEY_SIMPLEX, THEME["font_small"], THEME["accent"], 1)
                # Minimize toggle button (small square at top-right)
                cv2.rectangle(display, (panel_x2 - 24, panel_y1 + 8), (panel_x2 - 8, panel_y1 + 24), THEME["panel"], -1)
                symbol = "-" if not self.forensics_jpeg_panel_minimized else "+"
                cv2.putText(display, symbol, (panel_x2 - 20, panel_y1 + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, THEME["text_light"], 1)

                if not self.forensics_jpeg_panel_minimized:
                    ty = panel_y1 + 48
                    panel_h = panel_y2 - panel_y1
                    max_lines = int((panel_h - 150) / 16)
                    for i, line in enumerate(self.forensics_jpeg_lines[:max_lines]):
                        cv2.putText(display, line[:54], (panel_x1 + 14, ty + i * 16), cv2.FONT_HERSHEY_SIMPLEX, 0.40, THEME["text_dim"], 1)

                    # Thumbnail + diff preview if available.
                    box_y = panel_y2 - 120
                    if self.forensics_thumb is not None:
                        try:
                            thumb = cv2.resize(self.forensics_thumb, (90, 60), interpolation=cv2.INTER_AREA)
                            display[box_y:box_y+60, panel_x1+14:panel_x1+14+90] = thumb
                            cv2.rectangle(display, (panel_x1+14, box_y), (panel_x1+14+90, box_y+60), THEME["border"], 1)
                            cv2.putText(display, "Thumbnail", (panel_x1+14, box_y-6), cv2.FONT_HERSHEY_SIMPLEX, 0.38, THEME["text_muted"], 1)
                        except Exception:
                            pass
                    if self.forensics_thumb_diff is not None:
                        try:
                            diff = cv2.resize(self.forensics_thumb_diff, (90, 60), interpolation=cv2.INTER_AREA)
                            x0 = panel_x1 + 118
                            display[box_y:box_y+60, x0:x0+90] = diff
                            cv2.rectangle(display, (x0, box_y), (x0+90, box_y+60), THEME["border"], 1)
                            cv2.putText(display, "Thumb diff", (x0, box_y-6), cv2.FONT_HERSHEY_SIMPLEX, 0.38, THEME["text_muted"], 1)
                        except Exception:
                            pass

            if self.show_exif_hud and self.app_state in ["ANALYZE_PHOTO", "ANALYZE_VIDEO"]:
                # If OCR side panel is visible on the right, move metadata panel left to avoid overlap.
                ocr_side_visible = (
                    (self.app_state == "ANALYZE_PHOTO" and self.run_ocr and bool(self.ocr_boxes)) or
                    (self.app_state == "ANALYZE_VIDEO" and self.video_run_ocr and bool(self.ocr_boxes))
                )
                panel_x1 = 16 if ocr_side_visible else (win_w - 420)
                panel_y1 = 80
                panel_x2, panel_y2 = win_w-16, 580
                if ocr_side_visible:
                    panel_x2 = panel_x1 + 404
                self.copy_coords_rel = None
                self.nearby_rects = []
                cv2.rectangle(display, (panel_x1, panel_y1), (panel_x2, panel_y2), THEME["bg_card"], -1)
                cv2.rectangle(display, (panel_x1, panel_y1), (panel_x2, panel_y2), THEME["border"], 1)
                cv2.putText(display, "Metadata", (panel_x1+20, panel_y1+28), cv2.FONT_HERSHEY_SIMPLEX, THEME["font_body"], THEME["accent"], 1)
                text_y = panel_y1 + 56
                # Map card if GPS available
                if self.photo_gps and all(v is not None for v in self.photo_gps):
                    lat, lon = self.photo_gps
                    if self.photo_map_tile is None:
                        self.photo_map_tile = self._fetch_osm_tile(lat, lon, zoom=14)
                    if self.photo_map_tile is not None:
                        map_h, map_w = 140, 180
                        tile_resized = cv2.resize(self.photo_map_tile, (map_w, map_h))
                        mx1, my1 = panel_x1+16, text_y
                        mx2, my2 = mx1 + map_w, my1 + map_h
                        cv2.rectangle(display, (mx1-2, my1-2), (mx2+2, my2+2), THEME["border"], 1)
                        display[my1:my2, mx1:mx2] = tile_resized
                        # Day-in-the-life route polyline overlay on map card
                        if len(self.day_route_points) >= 2:
                            lats = [p["lat"] for p in self.day_route_points]
                            lons = [p["lon"] for p in self.day_route_points]
                            min_lat, max_lat = min(lats), max(lats)
                            min_lon, max_lon = min(lons), max(lons)
                            dlat = max(1e-6, max_lat - min_lat)
                            dlon = max(1e-6, max_lon - min_lon)
                            prev_pt = None
                            for p in self.day_route_points:
                                px = int(mx1 + ((p["lon"] - min_lon) / dlon) * (map_w - 1))
                                py = int(my2 - ((p["lat"] - min_lat) / dlat) * (map_h - 1))
                                if prev_pt is not None:
                                    cv2.line(display, prev_pt, (px, py), (255, 220, 80), 1)
                                prev_pt = (px, py)
                        cv2.putText(display, f"{lat:.5f},{lon:.5f}", (mx1, my2+18), cv2.FONT_HERSHEY_SIMPLEX, THEME["font_small"], THEME["text_dim"], 1)
                        # Copy coords button
                        self.copy_coords_rel = ((mx1 / win_w), ((my2 + 24) / win_h), 0.14, 0.04)
                        self.draw_button(display, "Copy coords", self.copy_coords_rel, bg=THEME["panel"])
                        text_y = my2 + 52
                # EXIF lines
                for i, line in enumerate(self.extracted_exif[:12]):
                    cv2.putText(display, line, (panel_x1+20, text_y + i*22), cv2.FONT_HERSHEY_SIMPLEX, THEME["font_small"], THEME["text_dim"], 1)
                # Nearby shots HUD
                if self.nearby_shots:
                    ny = text_y + 12 * 22 + 16
                    cv2.putText(display, "Nearby shots", (panel_x1+20, ny), cv2.FONT_HERSHEY_SIMPLEX, THEME["font_small"], THEME["accent"], 1)
                    for i, (dist_m, dt_min, name, path) in enumerate(self.nearby_shots[:3]):
                        row_y = ny + 20 + i*18
                        cv2.putText(display, f"{name[:20]}  {dist_m:.0f}m  {dt_min:.0f}m", (panel_x1+20, row_y), cv2.FONT_HERSHEY_SIMPLEX, 0.36, THEME["text_dim"], 1)
                        self.nearby_rects.append((panel_x1+16, row_y-14, 360, 16, path))

            if self.app_state not in ("MENU", "SETTINGS", "MEDIA_MENU"):
                titles = {"LIVE": "Live", "ANALYZE_PHOTO": "Photo", "ANALYZE_VIDEO": "Video", "ANALYZE_AUDIO": "Audio", "ANALYZE_TEXT": "Text", "FORENSICS": "Forensics"}
                self.draw_top_bar(display, titles.get(self.app_state, ""))
                if self.app_state == "LIVE" and self.cap and self.cap.isOpened():
                    bar_h = int(LAYOUT["top_bar"]["height"] * win_h)
                    dot_x, dot_y = int(win_w * 0.012), bar_h // 2
                    if (int(time.time() * 2) % 2) == 0:
                        cv2.circle(display, (dot_x, dot_y), 5, THEME["error"], -1)
                        cv2.circle(display, (dot_x, dot_y), 5, (255, 255, 255), 1)
                if self.recording: cv2.putText(display, "[REC]", (int(win_w*0.65), int(LAYOUT["top_bar"]["height"]*win_h*0.6)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, THEME["error"], 2)
            self._draw_image_controls(display)

            # Error banner — slim bar
            if self.error_message:
                bh = 32
                # Place banner below interactive bars so it never covers buttons.
                if self.app_state == "LIVE":
                    y0 = int((LAYOUT["live_toolbar"]["y"] + LAYOUT["live_toolbar"]["h"]) * win_h) + 6
                else:
                    y0 = int(LAYOUT["top_bar"]["height"] * win_h) + 6
                y1 = min(win_h - 2, y0 + bh)
                cv2.rectangle(display, (0, y0), (win_w, y1), (36, 28, 28), -1)
                cv2.line(display, (0, y1), (win_w, y1), THEME["error"], 1)
                cv2.putText(display, f"Error: {self.error_message[:78]}", (16, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, THEME["font_small"], THEME["error"], THEME["thickness"])

            if self.show_help:
                overlay = display.copy()
                cv2.rectangle(overlay, (0, 0), (win_w, win_h), THEME["bg_dark"], -1)
                display = cv2.addWeighted(overlay, 0.88, display, 0.12, 0)
                self.draw_card(display, (0.14, 0.10, 0.72, 0.78))
                cv2.putText(display, "HELP", (int(win_w*0.42), int(win_h*0.20)), cv2.FONT_HERSHEY_SIMPLEX, THEME["font_title"], THEME["accent"], THEME["thickness_heavy"])
                help_lines = [
                    "BACK — return to menu",
                    "Control Center — Skeleton, Emotion, Color; camera; export; AI confidence",
                    "Click on image — color picker",
                    "Press C — capture frame",
                ]
                for i, line in enumerate(help_lines):
                    cv2.putText(display, line, (int(win_w*0.20), int(win_h*0.30) + i * 36), cv2.FONT_HERSHEY_SIMPLEX, THEME["font_body"], THEME["text_dim"], THEME["thickness"])
                cv2.putText(display, "Click Help again to close", (int(win_w*0.20), int(win_h*0.30) + len(help_lines) * 36 + 12), cv2.FONT_HERSHEY_SIMPLEX, THEME["font_small"], THEME["text_muted"], THEME["thickness"])

            if self.flash_frames > 0: cv2.rectangle(display, (0,0), (win_w,win_h), (255,255,255), -1); self.flash_frames -= 1
        return display.copy()

    def run(self):
        """OpenCV event loop (used when use_qt=False). Use run_qt.py for PyQt6."""
        while True:
            display = self.paint_frame()
            cv2.imshow('CloutVision', display)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'): break
            if key == ord(' '): self.is_playing = not self.is_playing
            if key == ord('c') and self.app_state != "MENU": self.capture_media(display)
        self.close_all_media()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    CloutVision(use_qt=False).run()
