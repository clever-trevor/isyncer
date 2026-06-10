import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


AUDIO_EXTENSIONS = {".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".wma", ".alac"}

_PUNCT_CHARS = "_-:;.,!?()'\"[]&"
_PUNCT_TABLE = str.maketrans(_PUNCT_CHARS, " " * len(_PUNCT_CHARS))


def _fuzzy_name(name):
    """Strip punctuation/separators and collapse whitespace for loose folder comparison."""
    return " ".join(name.translate(_PUNCT_TABLE).split())


def _looks_like_android_device_path(path):
    if not path:
        return False

    normalized = str(path).strip().replace("\\", "/").lower()
    return (
        normalized.startswith("/sdcard/")
        or normalized.startswith("/storage/")
        or normalized.startswith("/mnt/")
        or normalized.startswith("sdcard/")
        or normalized.startswith("storage/")
    )


def _looks_like_shell_namespace_path(path):
    if not path:
        return False

    normalized = str(path).strip().replace("/", "\\")
    lowered = normalized.lower()
    return lowered.startswith("this pc\\") or lowered.startswith("computer\\") or lowered.startswith("::{")


def _ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def _normalize_adb_listing(output):
    entries = []
    for line in str(output).splitlines():
        cleaned = line.strip().replace("\\", "/")
        if not cleaned or cleaned in {".", ".."} or cleaned.startswith("total "):
            continue

        if cleaned.startswith("/"):
            name = os.path.basename(cleaned.rstrip("/"))
            if name and name not in {".", ".."}:
                entries.append(name)
            continue

        if not cleaned.endswith("/"):
            continue

        name = cleaned.rstrip("/")
        if name and name not in {".", ".."}:
            entries.append(name)

    return entries


def _adb_command(adb_path, serial=None):
    command = [adb_path]
    if serial:
        command.extend(["-s", serial])
    return command


def _run_adb_command(command, *, check=False):
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=check,
        encoding="utf-8",
        errors="replace",
    )


def _list_android_directories(path, serial=None):
    adb = _find_adb()
    if not adb:
        return []

    command = _adb_command(adb, serial)
    command.extend(["shell", f"find '{path}' -mindepth 1 -maxdepth 1 -type d"])

    result = _run_adb_command(command, check=False)
    if result.returncode != 0:
        return []

    entries = _normalize_adb_listing(result.stdout)
    return sorted(entries, key=str.casefold)


def _find_adb():
    candidates = []

    app_dir = os.path.dirname(os.path.abspath(__file__))
    candidates.extend([
        os.path.join(app_dir, "adb.exe"),
        os.path.join(app_dir, "adb"),
    ])

    for env_name in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        value = os.environ.get(env_name)
        if value:
            candidates.extend([
                os.path.join(value, "adb.exe"),
                os.path.join(value, "adb"),
                os.path.join(value, "platform-tools", "adb.exe"),
                os.path.join(value, "platform-tools", "adb"),
            ])

    candidates.extend([
        r"T:\android-sdk\adb.exe",
        r"T:\android-sdk\adb",
        r"T:\android-sdk\platform-tools\adb.exe",
        r"T:\android-sdk\platform-tools\adb",
    ])

    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate

    return shutil.which("adb") or shutil.which("adb.exe")


def _run_powershell(command):
    if os.name != "nt":
        return None

    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        check=False,
    )
    return result


def _path_exists(path, serial=None):
    if _looks_like_android_device_path(path):
        adb = _find_adb()
        if adb:
            command = _adb_command(adb, serial)
            command.extend(["shell", f"if [ -e '{path}' ]; then echo yes; else echo no; fi"])
            result = _run_adb_command(command, check=False)
            return bool(result and result.returncode == 0 and "yes" in result.stdout.lower())

    if _looks_like_shell_namespace_path(path) and os.name == "nt":
        result = _run_powershell(f"Test-Path -LiteralPath {_ps_quote(path)}")
        return bool(result and result.returncode == 0 and result.stdout.strip().lower() == "true")

    return os.path.exists(path)


