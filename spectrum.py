import numpy as np
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QPainterPath

BG_COLOR    = QColor(28, 28, 30)
AVG_COLOR   = QColor(200, 200, 255)
LABEL_COLOR = QColor(120, 120, 130)
GRID_COLOR  = QColor(55, 55, 60)
GREEN_COLOR = QColor(0x5E, 0xFF, 0xD1)  # fixed green for levels ≤ -80 dBFS

DB_FLOOR_FIXED = -80.0  # color boundary; below this is always green
DB_MAX         =   0.0
FPS            =  30
LABEL_W        =  34
LABEL_H        =  16

# Color ramp: norm 0.0 = -80 dBFS, 1.0 = 0 dBFS
RAMP_STOPS = [
    (0.00, QColor(0x5E, 0xFF, 0xD1)),  # -80 dB
    (0.25, QColor(0x8F, 0xFF, 0x5E)),  # -60 dB
    (0.50, QColor(0xFF, 0xEF, 0x5E)),  # -40 dB
    (0.75, QColor(0xFF, 0x5E, 0x5E)),  # -20 dB
    (1.00, QColor(0xCF, 0x5E, 0xFF)),  #   0 dB
]

# ISO 1/3-octave center frequencies (Hz)
CENTERS = [
    20, 25, 31.5, 40, 50, 63, 80, 100, 125, 160,
    200, 250, 315, 400, 500, 630, 800, 1000, 1250, 1600,
    2000, 2500, 3150, 4000, 5000, 6300, 8000, 10000, 12500, 16000, 20000,
]
N_BANDS = len(CENTERS)
FACTOR  = 2 ** (1 / 6)
BOUNDS  = [(f / FACTOR, f * FACTOR) for f in CENTERS]

FREQ_LABELS = {
    2: "32", 5: "63", 8: "125", 11: "250", 14: "500",
    17: "1k", 20: "2k", 23: "4k", 26: "8k", 29: "16k",
}


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


FFT_SIZE = 8192  # ~5.4 Hz/bin at 44100 Hz — resolves all ISO bands down to 20 Hz


