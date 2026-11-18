import logging
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

import customtkinter as ctk

log = logging.getLogger("ui")


def show_error(title: str, msg: str) -> None:
    log.error("%s: %s", title, msg)
    messagebox.showerror(title, msg)


def show_info(title: str, msg: str) -> None:
    messagebox.showinfo(title, msg)


def run_async(widget, fn, on_done=None, on_error=None) -> None:
    """Run fn() in a daemon thread; deliver result/exception back on the Tk thread."""
    q: queue.Queue = queue.Queue(maxsize=1)

    def worker():
        try:
            q.put((True, fn()))
        except Exception as e:  # noqa: BLE001 - surfaced to the UI
            log.exception("Background task failed")
            q.put((False, e))

    def poll():
        try:
            ok, val = q.get_nowait()
        except queue.Empty:
            if widget.winfo_exists():
                widget.after(100, poll)
            return
        if not widget.winfo_exists():
            return
        if ok:
            if on_done:
                on_done(val)
        elif on_error:
            on_error(val)
        else:
            show_error("Error", str(val))

    threading.Thread(target=worker, daemon=True).start()
    widget.after(100, poll)


class Spinner(ctk.CTkFrame):
    def __init__(self, master, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self.bar = ctk.CTkProgressBar(self, mode="indeterminate", width=160)
        self.label = ctk.CTkLabel(self, text="")
        self.label.pack(side="right")

    def start(self, text: str = "Working...") -> None:
        self.label.configure(text=text)
        if not self.bar.winfo_ismapped():
            self.bar.pack(side="left", padx=(0, 8))
        self.bar.start()

    def stop(self, text: str = "") -> None:
        self.bar.stop()
        self.bar.pack_forget()
        self.label.configure(text=text)


def make_tree(master, columns: list[tuple[str, str, int]], height: int = 12) -> tuple[ttk.Frame, ttk.Treeview]:
    """columns: [(key, heading, width)]"""
    frame = ttk.Frame(master)
    tree = ttk.Treeview(frame, columns=[c[0] for c in columns], show="headings", height=height,
                        selectmode="browse")
    for key, heading, width in columns:
        tree.heading(key, text=heading)
        tree.column(key, width=width, anchor="w", stretch=True)
    sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    tree.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    return frame, tree


def fill_tree(tree: ttk.Treeview, rows: list[tuple]) -> None:
    tree.delete(*tree.get_children())
    for row in rows:
        tree.insert("", "end", iid=str(row[0]), values=row)


def selected_id(tree: ttk.Treeview) -> int | None:
    sel = tree.selection()
    return int(sel[0]) if sel else None


def set_text(box: ctk.CTkTextbox, text: str) -> None:
    box.delete("1.0", tk.END)
    box.insert("1.0", text or "")


def get_text(box: ctk.CTkTextbox) -> str:
    return box.get("1.0", tk.END).strip()


def apply_scaling(root) -> float:
    """CustomTkinter auto-scales only on Windows/macOS; on Linux derive scale from screen height.
    Override with CG_UI_SCALE (e.g. 1.5)."""
    import os
    import sys
    env = os.environ.get("CG_UI_SCALE")
    if env:
        try:
            scale = max(0.5, float(env))
        except ValueError:
            scale = 1.0
    elif sys.platform.startswith("win") or sys.platform == "darwin":
        return 1.0
    else:
        scale = max(1.0, round(root.winfo_screenheight() / 1080 * 4) / 4)
    ctk.set_widget_scaling(scale)
    ctk.set_window_scaling(scale)
    root.tk.call("tk", "scaling", scale * 96 / 72)  # ttk/messagebox fonts
    log.info("UI scale %.2f", scale)
    return scale


FONT_PREFS = ["Segoe UI", "Ubuntu", "Noto Sans", "DejaVu Sans", "Cantarell", "Liberation Sans", "Helvetica"]


def apply_font(root) -> str:
    """Pick the first installed UI font (CustomTkinter defaults to Roboto, often missing)."""
    from tkinter import font as tkfont
    available = {f.lower() for f in tkfont.families(root)}
    family = next((f for f in FONT_PREFS if f.lower() in available), "TkDefaultFont")
    ctk.ThemeManager.theme["CTkFont"]["family"] = family
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        try:
            tkfont.nametofont(name, root).configure(family=family)
        except tk.TclError:
            pass
    log.info("UI font %s", family)
    return family


def style_ttk(root, scale: float = 1.0, family: str = "TkDefaultFont") -> None:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("Treeview", rowheight=int(26 * scale), font=(family, 10))
    style.configure("Treeview.Heading", font=(family, 10, "bold"))
