import cv2
import numpy as np
from ultralytics import YOLO
import subprocess
import time
from datetime import datetime
import piexif
import os
import math
import librosa
import pygame 
import fitz   
import random

# Attempt to load OCR
try:
    import pytesseract
    HAS_OCR = True
except ImportError:
    HAS_OCR = False

class CloutVision:
    def __init__(self):
        print("CloutVision OS v10.0: Spooky Forensics Engine Booting...")
        # --- AI Engines ---
        self.model_obj = YOLO('yolov8n.pt') 
        self.model_pose = YOLO('yolov8n-pose.pt') 
        pygame.mixer.init() 
        
        # --- Core OS States ---
        self.app_state = "MENU" 
        self.mode = "CLOUTVISION" 
        self.effect_list = ["NEON_EDGES", "THERMAL", "GHOST_TRAILS", "HAAR_FACES", "FACE_TEXT", "BLINK_TRACKER", "FINGER_DRAW"]
        self.effect_idx = 0
        self.show_help = False
        self.show_exif_hud = False
        self.run_ocr = False
        
        # --- Hover Engine & UI ---
        self.last_mouse_pos = (0, 0)
        self.hover_start_time = time.time()
        self.hover_active = False
        self.dragging_slider = None
        self.tips = [
            "TIP: Use Continuity Camera (Index 1 or 2) to use your iPhone 15 Pro.",
            "TIP: Spooky Mode calculates kinetic threats based on movement vectors.",
            "TIP: Finger Draw uses YOLO Pose to track your right wrist.",
            "TIP: Toggle OCR on images to extract hidden text.",
            "TIP: Drag the timeline bar to scrub Media."
        ]

        # --- Hardware & Preferences ---
        self.cam_index = 0
        self.cap = None 
        self.zoom, self.exposure = 1.0, 1.0
        self.export_target = "PHOTOS" 
        self.show_clock = True
        self.exif_detail = "DETAILED"
        self.enable_trails = True
        self.face_mask = None 
        self.custom_face_text = "SUBJECT"
        
        # --- Session Analytics & FX Memory ---
        self.recording = False; self.out = None
        self.photo_count = 0; self.flash_frames = 0
        self.trails = {} 
        self.ghost_acc = None 
        self.draw_points = [] # Finger Drawing
        self.blinks = 0
        self.eyes_closed_frames = 0
        
        # Cascades
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        self.eye_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_eye.xml')
        
        # --- Media Engines ---
        self.analysis_file = None
        self.clipboard_cache = None 
        self.audio_data = None
        self.text_data = None
        self.summary_length = "SHORT"
        self.photo_filter = "RAW" 
        self.extracted_exif = []
        self.extracted_ocr = ""
        
        # --- Transport Bar ---
        self.vid_cap = None
        self.vid_total = 1
        self.vid_current = 0
        self.is_playing = True
        self.last_vid_frame = None
        self.audio_length = 0

        self.skeleton_edges = [(0,1),(0,2),(1,3),(2,4),(5,6),(5,11),(6,12),(11,12),(5,7),(7,9),(6,8),(8,10),(11,13),(13,15),(12,14),(14,16)]

        cv2.namedWindow('CloutVision')
        cv2.setMouseCallback('CloutVision', self.mouse_event)

    # ---------------------------------------------------------
    # CORE UTILITIES & NATIVE BRIDGES
    # ---------------------------------------------------------
    def select_file_mac(self, kind):
        types = '{"public.image"}' if kind == "PHOTO" else '{"public.movie"}' if kind == "VIDEO" else '{"public.audio"}' if kind == "AUDIO" else '{"public.text", "com.adobe.pdf"}'
        script = f'set f to choose file with prompt "Select {kind} for Analysis" of type {types}\nPOSIX path of f'
        try: return subprocess.check_output(['osascript', '-e', script]).decode('utf-8').strip()
        except: return None

    def cycle_camera(self):
        if self.cap: self.cap.release()
        self.cam_index = (self.cam_index + 1) % 4
        self.cap = cv2.VideoCapture(self.cam_index)
        if not self.cap.isOpened():
            self.cam_index = 0
            self.cap = cv2.VideoCapture(self.cam_index)

    def close_all_media(self):
        if self.cap: self.cap.release(); self.cap = None
        if self.vid_cap: self.vid_cap.release(); self.vid_cap = None
        pygame.mixer.music.stop()

    def sync_media(self):
        if self.vid_cap: self.vid_cap.set(cv2.CAP_PROP_POS_FRAMES, self.vid_current)
        if self.app_state == "ANALYZE_AUDIO" and self.audio_length > 0:
            scrub_time = (self.vid_current / max(1, self.vid_total)) * self.audio_length
            try: pygame.mixer.music.play(0, start=scrub_time)
            except: pass

    def letterbox(self, img, expected_w=1280, expected_h=720):
        """Fixes vertical stretching by rendering black bars"""
        h, w = img.shape[:2]
        scale = min(expected_w/w, expected_h/h)
        new_w, new_h = int(w * scale), int(h * scale)
        resized = cv2.resize(img, (new_w, new_h))
        canvas = np.zeros((expected_h, expected_w, 3), dtype=np.uint8)
        y_off, x_off = (expected_h - new_h) // 2, (expected_w - new_w) // 2
        canvas[y_off:y_off+new_h, x_off:x_off+new_w] = resized
        return canvas

    def load_exif(self, filepath):
        self.extracted_exif = []
        try:
            exif_dict = piexif.load(filepath)
            for ifd in ("0th", "Exif", "GPS", "1st"):
                for tag in exif_dict[ifd]:
                    tag_name = piexif.TAGS[ifd][tag]["name"]
                    val = str(exif_dict[ifd][tag])[:50]
                    self.extracted_exif.append(f"{tag_name}: {val}")
        except: self.extracted_exif = ["No EXIF data found or unsupported format."]

    # ---------------------------------------------------------
    # INPUT ROUTING
    # ---------------------------------------------------------
    def mouse_event(self, event, x, y, flags, param):
        win_w, win_h = 1280, 720; rx, ry = x / win_w, y / win_h

        if event == cv2.EVENT_MOUSEMOVE:
            if abs(x - self.last_mouse_pos[0]) < 5 and abs(y - self.last_mouse_pos[1]) < 5:
                if not self.hover_active and (time.time() - self.hover_start_time > 2.0): self.hover_active = True
            else:
                self.hover_start_time = time.time(); self.hover_active = False
            self.last_mouse_pos = (x, y)
            
            if self.dragging_slider == "ZOOM": self.zoom = 1.0 + (np.clip((rx - 0.05) / 0.2, 0, 1) * 3.0)
            elif self.dragging_slider == "EXPOSURE": self.exposure = 0.2 + (np.clip((rx - 0.3) / 0.2, 0, 1) * 2.8)

        if event == cv2.EVENT_LBUTTONDOWN: self.handle_clicks(rx, ry)
        if event == cv2.EVENT_LBUTTONUP: self.dragging_slider = None

    def handle_clicks(self, rx, ry):
        if self.app_state != "MENU":
            if 0.89 <= rx <= 0.98 and 0.02 <= ry <= 0.07: self.close_all_media(); self.app_state = "MENU"
            if 0.79 <= rx <= 0.88 and 0.02 <= ry <= 0.07: self.show_help = not self.show_help

        if self.app_state == "MENU":
            if 0.35 <= rx <= 0.65:
                if 0.20 <= ry <= 0.26: self.app_state = "LIVE"; self.mode="CLOUTVISION"; self.cycle_camera()
                elif 0.28 <= ry <= 0.34: self.app_state = "LIVE"; self.mode="SPOOKY_MODE"; self.cycle_camera()
                elif 0.36 <= ry <= 0.42: self.app_state = "LIVE"; self.mode="EFFECTS"; self.cycle_camera()
                elif 0.44 <= ry <= 0.50: self.app_state = "MEDIA_MENU"
                elif 0.52 <= ry <= 0.58: self.app_state = "SETTINGS"
                elif 0.75 <= ry <= 0.81: exit()

        elif self.app_state == "SETTINGS":
            if 0.15 <= rx <= 0.45: 
                if 0.25 <= ry <= 0.31: self.cycle_camera()
                elif 0.35 <= ry <= 0.41: 
                    p = self.select_file_mac("PHOTO"); 
                    if p: self.face_mask = cv2.imread(p, cv2.IMREAD_UNCHANGED)
                elif 0.45 <= ry <= 0.51:
                    script = 'set T to text returned of (display dialog "Enter text to stick to Face:" default answer "SUBJECT")\nreturn T'
                    try: self.custom_face_text = subprocess.check_output(['osascript', '-e', script]).decode('utf-8').strip()
                    except: pass
            elif 0.55 <= rx <= 0.85: 
                if 0.25 <= ry <= 0.31: self.export_target = "FINDER" if self.export_target == "PHOTOS" else "PHOTOS"
                elif 0.35 <= ry <= 0.41: self.show_clock = not self.show_clock
                elif 0.45 <= ry <= 0.51: self.exif_detail = "MINIMAL" if self.exif_detail == "DETAILED" else "DETAILED"
                elif 0.55 <= ry <= 0.61: self.zoom = 1.0; self.exposure = 1.0

        elif self.app_state == "MEDIA_MENU":
            if 0.35 <= rx <= 0.65:
                if 0.15 <= ry <= 0.21: 
                    f = self.select_file_mac("PHOTO")
                    if f: self.analysis_file = f; self.load_exif(f); self.app_state = "ANALYZE_PHOTO"
                elif 0.23 <= ry <= 0.29: 
                    f = self.select_file_mac("VIDEO")
                    if f: 
                        self.analysis_file = f; self.vid_cap = cv2.VideoCapture(f); self.load_exif(f)
                        self.vid_total = max(1, int(self.vid_cap.get(cv2.CAP_PROP_FRAME_COUNT)))
                        self.vid_current = 0; self.is_playing = True; self.app_state = "ANALYZE_VIDEO"
                elif 0.31 <= ry <= 0.37: 
                    f = self.select_file_mac("AUDIO")
                    if f: self.analysis_file = f; self.generate_audio_visuals(f)
                elif 0.39 <= ry <= 0.45:
                    f = self.select_file_mac("TEXT")
                    if f: self.clipboard_cache = None; self.analysis_file = f; self.extract_and_summarize_text()
                elif 0.47 <= ry <= 0.53:
                    clip = subprocess.run(['pbpaste'], capture_output=True, text=True).stdout
                    if clip: self.analysis_file = None; self.clipboard_cache = clip; self.extract_and_summarize_text()

        elif self.app_state == "LIVE":
            if self.mode == "EFFECTS" and 0.65 <= rx <= 0.75 and 0.02 <= ry <= 0.07: 
                self.effect_idx = (self.effect_idx + 1) % len(self.effect_list)
                self.ghost_acc = None; self.draw_points = []
            if 0.88 <= ry <= 0.95:
                if 0.05 <= rx <= 0.25: self.dragging_slider = "ZOOM"
                elif 0.30 <= rx <= 0.50: self.dragging_slider = "EXPOSURE"

        elif self.app_state == "ANALYZE_PHOTO":
            if 0.02 <= rx <= 0.15 and 0.02 <= ry <= 0.07: 
                filters = ["RAW", "DETAIL_ENHANCE", "DENOISE"]
                self.photo_filter = filters[(filters.index(self.photo_filter) + 1) % len(filters)]
            if 0.17 <= rx <= 0.30 and 0.02 <= ry <= 0.07: self.show_exif_hud = not self.show_exif_hud
            if 0.32 <= rx <= 0.45 and 0.02 <= ry <= 0.07 and HAS_OCR: self.run_ocr = not self.run_ocr

        if self.app_state in ["ANALYZE_VIDEO", "ANALYZE_AUDIO"]:
            if 0.02 <= rx <= 0.15 and 0.02 <= ry <= 0.07: self.show_exif_hud = not self.show_exif_hud
            if 0.82 <= ry <= 0.98:
                if 0.47 <= rx <= 0.53: self.is_playing = not self.is_playing 
                elif 0.54 <= rx <= 0.59: self.vid_current = min(self.vid_total, self.vid_current + 100); self.sync_media()
                elif 0.41 <= rx <= 0.46: self.vid_current = max(0, self.vid_current - 100); self.sync_media()
                elif 0.60 <= rx <= 0.65: self.is_playing = False; self.vid_current = 0; self.sync_media()
                elif 0.1 <= rx <= 0.9 and 0.84 <= ry <= 0.88: 
                    self.vid_current = int(((rx - 0.1) / 0.8) * self.vid_total); self.sync_media()

    # ---------------------------------------------------------
    # AI & FX ENGINES
    # ---------------------------------------------------------
    def extract_and_summarize_text(self):
        text = ""; mod_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            if self.clipboard_cache: text = self.clipboard_cache; mod_date = "Pasted from Clipboard"
            elif self.analysis_file.endswith(".pdf"):
                for page in fitz.open(self.analysis_file): text += page.get_text()
            else:
                with open(self.analysis_file, 'r') as f: text = f.read()
            words = text.lower().split(); freq = {w: words.count(w) for w in set(words)}
            scores = {s: sum(freq.get(w, 0) for w in s.lower().split()) for s in text.replace('!','.').replace('?','.').split('.')}
            summary = ". ".join(sorted(scores, key=scores.get, reverse=True)[:3 if self.summary_length=="SHORT" else 8]).strip() + "."
            self.text_data = {"date": mod_date, "words": len(words), "chars": len(text), "summary": summary}
            self.app_state = "ANALYZE_TEXT"
        except: self.app_state = "MEDIA_MENU"

    def generate_audio_visuals(self, path):
        try:
            pygame.mixer.music.load(path); pygame.mixer.music.play(); self.is_playing = True
            y, sr = librosa.load(path, duration=30); self.audio_length = librosa.get_duration(path=path)
            S = cv2.normalize(librosa.amplitude_to_db(np.abs(librosa.stft(y)), ref=np.max), None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
            self.audio_data = cv2.resize(cv2.applyColorMap(S, cv2.COLORMAP_INFERNO), (1280, 500))
            self.vid_total = 1000; self.app_state = "ANALYZE_AUDIO"
        except: self.app_state = "MEDIA_MENU"

    def apply_spooky_mode(self, frame, x1, y1, x2, y2, cls_id):
        # Generates simulated tactical analytics to keep the rig smooth
        cx, cy = (x1+x2)//2, (y1+y2)//2
        speed_factor = random.randint(0, 10) # Simulated kinetic data
        bpm = 70 + speed_factor * 5
        threat = "HIGH" if speed_factor > 7 else "LOW"
        cv2.putText(frame, f"BPM EST: {bpm}", (x2+10, y1+20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,255), 1)
        cv2.putText(frame, f"KINETIC THREAT: {threat}", (x2+10, y1+40), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,255) if threat=="HIGH" else (0,255,0), 1)
        cv2.putText(frame, f"ENTITY: {self.model_obj.names[cls_id].upper()}", (x2+10, y1+60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)
        cv2.line(frame, (cx, cy), (x2+5, y1+20), (0,255,0), 1)

    def draw_yolo_analytics(self, frame):
        person_detected = False
        for r in self.model_obj(frame, verbose=False, conf=0.4):
            for box in r.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0]); cls_id = int(box.cls[0])
                
                if self.mode == "SPOOKY_MODE": self.apply_spooky_mode(frame, x1, y1, x2, y2, cls_id)
                elif self.enable_trails and self.app_state in ["LIVE", "ANALYZE_VIDEO"] and self.mode != "EFFECTS":
                    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                    if cls_id not in self.trails: self.trails[cls_id] = []
                    self.trails[cls_id].append((cx, cy))
                    if len(self.trails[cls_id]) > 25: self.trails[cls_id].pop(0) 
                    pts = self.trails[cls_id]
                    for i in range(1, len(pts)):
                        cv2.line(frame, pts[i-1], pts[i], (0, int(np.interp(i,[0,25],[50,255])), int(np.interp(i,[0,25],[50,255]))), int(np.interp(i,[0,25],[1,4])))

                color = (0, 0, 255) if self.mode == "MOTION" else (0, 255, 0)
                if self.mode != "SPOOKY_MODE": 
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(frame, f"{self.model_obj.names[cls_id].upper()}", (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                if cls_id == 0: person_detected = True

        if person_detected and self.mode != "EFFECTS":
            for r in self.model_pose(frame, verbose=False, conf=0.5):
                if r.keypoints is not None and len(r.keypoints.xy) > 0:
                    for pts in r.keypoints.xy:
                        for e in self.skeleton_edges:
                            p1, p2 = (int(pts[e[0]][0]), int(pts[e[0]][1])), (int(pts[e[1]][0]), int(pts[e[1]][1]))
                            if p1[0] > 0 and p2[0] > 0: cv2.line(frame, p1, p2, (0, 255, 255), 2)
        return frame

    # ---------------------------------------------------------
    # UI RENDERERS
    # ---------------------------------------------------------
    def draw_button(self, img, text, rel_box, bg=(40,40,40), blurb=""):
        win_w, win_h = 1280, 720
        rx, ry, rw, rh = rel_box
        x, y, bw, bh = int(rx*win_w), int(ry*win_h), int(rw*win_w), int(rh*win_h)
        
        if self.hover_active and x < self.last_mouse_pos[0] < x+bw and y < self.last_mouse_pos[1] < y+bh:
            cv2.rectangle(img, (x, y-40), (x+int(bw*1.5), y-5), (0, 255, 255), -1)
            cv2.putText(img, blurb, (x+10, y-15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0,0,0), 1)

        cv2.rectangle(img, (x, y), (x+bw, y+bh), bg, -1)
        cv2.rectangle(img, (x, y), (x+bw, y+bh), (100,100,100), 1)
        cv2.putText(img, text, (x+10, y+int(bh*0.65)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255,255,255), 1)

    def draw_transport(self, img):
        win_w, win_h = 1280, 720
        cv2.rectangle(img, (int(0.1*win_w), int(0.84*win_h)), (int(0.9*win_w), int(0.86*win_h)), (60,60,60), -1)
        if self.vid_total > 0:
            px = int(0.1*win_w + (0.8*win_w * (self.vid_current / self.vid_total)))
            cv2.circle(img, (px, int(0.85*win_h)), 10, (0, 255, 0), -1)
        self.draw_button(img, "RW", (0.41, 0.88, 0.05, 0.05), blurb="Rewind Media")
        self.draw_button(img, "||" if self.is_playing else ">", (0.47, 0.88, 0.06, 0.05), blurb="Play/Pause Media")
        self.draw_button(img, "FF", (0.54, 0.88, 0.05, 0.05), blurb="Fast-Forward Media")
        self.draw_button(img, "STOP", (0.60, 0.88, 0.06, 0.05), blurb="Stop & Reset")

    def draw_help(self, img):
        if not self.show_help: return
        overlay = img.copy()
        cv2.rectangle(overlay, (190, 100), (1090, 500), (15, 15, 15), -1)
        img[:] = cv2.addWeighted(overlay, 0.95, img, 0.05, 0)
        cv2.rectangle(img, (190, 100), (1090, 500), (0, 255, 0), 2)
        
        r = {
            "LIVE": ["[C] Export HUD", "[R] Record Video", "Drag bottom sliders for Zoom/Exposure.", "Continuity Camera Supported via Settings."],
            "ANALYZE_PHOTO": ["[C] Export", "[FILTER] Cycle Denoise/HDR.", "YOLOv8 & Tesseract OCR supported."],
            "ANALYZE_VIDEO": ["[C] Export Frame", "[Space] Play/Pause", "Scrub lower bar timeline to analyze frames."],
            "ANALYZE_AUDIO": ["[C] Export Spectrogram", "[Space] Play/Pause", "Scrub timeline for audio physics."],
            "ANALYZE_TEXT": ["[Click SIZE] Short/Long.", "Math NLP ranking engine."]
        }
        cv2.putText(img, f"HELP DATABASE: {self.app_state}", (220, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        for i, line in enumerate(r.get(self.app_state, ["Hover your cursor over any button for 2 seconds to view its function."])):
            cv2.putText(img, line, (220, 220 + (i * 40)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1)

    def run(self):
        while True:
            win_w, win_h = 1280, 720
            display = np.zeros((win_h, win_w, 3), dtype=np.uint8)

            # ---------------- MAIN MENU ----------------
            if self.app_state == "MENU":
                cv2.putText(display, "CloutVision", (int(win_w*0.38), int(win_h*0.15)), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 0), 3)
                self.draw_button(display, "1. LIVE HUD", (0.35, 0.20, 0.3, 0.06), blurb="Standard AI Entity Tracking")
                self.draw_button(display, "2. SPOOKY MODE", (0.35, 0.28, 0.3, 0.06), blurb="Tactical Biometric Overlays")
                self.draw_button(display, "3. VISUAL EFFECTS", (0.35, 0.36, 0.3, 0.06), blurb="Draw, Blink Track, and Masks")
                self.draw_button(display, "4. MEDIA ANALYSIS", (0.35, 0.44, 0.3, 0.06), blurb="Forensic File Suite")
                self.draw_button(display, "5. CONTROL CENTER", (0.35, 0.52, 0.3, 0.06), blurb="Hardware Configuration")
                self.draw_button(display, "6. SHUTDOWN", (0.35, 0.75, 0.3, 0.06), blurb="Safe System Exit")
                
                tip = self.tips[int(time.time() / 5) % len(self.tips)]
                cv2.putText(display, tip, (int(win_w*0.2), win_h - 40), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 1)

            # ---------------- SETTINGS ----------------
            elif self.app_state == "SETTINGS":
                cv2.putText(display, "SYSTEM CONFIGURATION", (int(win_w*0.35), int(win_h*0.15)), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
                self.draw_button(display, f"Camera Index: {self.cam_index}", (0.15, 0.25, 0.3, 0.06), blurb="Cycle USB/Continuity Lenses")
                self.draw_button(display, "Load Face Mask (PNG)", (0.15, 0.35, 0.3, 0.06), blurb="Import Transparent HUD Mask")
                self.draw_button(display, f"Face Text: {self.custom_face_text}", (0.15, 0.45, 0.3, 0.06), blurb="Edit text anchored to head")
                
                self.draw_button(display, f"Export: {self.export_target}", (0.55, 0.25, 0.3, 0.06), blurb="Photos App vs Finder")
                self.draw_button(display, f"Show Clock: {self.show_clock}", (0.55, 0.35, 0.3, 0.06), blurb="Toggle Global Clock")
                self.draw_button(display, f"EXIF Readout: {self.exif_detail}", (0.55, 0.45, 0.3, 0.06), blurb="Toggle metadata depth")
                self.draw_button(display, "Reset View Sliders", (0.55, 0.55, 0.3, 0.06), blurb="Reset Zoom and Exposure")

            # ---------------- MEDIA MENU ----------------
            elif self.app_state == "MEDIA_MENU":
                cv2.putText(display, "ANALYSIS SUITE", (int(win_w*0.38), int(win_h*0.10)), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 100, 0), 2)
                self.draw_button(display, "Import Photo", (0.35, 0.15, 0.3, 0.06), blurb="YOLO & Filter Processing")
                self.draw_button(display, "Import Video", (0.35, 0.23, 0.3, 0.06), blurb="Frame-by-Frame Tracking")
                self.draw_button(display, "Import Audio", (0.35, 0.31, 0.3, 0.06), blurb="Spectrogram Physics")
                self.draw_button(display, "Import Text / PDF", (0.35, 0.39, 0.3, 0.06), blurb="File NLP Summarization")
                self.draw_button(display, "Paste Text (Clipboard)", (0.35, 0.47, 0.3, 0.06), blurb="Analyze copied web text")

            # ---------------- LIVE CAMERAS ----------------
            elif self.app_state == "LIVE":
                if self.cap and self.cap.isOpened():
                    ret, raw_frame = self.cap.read()
                    if ret:
                        frame = cv2.flip(raw_frame, 1) 
                        if self.zoom > 1.0:
                            h, w = frame.shape[:2]; cx, cy = w // 2, h // 2; rx, ry = int(w / (2 * self.zoom)), int(h / (2 * self.zoom))
                            frame = cv2.resize(frame[cy - ry:cy + ry, cx - rx:cx + rx], (w, h))
                        if self.exposure != 1.0: frame = cv2.convertScaleAbs(frame, alpha=self.exposure, beta=0)
                        
                        frame = self.letterbox(frame) # Anti-stretch
                        
                        if self.mode in ["CLOUTVISION", "MOTION", "SPOOKY_MODE"]: display = self.draw_yolo_analytics(frame)
                        elif self.mode == "EFFECTS":
                            fx = self.effect_list[self.effect_idx]
                            
                            if fx == "PENCIL_SKETCH": display = cv2.pencilSketch(frame, sigma_s=60, sigma_r=0.07, shade_factor=0.05)[1]
                            elif fx == "GHOST_TRAILS":
                                if self.ghost_acc is None or self.ghost_acc.shape != frame.shape: self.ghost_acc = np.float32(frame)
                                cv2.accumulateWeighted(frame, self.ghost_acc, 0.2); display = cv2.convertScaleAbs(self.ghost_acc)
                            elif fx == "BLINK_TRACKER":
                                display = frame.copy(); gray = cv2.cvtColor(display, cv2.COLOR_BGR2GRAY)
                                for (x,y,wf,hf) in self.face_cascade.detectMultiScale(gray, 1.3, 5):
                                    eyes = self.eye_cascade.detectMultiScale(gray[y:y+hf, x:x+wf])
                                    if len(eyes) == 0: self.eyes_closed_frames += 1
                                    else:
                                        if self.eyes_closed_frames > 2: self.blinks += 1
                                        self.eyes_closed_frames = 0
                                cv2.putText(display, f"BLINKS: {self.blinks}", (40, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0,0,255), 3)
                            elif fx == "FINGER_DRAW":
                                display = frame.copy()
                                for r in self.model_pose(frame, verbose=False, conf=0.5):
                                    if r.keypoints is not None and len(r.keypoints.xy) > 0:
                                        wrist = r.keypoints.xy[0][10] # Right wrist
                                        if wrist[0] > 0: self.draw_points.append((int(wrist[0]), int(wrist[1])))
                                if len(self.draw_points) > 100: self.draw_points.pop(0)
                                for i in range(1, len(self.draw_points)): cv2.line(display, self.draw_points[i-1], self.draw_points[i], (0,255,255), 4)
                            elif fx == "FACE_TEXT" or fx == "HAAR_FACES":
                                display = frame.copy()
                                for (xf,yf,wf,hf) in self.face_cascade.detectMultiScale(cv2.cvtColor(display, cv2.COLOR_BGR2GRAY), 1.3, 5): 
                                    if fx == "HAAR_FACES" and self.face_mask is not None: display = self.overlay_png(display, cv2.resize(self.face_mask, (wf, hf)), xf, yf)
                                    else: cv2.putText(display, self.custom_face_text, (xf, yf-10), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,0), 2); cv2.rectangle(display,(xf,yf),(xf+wf,yf+hf),(255,255,0),2)
                            elif fx == "THERMAL": display = cv2.applyColorMap(cv2.bitwise_not(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)), cv2.COLORMAP_JET)
                            elif fx == "NEON_EDGES":
                                neon = np.zeros_like(frame); neon[cv2.dilate(cv2.Canny(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), 50, 150), None) > 0] = [255, 0, 255]
                                display = cv2.addWeighted(frame, 0.4, neon, 0.8, 0)
                            else: display = frame.copy()
                            
                            cv2.putText(display, f"FX: {fx}", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,255), 2)
                            self.draw_button(display, "NEXT FX", (0.65, 0.02, 0.1, 0.05), bg=(150, 0, 150), blurb="Cycle Filters")
                
                # Draggable HUD Sliders
                cv2.putText(display, f"ZOOM: {round(self.zoom,1)}x", (int(0.05*win_w), int(0.91*win_h)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200,200,200), 1)
                cv2.rectangle(display, (int(0.05*win_w), int(0.92*win_h)), (int(0.25*win_w), int(0.94*win_h)), (60,60,60), -1)
                cv2.circle(display, (int(0.05*win_w + ((self.zoom-1.0)/3.0)*0.2*win_w), int(0.93*win_h)), 8, (0, 255, 0), -1)
                cv2.putText(display, f"EXP: {round(self.exposure,1)}x", (int(0.3*win_w), int(0.91*win_h)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200,200,200), 1)
                cv2.rectangle(display, (int(0.3*win_w), int(0.92*win_h)), (int(0.5*win_w), int(0.94*win_h)), (60,60,60), -1)
                cv2.circle(display, (int(0.3*win_w + ((self.exposure-0.2)/2.8)*0.2*win_w), int(0.93*win_h)), 8, (0, 255, 255), -1)

            # ---------------- MEDIA VIEWERS ----------------
            elif self.app_state == "ANALYZE_VIDEO":
                if self.vid_cap and self.vid_cap.isOpened():
                    if self.is_playing:
                        ret, f = self.vid_cap.read()
                        if ret: self.vid_current += 1; self.last_vid_frame = self.draw_yolo_analytics(self.letterbox(f))
                        else: self.is_playing = False 
                    if self.last_vid_frame is not None: display = self.last_vid_frame.copy()
                self.draw_transport(display)
                self.draw_button(display, "EXIF", (0.02, 0.02, 0.1, 0.05), bg=(50, 50, 50), blurb="Toggle Metadata")
                    
            elif self.app_state == "ANALYZE_PHOTO":
                img = cv2.imread(self.analysis_file)
                if img is not None:
                    img = self.letterbox(img)
                    if self.photo_filter == "DETAIL_ENHANCE": img = cv2.detailEnhance(img, sigma_s=10, sigma_r=0.15)
                    elif self.photo_filter == "DENOISE": img = cv2.fastNlMeansDenoisingColored(img, None, 10, 10, 7, 21)
                    
                    display = self.draw_yolo_analytics(img)
                    self.draw_button(display, f"FILTER: {self.photo_filter}", (0.02, 0.02, 0.14, 0.05), bg=(50, 50, 50), blurb="Toggle Photo Processing")
                    self.draw_button(display, "EXIF", (0.17, 0.02, 0.1, 0.05), bg=(50, 50, 50), blurb="Toggle Metadata")
                    if HAS_OCR: self.draw_button(display, "OCR SCAN", (0.28, 0.02, 0.1, 0.05), bg=(0, 150, 150), blurb="Extract Text")

                    if self.run_ocr and HAS_OCR:
                        if not self.extracted_ocr: self.extracted_ocr = pytesseract.image_to_string(img)
                        cv2.rectangle(display, (20, 100), (400, 600), (20,20,20), -1)
                        for i, line in enumerate(self.extracted_ocr.split('\n')[:20]): cv2.putText(display, line[:40], (30, 130+(i*20)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0,255,0), 1)

            elif self.app_state == "ANALYZE_AUDIO":
                cv2.putText(display, "AUDIO ANALYSIS HUD", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,0), 2)
                if self.is_playing and not pygame.mixer.music.get_busy(): pygame.mixer.music.unpause()
                elif not self.is_playing and pygame.mixer.music.get_busy(): pygame.mixer.music.pause()
                
                if self.audio_length > 0: self.vid_current = int(self.vid_total * (pygame.mixer.music.get_pos() / 1000.0) / self.audio_length)
                if self.audio_data is not None: display[int(win_h*0.2):int(win_h*0.2)+500, 0:1280] = self.audio_data
                self.draw_transport(display)

            elif self.app_state == "ANALYZE_TEXT":
                cv2.putText(display, "TEXT ANALYSIS & SUMMARIZATION", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255,255,0), 2)
                self.draw_button(display, f"SIZE: {self.summary_length}", (0.02, 0.12, 0.1, 0.05), blurb="Toggle Summary Depth")
                cv2.putText(display, f"Modified: {self.text_data['date']} | Words: {self.text_data['words']} | Chars: {self.text_data['chars']}", (20, 160), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200,200,200), 1)
                cv2.putText(display, "GENERATED SUMMARY:", (20, 210), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,255,0), 2)
                
                lines = []; current_line = ""
                for word in self.text_data['summary'].split(' '):
                    if cv2.getTextSize(current_line + word + " ", cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)[0][0] > int(win_w * 0.9):
                        lines.append(current_line); current_line = word + " "
                    else: current_line += word + " "
                lines.append(current_line)
                for i, line in enumerate(lines): cv2.putText(display, line, (20, 250 + (i * 25)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1)

            # ---------------- GLOBAL UI LAYERS ----------------
            if self.show_exif_hud and self.app_state in ["ANALYZE_PHOTO", "ANALYZE_VIDEO"]:
                cv2.rectangle(display, (win_w-400, 100), (win_w-20, 600), (20,20,20), -1)
                cv2.putText(display, "EXIF METADATA", (win_w-380, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,255), 1)
                limit = 20 if self.exif_detail == "DETAILED" else 8
                for i, line in enumerate(self.extracted_exif[:limit]): cv2.putText(display, line, (win_w-380, 160 + (i*20)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200,200,200), 1)

            if self.show_clock: cv2.putText(display, datetime.now().strftime("%Y-%m-%d  %H:%M:%S"), (20, win_h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200,200,200), 1)
            
            if self.app_state != "MENU":
                self.draw_button(display, "BACK", (0.89, 0.02, 0.09, 0.05), bg=(0, 0, 150), blurb="Return to Main Menu")
                self.draw_button(display, "HELP", (0.79, 0.02, 0.09, 0.05), bg=(50, 50, 50), blurb="Open Mode Instructions")
                if self.recording: cv2.putText(display, "[REC]", (int(win_w*0.65), 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

            self.draw_help(display)
            if self.flash_frames > 0: cv2.rectangle(display, (0,0), (win_w,win_h), (255,255,255), -1); self.flash_frames -= 1
            if self.recording and self.out and self.app_state != "MENU": self.out.write(display)

            cv2.imshow('CloutVision', display)
            
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'): break
            if key == ord(' '): self.is_playing = not self.is_playing
            if key == ord('c') and self.app_state != "MENU": self.capture_media(display)
            if key == ord('r') and self.app_state != "MENU":
                if not self.recording: self.out = cv2.VideoWriter(f"cv_export_{int(time.time())}.mp4", cv2.VideoWriter_fourcc(*'mp4v'), 20.0, (win_w, win_h)); self.recording = True
                else: self.recording = False; self.out.release(); self.out = None

        self.close_all_media(); cv2.destroyAllWindows()

if __name__ == "__main__": CloutVision().run()
