# Alice's Clip of Holding

A bag of holding for the Windows clipboard.

Copy still goes to the normal OS clipboard. Every copy is also written into a local **clip folder** in the payload's genuine file type. Paste no longer dumps only the last item — **Ctrl+V opens a menu of everything in the bag**, and you choose what comes out.

## Install (this is the whole setup)

Prerequisite: [Python 3.10+](https://www.python.org/downloads/windows/) with **Add python.exe to PATH** checked.

Then, from the cloned or unzipped repo:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

That command:

1. Creates `%LOCALAPPDATA%\AlicesClipOfHolding\venv`
2. Installs the app and its dependencies there
3. Drops a Startup shortcut so it comes back after reboot
4. Drops a Desktop shortcut
5. Starts the tray app immediately

After that there is nothing else to configure. Copy and paste as usual.

Uninstall:

```powershell
powershell -ExecutionPolicy Bypass -File .\uninstall.ps1
```

## How it behaves

| Action | Result |
| --- | --- |
| Ctrl+C, or right-click **Copy** | OS clipboard updates **and** a new file is written into the bag |
| Ctrl+V | Picker opens over the bag. Enter pastes the highlighted item |
| Ctrl+Shift+V | Native last-item paste (no menu) |
| Delete in the picker | Drops that item from the bag |
| Tray icon | Open bag / Quit |

Right-click **Paste** in other programs still pastes whatever is currently on the OS clipboard. After you pick an item from the bag, that item *is* the OS clipboard, so the next context-menu Paste uses it. Replacing the system context-menu Paste entry itself requires a shell extension and is not part of v1.

## What gets stored

Each capture becomes a folder under:

```text
%LOCALAPPDATA%\AlicesClipOfHolding\clips\<timestamp>\
    meta.json
    item.txt | item.png | item.html | item.rtf | original-name.ext
```

| Clipboard content | File written |
| --- | --- |
| Plain text | `item.txt` (UTF-8) |
| HTML | `item.html` plus `item.txt` sidecar when available |
| Rich text | `item.rtf` |
| Image with real PNG bytes (Chrome, Edge, many editors) | `item.png` untouched |
| Image as a bitmap / DIB only | lossless `item.png` |
| Copied files | the original filename and extension, byte-for-byte |

Identical consecutive payloads (same SHA-256) are not stored twice. Oldest clips are pruned after 200 items (`max_clips` in `config.json`).

Nothing leaves the machine. There is no account, no network call, no cloud bag.

## Run from source (dev)

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\pip install -e .
.\.venv\Scripts\python -m alices_clip
```

## Layout

```text
src/alices_clip/
  models.py          ClipRecord contract
  config.py          paths + settings
  storage.py         clip folder + index
  win_clipboard.py   capture + restore, format-faithful
  hotkeys.py         Ctrl+V hook
  picker.py          bag menu
  tray.py            notification-area icon
  app.py             composition root
```

## Requirements

- Windows 10 or 11
- Python 3.10+
- Accessibility / input hooks allowed for the user session (standard for clipboard managers). Some games running as administrator will not see the Ctrl+V intercept unless this app is also elevated.

## License

MIT. See [LICENSE](LICENSE).
