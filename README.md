# iSyncer

This project is a Windows Python app for syncing selected iTunes playlists to an Android device.

## Pre-Reqs
1. Set up Developer Mode on your Android device, and enable USB debugging
2. Install Python 3.12 or newer.
3. Download the [SDK platform tools for Windows](https://developer.android.com/tools/releases/platform-tools) from Android site
4. Extract these two files from the zip file into the directory where this code lives
   - adb.exe
   - AdbWinApi.dll

## Run it

1. Double-click run_isyncer.cmd to launch the GUI.
2. In the UI, set the iTunes XML file and the Android target folder (for example, the Music folder on your connected Android device). 
3. Choose the playlists to sync.
4. Select the Test Mode option to see what it will copy or delete on the Android device
5. Once happy, untick Test Mode and Run Sync again

## What is included

- GUI for playlist selection and config updates
- Reads the iTunes XML library file
- Copies missing songs to the Android music root
- Removes songs present on Android but not in the selected playlists
- Test mode preview without copying or deleting files
- Progress/summary information in the UI
