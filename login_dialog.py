from PySide6.QtWidgets import (QDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QVBoxLayout)
import account


class LoginDialog(QDialog):
    def __init__(self, parent=None, mode="signup"):
        super().__init__(parent)
        self.mode = mode  # "login" or "signup"
        self.setWindowTitle("Log in" if mode == "login" else "Sign up")
        self.setMinimumWidth(360)

        self.email = QLineEdit(placeholderText="you@gmail.com")
        self.username = QLineEdit(placeholderText="Username")
        self.password = QLineEdit(placeholderText="Password")
        self.password.setEchoMode(QLineEdit.Password)

        saved = account.load_account()
        if saved:
            self.email.setText(saved["email"])
            self.username.setText(saved["username"])
            self.password.setText(saved["password"])

        form = QFormLayout()
        form.addRow("Gmail:", self.email)
        form.addRow("Username:", self.username)
        form.addRow("Password:", self.password)

        if mode == "login":
            self.username.hide()
            form.labelForField(self.username).hide()
        self.hint = QLabel("Scans work offline. Your details sync when you are online.")
        self.hint.setWordWrap(True)

        ok = QPushButton("Continue")
        ok.setDefault(True)
        ok.clicked.connect(self._accept)
        cancel = QPushButton("Quit")
        cancel.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(ok)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.hint)
        layout.addLayout(buttons)

    def _accept(self):
        if not account.valid_gmail(self.email.text()):
            QMessageBox.warning(self, "Check email", "Please enter a valid @gmail.com address.")
            return
        if self.mode == "signup" and not self.username.text().strip():
            QMessageBox.warning(self, "Check username", "Please enter a username.")
            return
        if len(self.password.text()) < 6:
            QMessageBox.warning(self, "Check password", "Password must be at least 6 characters.")
            return
        username = self.username.text() if self.mode == "signup" else \
            (account.load_account() or {}).get("username", "")
        account.save_account(self.email.text(), username, self.password.text())
        self.accept()
