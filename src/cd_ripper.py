import logging
import os
import re
import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

import gi
gi.require_version('Gtk','4.0')
gi.require_version('Adw','1')
from gi.repository import GLib

try:
    import cdio
    import pycdio
except ImportError:
    cdio = None
    pycdio = None

import numpy as np
import soundfile as sf

from src.i18n import _
from src.settings import Settings, NamingScheme
from src.cd_reader import AlbumInfo, TrackInfo

logger = logging.getLogger(__name__)

AUDIO_FRAME_BYTES = 2352
CHUNK_SECTORS = 25
CD_FRAMES_PER_SECOND = 75
SAMPLES_PER_FRAME = 588  # 2352 bytes / (2 channels * 2 bytes)

SFFORMAT = {
    'wav': ('WAV', 'PCM_16'),
    'flac': ('FLAC', 'PCM_16'),
    'mp3': ('MP3', 'MPEG_LAYER_III'),
}

@dataclass
class RipProgress:
    track_number: int
    track_title: str
    current: int
    total: int
    finished: bool = False
    overall_current: int = 0
    overall_total: int = 0

class ConflictAction(Enum):
    OVERWRITE = 'overwrite'
    SKIP = 'skip'
    CANCEL = 'cancel'

class ConflictCallback:
    """Bridge a worker-thread file-exists question to the main loop dialog."""
    def __init__(self, window, on_decision):
        self.window = window
        self.on_decision = on_decision
        self._result: Optional[ConflictAction] = None
        self._event = threading.Event()

    def ask(self, file_path: str) -> ConflictAction:
        self._result = None
        self._event.clear()
        GLib.idle_add(self._show, file_path)
        self._event.wait()
        return self._result

    def _show(self, file_path: str):
        self.on_decision(file_path, self._resolve)
        return False

    def _resolve(self, action: ConflictAction):
        self._result = action
        self._event.set()


def build_destination_path(output_dir, scheme: NamingScheme, extension: str,
                           artist, album, track_number, title) -> Path:
    """Build the full destination path for a track using the given naming scheme."""
    artist = _safe(artist) or _("Unknown Artist")
    album = _safe(album) or _("Unknown Album")
    title = _safe(title) or _("Track {number}").format(number=track_number)

    folder = scheme.folder_pattern.format(artist=artist, album=album)
    filename = scheme.filename_pattern.format(
        artist=artist, album=album,
        track=track_number, title=title,
    )
    return Path(output_dir) / folder / f"{filename}.{extension}"


def _safe(text: Optional[str]) -> str:
    if not text:
        return ''
    text = re.sub(r'[\\/:*?"<>|]', '_', text.strip())
    text = re.sub(r'\s+', ' ', text)
    return text.strip().rstrip('.')


