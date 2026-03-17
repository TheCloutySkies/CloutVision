# CloutVision tests

## Automated tests

- **`test_ui_buttons.py`** — Every UI button and its effect: menu navigation, BACK/HELP, Settings (export, clock, UI color, reset), LIVE toggles (Skel, Emo, Color), transport (play/pause, RW, FF, STOP), MDLS, TEXT SIZE. Ensures each label does what it says.
- **`test_core_logic.py`** — Letterbox shape, HSV→color name (black/white/red), `sample_hsv_color` and `sample_region_color` return (BGR, name).

### Run tests (recommended)

From the project root:

```bash
./run_tests.sh
```

This script temporarily restores opencv’s `libSDL2` (if you applied `fix_sdl_duplicate.sh`) so cv2 loads, runs pytest, then re-applies the fix. **First run can take 1–2 minutes** while YOLO loads. Optional: `./run_tests.sh -v` or `./run_tests.sh tests/test_ui_buttons.py`.

### Run tests manually

```bash
source venv/bin/activate
pip install pytest
pytest tests/ -v
```

If you applied `fix_sdl_duplicate.sh`, cv2 won’t load and all tests will be **skipped** unless you use `./run_tests.sh` or manually restore the dylib.

## Manual testing

Use **`MANUAL_TEST_CHECKLIST.md`** to verify GUI, camera, file pickers, and keyboard (Q, Space, C) once automated tests pass (or after confirming skips are due to cv2 only).
