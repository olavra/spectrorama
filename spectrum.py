import numpy as np
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QPainterPath

BG_COLOR    = QColor(28, 28, 30)
AVG_COLOR   = QColor(200, 200, 255)
LABEL_COLOR = QColor(120, 120, 130)
GRID_COLOR  = QColor(55, 55, 60)

# Color ramp: norm 0.0 = -80 dBFS, 1.0 = 0 dBFS
RAMP_STOPS = [
    (0.00, QColor(0x5E, 0xFF, 0xD1)),  # -80 dB
    (0.25, QColor(0x8F, 0xFF, 0x5E)),  # -60 dB
    (0.50, QColor(0xFF, 0xEF, 0x5E)),  # -40 dB
    (0.75, QColor(0xFF, 0x5E, 0x5E)),  # -20 dB
    (1.00, QColor(0xCF, 0x5E, 0xFF)),  #   0 dB
]


def _ramp_color(norm: float) -> QColor:
    n = max(0.0, min(1.0, norm))
    for i in range(len(RAMP_STOPS) - 1):
        t0, c0 = RAMP_STOPS[i]
        t1, c1 = RAMP_STOPS[i + 1]
        if n <= t1:
            f = (n - t0) / (t1 - t0)
            return QColor(
                int(c0.red()   + f * (c1.red()   - c0.red())),
                int(c0.green() + f * (c1.green() - c0.green())),
                int(c0.blue()  + f * (c1.blue()  - c0.blue())),
            )
    return RAMP_STOPS[-1][1]



DB_MIN  = -80.0
DB_MAX  =   0.0
FPS     = 30
LABEL_W = 34
LABEL_H = 16

TICK_DB = [0, -20, -40, -60, -80]

# ISO 1/3-octave center frequencies (Hz)
CENTERS = [
    20, 25, 31.5, 40, 50, 63, 80, 100, 125, 160,
    200, 250, 315, 400, 500, 630, 800, 1000, 1250, 1600,
    2000, 2500, 3150, 4000, 5000, 6300, 8000, 10000, 12500, 16000, 20000,
]
N_BANDS = len(CENTERS)
FACTOR  = 2 ** (1 / 6)
BOUNDS  = [(f / FACTOR, f * FACTOR) for f in CENTERS]

# Sparse X-axis labels (index → label string)
FREQ_LABELS = {
    2: "32", 5: "63", 8: "125", 11: "250", 14: "500",
    17: "1k", 20: "2k", 23: "4k", 26: "8k", 29: "16k",
}


def _to_db(v: float) -> float:
    return max(DB_MIN, 20.0 * np.log10(v) if v > 1e-9 else DB_MIN)


def _norm(db: float) -> float:
    return (db - DB_MIN) / (DB_MAX - DB_MIN)


FFT_SIZE = 8192  # ~5.4 Hz/bin at 44100 Hz — resolves all ISO bands down to 20 Hz


