import logging
import time
from dataclasses import dataclass, field
from typing import Optional, List

try:
    import cdio
    import pycdio
except ImportError:
    cdio = None
    pycdio = None

logger = logging.getLogger(__name__)

@dataclass
class TrackInfo:
    track_number: int
    start_frame: int
    duration_frames: int
    title: Optional[str] = None

@dataclass
class AlbumInfo:
    artist: Optional[str] = None
    album_title: Optional[str] = None
    disc_title: Optional[str] = None
    tracks: List[TrackInfo] = field(default_factory=list)

    def has_cdtext(self) -> bool:
        return bool(self.artist or self.album_title or self.disc_title
                    or any(t.title for t in self.tracks))

class CDReaderError(Exception):
    pass

class CDReader:
    @staticmethod
    def scan_cd(device_path: str, max_attempts: int = 5) -> AlbumInfo:
        if cdio is None:
            raise CDReaderError("pycdio not installed")

        logger.info("CDReader.scan_cd started device_path=%s max_attempts=%d", device_path, max_attempts)
        for attempt in range(1, max_attempts + 1):
            logger.debug("CDReader.scan_cd attempt %d of %d for %s", attempt, max_attempts, device_path)
            album = CDReader._scan_once(device_path)
            logger.info("CDReader.scan_cd attempt %d result has_cdtext=%d tracks=%d",
                        attempt, 1 if album.has_cdtext() else 0, len(album.tracks))
            if attempt < max_attempts and not album.has_cdtext():
                time.sleep(1)
                continue
            logger.info("CDReader.scan_cd returning after %d attempt(s)", attempt)
            return album
        logger.info("CDReader.scan_cd returning final result after reaching max_attempts")
        return CDReader._scan_once(device_path)

    @staticmethod
    def _scan_once(device_path: str) -> AlbumInfo:
        logger.info("CDReader._scan_once opening device=%s", device_path)
        device = None
        album_info = AlbumInfo()

        try:
            device = cdio.Device(device_path)
            if device.get_disc_mode() != 'CD-DA':
                err_msg = "Device %s is not an audio CD (mode=%s)", device_path, device.get_disc_mode()
                logger.error("CDReader._scan_once %s", err_msg[0] % err_msg[1:])
                raise CDReaderError("Device is not an audio CD")

            num_tracks = device.get_num_tracks()
            tracks: List[TrackInfo] = []

            for num in range(1, num_tracks + 1):
                track = device.get_track(num)
                duration = track.get_track_sec_count() or 0
                tracks.append(TrackInfo(
                    track_number=num,
                    start_frame=track.get_lsn() or 0,
                    duration_frames=duration,
                    title=None,
                ))

            cd_text_obj = device.get_cdtext()
            if cd_text_obj is not None:
                try:
                    disc_title = cd_text_obj.get(pycdio.CDTEXT_FIELD_TITLE, 0)
                    if disc_title:
                        album_info.disc_title = disc_title
                        album_info.album_title = disc_title
                    performer = cd_text_obj.get(pycdio.CDTEXT_FIELD_PERFORMER, 0)
                    if performer:
                        album_info.artist = performer
                    for t in tracks:
                        title = cd_text_obj.get(pycdio.CDTEXT_FIELD_TITLE, t.track_number)
                        if title:
                            t.title = title
                except Exception:
                    logger.warning("CD-Text not available on this disc")
            else:
                logger.warning("CD-Text not available on this disc")

            album_info.tracks = tracks
            return album_info

        finally:
            if device is not None:
                try:
                    device.close()
                except Exception:
                    pass

    @staticmethod
    def frames_to_seconds(frames: int) -> str:
        if frames is None or frames <= 0:
            return "0:00"
        total_seconds = frames / 75
        minutes = int(total_seconds // 60)
        seconds = int(total_seconds % 60)
        return f"{minutes}:{seconds:02d}"