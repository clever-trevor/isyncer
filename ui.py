import os
import queue
import threading
import tkinter as tk
from pathlib import PurePosixPath
from tkinter import filedialog, messagebox

import customtkinter as ctk

from config import CONFIG_FILE, load_config, save_config
from itunes import parse_itunes_library
from sync_engine import _find_adb, _list_android_directories, build_sync_plan, execute_plan

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

_DIM = "#8890a0"


def looks_like_shell_namespace_path(path):
    if not path:
        return False
    normalized = str(path).replace("/", "\\").strip().lower()
    return normalized.startswith("this pc\\") or normalized.startswith("::{")


def apply_android_target(entry, path, status_var, config):
    value = str(path).strip()
    entry.delete(0, "end")
    entry.insert(0, value)
    if config is not None:
        config["android_music_root"] = value
        save_config(config, CONFIG_FILE)
    if status_var is not None:
        status_var.set(f"Android target folder set to {value}.")
    return value


def persist_android_target(entry, path, status_var, config):
    value = apply_android_target(entry, path, status_var, config)
    if config is not None:
        config["android_music_root"] = value
        save_config(config, CONFIG_FILE)
    return value


class AndroidFolderBrowserDialog(ctk.CTkToplevel):
    def __init__(self, parent, serial):
        super().__init__(parent)
        self.serial = serial
        self.result_path = None
        self.current_path = "/sdcard/"

        self.title("Browse Android Folder")
        self.geometry("560x500")
        self.resizable(False, False)
        self.grab_set()

        ctk.CTkLabel(self, text=f"Device: {serial}", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=16, pady=(16, 2))
        self.path_label = ctk.CTkLabel(self, text=self.current_path, text_color="#4a9eff", font=ctk.CTkFont(size=12))
        self.path_label.pack(anchor="w", padx=16, pady=(0, 8))

        list_card = ctk.CTkFrame(self)
        list_card.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        self.listbox = tk.Listbox(
            list_card,
            bg="#2b2b3b", fg="#cdd6f4", selectbackground="#4a9eff", selectforeground="#ffffff",
            relief="flat", borderwidth=0, highlightthickness=0,
            font=("Segoe UI", 11), activestyle="none",
        )
        scrollbar = tk.Scrollbar(list_card, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.listbox.pack(side="left", fill="both", expand=True, padx=2, pady=2)
        self.listbox.bind("<Double-1>", lambda e: self.open_selected())

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=16, pady=(0, 16))
        ctk.CTkButton(btn_frame, text="Open", width=90, command=self.open_selected).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_frame, text="Up", width=60, command=self.go_up).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_frame, text="Use this folder", command=self.confirm_selection).pack(side="left")
        ctk.CTkButton(btn_frame, text="Cancel", fg_color="transparent", border_width=1, command=self.destroy).pack(side="right")

        self.refresh_entries()

    def refresh_entries(self):
        self.listbox.delete(0, tk.END)
        for entry in _list_android_directories(self.current_path, serial=self.serial):
            self.listbox.insert(tk.END, entry)
        self.path_label.configure(text=self.current_path)

    def open_selected(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        name = self.listbox.get(sel[0])
        self.current_path = (self.current_path.rstrip("/") + "/" + name).rstrip("/") + "/"
        self.refresh_entries()

    def go_up(self):
        parent = str(PurePosixPath(self.current_path).parent)
        if parent in (".", ""):
            parent = "/"
        self.current_path = parent if parent.endswith("/") else parent + "/"
        self.refresh_entries()

    def confirm_selection(self):
        self.result_path = self.current_path.rstrip("/")
        self.destroy()


class SyncApp:
    def __init__(self, root):
        self.root = root
        self.root.title("iSyncer")
        self.root.geometry("1020x780")
        self.root.minsize(800, 600)

        self.config = load_config(CONFIG_FILE)
        self.playlists = []
        self.checkbox_vars = {}

        self._build_ui()
        self._load_existing_config()

    def _build_ui(self):
        # ── Header ──────────────────────────────────────────────────────────
        header = ctk.CTkFrame(self.root, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(20, 0))

        ctk.CTkLabel(header, text="iSyncer", font=ctk.CTkFont(size=28, weight="bold")).pack(side="left")
        ctk.CTkLabel(header, text="iTunes → Android", font=ctk.CTkFont(size=14), text_color=_DIM).pack(side="left", padx=(12, 0), pady=(8, 0))

        # ── Config card ─────────────────────────────────────────────────────
        config_card = ctk.CTkFrame(self.root, corner_radius=10)
        config_card.pack(fill="x", padx=20, pady=(14, 0))
        config_card.columnconfigure(1, weight=1)

        rows = [
            ("iTunes library", "itunes_entry", "Path to iTunes Music Library.xml", self.browse_itunes_file),
            ("Android folder", "android_entry", "e.g. /sdcard/Music", self.browse_android_folder),
        ]
        for i, (label, attr, placeholder, cmd) in enumerate(rows):
            pady = (14, 6) if i == 0 else (6, 6)
            ctk.CTkLabel(config_card, text=label, text_color=_DIM, width=120, anchor="w").grid(row=i, column=0, padx=(16, 8), pady=pady, sticky="w")
            entry = ctk.CTkEntry(config_card, placeholder_text=placeholder)
            entry.grid(row=i, column=1, sticky="ew", padx=(0, 8), pady=pady)
            ctk.CTkButton(config_card, text="Browse", width=80, command=cmd).grid(row=i, column=2, padx=(0, 16), pady=pady)
            setattr(self, attr, entry)

        ctk.CTkLabel(config_card, text="ADB device", text_color=_DIM, width=120, anchor="w").grid(row=2, column=0, padx=(16, 8), pady=(6, 14), sticky="w")
        self.device_var = tk.StringVar(value="")
        self.device_combo = ctk.CTkComboBox(config_card, variable=self.device_var, values=[], state="readonly")
        self.device_combo.grid(row=2, column=1, sticky="ew", padx=(0, 8), pady=(6, 14))
        ctk.CTkButton(config_card, text="Refresh", width=80, command=self.refresh_android_devices).grid(row=2, column=2, padx=(0, 16), pady=(6, 14))

        # ── Action bar ──────────────────────────────────────────────────────
        action_bar = ctk.CTkFrame(self.root, fg_color="transparent")
        action_bar.pack(fill="x", padx=20, pady=(12, 0))

        secondary = {"fg_color": "#2b3a5c", "hover_color": "#3a4f7a"}
        ctk.CTkButton(action_bar, text="Load playlists", width=130, **secondary, command=self.load_playlists).pack(side="left", padx=(0, 8))
        ctk.CTkButton(action_bar, text="Save config", width=110, **secondary, command=self.save_config).pack(side="left", padx=(0, 8))
        ctk.CTkButton(action_bar, text="▶  Run sync", width=120, command=self.run_sync).pack(side="left")

        self.test_mode = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(action_bar, text="Test mode", variable=self.test_mode).pack(side="right")

        # ── Status + progress ───────────────────────────────────────────────
        self.status_var = tk.StringVar(value="Ready.")
        ctk.CTkLabel(self.root, textvariable=self.status_var, text_color=_DIM, font=ctk.CTkFont(size=12), anchor="w").pack(fill="x", padx=22, pady=(10, 2))

        self.progress = ctk.CTkProgressBar(self.root, mode="determinate")
        self.progress.set(0)
        self.progress.pack(fill="x", padx=20, pady=(0, 10))

        # ── Playlists + output pane ─────────────────────────────────────────
        pane = ctk.CTkFrame(self.root, fg_color="transparent")
        pane.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        pane.columnconfigure(0, weight=1)
        pane.columnconfigure(1, weight=2)
        pane.rowconfigure(0, weight=1)

        # Playlists card
        pl_card = ctk.CTkFrame(pane, corner_radius=10)
        pl_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        pl_card.rowconfigure(1, weight=1)
        pl_card.columnconfigure(0, weight=1)

        pl_hdr = ctk.CTkFrame(pl_card, fg_color="transparent")
        pl_hdr.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(pl_hdr, text="Playlists", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")

        self.playlist_scroll = ctk.CTkScrollableFrame(pl_card, fg_color="transparent")
        self.playlist_scroll.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 8))

        # Output card
        out_card = ctk.CTkFrame(pane, corner_radius=10)
        out_card.grid(row=0, column=1, sticky="nsew")
        out_card.rowconfigure(1, weight=1)
        out_card.columnconfigure(0, weight=1)

        ctk.CTkLabel(out_card, text="Output", font=ctk.CTkFont(size=13, weight="bold")).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 4))
        self.summary_box = ctk.CTkTextbox(out_card, font=ctk.CTkFont(family="Cascadia Code", size=12), wrap="word")
        self.summary_box.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

    # ── Event handlers ───────────────────────────────────────────────────────

    def _load_existing_config(self):
        self.itunes_entry.delete(0, "end")
        self.android_entry.delete(0, "end")
        self.itunes_entry.insert(0, self.config.get("itunes_library", ""))
        self.android_entry.insert(0, self.config.get("android_music_root", ""))
        self.test_mode.set(bool(self.config.get("test_mode", True)))
        self.refresh_android_devices()
        self.load_playlists()

    def _clear_playlist_list(self):
        for child in self.playlist_scroll.winfo_children():
            child.destroy()
        self.checkbox_vars = {}

    def browse_itunes_file(self):
        path = filedialog.askopenfilename(
            title="Choose the iTunes Music Library.xml file",
            filetypes=[("iTunes XML", "*.xml"), ("All files", "*.*")],
        )
        if path:
            self.itunes_entry.delete(0, "end")
            self.itunes_entry.insert(0, path)
            self.status_var.set("iTunes file selected. Click Load playlists to refresh.")

    def browse_android_folder(self):
        selected_device = self.device_var.get().strip()
        if selected_device:
            dialog = AndroidFolderBrowserDialog(self.root, selected_device)
            self.root.wait_window(dialog)
            path = getattr(dialog, "result_path", None)
            if path:
                persist_android_target(self.android_entry, path, self.status_var, self.config)
                self.status_var.set(f"Android folder selected on {selected_device}: {path}")
                return
        path = filedialog.askdirectory(title="Choose the Android music folder")
        if path:
            persist_android_target(self.android_entry, path, self.status_var, self.config)
            self.status_var.set("Android target folder selected.")

    def refresh_android_devices(self):
        import subprocess as _sp
        adb = _find_adb()
        devices = []
        if adb:
            try:
                result = _sp.run([adb, "devices"], capture_output=True, text=True, check=False, encoding="utf-8", errors="replace")
                if result.returncode == 0:
                    for line in result.stdout.splitlines()[1:]:
                        parts = line.split("\t")
                        if len(parts) >= 2 and parts[1] == "device":
                            devices.append(parts[0])
            except Exception:
                pass

        self.device_combo.configure(values=devices)
        if devices:
            self.device_combo.set(devices[0])
            current_target = (self.config or {}).get("android_music_root", "").strip()
            if not current_target:
                current_target = "/sdcard/"
                if self.config is not None:
                    self.config["android_music_root"] = current_target
                    save_config(self.config, CONFIG_FILE)
            self.android_entry.delete(0, "end")
            self.android_entry.insert(0, current_target)
            self.status_var.set(f"ADB device found: {devices[0]}")
        else:
            self.device_combo.set("")
            self.status_var.set("No ADB device found. Connect the phone and click Refresh.")

    def load_playlists(self):
        itunes_path = self.itunes_entry.get().strip()
        if not os.path.exists(itunes_path):
            messagebox.showerror("Missing file", "The iTunes XML file path does not exist. Update the path and try again.")
            return
        try:
            parsed = parse_itunes_library(itunes_path)
            self.playlists = [p for p in parsed.get("playlists", []) if len(p.get("tracks", [])) > 0]
        except Exception as exc:
            messagebox.showerror("Unable to read iTunes XML", str(exc))
            return

        self._clear_playlist_list()
        selected = set(self.config.get("selected_playlists", []))
        self.playlists = sorted(self.playlists, key=lambda p: str(p.get("name", "")).casefold())

        for playlist in self.playlists:
            var = tk.BooleanVar(value=playlist.get("name") in selected)
            self.checkbox_vars[playlist["name"]] = var

            row = ctk.CTkFrame(self.playlist_scroll, fg_color="transparent")
            row.pack(fill="x", pady=2)

            ctk.CTkCheckBox(row, text=playlist.get("name", "Unnamed"), variable=var, font=ctk.CTkFont(size=12)).pack(side="left")
            ctk.CTkLabel(row, text=f"{len(playlist.get('tracks', []))} tracks", text_color=_DIM, font=ctk.CTkFont(size=11)).pack(side="right", padx=8)

        self.status_var.set(f"Loaded {len(self.playlists)} playlists.")

    def save_config(self):
        config = {
            "itunes_library": self.itunes_entry.get().strip(),
            "android_music_root": self.android_entry.get().strip(),
            "selected_playlists": [name for name, var in self.checkbox_vars.items() if var.get()],
            "test_mode": bool(self.test_mode.get()),
        }
        save_config(config, CONFIG_FILE)
        self.config = config
        self.status_var.set("Configuration saved.")

    def run_sync(self):
        self._set_output("Starting sync…")
        self.root.update_idletasks()
        self.save_config()

        # Re-parse the iTunes library so any changes since the last UI load are picked up
        itunes_path = self.itunes_entry.get().strip()
        try:
            parsed = parse_itunes_library(itunes_path)
            fresh_playlists = {
                p["name"]: p
                for p in parsed.get("playlists", [])
                if p.get("tracks")
            }
        except Exception:
            fresh_playlists = {}

        selected_names = {name for name, var in self.checkbox_vars.items() if var.get()}
        selected_playlists = [
            {"name": name, "tracks": fresh_playlists[name].get("tracks", [])}
            for name in selected_names
            if name in fresh_playlists
        ]

        if not selected_playlists:
            messagebox.showinfo("No playlists selected", "Choose at least one playlist before running a sync.")
            return

        android_target = self.android_entry.get().strip()
        serial = self.device_var.get().strip() or None

        if serial and not android_target.startswith("/sdcard/") and not android_target.startswith("/storage/"):
            android_target = "/sdcard/"

        if looks_like_shell_namespace_path(android_target):
            messagebox.showerror("Cannot use Explorer shell path", "Use a real Android device path such as /sdcard/Music.")
            return

        if not serial and not os.path.exists(android_target):
            os.makedirs(android_target, exist_ok=True)

        self.status_var.set("Building sync plan…")
        self.root.update_idletasks()

        plan = build_sync_plan(
            selected_playlists=selected_playlists,
            android_root=android_target,
            iTunes_root=self.itunes_entry.get().strip(),
            test_mode=bool(self.test_mode.get()),
            serial=serial,
        )

        self.progress.set(0)

        if bool(self.test_mode.get()):
            self._show_test_summary(plan, selected_playlists)
        else:
            self._run_live_sync(plan, serial, selected_playlists)

    def _show_test_summary(self, plan, selected_playlists):
        lines = [
            f"Mode      : TEST",
            f"Playlists : {', '.join(p['name'] for p in selected_playlists)}",
            f"To copy   : {plan['summary']['copies']}",
            f"To remove : {plan['summary']['removals']}",
            f"M3U files : {plan['summary']['playlists']}",
            f"Play count: {plan['summary']['play_count_updates']} updates",
            "",
            "Preview only — no files will be changed.",
        ]

        playlist_counts = {p["name"]: 0 for p in selected_playlists}
        for item in plan.get("copy", []):
            if item.get("playlist") in playlist_counts:
                playlist_counts[item["playlist"]] += 1
        lines.append("\nPlaylist breakdown:")
        for name in sorted(playlist_counts):
            count = playlist_counts[name]
            suffix = f"{count} to copy" if count else "up to date — M3U will refresh"
            lines.append(f"  {name}: {suffix}")

        if plan.get("remove"):
            lines.append(f"\nFiles to remove ({len(plan['remove'])}):")
            for item in plan["remove"]:
                lines.append(f"  {item['path']}")

        if plan.get("play_count_updates"):
            lines.append(f"\nPlay counts to update in iTunes ({len(plan['play_count_updates'])}):")
            for item in plan["play_count_updates"]:
                lines.append(f"  {item['name']}: {item['itunes_play_count']} + {item['android_play_count']} = {item['new_count']}")

        self._set_output("\n".join(lines))
        self.status_var.set("Test run complete — review output.")
        self.progress.set(1.0)

    def _run_live_sync(self, plan, serial, selected_playlists):
        # All selected playlists will have their M3U refreshed — use that as the full list
        playlist_order = [p["name"] for p in plan.get("playlists", [])]
        playlist_totals = {}
        for item in plan.get("copy", []):
            pl = item["playlist"]
            playlist_totals[pl] = playlist_totals.get(pl, 0) + 1

        total_files = sum(playlist_totals.values())
        playlist_progress = {pl: 0 for pl in playlist_order}
        # Playlists with nothing to copy are immediately complete (M3U-only update)
        playlist_done = {pl for pl in playlist_order if not playlist_totals.get(pl)}

        header = [
            f"Mode      : LIVE",
            f"Playlists : {', '.join(p['name'] for p in selected_playlists)}",
            f"To copy   : {plan['summary']['copies']}",
            f"To remove : {plan['summary']['removals']}",
            "",
        ]

        def render():
            pad = max((len(pl) for pl in playlist_order), default=8)
            lines = list(header) + ["Syncing playlists:"]
            for pl in playlist_order:
                done = playlist_progress.get(pl, 0)
                total = playlist_totals.get(pl, 0)
                if total == 0:
                    count_str = "no new files"
                    status = "  M3U refresh"
                elif pl in playlist_done:
                    count_str = f"{done:>4} / {total}"
                    status = "  complete"
                else:
                    count_str = f"{done:>4} / {total}"
                    status = ""
                lines.append(f"  {pl:<{pad}}  {count_str}{status}")
            self._set_output("\n".join(lines))

        q = queue.Queue()
        self._set_run_button_state("disabled")
        render()

        def on_progress(pl, done, total):
            q.put(("progress", pl, done, total))

        def worker():
            result = execute_plan(plan, test_mode=False, serial=serial, progress_callback=on_progress)
            q.put(("done", result))

        threading.Thread(target=worker, daemon=True).start()

        def poll():
            try:
                while True:
                    msg = q.get_nowait()
                    if msg[0] == "progress":
                        _, pl, done, total = msg
                        playlist_progress[pl] = done
                        if done >= total:
                            playlist_done.add(pl)
                        render()
                        self.progress.set(sum(playlist_progress.values()) / max(1, total_files))
                    elif msg[0] == "done":
                        _, execution = msg
                        self._finish_live_sync(plan, execution, playlist_order, playlist_totals)
                        return
            except queue.Empty:
                pass
            self.root.after(100, poll)

        self.root.after(100, poll)

    def _finish_live_sync(self, plan, execution, playlist_order, playlist_totals):
        pad = max((len(pl) for pl in playlist_order), default=8)
        lines = [
            "Mode      : LIVE",
            "",
            "Playlist results:",
        ]
        for pl in playlist_order:
            total = playlist_totals.get(pl, 0)
            if total:
                lines.append(f"  {pl:<{pad}}  {total} / {total}  complete")
            else:
                lines.append(f"  {pl:<{pad}}  M3U refreshed")

        lines += [
            "",
            f"Copied  : {execution['copied']}",
            f"Removed : {execution['removed']}",
            f"M3U     : {execution['playlists_pushed']} pushed",
            f"iTunes  : {execution['play_counts_updated']} play counts updated",
        ]


        if plan.get("remove"):
            lines.append(f"\nRemoved files ({len(plan['remove'])}):")
            for item in plan["remove"]:
                lines.append(f"  {item['path']}")

        if plan.get("play_count_updates"):
            lines.append(f"\nPlay counts updated in iTunes ({len(plan['play_count_updates'])}):")
            for item in plan["play_count_updates"]:
                lines.append(f"  {item['name']}: {item['itunes_play_count']} + {item['android_play_count']} = {item['new_count']}")

        self._set_output("\n".join(lines))
        self.status_var.set("Sync complete.")
        self.progress.set(1.0)
        self._set_run_button_state("normal")

    def _set_output(self, text):
        self.summary_box.delete("1.0", "end")
        self.summary_box.insert("1.0", text)

    def _set_run_button_state(self, state):
        for widget in self.root.winfo_children():
            self._walk_buttons(widget, "▶  Run sync", state)

    def _walk_buttons(self, widget, label, state):
        if isinstance(widget, ctk.CTkButton) and widget.cget("text") == label:
            widget.configure(state=state)
            return
        for child in widget.winfo_children():
            self._walk_buttons(child, label, state)
