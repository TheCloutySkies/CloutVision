"""
Vigorous tests for every UI button and module in CloutVision.
Ensures each button does what its label suggests (state transitions and toggles).
Run: pytest tests/test_ui_buttons.py -v
Skips all tests if cloutvision_core cannot be imported (e.g. cv2/SDL missing).
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from cloutvision_core import CloutVision, LAYOUT
    _CloutVision, _LAYOUT = CloutVision, LAYOUT
    _CAN_IMPORT = True
except Exception:
    _CloutVision, _LAYOUT = None, None
    _CAN_IMPORT = False

# Use LAYOUT from module (or None if import failed)
LAYOUT = _LAYOUT if _CAN_IMPORT else {}
WIN_W, WIN_H = 1280, 720

def _center_rel(rel_box):
    """Return (rx, ry) center of rel_box (x, y, w, h)."""
    x, y, w, h = rel_box
    return (x + w / 2, y + h / 2)

def _center_px(rel_box):
    """Return (px, py) pixel center of rel_box."""
    rx, ry = _center_rel(rel_box)
    return (int(rx * WIN_W), int(ry * WIN_H))


@pytest.fixture(scope="module")
def app():
    """Create one CloutVision instance for all tests (loads YOLO/pygame once)."""
    if not _CAN_IMPORT:
        pytest.skip("cloutvision_core/cv2 not loadable")
    import builtins
    _real_exit = getattr(builtins, "exit", None)
    builtins.exit = lambda code=None: None
    try:
        app = _CloutVision()
        app.cap = None  # avoid camera
        yield app
    finally:
        if _real_exit is not None:
            builtins.exit = _real_exit


@pytest.fixture
def cl(app):
    """Reset app to known state and provide click(rel_box) helper."""
    app.app_state = "MENU"
    app.show_help = False
    app.error_message = None
    app.mode = "CLOUTVISION"
    app.toggle_skeleton = True
    app.toggle_emotion = True
    app.toggle_color = True
    app.show_exif_hud = False
    app.run_ocr = False
    app.summary_length = "SHORT"
    app.is_playing = True
    app.vid_current = 0
    app.vid_total = 100
    def click(rel_box):
        rx, ry = _center_rel(rel_box)
        app.last_mouse_pos = _center_px(rel_box)
        app.handle_clicks(rx, ry)
    return click


# ---- _in_button hit-test ----
@pytest.mark.skipif(not _CAN_IMPORT, reason="cloutvision_core not loadable")
def test_in_button_inside(app):
    """_in_button returns True when mouse is inside the box."""
    app.last_mouse_pos = _center_px(LAYOUT["top_bar"]["back"])
    assert app._in_button(LAYOUT["top_bar"]["back"]) is True

@pytest.mark.skipif(not _CAN_IMPORT, reason="cloutvision_core not loadable")
def test_in_button_outside(app):
    """_in_button returns False when mouse is outside."""
    app.last_mouse_pos = (0, 0)
    assert app._in_button(LAYOUT["top_bar"]["back"]) is False


# ---- MENU ----
@pytest.mark.skipif(not _CAN_IMPORT, reason="cloutvision_core not loadable")
def test_menu_live_hud(app, cl):
    """LIVE HUD -> app_state LIVE, mode CLOUTVISION."""
    cl(LAYOUT["menu_buttons"][0])
    assert app.app_state == "LIVE" and app.mode == "CLOUTVISION"

@pytest.mark.skipif(not _CAN_IMPORT, reason="cloutvision_core not loadable")
def test_menu_spooky_mode(app, cl):
    """SPOOKY MODE -> app_state LIVE, mode SPOOKY_MODE."""
    cl(LAYOUT["menu_buttons"][1])
    assert app.app_state == "LIVE" and app.mode == "SPOOKY_MODE"

@pytest.mark.skipif(not _CAN_IMPORT, reason="cloutvision_core not loadable")
def test_menu_visual_effects(app, cl):
    """VISUAL EFFECTS -> app_state LIVE, mode EFFECTS."""
    cl(LAYOUT["menu_buttons"][2])
    assert app.app_state == "LIVE" and app.mode == "EFFECTS"

@pytest.mark.skipif(not _CAN_IMPORT, reason="cloutvision_core not loadable")
def test_menu_media_analysis(app, cl):
    """MEDIA ANALYSIS -> app_state MEDIA_MENU."""
    cl(LAYOUT["menu_buttons"][3])
    assert app.app_state == "MEDIA_MENU"

@pytest.mark.skipif(not _CAN_IMPORT, reason="cloutvision_core not loadable")
def test_menu_control_center(app, cl):
    """CONTROL CENTER -> app_state SETTINGS."""
    cl(LAYOUT["menu_buttons"][4])
    assert app.app_state == "SETTINGS"

@pytest.mark.skipif(not _CAN_IMPORT, reason="cloutvision_core not loadable")
def test_menu_shutdown_calls_exit(app, cl):
    """SHUTDOWN triggers exit (mocked)."""
    import builtins
    m = pytest.Mock()
    builtins.exit = m
    try:
        cl(LAYOUT["menu"]["shutdown"])
        m.assert_called_once()
    finally:
        builtins.exit = lambda code=None: None


# ---- BACK and HELP ----
@pytest.mark.skipif(not _CAN_IMPORT, reason="cloutvision_core not loadable")
def test_back_from_settings_to_menu(app, cl):
    """BACK from SETTINGS -> MENU."""
    app.app_state = "SETTINGS"
    cl(LAYOUT["top_bar"]["back"])
    assert app.app_state == "MENU"

@pytest.mark.skipif(not _CAN_IMPORT, reason="cloutvision_core not loadable")
def test_back_from_media_menu_to_menu(app, cl):
    """BACK from MEDIA_MENU -> MENU."""
    app.app_state = "MEDIA_MENU"
    cl(LAYOUT["top_bar"]["back"])
    assert app.app_state == "MENU"

@pytest.mark.skipif(not _CAN_IMPORT, reason="cloutvision_core not loadable")
def test_help_toggles_show_help(app, cl):
    """HELP toggles show_help."""
    app.app_state = "SETTINGS"
    initial = app.show_help
    cl(LAYOUT["top_bar"]["help"])
    assert app.show_help == (not initial)
    cl(LAYOUT["top_bar"]["help"])
    assert app.show_help == initial


# ---- SETTINGS ----
@pytest.mark.skipif(not _CAN_IMPORT, reason="cloutvision_core not loadable")
def test_settings_export_toggle(app, cl):
    """Export button toggles PHOTOS <-> FINDER."""
    app.app_state = "SETTINGS"
    app.export_target = "PHOTOS"
    cl(LAYOUT["settings"]["col2"][0])
    assert app.export_target == "FINDER"
    cl(LAYOUT["settings"]["col2"][0])
    assert app.export_target == "PHOTOS"

@pytest.mark.skipif(not _CAN_IMPORT, reason="cloutvision_core not loadable")
def test_settings_clock_toggle(app, cl):
    """Clock button toggles show_clock."""
    app.app_state = "SETTINGS"
    initial = app.show_clock
    cl(LAYOUT["settings"]["col2"][1])
    assert app.show_clock == (not initial)

@pytest.mark.skipif(not _CAN_IMPORT, reason="cloutvision_core not loadable")
def test_settings_ui_color_cycles(app, cl):
    """UI color button cycles ui_color_idx."""
    app.app_state = "SETTINGS"
    idx = app.ui_color_idx
    cl(LAYOUT["settings"]["col2"][2])
    assert app.ui_color_idx == (idx + 1) % len(app.ui_colors)

@pytest.mark.skipif(not _CAN_IMPORT, reason="cloutvision_core not loadable")
def test_settings_reset_sliders(app, cl):
    """Reset sliders sets zoom=1, exposure=1, yolo_conf=0.4."""
    app.app_state = "SETTINGS"
    app.zoom = 2.0
    app.exposure = 1.5
    app.yolo_conf = 0.8
    cl(LAYOUT["settings"]["col2"][3])
    assert app.zoom == 1.0 and app.exposure == 1.0 and app.yolo_conf == 0.4


# ---- LIVE toggles ----
@pytest.mark.skipif(not _CAN_IMPORT, reason="cloutvision_core not loadable")
def test_toggle_skeleton(app, cl):
    """Skel button toggles toggle_skeleton."""
    app.app_state = "LIVE"
    initial = app.toggle_skeleton
    cl((0.34, 0.022, 0.08, 0.048))
    assert app.toggle_skeleton == (not initial)

@pytest.mark.skipif(not _CAN_IMPORT, reason="cloutvision_core not loadable")
def test_toggle_emotion(app, cl):
    """Emo button toggles toggle_emotion."""
    app.app_state = "LIVE"
    initial = app.toggle_emotion
    cl((0.44, 0.022, 0.08, 0.048))
    assert app.toggle_emotion == (not initial)

@pytest.mark.skipif(not _CAN_IMPORT, reason="cloutvision_core not loadable")
def test_toggle_color(app, cl):
    """Color button toggles toggle_color."""
    app.app_state = "LIVE"
    initial = app.toggle_color
    cl((0.54, 0.022, 0.08, 0.048))
    assert app.toggle_color == (not initial)


# ---- ANALYZE_PHOTO ----
@pytest.mark.skipif(not _CAN_IMPORT, reason="cloutvision_core not loadable")
def test_photo_mdls_toggle(app, cl):
    """MDLS button toggles show_exif_hud on ANALYZE_PHOTO."""
    app.app_state = "ANALYZE_PHOTO"
    initial = app.show_exif_hud
    cl((0.16, 0.072, 0.10, 0.048))
    assert app.show_exif_hud == (not initial)


# ---- ANALYZE_VIDEO / AUDIO transport ----
@pytest.mark.skipif(not _CAN_IMPORT, reason="cloutvision_core not loadable")
def test_transport_play_pause(app, cl):
    """Play/Pause button toggles is_playing."""
    app.app_state = "ANALYZE_VIDEO"
    initial = app.is_playing
    cl(LAYOUT["transport"]["play"])
    assert app.is_playing == (not initial)

@pytest.mark.skipif(not _CAN_IMPORT, reason="cloutvision_core not loadable")
def test_transport_stop(app, cl):
    """STOP sets is_playing False and vid_current 0."""
    app.app_state = "ANALYZE_VIDEO"
    app.is_playing = True
    app.vid_current = 50
    cl(LAYOUT["transport"]["stop"])
    assert app.is_playing is False and app.vid_current == 0

@pytest.mark.skipif(not _CAN_IMPORT, reason="cloutvision_core not loadable")
def test_transport_rw_decreases(app, cl):
    """RW decreases vid_current (capped at 0)."""
    app.app_state = "ANALYZE_VIDEO"
    app.vid_current = 50
    cl(LAYOUT["transport"]["rw"])
    assert app.vid_current == max(0, 50 - 100)

@pytest.mark.skipif(not _CAN_IMPORT, reason="cloutvision_core not loadable")
def test_transport_ff_increases(app, cl):
    """FF increases vid_current (capped at vid_total)."""
    app.app_state = "ANALYZE_VIDEO"
    app.vid_current = 10
    app.vid_total = 100
    cl(LAYOUT["transport"]["ff"])
    assert app.vid_current == min(100, 10 + 100)


# ---- ANALYZE_VIDEO / AUDIO MDLS ----
@pytest.mark.skipif(not _CAN_IMPORT, reason="cloutvision_core not loadable")
def test_video_mdls_toggle(app, cl):
    """MDLS on ANALYZE_VIDEO toggles show_exif_hud."""
    app.app_state = "ANALYZE_VIDEO"
    initial = app.show_exif_hud
    cl((0.02, 0.072, 0.08, 0.048))
    assert app.show_exif_hud == (not initial)


# ---- ANALYZE_TEXT SIZE ----
@pytest.mark.skipif(not _CAN_IMPORT, reason="cloutvision_core not loadable")
def test_text_size_toggle(app, cl):
    """SIZE button on ANALYZE_TEXT toggles summary_length SHORT <-> LONG."""
    app.app_state = "ANALYZE_TEXT"
    app.summary_length = "SHORT"
    cl((0.02, 0.12, 0.10, 0.05))
    assert app.summary_length == "LONG"
    cl((0.02, 0.12, 0.10, 0.05))
    assert app.summary_length == "SHORT"
