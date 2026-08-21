#!/usr/bin/env python3
"""Sync desktop-entry translatable strings into the gettext catalogs.

Reads data/dedisc.desktop.in, extracts the values of the translatable
keys and makes sure every po/*.po (and po/dedisc.pot) contains a
matching context-less msgid entry - the form "msgfmt --desktop" looks
up at install time.  Missing entries are appended (empty translation,
ready for translators).  Entries still referencing removed desktop
strings are reported as obsolete.

Also regenerates po/LINGUAS from the .po files present (required by
"msgfmt --desktop"; a missing or stale LINGUAS silently skips merging).

Stdlib only; idempotent; safe to run on every build.
"""

import argparse
import sys
from pathlib import Path

# Must match the -k allow-list used with "msgfmt --desktop" in the Makefile.
TRANSLATABLE_KEYS = ("GenericName", "Comment")

DESKTOP_REF = "#: data/dedisc.desktop.in"
HEADER_COMMENT = (
    "#. Desktop entry string kept in sync by tools/sync_desktop_po.py;"
    " do not remove."
)


def po_escape(value):
    out = []
    for ch in value:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        else:
            out.append(ch)
    return "".join(out)


def po_unescape(value):
    out = []
    i = 0
    while i < len(value):
        ch = value[i]
        if ch == "\\" and i + 1 < len(value):
            nxt = value[i + 1]
            out.append({"n": "\n", "t": "\t", '"': '"', "\\": "\\"}.get(nxt, nxt))
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def read_desktop_values(desktop_path):
    values = {}
    for line in desktop_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("[") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() in TRANSLATABLE_KEYS:
            values[key.strip()] = value
    return [values[k] for k in TRANSLATABLE_KEYS if k in values]


def parse_po_chunks(text):
    """Split a .po/.pot file into entry chunks (separated by blank lines).

    Returns a list of dicts: {msgid, ctxt, comments} where msgid is the
    fully unescaped message id and ctxt is None for context-less entries.
    """
    chunks = []
    current = []

    def flush():
        if not current:
            return
        entry = {"msgid": None, "ctxt": False, "comments": []}
        phase = None
        parts = {"msgid": [], "msgctxt": []}
        for line in current:
            stripped = line.strip()
            if stripped.startswith("#"):
                entry["comments"].append(stripped)
                continue
            if stripped.startswith(("msgctxt ", "msgid ", "msgstr ")):
                keyword, _, rest = stripped.partition(" ")
                if keyword == "msgstr":
                    phase = None
                    continue
                phase = keyword
                parts[phase].append(rest.strip())
            elif stripped.startswith('"') and phase:
                parts[phase].append(stripped)
        if parts["msgctxt"]:
            entry["ctxt"] = True
        if parts["msgid"]:
            joined = "".join(p.strip('"') for p in parts["msgid"])
            entry["msgid"] = po_unescape(joined)
        chunks.append(entry)
        current.clear()

    def is_entry_start(stripped):
        return stripped.startswith("#") or stripped.startswith(("msgctxt ", "msgid ", "msgstr "))

    for line in text.splitlines():
        if not line.strip():
            flush()
            continue
        stripped = line.strip()
        # Entries may be separated by a blank line OR follow each other
        # directly once the previous entry's msgstr is complete.
        if current and is_entry_start(stripped) and any(
            l.strip().startswith("msgstr ") for l in current
        ):
            flush()
        current.append(line)
    flush()
    return chunks


def sync_catalog(path, values, check_only):
    text = path.read_text(encoding="utf-8")
    chunks = parse_po_chunks(text)
    plain_ids = {c["msgid"] for c in chunks if c["msgid"] is not None and not c["ctxt"]}

    missing = [v for v in values if v not in plain_ids]
    stale = [
        c["msgid"]
        for c in chunks
        if DESKTOP_REF in c["comments"] and c["msgid"] not in values and c["msgid"]
    ]
    for msgid in stale:
        print(
            f"{path}: WARNING obsolete desktop entry dropped from template: {msgid!r}",
            file=sys.stderr,
        )

    if not missing:
        return False

    if check_only:
        return True

    block = "\n\n".join(
        f"{HEADER_COMMENT}\n{DESKTOP_REF}\n"
        f'msgid "{po_escape(v)}"\nmsgstr ""'
        for v in missing
    )
    text = text.rstrip("\n") + "\n\n" + block + "\n"
    path.write_text(text, encoding="utf-8")
    langs = ", ".join(missing)
    print(f"{path}: added {len(missing)} entr{'y' if len(missing) == 1 else 'ies'} ({langs})")
    return True


def sync_linguas(po_dir, check_only):
    linguas = po_dir / "LINGUAS"
    languages = sorted(p.stem for p in po_dir.glob("*.po"))
    wanted = "# Regenerated by tools/sync_desktop_po.py.\n" + "\n".join(languages) + "\n"
    current = linguas.read_text(encoding="utf-8") if linguas.exists() else ""
    effective = [
        ln for ln in current.splitlines() if ln.strip() and not ln.strip().startswith("#")
    ]
    if effective == languages:
        return False
    if check_only:
        return True
    linguas.write_text(wanted, encoding="utf-8")
    print(f"{linguas}: regenerated ({', '.join(languages)})")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--desktop", type=Path, default=Path("data/dedisc.desktop.in"))
    parser.add_argument("--po-dir", type=Path, default=Path("po"))
    parser.add_argument(
        "--check",
        action="store_true",
        help="report drift without modifying files; exit 1 when out of sync",
    )
    args = parser.parse_args()

    values = read_desktop_values(args.desktop)
    if not values:
        print(f"No translatable keys {TRANSLATABLE_KEYS} found in {args.desktop}")
        return 1

    changed = sync_linguas(args.po_dir, args.check)
    for po_file in sorted(args.po_dir.glob("*.po")):
        changed |= sync_catalog(po_file, values, args.check)
    pot = args.po_dir / "dedisc.pot"
    if pot.exists():
        changed |= sync_catalog(pot, values, args.check)

    if args.check and changed:
        print("Out of sync - run tools/sync_desktop_po.py to fix.")
        return 1
    if not changed:
        print("Desktop translations already in sync.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
