import gi
gi.require_version('Gtk','4.0')
gi.require_version('Adw','1')
from gi.repository import Gtk, Adw

from src.i18n import _
from src.settings import Settings, NAMING_SCHEMES, OUTPUT_FORMATS
from src.cd_manager import CDManager
from src.cd_reader import AlbumInfo
from src.cd_ripper import build_destination_path

PREVIEW_ARTIST = _('Artist')
PREVIEW_ALBUM = _('Album')
PREVIEW_TITLE = _('Title')


class PreviewRow(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.set_margin_start(12)
        self.set_margin_end(12)
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.path_label = Gtk.Label()
        self.path_label.set_wrap(True)
        self.path_label.set_xalign(0.0)
        self.path_label.set_selectable(True)
        self.path_label.add_css_class('monospace')
        self.append(self.path_label)


class PreferencesWindow(Adw.PreferencesWindow):
    def __init__(self, settings: Settings, cd_manager: CDManager,
                 album=None):
        super().__init__()
        self.set_default_size(560, 720)
        self.set_title(_("Preferences"))

        self.settings = settings
        self.cd_manager = cd_manager
        self.album = album
        self._drive_obj_paths = []

        page = Adw.PreferencesPage()
        page.set_title(_("General"))

        drive_group = Adw.PreferencesGroup()
        drive_group.set_title(_("CD Drive"))
        drive_group.set_description(_("Choose which drive to use when several are connected"))

        self.drive_row = Adw.ComboRow()
        self.drive_row.set_title(_("Drive"))
        self.drive_row.set_subtitle(_("Select a CD drive"))
        self.drive_row.connect('notify::selected', self._on_drive_selected)
        drive_group.add(self.drive_row)
        page.add(drive_group)

        output_group = Adw.PreferencesGroup()
        output_group.set_title(_("Ripping"))
        output_group.set_description(_("Where ripped tracks are saved"))

        self.output_dir_row = Adw.ActionRow()
        self.output_dir_row.set_title(_("Output Folder"))
        self.output_dir_row.set_subtitle(self.settings.output_dir)
        choose_button = Gtk.Button(label=_("Choose…"))
        choose_button.set_valign(Gtk.Align.CENTER)
        choose_button.connect('clicked', self._on_choose_clicked)
        self.output_dir_row.add_suffix(choose_button)
        output_group.add(self.output_dir_row)

        self.eject_row = Adw.SwitchRow()
        self.eject_row.set_title(_("Eject disc when ripping finishes"))
        self.eject_row.set_subtitle(_("Open the tray automatically after all tracks are saved"))
        self.eject_row.set_active(self.settings.eject_when_done)
        self.eject_row.connect('notify::active', self._on_eject_toggled)
        output_group.add(self.eject_row)
        page.add(output_group)

        naming_group = Adw.PreferencesGroup()
        naming_group.set_title(_("File Naming"))
        naming_group.set_description(_("Folder and file name pattern"))

        self.preview_row = PreviewRow()
        naming_content = naming_group.get_first_child()
        if naming_content is not None:
            header = naming_content.get_first_child()
            naming_content.append(self.preview_row)
            if header is not None:
                naming_content.reorder_child_after(self.preview_row, header)
        else:
            naming_group.add(self.preview_row)

        self._naming_buttons = []
        first_button = None
        for scheme in NAMING_SCHEMES:
            row = Adw.ActionRow()
            row.set_title(scheme.label)
            radio = Gtk.CheckButton()
            radio.set_valign(Gtk.Align.CENTER)
            if first_button is not None:
                radio.set_group(first_button)
            else:
                first_button = radio
            radio.set_active(self.settings.naming_scheme_id == scheme.scheme_id)
            radio.connect('toggled', self._on_naming_toggled, scheme.scheme_id)
            row.add_prefix(radio)
            row.set_activatable_widget(radio)
            self._naming_buttons.append((scheme.scheme_id, radio))
            naming_group.add(row)
        page.add(naming_group)

        format_group = Adw.PreferencesGroup()
        format_group.set_title(_("Output Format"))
        format_group.set_description(_("File format used when ripping tracks"))

        self._format_buttons = []
        first_button = None
        for format_id, format_label in OUTPUT_FORMATS:
            row = Adw.ActionRow()
            row.set_title(format_label)
            radio = Gtk.CheckButton()
            radio.set_valign(Gtk.Align.CENTER)
            if first_button is not None:
                radio.set_group(first_button)
            else:
                first_button = radio
            radio.set_active(self.settings.output_format == format_id)
            radio.connect('toggled', self._on_format_toggled, format_id)
            row.add_prefix(radio)
            row.set_activatable_widget(radio)
            self._format_buttons.append((format_id, radio))
            format_group.add(row)
        page.add(format_group)

        self.add(page)

        self._populate_drives()
        self._update_preview()

    def _populate_drives(self):
        drives = self.cd_manager.get_drives()
        labels = []
        self._drive_obj_paths = []
        for info in drives:
            label = info.drive_name or (f"{info.vendor} {info.model}".strip() or info.device_path)
            labels.append(label)
            self._drive_obj_paths.append(info.drive_object_path)

        model = Gtk.StringList.new(labels)
        self.drive_row.set_model(model)
        if self.settings.selected_drive_obj_path in self._drive_obj_paths:
            self.drive_row.set_selected(self._drive_obj_paths.index(self.settings.selected_drive_obj_path))
        elif len(drives) > 0:
            self.drive_row.set_selected(0)

    def _preview_track(self):
        if self.album and self.album.tracks:
            track = self.album.tracks[0]
            return (self.album.artist, self.album.album_title or self.album.disc_title,
                    track.track_number, track.title)
        return (PREVIEW_ARTIST, PREVIEW_ALBUM, 1, PREVIEW_TITLE)

    def _update_preview(self):
        scheme = self.settings.get_naming_scheme()
        extension = self.settings.get_output_extension()
        artist, album, track_number, title = self._preview_track()
        try:
            path = build_destination_path(
                self.settings.output_dir, scheme, extension,
                artist, album, track_number, title,
            )
            self.preview_row.path_label.set_text(str(path))
            self.preview_row.path_label.set_visible(True)
        except Exception:
            self.preview_row.path_label.set_visible(False)

    def _on_drive_selected(self, row, param):
        index = row.get_selected()
        if 0 <= index < len(self._drive_obj_paths):
            self.settings.selected_drive_obj_path = self._drive_obj_paths[index]
            self.settings.save()
            self.cd_manager.set_active_drive(self._drive_obj_paths[index])

    def _on_naming_toggled(self, button, scheme_id):
        if button.get_active():
            self.settings.naming_scheme_id = scheme_id
            self.settings.save()
            self._update_preview()

    def _on_format_toggled(self, button, format_id):
        if button.get_active():
            self.settings.output_format = format_id
            self.settings.save()
            self._update_preview()

    def _on_eject_toggled(self, row, param):
        self.settings.eject_when_done = row.get_active()
        self.settings.save()

    def _on_choose_clicked(self, button):
        dialog = Gtk.FileDialog()
        dialog.set_title(_("Choose Output Folder"))
        dialog.select_folder(self, None, self._on_folder_selected, None)

    def _on_folder_selected(self, dialog, result, user_data):
        try:
            folder = dialog.select_folder_finish(result)
        except Exception:
            return
        self.settings.output_dir = folder.get_path()
        self.settings.save()
        self.output_dir_row.set_subtitle(self.settings.output_dir)
        self._update_preview()