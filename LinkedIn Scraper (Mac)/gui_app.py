"""
gui_app.py — Tkinter GUI for LinkedIn Recruiter Scraper.

Coworker-friendly frontend. Your dev workflow (main.py + CLI) is untouched.
Run this file directly in dev, or build it into an .exe with build.bat.
"""

import asyncio
import os
import queue
import subprocess
import sys
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
import tkinter as tk


# ── Base directory (works in dev AND as a PyInstaller .exe) ──────────────────
def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        # PyInstaller .exe: use the folder the .exe lives in
        return Path(sys.executable).parent
    return Path(__file__).parent

BASE_DIR = _base_dir()
os.chdir(BASE_DIR)          # make all relative paths (whitelist, output/) work


# ── Chrome detection & launch ─────────────────────────────────────────────────
_CHROME_CANDIDATES = [
    # Windows
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
    # macOS
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
]

def _find_chrome() -> str | None:
    for p in _CHROME_CANDIDATES:
        if os.path.exists(p):
            return p
    return None

def _launch_chrome() -> tuple[bool, str]:
    chrome = _find_chrome()
    if not chrome:
        return False, "Google Chrome not found on this machine."
    debug_dir = os.path.join(tempfile.gettempdir(), "chrome-li-debug")
    try:
        subprocess.Popen([
            chrome,
            "--remote-debugging-port=9222",
            f"--user-data-dir={debug_dir}",
            "--no-first-run",
            "--no-default-browser-check",
        ])
        return True, chrome
    except Exception as exc:
        return False, str(exc)


# ── Colour palette ────────────────────────────────────────────────────────────
C = {
    "bg":    "#f3f2ef",   # LinkedIn off-white
    "blue":  "#0a66c2",   # LinkedIn blue
    "green": "#057642",
    "red":   "#b24020",
    "text":  "#000000",
    "muted": "#666666",
}


