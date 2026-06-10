import os
import re
import urllib.parse
import xml.etree.ElementTree as ET


def _parse_plist_node(node):
    tag = node.tag

    if tag == "plist":
        children = [_parse_plist_node(child) for child in node]
        return children[0] if len(children) == 1 else children

    if tag == "dict":
        result = {}
        children = list(node)
        index = 0
        while index < len(children):
            current = children[index]
            if current.tag != "key":
                index += 1
                continue

            key = current.text or ""
            index += 1
            if index >= len(children):
                break

            value = _parse_plist_node(children[index])
            result[key] = value
            index += 1
        return result

    if tag == "array":
        return [_parse_plist_node(child) for child in node]

    if tag in {"string", "data"}:
        return "".join(node.itertext()).strip()

    if tag == "true":
        return True

    if tag == "false":
        return False

    if tag in {"integer", "real"}:
        text = "".join(node.itertext()).strip()
        return int(float(text)) if tag == "integer" else float(text)

    return "".join(node.itertext()).strip()


def load_plist(path):
    tree = ET.parse(path)
    root = tree.getroot()
    return _parse_plist_node(root)


def normalize_file_path(value):
    if not value:
        return value

    candidate = urllib.parse.unquote(str(value).strip())

    if candidate.startswith("file://"):
        candidate = candidate.replace("file://", "", 1)
        if candidate.startswith("localhost/"):
            candidate = candidate[len("localhost/") :]
        if re.match(r"^/[A-Za-z]:", candidate):
            candidate = candidate[1:]

    candidate = candidate.replace("\\", "/")
    candidate = candidate.replace("//", "/") if not candidate.startswith("//") else candidate

    if re.match(r"^[A-Za-z]:/", candidate):
        candidate = candidate.replace("/", "\\")
        return os.path.normpath(candidate)

    if candidate.startswith("/") and re.match(r"^/[^/]+/", candidate):
        candidate = "\\" + candidate.lstrip("/").replace("/", "\\")
        return os.path.normpath(candidate)

    candidate = candidate.replace("/", "\\")
    return os.path.normpath(candidate)


def parse_itunes_library(path):
    plist = load_plist(path)
    tracks = plist.get("Tracks", {}) if isinstance(plist.get("Tracks"), dict) else {}
    playlists = plist.get("Playlists", []) if isinstance(plist.get("Playlists"), list) else []

    normalized_tracks = {}
    for track_id, raw_track in tracks.items():
        track = dict(raw_track)
        location = track.get("Location")
        if location:
            track["Location"] = normalize_file_path(location)
        normalized_tracks[str(track_id)] = track

    playlist_list = []
    for playlist in playlists:
        if not isinstance(playlist, dict):
            continue

        items = playlist.get("Playlist Items", [])
        song_ids = []
        songs = []

        for item in items:
            if isinstance(item, dict) and "Track ID" in item:
                track_id = str(item["Track ID"])
                song_ids.append(track_id)
                if track_id in normalized_tracks:
                    songs.append(normalized_tracks[track_id])

        playlist_list.append({
            "name": playlist.get("Name", "Untitled playlist"),
            "persistent_id": playlist.get("Persistent ID", ""),
            "track_ids": song_ids,
            "tracks": songs,
        })

    return {
        "tracks": normalized_tracks,
        "playlists": playlist_list,
        "plist": plist,
    }
