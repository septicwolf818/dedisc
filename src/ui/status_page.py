import gi
gi.require_version('Gtk','4.0')
gi.require_version('Adw','1')
from gi.repository import Adw
from src.i18n import _

def create_no_drive_status_page() -> Adw.StatusPage:
    page = Adw.StatusPage()
    page.set_icon_name('media-optical-symbolic')
    page.set_title(_('No drive detected'))
    page.set_description(_('Check that a CD drive is connected'))
    return page

def create_no_media_status_page() -> Adw.StatusPage:
    page = Adw.StatusPage()
    page.set_icon_name('media-optical-symbolic')
    page.set_title(_('No CD inserted'))
    page.set_description(_('Insert an audio CD to scan'))
    return page
