import logging
import shutil
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk
from pydantic import ValidationError

import classifier
import db
import pdf
import rag
from models import ComplaintIn, friendly
from ui import (Spinner, fill_tree, get_text, make_tree, run_async, selected_id, set_text,
                show_error, show_info)

log = logging.getLogger(__name__)

STATES = ["Andaman and Nicobar Islands", "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar",
          "Chandigarh", "Chhattisgarh", "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Goa",
          "Gujarat", "Haryana", "Himachal Pradesh", "Jammu and Kashmir", "Jharkhand", "Karnataka",
          "Kerala", "Ladakh", "Lakshadweep", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya",
          "Mizoram", "Nagaland", "Odisha", "Puducherry", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu",
          "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal"]
STATE_PLACEHOLDER = "Select state"
POLL_MS = 15000


def download_pdf(case: dict) -> None:
    src = Path(case["pdf_path"]) if case.get("pdf_path") else None
    if not src or not src.exists():
        show_error("No PDF", "No PDF exists for this complaint yet. Generate a draft and export it first.")
        return
    dest = filedialog.asksaveasfilename(defaultextension=".pdf", initialfile=src.name,
                                        filetypes=[("PDF", "*.pdf")])
    if dest:
        try:
            shutil.copyfile(src, dest)
            show_info("Saved", f"PDF saved to:\n{dest}")
        except OSError as e:
            show_error("Save failed", str(e))