class CDRipper:
    def __init__(self, settings: Settings, album: AlbumInfo, tracks: list[TrackInfo]):
        self.settings = settings
        self.album = album
        self.tracks = tracks
        self._cancelled = threading.Event()

    def cancel(self):
        self._cancelled.set()

    def rip(self, device_path: str, on_progress: Callable[[RipProgress], None],
            conflict_cb: ConflictCallback):
        """Rip selected tracks. Runs in a worker thread."""
        if cdio is None:
            raise RuntimeError(_("pycdio not installed"))

        dev = None
        try:
            dev = cdio.Device(device_path)
            if dev.get_disc_mode() != 'CD-DA':
                raise RuntimeError(_("Device is not an audio CD"))

            self._album_total = 0
            for track in self.tracks:
                tobj = dev.get_track(track.track_number)
                self._album_total += (tobj.get_track_sec_count() or 0) * AUDIO_FRAME_BYTES
            self._completed_bytes = 0

            scheme = self.settings.get_naming_scheme()
            extension = self.settings.get_output_extension()

            for track in self.tracks:
                if self._cancelled.is_set():
                    break
                target = self._destination_path(track, scheme, extension)
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    action = conflict_cb.ask(str(target))
                    if action == ConflictAction.CANCEL:
                        break
                    if action == ConflictAction.SKIP:
                        continue

                self._rip_track(dev, track, target, on_progress)

        finally:
            if dev is not None:
                try:
                    dev.close()
                except Exception:
                    pass

    def _destination_path(self, track: TrackInfo, scheme: NamingScheme, extension: str) -> Path:
        return build_destination_path(
            self.settings.output_dir, scheme, extension,
            self.album.artist, self.album.album_title or self.album.disc_title,
            track.track_number, track.title,
        )

    def _rip_track(self, dev, track: TrackInfo, target: Path,
                   on_progress: Callable[[RipProgress], None]):
        track_obj = dev.get_track(track.track_number)
        lsn = track_obj.get_lsn() or 0
        total_frames = track_obj.get_track_sec_count() or 0

        tmp_target = target.with_suffix(target.suffix + '.part')
        written = 0
        remaining = total_frames
        pos = lsn
        chunks = []

        sf_format, sf_subtype = SFFORMAT.get(
            self.settings.output_format, SFFORMAT['wav'])

        while remaining > 0:
            if self._cancelled.is_set():
                break
            n = min(CHUNK_SECTORS, remaining)
            drc, chunk = dev.read_sectors(pos, pycdio.READ_MODE_AUDIO, n)
            data = chunk.encode('utf-8', 'surrogateescape')
            expected = n * AUDIO_FRAME_BYTES
            if len(data) != expected:
                if drc < n:
                    break
                data = data[:expected]
            data = data[:len(data) // 4 * 4]
            pcm = np.frombuffer(data, dtype=np.int16).reshape(-1, 2)
            chunks.append(pcm)
            written += len(data)
            pos += n
            remaining -= n
            on_progress(RipProgress(
                track_number=track.track_number,
                track_title=track.title or '',
                current=written,
                total=total_frames * AUDIO_FRAME_BYTES,
                overall_current=self._completed_bytes + written,
                overall_total=self._album_total,
            ))

        if self._cancelled.is_set():
            tmp_target.unlink(missing_ok=True)
            return

        # Write the full PCM buffer in a single call. libsndfile's MP3 (LAME)
        # encoder produces broken/clicky output, so MP3 is encoded with lameenc
        # instead; WAV/FLAC keep using soundfile.
        audio = np.concatenate(chunks, axis=0) if chunks else np.zeros((0, 2), dtype=np.int16)
        if self.settings.output_format == 'mp3':
            self._write_mp3(tmp_target, audio)
        else:
            with sf.SoundFile(str(tmp_target), 'w', samplerate=44100,
                               channels=2, format=sf_format, subtype=sf_subtype) as f:
                f.write(audio)

        os.replace(tmp_target, target)
        self._write_tags(target, self.settings.output_format, track)
        self._completed_bytes += total_frames * AUDIO_FRAME_BYTES
        on_progress(RipProgress(
            track_number=track.track_number,
            track_title=track.title or '',
            current=total_frames * AUDIO_FRAME_BYTES,
            total=total_frames * AUDIO_FRAME_BYTES,
            overall_current=self._completed_bytes,
            overall_total=self._album_total,
            finished=True,
        ))

    def _write_tags(self, target: Path, extension: str, track: TrackInfo):
        """Write common tags (artist, album, title, track number) to the
        ripped file. FLAC and MP3 use full tag containers; WAV uses the INFO
        chunk. Best-effort: a missing mutagen install or unsupported file is
        silently skipped so ripping never fails because of metadata."""
        try:
            from mutagen.flac import FLAC
            from mutagen.mp3 import EasyMP3
            from mutagen.wave import WAVE
            from mutagen.id3 import TIT2, TPE1, TALB, TRCK
        except ImportError:
            return

        artist = self.album.artist or ''
        album = self.album.album_title or self.album.disc_title or ''
        title = track.title or ''
        total = len(self.tracks)
        track_number = track.track_number

        try:
            if extension == 'flac':
                f = FLAC(str(target))
                f['ARTIST'] = artist
                f['ALBUM'] = album
                f['TITLE'] = title
                f['TRACKNUMBER'] = str(track_number)
                if total:
                    f['TRACKTOTAL'] = str(total)
                f.save()
            elif extension == 'mp3':
                m = EasyMP3(str(target))
                m['artist'] = artist
                m['album'] = album
                m['title'] = title
                m['tracknumber'] = f"{track_number}/{total}" if total else str(track_number)
                m.save()
            elif extension == 'wav':
                w = WAVE(str(target))
                if w.tags is None:
                    w.add_tags()
                tags = w.tags
                tags.add(TIT2(encoding=3, text=title))
                tags.add(TPE1(encoding=3, text=artist))
                tags.add(TALB(encoding=3, text=album))
                tags.add(TRCK(encoding=3, text=f"{track_number}/{total}" if total else str(track_number)))
                w.save()
        except Exception as e:
            logger.warning("Failed to write tags to %s: %s", target, e)

    def _write_mp3(self, target: Path, audio: np.ndarray):
        """Encode PCM to MP3 with lameenc (libsndfile's MP3 writer is broken
        and produces ticking/scratching artifacts). Falls back to soundfile if
        lameenc is unavailable so ripping never fails outright."""
        try:
            import lameenc
        except ImportError:
            with sf.SoundFile(str(target), 'w', samplerate=44100, channels=2,
                               format='MP3', subtype='MPEG_LAYER_III') as f:
                f.write(audio)
            return
        enc = lameenc.Encoder()
        enc.set_bit_rate(320)
        enc.set_in_sample_rate(44100)
        enc.set_channels(2)
        enc.set_quality(2)
        data = enc.encode(audio.tobytes()) + enc.flush()
        with open(target, 'wb') as fh:
            fh.write(data)