# Contributing

Issues and pull requests are welcome.

## Code style

- UI strings must be wrapped in `_()` for translation.
- Always marshal UI updates via `GLib.idle_add()`. Never touch GTK from background threads.
- Keep the app offline. No network calls.

## Reporting issues

Describe your distro, GTK/Adwaita versions, CD drive model, and steps to reproduce.