def _iter_audio_files(root, serial=None):
    if _looks_like_android_device_path(root):
        adb = _find_adb()
        if adb:
            command = _adb_command(adb, serial)
            command.extend(["shell", "find '" + root + "' -type f \\( -iname '*.mp3' -o -iname '*.m4a' -o -iname '*.aac' -o -iname '*.wav' -o -iname '*.flac' -o -iname '*.ogg' -o -iname '*.wma' -o -iname '*.alac' \\) 2>/dev/null"])
            result = _run_adb_command(command, check=False)
            if result:
                lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
                if not lines:
                    print(f"[ADB find] returncode={result.returncode}")
                    print(f"[ADB find] stderr={result.stderr[:300]!r}")
                    print(f"[ADB find] stdout={result.stdout[:300]!r}")
                return lines
            return []

    if _looks_like_shell_namespace_path(root) and os.name == "nt":
        command = (
            "Get-ChildItem -LiteralPath " + _ps_quote(root) +
            " -Recurse -File -ErrorAction SilentlyContinue | "
            "Where-Object { $_.FullName -match '.*\\.(mp3|m4a|aac|wav|flac|ogg|wma|alac)$' } | "
            "Select-Object -ExpandProperty FullName"
        )
        result = _run_powershell(command)
        if result and result.returncode == 0:
            return [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return []

    if not root or not os.path.exists(root):
        return []

    results = []
    for directory, _, files in os.walk(root):
        for file_name in files:
            if Path(file_name).suffix.lower() in AUDIO_EXTENSIONS:
                results.append(os.path.join(directory, file_name))
    return results


def _copy_file(source, destination, serial=None):
    if _looks_like_android_device_path(destination):
        adb = _find_adb()
        if adb:
            destination_dir = os.path.dirname(destination)
            mkdir_cmd = _adb_command(adb, serial) + ["shell", f"mkdir -p '{destination_dir}'"]
            _run_adb_command(mkdir_cmd, check=False)
            push_cmd = _adb_command(adb, serial) + ["push", source, destination]
            result = _run_adb_command(push_cmd, check=False)
            return bool(result and result.returncode == 0)

    if _looks_like_shell_namespace_path(destination) and os.name == "nt":
        result = _run_powershell(
            "Copy-Item -LiteralPath " + _ps_quote(source) +
            " -Destination " + _ps_quote(destination) +
            " -Force"
        )
        return bool(result and result.returncode == 0)

    os.makedirs(os.path.dirname(destination), exist_ok=True)
    shutil.copy2(source, destination)
    return True


def _remove_file(path, serial=None):
    if _looks_like_android_device_path(path):
        adb = _find_adb()
        if adb:
            command = _adb_command(adb, serial) + ["shell", f"rm -f '{path}'"]
            result = _run_adb_command(command, check=False)
            return bool(result and result.returncode == 0)

    if _looks_like_shell_namespace_path(path) and os.name == "nt":
        result = _run_powershell("Remove-Item -LiteralPath " + _ps_quote(path) + " -Force -ErrorAction SilentlyContinue")
        return bool(result and result.returncode == 0)

    if os.path.exists(path):
        os.remove(path)
        return True

    return False


def _track_value(song, *keys):
    for key in keys:
        if key in song:
            return song[key]

    lowered = {str(key).lower(): value for key, value in song.items()}
    for key in keys:
        lower_key = str(key).lower()
        if lower_key in lowered:
            return lowered[lower_key]

    return None


def _normalize_name(value):
    return os.path.basename(str(value).replace("/", "\\")).lower()


def _normalize_android_path(value):
    normalized = str(value).replace("\\", "/").lower().strip("/")
    for prefix in ("storage/emulated/0", "storage/emulated/legacy", "storage/self/primary"):
        if normalized == prefix:
            return "sdcard"
        if normalized.startswith(prefix + "/"):
            return "sdcard/" + normalized[len(prefix) + 1:]
    return normalized


def _android_path_join(root, *parts):
    normalized_root = str(root).replace("\\", "/").rstrip("/")
    normalized_parts = [str(part).replace("\\", "/").strip("/") for part in parts if part]

    if not normalized_root:
        return "/" + "/".join(normalized_parts)

    return "/".join([normalized_root] + normalized_parts)


def _relative_destination_path(source, android_root):
    normalized_source = os.path.normpath(str(source).replace("/", "\\"))
    drive, tail = os.path.splitdrive(normalized_source)
    tail_parts = [part for part in tail.split("\\") if part]

    if drive and len(tail_parts) >= 2:
        # Strip the Windows music root (for example: E:\Music\MP3) and keep the
        # relative folder structure under it, then convert that path to Android format.
        root = os.path.normpath(drive + "\\" + tail_parts[0] + "\\" + tail_parts[1])
        relative_path = os.path.relpath(normalized_source, root).replace("\\", "/")
        if relative_path not in {".", ""}:
            return _android_path_join(android_root, relative_path)

    return _android_path_join(android_root, os.path.basename(normalized_source))


def _android_rel_keys(path, norm_android_root):
    """Return a frozenset of (folder, filename) keys for flexible matching.

    Generates exact and fuzzy variants using two folder levels so that:
    - Compilations top-folder vs artist-name top-folder both match via album key
    - Punctuation/separator substitutions (- vs _ vs :) are bridged via fuzzy keys
    """
    norm_fp = _normalize_android_path(path)
    prefix = norm_android_root.rstrip("/") + "/"
    if not norm_fp.startswith(prefix):
        return frozenset()
    rel = norm_fp[len(prefix):]
    parts = [p for p in rel.split("/") if p]
    if len(parts) >= 2:
        fname = parts[-1]
        artist = parts[0]
        album = parts[-2] if len(parts) >= 3 else parts[0]
        return frozenset({
            (artist, fname),
            (album, fname),
            (_fuzzy_name(artist), fname),
            (_fuzzy_name(album), fname),
        })
    if len(parts) == 1:
        return frozenset({(None, parts[0])})
    return frozenset()


def _sanitize_filename(name):
    """Strip characters that are invalid in filenames."""
    for ch in r'\/:*?"<>|':
        name = name.replace(ch, '_')
    return name.strip() or "playlist"


def _read_play_count_sidecar(path):
    sidecar = f"{path}.playcount.json"
    if not os.path.exists(sidecar):
        return None

    try:
        with open(sidecar, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError, TypeError):
        return None


def build_sync_plan(selected_playlists, android_root, iTunes_root, test_mode=False, serial=None):
    android_root = str(android_root)
    if not _looks_like_android_device_path(android_root) and not _looks_like_shell_namespace_path(android_root):
        android_root = os.path.abspath(android_root)

    iTunes_root = os.path.abspath(iTunes_root)

    selected_tracks = []
    for playlist in selected_playlists:
        playlist_name = playlist.get("name", "Unnamed playlist")
        for song in playlist.get("tracks", []):
            selected_tracks.append({"playlist_name": playlist_name, "song": song})

    android_files = _iter_audio_files(android_root, serial=serial)

    norm_android_root = _normalize_android_path(android_root)

    # Index Android files by all (folder, filename) keys to handle path mismatches.
    # Values are the original paths from adb find (used in M3U generation).
    android_by_key = {}
    for fp in android_files:
        for key in _android_rel_keys(fp, norm_android_root):
            android_by_key[key] = fp

    selected_names = set()
    selected_android_keys = set()
    for entry in selected_tracks:
        location = _track_value(entry["song"], "Location", "location")
        if _looks_like_android_device_path(android_root):
            source = os.path.abspath(str(location).replace("file://", "").replace("/", "\\"))
            destination = _relative_destination_path(source, android_root)
            selected_android_keys.update(_android_rel_keys(destination, norm_android_root))
        else:
            selected_names.add(_normalize_name(location or entry["song"].get("Name")))

    copy_actions = []
    remove_actions = []
    play_count_updates = []
    debug_printed = False

    for entry in selected_tracks:
        song = entry["song"]
        playlist_name = entry["playlist_name"]
        location = _track_value(song, "Location", "location")
        if not location:
            continue

        source = os.path.abspath(str(location).replace("file://", "").replace("/", "\\"))
        if not os.path.exists(source):
            continue

        if _looks_like_android_device_path(android_root):
            destination = _relative_destination_path(source, android_root)
        else:
            destination = os.path.join(android_root, os.path.basename(source))

        destination_exists = False
        if _looks_like_android_device_path(android_root):
            destination_exists = bool(_android_rel_keys(destination, norm_android_root) & android_by_key.keys())
        else:
            destination_exists = _path_exists(destination, serial=serial)

        if not destination_exists:
            copy_actions.append({
                "name": _track_value(song, "Name", "name") or os.path.basename(source),
                "artist": _track_value(song, "Artist", "artist") or "",
                "source": source,
                "destination": destination,
                "playlist": playlist_name,
                "play_count": _track_value(song, "Play Count", "play_count") or 0,
            })
        elif not test_mode:
            sidecar = _read_play_count_sidecar(destination)
            if sidecar and isinstance(sidecar, dict):
                current_play_count = int(sidecar.get("play_count", 0) or 0)
                library_play_count = int(_track_value(song, "Play Count", "play_count") or 0)
                if current_play_count > library_play_count:
                    play_count_updates.append({
                        "name": song.get("Name", os.path.basename(source)),
                        "android_play_count": current_play_count,
                        "itunes_play_count": library_play_count,
                    })

    for file_path in android_files:
        if _looks_like_android_device_path(android_root):
            file_keys = _android_rel_keys(file_path, norm_android_root)
            if not file_keys or not (file_keys & selected_android_keys):
                remove_actions.append({
                    "name": os.path.splitext(os.path.basename(file_path))[0],
                    "path": file_path,
                })
        elif _normalize_name(file_path) not in selected_names:
            remove_actions.append({
                "name": os.path.splitext(os.path.basename(file_path))[0],
                "path": file_path,
            })

    playlist_actions = []
    if _looks_like_android_device_path(android_root):
        for playlist in selected_playlists:
            name = playlist.get("name", "Untitled")
            lines = ["#EXTM3U"]
            for song in playlist.get("tracks", []):
                location = _track_value(song, "Location", "location")
                if not location:
                    continue
                source = os.path.abspath(str(location).replace("file://", "").replace("/", "\\"))
                if not os.path.exists(source):
                    continue
                destination = _relative_destination_path(source, android_root)
                android_path = destination
                for key in _android_rel_keys(destination, norm_android_root):
                    if key in android_by_key:
                        android_path = android_by_key[key]
                        break
                duration = int(_track_value(song, "Total Time", "total_time") or -1000) // 1000
                artist = _track_value(song, "Artist", "artist") or ""
                track_name = _track_value(song, "Name", "name") or os.path.basename(source)
                lines.append(f"#EXTINF:{duration},{artist} - {track_name}")
                lines.append(android_path)
            safe_name = _sanitize_filename(name)
            playlist_actions.append({
                "name": name,
                "destination": _android_path_join(android_root, f"{safe_name}.m3u"),
                "content": "\n".join(lines) + "\n",
            })

    summary = {
        "copies": len(copy_actions),
        "removals": len(remove_actions),
        "play_count_updates": len(play_count_updates),
        "playlists": len(playlist_actions),
        "test_mode": test_mode,
        "android_root": android_root,
        "itunes_root": iTunes_root,
    }

    return {
        "copy": copy_actions,
        "remove": remove_actions,
        "play_count_updates": play_count_updates,
        "playlists": playlist_actions,
        "summary": summary,
    }


def execute_plan(plan, test_mode=False, serial=None):
    copied = 0
    removed = 0

    if test_mode:
        return {
            "copied": 0,
            "removed": 0,
            "preview": plan,
        }

    for item in plan.get("copy", []):
        if _copy_file(item["source"], item["destination"], serial=serial):
            copied += 1

    for item in plan.get("remove", []):
        if _remove_file(item["path"], serial=serial):
            removed += 1

    playlists_pushed = 0
    for playlist in plan.get("playlists", []):
        fd, temp_path = tempfile.mkstemp(suffix=".m3u")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(playlist["content"])
            if _copy_file(temp_path, playlist["destination"], serial=serial):
                playlists_pushed += 1
        finally:
            try:
                os.unlink(temp_path)
            except OSError:
                pass

    return {
        "copied": copied,
        "removed": removed,
        "playlists_pushed": playlists_pushed,
        "preview": plan,
    }
