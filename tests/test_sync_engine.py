import os

import sync_engine
from itunes import parse_itunes_library
from sync_engine import _list_android_directories, _looks_like_android_device_path, _normalize_adb_listing, build_sync_plan


def test_build_sync_plan_copies_missing_and_marks_removals(tmp_path):
    android_root = tmp_path / "android"
    android_root.mkdir()

    itunes_root = tmp_path / "itunes"
    itunes_root.mkdir()

    existing_source = itunes_root / "Keep.mp3"
    existing_source.write_text("keep")
    new_source = itunes_root / "New.mp3"
    new_source.write_text("new")

    existing_song = android_root / "Keep.mp3"
    existing_song.write_text("keep")
    extra_song = android_root / "Remove.mp3"
    extra_song.write_text("remove")

    playlist_tracks = [
        {"name": "Keep", "artist": "Artist A", "location": str(existing_source), "play_count": 4},
        {"name": "New", "artist": "Artist B", "location": str(new_source), "play_count": 1},
    ]

    plan = build_sync_plan(
        selected_playlists=[{"name": "Test", "tracks": playlist_tracks}],
        android_root=str(android_root),
        iTunes_root=str(itunes_root),
        test_mode=True,
    )

    assert plan["copy"][0]["name"] == "New"
    assert plan["copy"][0]["playlist"] == "Test"
    assert plan["remove"][0]["name"] == "Remove"
    assert plan["summary"]["copies"] == 1
    assert plan["summary"]["removals"] == 1


def test_build_sync_plan_preserves_android_device_path(tmp_path):
    plan = build_sync_plan(
        selected_playlists=[{"name": "Test", "tracks": []}],
        android_root="/sdcard/Music",
        iTunes_root=str(tmp_path),
        test_mode=True,
    )

    assert plan["summary"]["android_root"] == "/sdcard/Music"


def test_detects_android_device_paths():
    assert _looks_like_android_device_path("/sdcard/Music") is True
    assert _looks_like_android_device_path("E:/Music/Android") is False


def test_normalize_adb_listing_returns_directory_names():
    entries = _normalize_adb_listing("Music/\nDownload/\nSong.mp3\n")

    assert entries == ["Music", "Download"]


def test_list_android_directories_uses_utf8_for_adb(monkeypatch):
    seen = {}

    def fake_find_adb():
        return r"T:\android-sdk\adb.exe"

    class FakeResult:
        returncode = 0
        stdout = ""

    def fake_run(command, capture_output, text, check, encoding=None, errors=None):
        seen["command"] = command
        seen["encoding"] = encoding
        seen["errors"] = errors
        return FakeResult()

    monkeypatch.setattr(sync_engine, "_find_adb", fake_find_adb)
    monkeypatch.setattr(sync_engine.subprocess, "run", fake_run)

    _list_android_directories("/sdcard/", serial="ABC123")

    assert seen["encoding"] == "utf-8"
    assert seen["errors"] == "replace"


def test_list_android_directories_uses_find_for_device_browsing(monkeypatch):
    seen = {}

    def fake_find_adb():
        return r"T:\android-sdk\adb.exe"

    class FakeResult:
        returncode = 0
        stdout = "/sdcard/Music\n/sdcard/Download\n"

    def fake_run(command, capture_output, text, check, encoding=None, errors=None):
        seen["command"] = command
        seen["encoding"] = encoding
        seen["errors"] = errors
        return FakeResult()

    monkeypatch.setattr(sync_engine, "_find_adb", fake_find_adb)
    monkeypatch.setattr(sync_engine.subprocess, "run", fake_run)

    entries = _list_android_directories("/sdcard/", serial="ABC123")

    assert entries == ["Download", "Music"]
    assert "find" in seen["command"][-1]
    assert "-type d" in seen["command"][-1]


def test_find_adb_prefers_local_sdk_directory(monkeypatch):
    monkeypatch.setattr(sync_engine.shutil, "which", lambda name: None)

    def fake_exists(path):
        return str(path).lower() in {
            r"t:\android-sdk\platform-tools\adb.exe",
            r"t:\android-sdk\adb.exe",
        }

    monkeypatch.setattr(sync_engine.os.path, "exists", fake_exists)

    assert sync_engine._find_adb() == r"T:\android-sdk\adb.exe"


def test_build_sync_plan_test_mode_does_not_probe_each_file(monkeypatch, tmp_path):
    source = tmp_path / "Song.mp3"
    source.write_text("song")

    monkeypatch.setattr(sync_engine, "_iter_audio_files", lambda root: ["/sdcard/Music/Existing.mp3"])

    def fail_path_exists(path):
        raise AssertionError("test mode should not probe Android files one by one")

    monkeypatch.setattr(sync_engine, "_path_exists", fail_path_exists)

    plan = build_sync_plan(
        selected_playlists=[{"name": "Test", "tracks": [{"Name": "Song", "Location": str(source), "Play Count": 1}]}],
        android_root="/sdcard/Music",
        iTunes_root=str(tmp_path),
        test_mode=True,
    )

    assert plan["summary"]["copies"] == 1


