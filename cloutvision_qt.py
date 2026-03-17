"""
CloutVision PyQt6 UI.
Run with: python cloutvision_qt.py
"""
import sys
try:
    from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtGui import QImage, QPixmap
except Exception as e:
    print("PyQt6 is not available in this Python environment.")
    print("Activate your project venv, then run again:")
    print("  source /Users/cloutyskies/Desktop/CloutVisionMac/venv/bin/activate")
    print("  python /Users/cloutyskies/Desktop/CloutVisionMac/cloutvision_qt.py")
    print(f"Import error: {e}")
    raise SystemExit(1)

# Import after env setup so core doesn't create OpenCV window
from cloutvision_core import CloutVision, WIN_W, WIN_H


def bgr_to_qimage(bgr, rgb_ref=None):
    """Convert OpenCV BGR (H,W,3) uint8 to QImage (RGB). Pass list to store ref: rgb_ref[:] = [arr] so buffer stays alive."""
    import numpy as np
    h, w = bgr.shape[:2]
    rgb = np.ascontiguousarray(bgr[:, :, ::-1])  # BGR -> RGB
    if rgb_ref is not None:
        rgb_ref.clear()
        rgb_ref.append(rgb)
    return QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888)


class VideoLabel(QLabel):
    """Central widget that displays the core's frame and forwards mouse/key events."""
    def __init__(self, core, parent=None):
        super().__init__(parent)
        self.core = core
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(640, 360)
        self.setScaledContents(False)
         # Match CloutVision dark background so letterbox bars blend with HUD.
        self.setStyleSheet("background-color: rgb(6, 6, 14);")
        # Where the rendered pixmap is actually drawn inside this widget when KeepAspectRatio is used.
        self._content_x = 0
        self._content_y = 0
        self._content_w = max(1, WIN_W)
        self._content_h = max(1, WIN_H)

    def set_content_rect(self, x, y, w, h):
        self._content_x = int(x)
        self._content_y = int(y)
        self._content_w = max(1, int(w))
        self._content_h = max(1, int(h))

    def _widget_to_logical(self, x, y):
        """Map widget coordinates to logical frame coords, accounting for letterbox bars."""
        # Convert from widget-space to content-space (inside displayed pixmap).
        cx = x - self._content_x
        cy = y - self._content_y
        if self._content_w <= 0 or self._content_h <= 0:
            return int(x), int(y)
        cx = max(0, min(self._content_w, cx))
        cy = max(0, min(self._content_h, cy))
        lx = int(cx * WIN_W / self._content_w)
        ly = int(cy * WIN_H / self._content_h)
        return max(0, min(WIN_W, lx)), max(0, min(WIN_H, ly))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            lx, ly = self._widget_to_logical(event.position().x(), event.position().y())
            self.core.inject_mouse("press", lx, ly)
        elif event.button() == Qt.MouseButton.RightButton:
            lx, ly = self._widget_to_logical(event.position().x(), event.position().y())
            self.core.last_mouse_pos = (lx, ly)
            self.core.inject_mouse("rpress", lx, ly)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            lx, ly = self._widget_to_logical(event.position().x(), event.position().y())
            self.core.inject_mouse("release", lx, ly)
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        lx, ly = self._widget_to_logical(event.position().x(), event.position().y())
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.core.inject_mouse("move", lx, ly)
        else:
            self.core.last_mouse_pos = (lx, ly)
        super().mouseMoveEvent(event)

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Q:
            self.window().close()
            return
        if key == Qt.Key.Key_Space:
            self.core.is_playing = not self.core.is_playing
            return
        if key == Qt.Key.Key_C and self.core.app_state != "MENU":
            # Capture uses last frame; parent window will pass it in on next tick
            self.window().request_capture = True
            return
        super().keyPressEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CloutVision")
        # Match HUD background for areas outside the rendered frame.
        self.setStyleSheet("background-color: rgb(6, 6, 14);")
        self.core = CloutVision(use_qt=True)
        self.last_frame = None
        self._rgb_ref = []  # keep reference so QImage buffer stays valid
        self.request_capture = False

        self.video_label = VideoLabel(self.core, self)
        self.setCentralWidget(self.video_label)
        self.setMinimumSize(720, 420)
        self.resize(WIN_W, WIN_H)

        # Simple native menubar.
        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction("Quit", self.close)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_tick)
        self.timer.start(20)  # ~50 fps
        self.video_label.setFocus()

    def keyPressEvent(self, event):
        """Forward keys so they work when window has focus."""
        key = event.key()
        if key == Qt.Key.Key_Q:
            self.close()
            return
        if key == Qt.Key.Key_Space:
            self.core.is_playing = not self.core.is_playing
            return
        if key == Qt.Key.Key_C and self.core.app_state != "MENU":
            self.request_capture = True
            return
        super().keyPressEvent(event)

    def _on_tick(self):
        self.last_frame = self.core.paint_frame()
        img = bgr_to_qimage(self.last_frame, self._rgb_ref)
        pix = QPixmap.fromImage(img)
        target = self.video_label.size()
        scaled = pix.scaled(
            target,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        # Compute where scaled pixmap sits within label to keep mouse mapping exact after resize.
        x = (target.width() - scaled.width()) // 2
        y = (target.height() - scaled.height()) // 2
        self.video_label.set_content_rect(x, y, scaled.width(), scaled.height())
        self.video_label.setPixmap(scaled)
        if self.request_capture and self.last_frame is not None:
            self.core.capture_media(self.last_frame)
            self.request_capture = False

    def closeEvent(self, event):
        self.timer.stop()
        self.core.close_all_media()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("CloutVision")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
