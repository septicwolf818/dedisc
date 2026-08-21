# Dedisc — OpenCode Instructions

## What we're building

Dedisc is a GTK4 + libadwaita CD ripper for Linux. It detects optical drives, reads audio CD metadata (TOC + CD-Text), displays album/track info offline, and rips tracks to WAV/FLAC/MP3. No network calls. All UI strings are English source with complete Polish translation (`po/pl.po`).

App id: `pl.septicwolf818.Dedisc` (reverse domain of septicwolf818.pl).

## Tech stack (verify before suggesting anything else)

| Layer | Choice |
|---|---|
| Language | Python 3.11+ |
| GUI | GTK4 + libadwaita via `gi.repository` (PyGObject 3.56+) |
| Build | Meson + ninja (`meson-python`) — **not** pure pip |
| Drive discovery | PyGObject `Gio.DBusProxy` → UDisks2 D-Bus API |
| CD metadata | `pycdio` (PyPI, wraps libcdio) for TOC + CD-Text |
| Disc ID | `discid` (PyPI) — optional library for future use |
| i18n | GNU gettext (`po/pl.po`, all UI strings) |

**System deps:** `gtk4`, `libadwaita`, `python-pycairo`, `libcdio`, `libdiscid`, `udisks2` (Arch: `pacman -S gtk4 libadwaita python-pycairo libcdio libdiscid udisks2`).

**PyPI deps:** `pycdio`, `discid`, `numpy`, `soundfile`.

## Commands

```bash
# Setup (one-time): runtime deps + build deps
pip install -r requirements.txt -r requirements-build.txt

# Build (meson is the only build tool)
meson setup build --prefix=/usr
ninja -C build
meson install -C build            # installs to prefix, incl. .mo translations

# Run from source (dev, no build needed)
PYTHONPATH=. python3 src/main.py

# i18n — extract new strings
xgettext --from-code=UTF-8 --language=Python \
  --keyword=_ --keyword=n_:1,2 \
  --output=po/dedisc.pot src/*.py src/ui/*.py

# Verify translations match
msgfmt --check -o /dev/null po/pl.po
```

Meson is the only build tool. `requirements.txt` holds runtime deps, `requirements-build.txt` holds build deps — never mix them.

## Critical constraints (agent gotchas)

- **Never use shell scripts or subprocess for CD detection.** Use `Gio.DBusProxy` for UDisks2 and `pycdio` for disc reading. This is a firm rule from the architecture decision.
- All user-facing strings must be wrapped in `_()` — no hardcoded UI text, even in error messages/tooltips/placeholders.
- Polish locale (`pl`) is the initial/primary translation target. Default system fallback should work. Test with `LANGUAGE=pl python3 src/main.py`.
- CD-Text may be absent on many discs — always handle `None` titles gracefully (fallback: `"…"`, tooltip: _("Track title is not available on this CD")).
- Audio frame duration uses the CD-DA standard of **75 frames per second** (not 44100 Hz audio). Use `frames / 75`.

## Architecture outline

```
main.py ──▶ window.py (Adw.ApplicationWindow)
                 ├── cd_manager.py (UDisks2 D-Bus monitor, background thread)
                 ├── cd_reader.py   (pycdio TOC/CD-Text reader, GTask worker)
                 ├── cd_ripper.py   (WAV/FLAC/MP3 ripping via pycdio + soundfile)
                 ├── settings.py    (settings persistence, naming schemes, formats)
                 ├── ui/track_list.py  (Gtk.ColumnView + ListStore)
                 ├── ui/preferences.py (Adw.PreferencesWindow + live path preview)
                 └── ui/status_page.py (Adw.StatusPage — no-drive / no-media states)
```

Data flow: UDisks2 DBus signal → `CDManager` → `GLib.idle_add(event)` → window switches to SCANNING state → `CDReader.scan_cd` reads TOC/CD-Text → window switches to LOADED state → populate track list → `CDRipper.rip` in a worker thread → `GLib.idle_add` progress + conflict dialogs.

**Always marshal UI updates via `GLib.idle_add()` — never touch GTK from background threads.**

## Quick dependency check (paste if new environment)

```bash
python3 -c "
import gi; gi.require_version('Gtk','4.0')
from gi.repository import Gtk, Adw
import pycdio, discid, numpy, soundfile
print(f'GTK {Gtk.MAJOR_VERSION}.{Gtk.MINOR_VERSION}  Adwaita {Adw.MAJOR_VERSION}.{Adw.MINOR_VERSION}  ✅')
"
```

## File map

| Path | Purpose |
|---|---|
| `meson.build` | Root build |
| `pyproject.toml` | Python packaging (meson-python backend) |
| `data/pl.septicwolf818.Dedisc.{desktop,svg}` | Desktop entry + app icon |
| `src/main.py` | Adw.Application entry point |
| `src/window.py` | Main window + stack state machine |
| `src/cd_manager.py` | UDisks2 D-Bus drive/media monitor |
| `src/cd_reader.py` | pycdio TOC/CD-Text extraction |
| `src/cd_ripper.py` | WAV/FLAC/MP3 ripping via pycdio + soundfile |
| `src/settings.py` | Settings persistence, naming schemes, formats |
| `src/i18n.py` | Gettext setup |
| `src/ui/track_list.py` | Gtk.ColumnView track widget |
| `src/ui/status_page.py` | StatusPage widgets (empty/error states) |
| `src/ui/preferences.py` | Preferences window (drive, output, naming, format, preview) |
| `src/ui/about.py` | About dialog |
| `po/pl.po` | Polish translation (always keep up-to-date with `_()` additions) |
