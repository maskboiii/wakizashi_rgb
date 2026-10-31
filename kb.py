"""Core HID control for ARDOR GAMING Wakizashi V2 / AULA F87 Pro.

SinoWealth (0x258A:0x010C) lighting interface. Commands go only through
Feature Reports with Report ID 0x06. No firmware / flash / bootloader
access is performed.
"""

import time

import hid

VID = 0x258A
PID = 0x010C            # default / wired
# Other AULA/SinoWealth product ids seen on 2.4 GHz receivers: the dongle
# may report the same lighting collection under a different PID/interface.
PIDS = [0x010C, 0x010B, 0x010A, 0x010D, 0x0109]

REPORT_ID = 0x06
DEFAULT_REPORT_LENGTH = 520

# The direct-RGB mode is volatile: the firmware reverts to the built-in
# effects unless the host keeps streaming color packets. The device falls
# back after ~1 s, so keep well below that (OpenRGB uses ~500 ms).
KEEPALIVE_S = 0.1

CMD_GET_MODEL = bytes([0x06, 0x82, 0x01, 0x00, 0x01, 0x00, 0x06])
MODEL_ID_OFFSET = 13

COLOR_HEADER = bytes([0x06, 0x08, 0x00, 0x00, 0x01, 0x00, 0x7A, 0x01])

# The OEM driver switches the firmware into host-driven direct RGB mode
# before streaming 0x08 packets: Report 0x39 (param reset) -> Report 0x3C
# (enable direct mode) -> Report 0x39 (confirm). Without this sequence the
# firmware keeps running its stored hardware effects and per-LED packets only
# flash through momentarily.
DIRECT_ENABLE_SEQUENCE = (
    bytes([0x39, 0x20, 0x06, 0x00, 0x01, 0x00]),
    bytes([0x3C, 0x20, 0x01, 0x00]),
    bytes([0x39, 0x20, 0x06, 0x01, 0x01, 0x00]),
)

MODEL_NAMES = {
    0x0B: "AULA F87 Pro (TKL 87)",
    0xBC: "AULA F87 Pro / Wakizashi V2 (TKL 87)",
    0xCD: "AULA F75",
    0xA4: "AULA F99",
    0xA3: "LEOBOG Hi75C Pro",
    0x20: "Redragon K686 Eisa Pro",
    0x05: "Redragon K686 Eisa Pro",
}

_F87_KEYS = [
    "ESC", "`", "TAB", "CAPS", "L_SHIFT", "L_CTRL", None,
    "1", "Q", "A", "Z", "L_WIN",
    "F1", "2", "W", "S", "X", "L_ALT",
    "F2", "3", "E", "D", "C", None,
    "F3", "4", "R", "F", "V", None,
    "F4", "5", "T", "G", "B", "SPACE",
    "F5", "6", "Y", "H", "N", None,
    "F6", "7", "U", "J", "M", None,
    "F7", "8", "I", "K", ",", "R_ALT",
    "F8", "9", "O", "L", ".", "FN",
    "F9", "0", "P", ";", "/", "MENU",
    "F10", "-", "[", "'", None, None,
    "F11", "=", "]", None, None, None,
    "F12", "BACKSPACE", "\\", "ENTER", "R_SHIFT", "R_CTRL",
    "PRINT", "INSERT", "DELETE", None, None,
    "LEFT",
    "SCROLL_LOCK", "HOME", "END", None,
    "UP", "DOWN",
    "PAUSE", "PAGE_UP", "PAGE_DOWN", None, None,
    "RIGHT",
]

