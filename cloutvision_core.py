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

class CloutVision:
    def __init__(self):
        print("CloutVision OS: Booting Stable 1280x720 Engine...")
        # --- AI Engines ---
        self.model_obj = YOLO('yolov8n.pt') 
        self.model_pose = YOLO('yolov8n-pose.pt') 
        pygame.mixer.init() 
        
        # --- Core OS States ---
        self.app_state = "MENU" 
        self.mode = "CLOUTVISION" 
        self.effect_list = ["NEON_EDGES", "THERMAL", "CHROMATIC_GLITCH", "NIGHT_VISION", "PENCIL_SKETCH", "WATERCOLOR", "GHOST_TRAILS", "HAAR_FACES"]
        self.effect_idx = 0
        self.show_help = False
        
        # --- Hover Engine Memory ---
        self.last_mouse_pos = (0, 0)
        self.hover_start_time = time.time()
        self.hover_active = False
        self.dragging_slider = None

        # --- Hardware & Settings ---
        self.cam_index = 0
        self.cap = None 
        self.zoom, self.exposure = 1.0, 1.0
        self.export_target = "PHOTOS" 
        self.show_clock = True
        self.exif_detail = "DETAILED"
        self.enable_trails = True
        
        # --- Session Analytics ---
        self.recording = False
        self.out = None
        self.photo_count = 0
        self.video_count = 0
        self.flash_frames = 0
        self.trails = {} 
        self.ghost_acc = None 
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        self.face_mask = None 
        
        # --- Media Engines ---
        self.analysis_file = None
        self.clipboard_cache = None 
        self.audio_data = None
        self.text_data = None
        self.summary_length = "SHORT"
        self.photo_filter = "RAW" 
        
        # --- Video Scrubbing Engine ---
        self.vid_cap = None
        self.vid_total = 1
        self.vid_current = 0
        self.is_playing = True
        self.last_vid_frame = None
        self.audio_length = 0

        self.skeleton_edges = [
            (0, 1), (0, 2), (1, 3), (2, 4), (5, 6), (5, 11), (6, 12), (11, 12),
            (5, 7), (7, 9), (6, 8), (8, 10), (11, 13), (13, 15), (12, 14), (14, 16)
        ]

        # --- Fixed Window Setup ---
        cv2.namedWindow('CloutVision')
        cv2.setMouseCallback('CloutVision', self.mouse_event)

    # ---------------------------------------------------------
    # UTILITY FUNCTIONS
    # ---------------------------------------------------------
    def select_file_mac(self, kind):
        types = '{"public.image"}' if kind == "PHOTO" else '{"public.movie"}' if kind == "VIDEO" else '{"public.audio"}' if kind == "AUDIO" else '{"public.text", "com.adobe.pdf"}'
        script = f'set f to choose file with prompt "Select {kind} for Analysis" of type {types}\nPOSIX path of f'
        try: return subprocess.check_output(['osascript', '-e', script]).decode('utf-8').strip()
        except: return None

    def close_all_media(self):
        if self.cap: self.cap.release(); self.cap = None
        if self.vid_cap: self.vid_cap.release(); self.vid_cap = None
        pygame.mixer.music.stop()

    def sync_media(self):
        if self.vid_cap: self.vid_cap.set(cv2.CAP_PROP_POS_FRAMES, self.vid_current)
        if self.app_state == "ANALYZE_AUDIO" and self.audio_length > 0:
            pct = self.vid_current / max(1, self.vid_total)
            pygame.mixer.music.set_pos(pct * self.audio_length)

    def capture_media(self, display_frame):
        self.photo_count += 1
        abs_path = os.path.abspath(f"cv_export_{int(time.time())}.jpg")
        cv2.imwrite(abs_path, display_frame) 
        piexif.insert(piexif.dump({"0th": {piexif.ImageIFD.Software: b"CloutVision Core"}, 
                                   "Exif": {piexif.ExifIFD.DateTimeOriginal: datetime.now().strftime("%Y:%m:%d %H:%M:%S").encode('utf-8')}}), abs_path)
        if self.export_target == "PHOTOS": subprocess.run(["osascript", "-e", f'tell application "Photos" to import POSIX file "{abs_path}"'])
        else: subprocess.run(["open", "-R", abs_path])
        self.flash_frames = 3

    # ---------------------------------------------------------
    # INPUT & EVENT ROUTING
    # ---------------------------------------------------------
    def mouse_event(self, event, x, y, flags, param):
        # Fixed 1280x720 scaling logic for stability
        win_w, win_h = 1280, 720
        rx, ry = x / win_w, y / win_h

        if event == cv2.EVENT_MOUSEMOVE:
            # 2-Second Hover Engine
            if abs(x - self.last_mouse_pos[0]) < 5 and abs(y - self.last_mouse_pos[1]) < 5:
                if not self.hover_active and (time.time() - self.hover_start_time > 2.0): self.hover_active = True
            else:
                self.hover_start_time = time.time(); self.hover_active = False
            self.last_mouse_pos = (x, y)
            
            # Slider Drag Logic
            if self.dragging_slider == "ZOOM": self.zoom = 1.0 + (np.clip((rx - 0.05) / 0.2, 0, 1) * 3.0)
            elif self.dragging_slider == "EXPOSURE": self.exposure = 0.2 + (np.clip((rx - 0.3) / 0.2, 0, 1) * 2.8)

        if event == cv2.EVENT_LBUTTONDOWN: self.handle_clicks(rx, ry)
        if event == cv2.EVENT_LBUTTONUP: self.dragging_slider = None

    def handle_clicks(self, rx, ry):
        # 1. Global Buttons (Available on EVERY page except Menu)
        if self.app_state != "MENU":
            if 0.89 <= rx <= 0.98 and 0.02 <= ry <= 0.07: self.close_all_media(); self.app_state = "MENU" # BACK
            if 0.79 <= rx <= 0.88 and 0.02 <= ry <= 0.07: self.show_help = not self.show_help # HELP

        # 2. Main Menu
        if self.app_state == "MENU":
            if 0.35 <= rx <= 0.65:
                if 0.20 <= ry <= 0.26: self.app_state = "LIVE"; self.mode = "CLOUTVISION"; self.cap = cv2.VideoCapture(self.cam_index)
                elif 0.28 <= ry <= 0.34: self.app_state = "LIVE"; self.mode = "MOTION"; self.cap = cv2.VideoCapture(self.cam_index)
                elif 0.36 <= ry <= 0.42: self.app_state = "LIVE"; self.mode = "EFFECTS"; self.cap = cv2.VideoCapture(self.cam_index)
                elif 0.44 <= ry <= 0.50: self.app_state = "MEDIA_MENU"
                elif 0.52 <= ry <= 0.58: self.app_state = "SETTINGS"
                elif 0.75 <= ry <= 0.81: exit()

        # 3. Settings Center
        elif self.app_state == "SETTINGS":
            if 0.15 <= rx <= 0.45: # Left Column
                if 0.25 <= ry <= 0.31: self.cam_index = (self.cam_index + 1) % 3
                elif 0.35 <= ry <= 0.41: 
                    p = self.select_file_mac("PHOTO")
                    if p: self.face_mask = cv2.imread(p, cv2.IMREAD_UNCHANGED)
            elif 0.55 <= rx <= 0.85: # Right Column
                if 0.25 <= ry <= 0.31: self.export_target = "FINDER" if self.export_target == "PHOTOS" else "PHOTOS"
                elif 0.35 <= ry <= 0.41: self.show_clock = not self.show_clock
                elif 0.45 <= ry <= 0.51: self.enable_trails = not self.enable_trails
                elif 0.55 <= ry <= 0.61: self.zoom = 1.0; self.exposure = 1.0

        # 4. Media Analysis Suite
        elif self.app_state == "MEDIA_MENU":
            if 0.35 <= rx <= 0.65:
                if 0.15 <= ry <= 0.21: 
                    f = self.select_file_mac("PHOTO")
                    if f: self.analysis_file = f; self.photo_filter = "RAW"; self.app_state = "ANALYZE_PHOTO"
                elif 0.23 <= ry <= 0.29: 
                    f = self.select_file_mac("VIDEO")
                    if f: 
                        self.analysis_file = f; self.vid_cap = cv2.VideoCapture(f)
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
                    if clip and len(clip.strip()) > 0:
                        self.analysis_file = None; self.clipboard_cache = clip; self.extract_and_summarize_text()

        # 5. Live HUD Sliders
        elif self.app_state == "LIVE":
            if self.mode == "EFFECTS" and 0.65 <= rx <= 0.75 and 0.02 <= ry <= 0.07: 
                self.effect_idx = (self.effect_idx + 1) % len(self.effect_list); self.ghost_acc = None
            if 0.88 <= ry <= 0.95:
                if 0.05 <= rx <= 0.25: self.dragging_slider = "ZOOM"
                elif 0.30 <= rx <= 0.50: self.dragging_slider = "EXPOSURE"

        elif self.app_state == "ANALYZE_PHOTO":
            if 0.02 <= rx <= 0.22 and 0.02 <= ry <= 0.07: # Filter Toggle
                filters = ["RAW", "DETAIL_ENHANCE", "DENOISE"]
                self.photo_filter = filters[(filters.index(self.photo_filter) + 1) % len(filters)]

        elif self.app_state == "ANALYZE_TEXT":
            if 0.02 <= rx <= 0.15 and 0.12 <= ry <= 0.17: # Size Toggle
                self.summary_length = "LONG" if self.summary_length == "SHORT" else "SHORT"
                self.extract_and_summarize_text() 

        # 6. Transport Controls (Lower Third Logic)
        if self.app_state in ["ANALYZE_VIDEO", "ANALYZE_AUDIO"]:
            if 0.82 <= ry <= 0.98:
                if 0.47 <= rx <= 0.53: self.is_playing = not self.is_playing # Play/Pause
                elif 0.54 <= rx <= 0.59: self.vid_current = min(self.vid_total, self.vid_current + 100); self.sync_media() # FF
                elif 0.41 <= rx <= 0.46: self.vid_current = max(0, self.vid_current - 100); self.sync_media() # RW
                elif 0.60 <= rx <= 0.65: self.is_playing = False; self.vid_current = 0; self.sync_media() # STOP
                elif 0.1 <= rx <= 0.9 and 0.84 <= ry <= 0.88: # Linear Scrubber Bar
                    self.vid_current = int(((rx - 0.1) / 0.8) * self.vid_total); self.sync_media()

    # ---------------------------------------------------------
    # HEAVY ENGINES (NLP, Audio, Tracking)
    # ---------------------------------------------------------
    def extract_and_summarize_text(self):
        text = ""; mod_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            if self.clipboard_cache: text = self.clipboard_cache; mod_date = "Pasted from Clipboard"
            elif self.analysis_file:
                mod_date = datetime.fromtimestamp(os.stat(self.analysis_file).st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                if self.analysis_file.endswith(".pdf"):
                    for page in fitz.open(self.analysis_file): text += page.get_text()
                else:
                    with open(self.analysis_file, 'r', encoding='utf-8') as f: text = f.read()
                
            words = text.lower().split(); freq = {w: words.count(w) for w in set(words)}
            scores = {s: sum(freq.get(w, 0) for w in s.lower().split()) for s in text.replace('!', '.').replace('?', '.').split('.')}
            limit = 3 if self.summary_length == "SHORT" else 8
            summary = ". ".join(sorted(scores, key=scores.get, reverse=True)[:limit]).strip() + "."
            self.text_data = {"date": mod_date, "words": len(words), "chars": len(text), "summary": summary}
            self.app_state = "ANALYZE_TEXT"
        except Exception: self.app_state = "MEDIA_MENU"

    def generate_audio_visuals(self, file_path):
        try:
            pygame.mixer.music.load(file_path); pygame.mixer.music.play(); self.is_playing = True
            y, sr = librosa.load(file_path, duration=30); self.audio_length = librosa.get_duration(path=file_path)
            S = cv2.normalize(librosa.amplitude_to_db(np.abs(librosa.stft(y)), ref=np.max), None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
            self.audio_data = cv2.resize(cv2.applyColorMap(S, cv2.COLORMAP_INFERNO), (1280, 500)) 
            self.vid_total = 100 # Dummy variable for audio scrubber sync
            self.app_state = "ANALYZE_AUDIO"
        except Exception: self.app_state = "MEDIA_MENU"

    def overlay_png(self, bg, overlay, x, y):
        if overlay.shape[2] < 4: return bg 
        h, w = overlay.shape[:2]; bg_h, bg_w = bg.shape[:2]
        if x >= bg_w or y >= bg_h or x + w <= 0 or y + h <= 0: return bg
        cx, cy = max(0, -x), max(0, -y); cw, ch = min(w, bg_w - x), min(h, bg_h - y)
        bx, by = max(0, x), max(0, y)
        overlay_crop = overlay[cy:cy+ch, cx:cx+cw]
        alpha = overlay_crop[:, :, 3] / 255.0
        for c in range(3): bg[by:by+ch, bx:bx+cw, c] = (alpha * overlay_crop[:, :, c] + (1 - alpha) * bg[by:by+ch, bx:bx+cw, c])
        return bg

    def draw_yolo_analytics(self, frame):
        person_detected = False
        for r in self.model_obj(frame, verbose=False, conf=0.4):
            for box in r.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cls_id = int(box.cls[0])
                
                # Ghost Trails Memory
                if self.enable_trails and self.app_state in ["LIVE", "ANALYZE_VIDEO"] and self.mode != "EFFECTS":
                    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                    if cls_id not in self.trails: self.trails[cls_id] = []
                    self.trails[cls_id].append((cx, cy))
                    if len(self.trails[cls_id]) > 25: self.trails[cls_id].pop(0) 
                    pts = self.trails[cls_id]
                    for i in range(1, len(pts)):
                        fade = int(np.interp(i, [0, 25], [50, 255]))
                        cv2.line(frame, pts[i-1], pts[i], (0, fade, fade), int(np.interp(i, [0, 25], [1, 4])))

                color = (0, 0, 255) if self.mode == "MOTION" else (0, 255, 0)
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(frame, f"{self.model_obj.names[cls_id].upper()} {math.ceil(box.conf[0].item() * 100)}%", (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                if cls_id == 0: person_detected = True

        if person_detected:
            for r in self.model_pose(frame, verbose=False, conf=0.5):
                if r.keypoints is not None and len(r.keypoints.xy) > 0:
                    for pts in r.keypoints.xy:
                        for edge in self.skeleton_edges:
                            p1, p2 = (int(pts[edge[0]][0]), int(pts[edge[0]][1])), (int(pts[edge[1]][0]), int(pts[edge[1]][1]))
                            if p1[0] > 0 and p1[1] > 0 and p2[0] > 0 and p2[1] > 0: cv2.line(frame, p1, p2, (0, 255, 255), 2)
                        for k in pts:
                            if k[0] > 0: cv2.circle(frame, (int(k[0]), int(k[1])), 4, (0, 0, 255), -1)
        return frame

    # ---------------------------------------------------------
    # RENDER ENGINE
    # ---------------------------------------------------------
    def draw_button(self, img, text, rel_box, bg=(40,40,40), blurb=""):
        win_w, win_h = 1280, 720
        rx, ry, rw, rh = rel_box
        x, y, bw, bh = int(rx*win_w), int(ry*win_h), int(rw*win_w), int(rh*win_h)
        
        # Hover Blurb Overlay
        if self.hover_active and x < self.last_mouse_pos[0] < x+bw and y < self.last_mouse_pos[1] < y+bh:
            overlay = img.copy()
            cv2.rectangle(overlay, (x, y-40), (x+int(bw*1.5), y-5), (0, 255, 255), -1)
            cv2.addWeighted(overlay, 0.9, img, 0.1, 0, img)
            cv2.putText(img, blurb, (x+10, y-15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0,0,0), 1)

        cv2.rectangle(img, (x, y), (x+bw, y+bh), bg, -1)
        cv2.rectangle(img, (x, y), (x+bw, y+bh), (100,100,100), 1)
        cv2.putText(img, text, (x+10, y+int(bh*0.65)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255,255,255), 1)

    def draw_transport_bar(self, img):
        win_w, win_h = 1280, 720
        # Scrubber
        cv2.rectangle(img, (int(0.1*win_w), int(0.84*win_h)), (int(0.9*win_w), int(0.86*win_h)), (60,60,60), -1)
        if self.vid_total > 0:
            px = int(0.1*win_w + (0.8*win_w * (self.vid_current / self.vid_total)))
            cv2.circle(img, (px, int(0.85*win_h)), 10, (0, 255, 0), -1)
        # Buttons
        self.draw_button(img, "RW", (0.41, 0.88, 0.05, 0.05), blurb="Rewind Media")
        self.draw_button(img, "||" if self.is_playing else ">", (0.47, 0.88, 0.06, 0.05), blurb="Play/Pause Media")
        self.draw_button(img, "FF", (0.54, 0.88, 0.05, 0.05), blurb="Fast-Forward Media")
        self.draw_button(img, "STOP", (0.60, 0.88, 0.06, 0.05), blurb="Stop & Reset")

    def draw_universal_help(self, img):
        if not self.show_help: return
        win_w, win_h = 1280, 720
        overlay = img.copy()
        cv2.rectangle(overlay, (int(win_w*0.15), int(win_h*0.15)), (int(win_w*0.85), int(win_h*0.65)), (15, 15, 15), -1)
        img[:] = cv2.addWeighted(overlay, 0.95, img, 0.05, 0)
        cv2.rectangle(img, (int(win_w*0.15), int(win_h*0.15)), (int(win_w*0.85), int(win_h*0.65)), (0, 255, 0), 2)
        
        r = {
            "LIVE": ["[C] Export HUD", "[R] Record Video", "Drag bottom sliders for Zoom/Exposure."],
            "ANALYZE_PHOTO": ["[C] Export Frame", "[Click FILTER] Cycle processing.", "YOLOv8 scans automatically."],
            "ANALYZE_VIDEO": ["[C] Export Frame", "[Space] Play/Pause", "Scrub lower bar timeline."],
            "ANALYZE_AUDIO": ["[C] Export Spectrogram", "[Space] Play/Pause", "Scrub lower bar timeline."],
            "ANALYZE_TEXT": ["[C] Export Summary", "[Click SIZE] Short/Long.", "Math NLP ranking."]
        }
        cv2.putText(img, f"HELP: {self.app_state}", (int(win_w*0.18), int(win_h*0.22)), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        for i, line in enumerate(r.get(self.app_state, ["Menu Navigation Mode. Hover over buttons for instructions."])):
            cv2.putText(img, line, (int(win_w*0.18), int(win_h*0.3) + (i * 30)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1)

    def run(self):
        while True:
            # Fixed 1280x720 Canvas
            win_w, win_h = 1280, 720
            display = np.zeros((win_h, win_w, 3), dtype=np.uint8)

            # 1. Render OS States
            if self.app_state == "MENU":
                cv2.putText(display, "CLOUTVISION OS", (int(win_w*0.38), int(win_h*0.15)), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                self.draw_button(display, "1. LIVE HUD", (0.35, 0.20, 0.3, 0.06), blurb="Real-time AI Entity Tracking")
                self.draw_button(display, "2. SECURITY MONITOR", (0.35, 0.28, 0.3, 0.06), blurb="Motion-Triggered Alerts")
                self.draw_button(display, "3. VISUAL EFFECTS", (0.35, 0.36, 0.3, 0.06), blurb="Computational Photography")
                self.draw_button(display, "4. MEDIA ANALYSIS", (0.35, 0.44, 0.3, 0.06), blurb="Forensic File Suite")
                self.draw_button(display, "5. CONTROL CENTER", (0.35, 0.52, 0.3, 0.06), blurb="Hardware Configuration")
                self.draw_button(display, "6. SHUTDOWN", (0.35, 0.75, 0.3, 0.06), blurb="Safe System Exit")

            elif self.app_state == "SETTINGS":
                cv2.putText(display, "SYSTEM CONFIGURATION", (int(win_w*0.35), int(win_h*0.15)), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
                self.draw_button(display, f"Camera Index: {self.cam_index}", (0.15, 0.25, 0.3, 0.06), blurb="Cycle USB/Internal Lenses")
                self.draw_button(display, "Load Face Mask (PNG)", (0.15, 0.35, 0.3, 0.06), blurb="Import Transparent HUD Mask")
                self.draw_button(display, f"Export: {self.export_target}", (0.55, 0.25, 0.3, 0.06), blurb="Photos App vs Finder")
                self.draw_button(display, f"Show Clock: {self.show_clock}", (0.55, 0.35, 0.3, 0.06), blurb="Toggle Global Clock")
                self.draw_button(display, f"Motion Trails: {'ON' if self.enable_trails else 'OFF'}", (0.55, 0.45, 0.3, 0.06), blurb="Toggle Object History")
                self.draw_button(display, "Reset View Sliders", (0.55, 0.55, 0.3, 0.06), blurb="Reset Zoom and Exposure")

            elif self.app_state == "MEDIA_MENU":
                cv2.putText(display, "ANALYSIS SUITE", (int(win_w*0.38), int(win_h*0.10)), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 100, 0), 2)
                self.draw_button(display, "Import Photo", (0.35, 0.15, 0.3, 0.06), blurb="YOLO & Filter Processing")
                self.draw_button(display, "Import Video", (0.35, 0.23, 0.3, 0.06), blurb="Frame-by-Frame Tracking")
                self.draw_button(display, "Import Audio", (0.35, 0.31, 0.3, 0.06), blurb="Spectrogram Physics")
                self.draw_button(display, "Import Text / PDF", (0.35, 0.39, 0.3, 0.06), blurb="File NLP Summarization")
                self.draw_button(display, "Paste Text (Clipboard)", (0.35, 0.47, 0.3, 0.06), blurb="Analyze copied web text")

            elif self.app_state == "LIVE":
                if self.cap and self.cap.isOpened():
                    ret, frame = self.cap.read()
                    if ret:
                        frame = cv2.flip(frame, 1) 
                        if self.zoom > 1.0:
                            h, w = frame.shape[:2]; cx, cy = w // 2, h // 2; rx, ry = int(w / (2 * self.zoom)), int(h / (2 * self.zoom))
                            frame = cv2.resize(frame[cy - ry:cy + ry, cx - rx:cx + rx], (w, h))
                        if self.exposure != 1.0: frame = cv2.convertScaleAbs(frame, alpha=self.exposure, beta=0)
                        
                        if self.mode in ["CLOUTVISION", "MOTION"]: display = cv2.resize(self.draw_yolo_analytics(frame), (win_w, win_h))
                        elif self.mode == "EFFECTS":
                            fx = self.effect_list[self.effect_idx]
                            if fx == "PENCIL_SKETCH": display = cv2.resize(cv2.pencilSketch(frame, sigma_s=60, sigma_r=0.07, shade_factor=0.05)[1], (win_w, win_h))
                            elif fx == "WATERCOLOR": display = cv2.resize(cv2.stylization(frame, sigma_s=60, sigma_r=0.07), (win_w, win_h))
                            elif fx == "GHOST_TRAILS":
                                if self.ghost_acc is None or self.ghost_acc.shape != frame.shape: self.ghost_acc = np.float32(frame)
                                cv2.accumulateWeighted(frame, self.ghost_acc, 0.2); display = cv2.resize(cv2.convertScaleAbs(self.ghost_acc), (win_w, win_h))
                            elif fx == "HAAR_FACES":
                                display = cv2.resize(frame.copy(), (win_w, win_h))
                                for (xf,yf,wf,hf) in self.face_cascade.detectMultiScale(cv2.cvtColor(display, cv2.COLOR_BGR2GRAY), 1.3, 5): 
                                    if self.face_mask is not None: display = self.overlay_png(display, cv2.resize(self.face_mask, (wf, hf)), xf, yf)
                                    else: cv2.rectangle(display,(xf,yf),(xf+wf,yf+hf),(255,255,0),2)
                            elif fx == "NEON_EDGES":
                                neon = np.zeros_like(frame); neon[cv2.dilate(cv2.Canny(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), 50, 150), None) > 0] = [255, 0, 255]
                                display = cv2.resize(cv2.addWeighted(frame, 0.4, neon, 0.8, 0), (win_w, win_h))
                            elif fx == "THERMAL": display = cv2.resize(cv2.applyColorMap(cv2.bitwise_not(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)), cv2.COLORMAP_JET), (win_w, win_h))
                            elif fx == "CHROMATIC_GLITCH":
                                display = cv2.resize(frame.copy(), (win_w, win_h)); display[:, :-15, 2] = display[:, 15:, 2]; display[:, 15:, 0] = display[:, :-15, 0]
                            elif fx == "NIGHT_VISION": display = cv2.resize(cv2.merge((frame[:,:,0]*0, cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), frame[:,:,0]*0)), (win_w, win_h))
                            
                            cv2.putText(display, f"FX: {fx}", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,255), 2)
                            self.draw_button(display, "NEXT FX", (0.65, 0.02, 0.1, 0.05), bg=(150, 0, 150), blurb="Cycle Filters")
                
                # Draggable HUD Sliders
                cv2.putText(display, f"ZOOM: {round(self.zoom,1)}x", (int(0.05*win_w), int(0.91*win_h)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200,200,200), 1)
                cv2.rectangle(display, (int(0.05*win_w), int(0.92*win_h)), (int(0.25*win_w), int(0.94*win_h)), (60,60,60), -1)
                cv2.circle(display, (int(0.05*win_w + ((self.zoom-1.0)/3.0)*0.2*win_w), int(0.93*win_h)), 8, (0, 255, 0), -1)
                cv2.putText(display, f"EXP: {round(self.exposure,1)}x", (int(0.3*win_w), int(0.91*win_h)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200,200,200), 1)
                cv2.rectangle(display, (int(0.3*win_w), int(0.92*win_h)), (int(0.5*win_w), int(0.94*win_h)), (60,60,60), -1)
                cv2.circle(display, (int(0.3*win_w + ((self.exposure-0.2)/2.8)*0.2*win_w), int(0.93*win_h)), 8, (0, 255, 255), -1)

            elif self.app_state == "ANALYZE_VIDEO":
                if self.vid_cap and self.vid_cap.isOpened():
                    if self.is_playing:
                        ret, f = self.vid_cap.read()
                        if ret: self.vid_current += 1; self.last_vid_frame = self.draw_yolo_analytics(f)
                        else: self.is_playing = False 
                    if self.last_vid_frame is not None: display = cv2.resize(self.last_vid_frame, (win_w, win_h))
                self.draw_transport_bar(display)
                    
            elif self.app_state == "ANALYZE_PHOTO":
                img = cv2.imread(self.analysis_file)
                if img is not None:
                    if img.shape[1] > 1280 or img.shape[0] > 720: img = cv2.resize(img, (int(img.shape[1]*min(1280/img.shape[1], 720/img.shape[0])), int(img.shape[0]*min(1280/img.shape[1], 720/img.shape[0]))))
                    if self.photo_filter == "DETAIL_ENHANCE": img = cv2.detailEnhance(img, sigma_s=10, sigma_r=0.15)
                    elif self.photo_filter == "DENOISE": img = cv2.fastNlMeansDenoisingColored(img, None, 10, 10, 7, 21)
                    display = cv2.resize(self.draw_yolo_analytics(img), (win_w, win_h))
                    self.draw_button(display, f"FILTER: {self.photo_filter}", (0.02, 0.02, 0.15, 0.05), bg=(50, 50, 50), blurb="Toggle Photo Processing")

            elif self.app_state == "ANALYZE_AUDIO":
                cv2.putText(display, "AUDIO ANALYSIS HUD", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,0), 2)
                if self.is_playing and not pygame.mixer.music.get_busy(): pygame.mixer.music.unpause()
                elif not self.is_playing and pygame.mixer.music.get_busy(): pygame.mixer.music.pause()
                
                if self.audio_length > 0: self.vid_current = int(100 * (pygame.mixer.music.get_pos() / 1000.0) / self.audio_length)
                self.draw_transport_bar(display)
                if self.audio_data is not None: display[int(win_h*0.2):int(win_h*0.2)+500, 0:1280] = self.audio_data

            elif self.app_state == "ANALYZE_TEXT":
                cv2.putText(display, "TEXT ANALYSIS & SUMMARIZATION", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255,255,0), 2)
                self.draw_button(display, f"SIZE: {self.summary_length}", (0.02, 0.12, 0.1, 0.05), blurb="Toggle Summary Depth")
                cv2.putText(display, f"Modified: {self.text_data['date']}", (20, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200,200,200), 1)
                cv2.putText(display, f"Word Count: {self.text_data['words']}", (300, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200,200,200), 1)
                cv2.putText(display, f"Letter Count: {self.text_data['chars']}", (550, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200,200,200), 1)
                cv2.putText(display, "GENERATED SUMMARY:", (20, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,255,0), 2)
                
                lines = []; current_line = ""
                for word in self.text_data['summary'].split(' '):
                    if cv2.getTextSize(current_line + word + " ", cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)[0][0] > int(win_w * 0.9):
                        lines.append(current_line); current_line = word + " "
                    else: current_line += word + " "
                lines.append(current_line)
                for i, line in enumerate(lines): cv2.putText(display, line, (20, 240 + (i * 25)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1)

            # 2. Universal Global Rendering (Top Layer)
            if self.show_clock: cv2.putText(display, datetime.now().strftime("%Y-%m-%d  %H:%M:%S"), (20, win_h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200,200,200), 1)
            
            if self.app_state != "MENU":
                self.draw_button(display, "BACK", (0.89, 0.02, 0.09, 0.05), bg=(0, 0, 150), blurb="Return to Main Menu")
                self.draw_button(display, "HELP", (0.79, 0.02, 0.09, 0.05), bg=(50, 50, 50), blurb="Open Mode Instructions")
                
                if self.recording: cv2.putText(display, "[REC]", (int(win_w*0.65), 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

            self.draw_universal_help(display)
            
            if self.flash_frames > 0: cv2.rectangle(display, (0,0), (win_w,win_h), (255,255,255), -1); self.flash_frames -= 1
            if self.recording and self.out and self.app_state != "MENU": self.out.write(display)

            cv2.imshow('CloutVision', display)
            
            # 3. Global Hotkeys
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'): break
            if key == ord(' '): self.is_playing = not self.is_playing
            if key == ord('c') and self.app_state != "MENU": self.capture_media(display)
            if key == ord('r') and self.app_state != "MENU":
                if not self.recording: self.out = cv2.VideoWriter(f"cv_export_{int(time.time())}.mp4", cv2.VideoWriter_fourcc(*'mp4v'), 20.0, (win_w, win_h)); self.recording = True
                else: self.recording = False; self.out.release(); self.out = None

        self.close_all_media(); cv2.destroyAllWindows()

if __name__ == "__main__": CloutVision().run()
