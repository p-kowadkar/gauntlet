import sys
import signal
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont
from PyQt6.QtCore import QTimer
from ui.overlay import GauntletOverlay


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Gauntlet")
    app.setFont(QFont("Segoe UI", 10))

    # Allow Ctrl+C to kill the process cleanly from the terminal.
    # Qt's event loop blocks Python's default SIGINT handler on Windows --
    # restoring SIG_DFL lets the OS handle it directly.
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # QTimer ticks every 500ms so Python can process pending signals
    # (including SIGINT) while the Qt event loop is running.
    sigint_timer = QTimer()
    sigint_timer.start(500)
    sigint_timer.timeout.connect(lambda: None)

    overlay = GauntletOverlay()
    overlay.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
