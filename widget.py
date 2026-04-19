from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox,
    QPushButton, QLabel, QApplication
)
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QPainter, QColor, QPainterPath, QCursor, QFontDatabase, QIcon
import os
import sys


def _resource_path(relative: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
    return os.path.join(base, relative)

from spectrum import SpectrumAnalyzer
from audio_capture import AudioCaptureThread
import ctypes
import ctypes.wintypes
from device_manager import get_output_devices, get_default_device_name, get_loopback_for_output, get_default_output_index

# Minimal MSG layout for reading the message-type field only (64-bit Windows)
class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd",    ctypes.c_void_p),
        ("message", ctypes.c_uint),
    ]

# ── Palette ──────────────────────────────────────────────────────────────────
BG         = QColor(28, 28, 30)
SURFACE    = QColor(38, 38, 40)
BORDER     = QColor(58, 58, 62)
BLUE       = QColor(0, 122, 255)
TEXT       = QColor(235, 235, 245)
TEXT_DIM   = QColor(140, 140, 150)
RADIUS     = 12

# ── WM_NCHITTEST constants ────────────────────────────────────────────────────
_EDGE         = 12     # px from window border treated as resize zone
_WM_NCHITTEST = 0x0084
_HTLEFT        = 10
_HTRIGHT       = 11
_HTTOP         = 12
_HTTOPLEFT     = 13
_HTTOPRIGHT    = 14
_HTBOTTOM      = 15
_HTBOTTOMLEFT  = 16
_HTBOTTOMRIGHT = 17


class DragHandle(QLabel):
    """Logo label that also lets the user drag the window."""
    def __init__(self, parent):
        super().__init__("Spectrorama dBFS", parent)
        self._drag_pos = None

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.window().frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag_pos and e.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, e):
        self._drag_pos = None


class SoundVolumeWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._pinned = True
        self._capture = None

        self._init_window()
        self._build_ui()
        self._start_capture()

    # ── Window setup ─────────────────────────────────────────────────────────

    def _init_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setWindowIcon(QIcon(_resource_path("ico.png")))
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setMinimumSize(320, 120)
        settings = QSettings("Spectrorama", "Spectrorama")
        geometry = settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            self.resize(480, 480)
        self.setSizePolicy(
            self.sizePolicy().horizontalPolicy(),
            self.sizePolicy().verticalPolicy(),
        )

    def showEvent(self, event):
        super().showEvent(event)
        # Disable Windows 11 automatic rounded corners so only our painted
        # border is visible (otherwise two rounded borders appear).
        try:
            DWMWA_WINDOW_CORNER_PREFERENCE = 33
            DONOTROUND = 1
            hwnd = int(self.winId())
            pref = ctypes.c_int(DONOTROUND)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
                ctypes.byref(pref), ctypes.sizeof(pref)
            )
        except Exception:
            pass

    # ── UI ───────────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._container = QWidget(self)
        self._container.setObjectName("container")
        outer.addWidget(self._container)

        root = QVBoxLayout(self._container)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(6)

        # Title bar row
        bar = QHBoxLayout()
        bar.setSpacing(8)

        drag = DragHandle(self)
        drag.setObjectName("logo")
        drag.setFixedHeight(20)
        drag.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))
        bar.addWidget(drag, 1)

        # Floor limit selector
        floor_label = QLabel("Floor")
        floor_label.setFixedWidth(28)
        bar.addWidget(floor_label)

        self._floor_combo = QComboBox()
        self._floor_combo.setFixedWidth(68)
        self._floor_combo.setFixedHeight(20)
        for val in [-80, -100, -120, -140, -160]:
            self._floor_combo.addItem(f"{val} dB", val)
        self._floor_combo.currentIndexChanged.connect(self._on_floor_changed)
        bar.addWidget(self._floor_combo)

        # Pin button
        self._pin_btn = QPushButton("⬘")
        self._pin_btn.setFixedSize(28, 20)
        self._pin_btn.setCheckable(True)
        self._pin_btn.setChecked(True)
        self._pin_btn.clicked.connect(self._toggle_pin)
        bar.addWidget(self._pin_btn)

        # Close button
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.clicked.connect(self.close)
        bar.addWidget(close_btn)

        root.addLayout(bar)

        self._spectrum = SpectrumAnalyzer()
        self._spectrum.setMinimumHeight(40)
        root.addWidget(self._spectrum, stretch=1)

        # Restore saved preferences
        _s = QSettings("Spectrorama", "Spectrorama")
        floor_idx = int(_s.value("floor_index", 2))
        pinned    = _s.value("pinned", True, type=bool)
        self._floor_combo.setCurrentIndex(floor_idx)       # triggers _on_floor_changed
        self._pin_btn.setChecked(pinned)
        self._toggle_pin(pinned)

        # Device row
        dev_row = QHBoxLayout()
        dev_row.setSpacing(8)

        dev_label = QLabel("Output")
        dev_label.setFixedWidth(40)
        dev_row.addWidget(dev_label)

        self._device_combo = QComboBox()
        self._device_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self._populate_devices()
        self._device_combo.currentIndexChanged.connect(self._on_device_changed)
        dev_row.addWidget(self._device_combo, 1)

        root.addLayout(dev_row)

        self._apply_styles()

    def _apply_styles(self):
        blue_hex = BLUE.name()
        _fid = QFontDatabase.addApplicationFont(
            _resource_path("VintageLegacy-Regular.otf")
        )
        logo_font = (
            f"'{QFontDatabase.applicationFontFamilies(_fid)[0]}'"
            if _fid >= 0 else "'Segoe UI'"
        )
        self.setStyleSheet(f"""
            QWidget#container {{
                background: transparent;
            }}
            QWidget {{
                color: {TEXT.name()};
                font-family: 'Segoe UI', system-ui, sans-serif;
                font-size: 12px;
            }}
            QComboBox {{
                background: {SURFACE.name()};
                border: 1px solid {BORDER.name()};
                border-radius: 6px;
                padding: 3px 8px;
                color: {TEXT.name()};
            }}
            QComboBox::drop-down {{
                border: none;
                padding-right: 6px;
            }}
            QComboBox QAbstractItemView {{
                background: {SURFACE.name()};
                border: 1px solid {BORDER.name()};
                selection-background-color: {blue_hex};
                outline: none;
            }}
            QPushButton {{
                background: {SURFACE.name()};
                border: 1px solid {BORDER.name()};
                border-radius: 5px;
                color: {TEXT_DIM.name()};
                font-size: 11px;
            }}
            QPushButton:hover {{
                border-color: {blue_hex};
                color: {TEXT.name()};
            }}
            QPushButton:checked {{
                background: {blue_hex};
                border-color: {blue_hex};
                color: white;
            }}
            QLabel {{
                color: {TEXT_DIM.name()};
                font-size: 11px;
            }}
            QLabel#logo {{
                color: {TEXT.name()};
                font-family: {logo_font};
                font-size: 13px;
                font-weight: 400;
                letter-spacing: 0.5px;
            }}
        """)

    # ── Painting (rounded card) ───────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        r = self.rect()
        path = QPainterPath()
        path.addRoundedRect(r.x() + 0.5, r.y() + 0.5, r.width() - 1, r.height() - 1, RADIUS, RADIUS)

        p.fillPath(path, BG)
        from PyQt6.QtGui import QPen
        pen = QPen(BORDER, 1.0)
        p.setPen(pen)
        p.drawPath(path)
        p.end()

    # ── Native hit-test: resize cursors + drag work through child widgets ────────

    def nativeEvent(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            addr = int(message)
            if addr:
                msg = _MSG.from_address(addr)
                if msg.message == _WM_NCHITTEST:
                    pos = self.mapFromGlobal(QCursor.pos())
                    x, y = pos.x(), pos.y()
                    w, h = self.width(), self.height()

                    left   = x < _EDGE
                    right  = x > w - _EDGE
                    top    = y < _EDGE
                    bottom = y > h - _EDGE

                    if top    and left:  return True, _HTTOPLEFT
                    if top    and right: return True, _HTTOPRIGHT
                    if bottom and left:  return True, _HTBOTTOMLEFT
                    if bottom and right: return True, _HTBOTTOMRIGHT
                    if left:             return True, _HTLEFT
                    if right:            return True, _HTRIGHT
                    if top:              return True, _HTTOP
                    if bottom:           return True, _HTBOTTOM
        return False, 0

    # ── Device management ────────────────────────────────────────────────────

    def _populate_devices(self):
        self._devices = get_output_devices()
        default_output_idx = get_default_output_index()
        self._device_combo.blockSignals(True)
        self._device_combo.clear()
        default_combo_idx = 0
        for i, (name, sd_idx) in enumerate(self._devices):
            self._device_combo.addItem(name)
            if sd_idx == default_output_idx:
                default_combo_idx = i
        self._device_combo.setCurrentIndex(default_combo_idx)
        self._device_combo.blockSignals(False)

    def _on_device_changed(self, combo_idx):
        if 0 <= combo_idx < len(self._devices):
            _, sd_idx = self._devices[combo_idx]
            self._restart_capture(sd_idx)

    # ── Audio capture ────────────────────────────────────────────────────────

    def _start_capture(self):
        combo_idx = self._device_combo.currentIndex()
        sd_idx = self._devices[combo_idx][1] if self._devices else None
        self._restart_capture(sd_idx)

    def _restart_capture(self, output_idx):
        if self._capture:
            self._capture.stop()
            self._capture = None

        loopback_idx, rate, channels = get_loopback_for_output(output_idx)
        if loopback_idx is None:
            print(f"[Widget] No loopback device found for output {output_idx}")
            return

        self._spectrum.set_sample_rate(rate)
        self._capture = AudioCaptureThread(
            loopback_index=loopback_idx,
            sample_rate=rate,
            channels=channels,
        )
        self._capture.samples_ready.connect(self._spectrum.push_samples)
        self._capture.start()

    def _on_floor_changed(self, idx):
        val = self._floor_combo.currentData()
        self._spectrum.set_floor(float(val))

    # ── Always on top toggle ─────────────────────────────────────────────────

    def _toggle_pin(self, checked):
        SWP_NOMOVE     = 0x0002
        SWP_NOSIZE     = 0x0001
        SWP_NOACTIVATE = 0x0010
        hwnd         = ctypes.c_void_p(int(self.winId()))
        insert_after = ctypes.c_void_p(-1 if checked else -2)
        ctypes.windll.user32.SetWindowPos(
            hwnd, insert_after, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
        )

    # ── Cleanup ──────────────────────────────────────────────────────────────

    def closeEvent(self, e):
        settings = QSettings("Spectrorama", "Spectrorama")
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("floor_index", self._floor_combo.currentIndex())
        settings.setValue("pinned", self._pin_btn.isChecked())
        if self._capture:
            self._capture.stop()
        super().closeEvent(e)
        QApplication.quit()
