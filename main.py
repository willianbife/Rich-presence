import sys
import traceback
from datetime import datetime

from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow


def exception_hook(exctype, value, tb):
    """Captura exceções não tratadas e as salva em um log."""
    err_msg = "".join(traceback.format_exception(exctype, value, tb))
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("crash_report.log", "a", encoding="utf-8") as f:
        f.write(f"\n[{timestamp}] CRASH DETECTADO:\n{err_msg}\n{'-'*50}\n")
    print(err_msg, file=sys.stderr)
    sys.__excepthook__(exctype, value, tb)


sys.excepthook = exception_hook


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Discord Rich Presence Studio")
    app.setOrganizationName("Rich Presence Studio")

    try:
        window = MainWindow()
        window.show()
        return app.exec()
    except Exception:
        exception_hook(*sys.exc_info())
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
