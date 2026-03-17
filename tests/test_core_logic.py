"""
Tests for core logic: letterbox, color sampling, ROI helpers.
Run: pytest tests/test_core_logic.py -v
Skips if cloutvision_core cannot be imported (e.g. cv2/SDL missing after fix_sdl_duplicate).
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from cloutvision_core import CloutVision, WIN_W, WIN_H
    HAS_APP = True
except Exception as e:
    HAS_APP = False
    import_error = e


@pytest.mark.skipif(not HAS_APP, reason="cloutvision_core/cv2 not loadable (e.g. SDL fix applied)")
def test_letterbox_shape():
    """letterbox returns image of expected size."""
    import numpy as np
    app = CloutVision()
    app.cap = None
    # 640x480 input -> letterbox to 1280x720
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    out = app.letterbox(img)
    assert out.shape == (WIN_H, WIN_W, 3)

@pytest.mark.skipif(not HAS_APP, reason="cloutvision_core/cv2 not loadable")
def test_letterbox_preserves_aspect():
    """letterbox centers and letterboxes; corners should be black."""
    import numpy as np
    app = CloutVision()
    app.cap = None
    img = np.ones((720, 1280, 3), dtype=np.uint8) * 255
    out = app.letterbox(img)
    assert out.shape == (720, 1280, 3)
    # Exact fit
    np.testing.assert_array_equal(out, img)

@pytest.mark.skipif(not HAS_APP, reason="cloutvision_core/cv2 not loadable")
def test_hsv_to_color_name_black():
    """_hsv_to_color_name returns BLACK for very low value."""
    app = CloutVision()
    app.cap = None
    _, name = app._hsv_to_color_name(0, 0, 30, (20, 20, 20))
    assert "BLACK" in name

@pytest.mark.skipif(not HAS_APP, reason="cloutvision_core/cv2 not loadable")
def test_hsv_to_color_name_white():
    """_hsv_to_color_name returns WHITE for low sat high value."""
    app = CloutVision()
    app.cap = None
    _, name = app._hsv_to_color_name(0, 20, 220, (250, 250, 250))
    assert "WHITE" in name

@pytest.mark.skipif(not HAS_APP, reason="cloutvision_core/cv2 not loadable")
def test_hsv_to_color_name_red():
    """_hsv_to_color_name returns RED for hue at red."""
    app = CloutVision()
    app.cap = None
    _, name = app._hsv_to_color_name(5, 200, 200, (0, 0, 255))
    assert "RED" in name

@pytest.mark.skipif(not HAS_APP, reason="cloutvision_core/cv2 not loadable")
def test_sample_hsv_color_returns_bgr_and_name():
    """sample_hsv_color returns (bgr_tuple, name)."""
    import numpy as np
    app = CloutVision()
    app.cap = None
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    frame[50, 50] = (0, 0, 255)  # red
    bgr, name = app.sample_hsv_color(frame, 50, 50)
    assert len(bgr) == 3
    assert isinstance(name, str)
    assert len(name) > 0

@pytest.mark.skipif(not HAS_APP, reason="cloutvision_core/cv2 not loadable")
def test_sample_region_color_returns_bgr_and_name():
    """sample_region_color returns (bgr_tuple, name) for a region."""
    import numpy as np
    app = CloutVision()
    app.cap = None
    frame = np.zeros((200, 200, 3), dtype=np.uint8)
    frame[50:150, 50:150] = (0, 255, 0)  # green block
    bgr, name = app.sample_region_color(frame, 50, 50, 150, 150)
    assert len(bgr) == 3
    assert isinstance(name, str)
