import signal
import sys
import logging
import gi
gi.require_version('Gtk','4.0')
gi.require_version('Adw','1')
from gi.repository import Gtk, Gio, Adw, GLib

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
_logger = logging.getLogger('dedisc')
_logger.setLevel(logging.INFO)

from src.i18n import _setup_translations
_setup_translations()

APP_ID = 'pl.septicwolf818.Dedisc'


class RipperApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self._logger = _logger
        self.connect('open', self._on_open)
        self.connect('shutdown', self._on_shutdown)
        self._install_signal_handlers()

    def _install_signal_handlers(self):
        # Ensure the rip subprocess is reaped if the app process is killed by
        # a terminal close (SIGHUP) or Ctrl+C (SIGINT), so the disc does not
        # keep spinning in an orphaned child.
        for sig in (signal.SIGINT, signal.SIGHUP):
            try:
                signal.signal(sig, self._on_signal)
            except (ValueError, OSError, AttributeError):
                pass

    def _on_signal(self, signum, frame):
        win = self.get_active_window()
        if win is not None and hasattr(win, '_cancel_rip_process'):
            win._cancel_rip_process()
        self.quit()

    def _on_shutdown(self, *args):
        win = self.get_active_window()
        if win is not None and hasattr(win, '_cancel_rip_process'):
            win._cancel_rip_process()

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
        self._logger.info("do_activate _requested_device=%r", device)
        win = RipperWindow(application=self, device=device)
        win.present()

    def _on_open(self, *args):
        # Launched as the default handler for an audio CD (Exec %f passes a
        # device/file URI). With PyGObject, args[1] is the list of GFile
        # objects for the opened location(s). CDManager auto-detects the
        # inserted disc via UDisks2, so we just remember the requested host
        # name and activate the window.
        self._logger.debug('_on_open raw args = %s', (args,))
        parsed_host = None

        if len(args) > 1:
            files = args[1]
            try:
                for f in files:
                    uri = f.get_uri() if hasattr(f, 'get_uri') else str(f)
                    path = f.get_path() if hasattr(f, 'get_path') else None
                    self._logger.debug('  GFile uri=%r get_path=%r', uri, path)

                    if uri.startswith('cdda://'):
                        # Nautilus/gvfs passes cdda://host/ (e.g. cdda://sr1/)
                        host_part = uri.replace('cdda://', '').rstrip('/')
                        self._logger.info('_on_open parsed cdda host=%r', host_part)
                        parsed_host = host_part
                    elif path and 'gvfs/cdda' in path:
                        # Fallback for the gvfs mount-point path (host=XXXX)
                        param = path.split('host=')[-1] if 'host=' in path else ''
                        if param:
                            self._logger.info('_on_open parsed gvfs host=%r', param)
                            parsed_host = param
                    elif path:
                        candidate = path.lstrip('/')
                        # e.g. /dev/sr0 → sr0 (but avoid things like 'sda')
                        if len(candidate) == 3 and candidate.startswith(('/sda', '/sr')):
                            self._logger.info('_on_open parsed plain device=%r', candidate)
                            parsed_host = candidate
            except Exception as e:
                self._logger.exception('_on_open extraction error')

        self._requested_device = parsed_host or getattr(self, '_requested_device', None)
        self._logger.info('_on_open resolved _requested_device=%r', self._requested_device)
        self.activate()


def main():
    sys.path.insert(0, '.')
    app = RipperApp()
    return app.run(sys.argv)


if __name__ == '__main__':
    main()
