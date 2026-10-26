import sys
from PySide6.QtWidgets import QApplication
import account
import gui


def run_app():
    QApplication.instance() or QApplication(sys.argv)
    # Login is optional. If an account already exists, try to sync it
    # (best-effort, never blocks the app). Otherwise start straight away.
    if account.load_account() is not None:
        account.sync_to_server()
    gui.run()


if __name__ == "__main__":
    run_app()
