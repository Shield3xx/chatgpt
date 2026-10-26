from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QListWidget,
    QMainWindow, QMessageBox, QPushButton, QTabWidget, QTextEdit,
    QVBoxLayout, QWidget, QProgressBar,
)
from pathlib import Path
import time

from login_dialog import LoginDialog
import account
from scanner import Scanner, ScanResult
from quarantine import quarantine_file, list_quarantined, restore_file, delete_quarantined
from monitor import RealtimeMonitor
import config
import database


class ScanWorker(QThread):
    """Runs scans off the UI thread so the window stays responsive."""
    progress = Signal(object)   # ScanResult
    finished_scan = Signal(int, int)  # scanned, infected

    def __init__(self, scanner: Scanner, target: Path):
        super().__init__()
        self.scanner = scanner
        self.target = target
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        scanned = infected = 0
        started = int(time.time())
        for result in self.scanner.scan_folder(
            self.target, should_stop=lambda: self._stop
        ):
            scanned += 1
            if result.infected:
                infected += 1
                try:
                    quarantine_file(Path(result.path), result.threat or "Unknown")
                except Exception as e:
                    result.error = f"Quarantine failed: {e}"
            self.progress.emit(result)
        database.add_scan_history(str(self.target), scanned, infected,
                                  started, int(time.time()))
        self.finished_scan.emit(scanned, infected)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(config.APP_NAME)
        self.resize(900, 600)

        try:
            self.scanner = Scanner()
        except RuntimeError as e:
            QMessageBox.critical(self, "ClamAV not running", str(e))
            self.scanner = None

        self.worker = None
        self.monitor = None

        root = QWidget(objectName="root")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)

        top = QHBoxLayout()
        self.btn_login = QPushButton("Log in", objectName="ghost")
        self.btn_login.clicked.connect(self._open_login)
        top.addWidget(self.btn_login, 0, Qt.AlignLeft | Qt.AlignTop)
        top.addStretch()
        self.btn_signup = QPushButton("Sign up", objectName="ghost")
        self.btn_signup.clicked.connect(self._open_signup)
        top.addWidget(self.btn_signup, 0, Qt.AlignRight | Qt.AlignTop)
        outer.addLayout(top)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        t = QLabel(config.APP_NAME, objectName="title")
        sub = QLabel("Antivirus protection for your files", objectName="subtitle")
        titles.addWidget(t)
        titles.addWidget(sub)
        header.addLayout(titles)
        header.addStretch()
        self.status_badge = QLabel("● Protected")
        self.status_badge.setStyleSheet(
            "color:#3ddc97; background:#16271f; border-radius:12px; padding:6px 12px;")
        header.addWidget(self.status_badge)
        outer.addLayout(header)

        self.tabs = QTabWidget()
        outer.addWidget(self.tabs)
        self.setCentralWidget(root)
        self.tabs.addTab(self._scan_tab(), "Scan")
        self.tabs.addTab(self._quarantine_tab(), "Quarantine")
        self.tabs.addTab(self._realtime_tab(), "Real-time")
        self._refresh_account_buttons()

        self.setStyleSheet("""
            QMainWindow, QWidget#root { background: #14151a; color: #e8eaf0;
                                        font-family: "Segoe UI", sans-serif; font-size: 13px; }
            QLabel#title { font-size: 20px; font-weight: 600; color: #ffffff; }
            QLabel#subtitle { color: #8b90a0; font-size: 12px; }
            QLabel#statValue { font-size: 22px; font-weight: 600; color: #ffffff; }
            QLabel#statLabel { color: #8b90a0; font-size: 11px; text-transform: uppercase; }
            QFrame#card { background: #1d1f26; border: 1px solid #2a2d36; border-radius: 10px; }
            QPushButton { background: #2f6fed; color: white; border: none;
                          padding: 9px 16px; border-radius: 7px; font-weight: 500; }
            QPushButton:hover { background: #4283f5; }
            QPushButton:pressed { background: #2459c4; }
            QPushButton:disabled { background: #2a2d36; color: #6b7080; }
            QPushButton#ghost { background: transparent; color: #c9cdd8;
                                border: 1px solid #353945; }
            QPushButton#ghost:hover { background: #242732; }
            QPushButton#danger { background: #c0392b; }
            QPushButton#danger:hover { background: #d9483b; }
            QTextEdit, QListWidget { background: #101116; border: 1px solid #2a2d36;
                                     border-radius: 8px; padding: 8px;
                                     selection-background-color: #2f6fed; }
            QListWidget::item { padding: 6px; border-radius: 4px; }
            QListWidget::item:selected { background: #2f6fed; }
            QTabWidget::pane { border: none; top: -1px; }
            QTabBar::tab { background: transparent; color: #8b90a0; padding: 10px 18px;
                           margin-right: 4px; border-bottom: 2px solid transparent;
                           font-weight: 500; }
            QTabBar::tab:selected { color: #ffffff; border-bottom: 2px solid #2f6fed; }
            QTabBar::tab:hover:!selected { color: #c9cdd8; }
            QProgressBar { border: none; background: #242732; border-radius: 3px;
                           height: 6px; }
            QProgressBar::chunk { background: #2f6fed; border-radius: 3px; }
            QMessageBox { background: #1d1f26; }
        """)

    def _stat_card(self, label: str, value: str) -> QFrame:
        card = QFrame(objectName="card")
        v = QVBoxLayout(card)
        v.setContentsMargins(16, 12, 16, 12)
        val = QLabel(value, objectName="statValue")
        lab = QLabel(label, objectName="statLabel")
        v.addWidget(val)
        v.addWidget(lab)
        card._value = val
        return card

    # ---- Scan tab ----
    def _scan_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        stats = QHBoxLayout()
        self.stat_scanned = self._stat_card("Files scanned", "0")
        self.stat_threats = self._stat_card("Threats found", "0")
        stats.addWidget(self.stat_scanned)
        stats.addWidget(self.stat_threats)
        layout.addLayout(stats)

        self.scan_log = QTextEdit(readOnly=True)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.hide()

        row = QHBoxLayout()
        self.btn_scan_file = QPushButton("Scan file")
        self.btn_scan_folder = QPushButton("Scan folder")
        self.btn_stop = QPushButton("Stop", objectName="ghost")
        self.btn_stop.setEnabled(False)
        row.addWidget(self.btn_scan_file)
        row.addWidget(self.btn_scan_folder)
        row.addWidget(self.btn_stop)

        self.btn_scan_file.clicked.connect(self._scan_file)
        self.btn_scan_folder.clicked.connect(self._scan_folder)
        self.btn_stop.clicked.connect(self._stop_scan)

        layout.addLayout(row)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.scan_log)
        return w

    def _scan_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose file to scan")
        if path:
            self._start_scan(Path(path))

    def _scan_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose folder to scan")
        if folder:
            self._start_scan(Path(folder))

    def _start_scan(self, target: Path):
        if not self.scanner:
            QMessageBox.warning(self, "Unavailable", "ClamAV is not connected.")
            return
        self.scan_log.clear()
        self.scan_log.append(f"Scanning {target} ...")
        self.progress_bar.show()
        self.btn_scan_file.setEnabled(False)
        self.btn_scan_folder.setEnabled(False)
        self.btn_stop.setEnabled(True)

        if target.is_file():
            result = self.scanner.scan_file(target)
            self._on_progress(result)
            now = int(time.time())
            database.add_scan_history(str(target), 1, 1 if result.infected else 0, now, now)
            self._on_finished(1, 1 if result.infected else 0)
            return

        self.worker = ScanWorker(self.scanner, target)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_scan.connect(self._on_finished)
        self.worker.start()

    def _stop_scan(self):
        if self.worker:
            self.worker.stop()

    def _on_progress(self, result: ScanResult):
        if result.error:
            self.scan_log.append(
                f'<span style="color:#f0b429">Error</span>&nbsp; {result.path}: {result.error}')
        elif result.infected:
            self.scan_log.append(
                f'<span style="color:#ff6b6b;font-weight:600">Threat</span>&nbsp; '
                f'{result.path} &rarr; {result.threat}')
        # clean files are not logged individually to keep the view fast

    def _on_finished(self, scanned: int, infected: int):
        self.progress_bar.hide()
        self.btn_scan_file.setEnabled(True)
        self.btn_scan_folder.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.stat_scanned._value.setText(str(scanned))
        self.stat_threats._value.setText(str(infected))
        self.scan_log.append(
            f'<br><span style="color:#8b90a0">Done. Scanned {scanned} files, '
            f'{infected} threat(s) quarantined.</span>')

    # ---- Quarantine tab ----
    def _quarantine_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self.q_list = QListWidget()
        row = QHBoxLayout()
        btn_refresh = QPushButton("Refresh", objectName="ghost")
        btn_restore = QPushButton("Restore", objectName="ghost")
        btn_delete = QPushButton("Delete permanently", objectName="danger")
        row.addWidget(btn_refresh)
        row.addWidget(btn_restore)
        row.addWidget(btn_delete)
        btn_refresh.clicked.connect(self._refresh_quarantine)
        btn_restore.clicked.connect(self._restore_selected)
        btn_delete.clicked.connect(self._delete_selected)
        layout.addLayout(row)
        layout.addWidget(self.q_list)
        self._refresh_quarantine()
        return w

    def _refresh_quarantine(self):
        self.q_list.clear()
        self._q_entries = list_quarantined()
        for e in self._q_entries:
            self.q_list.addItem(f"{e['threat']}  |  {e['original_path']}")

    def _selected_entry(self):
        row = self.q_list.currentRow()
        return self._q_entries[row] if 0 <= row < len(self._q_entries) else None

    def _restore_selected(self):
        e = self._selected_entry()
        if e:
            restore_file(e)
            self._refresh_quarantine()

    def _delete_selected(self):
        e = self._selected_entry()
        if e and QMessageBox.question(self, "Delete", "Permanently delete this file?") \
                == QMessageBox.Yes:
            delete_quarantined(e)
            self._refresh_quarantine()

    # ---- Real-time tab (paid feature) ----
    def _realtime_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self.rt_status = QLabel("Real-time protection: OFF")
        self.btn_rt = QPushButton("Start real-time protection")
        self.btn_rt.clicked.connect(self._toggle_realtime)
        layout.addWidget(self.rt_status)
        layout.addWidget(self.btn_rt)
        layout.addStretch()
        return w

    def _open_login(self):
        dlg = LoginDialog(self, mode="login")
        if dlg.exec() == LoginDialog.Accepted:
            self._refresh_account_buttons()

    def _open_signup(self):
        dlg = LoginDialog(self, mode="signup")
        if dlg.exec() == LoginDialog.Accepted:
            self._refresh_account_buttons()

    def _refresh_account_buttons(self):
        logged_in = account.load_account() is not None
        self.btn_login.setText("Logged in" if logged_in else "Log in")
        self.btn_signup.setVisible(not logged_in)

    def _toggle_realtime(self):
        # Real-time protection needs an account. Prompt for login/sign up if none.
        if account.load_account() is None:
            QMessageBox.information(
                self, "Account needed",
                "Real-time protection needs an account. Log in or sign up to continue.")
            self._open_signup()
            return
        # Gate: this will check the account/subscription once the backend exists.
        if not config.REALTIME_PROTECTION_ENABLED:
            QMessageBox.information(
                self, "Paid feature",
                "Real-time protection requires a paid plan."
            )
            return
        if self.monitor is None:
            self.monitor = RealtimeMonitor(self.scanner, self._on_realtime_threat)
            self.monitor.watch(str(Path.home() / "Downloads"))
            self.monitor.start()
            self.rt_status.setText("Real-time protection: ON (watching Downloads)")
            self.btn_rt.setText("Stop real-time protection")
        else:
            self.monitor.stop()
            self.monitor = None
            self.rt_status.setText("Real-time protection: OFF")
            self.btn_rt.setText("Start real-time protection")

    def _on_realtime_threat(self, path: str, threat: str):
        # Called from the watcher thread; hop back to the UI thread
        from PySide6.QtCore import QMetaObject, Q_ARG
        QMetaObject.invokeMethod(
            self.scan_log, "append", Qt.QueuedConnection,
            Q_ARG(str, f"[REAL-TIME] {path} -> {threat} (quarantined)")
        )

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait()
        if self.monitor:
            self.monitor.stop()
        super().closeEvent(event)


def run():
    database.init_db()
    app = QApplication.instance() or QApplication([])
    app.setApplicationName(config.APP_NAME)
    win = MainWindow()
    win.show()
    app.exec()