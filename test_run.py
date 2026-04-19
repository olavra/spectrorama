import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont

app = QApplication(sys.argv)
app.setFont(QFont("Segoe UI", 10))

try:
    from widget import SoundVolumeWidget
    w = SoundVolumeWidget()
    w.show()
    print("SUCCESS: window shown")
except Exception as e:
    import traceback
    traceback.print_exc()
    print("FAILED:", e)
