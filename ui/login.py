import customtkinter as ctk

import auth
from ui import Spinner, run_async, show_error, show_info


class LoginFrame(ctk.CTkFrame):
    def __init__(self, master, on_login):
        super().__init__(master)
        self.on_login = on_login
        card = ctk.CTkFrame(self, corner_radius=12)
        card.place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(card, text="ConsumerGuard", font=ctk.CTkFont(size=26, weight="bold")).pack(pady=(24, 2), padx=40)
        ctk.CTkLabel(card, text="Draft Indian consumer complaints offline").pack(pady=(0, 10))

        tabs = ctk.CTkTabview(card, width=380, height=300)
        tabs.pack(padx=20, pady=(0, 10))
        lt, rt = tabs.add("Login"), tabs.add("Register")

        self.l_email = ctk.CTkEntry(lt, placeholder_text="Email", width=300)
        self.l_pw = ctk.CTkEntry(lt, placeholder_text="Password", show="•", width=300)
        self.l_btn = ctk.CTkButton(lt, text="Login", width=300, command=self._do_login)
        for w in (self.l_email, self.l_pw, self.l_btn):
            w.pack(pady=8)
        self.l_pw.bind("<Return>", lambda _e: self._do_login())

        self.r_name = ctk.CTkEntry(rt, placeholder_text="Full name", width=300)
        self.r_email = ctk.CTkEntry(rt, placeholder_text="Email", width=300)
        self.r_pw = ctk.CTkEntry(rt, placeholder_text="Password (min 6 chars)", show="•", width=300)
        self.r_btn = ctk.CTkButton(rt, text="Create account", width=300, command=self._do_register)
        for w in (self.r_name, self.r_email, self.r_pw, self.r_btn):
            w.pack(pady=6)
        self.tabs = tabs

        self.spinner = Spinner(card)
        self.spinner.pack(pady=(0, 16))
        self.l_email.focus_set()

    def _busy(self, busy: bool, text: str = "") -> None:
        state = "disabled" if busy else "normal"
        self.l_btn.configure(state=state)
        self.r_btn.configure(state=state)
        self.spinner.start(text) if busy else self.spinner.stop()

    def _fail(self, title: str):
        def handler(e):
            self._busy(False)
            show_error(title, str(e))
        return handler

    def _do_login(self) -> None:
        email, pw = self.l_email.get(), self.l_pw.get()
        self._busy(True, "Signing in...")

        def done(user):
            self._busy(False)
            self.on_login(user)
        run_async(self, lambda: auth.login(email, pw), done, self._fail("Login failed"))

    def _do_register(self) -> None:
        name, email, pw = self.r_name.get(), self.r_email.get(), self.r_pw.get()
        self._busy(True, "Creating account...")

        def done(user):
            self._busy(False)
            show_info("Registered", f"Welcome, {user['name']}! You can now log in.")
            self.l_email.delete(0, "end")
            self.l_email.insert(0, user["email"])
            self.tabs.set("Login")
            self.l_pw.focus_set()
        run_async(self, lambda: auth.register(name, email, pw), done, self._fail("Registration failed"))