class SpectrumAnalyzer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._bars       = np.full(N_BANDS, DB_MIN, dtype=float)
        self._avg        = np.full(N_BANDS, DB_MIN, dtype=float)
        self._hold       = np.full(N_BANDS, DB_MIN, dtype=float)
        self._hold_count = np.zeros(N_BANDS, dtype=int)
        self._sample_rate = 44100
        self._ring        = np.zeros(FFT_SIZE, dtype=np.float32)
        self.setMinimumHeight(60)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000 // FPS)

    def set_sample_rate(self, rate: int):
        self._sample_rate = rate
        self._ring = np.zeros(FFT_SIZE, dtype=np.float32)

    def _tick(self):
        # Bar ballistics: fall 1.5 dB per frame
        self._bars = np.maximum(DB_MIN, self._bars - 1.5)
        # Peak hold: decay 0.4 dB/frame after hold expires
        self._hold_count = np.maximum(0, self._hold_count - 1)
        expired = self._hold_count == 0
        self._hold[expired] = np.maximum(DB_MIN, self._hold[expired] - 0.4)
        self.update()

    def push_samples(self, samples: np.ndarray):
        n = len(samples)
        if n == 0:
            return

        # Append new samples into the rolling buffer
        if n >= FFT_SIZE:
            self._ring[:] = samples[-FFT_SIZE:]
        else:
            self._ring = np.roll(self._ring, -n)
            self._ring[-n:] = samples

        fft_mag = np.abs(np.fft.rfft(self._ring)) * 2.0 / FFT_SIZE
        freqs   = np.fft.rfftfreq(FFT_SIZE, 1.0 / self._sample_rate)

        for i, (f_low, f_high) in enumerate(BOUNDS):
            mask = (freqs >= f_low) & (freqs < f_high)
            db   = _to_db(float(np.max(fft_mag[mask]))) if mask.any() else DB_MIN

            # Instant attack
            if db > self._bars[i]:
                self._bars[i] = db

            # Peak hold (1.5 s at 30 fps = 45 frames)
            if db >= self._hold[i]:
                self._hold[i]       = db
                self._hold_count[i] = 45

            # Slow EMA average (~3 s smoothing)
            self._avg[i] = 0.05 * db + 0.95 * self._avg[i]

    # ── Paint ────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        painter.fillRect(0, 0, w, h, BG_COLOR)

        font = QFont("Segoe UI", 7)
        painter.setFont(font)
        fm = painter.fontMetrics()

        plot_w = w - LABEL_W
        plot_h = h - LABEL_H
        band_w = plot_w / N_BANDS
        gap    = max(1.0, band_w * 0.12)

        # Y-axis grid + labels
        for db in TICK_DB:
            y_c   = plot_h - _norm(db) * plot_h
            label = str(db)
            lw    = fm.horizontalAdvance(label)
            ty    = int(y_c + fm.height() / 3)
            ty    = max(fm.ascent(), min(int(plot_h) - fm.descent(), ty))
            painter.setPen(QPen(LABEL_COLOR))
            painter.drawText(int(LABEL_W - lw - 4), ty, label)
            painter.setPen(QPen(GRID_COLOR, 1, Qt.PenStyle.DotLine))
            painter.drawLine(LABEL_W, int(y_c), w, int(y_c))

        # Bars + peak hold markers + X labels
        for i in range(N_BANDS):
            x  = LABEL_W + i * band_w
            bx = x + gap / 2
            bw = max(1.0, band_w - gap)

            # Bar — solid colour based on current level
            bar_h = _norm(self._bars[i]) * plot_h
            if bar_h > 0:
                top_y = int(plot_h - bar_h)
                painter.fillRect(int(bx), top_y, max(1, int(bw)), int(bar_h),
                                 _ramp_color(_norm(self._bars[i])))

            # Peak hold line — colour matches the ramp at that level
            if self._hold[i] > DB_MIN:
                hy = int(plot_h - _norm(self._hold[i]) * plot_h)
                c  = _ramp_color(_norm(self._hold[i]))
                c.setAlpha(220)
                painter.setPen(QPen(c, 1))
                painter.drawLine(int(bx), hy, int(bx + bw - 1), hy)

            # Frequency label (sparse)
            if i in FREQ_LABELS:
                label = FREQ_LABELS[i]
                lw    = fm.horizontalAdvance(label)
                painter.setPen(QPen(LABEL_COLOR))
                painter.drawText(int(x + band_w / 2 - lw / 2), h - 2, label)

        # Slow average line (green)
        avg_path = QPainterPath()
        for i, db_avg in enumerate(self._avg):
            x = LABEL_W + (i + 0.5) * band_w
            y = plot_h - _norm(db_avg) * plot_h
            if i == 0:
                avg_path.moveTo(x, y)
            else:
                avg_path.lineTo(x, y)
        painter.setPen(QPen(AVG_COLOR, 1.5))
        painter.drawPath(avg_path)

        painter.end()
