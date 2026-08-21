import gettext
import subprocess
from pathlib import Path

APP_ID = 'pl.septicwolf818.Dedisc'
DOMAIN = 'dedisc'

_LOCALE_DIRS = [
    Path(__file__).resolve().parent.parent / 'locale',
    Path.home() / '.local' / 'share' / 'locale',
    Path('/usr/share/locale'),
]

def _project_po_dir() -> Path:
    return Path(__file__).resolve().parent.parent / 'po'

def _compile_dev_translations():
    """Compile po/pl.po -> po/pl/LC_MESSAGES/dedisc.mo for source runs."""
    po_dir = _project_po_dir()
    po_file = po_dir / 'pl.po'
    if not po_file.is_file():
        return None
    mo_dir = po_dir / 'pl' / 'LC_MESSAGES'
    mo_file = mo_dir / f'{DOMAIN}.mo'
    if mo_file.is_file() and mo_file.stat().st_mtime >= po_file.stat().st_mtime:
        return po_dir
    mo_dir.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ['msgfmt', '--check', '-o', str(mo_file), str(po_file)],
            check=True, capture_output=True,
        )
        return po_dir
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

def _setup_translations():
    """Install translations so all code uses _('string') uniformly."""
    # Prefer the source-tree po/ (compiled on the fly) so a fresh checkout or
    # `make run` always uses up-to-date translations and never a stale system
    # install at /usr/share/locale.
    locale_dir = _compile_dev_translations()

    if locale_dir is None:
        for d in _LOCALE_DIRS:
            test = d / 'pl' / 'LC_MESSAGES' / f'{DOMAIN}.mo'
            if test.is_file():
                locale_dir = str(d)
                break

    if locale_dir is None:
        locale_dir = str(Path(__file__).resolve().parent.parent / 'locale')

    gettext.bindtextdomain(DOMAIN, locale_dir)
    gettext.textdomain(DOMAIN)
    return gettext.gettext


def _(msgid: str) -> str:
    """Shortcut for gettext."""
    return gettext.dgettext(DOMAIN, msgid)


def n_(singular: str, plural: str, n: int) -> str:
    """Plural-form support (needed by gettext.ngettext)."""
    return gettext.ngettext(msgid1=singular, msgid2=plural, n=n)