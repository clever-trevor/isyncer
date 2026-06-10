import subprocess

import ui


class FakeEntry:
    def __init__(self):
        self.text = ""

    def delete(self, start, end):
        self.text = ""

    def insert(self, index, value):
        self.text = value


class FakeStatus:
    def __init__(self):
        self.message = ""

    def set(self, value):
        self.message = value


class FakeVar:
    def __init__(self, value=""):
        self.value = value

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


def test_persist_android_target_saves_config(monkeypatch):
    saved = {}

    def fake_save_config(config, path):
        saved["config"] = dict(config)
        saved["path"] = path

    monkeypatch.setattr(ui, "save_config", fake_save_config)

    config = {"android_music_root": "old"}
    entry = FakeEntry()
    status = FakeStatus()

    result = ui.persist_android_target(entry, "  /sdcard/Music  ", status, config)

    assert result == "/sdcard/Music"
    assert entry.text == "/sdcard/Music"
    assert config["android_music_root"] == "/sdcard/Music"
    assert saved["config"] == config
    assert saved["path"] == ui.CONFIG_FILE
    assert status.message.startswith("Android target folder")


def test_refresh_android_devices_preserves_selected_target(monkeypatch):
    class FakeResult:
        returncode = 0
        stdout = "List of devices attached\nABC123\tdevice\n"

    monkeypatch.setattr(ui, "_find_adb", lambda: "adb")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: FakeResult())
    monkeypatch.setattr(ui, "save_config", lambda config, path: None)

    app = ui.SyncApp.__new__(ui.SyncApp)
    app.config = {"android_music_root": "/sdcard/syncr"}
    app.device_combo = {"values": []}
    app.device_var = FakeVar()
    app.status_var = FakeStatus()
    app.android_entry = FakeEntry()

    app.refresh_android_devices()

    assert app.device_var.value == "ABC123"
    assert app.android_entry.text == "/sdcard/syncr"
    assert app.config["android_music_root"] == "/sdcard/syncr"


def test_apply_android_target_saves_config(monkeypatch):
    saved = {}

    def fake_save_config(config, path):
        saved["config"] = config
        saved["path"] = path

    monkeypatch.setattr(ui, "save_config", fake_save_config)

    config = {"android_music_root": "old"}
    entry = FakeEntry()
    status = FakeStatus()

    result = ui.apply_android_target(entry, "  /sdcard/Music  ", status, config)

    assert result == "/sdcard/Music"
    assert entry.text == "/sdcard/Music"
    assert config["android_music_root"] == "/sdcard/Music"
    assert saved["config"] == config
    assert saved["path"] == ui.CONFIG_FILE
    assert status.message.startswith("Android target folder")
