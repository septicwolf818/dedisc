import gi
import logging
gi.require_version('Gtk','4.0')
gi.require_version('Adw','1')
from gi.repository import Gtk, Gio, GObject
from src.i18n import _
from src.cd_reader import TrackInfo, CDReader

logger = logging.getLogger(__name__)


class TrackItem(GObject.Object):
    __gtype_name__ = 'RipperTrackItem'

    selected = GObject.Property(type=bool, default=True)
    number = GObject.Property(type=int, default=0)
    title = GObject.Property(type=str, default='')
    duration = GObject.Property(type=str, default='')

    def __init__(self, track: TrackInfo):
        super().__init__()
        self.track_info = track
        self.number = track.track_number
        self.title = track.title or "…"
        self.duration = CDReader.frames_to_seconds(track.duration_frames)


class TrackList(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__()
        self.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.set_min_content_height(200)

        self.model = Gio.ListStore(item_type=TrackItem)
        self.selection = Gtk.NoSelection(model=self.model)

        self.columns = Gtk.ColumnView(model=self.selection)
        self.columns.set_show_row_separators(True)

        self._add_checkbox_column()
        self._add_number_column()
        self._add_title_column()
        self._add_duration_column()

        self.set_child(self.columns)

    def _make_label_factory(self, get_text, halign: Gtk.Align = Gtk.Align.START):
        factory = Gtk.SignalListItemFactory()

        def on_setup(factory, list_item):
            label = Gtk.Label(halign=halign)
            label.set_margin_start(12)
            label.set_margin_end(12)
            label.set_margin_top(6)
            label.set_margin_bottom(6)
            list_item.set_child(label)

        def on_bind(factory, list_item):
            item = list_item.get_item()
            label = list_item.get_child()
            label.set_text(get_text(item))

        factory.connect('setup', on_setup)
        factory.connect('bind', on_bind)
        return factory

    def _add_checkbox_column(self):
        factory = Gtk.SignalListItemFactory()

        def on_setup(factory, list_item):
            check = Gtk.CheckButton()
            check.set_margin_start(12)
            check.set_margin_end(12)
            check.set_margin_top(6)
            check.set_margin_bottom(6)
            list_item.set_child(check)

        def on_bind(factory, list_item):
            item = list_item.get_item()
            check = list_item.get_child()
            check.set_active(bool(item.selected))
            check.bind_property(
                'active', item, 'selected',
                GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE,
            )

        factory.connect('setup', on_setup)
        factory.connect('bind', on_bind)
        column = Gtk.ColumnViewColumn(title=_("Select"))
        column.set_factory(factory)
        column.set_fixed_width(60)
        self.columns.append_column(column)

    def _add_number_column(self):
        factory = self._make_label_factory(lambda item: str(item.number))
        column = Gtk.ColumnViewColumn(title=_("Track"))
        column.set_factory(factory)
        column.set_fixed_width(60)
        self.columns.append_column(column)

    def _add_title_column(self):
        factory = self._make_label_factory(lambda item: item.title)
        column = Gtk.ColumnViewColumn(title=_("Title"))
        column.set_factory(factory)
        column.set_expand(True)
        self.columns.append_column(column)

    def _add_duration_column(self):
        factory = self._make_label_factory(lambda item: item.duration, halign=Gtk.Align.END)
        column = Gtk.ColumnViewColumn(title=_("Duration"))
        column.set_factory(factory)
        column.set_fixed_width(90)
        self.columns.append_column(column)

    def set_tracks(self, tracks):
        logger.info("TrackList.set_tracks count=%d", len(tracks))
        self.model.splice(0, len(self.model), [TrackItem(t) for t in tracks])

    def get_selected_tracks(self):
        logger.info("TrackList.get_selected_tracks")
        result = []
        for i in range(len(self.model)):
            item = self.model.get_item(i)
            if item.selected:
                result.append(item.track_info)
        return result

    def select_all(self):
        logger.info("TrackList.select_all count=%d", len(self.model))
        for i in range(len(self.model)):
            self.model.get_item(i).selected = True

    def deselect_all(self):
        for i in range(len(self.model)):
            self.model.get_item(i).selected = False