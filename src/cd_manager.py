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

    def __init__(self, on_event: Callable[[DriveEvent], None], preferred_host: Optional[str] = None):
        self._on_event = on_event
        self._proxy: Optional[Gio.DBusProxy] = None
        self._drive_proxies: dict[str, Gio.DBusProxy] = {}
        self._connected_drives: dict[str, CDInfo] = {}
        self._active_drive_obj_path: str = ''
        self._preferred_host = preferred_host

    def start(self):
        logger.info("CDManager start preferred_host=%s", self._preferred_host)
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
        logger.info("CDManager start complete, active_drive=%s connected=%d", self._active_drive_obj_path, len(self._connected_drives))

    def stop(self):
        logger.info("CDManager stop")
        if self._proxy:
            self._proxy = None
            self._connected_drives.clear()
        logger.info("CDManager stopped")

    def get_drives(self) -> list[CDInfo]:
        logger.info("CDManager get_drives count=%d", len(self._connected_drives))
        return list(self._connected_drives.values())

    def set_active_drive(self, drive_obj_path: str):
        logger.info("CDManager set_active_drive %s", drive_obj_path)
        self._active_drive_obj_path = drive_obj_path
        cd_info = self._connected_drives.get(drive_obj_path)
        if cd_info is None:
            logger.info("CDManager set_active_drive no cd_info for %s", drive_obj_path)
            return
        logger.info("CDManager set_active_drive active drive has_media=%s", cd_info.has_media)
        if cd_info.has_media:
            GLib.idle_add(self._on_event, DriveEvent('media_inserted', cd_info))
        else:
            GLib.idle_add(self._on_event, DriveEvent('drive_detected', cd_info))

    def _process_interfaces(self, obj_path: str, interfaces: dict):
        logger.info("CDManager _process_interfaces obj_path=%s", obj_path)
        drive_props = interfaces.get(self._DRIVE_IFACE)
        if not drive_props or not self._is_optical(drive_props):
            logger.info("CDManager _process_interfaces not optical or no drive props")
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
        logger.info("CDManager _process_interfaces obj_path=%s device_path=%s preferred_host=%s", obj_path, device_path, self._preferred_host)

        # Select active drive with preferred host matching
        if not self._active_drive_obj_path:
            # First drive seen
            logger.info("CDManager selecting first drive as active: %s", obj_path)
            self._active_drive_obj_path = obj_path
        else:
            # If preferred host is set, prefer matching drive
            if self._preferred_host:
                current_active = self._connected_drives.get(self._active_drive_obj_path)
                # Check if current active matches preferred host
                matches_current = current_active and self._preferred_host in (current_active.device_path or '')
                # Check if new drive matches preferred host
                matches_new = self._preferred_host in (device_path or '')
                logger.info("CDManager host match check current_active=%s matches_current=%s matches_new=%s", 
                            self._active_drive_obj_path, matches_current, matches_new)
                if matches_new and not matches_current:
                    logger.info("CDManager switching active drive to preferred host match: %s", obj_path)
                    self._active_drive_obj_path = obj_path
                # If both match or neither, keep current

        if self._active_drive_obj_path != obj_path:
            logger.info("CDManager skipping drive %s, active is %s", obj_path, self._active_drive_obj_path)
            return

        if has_media:
            GLib.idle_add(self._on_event, DriveEvent('media_inserted', cd_info))
        else:
            GLib.idle_add(self._on_event, DriveEvent('drive_detected', cd_info))

    def _watch_drive_properties(self, drive_obj_path: str):
        logger.info("CDManager _watch_drive_properties %s", drive_obj_path)
        if drive_obj_path in self._drive_proxies:
            logger.info("CDManager _watch_drive_properties already watching")
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
        logger.info("CDManager _on_properties_changed signal_name=%s", signal_name)
        if signal_name != 'PropertiesChanged':
            logger.debug("CDManager _on_properties_changed ignoring signal %s", signal_name)
            return
        iface_name, changed_props, _invalidated = parameters.unpack()
        if iface_name != self._DRIVE_IFACE:
            logger.debug("CDManager _on_properties_changed ignoring iface %s", iface_name)
            return

        drive_obj_path = proxy.get_object_path()
        cd_info = self._connected_drives.get(drive_obj_path)
        if cd_info is None:
            logger.info("CDManager _on_properties_changed no cd_info for %s", drive_obj_path)
            return

        has_media = changed_props.get('MediaAvailable', cd_info.has_media)
        cd_info.has_media = bool(has_media)

        if 'Media' in changed_props:
            cd_info.media_types = list(changed_props['Media'])

        block_devices = self._find_block_device_for_drive(drive_obj_path)
        cd_info.device_path = block_devices[0] if block_devices else ''
        logger.info("CDManager _on_properties_changed drive=%s device_path=%s has_media=%s", drive_obj_path, cd_info.device_path, cd_info.has_media)

        if self._active_drive_obj_path != drive_obj_path:
            logger.info("CDManager _on_properties_changed not active drive, skipping")
            return

        logger.info("CDManager _on_properties_changed active drive media change, has_media=%s", cd_info.has_media)
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
        logger.info("CDManager _find_block_device_for_drive %s", drive_obj_path)
        if not self._proxy:
            logger.info("CDManager _find_block_device_for_drive no proxy")
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
                dev = self._decode_device_bytes(device_list)
                logger.info("CDManager _find_block_device_for_drive found device %s for %s", dev, drive_obj_path)
                devices.append(dev)
        logger.info("CDManager _find_block_device_for_drive done, found %d devices", len(devices))
        return devices

    @staticmethod
    def _decode_device_bytes(byte_list) -> str:
        if isinstance(byte_list, str):
            return byte_list
        raw = bytes(byte_list)
        return raw.rstrip(b'\x00').decode(errors='replace')

    def _on_dbus_signal(self, proxy, sender_name, signal_name, parameters):
        logger.info("CDManager _on_dbus_signal signal_name=%s", signal_name)
        if signal_name == 'InterfacesAdded':
            obj_path, interfaces = parameters.unpack()
            logger.info("CDManager _on_dbus_signal InterfacesAdded obj_path=%s", obj_path)
            self._process_interfaces(obj_path, interfaces)
        elif signal_name == 'InterfacesRemoved':
            obj_path, iface_names = parameters.unpack()
            logger.info("CDManager _on_dbus_signal InterfacesRemoved obj_path=%s", obj_path)
            if obj_path in self._connected_drives:
                del self._connected_drives[obj_path]
                self._drive_proxies.pop(obj_path, None)
                was_active = self._active_drive_obj_path == obj_path
                logger.info("CDManager drive removed obj_path=%s was_active=%s", obj_path, was_active)
                if was_active:
                    if self._connected_drives:
                        # Try to preserve preferred host matching
                        if self._preferred_host:
                            # Find drive matching preferred host
                            matching = None
                            for path, info in self._connected_drives.items():
                                if self._preferred_host in (info.device_path or ''):
                                    matching = path
                                    break
                            self._active_drive_obj_path = matching or next(iter(self._connected_drives))
                            logger.info("CDManager new active drive after removal: %s", self._active_drive_obj_path)
                        else:
                            self._active_drive_obj_path = next(iter(self._connected_drives))
                    else:
                        self._active_drive_obj_path = ''
                if was_active or not self._connected_drives:
                    GLib.idle_add(self._on_event, DriveEvent('removed', None))

    def eject_drive(self, drive_obj_path: str) -> bool:
        logger.info("CDManager eject_drive %s", drive_obj_path)
        if not drive_obj_path:
            logger.info("CDManager eject_drive no drive_obj_path")
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
            logger.info("CDManager eject_drive ejected %s", drive_obj_path)
            return True
        except Exception as e:
            logger.error("CDManager eject_drive failed for %s: %s", drive_obj_path, e)
            return False
