import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont, QIcon
from widget import SoundVolumeWidget, _resource_path


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Sound Volume")
    app.setWindowIcon(QIcon(_resource_path("ico.png")))
    app.setFont(QFont("Segoe UI", 10))

    win = SoundVolumeWidget()
    win.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