KEY_ALIASES = {
    "ESCAPE": "ESC",
    "BS": "BACKSPACE",
    "BSPC": "BACKSPACE",
    "INS": "INSERT",
    "DEL": "DELETE",
    "CAPSLOCK": "CAPS",
    "CAPS_LOCK": "CAPS",
    "PRINT_SCREEN": "PRINT",
    "PRTSC": "PRINT",
    "PRTSCRN": "PRINT",
    "SCRLK": "SCROLL_LOCK",
    "PGUP": "PAGE_UP",
    "PGDN": "PAGE_DOWN",
    "RETURN": "ENTER",
    "RET": "ENTER",
    "SPACEBAR": "SPACE",
    "LSHIFT": "L_SHIFT",
    "SHIFT": "L_SHIFT",
    "RSHIFT": "R_SHIFT",
    "LCTRL": "L_CTRL",
    "LCONTROL": "L_CTRL",
    "CTRL": "L_CTRL",
    "RCTRL": "R_CTRL",
    "RCONTROL": "R_CTRL",
    "LWIN": "L_WIN",
    "WIN": "L_WIN",
    "WINDOWS": "L_WIN",
    "LALT": "L_ALT",
    "ALT": "L_ALT",
    "RALT": "R_ALT",
    "APP": "MENU",
    "R_MENU": "MENU",
    "FUNCTION": "FN",
    "GRAVE": "`",
    "BACKTICK": "`",
    "TILDE": "`",
    "MINUS": "-",
    "EQUALS": "=",
    "EQUAL": "=",
    "LBRACKET": "[",
    "RBRACKET": "]",
    "BACKSLASH": "\\",
    "SEMICOLON": ";",
    "QUOTE": "'",
    "APOSTROPHE": "'",
    "COMMA": ",",
    "PERIOD": ".",
    "DOT": ".",
    "SLASH": "/",
    "FORWARD_SLASH": "/",
    "UP_ARROW": "UP",
    "ARROW_UP": "UP",
    "ARROW UP": "UP",
    "DOWN_ARROW": "DOWN",
    "ARROW_DOWN": "DOWN",
    "ARROW DOWN": "DOWN",
    "LEFT_ARROW": "LEFT",
    "ARROW_LEFT": "LEFT",
    "ARROW LEFT": "LEFT",
    "RIGHT_ARROW": "RIGHT",
    "ARROW_RIGHT": "RIGHT",
    "ARROW RIGHT": "RIGHT",
}


def _build_layout(keys):
    by_name = {}
    for index, name in enumerate(keys):
        if name is not None and name not in by_name:
            by_name[name] = index
    return {"keys": keys, "led_count": len(keys), "by_name": by_name}


LAYOUTS = {"F87": _build_layout(_F87_KEYS)}
DEFAULT_LAYOUT = "F87"


class KbError(Exception):
    pass


def _attr(obj, name):
    if hasattr(obj, "get"):
        return obj.get(name)
    return getattr(obj, name, None)


def report_length(device=None, info=None, default=DEFAULT_REPORT_LENGTH):
    """Resolve the feature report length from the HID descriptor."""
    for src in (info, device):
        if src is None:
            continue
        value = _attr(src, "max_feature_report_length")
        if isinstance(value, int) and value > 0:
            return value
    return default


def _open_device(path):
    """Open a HID device path using the API of the installed hidapi version."""
    if hasattr(hid, "Device"):
        return hid.Device(path=path)
    device_cls = getattr(hid, "device", None)
    if device_cls is None:
        raise KbError("hid-модуль не предоставляет API для открытия устройства")
    dev = device_cls()
    dev.open_path(path)
    return dev


def _candidates():
    """Collect candidate lighting collections across known PIDs.

    Wired boards appear as 0x258A:0x010C on interface 1; a 2.4 GHz receiver
    exposes the same 0xFF00 lighting collection, sometimes on another PID or
    interface, so we scan several PIDs and prefer the 0xFF00 collection.
    """
    infos = []
    for pid in PIDS:
        for info in hid.enumerate(VID, pid):
            infos.append(info)
    infos.sort(key=lambda i: (
        0 if i.get("usage_page") == 0xFF00 else 1,
        0 if i.get("interface_number") == 1 else 1,
    ))
    return infos


def _probe(dev, info):
    length = report_length(dev, info)
    request = bytearray(length)
    request[:len(CMD_GET_MODEL)] = CMD_GET_MODEL
    dev.send_feature_report(bytes(request))
    time.sleep(0.01)
    return dev.get_feature_report(REPORT_ID, length)


def _open_working():
    """Open the lighting collection (probe 0xFF00 sub-collections of interface 1)."""
    for info in _candidates():
        if info.get("usage_page") != 0xFF00:
            continue
        try:
            dev = _open_device(info["path"])
        except Exception:
            continue
        try:
            response = _probe(dev, info)
            if response and len(response) > MODEL_ID_OFFSET:
                return dev, info, response
        except Exception:
            pass
        try:
            dev.close()
        except Exception:
            pass
    return None, None, None


