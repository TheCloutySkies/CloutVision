import os
import sys

# --- Suppress PyGame/OpenCV Terminal Spam ---
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "hide"
os.environ["PATH"] += os.pathsep + "/usr/local/bin" + os.pathsep + "/opt/homebrew/bin"

import pygame 
import cv2
import numpy as np
from ultralytics import YOLO
import subprocess
import time
from datetime import datetime
import librosa
import fitz   
import re
import warnings

warnings.filterwarnings("ignore")

# ============================================================================
# UNBREAKABLE DEPENDENCY LOADERS
# ============================================================================
try:
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = '/opt/homebrew/bin/tesseract'
    HAS_OCR = True
except ImportError:
    HAS_OCR = False

try:
    import mediapipe as mp
    try: 
        mp_face_mesh = mp.solutions.face_mesh
        mp_drawing = mp.solutions.drawing_utils
        mp_drawing_styles = mp.solutions.drawing_styles
    except AttributeError: 
        import mediapipe.python.solutions.face_mesh as mp_face_mesh
        import mediapipe.python.solutions.drawing_utils as mp_drawing
        import mediapipe.python.solutions.drawing_styles as mp_drawing_styles
    
    face_mesh_engine = mp_face_mesh.FaceMesh(max_num_faces=3, refine_landmarks=True, min_detection_confidence=0.5)
    HAS_MP = True
except Exception as e:
    print(f"\n[SYSTEM WARNING] MediaPipe Face Mesh offline: {e}\n(Try 'pip install mediapipe-silicon')\n")
    HAS_MP = False
    mp_face_mesh, mp_drawing, mp_drawing_styles, face_mesh_engine = None, None, None, None

