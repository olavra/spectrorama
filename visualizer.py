import numpy as np
from collections import deque
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QPainterPath

BG_COLOR    = QColor(28, 28, 30)
LABEL_COLOR = QColor(120, 120, 130)

BAND_KEYS = ("all", "low", "mid", "high")
BAND_COLORS = {
    "all":  QColor(0,   122, 255),
    "low":  QColor(255, 149,   0),
    "mid":  QColor(48,  209,  88),
    "high": QColor(191,  90, 242),
}
BAND_LABELS = {"all": "All", "low": "Low", "mid": "Mid", "high": "High"}

HISTORY = 300
FPS     = 30
LABEL_W = 40
LOW_MAX = 250
MID_MAX = 4000
DB_MIN  = -80.0
DB_MAX  =   0.0
TICK_DB = [0, -20, -40, -60, -80]


class VolumeVisualizer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._histories = {k: deque([DB_MIN] * HISTORY, maxlen=HISTORY) for k in BAND_KEYS}
        self._pending   = {k: None for k in BAND_KEYS}
        self._visible   = {"all": True, "low": False, "mid": False, "high": False}
        self._sample_rate = 44100
        self.setMinimumHeight(40)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000 // FPS)

    def set_sample_rate(self, rate: int):
        self._sample_rate = rate

    def set_band_visible(self, key: str, visible: bool):
        self._visible[key] = visible

    def _tick(self):
        for k in BAND_KEYS:
            val = self._pending[k] if self._pending[k] is not None else DB_MIN
            self._pending[k] = None
            self._histories[k].append(val)
        self.update()

    @staticmethod
    def _to_db(linear):
        if linear < 1e-9:
            return DB_MIN
        return max(DB_MIN, 20.0 * np.log10(linear))

    @staticmethod
    def _norm(db):
        return (db - DB_MIN) / (DB_MAX - DB_MIN)

    def push_samples(self, samples: np.ndarray):
        self._update_pending("all", self._to_db(float(np.max(np.abs(samples)))))
        n = len(samples)
        if n < 64:
            return
        fft_mag = np.abs(np.fft.rfft(samples)) * 2.0 / n
        freqs   = np.fft.rfftfreq(n, 1.0 / self._sample_rate)
        for key, mask in (
            ("low",  freqs <= LOW_MAX),
            ("mid",  (freqs > LOW_MAX) & (freqs <= MID_MAX)),
            ("high", freqs > MID_MAX),
        ):
            if mask.any():
                self._update_pending(key, self._to_db(float(np.max(fft_mag[mask]))))

    def _update_pending(self, key, db):
        if self._pending[key] is None or db > self._pending[key]:
            self._pending[key] = db

    # ── Paint ────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        painter.fillRect(0, 0, w, h, BG_COLOR)

        font = QFont("Segoe UI", 8)
        painter.setFont(font)
        fm      = painter.fontMetrics()
        plot_w  = w - LABEL_W

        self._draw_axis(painter, w, h, fm)

        # Draw in back-to-front order so "all" is always on top
        for key in ("low", "mid", "high", "all"):
            if not self._visible[key]:
                continue
            history = list(self._histories[key])
            bar_w   = max(1.0, plot_w / len(history))
            filled  = key == "all"
            self._draw_line(painter, history, BAND_COLORS[key], h, plot_w, bar_w, filled)

            peak = max(history)
            if peak > DB_MIN:
                self._draw_peak(painter, peak, w, h, fm, BAND_COLORS[key])

        painter.end()

    def _draw_axis(self, painter, w, h, fm):
        for db in TICK_DB:
            norm  = self._norm(db)
            y_c   = h - norm * h
            label = f"{db:d}"
            lw    = fm.horizontalAdvance(label)
            ty    = int(y_c + fm.height() / 3)
            ty    = max(fm.ascent(), min(h - fm.descent(), ty))
            painter.setPen(QPen(LABEL_COLOR))
            painter.drawText(int(LABEL_W - lw - 4), ty, label)
            painter.setPen(QPen(QColor(55, 55, 60), 1, Qt.PenStyle.DotLine))
            painter.drawLine(LABEL_W, int(y_c), w, int(y_c))

    def _draw_line(self, painter, history, color, h, plot_w, bar_w, filled):
        n = len(history)
        if n == 0:
            return

        def _pt(i, val):
            return (LABEL_W + (i + 0.5) * bar_w,
                    h - self._norm(val) * h)

        if filled:
            path = QPainterPath()
            path.moveTo(LABEL_W, h)
            for i, val in enumerate(history):
                path.lineTo(*_pt(i, val))
            path.lineTo(LABEL_W + plot_w, h)
            path.closeSubpath()
            fc = QColor(color)
            fc.setAlpha(35)
            painter.fillPath(path, fc)

        stroke = QPainterPath()
        for i, val in enumerate(history):
            x, y = _pt(i, val)
            if i == 0:
                stroke.moveTo(x, y)
            else:
                stroke.lineTo(x, y)
        painter.setPen(QPen(color, 1.5))
        painter.drawPath(stroke)

    def _draw_peak(self, painter, peak_db, w, h, fm, color):
        peak_y = int(h - self._norm(peak_db) * h)
        painter.setPen(QPen(color, 1))
        painter.drawLine(LABEL_W, peak_y, w, peak_y)
        label = f"{peak_db:.1f}"
        ty = peak_y - 3
        ty = max(fm.ascent(), min(h - fm.descent(), ty))
        painter.setPen(QPen(color))
        painter.drawText(LABEL_W + 4, ty, label)
