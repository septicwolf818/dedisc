import sys
import gi
gi.require_version('Gtk','4.0')
gi.require_version('Adw','1')
from gi.repository import Gtk, Gio, Adw, GLib

from src.i18n import _setup_translations
_setup_translations()

APP_ID = 'pl.septicwolf818.Dedisc'

class RipperApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self.connect('open', self._on_open)

    def do_startup(self):
        Adw.Application.do_startup(self)
        self._setup_actions()

    def _setup_actions(self):
        self._preferences_action = Gio.SimpleAction.new('preferences', None)
        self._preferences_action.connect('activate', self._on_preferences)
        self.add_action(self._preferences_action)

        self._about_action = Gio.SimpleAction.new('about', None)
        self._about_action.connect('activate', self._on_about)
        self.add_action(self._about_action)

        self._homepage_action = Gio.SimpleAction.new('homepage', None)
        self._homepage_action.connect('activate', self._on_homepage)
        self.add_action(self._homepage_action)

        self.set_accels_for_action('app.preferences', ['<Control>comma'])

    def _on_preferences(self, action, param):
        win = self.get_active_window()
        if win is None:
            return
        win.show_preferences()

    def _on_about(self, action, param):
        win = self.get_active_window()
        if win is None:
            return
        win.show_about()

    def _on_homepage(self, action, param):
        win = self.get_active_window()
        if win is None:
            return
        win.open_homepage()

    def do_activate(self):
        from src.window import RipperWindow
        device = getattr(self, '_requested_device', None)
        win = RipperWindow(application=self, device=device)
        win.present()

    def _on_open(self, *args):
        # Launched as the default handler for an audio CD (Exec %f passes a
        # device/file URI). With PyGObject, args[1] is the list of GFile
        # objects for the opened location(s). CDManager auto-detects the
        # inserted disc via UDisks2, so we just remember the requested device
        # and activate the window.
        paths = []
        if len(args) > 1:
            files = args[1]
            try:
                for f in files:
                    paths.append(f.get_path())
            except Exception:
                pass
        if paths:
            self._requested_device = paths[0]
        self.activate()

def main():
    sys.path.insert(0, '.')
    app = RipperApp()
    return app.run(sys.argv)

if __name__ == '__main__':
    main()