def find_device():
    """Open and return the working lighting interface device, or None."""
    dev, _info, _response = _open_working()
    return dev


def get_model_id(device, length=None):
    """Query the model id byte via the init feature report.

    The id sits at response[13] (0x0B for stock F87 Pro; Wakizashi V2
    reports 0xBC). Returns None if the device did not answer.
    """
    length = length or report_length(device)
    request = bytearray(length)
    request[:len(CMD_GET_MODEL)] = CMD_GET_MODEL
    device.send_feature_report(bytes(request))
    time.sleep(0.01)
    response = device.get_feature_report(REPORT_ID, length)
    if len(response) <= MODEL_ID_OFFSET:
        return None
    return response[MODEL_ID_OFFSET]


def clamp_byte(value):
    return max(0, min(255, int(value)))


class Keyboard:
    """High-level controller for the Wakizashi V2 / F87 Pro lighting interface."""

    def __init__(self, device=None, layout=DEFAULT_LAYOUT, report_len=None):
        self._info = None
        self._model_response = None
        if device is not None:
            self.device = device
        else:
            self.device, self._info, self._model_response = _open_working()
        if self.device is None:
            raise KbError("Клавиатура не найдена. Проверьте USB-подключение "
                          "и режим (для RGB-управления нужен кабель).")
        if layout not in LAYOUTS:
            self.close()
            raise KbError(f"Неизвестный layout: {layout}")
        self.layout_name = layout
        layout_data = LAYOUTS[layout]
        self.led_count = layout_data["led_count"]
        self.key_index = layout_data["by_name"]
        self.report_length = report_len or report_length(self.device, self._info)
        if self._model_response and len(self._model_response) > MODEL_ID_OFFSET:
            self.model_id = self._model_response[MODEL_ID_OFFSET]
        else:
            self.model_id = None
        self.enable_direct_mode()

    def get_model_id(self):
        if self.model_id is None:
            self.model_id = get_model_id(self.device, self.report_length)
        return self.model_id

    def enable_direct_mode(self):
        """Switch the firmware into host-driven direct RGB mode.

        The OEM driver sends this short sequence before any 0x08 direct
        packets; without it the keyboard only flashes per-LED colors while
        its own hardware effect keeps running underneath.
        """
        for report in DIRECT_ENABLE_SEQUENCE:
            try:
                self.device.send_feature_report(report)
            except Exception:
                pass
            time.sleep(0.005)

    def _build_colors_packet(self, colors):
        packet = bytearray(self.report_length)
        packet[:len(COLOR_HEADER)] = COLOR_HEADER
        for index, (r, g, b) in enumerate(colors):
            if index >= self.led_count:
                break
            base = len(COLOR_HEADER) + index * 3
            packet[base] = clamp_byte(r)
            packet[base + 1] = clamp_byte(g)
            packet[base + 2] = clamp_byte(b)
        return bytes(packet)

    def set_solid_color(self, r, g, b):
        self.set_led_colors([(r, g, b)] * self.led_count)

    def set_led_colors(self, colors):
        """Stream a full per-LED colour frame (host-driven effects)."""
        self.device.send_feature_report(self._build_colors_packet(colors))

    def set_per_key(self, color_map):
        colors = [(0, 0, 0)] * self.led_count
        for key, color in color_map.items():
            index = self.resolve_index(key)
            if index is None:
                continue
            colors[index] = tuple(clamp_byte(channel) for channel in color)
        self.device.send_feature_report(self._build_colors_packet(colors))

    def set_off(self):
        self.set_solid_color(0, 0, 0)

    def resolve_index(self, key):
        if isinstance(key, int):
            return key if 0 <= key < self.led_count else None
        name = str(key).strip().upper()
        if name in self.key_index:
            return self.key_index[name]
        alias = KEY_ALIASES.get(name)
        if alias is not None and alias in self.key_index:
            return self.key_index[alias]
        return None

    def key_at(self, index):
        if 0 <= index < len(LAYOUTS[self.layout_name]["keys"]):
            return LAYOUTS[self.layout_name]["keys"][index]
        return None

    def close(self):
        if self.device is not None:
            try:
                self.device.close()
            except Exception:
                pass
            self.device = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
