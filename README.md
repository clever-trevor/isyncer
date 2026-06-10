# iSyncer

This project is a Windows-friendly music sync app for syncing selected iTunes playlists to an Android music folder.

## Run it

1. Install Python 3.12 or newer.
2. Download the [SDK platform tools for Windows](https://developer.android.com/tools/releases/platform-tools) from Android site
3. Extract these two files from the zip file ~~into~~ the directory where this code lives
   1. adb.exe
   2. AdbWinApi.dll
4. Double-click run_isyncer.cmd to launch the GUI.
5. In the UI, set the iTunes XML file and the Android target folder (for example, the Music folder on your connected Android device). Then choose the playlists to sync.

## What is included

- GUI for playlist selection and config updates
- Reads the iTunes XML library file
- Copies missing songs to the Android music root
- Removes songs present on Android but not in the selected playlists
- Test mode preview without copying or deleting files
- Progress/summary information in the UI
