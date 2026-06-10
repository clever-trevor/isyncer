import os
import tkinter as tk
from pathlib import PurePosixPath
from tkinter import filedialog, messagebox, ttk

from config import CONFIG_FILE, load_config, save_config
from itunes import parse_itunes_library
from sync_engine import _find_adb, _list_android_directories, build_sync_plan, execute_plan


def looks_like_shell_namespace_path(path):
    if not path:
        return False

    normalized = str(path).replace("/", "\\").strip().lower()
    return normalized.startswith("this pc\\") or normalized.startswith("this pc/") or normalized.startswith("::{")


def apply_android_target(entry, path, status_var, config):
    value = str(path).strip()

    entry.delete(0, tk.END)
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


class AndroidFolderBrowserDialog(tk.Toplevel):
    def __init__(self, parent, serial):
        super().__init__(parent)
        self.serial = serial
        self.result_path = None
        self.current_path = "/sdcard/"

        self.title("Browse Android folder")
        self.transient(parent)
        self.geometry("520x420")

        ttk.Label(self, text=f"Device: {serial}", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=10, pady=(8, 4))

        self.path_var = tk.StringVar(value=self.current_path)
        ttk.Label(self, textvariable=self.path_var, foreground="#0b5fff").pack(anchor="w", padx=10)

        self.listbox = tk.Listbox(self, height=18, width=70)
        self.listbox.pack(fill="both", expand=True, padx=10, pady=(6, 8))
        self.listbox.bind("<Double-1>", self.on_double_click)

        button_bar = ttk.Frame(self)
        button_bar.pack(fill="x", padx=10, pady=(0, 10))

        ttk.Button(button_bar, text="Open", command=self.open_selected).pack(side="left", padx=(0, 6))
        ttk.Button(button_bar, text="Up", command=self.go_up).pack(side="left", padx=(0, 6))
        ttk.Button(button_bar, text="Use this folder", command=self.confirm_selection).pack(side="left")
        ttk.Button(button_bar, text="Cancel", command=self.destroy).pack(side="right")

        self.refresh_entries()

    def refresh_entries(self):
        self.listbox.delete(0, tk.END)
        entries = _list_android_directories(self.current_path, serial=self.serial)
        for entry in entries:
            self.listbox.insert(tk.END, entry)
        self.path_var.set(self.current_path)

    def on_double_click(self, event=None):
        self.open_selected()

    def open_selected(self):
        selection = self.listbox.curselection()
        if not selection:
            return

        name = self.listbox.get(selection[0])
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
        self.root.geometry("980x640")

        self.config = load_config(CONFIG_FILE)
        self.playlists = []
        self.checkbox_vars = {}

        self._build_ui()
        self._load_existing_config()

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text="iSyncer — Windows music sync UI", font=("Segoe UI", 16, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(main, text="Configure the iTunes library path and the target Android music folder (for example, the Music or Download folder on your connected Android device). A test run reports actions without copying or removing files.", wraplength=900).grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 10))

        ttk.Label(main, text="iTunes XML file:").grid(row=2, column=0, sticky="w")
        self.itunes_entry = ttk.Entry(main, width=80)
        self.itunes_entry.grid(row=2, column=1, sticky="ew", padx=(8, 8))
        ttk.Button(main, text="Browse…", command=self.browse_itunes_file).grid(row=2, column=2, sticky="w")

        ttk.Label(main, text="Android target folder:").grid(row=3, column=0, sticky="w")
        self.android_entry = ttk.Entry(main, width=80)
        self.android_entry.grid(row=3, column=1, sticky="ew", padx=(8, 8))
        ttk.Button(main, text="Browse…", command=self.browse_android_folder).grid(row=3, column=2, sticky="w")

        ttk.Label(main, text="ADB device:").grid(row=4, column=0, sticky="w")
        self.device_var = tk.StringVar(value="")
        self.device_combo = ttk.Combobox(main, textvariable=self.device_var, state="readonly", width=78)
        self.device_combo.grid(row=4, column=1, sticky="ew", padx=(8, 8))
        ttk.Button(main, text="Refresh devices", command=self.refresh_android_devices).grid(row=4, column=2, sticky="w")

        self.test_mode = tk.BooleanVar(value=True)
        self.test_checkbox = ttk.Checkbutton(main, text="Test mode (preview only)", variable=self.test_mode)
        self.test_checkbox.grid(row=5, column=1, sticky="w", padx=(8, 0), pady=(4, 0))

        button_row = ttk.Frame(main)
        button_row.grid(row=6, column=0, columnspan=2, sticky="w", pady=(8, 12))
        ttk.Button(button_row, text="Load playlists", command=self.load_playlists).pack(side="left", padx=(0, 8))
        ttk.Button(button_row, text="Save config", command=self.save_config).pack(side="left", padx=(0, 8))
        ttk.Button(button_row, text="Run sync", command=self.run_sync).pack(side="left")

        self.status_var = tk.StringVar(value="Ready to load playlists from the configured iTunes library. If the phone only appears as an Explorer shell path, use a real Android device path such as /sdcard/Music after installing Android platform-tools (adb).")
        ttk.Label(main, textvariable=self.status_var, foreground="#0b5fff").grid(row=7, column=0, columnspan=2, sticky="w")

        self.progress = ttk.Progressbar(main, mode="determinate", maximum=100)
        self.progress.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(4, 8))

        self.playlist_frame = ttk.LabelFrame(main, text="Available playlists")
        self.playlist_frame.grid(row=9, column=0, columnspan=2, sticky="nsew", pady=(4, 0))

        self.playlist_canvas = tk.Canvas(self.playlist_frame, height=260, highlightthickness=0)
        self.playlist_canvas.bind("<MouseWheel>", self._on_playlist_wheel)
        self.playlist_canvas.bind("<Shift-MouseWheel>", self._on_playlist_wheel)
        self.playlist_scroll = ttk.Scrollbar(self.playlist_frame, orient="vertical", command=self.playlist_canvas.yview)
        self.playlist_inner = ttk.Frame(self.playlist_canvas)

        self.playlist_canvas.configure(yscrollcommand=self.playlist_scroll.set)
        self.playlist_canvas.create_window((0, 0), window=self.playlist_inner, anchor="nw")
        self.playlist_canvas.pack(side="left", fill="both", expand=True)
        self.playlist_scroll.pack(side="right", fill="y")

        self.summary_box = tk.Text(main, height=10, wrap="word")
        self.summary_box.grid(row=10, column=0, columnspan=2, sticky="nsew", pady=(10, 0))

        main.columnconfigure(1, weight=1)
        main.rowconfigure(9, weight=1)
        self.playlist_frame.columnconfigure(0, weight=1)
        self.playlist_frame.rowconfigure(0, weight=1)

    def _load_existing_config(self):
        self.itunes_entry.delete(0, tk.END)
        self.android_entry.delete(0, tk.END)
        self.itunes_entry.insert(0, self.config.get("itunes_library", ""))
        self.android_entry.insert(0, self.config.get("android_music_root", ""))
        self.test_mode.set(bool(self.config.get("test_mode", True)))
        self.refresh_android_devices()
        self.load_playlists()

    def _clear_playlist_list(self):
        for child in self.playlist_inner.winfo_children():
            child.destroy()
        self.checkbox_vars = {}

    def browse_itunes_file(self):
        path = filedialog.askopenfilename(
            title="Choose the iTunes Music Library.xml file",
            filetypes=[("iTunes XML", "*.xml"), ("All files", "*.*")],
        )
        if path:
            self.itunes_entry.delete(0, tk.END)
            self.itunes_entry.insert(0, path)
            self.status_var.set("iTunes file selected. Click Load playlists to refresh the playlist list.")

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
            self.status_var.set("Android target folder selected. Use this mounted folder for the sync.")

    def refresh_android_devices(self):
        adb = _find_adb()
        devices = []

        if adb:
            import subprocess

            try:
                result = subprocess.run([adb, "devices"], capture_output=True, text=True, check=False, encoding="utf-8", errors="replace")
                if result.returncode == 0:
                    for line in result.stdout.splitlines()[1:]:
                        parts = line.split("\t")
                        if len(parts) >= 2 and parts[1] == "device":
                            devices.append(parts[0])
            except Exception:
                devices = []

        self.device_combo["values"] = devices
        if devices:
            self.device_var.set(devices[0])

            current_target = (self.config or {}).get("android_music_root", "").strip()
            if not current_target:
                current_target = "/sdcard/"
                if self.config is not None:
                    self.config["android_music_root"] = current_target
                    save_config(self.config, CONFIG_FILE)

            self.android_entry.delete(0, tk.END)
            self.android_entry.insert(0, current_target)
            self.status_var.set(f"ADB device found. Current Android target path is {current_target}.")
        else:
            self.device_var.set("")
            self.status_var.set("No ADB device found. Connect the phone and click Refresh devices.")

    def paste_android_folder(self):
        try:
            path = self.root.clipboard_get()
        except tk.TclError:
            path = self.android_entry.get().strip()

        if not path:
            messagebox.showinfo("No path found", "Copy the mounted Android folder path from Explorer, then click the button again.")
            return

        if looks_like_shell_namespace_path(path):
            messagebox.showerror(
                "Cannot use Explorer shell path",
                "This is an Explorer shell-namespace path, not a real Windows filesystem folder. It cannot be used for copying music. Use a real Android device path such as /sdcard/Music (with Android platform-tools/adb installed), or choose a real mounted folder path if Windows exposes one."
            )
            return

        persist_android_target(self.android_entry, path.strip(), self.status_var, self.config)
        self.status_var.set("Android target folder set from the clipboard. Use this mounted folder path for the sync.")

    def load_playlists(self):
        itunes_path = self.itunes_entry.get().strip()
        if not os.path.exists(itunes_path):
            messagebox.showerror("Missing file", "The iTunes XML file path does not exist. Update the path and try again.")
            return

        try:
            parsed = parse_itunes_library(itunes_path)
            self.playlists = [
                playlist
                for playlist in parsed.get("playlists", [])
                if len(playlist.get("tracks", [])) > 0
            ]
        except Exception as exc:
            messagebox.showerror("Unable to read iTunes XML", str(exc))
            return

        self._clear_playlist_list()
        selected = set(self.config.get("selected_playlists", []))

        self.playlists = sorted(self.playlists, key=lambda playlist: str(playlist.get("name", "")).casefold())

        for playlist in self.playlists:
            var = tk.BooleanVar(value=playlist.get("name") in selected)
            self.checkbox_vars[playlist["name"]] = var
            row = ttk.Frame(self.playlist_inner)
            row.pack(fill="x", padx=6, pady=2)
            ttk.Checkbutton(row, variable=var, text=playlist.get("name", "Unnamed playlist")).pack(side="left")
            ttk.Label(row, text=f"{len(playlist.get('tracks', []))} tracks").pack(side="left", padx=(8, 0))

        self.playlist_inner.update_idletasks()
        self.playlist_canvas.config(scrollregion=self.playlist_canvas.bbox("all"))
        self.status_var.set(f"Loaded {len(self.playlists)} playlists from {itunes_path}")

    def _on_playlist_wheel(self, event):
        if hasattr(event, "delta") and event.delta:
            self.playlist_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        else:
            self.playlist_canvas.yview_scroll(int(-1 * event.num), "units")
        return "break"

    def save_config(self):
        config = {
            "itunes_library": self.itunes_entry.get().strip(),
            "android_music_root": self.android_entry.get().strip(),
            "selected_playlists": [name for name, var in self.checkbox_vars.items() if var.get()],
            "test_mode": bool(self.test_mode.get()),
        }
        save_config(config, CONFIG_FILE)
        self.config = config
        self.status_var.set("Configuration saved to isyncer_config.json")

    def run_sync(self):
        self.save_config()

        selected_playlists = [
            {"name": playlist["name"], "tracks": playlist.get("tracks", [])}
            for playlist in self.playlists
            if self.checkbox_vars.get(playlist["name"], tk.BooleanVar(value=False)).get()
        ]

        if not selected_playlists:
            messagebox.showinfo("No playlists selected", "Choose at least one playlist before running a sync.")
            return

        android_target = self.android_entry.get().strip()
        serial = self.device_var.get().strip() or None

        if serial and not android_target.startswith("/sdcard/") and not android_target.startswith("/storage/"):
            android_target = "/sdcard/"

        if looks_like_shell_namespace_path(android_target):
            messagebox.showerror(
                "Cannot use Explorer shell path",
                "This is an Explorer shell-namespace path, not a real Windows filesystem folder. It cannot be used for copying music. Use a real Android device path such as /sdcard/Music (with Android platform-tools/adb installed)."
            )
            return

        if not serial and not os.path.exists(android_target):
            os.makedirs(android_target, exist_ok=True)

        plan = build_sync_plan(
            selected_playlists=selected_playlists,
            android_root=android_target,
            iTunes_root=self.itunes_entry.get().strip(),
            test_mode=bool(self.test_mode.get()),
            serial=serial,
        )

        self.progress["maximum"] = max(1, len(plan["copy"]) + len(plan["remove"]))
        self.progress["value"] = 0

        summary_lines = [
            f"Mode: {'TEST' if bool(self.test_mode.get()) else 'LIVE'}",
            f"Selected playlists: {', '.join([item['name'] for item in selected_playlists])}",
            f"Songs to copy: {plan['summary']['copies']}",
            f"Songs to remove: {plan['summary']['removals']}",
            f"M3U playlist files: {plan['summary']['playlists']}",
            f"Play-count updates detected: {plan['summary']['play_count_updates']}",
        ]

        if bool(self.test_mode.get()):
            summary_lines.append("Preview only — no files will be copied or removed.")
            playlist_counts = {playlist['name']: 0 for playlist in selected_playlists}

            for item in plan.get('copy', []):
                playlist_name = item.get('playlist')
                if playlist_name in playlist_counts:
                    playlist_counts[playlist_name] += 1

            if playlist_counts:
                summary_lines.append("\nFiles to copy by playlist:")
                for playlist_name in sorted(playlist_counts):
                    count = playlist_counts[playlist_name]
                    summary_lines.append(f" - {playlist_name}: {count} file(s)")

            if plan.get('remove'):
                summary_lines.append(f"\nFiles to remove from device ({len(plan['remove'])}):")
                for item in plan['remove']:
                    summary_lines.append(f" - {item['path']}")
        else:
            execution = execute_plan(plan, test_mode=False, serial=serial)
            summary_lines.append(f"Executed copies: {execution['copied']}")
            summary_lines.append(f"Executed removals: {execution['removed']}")
            summary_lines.append(f"M3U files pushed: {execution['playlists_pushed']}")
            summary_lines.append(f"iTunes play counts updated: {execution['play_counts_updated']}")

            if plan.get("remove"):
                summary_lines.append(f"\nRemoval actions ({len(plan['remove'])}):")
                for item in plan["remove"]:
                    summary_lines.append(f" - {item['path']}")

        if plan.get("play_count_updates"):
            verb = "to update" if bool(self.test_mode.get()) else "updated"
            summary_lines.append(f"\nPlay counts {verb} in iTunes ({len(plan['play_count_updates'])}):")
            for item in plan["play_count_updates"]:
                summary_lines.append(
                    f" - {item['name']}: {item['itunes_play_count']} + {item['android_play_count']} = {item['new_count']}"
                )

        self.summary_box.delete("1.0", tk.END)
        self.summary_box.insert("1.0", "\n".join(summary_lines))
        self.status_var.set("Sync plan generated. Review the summary and run again for a real sync.")
        self.progress["value"] = 100
