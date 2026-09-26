# Alice's Clip of Holding

A bag of holding for the Windows clipboard.

Copy still goes to the normal OS clipboard. Every copy is also written into a local **clip folder** in the payload's genuine file type. Paste no longer dumps only the last item — **Ctrl+V opens a menu of everything in the bag**, and you choose what comes out.

## Install

### Option A — just the `.exe` (recommended)

1. Grab `AlicesClipOfHolding.exe` from [Releases](https://github.com/GalacticOrgOfDev/Alices-Clip-of-Holding/releases).
2. Double-click it.

That is the whole setup. The exe copies itself into `%LOCALAPPDATA%\AlicesClipOfHolding\bin\`, registers Explorer verbs, adds a Start Menu / Apps & Features entry, starts with Windows, and lives in the tray.

To build that exe on a Windows machine from this repo:

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

GitHub Actions also builds it on every `v*` tag and on `main`.

### Option B — from source

Python 3.10+ with **Add python.exe to PATH**, then:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

## Uninstall

Any of these opens the same prompt — **keep clip files** or **delete clip files**:

- Settings → Apps → Installed apps → Alice's Clip of Holding → Uninstall
- Start Menu → Alice's Clip of Holding → Uninstall Alice's Clip of Holding
- Tray icon → Uninstall…
- `uninstall.ps1` in this repo

Cancel leaves everything installed.

## How it behaves

| Action | Result |
| --- | --- |
| Ctrl+C, or an app's Copy command | OS clipboard updates **and** a new file is written into the bag |
| Ctrl+V | Picker opens over the bag. Enter pastes the highlighted item |
| Ctrl+Shift+V | Native last-item paste (no menu) |
| Explorer: right-click file(s) → **Copy to Alice's Clip of Holding** | Those files go into the bag with their real names and extensions |
| Explorer: right-click a folder or empty folder background → **Paste from Alice's Clip of Holding** | Picker opens; the chosen clip is written into that folder |
| Settings → Apps → Uninstall | Prompt to keep or clear the clip folder |

Other programs' own **Paste** command still pastes the current OS clipboard. After you pick an item from the bag, that item *is* the OS clipboard.

Explorer multi-select asks the live Explorer window for every highlighted file, not just the first.

## What gets stored

```text
%LOCALAPPDATA%\AlicesClipOfHolding\clips\<timestamp>\
    meta.json
    item.txt | item.png | item.html | item.rtf | original-name.ext
```

Identical consecutive payloads are not stored twice. Oldest clips prune after 200 items.
Nothing leaves the machine.

## Requirements

- Windows 10 or 11
- The packaged exe needs no extra runtime
- Source installs need Python 3.10+

## License

MIT. See [LICENSE](LICENSE).