class CloutVision:
    def __init__(self):
        print("CloutVision OS v23.0: Total Control Engine Booting...")
        self.model_obj = YOLO('yolov8n.pt') 
        self.model_pose = YOLO('yolov8n-pose.pt') 
        pygame.mixer.init() 
        
        # --- Core OS States ---
        self.app_state = "MENU" 
        self.mode = "CLOUTVISION" 
        self.effect_list = ["NEON_EDGES", "THERMAL", "GHOST_TRAILS", "PENCIL_SKETCH", "HAAR_FACES", "BLINK_TRACKER", "FINGER_DRAW"]
        self.effect_idx = 0
        self.show_help = False
        self.show_exif_hud = False
        
        # --- Global System Preferences ---
        self.ui_colors = [(0, 255, 0), (255, 255, 0), (0, 150, 255), (255, 0, 255)]
        self.ui_color_idx = 0
        self.yolo_conf = 0.4
        self.zoom, self.exposure = 1.0, 1.0
        
        # --- Modular Toggles ---
        self.run_ocr = False
        self.toggle_skeleton = True
        self.toggle_emotion = True
        self.toggle_color = True
        
        self.last_mouse_pos = (0, 0)
        self.color_sample_pos = None 
        self.hover_start_time = time.time()
        self.hover_active = False
        self.dragging_slider = None
        self.dragging_timeline = False
        
        self.frame_counter = 0
        self.cached_dets = []
        self.cached_pose = None
        self.cached_mesh = []
        
        self.tips = [
            "TIP: Click anywhere on the screen to deploy the Color Picker Crosshair.",
            "TIP: Toggle SKELETONS to show YOLO Pose estimation on Photos and Videos.",
            "TIP: The Face Mesh calculates Emotion using advanced Aspect Ratios.",
            "TIP: OCR now spatially maps text coordinates directly onto the image.",
            "TIP: Use the Control Center to adjust AI Confidence and UI Colors."
        ]
        
        self.cam_index = 0
        self.cap = None 
        self.export_target = "PHOTOS" 
        self.show_clock = True
        self.exif_detail = "DETAILED"
        self.custom_face_text = "SUBJECT"
        
        self.recording = False; self.out = None
        self.flash_frames = 0; self.ghost_acc = None 
        self.draw_points = []; self.blinks = 0; self.eyes_closed_frames = 0
        
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        self.eye_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_eye.xml')
        
        self.analysis_file = None; self.clipboard_cache = None; self.audio_data = None
        self.text_data = None; self.summary_length = "SHORT"; self.photo_filter = "RAW" 
        self.extracted_exif = []; self.ocr_cache = None 
        
        self.vid_cap = None; self.vid_total = 1; self.vid_current = 0
        self.is_playing = True; self.last_vid_frame = None; self.audio_length = 0

        self.skeleton_edges = [(0,1),(0,2),(1,3),(2,4),(5,6),(5,11),(6,12),(11,12),(5,7),(7,9),(6,8),(8,10),(11,13),(13,15),(12,14),(14,16)]

        cv2.namedWindow('CloutVision')
        cv2.setMouseCallback('CloutVision', self.mouse_event)

    # ---------------------------------------------------------
    # MAC BRIDGES & MEDIA
    # ---------------------------------------------------------
    def select_file_mac(self, kind):
        types = '{"public.image"}' if kind == "PHOTO" else '{"public.movie"}' if kind == "VIDEO" else '{"public.audio"}' if kind == "AUDIO" else '{"public.text", "com.adobe.pdf"}'
        script = f'set f to choose file with prompt "Select {kind} for Analysis" of type {types}\nPOSIX path of f'
        try: return subprocess.check_output(['osascript', '-e', script]).decode('utf-8').strip()
        except: return None

    def cycle_camera(self):
        if self.cap: self.cap.release()
        self.cam_index = 1 if self.cam_index == 0 else 0
        self.cap = cv2.VideoCapture(self.cam_index)
        if not self.cap or not self.cap.isOpened():
            self.cam_index = 0; self.cap = cv2.VideoCapture(self.cam_index)

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
        h, w = img.shape[:2]
        scale = min(expected_w/w, expected_h/h)
        new_w, new_h = int(w * scale), int(h * scale)
        resized = cv2.resize(img, (new_w, new_h))
        canvas = np.zeros((expected_h, expected_w, 3), dtype=np.uint8)
        y_off, x_off = (expected_h - new_h) // 2, (expected_w - new_w) // 2
        canvas[y_off:y_off+new_h, x_off:x_off+new_w] = resized
        return canvas

    def load_metadata_mac(self, filepath):
        self.extracted_exif = []
        try:
            out = subprocess.check_output(['mdls', filepath]).decode('utf-8')
            for line in out.split('\n'):
                if '=' in line and 'kMDItem' in line:
                    clean = line.split('=')
                    key = clean[0].strip().replace('kMDItem', '')
                    val = clean[1].strip().strip('"')
                    self.extracted_exif.append(f"{key}: {val}"[:60])
            if not self.extracted_exif: self.extracted_exif = ["No MDLS data found."]
        except Exception as e:
            self.extracted_exif = [f"Metadata Error: {e}"]

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
        text = ""; mod_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            if self.clipboard_cache: 
                text = self.clipboard_cache; mod_date = "Pasted from Clipboard"
            elif self.analysis_file.endswith(".pdf"):
                for page in fitz.open(self.analysis_file): text += page.get_text()
            else:
                try: text = subprocess.check_output(['textutil', '-stdout', '-convert', 'txt', self.analysis_file]).decode('utf-8')
                except: 
                    with open(self.analysis_file, 'r') as f: text = f.read()
            
            text = re.sub(r'[^a-zA-Z0-9\s.,!?\'"-]', '', text) 
            text = re.sub(r'\s+', ' ', text).strip()
            
            words = text.lower().split(); freq = {w: words.count(w) for w in set(words)}
            scores = {s: sum(freq.get(w, 0) for w in s.lower().split()) for s in text.replace('!','.').replace('?','.').split('.')}
            summary = ". ".join(sorted(scores, key=scores.get, reverse=True)[:3 if self.summary_length=="SHORT" else 8]).strip() + "."
            
            self.text_data = {"date": mod_date, "words": len(words), "chars": len(text), "summary": summary}
            self.app_state = "ANALYZE_TEXT"
        except: self.app_state = "MEDIA_MENU"

    def analyze_emotion(self, mesh):
        """Advanced MediaPipe EAR/MAR Emotion Logic"""
        # MAR: Inner lip distance
        mar = abs(mesh[13].y - mesh[14].y)
        # EAR: Eye openness (average of both eyes)
        ear_l = abs(mesh[159].y - mesh[145].y)
        ear_r = abs(mesh[386].y - mesh[374].y)
        ear = (ear_l + ear_r) / 2.0
        # Smile Width
        smile_w = abs(mesh[61].x - mesh[291].x)
        
        if mar > 0.05 and ear > 0.025: return "SURPRISED"
        if mar > 0.035: return "TALKING / ACTIVE"
        if smile_w > 0.15 and mar < 0.03: return "HAPPY"
        if ear < 0.01: return "BLINKING / DROWSY"
        return "NEUTRAL"

    def sample_hsv_color(self, frame, x, y):
        """Highly precise HSV Color Logic."""
        h, w = frame.shape[:2]
        region = frame[max(0, y-4):min(h, y+5), max(0, x-4):min(w, x+5)]
        if region.size == 0: return (0,255,0), "UNKNOWN"
        
        hsv_region = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
        hue, sat, val = np.mean(hsv_region, axis=(0,1))
        b, g, r = np.mean(region, axis=(0,1))
        bgr_color = (int(b), int(g), int(r))

        if val < 40: return bgr_color, "BLACK / DARK"
        if sat < 40 and val > 180: return bgr_color, "WHITE / LIGHT"
        if sat < 50: return bgr_color, "GRAY / NEUTRAL"
        
        if hue < 10 or hue > 165: return bgr_color, "RED"
        elif 10 <= hue < 25: return bgr_color, "ORANGE / BROWN"
        elif 25 <= hue < 35: return bgr_color, "YELLOW"
        elif 35 <= hue < 85: return bgr_color, "GREEN"
        elif 85 <= hue < 100: return bgr_color, "CYAN"
        elif 100 <= hue < 135: return bgr_color, "BLUE"
        elif 135 <= hue <= 155: return bgr_color, "PURPLE"
        elif 155 < hue <= 165: return bgr_color, "PINK"
        return bgr_color, "UNKNOWN"

    def apply_visual_effects(self, frame):
        fx = self.effect_list[self.effect_idx]
        display = frame.copy()
        
        if fx == "PENCIL_SKETCH": display = cv2.pencilSketch(frame, sigma_s=60, sigma_r=0.07, shade_factor=0.05)[1]
        elif fx == "GHOST_TRAILS":
            if self.ghost_acc is None or self.ghost_acc.shape != frame.shape: self.ghost_acc = np.float32(frame)
            cv2.accumulateWeighted(frame, self.ghost_acc, 0.2); display = cv2.convertScaleAbs(self.ghost_acc)
        elif fx == "BLINK_TRACKER":
            gray = cv2.cvtColor(display, cv2.COLOR_BGR2GRAY)
            for (x,y,wf,hf) in self.face_cascade.detectMultiScale(gray, 1.3, 5):
                eyes = self.eye_cascade.detectMultiScale(gray[y:y+hf, x:x+wf])
                if len(eyes) == 0: self.eyes_closed_frames += 1
                else:
                    if self.eyes_closed_frames > 2: self.blinks += 1
                    self.eyes_closed_frames = 0
            cv2.putText(display, f"BLINKS: {self.blinks}", (40, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0,0,255), 3)
        elif fx == "FINGER_DRAW":
            for r in self.model_pose(frame, verbose=False, conf=0.5):
                if r.keypoints is not None and len(r.keypoints.xy) > 0:
                    wrist = r.keypoints.xy[0][10] 
                    if wrist[0] > 0: self.draw_points.append((int(wrist[0]), int(wrist[1])))
            if len(self.draw_points) > 100: self.draw_points.pop(0)
            for i in range(1, len(self.draw_points)): cv2.line(display, self.draw_points[i-1], self.draw_points[i], (0,255,255), 4)
        elif fx == "HAAR_FACES" or fx == "FACE_TEXT":
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
        self.frame_counter += 1
        h, w = frame.shape[:2]
        ui_col = self.ui_colors[self.ui_color_idx]
        
        # --- GPU Governor & AI Inference ---
        if self.frame_counter % 2 == 0:
            res = self.model_obj(frame, verbose=False, conf=self.yolo_conf)
            self.cached_dets = []
            if len(res) > 0:
                for i, box in enumerate(res[0].boxes):
                    coords = tuple(map(int, box.xyxy[0]))
                    conf = float(box.conf[0])
                    cls_id = int(box.cls[0])
                    self.cached_dets.append({"box": coords, "id": i, "conf": conf, "cls": cls_id})
            
            if self.toggle_skeleton or self.mode == "SPOOKY_MODE":
                pose_res = self.model_pose(frame, verbose=False, conf=self.yolo_conf)
                if len(pose_res) > 0 and pose_res[0].keypoints is not None and len(pose_res[0].keypoints.xy) > 0:
                    self.cached_pose = pose_res[0].keypoints.xy[0]
                else: self.cached_pose = None
            
            if HAS_MP and self.toggle_emotion and self.mode == "SPOOKY_MODE" and face_mesh_engine is not None:
                fm_res = face_mesh_engine.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                self.cached_mesh = fm_res.multi_face_landmarks if fm_res and fm_res.multi_face_landmarks else []

        # --- Visual Effects Override Protection ---
        if self.mode == "EFFECTS" and self.app_state == "LIVE":
            return self.apply_visual_effects(frame)

        # --- Face Mesh Render ---
        if HAS_MP and self.toggle_emotion and self.mode == "SPOOKY_MODE" and self.cached_mesh and mp_drawing is not None:
            for face_landmarks in self.cached_mesh:
                mp_drawing.draw_landmarks(
                    image=frame, landmark_list=face_landmarks, connections=mp_face_mesh.FACEMESH_TESSELATION,
                    landmark_drawing_spec=None, connection_drawing_spec=mp_drawing_styles.get_default_face_mesh_tesselation_style()
                )

        # --- Interactive Crosshair ---
        if self.color_sample_pos is not None:
            cx, cy = self.color_sample_pos
            cv2.circle(frame, (cx, cy), 15, (0, 255, 255), 2)
            cv2.drawMarker(frame, (cx, cy), (0, 0, 255), markerType=cv2.MARKER_CROSS, markerSize=20, thickness=2)
            col_bgr, col_name = self.sample_hsv_color(frame, cx, cy)
            cv2.putText(frame, f"SAMPLED: {col_name}", (cx+20, cy-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, col_bgr, 2)
            cv2.rectangle(frame, (cx+20, cy), (cx+150, cy+20), col_bgr, -1)

        # --- HUD RENDER LOOP ---
        person_detected = False
        for det in self.cached_dets:
            x1, y1, x2, y2 = det["box"]
            box_id, conf, cls_id = det["id"], det["conf"], det["cls"]
            
            if cls_id == 0: person_detected = True

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
                        cx, cy = (x1+x2)//2, y1 + int((y2-y1)*0.3)
                        col_bgr, col_name = self.sample_hsv_color(frame, cx, cy)
                        cv2.circle(frame, (cx, cy), 4, col_bgr, -1)
                        cv2.putText(frame, f"ATTIRE: {col_name}", (x2+10, y_off), cv2.FONT_HERSHEY_SIMPLEX, 0.5, col_bgr, 1)
                        y_off += 20

                    if HAS_MP and self.toggle_emotion and self.cached_mesh:
                        emo = self.analyze_emotion(self.cached_mesh[0].landmark)
                        cv2.putText(frame, f"EMOTION: {emo}", (x2+10, y_off), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 2)
                        y_off += 20

                # Universal Spooky Tracking for ALL Objects
                cv2.rectangle(frame, (x1, y1), (x2, y2), ui_col, 1)
                obj_name = self.model_obj.names[cls_id].upper()
                cv2.putText(frame, f"{obj_name} [{conf:.2f}]", (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, ui_col, 2)
                cv2.line(frame, ((x1+x2)//2, (y1+y2)//2), (x2+5, y1+20), ui_col, 1)

            else:
                # Basic Vision Mode
                cv2.rectangle(frame, (x1, y1), (x2, y2), ui_col, 2)
                obj_name = self.model_obj.names[cls_id].upper()
                cv2.putText(frame, f"{obj_name} [{conf:.2f}]", (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, ui_col, 2)

        # Draw Skeletons
        if person_detected and self.toggle_skeleton and self.cached_pose is not None and self.mode != "EFFECTS":
            for e in self.skeleton_edges:
                p1, p2 = (int(self.cached_pose[e[0]][0]), int(self.cached_pose[e[0]][1])), (int(self.cached_pose[e[1]][0]), int(self.cached_pose[e[1]][1]))
                if p1[0] > 0 and p2[0] > 0: cv2.line(frame, p1, p2, (0, 255, 255), 2)
                
        return frame

    # ---------------------------------------------------------
    # INPUT ROUTING & UI
    # ---------------------------------------------------------
    def mouse_event(self, event, x, y, flags, param):
        win_w, win_h = 1280, 720; rx, ry = x / win_w, y / win_h
        self.last_mouse_pos = (x, y)
        is_timeline_area = (0.1 <= rx <= 0.9 and 0.83 <= ry <= 0.88)

        if event == cv2.EVENT_MOUSEMOVE:
            self.hover_active = True
            if self.dragging_slider == "ZOOM": self.zoom = 1.0 + (np.clip((rx - 0.05) / 0.2, 0, 1) * 3.0)
            elif self.dragging_slider == "EXPOSURE": self.exposure = 0.2 + (np.clip((rx - 0.3) / 0.2, 0, 1) * 2.8)
            elif self.dragging_slider == "CONF": self.yolo_conf = 0.1 + (np.clip((rx - 0.55) / 0.3, 0, 1) * 0.8)
            elif self.dragging_timeline and self.app_state in ["ANALYZE_VIDEO", "ANALYZE_AUDIO"]:
                self.vid_current = int(np.clip((rx - 0.1) / 0.8, 0, 1) * self.vid_total)
                self.sync_media()

        elif event == cv2.EVENT_LBUTTONDOWN:
            if is_timeline_area and self.app_state in ["ANALYZE_VIDEO", "ANALYZE_AUDIO"]:
                self.dragging_timeline = True
                self.vid_current = int(np.clip((rx - 0.1) / 0.8, 0, 1) * self.vid_total)
                self.sync_media()
            elif self.app_state in ["LIVE", "ANALYZE_PHOTO", "ANALYZE_VIDEO"] and ry < 0.8: 
                self.color_sample_pos = (x, y)
            self.handle_clicks(rx, ry)
            
        elif event == cv2.EVENT_RBUTTONDOWN: self.color_sample_pos = None 
        elif event == cv2.EVENT_LBUTTONUP: 
            self.dragging_slider = None; self.dragging_timeline = False

    def handle_clicks(self, rx, ry):
        if self.app_state != "MENU":
            if 0.89 <= rx <= 0.98 and 0.02 <= ry <= 0.07: self.close_all_media(); self.app_state = "MENU"; self.ocr_cache = None
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
                    try: self.custom_face_text = subprocess.check_output(['osascript', '-e', 'set T to text returned of (display dialog "Enter text to stick to Face:" default answer "SUBJECT")\nreturn T']).decode('utf-8').strip()
                    except: pass
            elif 0.55 <= rx <= 0.85:
                if 0.25 <= ry <= 0.31: self.export_target = "FINDER" if self.export_target == "PHOTOS" else "PHOTOS"
                elif 0.35 <= ry <= 0.41: self.show_clock = not self.show_clock
                elif 0.45 <= ry <= 0.51: self.ui_color_idx = (self.ui_color_idx + 1) % len(self.ui_colors)
                elif 0.55 <= ry <= 0.61: self.zoom = 1.0; self.exposure = 1.0; self.yolo_conf = 0.4
            # Slider bounds
            if 0.55 <= rx <= 0.85 and 0.65 <= ry <= 0.70: self.dragging_slider = "CONF"

        elif self.app_state == "MEDIA_MENU":
            if 0.35 <= rx <= 0.65:
                if 0.15 <= ry <= 0.21: 
                    f = self.select_file_mac("PHOTO")
                    if f: self.analysis_file = f; self.load_metadata_mac(f); self.app_state = "ANALYZE_PHOTO"; self.ocr_cache = None
                elif 0.23 <= ry <= 0.29: 
                    f = self.select_file_mac("VIDEO")
                    if f: 
                        self.analysis_file = f; self.vid_cap = cv2.VideoCapture(f); self.load_metadata_mac(f)
                        self.vid_total = max(1, int(self.vid_cap.get(cv2.CAP_PROP_FRAME_COUNT)))
                        self.vid_current = 0; self.is_playing = True; self.app_state = "ANALYZE_VIDEO"
                elif 0.31 <= ry <= 0.37: 
                    f = self.select_file_mac("AUDIO")
                    if f: self.analysis_file = f; self.generate_audio_visuals(f)
                elif 0.39 <= ry <= 0.45:
                    f = self.select_file_mac("TEXT")
                    if f: self.clipboard_cache = None; self.analysis_file = f; self.extract_and_summarize_text()

        # Modular Toggles 
        if self.app_state in ["LIVE", "ANALYZE_PHOTO", "ANALYZE_VIDEO"]:
            if 0.35 <= rx <= 0.45 and 0.02 <= ry <= 0.07: self.toggle_skeleton = not self.toggle_skeleton
            if 0.47 <= rx <= 0.57 and 0.02 <= ry <= 0.07: self.toggle_emotion = not self.toggle_emotion
            if 0.59 <= rx <= 0.69 and 0.02 <= ry <= 0.07: self.toggle_color = not self.toggle_color

        if self.app_state == "LIVE":
            if 0.70 <= rx <= 0.78 and 0.02 <= ry <= 0.07: self.cycle_camera()
            if self.mode == "EFFECTS" and 0.23 <= rx <= 0.33 and 0.02 <= ry <= 0.07: 
                self.effect_idx = (self.effect_idx + 1) % len(self.effect_list)
            if 0.88 <= ry <= 0.95:
                if 0.05 <= rx <= 0.25: self.dragging_slider = "ZOOM"
                elif 0.30 <= rx <= 0.50: self.dragging_slider = "EXPOSURE"

        elif self.app_state == "ANALYZE_PHOTO":
            if 0.17 <= rx <= 0.30 and 0.02 <= ry <= 0.07: self.show_exif_hud = not self.show_exif_hud
            if 0.32 <= rx <= 0.45 and 0.02 <= ry <= 0.07 and HAS_OCR: 
                self.run_ocr = not self.run_ocr; self.ocr_cache = None 

        if self.app_state in ["ANALYZE_VIDEO", "ANALYZE_AUDIO"]:
            if 0.02 <= rx <= 0.15 and 0.02 <= ry <= 0.07: self.show_exif_hud = not self.show_exif_hud
            if 0.82 <= ry <= 0.98:
                if 0.47 <= rx <= 0.53: self.is_playing = not self.is_playing 
                elif 0.54 <= rx <= 0.59: self.vid_current = min(self.vid_total, self.vid_current + 100); self.sync_media()
                elif 0.41 <= rx <= 0.46: self.vid_current = max(0, self.vid_current - 100); self.sync_media()
                elif 0.60 <= rx <= 0.65: self.is_playing = False; self.vid_current = 0; self.sync_media()

    # ---------------------------------------------------------
    # UI RENDERERS
    # ---------------------------------------------------------
    def draw_button(self, img, text, rel_box, bg=(40,40,40)):
        win_w, win_h = 1280, 720; rx, ry, rw, rh = rel_box
        x, y, bw, bh = int(rx*win_w), int(ry*win_h), int(rw*win_w), int(rh*win_h)
        
        is_hover = x < self.last_mouse_pos[0] < x+bw and y < self.last_mouse_pos[1] < y+bh
        color = (0, 200, 200) if is_hover else bg

        cv2.rectangle(img, (x, y), (x+bw, y+bh), color, -1)
        cv2.rectangle(img, (x, y), (x+bw, y+bh), (100,100,100), 1)
        txt_col = (0,0,0) if is_hover else (255,255,255)
        cv2.putText(img, text, (x+10, y+int(bh*0.65)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, txt_col, 1)

    def draw_transport(self, img):
        win_w, win_h = 1280, 720
        cv2.rectangle(img, (int(0.1*win_w), int(0.84*win_h)), (int(0.9*win_w), int(0.86*win_h)), (60,60,60), -1)
        if self.vid_total > 0:
            px = int(0.1*win_w + (0.8*win_w * (self.vid_current / self.vid_total)))
            radius = 15 if self.dragging_timeline else 10
            cv2.circle(img, (px, int(0.85*win_h)), radius, (0, 255, 0), -1)
        self.draw_button(img, "RW", (0.41, 0.88, 0.05, 0.05))
        self.draw_button(img, "||" if self.is_playing else ">", (0.47, 0.88, 0.06, 0.05))
        self.draw_button(img, "FF", (0.54, 0.88, 0.05, 0.05))
        self.draw_button(img, "STOP", (0.60, 0.88, 0.06, 0.05))

    def run(self):
        while True:
            win_w, win_h = 1280, 720
            display = np.zeros((win_h, win_w, 3), dtype=np.uint8)
            
            if self.app_state in ["MENU", "SETTINGS", "MEDIA_MENU"]:
                if self.cap and self.cap.isOpened():
                    ret, bg_frame = self.cap.read()
                    if ret: 
                        bg_frame = cv2.GaussianBlur(self.letterbox(cv2.flip(bg_frame, 1)), (51, 51), 0)
                        display = cv2.addWeighted(bg_frame, 0.4, display, 0.6, 0)

            if self.app_state == "MENU":
                cv2.putText(display, "CloutVision OS", (int(win_w*0.38), int(win_h*0.15)), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 0), 3)
                self.draw_button(display, "1. LIVE HUD", (0.35, 0.20, 0.3, 0.06))
                self.draw_button(display, "2. SPOOKY MODE", (0.35, 0.28, 0.3, 0.06))
                self.draw_button(display, "3. VISUAL EFFECTS", (0.35, 0.36, 0.3, 0.06))
                self.draw_button(display, "4. MEDIA ANALYSIS", (0.35, 0.44, 0.3, 0.06))
                self.draw_button(display, "5. CONTROL CENTER", (0.35, 0.52, 0.3, 0.06))
                self.draw_button(display, "6. SHUTDOWN", (0.35, 0.75, 0.3, 0.06))
                cv2.putText(display, self.tips[int(time.time() / 5) % len(self.tips)], (int(win_w*0.2), win_h - 40), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 1)

            elif self.app_state == "SETTINGS":
                cv2.putText(display, "CONTROL CENTER", (int(win_w*0.38), int(win_h*0.15)), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
                self.draw_button(display, f"Camera Index: {self.cam_index}", (0.15, 0.25, 0.3, 0.06))
                self.draw_button(display, f"Export: {self.export_target}", (0.55, 0.25, 0.3, 0.06))
                self.draw_button(display, f"Show Clock: {self.show_clock}", (0.55, 0.35, 0.3, 0.06))
                self.draw_button(display, f"Cycle UI Color", (0.55, 0.45, 0.3, 0.06))
                self.draw_button(display, "Reset View Sliders", (0.55, 0.55, 0.3, 0.06))
                
                # Confidence Slider
                cv2.putText(display, f"AI CONFIDENCE: {round(self.yolo_conf,2)}", (int(0.55*win_w), int(0.64*win_h)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200,200,200), 1)
                cv2.rectangle(display, (int(0.55*win_w), int(0.65*win_h)), (int(0.85*win_w), int(0.67*win_h)), (60,60,60), -1)
                cv2.circle(display, (int(0.55*win_w + ((self.yolo_conf-0.1)/0.8)*0.3*win_w), int(0.66*win_h)), 8, (0, 255, 0), -1)

            elif self.app_state == "MEDIA_MENU":
                cv2.putText(display, "ANALYSIS SUITE", (int(win_w*0.38), int(win_h*0.10)), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 100, 0), 2)
                self.draw_button(display, "Import Photo", (0.35, 0.15, 0.3, 0.06))
                self.draw_button(display, "Import Video", (0.35, 0.23, 0.3, 0.06))
                self.draw_button(display, "Import Audio", (0.35, 0.31, 0.3, 0.06))
                self.draw_button(display, "Import Text / PDF", (0.35, 0.39, 0.3, 0.06))

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
                    except Exception as e: print(f"Camera Error: {e}")

                cv2.putText(display, f"ZOOM: {round(self.zoom,1)}x", (int(0.05*win_w), int(0.91*win_h)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200,200,200), 1)
                cv2.rectangle(display, (int(0.05*win_w), int(0.92*win_h)), (int(0.25*win_w), int(0.94*win_h)), (60,60,60), -1)
                cv2.circle(display, (int(0.05*win_w + ((self.zoom-1.0)/3.0)*0.2*win_w), int(0.93*win_h)), 8, (0, 255, 0), -1)
                cv2.putText(display, f"EXP: {round(self.exposure,1)}x", (int(0.3*win_w), int(0.91*win_h)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200,200,200), 1)
                cv2.rectangle(display, (int(0.3*win_w), int(0.92*win_h)), (int(0.5*win_w), int(0.94*win_h)), (60,60,60), -1)
                cv2.circle(display, (int(0.3*win_w + ((self.exposure-0.2)/2.8)*0.2*win_w), int(0.93*win_h)), 8, (0, 255, 255), -1)
                
                self.draw_button(display, "CYCLE LENS", (0.75, 0.02, 0.12, 0.05), bg=(100, 50, 0))
                if self.mode == "EFFECTS":
                    self.draw_button(display, "NEXT FX", (0.23, 0.02, 0.1, 0.05), bg=(150, 0, 150))

            elif self.app_state == "ANALYZE_VIDEO":
                if self.vid_cap and self.vid_cap.isOpened():
                    if self.is_playing:
                        ret, f = self.vid_cap.read()
                        if ret: self.vid_current += 1; self.last_vid_frame = self.draw_yolo_analytics(self.letterbox(f))
                        else: self.is_playing = False 
                    if self.last_vid_frame is not None: display = self.last_vid_frame.copy()
                self.draw_transport(display)
                self.draw_button(display, "MDLS DATA", (0.02, 0.02, 0.1, 0.05), bg=(50, 50, 50))
                    
            elif self.app_state == "ANALYZE_PHOTO":
                img = cv2.imread(self.analysis_file)
                if img is not None:
                    img = self.letterbox(img)
                    display = self.draw_yolo_analytics(img)
                    
                    self.draw_button(display, "MDLS DATA", (0.17, 0.02, 0.12, 0.05), bg=(50, 50, 50))
                    if HAS_OCR: self.draw_button(display, "SPATIAL OCR", (0.32, 0.02, 0.13, 0.05), bg=(0, 150, 150))

                    if self.run_ocr and HAS_OCR:
                        if self.ocr_cache is None:
                            gray = cv2.cvtColor(display, cv2.COLOR_BGR2GRAY)
                            thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 11, 2)
                            self.ocr_cache = pytesseract.image_to_data(thresh, output_type=pytesseract.Output.DICT)
                        
                        for i in range(len(self.ocr_cache['text'])):
                            if int(self.ocr_cache['conf'][i]) > 50 and len(self.ocr_cache['text'][i].strip()) > 1:
                                x, y, w, h = self.ocr_cache['left'][i], self.ocr_cache['top'][i], self.ocr_cache['width'][i], self.ocr_cache['height'][i]
                                cv2.rectangle(display, (x, y), (x+w, y+h), (0, 255, 255), 2)
                                cv2.putText(display, f"[{x},{y}]", (x, y-5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)

            elif self.app_state == "ANALYZE_AUDIO":
                cv2.putText(display, "AUDIO ANALYSIS HUD", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,0), 2)
                if self.is_playing and not pygame.mixer.music.get_busy(): pygame.mixer.music.unpause()
                elif not self.is_playing and pygame.mixer.music.get_busy(): pygame.mixer.music.pause()
                
                if self.audio_length > 0: self.vid_current = int(self.vid_total * (pygame.mixer.music.get_pos() / 1000.0) / self.audio_length)
                if self.audio_data is not None: display[int(win_h*0.2):int(win_h*0.2)+500, 0:1280] = self.audio_data
                self.draw_transport(display)

            elif self.app_state == "ANALYZE_TEXT":
                cv2.putText(display, "TEXT ANALYSIS & SUMMARIZATION", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255,255,0), 2)
                self.draw_button(display, f"SIZE: {self.summary_length}", (0.02, 0.12, 0.1, 0.05))
                cv2.putText(display, f"Modified: {self.text_data['date']} | Words: {self.text_data['words']} | Chars: {self.text_data['chars']}", (20, 160), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200,200,200), 1)
                cv2.putText(display, "GENERATED SUMMARY:", (20, 210), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,255,0), 2)
                
                lines = []; current_line = ""
                for word in self.text_data['summary'].split(' '):
                    if cv2.getTextSize(current_line + word + " ", cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)[0][0] > int(win_w * 0.9):
                        lines.append(current_line); current_line = word + " "
                    else: current_line += word + " "
                lines.append(current_line)
                for i, line in enumerate(lines): cv2.putText(display, line, (20, 250 + (i * 25)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1)

            # --- Global Modular Toggles ---
            if self.app_state in ["LIVE", "ANALYZE_PHOTO", "ANALYZE_VIDEO"]:
                self.draw_button(display, f"SKEL: {'ON' if self.toggle_skeleton else 'OFF'}", (0.35, 0.02, 0.09, 0.05), bg=(0, 100, 0) if self.toggle_skeleton else (100, 0, 0))
                self.draw_button(display, f"EMO: {'ON' if self.toggle_emotion else 'OFF'}", (0.47, 0.02, 0.09, 0.05), bg=(0, 100, 0) if self.toggle_emotion else (100, 0, 0))
                self.draw_button(display, f"COL: {'ON' if self.toggle_color else 'OFF'}", (0.59, 0.02, 0.09, 0.05), bg=(0, 100, 0) if self.toggle_color else (100, 0, 0))

            if self.show_exif_hud and self.app_state in ["ANALYZE_PHOTO", "ANALYZE_VIDEO"]:
                cv2.rectangle(display, (win_w-450, 100), (win_w-20, 600), (20,20,20), -1)
                cv2.putText(display, "MDLS METADATA", (win_w-430, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,255), 1)
                for i, line in enumerate(self.extracted_exif[:20]): cv2.putText(display, line, (win_w-430, 160 + (i*20)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200,200,200), 1)

            if self.app_state != "MENU":
                self.draw_button(display, "BACK", (0.89, 0.02, 0.09, 0.05), bg=(0, 0, 150))
                if self.recording: cv2.putText(display, "[REC]", (int(win_w*0.65), 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

            if self.flash_frames > 0: cv2.rectangle(display, (0,0), (win_w,win_h), (255,255,255), -1); self.flash_frames -= 1
            cv2.imshow('CloutVision', display)
            
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'): break
            if key == ord(' '): self.is_playing = not self.is_playing
            if key == ord('c') and self.app_state != "MENU": self.capture_media(display)

        self.close_all_media(); cv2.destroyAllWindows()

if __name__ == "__main__": CloutVision().run()
