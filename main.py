import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont
from widget import SoundVolumeWidget


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Sound Volume")
    app.setFont(QFont("Segoe UI", 10))

    win = SoundVolumeWidget()
    win.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
