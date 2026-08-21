import logging
from dataclasses import dataclass, field
from typing import Callable, Optional
import gi
gi.require_version('Gtk','4.0')
gi.require_version('Adw','1')
from gi.repository import Gio, GLib

from src.i18n import _

logger = logging.getLogger(__name__)

@dataclass
class CDInfo:
    drive_name: str
    vendor: str
    model: str
    device_path: str
    has_media: bool
    drive_object_path: str = ''
    media_types: list[str] = field(default_factory=list)

@dataclass
class DriveEvent:
    event_type: str
    cd_info: Optional[CDInfo] = None

class CDManager:
    _UDISKS2_SERVICE = 'org.freedesktop.UDisks2'
    _UDISKS2_OBJECT_PATH = '/org/freedesktop/UDisks2'
    _OBJECT_MANAGER_IFACE = 'org.freedesktop.DBus.ObjectManager'
    _PROPERTIES_IFACE = 'org.freedesktop.DBus.Properties'
    _DRIVE_IFACE = 'org.freedesktop.UDisks2.Drive'
    _BLOCK_IFACE = 'org.freedesktop.UDisks2.Block'

    def __init__(self, on_event: Callable[[DriveEvent], None]):
        self._on_event = on_event
        self._proxy: Optional[Gio.DBusProxy] = None
        self._drive_proxies: dict[str, Gio.DBusProxy] = {}
        self._connected_drives: dict[str, CDInfo] = {}
        self._active_drive_obj_path: str = ''

    def start(self):
        proxy = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SYSTEM,
            Gio.DBusProxyFlags.NONE,
            None,
            self._UDISKS2_SERVICE,
            self._UDISKS2_OBJECT_PATH,
            self._OBJECT_MANAGER_IFACE,
            None,
        )
        self._proxy = proxy
        proxy.connect('g-signal', self._on_dbus_signal)

        result = proxy.call_sync(
            'GetManagedObjects', None, Gio.DBusCallFlags.NONE, -1, None
        )
        unpacked = result.unpack()
        if isinstance(unpacked, tuple) and len(unpacked) == 1:
            unpacked = unpacked[0]
        if isinstance(unpacked, dict):
            items = unpacked.items()
        else:
            items = unpacked
        for obj_path, interfaces in items:
            self._process_interfaces(obj_path, interfaces)

    def stop(self):
        if self._proxy:
            self._proxy = None
            self._connected_drives.clear()

    def get_drives(self) -> list[CDInfo]:
        return list(self._connected_drives.values())

    def set_active_drive(self, drive_obj_path: str):
        self._active_drive_obj_path = drive_obj_path
        cd_info = self._connected_drives.get(drive_obj_path)
        if cd_info is None:
            return
        if cd_info.has_media:
            GLib.idle_add(self._on_event, DriveEvent('media_inserted', cd_info))
        else:
            GLib.idle_add(self._on_event, DriveEvent('drive_detected', cd_info))

    def _process_interfaces(self, obj_path: str, interfaces: dict):
        drive_props = interfaces.get(self._DRIVE_IFACE)
        if not drive_props or not self._is_optical(drive_props):
            return

        name = drive_props.get('Name') or ''
        if not name:
            vendor = drive_props.get('Vendor') or ''
            model = drive_props.get('Model') or ''
            name = ' '.join(part for part in (vendor, model) if part).strip() or 'Unknown'
        vendor = drive_props.get('Vendor', '')
        model = drive_props.get('Model', '')
        has_media = bool(drive_props.get('MediaAvailable', False))
        media_types = list(drive_props.get('Media', []))

        block_devices = self._find_block_device_for_drive(obj_path)
        device_path = block_devices[0] if block_devices else ''

        cd_info = CDInfo(
            drive_name=name,
            vendor=vendor,
            model=model,
            device_path=device_path,
            has_media=has_media,
            drive_object_path=obj_path,
            media_types=media_types,
        )

        self._connected_drives[obj_path] = cd_info
        self._watch_drive_properties(obj_path)

        if not self._active_drive_obj_path:
            self._active_drive_obj_path = obj_path

        if self._active_drive_obj_path != obj_path:
            return

        if has_media:
            GLib.idle_add(self._on_event, DriveEvent('media_inserted', cd_info))
        else:
            GLib.idle_add(self._on_event, DriveEvent('drive_detected', cd_info))

    def _watch_drive_properties(self, drive_obj_path: str):
        if drive_obj_path in self._drive_proxies:
            return
        proxy = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SYSTEM,
            Gio.DBusProxyFlags.NONE,
            None,
            self._UDISKS2_SERVICE,
            drive_obj_path,
            self._PROPERTIES_IFACE,
            None,
        )
        proxy.connect('g-signal', self._on_properties_changed)
        self._drive_proxies[drive_obj_path] = proxy

    def _on_properties_changed(self, proxy, sender_name, signal_name, parameters):
        if signal_name != 'PropertiesChanged':
            return
        iface_name, changed_props, _invalidated = parameters.unpack()
        if iface_name != self._DRIVE_IFACE:
            return

        drive_obj_path = proxy.get_object_path()
        cd_info = self._connected_drives.get(drive_obj_path)
        if cd_info is None:
            return

        has_media = changed_props.get('MediaAvailable', cd_info.has_media)
        cd_info.has_media = bool(has_media)

        if 'Media' in changed_props:
            cd_info.media_types = list(changed_props['Media'])

        block_devices = self._find_block_device_for_drive(drive_obj_path)
        cd_info.device_path = block_devices[0] if block_devices else ''

        if self._active_drive_obj_path != drive_obj_path:
            return

        if cd_info.has_media:
            GLib.idle_add(self._on_event, DriveEvent('media_inserted', cd_info))
        else:
            GLib.idle_add(self._on_event, DriveEvent('media_removed', cd_info))

    @staticmethod
    def _is_optical(drive_props: dict) -> bool:
        if drive_props.get('Optical', False):
            return True
        compat = drive_props.get('MediaCompatibility', []) or []
        return any(str(t).startswith('optical_') for t in compat)

    def _find_block_device_for_drive(self, drive_obj_path: str) -> list[str]:
        if not self._proxy:
            return []
        result = self._proxy.call_sync(
            'GetManagedObjects', None, Gio.DBusCallFlags.NONE, -1, None
        )
        devices = []
        unpacked = result.unpack()
        if isinstance(unpacked, tuple) and len(unpacked) == 1:
            unpacked = unpacked[0]
        for obj_path, interfaces in unpacked.items():
            block_props = interfaces.get(self._BLOCK_IFACE)
            if not block_props:
                continue
            drive_ref = block_props.get('Drive', '')
            if drive_ref == drive_obj_path:
                device_list = block_props.get('PreferredDevice', block_props.get('Device', []))
                devices.append(self._decode_device_bytes(device_list))
        return devices

    @staticmethod
    def _decode_device_bytes(byte_list) -> str:
        if isinstance(byte_list, str):
            return byte_list
        raw = bytes(byte_list)
        return raw.rstrip(b'\x00').decode(errors='replace')

    def _on_dbus_signal(self, proxy, sender_name, signal_name, parameters):
        if signal_name == 'InterfacesAdded':
            obj_path, interfaces = parameters.unpack()
            self._process_interfaces(obj_path, interfaces)
        elif signal_name == 'InterfacesRemoved':
            obj_path, iface_names = parameters.unpack()
            if obj_path in self._connected_drives:
                del self._connected_drives[obj_path]
                self._drive_proxies.pop(obj_path, None)
                was_active = self._active_drive_obj_path == obj_path
                if was_active:
                    if self._connected_drives:
                        self._active_drive_obj_path = next(iter(self._connected_drives))
                    else:
                        self._active_drive_obj_path = ''
                if was_active or not self._connected_drives:
                    GLib.idle_add(self._on_event, DriveEvent('removed', None))

    def eject_drive(self, drive_obj_path: str) -> bool:
        if not drive_obj_path:
            return False
        try:
            proxy = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SYSTEM,
                Gio.DBusProxyFlags.NONE,
                None,
                self._UDISKS2_SERVICE,
                drive_obj_path,
                self._DRIVE_IFACE,
                None,
            )
            options = GLib.Variant('(a{sv})', ({},))
            proxy.call_sync(
                'Eject', options, Gio.DBusCallFlags.NONE, -1, None
            )
            logger.info(_("Ejected drive %s"), drive_obj_path)
            return True
        except Exception as e:
            logger.error(_("Eject failed for %s: %s"), drive_obj_path, e)
            return False
