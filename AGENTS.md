# Dedisc — OpenCode Instructions

## What we're building

Dedisc is a GTK4 + libadwaita CD ripper for Linux. It detects optical drives, reads audio CD metadata (TOC + CD-Text), displays album/track info offline, and rips tracks to WAV/FLAC/MP3. No network calls. All UI strings are English source with complete Polish translation (`po/pl.po`).

App id: `pl.septicwolf818.Dedisc` (reverse domain of septicwolf818.pl).

## Tech stack (verify before suggesting anything else)

| Layer | Choice |
|---|---|
| Language | Python 3.11+ |
| GUI | GTK4 + libadwaita via `gi.repository` (PyGObject 3.56+) |
| Build | Makefile (copy-based installer, no root); meson-python optional for system-wide packaging |
| Drive discovery | PyGObject `Gio.DBusProxy` → UDisks2 D-Bus API |
| CD metadata | `pycdio` (PyPI, wraps libcdio) for TOC + CD-Text |
| Disc ID | `discid` (PyPI) — optional library for future use |
| i18n | GNU gettext (`po/pl.po`, all UI strings) |

**System deps:** `gtk4`, `libadwaita`, `python-gobject`, `libcdio`, `libdiscid`, `udisks2`, `swig` (Arch: `pacman -S gtk4 libadwaita libcdio libdiscid udisks2 python-gobject swig`). `python-gobject` provides the `gi` module (`python-pycairo` alone is not enough); `swig` is required to build `pycdio` from source. MP3 uses `lameenc` (pip, bundles its own LAME) so needs no extra system package.

**PyPI deps:** `pycdio`, `discid`, `numpy`, `soundfile`.

## Commands

```bash
# Primary installer (copy-based, no root) — handles venv + patched pycdio + deps
make install      # install to ~/.local/share/Dedisc + launcher/desktop entry
make run          # dev: local venv, install deps, run from source
make uninstall    # remove installed files and venv

# Run from source (dev, no build needed)
PYTHONPATH=. python3 src/main.py

# i18n — extract new strings
xgettext --from-code=UTF-8 --language=Python \
  --keyword=_ --keyword=n_:1,2 \
  --output=po/dedisc.pot src/*.py src/ui/*.py

# Verify translations match
msgfmt --check -o /dev/null po/pl.po
```

The Makefile is the primary installer (copy-based install into the user's
home, no root). `meson.build` + `pyproject.toml` provide an **optional**
meson-python packaging path for system-wide/distro installs:
`meson setup build --prefix=/usr && ninja -C build && meson install -C build`.
`requirements.txt` holds runtime deps, `requirements-build.txt` holds build
deps — never mix them.

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
import pycdio, discid, numpy, soundfile, lameenc
print(f'GTK {Gtk.MAJOR_VERSION}.{Gtk.MINOR_VERSION}  Adwaita {Adw.MAJOR_VERSION}.{Adw.MINOR_VERSION}  MP3(lameenc)  ✅')
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