def test_build_sync_plan_uses_full_android_destination_paths_for_exists_check(monkeypatch, tmp_path):
    song_one = r"E:\Music\MP3\Artist A\Album 1\Song.mp3"
    song_two = r"E:\Music\MP3\Artist A\Album 2\Song.mp3"

    original_exists = sync_engine.os.path.exists

    def fake_exists(path):
        if str(path).lower().startswith(r"e:\music\mp3"):
            return True
        return original_exists(path)

    monkeypatch.setattr(sync_engine.os.path, "exists", fake_exists)
    monkeypatch.setattr(sync_engine, "_iter_audio_files", lambda root: ["/sdcard/Music/Artist A/Album 1/Song.mp3"])

    plan = build_sync_plan(
        selected_playlists=[{"name": "Test", "tracks": [
            {"Name": "Song A", "Location": song_one, "Play Count": 1},
            {"Name": "Song B", "Location": song_two, "Play Count": 1},
        ]}],
        android_root="/sdcard/Music",
        iTunes_root=str(tmp_path),
        test_mode=True,
    )

    assert len(plan["copy"]) == 1
    assert plan["copy"][0]["destination"] == "/sdcard/Music/Artist A/Album 2/Song.mp3"


def test_build_sync_plan_uses_relative_android_subfolders_for_music_root(monkeypatch, tmp_path):
    song = r"E:\Music\MP3\Adamski\Dance 2 The 90s [Everybody's Free 1990 -\34 Killer.mp3"

    original_exists = sync_engine.os.path.exists

    def fake_exists(path):
        if str(path).lower().startswith(r"e:\music\mp3"):
            return True
        return original_exists(path)

    monkeypatch.setattr(sync_engine.os.path, "exists", fake_exists)
    monkeypatch.setattr(
        sync_engine,
        "_iter_audio_files",
        lambda root: ["/sdcard/syncr/Adamski/Dance 2 The 90s [Everybody's Free 1990 -/34 Killer.mp3"],
    )

    plan = build_sync_plan(
        selected_playlists=[{"name": "Test", "tracks": [
            {"Name": "Dance 2 The 90s", "Location": song, "Play Count": 1},
        ]}],
        android_root="/sdcard/syncr",
        iTunes_root=str(tmp_path),
        test_mode=True,
    )

    assert plan["copy"] == []
    assert plan["summary"]["copies"] == 0


def test_build_sync_plan_uses_relative_android_subfolders(monkeypatch, tmp_path):
    song_one = r"E:\Music\MP3\Pink Floyd\The Wall\12 Another Brick in the Wall, Pt. 3.mp3"
    song_two = r"E:\Music\MP3\Pink Floyd\Wish You Were Here\Shine On You Crazy Diamond.mp3"

    original_exists = sync_engine.os.path.exists

    def fake_exists(path):
        if str(path).lower().startswith(r"e:\music\mp3"):
            return True
        return original_exists(path)

    monkeypatch.setattr(sync_engine.os.path, "exists", fake_exists)
    monkeypatch.setattr(sync_engine, "_iter_audio_files", lambda root: [])

    plan = build_sync_plan(
        selected_playlists=[{"name": "Test", "tracks": [
            {"Name": "Another Brick", "Location": song_one, "Play Count": 1},
            {"Name": "Shine On", "Location": song_two, "Play Count": 1},
        ]}],
        android_root="/sdcard/Music",
        iTunes_root=str(tmp_path),
        test_mode=True,
    )

    assert plan["copy"][0]["destination"] == "/sdcard/Music/Pink Floyd/The Wall/12 Another Brick in the Wall, Pt. 3.mp3"
    assert plan["copy"][1]["destination"] == "/sdcard/Music/Pink Floyd/Wish You Were Here/Shine On You Crazy Diamond.mp3"


def test_build_sync_plan_preserves_shell_namespace_android_path(tmp_path):
    shell_target = r"This PC\Trevor's S26 Ultra\Internal storage\syncr"

    plan = build_sync_plan(
        selected_playlists=[{"name": "Test", "tracks": []}],
        android_root=shell_target,
        iTunes_root=str(tmp_path),
        test_mode=True,
    )

    assert plan["summary"]["android_root"] == shell_target


def test_parse_itunes_library_normalizes_localhost_file_urls(tmp_path):
    plist_path = tmp_path / "library.xml"
    plist_path.write_text(
        """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<plist version=\"1.0\">
  <dict>
    <key>Tracks</key>
    <dict>
      <key>1</key>
      <dict>
        <key>Name</key>
        <string>Song A</string>
        <key>Location</key>
        <string>file://localhost/E:/Music/My%20Song.mp3</string>
      </dict>
    </dict>
    <key>Playlists</key>
    <array>
      <dict>
        <key>Name</key>
        <string>My Playlist</string>
        <key>Playlist Items</key>
        <array>
          <dict>
            <key>Track ID</key>
            <integer>1</integer>
          </dict>
        </array>
      </dict>
    </array>
  </dict>
</plist>
""",
        encoding="utf-8",
    )

    parsed = parse_itunes_library(str(plist_path))

    assert parsed["playlists"][0]["tracks"][0]["Location"] == r"E:\Music\My Song.mp3"


def test_parse_itunes_library_handles_plist_root(tmp_path):
    plist_path = tmp_path / "library.xml"
    plist_path.write_text(
        """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<plist version=\"1.0\">
  <dict>
    <key>Tracks</key>
    <dict>
      <key>1</key>
      <dict>
        <key>Name</key>
        <string>Song A</string>
        <key>Artist</key>
        <string>Artist A</string>
        <key>Location</key>
        <string>file:///E:/Music/Song%20A.mp3</string>
      </dict>
    </dict>
    <key>Playlists</key>
    <array>
      <dict>
        <key>Name</key>
        <string>My Playlist</string>
        <key>Playlist Items</key>
        <array>
          <dict>
            <key>Track ID</key>
            <integer>1</integer>
          </dict>
        </array>
      </dict>
    </array>
  </dict>
</plist>
""",
        encoding="utf-8",
    )

    parsed = parse_itunes_library(str(plist_path))

    assert parsed["playlists"][0]["name"] == "My Playlist"
    assert parsed["playlists"][0]["tracks"][0]["Name"] == "Song A"
