# CloutVision manual test checklist

Use this after automated tests pass, to verify behavior that requires GUI, camera, or file dialogs.

---

## 1. MENU

| Action | Expected |
|--------|----------|
| Click **LIVE HUD** | Opens live camera view; mode = CLOUTVISION; YOLO boxes on objects |
| Click **SPOOKY MODE** | Live camera; mode = SPOOKY; stance/emotion/shirt/pants labels on people |
| Click **VISUAL EFFECTS** | Live camera; mode = EFFECTS; **Next FX** visible; cycle through FX (Pencil, Ghost, etc.) |
| Click **MEDIA ANALYSIS** | Opens Analysis Suite (Import Photo/Video/Audio/Text) |
| Click **CONTROL CENTER** | Opens Control Center (camera, export, clock, UI color, reset, AI confidence) |
| Click **SHUTDOWN** | App exits |
| Click **BACK** (from any sub-screen) | Returns to MENU; error message cleared |
| Click **HELP** | Toggles help overlay; click again to close |

---

## 2. CONTROL CENTER (SETTINGS)

| Button / control | Expected |
|------------------|----------|
| **Camera: 0** (or 1) | Cycles camera index; label updates |
| **Face mask…** | Opens file picker for image; if selected, stored (used by face effects) |
| **Face label…** | Opens dialog "Enter text to stick to Face"; updates custom face text |
| **Export: PHOTOS** / **FINDER** | Toggles; captures go to Photos app or reveal in Finder |
| **Clock: On** / **Off** | Toggles show_clock |
| **UI color** | Cycles accent color (green/yellow/blue/magenta) |
| **Reset sliders** | zoom=1, exposure=1, yolo_conf=0.4 |
| **AI confidence** slider | Drag to change 0.1–0.9; value shown above |

---

## 3. ANALYSIS SUITE (MEDIA_MENU)

| Button | Expected |
|--------|----------|
| **Import Photo** | File picker (images); if selected → ANALYZE_PHOTO with YOLO + MDLS/OCR buttons |
| **Import Video** | File picker (video); if selected → ANALYZE_VIDEO with transport bar |
| **Import Audio** | File picker (audio); if selected → ANALYZE_AUDIO with spectrogram + transport |
| **Import Text / PDF** | File picker (text/PDF); if selected → ANALYZE_TEXT with summary |

Cancel file picker → stay on same screen, no crash.

---

## 4. LIVE view

| Control | Expected |
|---------|----------|
| **Skel** | Toggle skeleton lines on/off (green when ON) |
| **Emo** | Toggle emotion/face mesh on/off (green when ON) |
| **Color** | Toggle shirt/pants color regions on/off (green when ON) |
| **Lens** | Cycle camera (0 ↔ 1) |
| **Next FX** (EFFECTS mode only) | Cycle effect (Pencil, Ghost, Blink, etc.) |
| **Zoom** bar (bottom) | Drag to zoom 1x–4x |
| **Exp** bar (bottom) | Drag to adjust exposure |
| **Left-click** on image (below toolbar) | Places color picker crosshair; shows "SAMPLED: <color>" |
| **Right-click** | Clears color picker |

---

## 5. ANALYZE_PHOTO

| Button | Expected |
|--------|----------|
| **MDLS** | Toggle metadata panel (right side) on/off |
| **OCR** (if available) | Toggle spatial OCR boxes on image |
| **BACK** | Return to MENU |

---

## 6. ANALYZE_VIDEO / ANALYZE_AUDIO

| Control | Expected |
|---------|----------|
| **MDLS** | Toggle metadata panel |
| **Track** (timeline) | Click/drag to seek |
| **\|<<** | Rewind (vid_current − 100) |
| **>** / **\|\|** | Play / Pause |
| **>>\|** | Forward (vid_current + 100) |
| **STOP** | Pause and reset to start |
| **BACK** | Return to MENU |

---

## 7. ANALYZE_TEXT

| Control | Expected |
|---------|----------|
| **SIZE: SHORT** / **LONG** | Toggle summary length; affects next extraction (current screen text unchanged until re-import) |
| **BACK** | Return to MENU |

---

## 8. Keyboard

| Key | Expected |
|-----|----------|
| **Q** | Quit app |
| **Space** | Toggle play/pause (video/audio) |
| **C** (when not on MENU) | Capture current frame to file; export to Photos or Finder per setting |

---

## 9. Error handling

| Scenario | Expected |
|----------|----------|
| No camera connected, then **LIVE HUD** | Error banner: "Camera could not be opened." (or similar) |
| Cancel file picker | No crash; stay on current screen |
| Invalid/corrupt image file | Error message; no crash |
| Audio load failure | Error message; remain in MEDIA_MENU |

---

Run automated tests first:

```bash
cd /path/to/CloutVisionMac
source venv/bin/activate
pip install pytest  # if needed
pytest tests/ -v
```

**Note:** If you applied `fix_sdl_duplicate.sh`, cv2 may not load and all automated tests will be **skipped**. To run the automated tests, temporarily restore the SDL dylib:  
`mv venv/lib/python3.*/site-packages/cv2/.dylibs/libSDL2-2.0.0.dylib.bak venv/lib/python3.*/site-packages/cv2/.dylibs/libSDL2-2.0.0.dylib`  
Then run `pytest tests/ -v`; re-apply the fix afterward if you want to run the app without SDL warnings.

Then go through this checklist manually.
