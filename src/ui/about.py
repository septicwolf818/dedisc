import gi
gi.require_version('Gtk','4.0')
gi.require_version('Adw','1')
from gi.repository import Adw, Gtk

from src.i18n import _
from src.settings import APP_ID

VERSION = '0.1.0'
HOMEPAGE_URL = 'https://github.com/septicwolf818/dedisc'
DEVELOPER = 'Rafał Widło'
DEVELOPER_URL = 'https://septicwolf818.pl'

def create_about_dialog() -> Adw.AboutDialog:
    about = Adw.AboutDialog()
    about.set_application_name(_("Dedisc"))
    about.set_version(VERSION)
    about.set_developer_name(DEVELOPER)
    about.set_website(HOMEPAGE_URL)
    about.set_issue_url(HOMEPAGE_URL + '/issues')
    about.set_copyright("© 2026 " + DEVELOPER)
    about.set_license_type(Gtk.License.MIT_X11)
    about.set_comments(_("An offline CD scanner and ripper for GNOME"))
    about.add_link(_("Website"), DEVELOPER_URL)
    return about