class ConsumerFrame(ctk.CTkFrame):
    def __init__(self, master, user: dict, on_logout):
        super().__init__(master, fg_color="transparent")
        self.user = user
        self.case_id: int | None = None

        top = ctk.CTkFrame(self, height=50)
        top.pack(fill="x", padx=10, pady=(10, 0))
        ctk.CTkLabel(top, text=f"ConsumerGuard  ·  {user['name']}",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(side="left", padx=12, pady=8)
        ctk.CTkButton(top, text="Logout", width=80, fg_color="gray40", command=on_logout).pack(side="right", padx=8)
        self.bell = ctk.CTkButton(top, text="Notifications (0)", width=140,
                                  command=lambda: self._goto("Notifications"))
        self.bell.pack(side="right", padx=8)

        self.tabs = ctk.CTkTabview(self, command=self._on_tab)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=10)
        self._build_file(self.tabs.add("File Complaint"))
        self._build_history(self.tabs.add("My Complaints"))
        self._build_notifs(self.tabs.add("Notifications"))

        self.refresh_history()
        self._poll()

    # ---------- file complaint ----------
    def _build_file(self, tab):
        tab.grid_columnconfigure(0, weight=2)
        tab.grid_columnconfigure(1, weight=3)
        tab.grid_rowconfigure(0, weight=1)

        form = ctk.CTkFrame(tab)
        form.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        form.grid_columnconfigure(0, weight=1)
        r = 0

        def label(text):
            nonlocal r
            ctk.CTkLabel(form, text=text, anchor="w").grid(row=r, column=0, sticky="w", padx=12, pady=(8, 0))
            r += 1

        def place(w, **kw):
            nonlocal r
            w.grid(row=r, column=0, padx=12, **{"pady": 2, "sticky": "ew", **kw})
            r += 1

        label("Opposite party (seller / company)")
        self.opp = ctk.CTkEntry(form)
        place(self.opp)
        label("State *")
        self.state = ctk.CTkOptionMenu(form, values=STATES, dynamic_resizing=False)
        self.state.set(STATE_PLACEHOLDER)
        place(self.state)
        label("District")
        self.district = ctk.CTkEntry(form)
        place(self.district)
        label("Value of goods/services (₹) *")
        self.value = ctk.CTkEntry(form, placeholder_text="e.g. 45000")
        self.value.bind("<KeyRelease>", lambda _e: self._live_forum())
        place(self.value)
        label("What happened? * (min 50 characters)")
        self.text = ctk.CTkTextbox(form, height=180, wrap="word")
        place(self.text, sticky="nsew")
        form.grid_rowconfigure(r - 1, weight=1)
        self.info = ctk.CTkLabel(form, text="Forum: —", anchor="w", justify="left",
                                 font=ctk.CTkFont(weight="bold"))
        place(self.info)
        btns = ctk.CTkFrame(form, fg_color="transparent")
        place(btns, pady=(6, 12))
        ctk.CTkButton(btns, text="Submit complaint", command=self._submit).pack(side="left")
        ctk.CTkButton(btns, text="New", width=70, fg_color="gray40", command=self._reset).pack(side="left", padx=8)

        right = ctk.CTkFrame(tab)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(2, weight=1)
        self.case_lbl = ctk.CTkLabel(right, text="Draft — submit a complaint first", anchor="w",
                                     font=ctk.CTkFont(size=14, weight="bold"))
        self.case_lbl.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        bar = ctk.CTkFrame(right, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="ew", padx=12)
        self.gen_btn = ctk.CTkButton(bar, text="Generate draft", state="disabled", command=self._generate)
        self.gen_btn.pack(side="left")
        self.spinner = Spinner(bar)
        self.spinner.pack(side="left", padx=10)
        self.draft = ctk.CTkTextbox(right, wrap="word")
        self.draft.grid(row=2, column=0, sticky="nsew", padx=12, pady=8)
        bar2 = ctk.CTkFrame(right, fg_color="transparent")
        bar2.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 12))
        self.save_btn = ctk.CTkButton(bar2, text="Save draft", state="disabled", command=self._save_draft)
        self.save_btn.pack(side="left")
        self.pdf_btn = ctk.CTkButton(bar2, text="Export PDF", state="disabled", command=self._export)
        self.pdf_btn.pack(side="left", padx=8)

    def _live_forum(self):
        raw = self.value.get().replace(",", "").replace("₹", "").strip()
        try:
            v = float(raw)
            if v <= 0:
                raise ValueError
        except ValueError:
            self.info.configure(text="Forum: —")
            return
        f = classifier.pick_forum(v)
        self.info.configure(text=f"Forum: {classifier.FORUM_NAMES[f]}")

    def _reset(self):
        self.case_id = None
        self.opp.delete(0, "end")
        self.district.delete(0, "end")
        self.value.delete(0, "end")
        self.state.set(STATE_PLACEHOLDER)
        set_text(self.text, "")
        set_text(self.draft, "")
        self.info.configure(text="Forum: —")
        self.case_lbl.configure(text="Draft — submit a complaint first")
        for b in (self.gen_btn, self.save_btn, self.pdf_btn):
            b.configure(state="disabled")

    def _submit(self):
        state = self.state.get()
        try:
            data = ComplaintIn(text=get_text(self.text), value=self.value.get(),
                               state="" if state == STATE_PLACEHOLDER else state,
                               district=self.district.get(), opposite_party=self.opp.get())
        except ValidationError as e:
            show_error("Please fix the form", friendly(e))
            return
        category, forum = classifier.classify(data.text, data.value)
        try:
            cid = db.create_case(self.user["id"], data.text, data.value, data.state, data.district,
                                 category, forum, data.opposite_party)
        except Exception as e:
            log.exception("create_case failed")
            show_error("Could not save complaint", str(e))
            return
        self._load_case(cid)
        self.refresh_history()

    def _load_case(self, cid: int):
        case = db.get_case(cid)
        if not case:
            return
        self.case_id = cid
        self.info.configure(text=f"Category: {case['category']}\n"
                                 f"Forum: {classifier.forum_heading(case['forum'], case['state'], case['district'])}")
        self.case_lbl.configure(text=f"Draft — Complaint #{cid} ({case['status']})")
        set_text(self.draft, case.get("draft") or "")
        self.gen_btn.configure(state="normal")
        has_draft = bool(case.get("draft"))
        self.save_btn.configure(state="normal" if has_draft else "disabled")
        self.pdf_btn.configure(state="normal" if has_draft else "disabled")

    def _generate(self):
        if not self.case_id:
            return
        case, user = db.get_case(self.case_id), self.user
        self.gen_btn.configure(state="disabled")
        self.spinner.start("Retrieving law and drafting...")

        def done(res):
            self.spinner.stop(res["note"])
            self.gen_btn.configure(state="normal")
            set_text(self.draft, res["draft"])
            fields = {"draft": res["draft"]}
            if case["status"] == "submitted":
                fields["status"] = "drafted"
            db.update_case(case["id"], **fields)
            self._load_case(case["id"])
            self.spinner.stop(res["note"])
            self.refresh_history()

        def fail(e):
            self.spinner.stop()
            self.gen_btn.configure(state="normal")
            show_error("Drafting failed", str(e))

        run_async(self, lambda: rag.generate_draft(case, user), done, fail)

    def _save_draft(self) -> bool:
        text = get_text(self.draft)
        if len(text) < 50:
            show_error("Draft too short", "The draft is empty or too short.")
            return False
        try:
            db.update_case(self.case_id, draft=text)
        except Exception as e:
            show_error("Save failed", str(e))
            return False
        return True

    def _export(self):
        if not self.case_id or not self._save_draft():
            return
        case, user, text = db.get_case(self.case_id), self.user, get_text(self.draft)
        self.pdf_btn.configure(state="disabled")
        self.spinner.start("Building PDF...")

        def done(path):
            self.spinner.stop("PDF ready.")
            self.pdf_btn.configure(state="normal")
            db.update_case(case["id"], pdf_path=str(path))
            self.refresh_history()
            download_pdf(db.get_case(case["id"]))

        def fail(e):
            self.spinner.stop()
            self.pdf_btn.configure(state="normal")
            show_error("PDF export failed", str(e))

        run_async(self, lambda: pdf.build_pdf(case, user, text), done, fail)

    # ---------- history ----------
    def _build_history(self, tab):
        bar = ctk.CTkFrame(tab, fg_color="transparent")
        bar.pack(fill="x", pady=(0, 6))
        ctk.CTkButton(bar, text="Refresh", width=90, command=self.refresh_history).pack(side="left")
        ctk.CTkButton(bar, text="Open in editor", command=self._open_selected).pack(side="left", padx=8)
        ctk.CTkButton(bar, text="Download PDF", command=self._download_selected).pack(side="left")
        frame, self.hist = make_tree(tab, [("id", "#", 50), ("date", "Filed", 150), ("category", "Category", 110),
                                           ("forum", "Forum", 90), ("value", "Value (Rs.)", 120),
                                           ("status", "Status", 110), ("note", "Admin note", 300)])
        frame.pack(fill="both", expand=True)
        self.hist.bind("<Double-1>", lambda _e: self._open_selected())

    def refresh_history(self):
        rows = db.list_cases(user_id=self.user["id"])
        fill_tree(self.hist, [(c["id"], c["created_at"].replace("T", " "), c["category"], c["forum"],
                               classifier.format_inr(c["value"]), c["status"], c["admin_note"] or "")
                              for c in rows])

    def _open_selected(self):
        cid = selected_id(self.hist)
        if cid is None:
            show_error("Select a complaint", "Select a complaint first.")
            return
        self._load_case(cid)
        self.tabs.set("File Complaint")

    def _download_selected(self):
        cid = selected_id(self.hist)
        if cid is None:
            show_error("Select a complaint", "Select a complaint first.")
            return
        download_pdf(db.get_case(cid))

    # ---------- notifications ----------
    def _build_notifs(self, tab):
        frame, self.notif_tree = make_tree(tab, [("id", "#", 50), ("date", "Date", 160), ("msg", "Message", 700)])
        frame.pack(fill="both", expand=True)

    def _goto(self, name):
        self.tabs.set(name)
        self._on_tab()

    def _on_tab(self):
        if self.tabs.get() == "Notifications":
            self._refresh_notifs()
            db.mark_all_read(self.user["id"])
            self._refresh_badge()
        elif self.tabs.get() == "My Complaints":
            self.refresh_history()

    def _refresh_notifs(self):
        rows = db.list_notifications(self.user["id"])
        fill_tree(self.notif_tree, [(n["id"], n["created_at"].replace("T", " "),
                                     ("● " if not n["read"] else "") + n["msg"]) for n in rows])

    def _refresh_badge(self):
        n = db.unread_count(self.user["id"])
        self.bell.configure(text=f"Notifications ({n})", fg_color="#c0392b" if n else ["#3B8ED0", "#1F6AA5"])

    def _poll(self):
        if not self.winfo_exists():
            return
        try:
            self._refresh_badge()
        except Exception:
            log.exception("badge refresh failed")
        self.after(POLL_MS, self._poll)