class SpectrumAnalyzer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._db_min      = DB_FLOOR_FIXED
        self._bars        = np.full(N_BANDS, DB_FLOOR_FIXED, dtype=float)
        self._avg         = np.full(N_BANDS, DB_FLOOR_FIXED, dtype=float)
        self._hold        = np.full(N_BANDS, DB_FLOOR_FIXED, dtype=float)
        self._hold_count  = np.zeros(N_BANDS, dtype=int)
        self._sample_rate = 44100
        self._ring        = np.zeros(FFT_SIZE, dtype=np.float32)
        self.setMinimumHeight(60)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000 // FPS)

    def set_sample_rate(self, rate: int):
        self._sample_rate = rate
        self._ring = np.zeros(FFT_SIZE, dtype=np.float32)

    def set_floor(self, db_min: float):
        self._db_min = db_min
        self._bars[:] = db_min
        self._avg[:] = db_min
        self._hold[:] = db_min
        self._hold_count[:] = 0

    def _norm_pos(self, db: float) -> float:
        return max(0.0, min(1.0, (db - self._db_min) / (DB_MAX - self._db_min)))

    def _norm_color(self, db: float) -> float:
        return max(0.0, min(1.0, (db - DB_FLOOR_FIXED) / (DB_MAX - DB_FLOOR_FIXED)))

    def _to_db(self, v: float) -> float:
        return max(self._db_min, 20.0 * np.log10(v) if v > 1e-9 else self._db_min)

    def _tick(self):
        self._bars = np.maximum(self._db_min, self._bars - 1.5)
        self._hold_count = np.maximum(0, self._hold_count - 1)
        expired = self._hold_count == 0
        self._hold[expired] = np.maximum(self._db_min, self._hold[expired] - 0.4)
        self.update()

    def push_samples(self, samples: np.ndarray):
        n = len(samples)
        if n == 0:
            return

        if n >= FFT_SIZE:
            self._ring[:] = samples[-FFT_SIZE:]
        else:
            self._ring = np.roll(self._ring, -n)
            self._ring[-n:] = samples

        fft_mag = np.abs(np.fft.rfft(self._ring)) * 2.0 / FFT_SIZE
        freqs   = np.fft.rfftfreq(FFT_SIZE, 1.0 / self._sample_rate)

        for i, (f_low, f_high) in enumerate(BOUNDS):
            mask = (freqs >= f_low) & (freqs < f_high)
            if mask.any():
                db = self._to_db(float(np.max(fft_mag[mask])))
            else:
                nearest = np.argmin(np.abs(freqs - CENTERS[i]))
                db = self._to_db(float(fft_mag[nearest]))

            if db > self._bars[i]:
                self._bars[i] = db

            if db >= self._hold[i]:
                self._hold[i]       = db
                self._hold_count[i] = 45

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

        # Dynamic ticks: every 20 dB from 0 down to floor
        ticks = list(range(0, int(self._db_min) - 1, -20))
        if int(self._db_min) not in ticks:
            ticks.append(int(self._db_min))

        # Y-axis grid + labels
        for db in ticks:
            y_c   = plot_h - self._norm_pos(db) * plot_h
            label = str(db)
            lw    = fm.horizontalAdvance(label)
            ty    = int(y_c + fm.height() / 3)
            ty    = max(fm.ascent(), min(int(plot_h) - fm.descent(), ty))
            line_color = GREEN_COLOR if db <= DB_FLOOR_FIXED else _ramp_color(self._norm_color(db))
            line_color = QColor(line_color)
            line_color.setAlpha(80)
            painter.setPen(QPen(line_color))
            painter.drawText(int(LABEL_W - lw - 4), ty, label)
            painter.setPen(QPen(line_color, 1, Qt.PenStyle.DotLine))
            painter.drawLine(LABEL_W, int(y_c), w, int(y_c))

        # Bars + peak hold markers + X labels
        for i in range(N_BANDS):
            x  = LABEL_W + i * band_w
            bx = x + gap / 2
            bw = max(1.0, band_w - gap)

            bar_h = self._norm_pos(self._bars[i]) * plot_h
            if bar_h > 0:
                green_h = self._norm_pos(DB_FLOOR_FIXED) * plot_h  # 0 when floor == -80

                if self._bars[i] <= DB_FLOOR_FIXED:
                    # Entire bar is in the green zone
                    painter.fillRect(int(bx), int(plot_h - bar_h),
                                     max(1, int(bw)), int(bar_h), GREEN_COLOR)
                else:
                    # Ramp-colored section above -80 dBFS
                    ramp_h = bar_h - green_h
                    painter.fillRect(int(bx), int(plot_h - bar_h),
                                     max(1, int(bw)), max(1, int(ramp_h)),
                                     _ramp_color(self._norm_color(self._bars[i])))
                    # Green section below -80 dBFS (only when floor is extended)
                    if green_h > 0:
                        painter.fillRect(int(bx), int(plot_h - green_h),
                                         max(1, int(bw)), int(green_h), GREEN_COLOR)

            # Peak hold line
            if self._hold[i] > self._db_min:
                hy = int(plot_h - self._norm_pos(self._hold[i]) * plot_h)
                if self._hold[i] <= DB_FLOOR_FIXED:
                    c = QColor(GREEN_COLOR)
                else:
                    c = _ramp_color(self._norm_color(self._hold[i]))
                c.setAlpha(220)
                painter.setPen(QPen(c, 1))
                painter.drawLine(int(bx), hy, int(bx + bw - 1), hy)

            # Frequency label (sparse)
            if i in FREQ_LABELS:
                label = FREQ_LABELS[i]
                lw    = fm.horizontalAdvance(label)
                painter.setPen(QPen(LABEL_COLOR))
                painter.drawText(int(x + band_w / 2 - lw / 2), h - 2, label)

        # Slow average line
        avg_path = QPainterPath()
        for i, db_avg in enumerate(self._avg):
            x = LABEL_W + (i + 0.5) * band_w
            y = plot_h - self._norm_pos(db_avg) * plot_h
            if i == 0:
                avg_path.moveTo(x, y)
            else:
                avg_path.lineTo(x, y)
        painter.setPen(QPen(AVG_COLOR, 1.5))
        painter.drawPath(avg_path)

        painter.end()
