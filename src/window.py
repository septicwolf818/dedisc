from enum import IntEnum
from typing import TYPE_CHECKING, Optional
import gi
gi.require_version('Gtk','4.0')
gi.require_version('Adw','1')
from gi.repository import Gtk, Adw, GLib, Gio
from threading import Thread
import multiprocessing
import queue

if TYPE_CHECKING:
    from src.cd_ripper import CDRipper

from src.i18n import _
from src.cd_manager import CDManager, DriveEvent, CDInfo
from src.cd_reader import CDReader, AlbumInfo
from src.cd_ripper import ConflictAction, run_rip, build_destination_path
from src.ui.track_list import TrackList

class WindowState(IntEnum):
    EMPTY = 0
    NO_MEDIA = 1
    SCANNING = 2
    LOADED = 3

class RipperWindow(Adw.ApplicationWindow):
    def __init__(self, device=None, **kwargs):
        super().__init__(**kwargs)
        self.set_default_size(600, 500)
        self.set_title(_("Dedisc"))

        self._state = WindowState.EMPTY
        self._cd_manager: Optional[CDManager] = None
        self._cd_reader = CDReader()
        self._current_cd_info = None
        self._current_album: Optional[AlbumInfo] = None
        self._requested_device = device
        self._rip_start_time = None
        self._pending_rip = None
        self._rip_process = None
        self._rip_queue = None
        self._rip_cancel = None
        self._rip_timer = None
        self._rip_finished = False

        self.stack = Gtk.Stack()

        self.toolbar = Adw.ToolbarView()
        self.toolbar.set_content(self.stack)
        self.set_content(self.toolbar)

        self.header = Adw.HeaderBar()
        self.title_widget = Adw.WindowTitle(title=_("Dedisc"))
        self.header.set_title_widget(self.title_widget)

        self.eject_button = Gtk.Button(icon_name='media-eject-symbolic')
        self.eject_button.set_tooltip_text(_("Eject Disc"))
        self.eject_button.connect('clicked', self._on_eject_clicked)
        self.eject_button.set_visible(False)
        self.header.pack_start(self.eject_button)

        self.menu_button = Gtk.MenuButton()
        self.menu_button.set_icon_name('open-menu-symbolic')
        self.menu_button.set_tooltip_text(_("Main Menu"))
        self.menu_button.set_menu_model(self._build_menu())
        self.header.pack_end(self.menu_button)

        self.toolbar.add_top_bar(self.header)

        from src.ui.status_page import create_no_drive_status_page, create_no_media_status_page
        self.status_no_drive = create_no_drive_status_page()
        self.status_no_media = create_no_media_status_page()
        self.stack.add_named(self.status_no_drive, "no-drive")
        self.stack.add_named(self.status_no_media, "no-media")

        self.scanning_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.scanning_page.set_halign(Gtk.Align.CENTER)
        self.scanning_page.set_valign(Gtk.Align.CENTER)
        spinner = Gtk.Spinner()
        spinner.start()
        label = Gtk.Label(label=_("Scanning..."))
        self.scanning_page.append(spinner)
        self.scanning_page.append(label)
        self.stack.add_named(self.scanning_page, "scanning")

        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.content_box.set_margin_start(12)
        self.content_box.set_margin_end(12)
        self.content_box.set_margin_top(12)
        self.content_box.set_margin_bottom(12)

        self.album_header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.album_header.set_margin_start(4)
        self.album_header.set_margin_end(4)
        self.album_header.set_margin_bottom(8)

        self.album_title_label = Gtk.Label()
        self.album_title_label.add_css_class('title-1')
        self.album_title_label.set_halign(Gtk.Align.START)
        self.album_title_label.set_ellipsize(True)

        self.artist_label = Gtk.Label()
        self.artist_label.add_css_class('title-4')
        self.artist_label.set_halign(Gtk.Align.START)
        self.artist_label.set_ellipsize(True)

        self.album_header.append(self.album_title_label)
        self.album_header.append(self.artist_label)
        self.content_box.append(self.album_header)

        self.select_toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.select_toolbar.set_margin_start(4)
        self.select_toolbar.set_margin_end(4)
        self.select_all_button = Gtk.Button(label=_("Select all"))
        self.select_all_button.connect('clicked', self._on_select_all_clicked)
        self.select_none_button = Gtk.Button(label=_("Select none"))
        self.select_none_button.connect('clicked', self._on_select_none_clicked)
        self.select_toolbar.append(self.select_all_button)
        self.select_toolbar.append(self.select_none_button)

        self.rip_button = Gtk.Button(label=_("Rip selected"))
        self.rip_button.add_css_class('suggested-action')
        self.rip_button.connect('clicked', self._on_rip_clicked)
        self.select_toolbar.append(self.rip_button)
        self.content_box.append(self.select_toolbar)

        self.rip_progress_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.rip_progress_box.set_margin_start(4)
        self.rip_progress_box.set_margin_end(4)
        self.rip_progress_box.set_visible(False)

        self.rip_status_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.rip_progress_label = Gtk.Label()
        self.rip_progress_label.set_halign(Gtk.Align.START)
        self.rip_progress_label.set_hexpand(True)
        self.rip_status_row.append(self.rip_progress_label)
        self.abort_button = Gtk.Button(label=_("Cancel"))
        self.abort_button.add_css_class('destructive-action')
        self.abort_button.set_tooltip_text(_("Abort ripping"))
        self.abort_button.connect('clicked', self._on_abort_clicked)
        self.abort_button.set_visible(False)
        self.rip_status_row.append(self.abort_button)
        self.rip_progress_box.append(self.rip_status_row)

        self.track_progress_bar = Gtk.ProgressBar()
        self.track_progress_bar.set_show_text(True)
        self.rip_progress_box.append(self.track_progress_bar)

        self.rip_progress_bar = Gtk.ProgressBar()
        self.rip_progress_bar.set_show_text(True)
        self.rip_progress_box.append(self.rip_progress_bar)
        self.content_box.append(self.rip_progress_box)

        self.track_list = TrackList()
        self.track_list.set_vexpand(True)
        self.content_box.append(self.track_list)

        self.stack.add_named(self.content_box, "loaded")

        self.stack.set_visible_child_name("no-drive")

        self._cd_manager = CDManager(on_event=self._on_cd_event)
        self._cd_manager.start()

        # If launched as the default handler for a specific drive (Exec %f),
        # scan that drive directly instead of waiting for/ relying on the
        # auto-detected event (matters when several drives are present).
        if self._requested_device:
            GLib.idle_add(self._scan_cd, self._requested_device)

    def _build_menu(self) -> Gio.Menu:
        menu = Gio.Menu()
        menu.append(_("Preferences"), "app.preferences")
        menu.append(_("About"), "app.about")
        menu.append(_("Homepage"), "app.homepage")
        return menu

    def _on_eject_clicked(self, button):
        if self._current_cd_info and self._cd_manager is not None:
            self._cd_manager.eject_drive(self._current_cd_info.drive_object_path)

    def _on_select_all_clicked(self, button):
        self.track_list.select_all()

    def _on_select_none_clicked(self, button):
        self.track_list.deselect_all()

    def _on_rip_clicked(self, button):
        if self._cd_manager is None or self._current_cd_info is None:
            return
        tracks = self.track_list.get_selected_tracks()
        if not tracks:
            return
        from src.settings import Settings
        settings = Settings()
        album = AlbumInfo(
            artist=self.artist_label.get_text() or None,
            album_title=self.album_title_label.get_text() or None,
            disc_title=None,
            tracks=tracks,
        )
        self._rip_settings = settings
        device_path = self._current_cd_info.device_path

        scheme = settings.get_naming_scheme()
        extension = settings.get_output_extension()
        conflicting = []
        for t in tracks:
            p = build_destination_path(
                settings.output_dir, scheme, extension,
                album.artist, album.album_title or album.disc_title,
                t.track_number, t.title)
            if p.exists():
                conflicting.append(p)

        if conflicting:
            self._pending_rip = (device_path, settings, album, tracks)
            self._on_rip_conflict(conflicting[0], self._rip_conflict_resolved)
        else:
            self._start_rip_process(
                device_path, settings, album, tracks, ConflictAction.OVERWRITE)

    def _rip_conflict_resolved(self, action):
        pending = getattr(self, '_pending_rip', None)
        self._pending_rip = None
        if pending is None:
            return
        device_path, settings, album, tracks = pending
        if action == ConflictAction.CANCEL:
            self.rip_progress_box.set_visible(False)
            self.abort_button.set_visible(False)
            self.rip_button.set_sensitive(True)
            self.select_all_button.set_sensitive(True)
            self.select_none_button.set_sensitive(True)
            return
        self._start_rip_process(device_path, settings, album, tracks, action)

    def _start_rip_process(self, device_path, settings, album, tracks, conflict_action):
        self.rip_button.set_sensitive(False)
        self.select_all_button.set_sensitive(False)
        self.select_none_button.set_sensitive(False)
        self.rip_progress_box.set_visible(True)
        self.abort_button.set_visible(True)
        self.abort_button.set_sensitive(True)
        self.rip_progress_bar.set_fraction(0.0)
        self.rip_progress_bar.set_text(_("Preparing…"))
        self.track_progress_bar.set_fraction(0.0)
        self.track_progress_bar.set_text(_("Preparing…"))
        self._rip_start_time = None
        self._rip_last_overall = 0
        self._rip_finished = False

        ctx = multiprocessing.get_context('spawn')
        q = ctx.Queue()
        cancel = ctx.Event()
        p = ctx.Process(target=run_rip,
                        args=(q, cancel, device_path, settings, album, tracks, conflict_action))
        p.start()
        self._rip_process = p
        self._rip_queue = q
        self._rip_cancel = cancel
        self._rip_timer = GLib.timeout_add(40, self._poll_rip_queue)

    def _poll_rip_queue(self):
        q = self._rip_queue
        while True:
            try:
                kind, payload = q.get_nowait()
            except queue.Empty:
                break
            self._handle_rip_message(kind, payload)
        if self._rip_finished:
            return False
        if not self._rip_process.is_alive():
            try:
                kind, payload = q.get_nowait()
            except queue.Empty:
                self._finish_rip(_("Ripping process exited unexpectedly"))
                return False
            self._handle_rip_message(kind, payload)
            if self._rip_finished:
                return False
        return True

    def _handle_rip_message(self, kind, payload):
        if kind == 'progress':
            self._on_rip_progress(payload)
        elif kind == 'done':
            self._rip_finished = True
            self._finish_rip(None)
        elif kind == 'error':
            self._rip_finished = True
            self._finish_rip(payload)

    def _finish_rip(self, error_message):
        if self._rip_timer:
            GLib.source_remove(self._rip_timer)
            self._rip_timer = None
        if self._rip_process is not None:
            self._rip_process.join(timeout=3)
            self._rip_process = None
        self._rip_queue = None
        self._rip_cancel = None
        self._rip_finished = False
        self._on_rip_done(error_message, None)

    def _on_rip_progress(self, progress):
        if progress.overall_total > 0:
            overall = progress.overall_current / progress.overall_total
            self.rip_progress_bar.set_fraction(overall)
            self.rip_progress_bar.set_text(
                _("Overall: {percent}%").format(percent=int(overall * 100)))
        if progress.total > 0:
            track = progress.current / progress.total
            self.track_progress_bar.set_fraction(track)
            self.track_progress_bar.set_text(
                _("Track {number}: {percent}%").format(
                    number=progress.track_number, percent=int(track * 100)))

        if progress.finished:
            self.rip_progress_bar.set_fraction(1.0)
            self.track_progress_bar.set_fraction(1.0)
            self.rip_progress_bar.set_text(None)
            self.track_progress_bar.set_text(None)
            self.rip_progress_label.set_text(_("Ripping finished"))
            return False

        label = _("Ripping track {number}…").format(number=progress.track_number)
        if progress.overall_total > 0 and progress.overall_current > 0:
            now = GLib.get_monotonic_time() / 1_000_000.0
            if self._rip_start_time is None:
                self._rip_start_time = now
            elapsed = now - self._rip_start_time
            if elapsed >= 1.0:
                speed = progress.overall_current / elapsed
                remaining = progress.overall_total - progress.overall_current
                eta = remaining / speed if speed > 0 else 0
                label = "{0}   {1}   {2}".format(
                    label, self._format_speed(speed),
                    _("ETA {time}").format(time=self._format_time(eta)))
        self.rip_progress_label.set_text(label)
        return False

    def _on_abort_clicked(self, button):
        if self._rip_cancel is not None:
            self._rip_cancel.set()
        self.abort_button.set_sensitive(False)
        self.rip_progress_label.set_text(_("Cancelling…"))

    @staticmethod
    def _format_speed(bps: float) -> str:
        mb = bps / 1_000_000.0
        xs = bps / 176_400.0
        return _("{} MB/s (×{:.1f})").format(f"{mb:.1f}", xs)

    @staticmethod
    def _format_time(seconds: float) -> str:
        seconds = int(seconds)
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    def _on_rip_conflict(self, file_path: str, resolve):
        dialog = Adw.MessageDialog.new(
            self,
            _("File already exists"),
            _("The file “{path}” already exists. What should be done?").format(path=file_path),
        )
        dialog.add_response("overwrite", _("Overwrite"))
        dialog.add_response("skip", _("Skip"))
        dialog.add_response("cancel", _("Cancel"))
        dialog.set_default_response("skip")
        dialog.set_close_response("cancel")
        dialog.connect('response', self._on_rip_conflict_response, resolve)
        dialog.present()

    def _on_rip_conflict_response(self, dialog, response, resolve):
        from src.cd_ripper import ConflictAction
        mapping = {
            'overwrite': ConflictAction.OVERWRITE,
            'skip': ConflictAction.SKIP,
            'cancel': ConflictAction.CANCEL,
        }
        action = mapping.get(response, ConflictAction.SKIP)
        dialog.close()
        resolve(action)

    def _on_rip_done(self, error_message, unused):
        self.rip_button.set_sensitive(True)
        self.select_all_button.set_sensitive(True)
        self.select_none_button.set_sensitive(True)
        self.abort_button.set_visible(False)
        self.rip_progress_box.set_visible(False)
        if not error_message and getattr(self, '_rip_settings', None) is not None \
                and self._rip_settings.eject_when_done \
                and self._cd_manager is not None and self._current_cd_info is not None:
            self._cd_manager.eject_drive(self._current_cd_info.drive_object_path)
        if error_message:
            dialog = Adw.MessageDialog.new(
                self,
                _("Ripping failed"),
                error_message,
            )
            dialog.add_response("ok", _("OK"))
            dialog.present()
        return False

    def show_preferences(self):
        if self._cd_manager is None:
            return
        from src.settings import Settings
        from src.ui.preferences import PreferencesWindow
        settings = Settings()
        settings.selected_drive_obj_path = self._cd_manager._active_drive_obj_path
        win = PreferencesWindow(settings, self._cd_manager, getattr(self, '_current_album', None))
        win.present()

    def show_about(self):
        from src.ui.about import create_about_dialog
        about = create_about_dialog()
        about.present(self)

    def open_homepage(self):
        from src.ui.about import HOMEPAGE_URL
        try:
            Gtk.show_uri(self, HOMEPAGE_URL, GLib.get_current_time())
        except Exception:
            pass

    def _on_cd_event(self, event: DriveEvent):
        # When launched for a specific drive, ignore events from other drives
        # so the requested disc stays in view (e.g. two drives present).
        dev = event.cd_info.device_path if event.cd_info else None
        if self._requested_device and dev and dev != self._requested_device:
            return

        if event.event_type == 'media_inserted':
            self._current_cd_info = event.cd_info
            self._set_state(WindowState.SCANNING)
            if event.cd_info:
                self._scan_cd(event.cd_info.device_path)
        elif event.event_type == 'drive_detected':
            self._current_cd_info = event.cd_info
            GLib.idle_add(self._set_state, WindowState.NO_MEDIA)
        elif event.event_type == 'media_removed':
            self._current_cd_info = event.cd_info
            self._current_album = None
            if dev == self._requested_device:
                self._requested_device = None
            GLib.idle_add(self._set_state, WindowState.NO_MEDIA)
        elif event.event_type == 'removed':
            self._current_cd_info = None
            self._current_album = None
            GLib.idle_add(self._set_state, WindowState.EMPTY)

    def _set_state(self, state: WindowState):
        self._state = state
        has_drive = state != WindowState.EMPTY
        self.eject_button.set_visible(has_drive)
        if state == WindowState.EMPTY:
            self.stack.set_visible_child_name("no-drive")
        elif state == WindowState.NO_MEDIA:
            self.stack.set_visible_child_name("no-media")
        elif state == WindowState.SCANNING:
            self.stack.set_visible_child_name("scanning")
        elif state == WindowState.LOADED:
            self.stack.set_visible_child_name("loaded")

    def _scan_cd(self, device_path: str):
        self._scanning_device = device_path
        def work():
            try:
                album = self._cd_reader.scan_cd(device_path)
                GLib.idle_add(self._on_scan_done, album)
            except Exception as e:
                GLib.idle_add(self._on_scan_error, str(e))
        thread = Thread(target=work, name="cd-scan")
        thread.daemon = True
        thread.start()

    def _on_scan_done(self, album: AlbumInfo):
        artist = album.artist or ""
        title = album.album_title or album.disc_title or ""
        self._current_album = album
        self.album_title_label.set_text(title)
        self.album_title_label.set_visible(bool(title))
        self.artist_label.set_text(artist)
        self.artist_label.set_visible(bool(artist))
        self.track_list.set_tracks(album.tracks)
        self._set_state(WindowState.LOADED)
        if getattr(self, '_scanning_device', None) == self._requested_device:
            self._requested_device = None

    def _on_scan_error(self, error_message: str):
        self._set_state(WindowState.NO_MEDIA)
        self.status_no_media.set_description(_("Insert an audio CD to scan") + f" ({error_message})")
        if getattr(self, '_scanning_device', None) == self._requested_device:
            self._requested_device = None
