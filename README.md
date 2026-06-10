# iSyncer

A Windows desktop app for syncing selected iTunes playlists to an Android device over USB.

## Pre-requisites

1. **Android device** — enable Developer Mode and USB Debugging on the device.
2. **Python 3.12+** — download from [python.org](https://www.python.org/downloads/).
3. **ADB platform tools** — download the [SDK Platform Tools for Windows](https://developer.android.com/tools/releases/platform-tools) from the Android site, then extract these two files into the same folder as this code:
   - `adb.exe`
   - `AdbWinApi.dll`

## Setup

Open a terminal in the project folder and run:

```cmd
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

## Run

Double-click **`run_isyncer.cmd`** to launch the app (no terminal window needed).

## First-time configuration

1. Set the **iTunes library** path (e.g. `E:\Music\iTunes\iTunes Music Library.xml`).
2. Set the **Android folder** — click Browse to navigate the device directly, or type a path such as `/sdcard/Music`.
3. Select which **playlists** to sync.
4. Click **Save config** — settings are stored in `isyncer_config.json`.

## Syncing

1. Connect your Android device via USB and make sure it appears in the **ADB device** dropdown (click Refresh if needed).
2. Tick **Test mode** and click **Run sync** to preview what will be copied or removed — no files are changed.
3. Once happy, untick **Test mode** and click **Run sync** again to perform the actual sync.

## Features

- Copies songs in selected playlists that are missing from the device
- Removes songs from the device that are no longer in any selected playlist
- Generates and pushes `.m3u` playlist files to the device
- Reads play counts from the device (`isyncr.xml`) and adds them back to iTunes
- Resets `isyncr.xml` after a live sync so counts are not double-applied
- Test mode preview without making any changes
- Live progress and summary in the UI