# ── Main GUI application ──────────────────────────────────────────────────────
class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("LinkedIn Recruiter Scraper")
        self.root.geometry("700x580")
        self.root.resizable(False, False)
        self.root.configure(bg=C["bg"])

        self.log_q: queue.Queue = queue.Queue()
        self.last_output_dir: str = str(Path.home() / "Desktop")
        self._stop_flag = threading.Event()

        self._build_ui()
        self._poll_queue()

    # ─── UI layout ────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Header
        hdr = tk.Frame(self.root, bg=C["blue"], height=54)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="LinkedIn Recruiter Scraper",
                 font=("Segoe UI", 15, "bold"), bg=C["blue"], fg="white").pack(pady=13)

        # Notebook tabs
        style = ttk.Style()
        style.configure("TNotebook", background=C["bg"])
        style.configure("TNotebook.Tab", font=("Segoe UI", 10), padding=[10, 4])
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=16, pady=10)

        p = dict(padx=22, pady=12)
        self.t1 = tk.Frame(self.nb, bg=C["bg"], **p)
        self.t2 = tk.Frame(self.nb, bg=C["bg"], **p)
        self.t3 = tk.Frame(self.nb, bg=C["bg"], padx=14, pady=10)
        self.nb.add(self.t1, text="  1 · Setup  ")
        self.nb.add(self.t2, text="  2 · Search  ")
        self.nb.add(self.t3, text="  3 · Run  ")
        self.nb.tab(1, state="disabled")
        self.nb.tab(2, state="disabled")

        self._build_setup()
        self._build_search()
        self._build_run()

    # ─── Tab 1: Setup ─────────────────────────────────────────────────────────

    def _build_setup(self):
        f = self.t1
        tk.Label(f, text="Step 1 — Launch Chrome",
                 font=("Segoe UI", 13, "bold"), bg=C["bg"]).pack(anchor="w")
        tk.Label(f, text=(
            "The scraper connects to your existing LinkedIn session.\n"
            "We need to open Chrome with a special debugging flag so it can connect."
        ), font=("Segoe UI", 10), bg=C["bg"], fg=C["muted"],
            justify="left", wraplength=620).pack(anchor="w", pady=(4, 14))

        self.lbl_chrome = tk.Label(f, text="", font=("Segoe UI", 10), bg=C["bg"])
        self.lbl_chrome.pack(anchor="w")

        self.btn_launch = self._btn(f, "  Launch Chrome  ", C["blue"], self._on_launch)
        self.btn_launch.pack(anchor="w", pady=8)

        # Instruction box (shown after Chrome launches)
        self.instr = tk.Label(f, text="", font=("Segoe UI", 10),
                              bg="#e8f4fd", fg=C["text"], justify="left",
                              anchor="nw", wraplength=600, padx=12, pady=10)

        self.btn_cont = self._btn(f, "  Continue to Search →  ", C["green"],
                                  self._go_to_search, state="disabled")
        self.btn_cont.pack(anchor="w", pady=(18, 0))

    def _on_launch(self):
        ok, result = _launch_chrome()
        if ok:
            self.lbl_chrome.config(text="✓  Chrome launched successfully", fg=C["green"])
            self.btn_launch.config(text="  Re-launch Chrome  ", bg=C["muted"])
            self.instr.config(text=(
                "Chrome is now open.\n\n"
                "1.  In the Chrome window, go to linkedin.com/recruiter\n"
                "2.  Log in to your LinkedIn Recruiter Lite account\n"
                "3.  Once you're on the Recruiter dashboard, click Continue below"
            ))
            self.instr.pack(fill="x", pady=10)
            self.btn_cont.config(state="normal")
        else:
            self.lbl_chrome.config(text=f"✗  {result}", fg=C["red"])
            messagebox.showerror("Chrome not found", (
                f"{result}\n\n"
                "Please open Chrome manually with:\n\n"
                "chrome.exe --remote-debugging-port=9222 "
                "--user-data-dir=%TEMP%\\chrome-li-debug"
            ))

    def _go_to_search(self):
        self.nb.tab(1, state="normal")
        self.nb.select(1)

    # ─── Tab 2: Search config ──────────────────────────────────────────────────

    def _build_search(self):
        f = self.t2
        tk.Label(f, text="Step 2 — Configure Your Search",
                 font=("Segoe UI", 13, "bold"), bg=C["bg"]).pack(anchor="w")
        tk.Label(f, text=(
            "Run your Recruiter Lite search with all filters applied, "
            "then paste the full URL from your browser address bar."
        ), font=("Segoe UI", 10), bg=C["bg"], fg=C["muted"],
            justify="left", wraplength=620).pack(anchor="w", pady=(4, 14))

        # Search URL
        tk.Label(f, text="Search URL:", font=("Segoe UI", 10, "bold"),
                 bg=C["bg"]).pack(anchor="w")
        self.url_var = tk.StringVar()
        tk.Entry(f, textvariable=self.url_var, font=("Segoe UI", 9),
                 relief="solid", bd=1, width=78).pack(anchor="w", pady=(3, 14))

        # Page range
        tk.Label(f, text="Pages to scrape:", font=("Segoe UI", 10, "bold"),
                 bg=C["bg"]).pack(anchor="w")
        tk.Label(f, text="Each page = ~25 profiles.  Page 1 → profiles 1–25,  page 2 → 26–50, etc.",
                 font=("Segoe UI", 9), bg=C["bg"], fg=C["muted"]).pack(anchor="w")
        row = tk.Frame(f, bg=C["bg"])
        row.pack(anchor="w", pady=(4, 14))
        tk.Label(row, text="From page:", bg=C["bg"], font=("Segoe UI", 10)).pack(side="left")
        self.pg_start = tk.IntVar(value=1)
        tk.Spinbox(row, from_=1, to=999, textvariable=self.pg_start,
                   width=5, font=("Segoe UI", 10)).pack(side="left", padx=(4, 14))
        tk.Label(row, text="to page:", bg=C["bg"], font=("Segoe UI", 10)).pack(side="left")
        self.pg_end = tk.IntVar(value=5)
        tk.Spinbox(row, from_=1, to=999, textvariable=self.pg_end,
                   width=5, font=("Segoe UI", 10)).pack(side="left", padx=(4, 10))
        tk.Label(row, text="(~25 profiles/page)", bg=C["bg"],
                 fg=C["muted"], font=("Segoe UI", 9)).pack(side="left")

        # Output folder
        tk.Label(f, text="Save CSV to:", font=("Segoe UI", 10, "bold"),
                 bg=C["bg"]).pack(anchor="w")
        out_row = tk.Frame(f, bg=C["bg"])
        out_row.pack(anchor="w", pady=(3, 20))
        self.out_dir = tk.StringVar(value=str(Path.home() / "Desktop"))
        tk.Entry(out_row, textvariable=self.out_dir, font=("Segoe UI", 9),
                 relief="solid", bd=1, width=60).pack(side="left")
        tk.Button(out_row, text="Browse…", relief="solid", bd=1, padx=8, pady=3,
                  command=self._browse_output).pack(side="left", padx=6)

        self._btn(f, "  Start Scraping →  ", C["blue"], self._on_start).pack(anchor="w")

    def _browse_output(self):
        d = filedialog.askdirectory(initialdir=self.out_dir.get())
        if d:
            self.out_dir.set(d)

    # ─── Tab 3: Run / log ─────────────────────────────────────────────────────

    def _build_run(self):
        f = self.t3

        self.lbl_status = tk.Label(f, text="Waiting to start…",
                                   font=("Segoe UI", 11, "bold"), bg=C["bg"])
        self.lbl_status.pack(anchor="w", pady=(2, 2))

        self.progress = ttk.Progressbar(f, mode="indeterminate", length=660)
        self.progress.pack(fill="x", pady=(0, 6))

        tk.Label(f, text="Activity log:", font=("Segoe UI", 8),
                 bg=C["bg"], fg=C["muted"]).pack(anchor="w")

        self.log_box = scrolledtext.ScrolledText(
            f, height=17, width=86, font=("Consolas", 8),
            bg="#1e1e1e", fg="#d4d4d4", relief="flat", state="disabled")
        self.log_box.pack(fill="both", expand=True, pady=(2, 8))
        self.log_box.tag_config("ok",   foreground="#4ec9b0")
        self.log_box.tag_config("warn", foreground="#dcdcaa")
        self.log_box.tag_config("err",  foreground="#f44747")
        self.log_box.tag_config("dim",  foreground="#555555")

        btns = tk.Frame(f, bg=C["bg"])
        btns.pack(anchor="w")
        self.btn_stop   = self._btn(btns, "Stop",              C["red"],   self._on_stop,        state="disabled")
        self.btn_folder = self._btn(btns, "Open Output Folder", C["green"], self._open_folder,    state="disabled")
        self.btn_again  = self._btn(btns, "Run Again",          C["muted"], self._on_run_again,   state="disabled")
        for b in (self.btn_stop, self.btn_folder, self.btn_again):
            b.pack(side="left", padx=(0, 6))

    # ─── Scraper execution ─────────────────────────────────────────────────────

    def _on_start(self):
        url = self.url_var.get().strip()
        if not url or "linkedin.com" not in url:
            messagebox.showerror("Invalid URL",
                "Please paste a valid LinkedIn Recruiter search URL.")
            return
        s, e = self.pg_start.get(), self.pg_end.get()
        if e < s:
            messagebox.showerror("Invalid pages", "End page must be ≥ start page.")
            return

        # Switch to Run tab
        self.nb.tab(2, state="normal")
        self.nb.select(2)
        self.progress.start(10)
        self.btn_stop.config(state="normal")
        self.btn_folder.config(state="disabled")
        self.btn_again.config(state="disabled")
        self.lbl_status.config(text="Scraping in progress…", fg=C["blue"])
        self._stop_flag.clear()
        self.last_output_dir = self.out_dir.get()
        self._log("Starting LinkedIn Recruiter scraper…")

        cfg = {
            "search": {
                "saved_search_url": url,
                "start_page": s,
                "max_pages": e,
                "scrape_all": False,
            },
            "filters": {
                "bachelors_grad_year_min": 2010,
                "bachelors_grad_year_max": 2024,
                "no_bachelors_action": "flag",
            },
            "output": {
                "csv": {"enabled": True, "filename": "recruiter_results_{timestamp}.csv"},
                "airtable": {"enabled": False},
            },
            "browser": {
                "use_existing_browser": True,
                "cdp_url": "http://localhost:9222",
                "headless": False,
                "slow_mo": 600,
                "random_delay_range": [2, 5],
                "timeout": 30000,
                "persist_session": True,
                "max_profiles_per_run": 500,
            },
        }

        threading.Thread(target=self._worker, args=(cfg,), daemon=True).start()

    # ─── Background thread ─────────────────────────────────────────────────────

    def _worker(self, cfg: dict):
        """Runs the async scraper in a background thread."""
        from loguru import logger
        logger.remove()
        logger.add(self._sink, level="DEBUG", format="{message}")
        try:
            asyncio.run(self._scrape(cfg))
        except KeyboardInterrupt:
            self.log_q.put(("warn", "Stopped by user."))
        except Exception as exc:
            self.log_q.put(("err", f"Fatal error: {exc}"))
        finally:
            self.log_q.put(("__done__", None))

    def _sink(self, message):
        """Loguru sink — routes log records into the GUI queue."""
        level = message.record["level"].name.lower()
        text  = message.record["message"]
        tag = (
            "ok"   if level == "success"                        else
            "warn" if level == "warning"                        else
            "err"  if level in ("error", "critical")            else
            "dim"  if "skipping" in text.lower()                else
            ""
        )
        self.log_q.put((tag, text))

    async def _scrape(self, cfg: dict):
        from browser import init_browser, login_to_linkedin
        from search  import run_search, load_incremental_profiles
        from filters import apply_filters, load_title_whitelist
        from export  import write_csv

        whitelist = load_title_whitelist()
        browser   = None
        profiles  = []

        try:
            browser, _ctx, page = await init_browser(cfg["browser"])
            await login_to_linkedin(page, cfg["browser"])
            profiles, _ = await run_search(page, cfg["search"], whitelist)
        except Exception as exc:
            self.log_q.put(("err", str(exc)))
            profiles = profiles or load_incremental_profiles()
        finally:
            if profiles:
                filtered = apply_filters(profiles, cfg["filters"])
                ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
                name = f"recruiter_results_{ts}.csv"
                dest = str(Path(self.last_output_dir) / name)
                Path(self.last_output_dir).mkdir(parents=True, exist_ok=True)
                write_csv(filtered, dest)
                self.log_q.put(("__result__", (len(profiles), len(filtered), dest)))
            if browser:
                await browser.close()

    # ─── Queue polling ─────────────────────────────────────────────────────────

    def _poll_queue(self):
        try:
            while True:
                tag, val = self.log_q.get_nowait()
                if tag == "__done__":
                    self.progress.stop()
                    self.btn_stop.config(state="disabled")
                    self.btn_folder.config(state="normal")
                    self.btn_again.config(state="normal")
                    if "progress" in self.lbl_status.cget("text").lower():
                        self.lbl_status.config(
                            text="Stopped early — partial results saved", fg=C["muted"])
                elif tag == "__result__":
                    total, kept, path = val
                    self.lbl_status.config(
                        text=f"Done!  {kept} profiles saved.", fg=C["green"])
                    self._log(f"✓  Saved {kept} profiles (from {total} scraped) → {path}", "ok")
                else:
                    self._log(val, tag)
        except Exception:
            pass
        self.root.after(100, self._poll_queue)

    def _log(self, msg: str, tag: str = ""):
        self.log_box.config(state="normal")
        self.log_box.insert("end", msg + "\n", tag)
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    # ─── Button callbacks ──────────────────────────────────────────────────────

    def _on_stop(self):
        self._stop_flag.set()
        self._log("Stop requested — finishing current profile…", "warn")
        self.btn_stop.config(state="disabled")

    def _open_folder(self):
        if sys.platform == "darwin":
            subprocess.run(["open", self.last_output_dir])
        elif sys.platform == "win32":
            os.startfile(self.last_output_dir)
        else:
            subprocess.run(["xdg-open", self.last_output_dir])

    def _on_run_again(self):
        self.nb.select(1)
        self.log_box.config(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.config(state="disabled")
        self.lbl_status.config(text="Waiting to start…", fg=C["text"])

    # ─── Helper ────────────────────────────────────────────────────────────────

    @staticmethod
    def _btn(parent, text, color, cmd, state="normal") -> tk.Button:
        return tk.Button(
            parent, text=text, command=cmd,
            font=("Segoe UI", 10, "bold"),
            bg=color, fg="white", relief="flat",
            padx=12, pady=6, cursor="hand2", state=state,
        )


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
