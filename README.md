# Dedisc - Offline CD ripper for GNOME

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
below - no manual `pip install` needed.

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

## Usage

1. Insert an audio CD.
2. Dedisc scans the disc, shows artist/album/track list.
3. Select tracks.
4. Open *Preferences* (Ctrl+,) to set output folder, naming scheme and format.
5. Click *Rip selected* to rip.

## Development

Translations are handled via gettext. Refresh the UI template and sync
desktop-entry strings (`GenericName`, `Comment`) with:

```bash
make update-po    # runs xgettext + tools/sync_desktop_po.py (also regenerates po/LINGUAS)

# Merge new and changed UI msgids into every existing language catalog
for po in po/*.po; do
  msgmerge --update --no-fuzzy-matching --backup=none "$po" po/dedisc.pot
done
```

Desktop-entry strings are not extracted by xgettext; the sync script appends
them to every `po/<lang>.po` automatically and they are merged into the
installed desktop file at install time via `msgfmt --desktop`. Existing
translations are never overwritten. `msgmerge` updates the normal UI catalogs;
review its output, translate every new or changed UI entry in every language,
and keep format placeholders such as `{path}` intact. Old msgids no longer in
the source become obsolete entries rather than being silently discarded.

Validate all catalogs and their format placeholders:

```bash
for po in po/*.po; do
  msgfmt --check --check-format -o /dev/null "$po"
done
```

To add a new language, create `po/<lang>.po` from the template, then run
`make update-po` once so the desktop-entry entries and `po/LINGUAS` pick it
up (add it to the `languages` list in `po/meson.build` only for the optional
meson install path):

```bash
msginit --locale=<lang> --input=po/dedisc.pot --output=po/<lang>.po
make update-po
```

Then run the `msgmerge` loop above for all catalogs and complete the new
language's translations before validating them.

The i18n module compiles every `po/<lang>.po` → `po/<lang>/LC_MESSAGES/dedisc.mo` on demand when running from source, so translations are picked up automatically.

## Contributing

Issues and patches are welcome. Keep UI strings wrapped in `_()`. Prefer English as source language.

## License

MIT - see `LICENSE`.

Author: Rafał Widło <rafal.widlo@gmail.com>

Website: https://septicwolf818.pl
