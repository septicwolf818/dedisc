import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List
import gi
gi.require_version('Gtk','4.0')
gi.require_version('Adw','1')

from src.i18n import _

DOMAIN = 'dedisc'
APP_ID = 'pl.septicwolf818.Dedisc'

@dataclass
class NamingScheme:
    scheme_id: str
    label: str
    folder_pattern: str
    filename_pattern: str

NAMING_SCHEMES = [
    NamingScheme(
        scheme_id='artist-album-track-title',
        label=_('Artist / Album / Track - Title'),
        folder_pattern='{artist}/{album}',
        filename_pattern='{track:02d} - {title}',
    ),
    NamingScheme(
        scheme_id='artist-album-trackdot-title',
        label=_('Artist / Album / Track. Title'),
        folder_pattern='{artist}/{album}',
        filename_pattern='{track:02d}. {title}',
    ),
    NamingScheme(
        scheme_id='artist-album-title',
        label=_('Artist / Album / Title'),
        folder_pattern='{artist}/{album}',
        filename_pattern='{title}',
    ),
    NamingScheme(
        scheme_id='artist-album-artist-title',
        label=_('Artist - Album / Track - Artist - Title'),
        folder_pattern='{artist} - {album}',
        filename_pattern='{track:02d} - {artist} - {title}',
    ),
    NamingScheme(
        scheme_id='artist-album-title-artist',
        label=_('Artist / Album / Track - Title - Artist'),
        folder_pattern='{artist}/{album}',
        filename_pattern='{track:02d} - {title} - {artist}',
    ),
    NamingScheme(
        scheme_id='album-track-title',
        label=_('Album / Track - Title'),
        folder_pattern='{album}',
        filename_pattern='{track:02d} - {title}',
    ),
    NamingScheme(
        scheme_id='album-track-artist-title',
        label=_('Album / Track - Artist - Title'),
        folder_pattern='{album}',
        filename_pattern='{track:02d} - {artist} - {title}',
    ),
    NamingScheme(
        scheme_id='artist-track-title',
        label=_('Artist / Track - Title'),
        folder_pattern='{artist}',
        filename_pattern='{track:02d} - {title}',
    ),
]

OUTPUT_FORMATS = [
    ('wav', 'WAV'),
    ('flac', 'FLAC'),
    ('mp3', 'MP3'),
]

class Settings:
    def __init__(self):
        self.output_dir: str = str(Path.home() / 'Music')
        self.naming_scheme_id: str = 'artist-album-track-title'
        self.output_format: str = 'wav'
        self.selected_drive_obj_path: str = ''
        self.eject_when_done: bool = False
        self._config_file = self._config_path()
        self.load()

    def _config_path(self) -> Path:
        base = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
        return base / APP_ID / 'settings.json'

    def load(self):
        try:
            data = json.loads(self._config_file.read_text(encoding='utf-8'))
            self.output_dir = data.get('output_dir', self.output_dir)
            self.naming_scheme_id = data.get('naming_scheme_id', self.naming_scheme_id)
            self.output_format = data.get('output_format', self.output_format)
            self.selected_drive_obj_path = data.get('selected_drive_obj_path', '')
            self.eject_when_done = bool(data.get('eject_when_done', False))
        except (OSError, ValueError):
            pass

    def save(self):
        try:
            self._config_file.parent.mkdir(parents=True, exist_ok=True)
            self._config_file.write_text(json.dumps({
                'output_dir': self.output_dir,
                'naming_scheme_id': self.naming_scheme_id,
                'output_format': self.output_format,
                'selected_drive_obj_path': self.selected_drive_obj_path,
                'eject_when_done': self.eject_when_done,
            }, indent=2), encoding='utf-8')
        except OSError:
            pass

    def get_naming_scheme(self) -> NamingScheme:
        for scheme in NAMING_SCHEMES:
            if scheme.scheme_id == self.naming_scheme_id:
                return scheme
        return NAMING_SCHEMES[0]

    def get_output_extension(self) -> str:
        if self.output_format == 'flac':
            return 'flac'
        if self.output_format == 'mp3':
            return 'mp3'
        return 'wav'