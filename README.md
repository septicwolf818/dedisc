# Dedisc — Offline CD ripper for GNOME

An offline GTK4/libadwaita CD scanner and ripper for Linux. Detect optical drives via UDisks2, read TOC and CD-Text with pycdio, preview album/track info, and rip tracks to WAV/FLAC/MP3. No network calls.

## Features

- Automatic optical drive detection with UDisks2
- TOC/CD-Text reading with `pycdio`
- Album/track list with selectable tracks
- Preferences: drive selection, output folder, naming schemes, output format
- Live preview of destination path using the first track of the inserted disc
- Ripping to WAV/FLAC/MP3 (WAV/FLAC via `soundfile`, MP3 via `lameenc`)
- Conflict handling: overwrite / skip / cancel
- Gettext i18n with on-demand `.mo` compilation for development

## System dependencies

Arch Linux:

```bash
pacman -S gtk4 libadwaita libcdio udisks2 python-gobject swig
```

`swig` is required to build `pycdio` from source. All Python
dependencies (including a patched `pycdio` for Python 3.14 and `lameenc`
for MP3) are installed automatically into a bundled venv by the Makefile
below — no manual `pip install` needed.

## Install

The provided Makefile does a copy-based install into your home directory
(no root required) and sets up a launcher and desktop entry:

```bash
make install      # install to ~/.local/share/Dedisc + create launcher/desktop entry
make run          # dev: create a local venv, install deps, run from source
make uninstall    # remove the installed files and venv
```

### Alternative: meson packaging

For a system-wide package install (e.g. distro packaging) use meson:

```bash
meson setup build --prefix=/usr
ninja -C build
meson install -C build            # installs to prefix, incl. .mo translations
```

Run from source without install:

```bash
PYTHONPATH=. python3 src/main.py
```

## Usage

1. Insert an audio CD.
2. Dedisc scans the disc, shows artist/album/track list.
3. Select tracks.
4. Open *Preferences* (Ctrl+,) to set output folder, naming scheme and format.
5. Click *Zgraj zaznaczone* to rip.

## Development

Translations are handled via gettext. Extract new strings:

```bash
xgettext --from-code=UTF-8 --language=Python \
  --keyword=_ --keyword=n_:1,2 \
  --output=po/dedisc.pot src/*.py src/ui/*.py
```

Verify translations:

```bash
msgfmt --check -o /dev/null po/pl.po
```

The i18n module compiles `po/pl.po` → `po/pl/LC_MESSAGES/dedisc.mo` on demand when running from source.

## Contributing

Issues and patches are welcome. Keep UI strings wrapped in `_()`. Prefer English as source language.

## License

MIT — see `LICENSE`.

Author: Rafał Widło <rafal.widlo@gmail.com>

Website: https://septicwolf818.pl