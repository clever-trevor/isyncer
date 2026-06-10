import copy
import json
from pathlib import Path

CONFIG_FILE = Path(__file__).with_name("isyncer_config.json")

DEFAULT_CONFIG = {
    "itunes_library": r"E:\Music\iTunes\iTunes Music Library.xml",
    "android_music_root": r"E:\Music\Android",
    "selected_playlists": [],
    "test_mode": True,
}


def load_config(path: Path | None = None) -> dict:
    config_path = Path(path) if path else CONFIG_FILE
    if not config_path.exists():
        return copy.deepcopy(DEFAULT_CONFIG)

    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
    except json.JSONDecodeError:
        return copy.deepcopy(DEFAULT_CONFIG)

    merged = copy.deepcopy(DEFAULT_CONFIG)
    merged.update(loaded)
    return merged


def save_config(config: dict, path: Path | None = None) -> None:
    config_path = Path(path) if path else CONFIG_FILE
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)
