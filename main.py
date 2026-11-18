import logging
import sys
from tkinter import messagebox

import config

config.setup_logging()
log = logging.getLogger("main")

import customtkinter as ctk  # noqa: E402

import db  # noqa: E402
import kb  # noqa: E402
from ui import apply_font, apply_scaling, run_async, show_error, style_ttk  # noqa: E402
from ui.admin import AdminFrame  # noqa: E402
from ui.consumer import ConsumerFrame  # noqa: E402
from ui.login import LoginFrame  # noqa: E402


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        scale = apply_scaling(self)
        family = apply_font(self)
        self.title("ConsumerGuard")
        self.geometry("1180x760")
        self.minsize(980, 640)
        style_ttk(self, scale, family)
        self.frame = None
        self.show_login()
        run_async(self, kb.startup_sync,
                  on_done=lambda r: log.info("KB startup: %s", r),
                  on_error=lambda e: log.warning("KB startup failed: %s", e))

    def report_callback_exception(self, exc, val, tb):
        log.error("Unhandled UI error", exc_info=(exc, val, tb))
        show_error("Unexpected error", f"{val}\n\nDetails were written to:\n{config.LOG_PATH}")

    def _switch(self, frame):
        if self.frame is not None:
            self.frame.destroy()
        self.frame = frame
        frame.pack(fill="both", expand=True)

    def show_login(self):
        self._switch(LoginFrame(self, on_login=self.on_login))

    def on_login(self, user: dict):
        cls = AdminFrame if user["role"] == "admin" else ConsumerFrame
        self._switch(cls(self, user, on_logout=self.show_login))


def _excepthook(exc, val, tb):
    log.critical("Uncaught exception", exc_info=(exc, val, tb))


def main():
    sys.excepthook = _excepthook
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")
    try:
        db.init_db()
    except Exception as e:
        log.exception("Database init failed")
        messagebox.showerror("ConsumerGuard", f"Could not open database:\n{e}")
        return
    log.info("Starting ConsumerGuard, data dir %s", config.DATA_DIR)
    App().mainloop()


if __name__ == "__main__":
    main()
