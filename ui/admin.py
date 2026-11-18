import logging
from tkinter import filedialog, messagebox

import customtkinter as ctk

import classifier
import config
import db
import kb
from ui import (Spinner, fill_tree, get_text, make_tree, run_async, selected_id, set_text,
                show_error, show_info)
from ui.consumer import download_pdf

log = logging.getLogger(__name__)
KB_CATEGORIES = ["general"] + config.CATEGORIES


class AdminFrame(ctk.CTkFrame):
    def __init__(self, master, user: dict, on_logout):
        super().__init__(master, fg_color="transparent")
        self.user = user
        top = ctk.CTkFrame(self)
        top.pack(fill="x", padx=10, pady=(10, 0))
        ctk.CTkLabel(top, text=f"ConsumerGuard Admin  ·  {user['name']}",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(side="left", padx=12, pady=8)
        ctk.CTkButton(top, text="Logout", width=80, fg_color="gray40", command=on_logout).pack(side="right", padx=8)

        self.tabs = ctk.CTkTabview(self, command=self._on_tab)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=10)
        self._build_cases(self.tabs.add("Complaints"))
        self._build_templates(self.tabs.add("Templates"))
        self._build_users(self.tabs.add("Users"))
        self._build_kb(self.tabs.add("Knowledge Base"))
        self.refresh_cases()

    def _on_tab(self):
        {"Complaints": self.refresh_cases, "Templates": self.refresh_templates,
         "Users": self.refresh_users, "Knowledge Base": self.refresh_kb}[self.tabs.get()]()

    # ---------- complaints ----------
    def _build_cases(self, tab):
        bar = ctk.CTkFrame(tab, fg_color="transparent")
        bar.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(bar, text="Status:").pack(side="left")
        self.filter = ctk.CTkOptionMenu(bar, values=["all"] + config.STATUSES,
                                        command=lambda _v: self.refresh_cases())
        self.filter.pack(side="left", padx=6)
        ctk.CTkButton(bar, text="Refresh", width=90, command=self.refresh_cases).pack(side="left", padx=6)
        ctk.CTkButton(bar, text="Download PDF", command=self._download).pack(side="left", padx=6)

        frame, self.cases = make_tree(tab, [("id", "#", 50), ("user", "Consumer", 150), ("date", "Filed", 140),
                                            ("category", "Category", 100), ("forum", "Forum", 80),
                                            ("value", "Value (Rs.)", 110), ("status", "Status", 100)], height=9)
        frame.pack(fill="both", expand=True)
        self.cases.bind("<<TreeviewSelect>>", lambda _e: self._show_case())

        detail = ctk.CTkFrame(tab)
        detail.pack(fill="both", expand=True, pady=(8, 0))
        detail.grid_columnconfigure(0, weight=1)
        detail.grid_rowconfigure(0, weight=1)
        self.case_text = ctk.CTkTextbox(detail, wrap="word", height=170)
        self.case_text.grid(row=0, column=0, columnspan=5, sticky="nsew", padx=8, pady=8)
        ctk.CTkLabel(detail, text="New status:").grid(row=1, column=0, sticky="e", padx=4)
        self.new_status = ctk.CTkOptionMenu(detail, values=config.STATUSES)
        self.new_status.grid(row=1, column=1, padx=4, pady=(0, 8))
        self.note = ctk.CTkEntry(detail, placeholder_text="Note to consumer", width=360)
        self.note.grid(row=1, column=2, padx=4, pady=(0, 8))
        ctk.CTkButton(detail, text="Update & notify", command=self._update_case).grid(row=1, column=3, padx=8, pady=(0, 8))

    def refresh_cases(self):
        status = self.filter.get()
        rows = db.list_cases(status=None if status == "all" else status)
        fill_tree(self.cases, [(c["id"], c["user_name"], c["created_at"].replace("T", " "), c["category"],
                                c["forum"], classifier.format_inr(c["value"]), c["status"]) for c in rows])
        set_text(self.case_text, "")

    def _show_case(self):
        cid = selected_id(self.cases)
        case = db.get_case(cid) if cid else None
        if not case:
            return
        self.new_status.set(case["status"])
        self.note.delete(0, "end")
        self.note.insert(0, case["admin_note"] or "")
        set_text(self.case_text,
                 f"#{case['id']}  {case['user_name']} <{case['user_email']}>\n"
                 f"Against: {case['opposite_party'] or '-'}  |  {case['district'] or '-'}, {case['state']}\n"
                 f"Forum: {classifier.FORUM_NAMES.get(case['forum'], case['forum'])}  |  "
                 f"Value: Rs. {classifier.format_inr(case['value'])}  |  PDF: {'yes' if case['pdf_path'] else 'no'}\n\n"
                 f"COMPLAINT:\n{case['text']}\n\nDRAFT:\n{case['draft'] or '(not generated)'}")

    def _update_case(self):
        cid = selected_id(self.cases)
        if cid is None:
            show_error("Select a complaint", "Select a complaint first.")
            return
        case = db.get_case(cid)
        status, note = self.new_status.get(), self.note.get().strip()
        try:
            db.update_case(cid, status=status, admin_note=note)
            msg = f"Complaint #{cid} status: {status.replace('_', ' ')}."
            if note:
                msg += f" Note: {note}"
            db.add_notification(case["user_id"], msg)
        except Exception as e:
            show_error("Update failed", str(e))
            return
        self.refresh_cases()
        if self.cases.exists(str(cid)):
            self.cases.selection_set(str(cid))
        show_info("Updated", "Status updated and consumer notified.")

    def _download(self):
        cid = selected_id(self.cases)
        if cid is None:
            show_error("Select a complaint", "Select a complaint first.")
            return
        download_pdf(db.get_case(cid))

    # ---------- templates ----------
    def _build_templates(self, tab):
        tab.grid_columnconfigure(1, weight=1)
        tab.grid_rowconfigure(0, weight=1)
        left = ctk.CTkFrame(tab, fg_color="transparent")
        left.grid(row=0, column=0, sticky="ns", padx=(0, 8))
        frame, self.tpl_tree = make_tree(left, [("id", "#", 40), ("category", "Category", 130)])
        frame.pack(fill="both", expand=True)
        self.tpl_tree.bind("<<TreeviewSelect>>", lambda _e: self._show_tpl())

        right = ctk.CTkFrame(tab)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(2, weight=1)
        row = ctk.CTkFrame(right, fg_color="transparent")
        row.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        ctk.CTkLabel(row, text="Category:").pack(side="left")
        self.tpl_cat = ctk.CTkOptionMenu(row, values=config.CATEGORIES)
        self.tpl_cat.pack(side="left", padx=6)
        ctk.CTkLabel(right, anchor="w", text="Placeholders: {complainant} {opposite_party} {facts} {value} "
                     "{state} {district} {forum} {category} {date} {grounds}").grid(row=1, column=0, sticky="ew", padx=8)
        self.tpl_body = ctk.CTkTextbox(right, wrap="word")
        self.tpl_body.grid(row=2, column=0, sticky="nsew", padx=8, pady=8)
        btns = ctk.CTkFrame(right, fg_color="transparent")
        btns.grid(row=3, column=0, sticky="ew", padx=8, pady=(0, 8))
        ctk.CTkButton(btns, text="New", width=80, command=self._new_tpl).pack(side="left")
        ctk.CTkButton(btns, text="Save", width=80, command=self._save_tpl).pack(side="left", padx=8)
        ctk.CTkButton(btns, text="Delete", width=80, fg_color="#c0392b", command=self._delete_tpl).pack(side="left")
        self.tpl_id: int | None = None

    def refresh_templates(self):
        fill_tree(self.tpl_tree, [(t["id"], t["category"]) for t in db.list_templates()])

    def _show_tpl(self):
        tid = selected_id(self.tpl_tree)
        tpl = next((t for t in db.list_templates() if t["id"] == tid), None)
        if tpl:
            self.tpl_id = tid
            self.tpl_cat.set(tpl["category"])
            set_text(self.tpl_body, tpl["body"])

    def _new_tpl(self):
        self.tpl_id = None
        self.tpl_tree.selection_remove(*self.tpl_tree.selection())
        self.tpl_cat.set(config.CATEGORIES[0])
        set_text(self.tpl_body, "FACTS OF THE CASE:\n{facts}\n\nGROUNDS:\n{grounds}\n\nRELIEF SOUGHT:\n\n"
                                "VERIFICATION:\nVerified at {district}, {state} on {date}.")

    def _save_tpl(self):
        body = get_text(self.tpl_body)
        if len(body) < 20:
            show_error("Invalid template", "Template body is too short.")
            return
        try:
            if self.tpl_id:
                db.update_template(self.tpl_id, self.tpl_cat.get(), body)
            else:
                self.tpl_id = db.create_template(self.tpl_cat.get(), body)
        except Exception as e:
            show_error("Save failed", str(e))
            return
        self.refresh_templates()
        self.tpl_tree.selection_set(str(self.tpl_id))
        show_info("Saved", "Template saved.")

    def _delete_tpl(self):
        if not self.tpl_id:
            show_error("Select a template", "Select a template first.")
            return
        if not messagebox.askyesno("Delete", "Delete this template?"):
            return
        db.delete_template(self.tpl_id)
        self.tpl_id = None
        set_text(self.tpl_body, "")
        self.refresh_templates()

    # ---------- users ----------
    def _build_users(self, tab):
        bar = ctk.CTkFrame(tab, fg_color="transparent")
        bar.pack(fill="x", pady=(0, 6))
        ctk.CTkButton(bar, text="Refresh", width=90, command=self.refresh_users).pack(side="left")
        ctk.CTkButton(bar, text="Activate / Deactivate", command=self._toggle_user).pack(side="left", padx=8)
        self.role_menu = ctk.CTkOptionMenu(bar, values=config.ROLES, width=120)
        self.role_menu.pack(side="left", padx=(16, 4))
        ctk.CTkButton(bar, text="Set role", width=90, command=self._set_role).pack(side="left")
        frame, self.users = make_tree(tab, [("id", "#", 50), ("name", "Name", 200), ("email", "Email", 260),
                                            ("role", "Role", 100), ("active", "Active", 80)])
        frame.pack(fill="both", expand=True)

    def refresh_users(self):
        fill_tree(self.users, [(u["id"], u["name"], u["email"], u["role"], "yes" if u["active"] else "no")
                               for u in db.list_users()])

    def _selected_other_user(self) -> dict | None:
        uid = selected_id(self.users)
        if uid is None:
            show_error("Select a user", "Select a user first.")
            return None
        if uid == self.user["id"]:
            show_error("Not allowed", "You cannot change your own account here.")
            return None
        return db.get_user(uid)

    def _toggle_user(self):
        u = self._selected_other_user()
        if u:
            db.set_user_active(u["id"], not u["active"])
            self.refresh_users()

    def _set_role(self):
        u = self._selected_other_user()
        if u:
            try:
                db.set_user_role(u["id"], self.role_menu.get())
            except ValueError as e:
                show_error("Invalid role", str(e))
            self.refresh_users()

    # ---------- knowledge base ----------
    def _build_kb(self, tab):
        bar = ctk.CTkFrame(tab, fg_color="transparent")
        bar.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(bar, text="Category:").pack(side="left")
        self.kb_cat = ctk.CTkOptionMenu(bar, values=KB_CATEGORIES, width=130)
        self.kb_cat.pack(side="left", padx=6)
        self.upload_btn = ctk.CTkButton(bar, text="Upload law PDF", command=self._upload)
        self.upload_btn.pack(side="left", padx=6)
        self.reembed_btn = ctk.CTkButton(bar, text="Embed missing chunks", command=self._reembed)
        self.reembed_btn.pack(side="left", padx=6)
        ctk.CTkButton(bar, text="Refresh", width=90, command=self.refresh_kb).pack(side="left", padx=6)
        self.kb_spinner = Spinner(bar)
        self.kb_spinner.pack(side="left", padx=10)
        self.kb_text = ctk.CTkTextbox(tab, wrap="word")
        self.kb_text.pack(fill="both", expand=True)

    def refresh_kb(self):
        s = kb.stats()
        lines = [f"Total chunks: {s['total']}", f"Embedded: {s['embedded']}  |  Missing embeddings: "
                 f"{s['total'] - s['embedded']}", f"Embedding model: {config.EMBED_MODEL}  |  "
                 f"Ollama: {config.OLLAMA_URL}", "", "Sources:"]
        lines += [f"  {r['source']}  [{r['category']}]  — {r['n']} chunks" for r in s["by_source"]]
        set_text(self.kb_text, "\n".join(lines))

    def _kb_busy(self, busy: bool, text: str = ""):
        for b in (self.upload_btn, self.reembed_btn):
            b.configure(state="disabled" if busy else "normal")
        self.kb_spinner.start(text) if busy else self.kb_spinner.stop(text)

    def _kb_fail(self, title):
        def handler(e):
            self._kb_busy(False)
            show_error(title, str(e))
        return handler

    def _upload(self):
        path = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
        if not path:
            return
        cat = self.kb_cat.get()
        self._kb_busy(True, "Extracting and embedding...")

        def done(res):
            n, embedded = res
            self._kb_busy(False, f"Added {n} chunks.")
            self.refresh_kb()
            if not embedded:
                show_info("Stored without embeddings",
                          f"{n} chunks stored, but Ollama embeddings were unavailable. "
                          "Use 'Embed missing chunks' once Ollama is running.")
        run_async(self, lambda: kb.ingest_pdf(path, cat), done, self._kb_fail("Upload failed"))

    def _reembed(self):
        self._kb_busy(True, "Embedding...")

        def done(n):
            self._kb_busy(False, f"Embedded {n} chunks.")
            self.refresh_kb()
        run_async(self, kb.reembed_missing, done, self._kb_fail("Embedding failed"))
