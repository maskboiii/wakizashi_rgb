"""PyQt6 painter/effect host for the Wakizashi V2 / AULA F87 Pro RGB control.

The TKL layout is drawn as a grid of keycap-styled buttons placed at
absolute pixel coordinates on a dark themed background. Left-clicking a key
paints it with the currently armed palette colour; right-clicking clears the
key and turns it off. A selection mode lets you frame keys and recolor them
in batch. The "Effects" tab runs host-generated animations (rainbow wave,
breathing, ...) streamed through the direct-RGB protocol.
"""

import ctypes
import math
import random
import sys
import time
import winreg

from PyQt6.QtCore import Qt, QRect, QSettings, QSize, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QRubberBand,
    QScrollArea,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QSystemTrayIcon,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

import kb
from theme import (DARK, LIGHT, build_qss, keycap_base_qss, keycap_qss,
                   keycap_selected_qss, swatch_qss)
from widgets import (
    AuroraBackground,
    GlassPanel,
    HeaderBar,
    KeyboardCanvas,
    SpectrumWidget,
    StatusBar,
)

try:
    import audio as _audio
except Exception:  # audio capture is optional, like mss
    _audio = None

try:
    import mss as _mss
except Exception:  # mss is optional; the app falls back to QScreen grab
    _mss = None


def _new_grabber():
    """Create an mss grabber (new API name on recent mss, old one on legacy)."""
    factory = getattr(_mss, "MSS", None) or _mss.mss
    return factory()

# --------------------------------------------------------------------------
# Layout constants
# --------------------------------------------------------------------------
WINDOW_W = 1210         # main window width
WINDOW_H = 770          # main window height
KEYBOARD_W = 800        # fixed width of the keyboard canvas
KEYBOARD_H = 300        # height of the keyboard canvas
HEADER_H = 48           # slim brand / status strip above the workspace
DOCK_H = 52             # canvas hint + bulk actions strip
STATUS_H = 30           # status strip at the bottom
RAIL_W = 348            # fixed width of the control rail
X_OFFSET = 42            # horizontal centering shift for the key grid

# Application-wide stylesheet, key styles and design tokens now live in
# theme.py; the custom glass widgets live in widgets.py.

# --------------------------------------------------------------------------
# Pixel map for the 800x300 TKL grid.
# Format: (row, key_name, x, y, width, height, seq_index)
# seq_index is only a readable counter; the real hardware LED index is
# resolved from key_name against the layout in kb.py.
# --------------------------------------------------------------------------
KEY_MAP = [
    # Row 0 - function keys (y=14)
    (0, "Esc", 13, 14, 35, 30, 0),
    (0, "F1", 95, 14, 35, 30, 1),
    (0, "F2", 132, 14, 35, 30, 2),
    (0, "F3", 169, 14, 35, 30, 3),
    (0, "F4", 206, 14, 35, 30, 4),
    (0, "F5", 262, 14, 35, 30, 5),
    (0, "F6", 299, 14, 35, 30, 6),
    (0, "F7", 336, 14, 35, 30, 7),
    (0, "F8", 373, 14, 35, 30, 8),
    (0, "F9", 430, 14, 35, 30, 9),
    (0, "F10", 467, 14, 35, 30, 10),
    (0, "F11", 504, 14, 35, 30, 11),
    (0, "F12", 541, 14, 35, 30, 12),
    (0, "PrtSc", 595, 14, 35, 30, 13),
    (0, "ScrLk", 632, 14, 35, 30, 14),
    (0, "Pause", 669, 14, 35, 30, 15),

    # Row 1 - numbers (y=54)
    (1, "~", 13, 54, 35, 30, 16),
    (1, "1", 50, 54, 35, 30, 17),
    (1, "2", 87, 54, 35, 30, 18),
    (1, "3", 124, 54, 35, 30, 19),
    (1, "4", 161, 54, 35, 30, 20),
    (1, "5", 198, 54, 35, 30, 21),
    (1, "6", 235, 54, 35, 30, 22),
    (1, "7", 272, 54, 35, 30, 23),
    (1, "8", 309, 54, 35, 30, 24),
    (1, "9", 346, 54, 35, 30, 25),
    (1, "0", 383, 54, 35, 30, 26),
    (1, "-", 420, 54, 35, 30, 27),
    (1, "=", 457, 54, 35, 30, 28),
    (1, "Backspace", 494, 54, 82, 30, 29),
    (1, "Ins", 595, 54, 35, 30, 30),
    (1, "Home", 632, 54, 35, 30, 31),
    (1, "PgUp", 669, 54, 35, 30, 32),

    # Row 2 - QWERTY (y=90)
    (2, "Tab", 13, 90, 52, 30, 33),
    (2, "Q", 68, 90, 35, 30, 34),
    (2, "W", 105, 90, 35, 30, 35),
    (2, "E", 142, 90, 35, 30, 36),
    (2, "R", 179, 90, 35, 30, 37),
    (2, "T", 216, 90, 35, 30, 38),
    (2, "Y", 253, 90, 35, 30, 39),
    (2, "U", 290, 90, 35, 30, 40),
    (2, "I", 327, 90, 35, 30, 41),
    (2, "O", 364, 90, 35, 30, 42),
    (2, "P", 401, 90, 35, 30, 43),
    (2, "[", 438, 90, 35, 30, 44),
    (2, "]", 475, 90, 35, 30, 45),
    (2, "\\", 512, 90, 64, 30, 46),
    (2, "Del", 595, 90, 35, 30, 47),
    (2, "End", 632, 90, 35, 30, 48),
    (2, "PgDn", 669, 90, 35, 30, 49),

    # Row 3 - ASDF (y=126)
    (3, "Caps", 13, 126, 62, 30, 50),
    (3, "A", 78, 126, 35, 30, 51),
    (3, "S", 115, 126, 35, 30, 52),
    (3, "D", 152, 126, 35, 30, 53),
    (3, "F", 189, 126, 35, 30, 54),
    (3, "G", 226, 126, 35, 30, 55),
    (3, "H", 263, 126, 35, 30, 56),
    (3, "J", 300, 126, 35, 30, 57),
    (3, "K", 337, 126, 35, 30, 58),
    (3, "L", 374, 126, 35, 30, 59),
    (3, ";", 411, 126, 35, 30, 60),
    (3, "'", 448, 126, 35, 30, 61),
    (3, "Enter", 485, 126, 91, 30, 62),

    # Row 4 - ZXCV (y=162)
    (4, "LShift", 13, 162, 82, 30, 63),
    (4, "Z", 98, 162, 35, 30, 64),
    (4, "X", 135, 162, 35, 30, 65),
    (4, "C", 172, 162, 35, 30, 66),
    (4, "V", 209, 162, 35, 30, 67),
    (4, "B", 246, 162, 35, 30, 68),
    (4, "N", 283, 162, 35, 30, 69),
    (4, "M", 320, 162, 35, 30, 70),
    (4, ",", 357, 162, 35, 30, 71),
    (4, ".", 394, 162, 35, 30, 72),
    (4, "/", 431, 162, 35, 30, 73),
    (4, "RShift", 468, 162, 108, 30, 74),
    (4, "\u2191", 632, 162, 35, 30, 75),

    # Row 5 - bottom row (y=198)
    (5, "LCtrl", 13, 198, 48, 30, 76),
    (5, "LWin", 64, 198, 40, 30, 77),
    (5, "LAlt", 107, 198, 45, 30, 78),
    (5, "Space", 155, 198, 235, 30, 79),
    (5, "RAlt", 393, 198, 45, 30, 80),
    (5, "Fn", 441, 198, 40, 30, 81),
    (5, "Menu", 484, 198, 40, 30, 82),
    (5, "RCtrl", 527, 198, 49, 30, 83),
    (5, "\u2190", 595, 198, 35, 30, 84),
    (5, "\u2193", 632, 198, 35, 30, 85),
    (5, "\u2192", 669, 198, 35, 30, 86),
]

# Quick palette shown in the Paint tab.
PALETTE = [
    (255, 0, 0), (255, 128, 0), (255, 255, 0), (0, 255, 0),
    (0, 255, 255), (0, 128, 255), (0, 0, 255), (128, 0, 255),
    (255, 0, 255), (255, 255, 255), (0, 0, 0),
]

# UI key names that differ from the names known to kb.py.
UI_ALIASES = {"~": "`", "\u2191": "UP", "\u2190": "LEFT", "\u2193": "DOWN", "\u2192": "RIGHT"}

# The navigation + arrow cluster on the right side of the TKL board. When the
# "right section without effects" option is on, effects leave these LEDs dark.
RIGHT_SECTION_KEYS = (
    "PrtSc", "ScrLk", "Pause",
    "Ins", "Home", "PgUp",
    "Del", "End", "PgDn",
    "\u2191", "\u2190", "\u2193", "\u2192",
)

# Windows virtual-key → UI key name (US layout).
VK_TO_NAME = {
    0x41: "A", 0x42: "B", 0x43: "C", 0x44: "D", 0x45: "E",
    0x46: "F", 0x47: "G", 0x48: "H", 0x49: "I", 0x4A: "J",
    0x4B: "K", 0x4C: "L", 0x4D: "M", 0x4E: "N", 0x4F: "O",
    0x50: "P", 0x51: "Q", 0x52: "R", 0x53: "S", 0x54: "T",
    0x55: "U", 0x56: "V", 0x57: "W", 0x58: "X", 0x59: "Y", 0x5A: "Z",
    0x30: "0", 0x31: "1", 0x32: "2", 0x33: "3", 0x34: "4",
    0x35: "5", 0x36: "6", 0x37: "7", 0x38: "8", 0x39: "9",
    0x70: "F1", 0x71: "F2", 0x72: "F3", 0x73: "F4",
    0x74: "F5", 0x75: "F6", 0x76: "F7", 0x77: "F8",
    0x78: "F9", 0x79: "F10", 0x7A: "F11", 0x7B: "F12",
    0x1B: "Esc", 0x09: "Tab", 0x14: "Caps",
    0xA0: "LShift", 0xA1: "RShift",
    0xA2: "LCtrl", 0xA3: "RCtrl",
    0xA4: "LAlt", 0xA5: "RAlt",
    0x5B: "LWin", 0x5C: "LWin",
    0x20: "Space", 0x0D: "Enter", 0x08: "Backspace",
    0x2E: "Del", 0x2D: "Ins", 0x24: "Home", 0x23: "End",
    0x21: "PgUp", 0x22: "PgDn",
    0x26: "\u2191", 0x28: "\u2193", 0x25: "\u2190", 0x27: "\u2192",
    0x2C: "PrtSc", 0x91: "ScrLk", 0x13: "Pause",
    0xC0: "~", 0xBD: "-", 0xBB: "=", 0xDB: "[", 0xDD: "]", 0xDC: "\\",
    0xBA: ";", 0xDE: "'", 0xBC: ",", 0xBE: ".", 0xBF: "/",
    0x5D: "Menu",
}

EFFECTS = ["Статичный", "Дыхание", "Радуга", "Волна", "Амбилайт", "Игра",
           "Змейка", "Звёздный дождь", "Цветовой цикл", "Пульс", "Сканер",
           "Реактивный", "Спектр", "Спектр 2D", "Осциллограф", "Аудио-пульс"]

AUDIO_EFFECTS = ("Спектр", "Спектр 2D", "Осциллограф", "Аудио-пульс")
AUDIO_EFFECT_MODES = {
    "Спектр": "bars",
    "Спектр 2D": "fill",
    "Осциллограф": "wave",
    "Аудио-пульс": "pulse",
}

# Which controls actually affect each effect. Anything omitted is hidden in
# the rail to keep the panel focused. Audio effects are handled dynamically
# because their colour mode has its own selector.
EFFECT_PARAMS = {
    "Статичный": {"color", "rainbow"},
    "Дыхание": {"speed", "color", "rainbow"},
    "Радуга": {"speed", "reverse"},
    "Волна": {"speed", "reverse", "color", "rainbow"},
    "Амбилайт": set(),
    "Игра": set(),
    "Змейка": {"speed", "reverse", "color", "rainbow"},
    "Звёздный дождь": {"speed"},
    "Цветовой цикл": {"speed", "reverse"},
    "Пульс": {"speed", "reverse", "color", "rainbow"},
    "Сканер": {"speed", "reverse", "color", "rainbow"},
    "Реактивный": {"speed", "color", "rainbow"},
}

# One-click game lighting presets. Selecting one turns every other key off
# and lights only the listed keys in the preset colour.
GAME_PRESETS = {
    "CS2": {
        "color": (255, 128, 0),
        "keys": [
            "W", "A", "S", "D",
            "LShift", "LCtrl", "Space",
            "1", "2", "3", "4", "5",
            "R", "E", "Q", "F", "G", "Tab",
        ],
    },
    "Dota 2": {
        "color": (0, 200, 220),
        "keys": [
            "Q", "W", "E", "R",
            "A", "S", "D", "F",
            "1", "2", "3", "4", "5", "6",
            "Space", "Tab",
            "Z", "X", "C", "V", "B", "LAlt",
        ],
    },
    "LoL": {
        "color": (200, 170, 50),
        "keys": [
            "Q", "W", "E", "R",
            "D", "F",
            "A", "S",
            "1", "2", "3", "4", "5", "6", "7",
            "Space", "P", "B", "Tab",
        ],
    },
    "Apex Legends": {
        "color": (255, 100, 30),
        "keys": [
            "W", "A", "S", "D",
            "LShift", "LCtrl", "Space",
            "Q", "E", "R", "F", "Z",
            "1", "2", "3", "4",
            "Tab", "M", "C", "V",
        ],
    },
    "Fortnite": {
        "color": (150, 80, 255),
        "keys": [
            "W", "A", "S", "D",
            "LShift", "LCtrl", "Space",
            "E", "R", "Q", "F",
            "C", "V", "G",
            "Tab", "M", "LAlt",
            "1", "2", "3", "4", "5",
        ],
    },
    "Valorant": {
        "color": (240, 50, 50),
        "keys": [
            "W", "A", "S", "D",
            "LShift", "LCtrl", "Space",
            "Q", "E", "C", "X",
            "F", "R",
            "1", "2", "3", "4",
            "Caps", "M",
        ],
    },
    "Minecraft": {
        "color": (100, 200, 50),
        "keys": [
            "W", "A", "S", "D",
            "LShift", "LCtrl", "Space",
            "E", "Q",
            "1", "2", "3", "4", "5", "6", "7", "8", "9",
            "F", "T", "Esc",
        ],
    },
    "GTA V": {
        "color": (255, 220, 0),
        "keys": [
            "W", "A", "S", "D",
            "LShift", "LCtrl", "Space",
            "F", "R", "Q", "E",
            "Tab", "M",
            "1", "2", "3", "4", "5",
        ],
    },
    "Escape from Tarkov": {
        "color": (200, 130, 40),
        "keys": [
            "W", "A", "S", "D",
            "LShift", "C", "X", "Space",
            "F", "R", "Q", "E",
            "Tab",
            "1", "2", "3", "4", "5", "6", "7", "8", "9", "0",
            "B", "T", "G", "N", "Y", "Z", "LAlt",
        ],
    },
    "R6 Siege": {
        "color": (50, 130, 240),
        "keys": [
            "W", "A", "S", "D",
            "LShift", "LCtrl", "C", "Space",
            "F", "R", "Q", "E", "G", "V",
            "Z",
            "1", "2", "3", "4",
            "Tab", "Caps",
        ],
    },
    "CoD Warzone": {
        "color": (100, 180, 60),
        "keys": [
            "W", "A", "S", "D",
            "LShift", "LCtrl", "C", "Space",
            "F", "R", "Q", "E", "G", "V",
            "Tab", "M",
            "1", "2", "3", "4",
            "X",
        ],
    },
    "WoW": {
        "color": (220, 180, 40),
        "keys": [
            "W", "A", "S", "D",
            "Space",
            "Q", "E", "R", "T", "F", "G",
            "Z", "X", "C", "V", "B",
            "Tab", "Esc",
            "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "=",
            "M", "P", "L",
        ],
    },
    "Elden Ring": {
        "color": (200, 160, 30),
        "keys": [
            "W", "A", "S", "D",
            "Space", "F",
            "E", "R", "Q",
            "LCtrl", "G",
            "Esc",
            "1", "2", "3", "4",
            "\u2191", "\u2193", "\u2190", "\u2192",
        ],
    },
    "Cyberpunk 2077": {
        "color": (230, 255, 30),
        "keys": [
            "W", "A", "S", "D",
            "LShift", "LCtrl", "C", "Space",
            "F", "R", "Q", "E",
            "Tab",
            "1", "2", "3", "4",
            "M", "I", "T", "X", "LAlt",
        ],
    },
    "Battlefield": {
        "color": (0, 220, 120),
        "keys": [
            "W", "A", "S", "D",
            "LShift", "LCtrl", "Space",
            "R", "F", "Q", "E", "C", "X",
            "1", "2", "3", "4", "5",
        ],
    },
}


def resolve_led_index(name):
    """Map a UI key name to the real hardware LED index used by kb.py."""
    key = UI_ALIASES.get(name.strip().upper(), name.strip().upper())
    index_map = kb.LAYOUTS[kb.DEFAULT_LAYOUT]["by_name"]
    if key in index_map:
        return index_map[key]
    alias = kb.KEY_ALIASES.get(key)
    if alias is not None and alias in index_map:
        return index_map[alias]
    return None


def hsv_to_rgb(h, s, v):
    h = h % 360
    c = v * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = v - c
    if h < 60:
        r, g, b = c, x, 0
    elif h < 120:
        r, g, b = x, c, 0
    elif h < 180:
        r, g, b = 0, c, x
    elif h < 240:
        r, g, b = 0, x, c
    elif h < 300:
        r, g, b = x, 0, c
    else:
        r, g, b = c, 0, x
    return (int((r + m) * 255), int((g + m) * 255), int((b + m) * 255))


_GRADIENT_STOPS = (
    (0.0, (14, 0, 32)),
    (0.35, (74, 0, 140)),
    (0.6, (190, 0, 150)),
    (0.8, (255, 45, 60)),
    (1.0, (255, 165, 35)),
)


def _gradient(stops, t):
    t = max(0.0, min(1.0, float(t)))
    for i in range(len(stops) - 1):
        t0, c0 = stops[i]
        t1, c1 = stops[i + 1]
        if t <= t1:
            k = 0.0 if t1 <= t0 else (t - t0) / (t1 - t0)
            return tuple(int(round(c0[j] + (c1[j] - c0[j]) * k))
                         for j in range(3))
    return stops[-1][1]


def minimeters_colormap(t):
    """Amplitude gradient modelled on the MiniMeters Spectrum module."""
    return _gradient(_GRADIENT_STOPS, t)


# Base frame rate the effect math was written for. `_frame` is kept as a
# frame-equivalent counter derived from real elapsed time, so animations run at
# the same speed no matter how fast the timer ticks.
FRAME_HZ = 20.0

# Samples per zone axis when averaging a screen zone (8 -> 64 samples/zone).
AMBI_SAMPLES = 8


# sRGB -> linear light lookup (for physically correct zone averaging).
_SRGB_TO_LINEAR = tuple(
    (c / 255.0 / 12.92) if (c / 255.0) <= 0.04045
    else (((c / 255.0) + 0.055) / 1.055) ** 2.4
    for c in range(256)
)


def _linear_to_srgb(value):
    value = 0.0 if value < 0.0 else (1.0 if value > 1.0 else value)
    if value <= 0.0031308:
        s = value * 12.92
    else:
        s = 1.055 * (value ** (1.0 / 2.4)) - 0.055
    return int(round(s * 255))


def boost_saturation(rgb, amount):
    """Push a colour away from grey by `amount` (0..2) to counter LED washout."""
    if amount <= 0:
        return rgb
    r, g, b = rgb
    luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return tuple(
        max(0, min(255, int(round(luma + (c - luma) * (1.0 + amount)))))
        for c in (r, g, b)
    )


def apply_brightness(rgb, gain):
    """Scale a colour by `gain` (1.0 = unchanged) to recover dim ambilight zones."""
    if gain == 1.0:
        return rgb
    return tuple(
        max(0, min(255, int(round(c * gain))))
        for c in rgb
    )


def grade_zone(rgb, saturation, brightness):
    """Apply the ambilight saturation + brightness controls to one colour."""
    if saturation > 0:
        rgb = boost_saturation(rgb, saturation)
    return apply_brightness(rgb, brightness)


class AmbilightWorker(QThread):
    """Grabs a monitor off the GUI thread and emits averaged zone colours.

    QScreen.grabWindow() must run on the GUI thread, so the capture uses mss
    (GDI BitBlt) which returns plain bytes and is safe in a worker thread.
    """

    gridReady = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cols = 8
        self.rows = 4
        self.hz = 25.0
        self.drop_dark = False
        self.monitor = None   # mss monitor dict {left, top, width, height}

    def run(self):
        if _mss is None:
            return
        try:
            grabber = _new_grabber()
        except Exception:
            return
        try:
            while not self.isInterruptionRequested():
                started = time.monotonic()
                monitor = self.monitor
                if monitor is None:
                    self.msleep(200)
                    continue
                try:
                    shot = grabber.grab(monitor)
                except Exception:
                    self.msleep(200)
                    continue
                try:
                    self.gridReady.emit(self._sample(shot))
                except Exception:
                    pass
                wait = (1.0 / max(1.0, self.hz)) - (time.monotonic() - started)
                if wait > 0:
                    self.msleep(int(wait * 1000))
        finally:
            try:
                grabber.close()
            except Exception:
                pass

    def _sample(self, shot):
        raw = shot.raw
        width = shot.width
        height = shot.height
        cols = self.cols
        rows = self.rows
        colors = []
        for row in range(rows):
            y0 = height * row // rows
            y1 = max(y0 + 1, height * (row + 1) // rows)
            for col in range(cols):
                x0 = width * col // cols
                x1 = max(x0 + 1, width * (col + 1) // cols)
                colors.append(self._zone_color(raw, width, x0, y0, x1, y1))
        return colors

    def _zone_color(self, raw, width, x0, y0, x1, y1):
        step = AMBI_SAMPLES
        span_x = x1 - x0
        span_y = y1 - y0
        drop_dark = self.drop_dark
        tr = tg = tb = 0.0
        count = 0
        for iy in range(step):
            row_base = ((y0 + (iy * span_y) // step) * width) * 4
            for ix in range(step):
                o = row_base + (x0 + (ix * span_x) // step) * 4
                b = raw[o]
                g = raw[o + 1]
                r = raw[o + 2]
                if drop_dark and r < 12 and g < 12 and b < 12:
                    continue
                tr += _SRGB_TO_LINEAR[r]
                tg += _SRGB_TO_LINEAR[g]
                tb += _SRGB_TO_LINEAR[b]
                count += 1
        if count == 0:
            return (0, 0, 0)
        return (
            _linear_to_srgb(tr / count),
            _linear_to_srgb(tg / count),
            _linear_to_srgb(tb / count),
        )


class KeyButton(QPushButton):
    """QPushButton that also emits rightClicked on the right mouse button."""

    rightClicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.rightClicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Wakizashi V2 — RGB Paint")
        self.setMinimumSize(WINDOW_W, WINDOW_H)
        self.resize(WINDOW_W, WINDOW_H)

        self.keyboard = None
        self.painted = {}          # key_name -> (r, g, b)
        self.selected = set()      # key_names framed in the selection mode
        self.current_color = None  # armed palette colour
        self.selection_mode = False
        self.key_buttons = {}
        self.palette_buttons = []
        self.led_pos = {}          # led_index -> (center_x, center_y)

        self.active_effect = None
        self.effect_color = (255, 255, 255)
        self._frame = 0.0
        self._elapsed = 0.0
        self._last_tick = None
        self._tick = 0
        self._ambi_target = (255, 255, 255)
        self._ambi_current = []
        self._ambi_single = (0, 0, 0)
        self._ambi_last = 0.0
        self._ambi_grid = None
        self._ambi_worker = None
        self._amba_monitors = []
        self.led_zone = {}
        self._ambi_cols = 8
        self._ambi_rows = 4
        self._force_close = False
        self._sparkle_keys = {}    # led_index -> (r, g, b, life)
        self._snake_path = None
        self._audio_worker = None
        self._audio_data = {"bands": [], "wave": [], "level": 0.0, "peak": 0.0}
        self._audio_last = 0.0
        self._led_band = {}
        self._led_xnorm = {}
        self._led_ynorm = {}
        self._audio_map_key = None
        self._rubber_band = None
        self._sel_origin = None
        self._preview_only = False
        self._rainbow_mode = False
        self._ripples = []         # (x, y, start_frame, hue_or_None)
        self._prev_keys = set()    # previously pressed VK codes

        self._tokens = DARK
        self._excluded_leds = set()  # right-section LEDs skipped by effects

        self._build_ui()
        self._connect_device()
        self._setup_tray()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._keepalive)
        self.timer.start(int(kb.KEEPALIVE_S * 1000))

        self.effect_timer = QTimer(self)
        self.effect_timer.setInterval(33)
        self.effect_timer.timeout.connect(self._effect_tick)

        self.settings_dialog = self._build_settings_dialog()
        self._load_settings()
        self._apply_dark_titlebar(self._tokens.get("name") == "dark")

    # -- UI -------------------------------------------------------------
    def _build_ui(self):
        self.aurora = AuroraBackground(self._tokens, self)
        self.setCentralWidget(self.aurora)
        outer = QVBoxLayout(self.aurora)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.header = HeaderBar(self._tokens, self.aurora)
        outer.addWidget(self.header)

        body = QWidget(self.aurora)
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(16, 12, 16, 12)
        body_layout.setSpacing(12)
        outer.addWidget(body, 1)

        stage = QWidget(body)
        stage_layout = QVBoxLayout(stage)
        stage_layout.setContentsMargins(0, 0, 0, 0)
        stage_layout.setSpacing(12)

        hero = QHBoxLayout()
        hero.setContentsMargins(0, 0, 0, 0)
        hero.addStretch(1)
        self.background = KeyboardCanvas(self._tokens, stage)
        self.background.setFixedSize(KEYBOARD_W, KEYBOARD_H)
        self.background.installEventFilter(self)
        self._rubber_band = QRubberBand(QRubberBand.Shape.Rectangle, self.background)
        hero.addWidget(self.background)
        hero.addStretch(1)
        stage_layout.addLayout(hero)

        self._build_presets_panel(stage)
        stage_layout.addWidget(self.presets_panel)

        self._build_dock(stage)
        stage_layout.addWidget(self.dock)
        stage_layout.addStretch(1)
        body_layout.addWidget(stage, 1)

        self._build_side_rail(body)
        body_layout.addWidget(self.rail, 0)

        self.status_text = "поиск устройства..."
        self.status_label = StatusBar(self._tokens, self.status_text, self.aurora)
        self.status_label.setFixedHeight(STATUS_H)
        outer.addWidget(self.status_label)

        self._build_keys()
        self.mode_buttons[0].setFocus()

    # -- Layout helpers --------------------------------------------------
    def _group_title(self, text):
        label = QLabel(text)
        label.setObjectName("GroupTitle")
        return label

    def _divider(self):
        line = QFrame()
        line.setObjectName("Divider")
        line.setFixedHeight(1)
        return line

    def _scroll_page(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.viewport().setAutoFillBackground(False)
        inner = QWidget()
        inner.setAutoFillBackground(False)
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(0, 0, 6, 0)
        layout.setSpacing(10)
        scroll.setWidget(inner)
        return scroll, layout

    def _build_presets_panel(self, parent):
        self.presets_panel = GlassPanel(self._tokens, 14, parent)
        layout = QVBoxLayout(self.presets_panel)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(10)
        layout.addWidget(self._group_title("ИГРОВЫЕ ПРЕСЕТЫ"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        for i, name in enumerate(GAME_PRESETS):
            btn = QPushButton(name)
            btn.setObjectName("Preset")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(f"Применить пресет «{name}»")
            btn.clicked.connect(lambda _checked=False, n=name: self._apply_game_preset(n))
            grid.addWidget(btn, i // 5, i % 5)
        layout.addLayout(grid)

    def _build_dock(self, parent):
        self.dock = GlassPanel(self._tokens, 12, parent)
        self.dock.setFixedHeight(DOCK_H)
        layout = QHBoxLayout(self.dock)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(10)
        hint = QLabel("ЛКМ — покрасить · ПКМ — очистить · «Выделение» — рамка и пакетная заливка")
        hint.setStyleSheet(f"color: {self._tokens['text_muted']}; font-size: 11px;")
        layout.addWidget(hint, 1)
        clear = QPushButton("Очистить всё")
        clear.clicked.connect(self._clear_all)
        layout.addWidget(clear)
        rescan = QPushButton("Пересканировать")
        rescan.setToolTip("Повторный поиск клавиатуры по USB")
        rescan.clicked.connect(self._rescan)
        layout.addWidget(rescan)

    def _build_side_rail(self, parent):
        self.rail = GlassPanel(self._tokens, 16, parent)
        self.rail.setFixedWidth(RAIL_W)
        layout = QVBoxLayout(self.rail)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        seg = QHBoxLayout()
        seg.setSpacing(4)
        self.mode_buttons = []
        for index, label in enumerate(("Покраска", "Эффекты")):
            btn = QPushButton(label)
            btn.setObjectName("SegMode")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _checked=False, i=index: self._set_mode(i))
            seg.addWidget(btn, 1)
            self.mode_buttons.append(btn)
        layout.addLayout(seg)
        layout.addWidget(self._divider())

        self.mode_stack = QStackedWidget()
        self._build_paint_tab()
        self._build_effects_tab()
        layout.addWidget(self.mode_stack, 1)

        self._build_rail_footer(layout)

        self._set_mode(0)

    def _build_rail_footer(self, layout):
        layout.addWidget(self._divider())
        run_row = QHBoxLayout()
        run_row.setSpacing(6)
        self.start_btn = QPushButton("Запустить")
        self.start_btn.setObjectName("Primary")
        self.start_btn.clicked.connect(self._start_effect)
        run_row.addWidget(self.start_btn, 1)
        self.stop_btn = QPushButton("Стоп")
        self.stop_btn.clicked.connect(self._stop_effect)
        run_row.addWidget(self.stop_btn)
        layout.addLayout(run_row)

        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        self.preview_check = QCheckBox("Превью")
        self.preview_check.setToolTip("Анимация только на экране, без клавиатуры")
        self.preview_check.toggled.connect(self._toggle_preview)
        bottom.addWidget(self.preview_check)
        bottom.addStretch(1)
        self.settings_btn = QPushButton("Настройки")
        self.settings_btn.setToolTip("Настройки приложения")
        self.settings_btn.setFixedHeight(28)
        self.settings_btn.clicked.connect(self._open_settings)
        bottom.addWidget(self.settings_btn)
        layout.addLayout(bottom)

    def _set_mode(self, index):
        for i, btn in enumerate(self.mode_buttons):
            btn.setChecked(i == index)
        self.mode_stack.setCurrentIndex(index)

    def _swatch_style(self, r, g, b, active=False):
        return swatch_qss(r, g, b, active, self._tokens["accent"])

    def _build_paint_tab(self):
        page, v = self._scroll_page()
        v.addWidget(self._group_title("ЦВЕТ"))

        armed = QHBoxLayout()
        armed.setSpacing(10)
        self.swatch = QLabel()
        self.swatch.setFixedSize(28, 28)
        self.swatch.setStyleSheet(
            f"background-color: transparent;"
            f" border: 1px dashed {self._tokens['text_muted']}; border-radius: 14px;")
        self.hex_label = QLabel("—")
        self.hex_label.setObjectName("MonoValue")
        armed.addWidget(self.swatch)
        armed.addWidget(self.hex_label, 1)
        v.addLayout(armed)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        for i, color in enumerate(PALETTE):
            sw = QPushButton()
            sw.setFixedSize(28, 28)
            sw.setCursor(Qt.CursorShape.PointingHandCursor)
            sw.setStyleSheet(self._swatch_style(*color))
            sw.setToolTip(f"rgb({color[0]}, {color[1]}, {color[2]})")
            sw.clicked.connect(lambda _checked=False, c=color: self._arm_color(*c))
            grid.addWidget(sw, i // 6, i % 6)
            self.palette_buttons.append((sw, color))
        v.addLayout(grid)

        custom = QPushButton("Свой цвет...")
        custom.clicked.connect(self._custom_color)
        v.addWidget(custom)

        v.addWidget(self._divider())
        v.addWidget(self._group_title("ВЫДЕЛЕНИЕ"))
        self.sel_check = QCheckBox("Режим выделения")
        self.sel_check.toggled.connect(self._set_selection_mode)
        v.addWidget(self.sel_check)

        row = QHBoxLayout()
        row.setSpacing(6)
        b_all = QPushButton("Выделить все")
        b_all.clicked.connect(self._select_all)
        row.addWidget(b_all, 1)
        b_none = QPushButton("Снять")
        b_none.setToolTip("Снять выделение")
        b_none.clicked.connect(self._deselect_all)
        row.addWidget(b_none, 1)
        v.addLayout(row)

        b_apply = QPushButton("Покрасить выделенные")
        b_apply.setObjectName("Primary")
        b_apply.setFixedHeight(32)
        b_apply.clicked.connect(self._apply_to_selection)
        v.addWidget(b_apply)
        v.addStretch(1)

        self.mode_stack.addWidget(page)

    def _build_effects_tab(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 6, 0)
        v.setSpacing(6)
        v.addWidget(self._group_title("ЭФФЕКТ"))

        self.effect_combo = QComboBox()
        self.effect_combo.addItems(EFFECTS)
        self.effect_combo.currentTextChanged.connect(self._on_effect_changed)
        v.addWidget(self.effect_combo)

        self.effect_color_box = QWidget()
        color_row = QHBoxLayout(self.effect_color_box)
        color_row.setContentsMargins(0, 0, 0, 0)
        color_row.setSpacing(8)
        self.effect_color_swatch = QLabel()
        self.effect_color_swatch.setFixedSize(28, 28)
        self.effect_color_swatch.setStyleSheet(self._swatch_style(255, 255, 255))
        color_row.addWidget(self.effect_color_swatch)
        btn_color = QPushButton("Цвет...")
        btn_color.clicked.connect(self._pick_effect_color)
        color_row.addWidget(btn_color, 1)
        v.addWidget(self.effect_color_box)

        self.speed_box = QWidget()
        speed_row = QHBoxLayout(self.speed_box)
        speed_row.setContentsMargins(0, 0, 0, 0)
        speed_row.setSpacing(10)
        speed_row.addWidget(QLabel("Скорость"))
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(1, 30)
        self.speed_slider.setValue(10)
        speed_row.addWidget(self.speed_slider, 1)
        v.addWidget(self.speed_box)

        checks = QHBoxLayout()
        checks.setSpacing(16)
        self.reverse_check = QCheckBox("Реверс")
        checks.addWidget(self.reverse_check)
        self.rainbow_check = QCheckBox("Радужный")
        self.rainbow_check.toggled.connect(self._toggle_rainbow)
        checks.addWidget(self.rainbow_check)
        checks.addStretch(1)
        v.addLayout(checks)

        self.excl_right_check = QCheckBox("Правая секция без эффектов")
        self.excl_right_check.setToolTip(
            "Эффекты не подсвечивают Ins/Home/PgUp/Del/End/PgDn, стрелки "
            "и PrtSc/ScrLk/Pause; амбилайт-сетка растягивается на остальные клавиши")
        self._connect_setting_persist(self.excl_right_check)
        self.excl_right_check.toggled.connect(self._rebuild_led_zones)
        v.addWidget(self.excl_right_check)

        v.addWidget(self._divider())
        self._build_ambilight_widget()
        v.addWidget(self.ambi_widget)
        self._build_audio_widget()
        v.addWidget(self.audio_widget)
        v.addStretch(1)

        self._update_effect_params()
        self.mode_stack.addWidget(page)

    def _update_effect_params(self, *_):
        if not hasattr(self, "speed_box"):
            return
        effect = self.effect_combo.currentText()
        if effect in AUDIO_EFFECTS:
            params = {"rainbow"}
            if effect in ("Спектр", "Спектр 2D"):
                if self.audio_color_combo.currentIndex() == 2:
                    params.add("color")
            else:
                params.add("color")
        else:
            params = EFFECT_PARAMS.get(
                effect, {"speed", "reverse", "color", "rainbow"})
        self.speed_box.setVisible("speed" in params)
        self.reverse_check.setVisible("reverse" in params)
        self.rainbow_check.setVisible("rainbow" in params)
        self.effect_color_box.setVisible("color" in params)

    def _build_ambilight_widget(self):
        self.ambi_widget = QWidget()
        v = QVBoxLayout(self.ambi_widget)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        v.addWidget(self._group_title("AMBIENT LIGHT"))

        monitor_row = QHBoxLayout()
        monitor_row.setSpacing(8)
        monitor_row.addWidget(QLabel("Монитор"))
        self.screen_combo = QComboBox()
        self.screens = QApplication.screens()
        for i, sc in enumerate(self.screens):
            g = sc.geometry()
            self.screen_combo.addItem(f"{i + 1}: {sc.name()} {g.width()}x{g.height()}")
        primary = QApplication.primaryScreen()
        default_idx = self.screens.index(primary) if primary in self.screens else 0
        self.screen_combo.setCurrentIndex(default_idx)
        monitor_row.addWidget(self.screen_combo, 1)
        v.addLayout(monitor_row)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        mode_row.addWidget(QLabel("Режим"))
        self.ambi_mode_combo = QComboBox()
        self.ambi_mode_combo.addItems(["Сетка (колонки × строки)", "Колонки"])
        mode_row.addWidget(self.ambi_mode_combo, 1)
        v.addLayout(mode_row)

        spins = QGridLayout()
        spins.setHorizontalSpacing(8)
        spins.setVerticalSpacing(2)
        spins.addWidget(QLabel("Колонок"), 0, 0)
        self.ambi_cols_spin = QSpinBox()
        self.ambi_cols_spin.setRange(1, 16)
        self.ambi_cols_spin.setValue(8)
        spins.addWidget(self.ambi_cols_spin, 1, 0)
        spins.addWidget(QLabel("Строк"), 0, 1)
        self.ambi_rows_spin = QSpinBox()
        self.ambi_rows_spin.setRange(1, 6)
        self.ambi_rows_spin.setValue(4)
        spins.addWidget(self.ambi_rows_spin, 1, 1)
        spins.addWidget(QLabel("Частота, Гц"), 0, 2)
        self.ambi_hz_spin = QSpinBox()
        self.ambi_hz_spin.setRange(5, 60)
        self.ambi_hz_spin.setValue(25)
        spins.addWidget(self.ambi_hz_spin, 1, 2)
        for column in range(3):
            spins.setColumnStretch(column, 1)
        v.addLayout(spins)

        self.ambi_smooth_slider = QSlider(Qt.Orientation.Horizontal)
        self.ambi_smooth_slider.setRange(10, 100)
        self.ambi_smooth_slider.setValue(60)
        self.ambi_sat_slider = QSlider(Qt.Orientation.Horizontal)
        self.ambi_sat_slider.setRange(0, 200)
        self.ambi_sat_slider.setValue(30)
        self.ambi_sat_slider.setToolTip("100% — как на экране, выше — сочнее")
        self.ambi_bright_slider = QSlider(Qt.Orientation.Horizontal)
        self.ambi_bright_slider.setRange(10, 200)
        self.ambi_bright_slider.setValue(130)
        self.ambi_bright_slider.setToolTip("100% — без изменений, выше — ярче")

        sliders = QGridLayout()
        sliders.setHorizontalSpacing(8)
        sliders.setVerticalSpacing(4)
        for row, (label, slider) in enumerate((
            ("Сглаживание", self.ambi_smooth_slider),
            ("Насыщенность", self.ambi_sat_slider),
            ("Яркость", self.ambi_bright_slider),
        )):
            sliders.addWidget(QLabel(label), row, 0)
            sliders.addWidget(slider, row, 1)
        sliders.setColumnStretch(1, 1)
        v.addLayout(sliders)

        self.ambi_dark_check = QCheckBox("Игнорировать чёрные полосы")
        v.addWidget(self.ambi_dark_check)

        self._amba_monitors = []
        if _mss is not None:
            try:
                with _new_grabber() as probe:
                    self._amba_monitors = list(probe.monitors)
            except Exception:
                self._amba_monitors = []

        self.ambi_cols_spin.valueChanged.connect(self._rebuild_led_zones)
        self.ambi_rows_spin.valueChanged.connect(self._rebuild_led_zones)
        self.ambi_mode_combo.currentIndexChanged.connect(self._rebuild_led_zones)
        self.ambi_dark_check.toggled.connect(self._sync_ambi_worker)
        self.ambi_hz_spin.valueChanged.connect(self._sync_ambi_worker)
        for widget in (self.ambi_cols_spin, self.ambi_rows_spin, self.ambi_mode_combo,
                       self.ambi_dark_check, self.ambi_hz_spin, self.ambi_smooth_slider,
                       self.ambi_sat_slider, self.ambi_bright_slider, self.screen_combo):
            self._connect_setting_persist(widget)
        self.ambi_widget.setVisible(False)

    def _build_audio_widget(self):
        self.audio_widget = QWidget()
        v = QVBoxLayout(self.audio_widget)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        v.addWidget(self._group_title("АУДИО"))
        self.spectrum_widget = SpectrumWidget(self._tokens)
        self.spectrum_widget.setFixedHeight(48)
        v.addWidget(self.spectrum_widget)

        device_row = QHBoxLayout()
        device_row.setSpacing(8)
        device_row.addWidget(QLabel("Устройство"))
        self.audio_device_combo = QComboBox()
        self.audio_device_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.audio_device_combo.setMinimumContentsLength(10)
        device_row.addWidget(self.audio_device_combo, 1)
        audio_refresh = QPushButton("Обновить")
        audio_refresh.setToolTip("Обновить список устройств")
        audio_refresh.clicked.connect(self._refresh_audio_devices)
        device_row.addWidget(audio_refresh)
        v.addLayout(device_row)

        opts = QHBoxLayout()
        opts.setSpacing(6)
        opts.addWidget(QLabel("Полос"))
        self.audio_bands_spin = QSpinBox()
        self.audio_bands_spin.setRange(4, 64)
        self.audio_bands_spin.setValue(16)
        opts.addWidget(self.audio_bands_spin)
        opts.addWidget(QLabel("Шкала"))
        self.audio_scale_combo = QComboBox()
        self.audio_scale_combo.addItems(["Лог", "Mel", "Линейная"])
        opts.addWidget(self.audio_scale_combo, 1)
        v.addLayout(opts)

        self.audio_gain_slider = QSlider(Qt.Orientation.Horizontal)
        self.audio_gain_slider.setRange(-24, 24)
        self.audio_gain_slider.setValue(0)
        self.audio_floor_spin = QSpinBox()
        self.audio_floor_spin.setRange(-90, -20)
        self.audio_floor_spin.setValue(-80)
        self.audio_attack_slider = QSlider(Qt.Orientation.Horizontal)
        self.audio_attack_slider.setRange(1, 200)
        self.audio_attack_slider.setValue(10)
        self.audio_release_slider = QSlider(Qt.Orientation.Horizontal)
        self.audio_release_slider.setRange(10, 1000)
        self.audio_release_slider.setValue(150)

        sliders = QGridLayout()
        sliders.setHorizontalSpacing(8)
        sliders.setVerticalSpacing(4)
        for row, (label, widget) in enumerate((
            ("Гейн, дБ", self.audio_gain_slider),
            ("Пол, дБ", self.audio_floor_spin),
            ("Атака", self.audio_attack_slider),
            ("Спад", self.audio_release_slider),
        )):
            sliders.addWidget(QLabel(label), row, 0)
            sliders.addWidget(widget, row, 1)
        sliders.setColumnStretch(1, 1)
        v.addLayout(sliders)

        color_row = QHBoxLayout()
        color_row.setSpacing(6)
        color_row.addWidget(QLabel("Окраска"))
        self.audio_color_combo = QComboBox()
        self.audio_color_combo.addItems(["MiniMeters", "Радужный", "Статичный"])
        color_row.addWidget(self.audio_color_combo, 1)
        self.audio_mono_check = QCheckBox("Моно")
        self.audio_mono_check.setChecked(True)
        color_row.addWidget(self.audio_mono_check)
        v.addLayout(color_row)

        self._refresh_audio_devices()
        for widget in (self.audio_device_combo, self.audio_bands_spin,
                       self.audio_scale_combo, self.audio_gain_slider,
                       self.audio_floor_spin, self.audio_attack_slider,
                       self.audio_release_slider, self.audio_color_combo,
                       self.audio_mono_check):
            self._connect_setting_persist(widget)
            if isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(self._audio_settings_changed)
            elif isinstance(widget, QSpinBox):
                widget.valueChanged.connect(self._audio_settings_changed)
            elif isinstance(widget, QCheckBox):
                widget.toggled.connect(self._audio_settings_changed)
            elif isinstance(widget, QSlider):
                widget.valueChanged.connect(self._audio_settings_changed)
        self.audio_color_combo.currentIndexChanged.connect(self._update_effect_params)
        self.audio_widget.setVisible(False)

    # -- Settings dialog ---------------------------------------------------
    def _build_settings_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Настройки")
        dlg.setMinimumWidth(420)
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        shell = QVBoxLayout(dlg)
        shell.setContentsMargins(12, 12, 12, 12)
        self._settings_panel = GlassPanel(self._tokens, 16, dlg)
        shell.addWidget(self._settings_panel)
        form = QVBoxLayout(self._settings_panel)
        form.setContentsMargins(20, 18, 20, 18)
        form.setSpacing(12)

        self.autostart_check = QCheckBox("Запускать вместе с Windows")
        self.autostart_check.toggled.connect(self._toggle_autostart)
        form.addWidget(self.autostart_check)

        theme_row = QHBoxLayout()
        theme_row.setSpacing(6)
        theme_row.addWidget(QLabel("Тема оформления:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Тёмная", "Светлая"])
        self.theme_combo.currentIndexChanged.connect(self._apply_theme)
        theme_row.addWidget(self.theme_combo)
        theme_row.addStretch(1)
        form.addLayout(theme_row)

        self.tray_check = QCheckBox("Сворачивать в трей при закрытии (без вопроса)")
        self.tray_check.toggled.connect(self._save_settings)
        form.addWidget(self.tray_check)

        line = QLabel()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background-color: {self._tokens['glass_border']};")
        form.addWidget(line)

        reset_row = QHBoxLayout()
        reset_btn = QPushButton("Сбросить настройки")
        reset_btn.clicked.connect(self._reset_settings)
        reset_row.addWidget(reset_btn)
        reset_row.addStretch(1)
        form.addLayout(reset_row)

        about = QLabel("Wakizashi RGB · v1.9.1\nПодсветка клавиатуры SinoWealth (AULA F87 Pro и совместимые)")
        about.setStyleSheet(f"color: {self._tokens['text_muted']}; font-size: 11px;")
        form.addWidget(about)

        form.addStretch(1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(close_btn)
        form.addLayout(btn_row)

        return dlg

    def _open_settings(self):
        self.settings_dialog.exec()

    # -- Settings logic ---------------------------------------------------
    def _settings(self):
        return QSettings("Wakizashi", "RGB")

    def _load_settings(self):
        s = self._settings()
        autostart = self._read_autostart_registry()
        self.autostart_check.blockSignals(True)
        self.autostart_check.setChecked(autostart)
        self.autostart_check.blockSignals(False)

        theme = s.value("theme/mode", "dark")
        self.theme_combo.blockSignals(True)
        self.theme_combo.setCurrentIndex(0 if theme == "dark" else 1)
        self.theme_combo.blockSignals(False)
        self._set_tokens(DARK if theme == "dark" else LIGHT)
        self._restyle_all()

        self.excl_right_check.blockSignals(True)
        self.excl_right_check.setChecked(s.value("effect/exclude_right", False, type=bool))
        self.excl_right_check.blockSignals(False)

        tray = s.value("tray/minimize", False, type=bool)
        self.tray_check.blockSignals(True)
        self.tray_check.setChecked(tray)
        self.tray_check.blockSignals(False)

        self.ambi_mode_combo.blockSignals(True)
        self.ambi_mode_combo.setCurrentIndex(s.value("ambi/mode", 0, type=int))
        self.ambi_mode_combo.blockSignals(False)
        self.ambi_cols_spin.blockSignals(True)
        self.ambi_cols_spin.setValue(s.value("ambi/cols", 8, type=int))
        self.ambi_cols_spin.blockSignals(False)
        self.ambi_rows_spin.blockSignals(True)
        self.ambi_rows_spin.setValue(s.value("ambi/rows", 4, type=int))
        self.ambi_rows_spin.blockSignals(False)
        self.ambi_hz_spin.blockSignals(True)
        self.ambi_hz_spin.setValue(s.value("ambi/hz", 25, type=int))
        self.ambi_hz_spin.blockSignals(False)
        self.ambi_smooth_slider.blockSignals(True)
        self.ambi_smooth_slider.setValue(s.value("ambi/smooth", 60, type=int))
        self.ambi_smooth_slider.blockSignals(False)
        self.ambi_sat_slider.blockSignals(True)
        self.ambi_sat_slider.setValue(s.value("ambi/sat", 30, type=int))
        self.ambi_sat_slider.blockSignals(False)
        self.ambi_bright_slider.blockSignals(True)
        self.ambi_bright_slider.setValue(s.value("ambi/bright", 130, type=int))
        self.ambi_bright_slider.blockSignals(False)
        self.ambi_dark_check.blockSignals(True)
        self.ambi_dark_check.setChecked(s.value("ambi/dark", False, type=bool))
        self.ambi_dark_check.blockSignals(False)
        self.screen_combo.blockSignals(True)
        self.screen_combo.setCurrentIndex(s.value("ambi/monitor", self.screen_combo.currentIndex(), type=int))
        self.screen_combo.blockSignals(False)
        self._refresh_audio_devices()
        self.audio_bands_spin.blockSignals(True)
        self.audio_bands_spin.setValue(s.value("audio/bands", 16, type=int))
        self.audio_bands_spin.blockSignals(False)
        self.audio_scale_combo.blockSignals(True)
        self.audio_scale_combo.setCurrentIndex(s.value("audio/scale", 0, type=int))
        self.audio_scale_combo.blockSignals(False)
        self.audio_gain_slider.blockSignals(True)
        self.audio_gain_slider.setValue(s.value("audio/gain", 0, type=int))
        self.audio_gain_slider.blockSignals(False)
        self.audio_floor_spin.blockSignals(True)
        self.audio_floor_spin.setValue(s.value("audio/floor", -80, type=int))
        self.audio_floor_spin.blockSignals(False)
        self.audio_attack_slider.blockSignals(True)
        self.audio_attack_slider.setValue(s.value("audio/attack", 10, type=int))
        self.audio_attack_slider.blockSignals(False)
        self.audio_release_slider.blockSignals(True)
        self.audio_release_slider.setValue(s.value("audio/release", 150, type=int))
        self.audio_release_slider.blockSignals(False)
        self.audio_color_combo.blockSignals(True)
        self.audio_color_combo.setCurrentIndex(s.value("audio/color", 0, type=int))
        self.audio_color_combo.blockSignals(False)
        self.audio_mono_check.blockSignals(True)
        self.audio_mono_check.setChecked(s.value("audio/mono", True, type=bool))
        self.audio_mono_check.blockSignals(False)
        stored_device = s.value("audio/device", None)
        if stored_device is not None:
            device_index = self.audio_device_combo.findData(stored_device)
            if device_index >= 0:
                self.audio_device_combo.blockSignals(True)
                self.audio_device_combo.setCurrentIndex(device_index)
                self.audio_device_combo.blockSignals(False)
        self._rebuild_led_zones()

    def _connect_setting_persist(self, widget):
        if isinstance(widget, QSpinBox):
            widget.valueChanged.connect(self._save_settings)
        elif isinstance(widget, QComboBox):
            widget.currentIndexChanged.connect(self._save_settings)
        elif isinstance(widget, QCheckBox):
            widget.toggled.connect(self._save_settings)
        elif isinstance(widget, QSlider):
            widget.valueChanged.connect(self._save_settings)

    def _save_settings(self, *_):
        s = self._settings()
        s.setValue("theme/mode", "dark" if self.theme_combo.currentIndex() == 0 else "light")
        s.setValue("tray/minimize", self.tray_check.isChecked())
        s.setValue("ambi/mode", self.ambi_mode_combo.currentIndex())
        s.setValue("ambi/cols", self.ambi_cols_spin.value())
        s.setValue("ambi/rows", self.ambi_rows_spin.value())
        s.setValue("ambi/hz", self.ambi_hz_spin.value())
        s.setValue("ambi/smooth", self.ambi_smooth_slider.value())
        s.setValue("ambi/sat", self.ambi_sat_slider.value())
        s.setValue("ambi/bright", self.ambi_bright_slider.value())
        s.setValue("ambi/dark", self.ambi_dark_check.isChecked())
        s.setValue("ambi/monitor", self.screen_combo.currentIndex())
        s.setValue("effect/exclude_right", self.excl_right_check.isChecked())
        s.setValue("audio/device", self.audio_device_combo.currentData())
        s.setValue("audio/bands", self.audio_bands_spin.value())
        s.setValue("audio/scale", self.audio_scale_combo.currentIndex())
        s.setValue("audio/gain", self.audio_gain_slider.value())
        s.setValue("audio/floor", self.audio_floor_spin.value())
        s.setValue("audio/attack", self.audio_attack_slider.value())
        s.setValue("audio/release", self.audio_release_slider.value())
        s.setValue("audio/color", self.audio_color_combo.currentIndex())
        s.setValue("audio/mono", self.audio_mono_check.isChecked())

    def _reset_settings(self):
        s = self._settings()
        s.clear()
        self.autostart_check.blockSignals(True)
        self.autostart_check.setChecked(False)
        self.autostart_check.blockSignals(False)
        self._set_autostart(False)
        self.theme_combo.blockSignals(True)
        self.theme_combo.setCurrentIndex(0)
        self.theme_combo.blockSignals(False)
        self._apply_theme(0)
        self.tray_check.blockSignals(True)
        self.tray_check.setChecked(False)
        self.tray_check.blockSignals(False)
        self.ambi_mode_combo.blockSignals(True)
        self.ambi_mode_combo.setCurrentIndex(0)
        self.ambi_mode_combo.blockSignals(False)
        for widget, value in ((self.ambi_cols_spin, 8), (self.ambi_rows_spin, 4),
                              (self.ambi_hz_spin, 25), (self.ambi_smooth_slider, 60),
                              (self.ambi_sat_slider, 30), (self.ambi_bright_slider, 130)):
            widget.blockSignals(True)
            widget.setValue(value)
            widget.blockSignals(False)
        self.ambi_dark_check.blockSignals(True)
        self.ambi_dark_check.setChecked(False)
        self.ambi_dark_check.blockSignals(False)
        self.excl_right_check.blockSignals(True)
        self.excl_right_check.setChecked(False)
        self.excl_right_check.blockSignals(False)
        for widget, value in ((self.audio_bands_spin, 16),
                              (self.audio_gain_slider, 0),
                              (self.audio_floor_spin, -80),
                              (self.audio_attack_slider, 10),
                              (self.audio_release_slider, 150)):
            widget.blockSignals(True)
            widget.setValue(value)
            widget.blockSignals(False)
        for widget, value in ((self.audio_scale_combo, 0),
                              (self.audio_color_combo, 0)):
            widget.blockSignals(True)
            widget.setCurrentIndex(value)
            widget.blockSignals(False)
        self.audio_mono_check.blockSignals(True)
        self.audio_mono_check.setChecked(True)
        self.audio_mono_check.blockSignals(False)
        self._refresh_audio_devices()
        self._rebuild_led_zones()
        self._save_settings()

    def _set_tokens(self, tokens):
        self._tokens = tokens
        QApplication.instance().setStyleSheet(build_qss(tokens))
        self.aurora.set_tokens(tokens)
        self.header.set_tokens(tokens)
        self.background.set_tokens(tokens)
        self.status_label.set_tokens(tokens)
        self.rail.set_tokens(tokens)
        self.presets_panel.set_tokens(tokens)
        self.dock.set_tokens(tokens)
        self._settings_panel.set_tokens(tokens)
        self.spectrum_widget.set_tokens(tokens)

    def _apply_theme(self, index):
        self._set_tokens(DARK if index == 0 else LIGHT)
        self._restyle_all()
        self._apply_dark_titlebar(index == 0)
        self._save_settings()

    def _apply_dark_titlebar(self, dark):
        """Match the Windows title bar to the dark Command Deck shell."""
        try:
            hwnd = int(self.winId())
            value = ctypes.c_int(1 if dark else 0)
            for attr in (20, 19):
                result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(value), ctypes.sizeof(value))
                if result == 0:
                    break
        except (AttributeError, OSError):
            pass

    def _read_autostart_registry(self):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
            winreg.QueryValueEx(key, "WakizashiRGB")
            winreg.CloseKey(key)
            return True
        except OSError:
            return False

    def _set_autostart(self, enable):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
            if enable:
                import os
                exe_path = sys.executable
                if getattr(sys, 'frozen', False):
                    exe_path = sys.executable
                winreg.SetValueEx(key, "WakizashiRGB", 0, winreg.REG_SZ, f'"{exe_path}"')
            else:
                try:
                    winreg.DeleteValue(key, "WakizashiRGB")
                except OSError:
                    pass
            winreg.CloseKey(key)
        except OSError:
            pass

    def _toggle_autostart(self, checked):
        self._set_autostart(checked)

    def _build_keys(self):
        self.led_to_name = {}
        for _row, name, x, y, w, h, _seq in KEY_MAP:
            kx = x + X_OFFSET
            btn = KeyButton(name, self.background)
            btn.setGeometry(kx, y, w, h)
            btn.setStyleSheet(keycap_base_qss(self._tokens))
            led = resolve_led_index(name)
            btn.setProperty("key_name", name)
            btn.setProperty("led_index", led)
            if led is not None:
                btn.setToolTip(f"{name} — LED {led} (ПКМ — очистить)")
                self.led_pos[led] = (kx + w // 2, y + h // 2)
                self.led_to_name[led] = name
            btn.clicked.connect(lambda _checked=False, b=btn: self._on_key_clicked(b))
            btn.rightClicked.connect(lambda b=btn: self._clear_key(b))
            self.key_buttons[name] = btn
        self._excluded_leds = {
            led for led in (resolve_led_index(n) for n in RIGHT_SECTION_KEYS)
            if led is not None
        }
        self._rebuild_led_zones()

    # -- Device ----------------------------------------------------------
    def _connect_device(self):
        try:
            self.keyboard = kb.Keyboard()
            model = self.keyboard.get_model_id()
            name = kb.MODEL_NAMES.get(model, "неизвестная модель")
            self.status_label.setText(f"Подключено: {name}")
            self.status_label.set_ok(True)
            return True
        except kb.KbError as exc:
            self.keyboard = None
            self.status_label.setText(f"Не подключено ({exc})")
            self.status_label.set_ok(False)
            return False

    def _rescan(self):
        """Close any stale handle and look for the keyboard again."""
        if self.keyboard is not None:
            self.keyboard.close()
            self.keyboard = None
        self.timer.start(int(kb.KEEPALIVE_S * 1000))
        self.effect_timer.stop()
        self._stop_ambi_worker()
        self._stop_audio_worker()
        self._connect_device()

    # -- Painting / selection -------------------------------------------
    def _style_for(self, name):
        painted = name in self.painted
        selected = name in self.selected
        if painted:
            r, g, b = self.painted[name]
            return keycap_qss(self._tokens, r, g, b, selected)
        if selected:
            return keycap_selected_qss(self._tokens)
        return keycap_base_qss(self._tokens)

    def _apply_style(self, name):
        btn = self.key_buttons.get(name)
        if btn is not None:
            btn.setStyleSheet(self._style_for(name))

    def _restyle_all(self):
        for name in self.key_buttons:
            self._apply_style(name)

    def _on_key_clicked(self, btn):
        if self.keyboard is None:
            self.status_label.setText("Не подключено")
            return
        name = btn.property("key_name")
        if self.selection_mode:
            self._toggle_selection(name)
            return
        if self.current_color is None:
            color = self._pick_color()
            if color is None:
                return
            self._arm_color(*color)
        self._paint_single(name)

    def _paint_single(self, name):
        self._stop_effect()
        self.painted[name] = self.current_color
        self._apply_style(name)
        self._send()

    def _clear_key(self, btn):
        """Right-click: turn the key off and revert its button style."""
        name = btn.property("key_name")
        self.painted.pop(name, None)
        self.selected.discard(name)
        self._apply_style(name)
        self._send()

    def _toggle_selection(self, name):
        if name in self.selected:
            self.selected.discard(name)
        else:
            self.selected.add(name)
        self._apply_style(name)

    def _set_selection_mode(self, checked):
        self.selection_mode = checked
        if not checked:
            self._deselect_all()

    def _select_all(self):
        self.selected = set(self.key_buttons.keys())
        self._restyle_all()

    def _deselect_all(self):
        self.selected.clear()
        self._restyle_all()

    def _apply_to_selection(self):
        if self.keyboard is None:
            self.status_label.setText("Не подключено")
            return
        if self.current_color is None:
            color = self._pick_color()
            if color is None:
                return
            self._arm_color(*color)
        self._stop_effect()
        for name in self.selected:
            self.painted[name] = self.current_color
            self._apply_style(name)
        self._send()

    def _clear_all(self):
        self._stop_effect()
        self.painted.clear()
        self.selected.clear()
        self._restyle_all()
        self.background.set_ambient(None)
        if self.keyboard is not None:
            try:
                self.keyboard.set_per_key({})
            except (kb.KbError, OSError):
                pass

    def _apply_game_preset(self, name):
        if self.keyboard is None:
            self.status_label.setText("Не подключено")
            return
        if self.active_effect != "Игра":
            self._stop_effect()
        if self.effect_combo.currentText() != "Игра":
            self.effect_combo.setCurrentText("Игра")
        preset = GAME_PRESETS[name]
        color = preset["color"]
        self.painted.clear()
        for key in preset["keys"]:
            self.painted[key] = color
        self.current_color = color
        self.swatch.setStyleSheet(self._swatch_style(*color, active=True))
        self.hex_label.setText("#%02X%02X%02X" % color)
        self.header.set_color(color)
        self.background.set_ambient(color)
        for btn, preset_color in self.palette_buttons:
            btn.setStyleSheet(self._swatch_style(*preset_color,
                                                 active=preset_color == color))
        self._restyle_all()
        self._send()

    # -- Color -----------------------------------------------------------
    def _pick_color(self):
        current = QColor(*(self.current_color or (255, 255, 255)))
        color = QColorDialog.getColor(current, self, "Выберите цвет")
        if color.isValid():
            return color.red(), color.green(), color.blue()
        return None

    def _custom_color(self):
        color = self._pick_color()
        if color is not None:
            self._arm_color(*color)

    def _arm_color(self, r, g, b):
        self.current_color = (r, g, b)
        self.swatch.setStyleSheet(self._swatch_style(r, g, b, active=True))
        self.hex_label.setText("#%02X%02X%02X" % (r, g, b))
        self.header.set_color(self.current_color)
        self.background.set_ambient(self.current_color)
        for btn, color in self.palette_buttons:
            btn.setStyleSheet(self._swatch_style(*color, active=color == self.current_color))
        if self.selection_mode and self.selected:
            self._apply_to_selection()

    # -- Sending ---------------------------------------------------------
    def _send(self):
        if self.keyboard is None:
            return
        try:
            mapped = {}
            for name, color in self.painted.items():
                key = UI_ALIASES.get(name.strip().upper(), name.strip().upper())
                mapped[key] = color
            self.keyboard.set_per_key(mapped)
        except (kb.KbError, OSError):
            # Wireless link may drop temporarily; keep retrying, don't stop.
            self.status_label.setText("Устройство недоступно")
            self.status_label.set_ok(False)

    # -- Effects ---------------------------------------------------------
    def _pick_effect_color(self):
        color = QColorDialog.getColor(QColor(*self.effect_color), self, "Цвет эффекта")
        if color.isValid():
            self.effect_color = (color.red(), color.green(), color.blue())
            self.effect_color_swatch.setStyleSheet(
                self._swatch_style(color.red(), color.green(), color.blue()))

    def _toggle_rainbow(self, checked):
        self._rainbow_mode = checked

    def _poll_keys(self):
        current = set()
        for vk in range(8, 256):
            if ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000:
                current.add(vk)
        new_presses = current - self._prev_keys
        for vk in new_presses:
            name = VK_TO_NAME.get(vk)
            if name is None:
                continue
            if name in self.key_buttons:
                btn = self.key_buttons[name]
                r = btn.geometry()
                x, y = r.x() + r.width() // 2, r.y() + r.height() // 2
                hue = (self._frame * 7 + x * 0.3) % 360 if self._rainbow_mode else None
                self._ripples.append((x, y, self._frame, hue))
        self._prev_keys = current

    def _color_for_led(self, led_index):
        if self._rainbow_mode:
            x = self.led_pos.get(led_index, (0, 0))[0]
            hue = (x * 0.35 + self._frame * 0.8) % 360
            return hsv_to_rgb(hue, 1.0, 1.0)
        return self.effect_color

    # -- Ambilight zones / capture worker ---------------------------------
    def _effective_ambi_grid(self):
        cols = int(self.ambi_cols_spin.value())
        if self.ambi_mode_combo.currentIndex() == 1:   # columns only
            return cols, 1
        return cols, int(self.ambi_rows_spin.value())

    def _active_led_pos(self):
        """LED positions the ambilight may use.

        When the right section is excluded from effects, its LEDs are left out
        of the bounding box so the screen grid spreads across the remaining
        keys instead of reserving space for the dark section.
        """
        if self.excl_right_check.isChecked() and self._excluded_leds:
            return {led: pos for led, pos in self.led_pos.items()
                    if led not in self._excluded_leds}
        return self.led_pos

    def _rebuild_led_zones(self, *_):
        """Assign every active LED to a screen zone based on its board position."""
        self._ambi_cols, self._ambi_rows = self._effective_ambi_grid()
        self._ambi_grid = None
        self._ambi_current = [(0, 0, 0)] * (self._ambi_cols * self._ambi_rows)
        self.led_zone = {}
        source = self._active_led_pos()
        if not source:
            return
        xs = [pos[0] for pos in source.values()]
        ys = [pos[1] for pos in source.values()]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        span_x = max(1, max_x - min_x)
        span_y = max(1, max_y - min_y)
        cols, rows = self._ambi_cols, self._ambi_rows
        for led, (x, y) in source.items():
            cx = int((x - min_x) / span_x * cols)
            cy = int((y - min_y) / span_y * rows)
            cx = 0 if cx < 0 else (cols - 1 if cx >= cols else cx)
            cy = 0 if cy < 0 else (rows - 1 if cy >= rows else cy)
            self.led_zone[led] = cy * cols + cx

    def _current_monitor(self):
        """Match the selected Qt screen to an mss monitor (physical pixels)."""
        monitors = self._amba_monitors
        if not monitors:
            return None
        idx = self.screen_combo.currentIndex()
        if 0 <= idx < len(self.screens):
            screen = self.screens[idx]
            geo = screen.geometry()
            dpr = screen.devicePixelRatio() or 1.0
            want = (int(geo.x() * dpr), int(geo.y() * dpr),
                    int(geo.width() * dpr), int(geo.height() * dpr))
            for mon in monitors[1:]:
                if (mon["left"], mon["top"], mon["width"], mon["height"]) == want:
                    return mon
            if idx + 1 < len(monitors):
                return monitors[idx + 1]
        return monitors[1] if len(monitors) > 1 else monitors[0]

    def _sync_ambi_worker(self, *_):
        worker = self._ambi_worker
        if worker is None:
            return
        worker.cols = self._ambi_cols
        worker.rows = self._ambi_rows
        worker.hz = float(self.ambi_hz_spin.value())
        worker.drop_dark = self.ambi_dark_check.isChecked()

    def _ensure_ambi_worker(self):
        if _mss is None:
            return False
        monitor = self._current_monitor()
        if monitor is None:
            return False
        if self._ambi_worker is None:
            self._ambi_worker = AmbilightWorker(self)
            self._ambi_worker.gridReady.connect(self._on_ambi_grid)
        self._sync_ambi_worker()
        self._ambi_worker.monitor = monitor
        if not self._ambi_worker.isRunning():
            self._ambi_worker.start()
        return True

    def _stop_ambi_worker(self):
        worker = self._ambi_worker
        if worker is not None and worker.isRunning():
            worker.requestInterruption()
            worker.wait(2000)

    def _on_ambi_grid(self, colors):
        self._ambi_grid = colors
        if len(self._ambi_current) != len(colors):
            self._ambi_current = list(colors)

    def _legacy_ambi(self, n):
        """Fallback when mss is unavailable: whole-screen average via QScreen."""
        now = time.monotonic()
        if now - self._ambi_last >= 0.15:
            self._ambi_last = now
            self._ambi_target = self._sample_screen()
        target = self._ambi_target
        k = self.ambi_smooth_slider.value() / 100.0
        cur = self._ambi_single
        cur = tuple(int(cur[i] + (target[i] - cur[i]) * k) for i in range(3))
        self._ambi_single = cur
        graded = grade_zone(cur, self.ambi_sat_slider.value() / 100.0,
                            self.ambi_bright_slider.value() / 100.0)
        return [graded] * n

    # -- Audio source / analyzer ------------------------------------------
    def _refresh_audio_devices(self):
        combo = self.audio_device_combo
        current = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        devices = _audio.loopback_devices() if _audio is not None else []
        for device_id, name in devices:
            combo.addItem(name, device_id)
        index = combo.findData(current) if current is not None else -1
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)
        self._audio_settings_changed()

    def _audio_settings_changed(self, *_):
        self._sync_audio_worker()

    def _sync_audio_worker(self):
        worker = self._audio_worker
        if worker is None:
            return
        worker.device_id = self.audio_device_combo.currentData()
        worker.bands = int(self.audio_bands_spin.value())
        worker.scale = ("log", "mel", "linear")[
            max(0, min(2, self.audio_scale_combo.currentIndex()))]
        worker.gain_db = float(self.audio_gain_slider.value())
        worker.floor_db = float(self.audio_floor_spin.value())
        worker.ceil_db = 0.0
        worker.attack = self.audio_attack_slider.value() / 1000.0
        worker.release = self.audio_release_slider.value() / 1000.0
        worker.mono = self.audio_mono_check.isChecked()

    def _ensure_audio_worker(self):
        if _audio is None or not _audio.AVAILABLE:
            return False
        if self._audio_worker is None:
            self._audio_worker = _audio.AudioWorker(self)
            self._audio_worker.audioReady.connect(self._on_audio_data)
        self._sync_audio_worker()
        if not self._audio_worker.isRunning():
            self._audio_worker.start()
        return True

    def _stop_audio_worker(self):
        worker = self._audio_worker
        if worker is not None and worker.isRunning():
            worker.requestInterruption()
            worker.wait(2000)

    def _on_audio_data(self, data):
        self._audio_data = data
        self._audio_last = time.monotonic()
        widget = getattr(self, "spectrum_widget", None)
        if widget is not None:
            widget.set_data(data.get("bands", ()), data.get("wave", ()),
                            data.get("level", 0.0), data.get("peak", 0.0))

    def _ensure_audio_map(self, band_count):
        source = self._active_led_pos()
        key = (band_count, self.excl_right_check.isChecked(), len(source))
        if self._audio_map_key == key:
            return
        self._led_band = {}
        self._led_xnorm = {}
        self._led_ynorm = {}
        if source:
            xs = [pos[0] for pos in source.values()]
            ys = [pos[1] for pos in source.values()]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            span_x = max(1, max_x - min_x)
            span_y = max(1, max_y - min_y)
            count = max(1, band_count)
            for led, (x, y) in source.items():
                xn = (x - min_x) / span_x
                band = int(xn * count)
                band = 0 if band < 0 else (count - 1 if band >= count else band)
                self._led_band[led] = band
                self._led_xnorm[led] = xn
                self._led_ynorm[led] = (y - min_y) / span_y
        self._audio_map_key = key

    def _audio_color(self, band, band_count, level):
        mode = self.audio_color_combo.currentIndex()
        if self._rainbow_mode or mode == 1:
            hue = (band / max(1, band_count - 1)) * 300.0
            return hsv_to_rgb(hue, 1.0, 1.0)
        if mode == 0:
            return minimeters_colormap(level)
        return self.effect_color

    def _compute_audio(self, effect, n):
        data = self._audio_data
        bands = data.get("bands") or ()
        if not bands:
            return [(0, 0, 0)] * n
        count = len(bands)
        self._ensure_audio_map(count)
        if effect == "Осциллограф":
            return self._render_wave(data.get("wave") or (), n)
        if effect == "Аудио-пульс":
            level = float(data.get("level", 0.0))
            peak = float(data.get("peak", 0.0))
            value = 0.12 + 0.88 * max(level, peak * 0.6)
            if self._rainbow_mode:
                return [tuple(int(c * value) for c in self._color_for_led(led))
                        for led in range(n)]
            r0, g0, b0 = self.effect_color
            return [(int(r0 * value), int(g0 * value), int(b0 * value))] * n
        if effect == "Спектр":
            return self._render_spectrum_area(bands, n, count)
        result = [(0, 0, 0)] * n
        for led in range(n):
            band = self._led_band.get(led)
            if band is None:
                continue
            level = max(0.0, min(1.0, float(bands[band])))
            if level <= 0.0:
                continue
            height = 1.0 - self._led_ynorm.get(led, 0.0)
            if level < height:
                continue
            cr, cg, cb = self._audio_color(band, count, level)
            value = level ** 0.85
            result[led] = (int(cr * value), int(cg * value), int(cb * value))
        return result

    def _render_spectrum_area(self, bands, n, count):
        """MiniMeters-style filled spectrum: louder bands are brighter, the
        lower rows fill first and the wave edge gets a light contour."""
        result = [(0, 0, 0)] * n
        minimeters = (self.audio_color_combo.currentIndex() == 0
                      and not self._rainbow_mode)
        for led in range(n):
            band = self._led_band.get(led)
            if band is None:
                continue
            level = max(0.0, min(1.0, float(bands[band])))
            if level <= 0.0:
                continue
            height = 1.0 - self._led_ynorm.get(led, 0.0)
            if height > level:
                continue
            rel = min(1.0, height / level)
            if minimeters:
                cr, cg, cb = minimeters_colormap(rel)
            else:
                cr, cg, cb = self._audio_color(band, count, level)
            value = level ** 0.75
            if rel > 0.82:
                blend = min(1.0, (rel - 0.82) / 0.18) * 0.7
                cr = int(cr + (235 - cr) * blend)
                cg = int(cg + (245 - cg) * blend)
                cb = int(cb + (255 - cb) * blend)
                value = min(1.0, value + 0.2 * blend)
            result[led] = (int(cr * value), int(cg * value), int(cb * value))
        return result

    def _render_wave(self, wave, n):
        if len(wave) < 2:
            return [(0, 0, 0)] * n
        result = [(0, 0, 0)] * n
        for led in range(n):
            xn = self._led_xnorm.get(led)
            if xn is None:
                continue
            index = int(xn * (len(wave) - 1))
            value = min(1.0, abs(float(wave[index])) * 1.6)
            if value <= 0.0:
                continue
            if self._rainbow_mode:
                cr, cg, cb = hsv_to_rgb((xn * 300.0 + self._frame * 0.6) % 360,
                                        1.0, 1.0)
            else:
                cr, cg, cb = self.effect_color
            result[led] = (int(cr * value), int(cg * value), int(cb * value))
        return result

    def _on_effect_changed(self, text):
        self.ambi_widget.setVisible(text == "Амбилайт")
        self.audio_widget.setVisible(text in AUDIO_EFFECTS)
        if text != "Амбилайт":
            self._stop_ambi_worker()
        if text not in AUDIO_EFFECTS:
            self._stop_audio_worker()
        else:
            self.spectrum_widget.set_mode(AUDIO_EFFECT_MODES.get(text, "bars"))
        self._ripples.clear()
        self._prev_keys.clear()
        if self._preview_only:
            self.active_effect = text
            self._frame = 0.0
            self._elapsed = 0.0
            self._last_tick = None
            self._sparkle_keys.clear()
            self._snake_path = None
        self._update_effect_params()

    def _start_effect(self):
        if self.keyboard is None:
            self.status_label.setText("Не подключено")
            return
        effect = self.effect_combo.currentText()
        if effect == "Игра":
            if not self.painted:
                self.status_label.setText("Сначала выберите игру из пресетов")
                return
        if effect in AUDIO_EFFECTS and not self._ensure_audio_worker():
            self.status_label.setText(
                "Аудио недоступно: установите soundcard и numpy")
            self.status_label.set_ok(False)
            return
        self._preview_only = False
        self.preview_check.blockSignals(True)
        self.preview_check.setChecked(False)
        self.preview_check.blockSignals(False)
        self.active_effect = effect
        self._frame = 0.0
        self._elapsed = 0.0
        self._last_tick = None
        self._sparkle_keys.clear()
        self._snake_path = None
        self._ripples.clear()
        self._prev_keys.clear()
        if effect == "Амбилайт":
            self._ensure_ambi_worker()
        self.effect_timer.start()

    def _stop_effect(self):
        if self.active_effect is None:
            return
        self.active_effect = None
        self._preview_only = False
        self._last_tick = None
        self.preview_check.blockSignals(True)
        self.preview_check.setChecked(False)
        self.preview_check.blockSignals(False)
        self.effect_timer.stop()
        self._stop_ambi_worker()
        self._stop_audio_worker()
        self._restyle_all()

    def _toggle_preview(self, checked):
        if checked:
            effect = self.effect_combo.currentText()
            if effect == "Игра" and not self.painted:
                self.preview_check.blockSignals(True)
                self.preview_check.setChecked(False)
                self.preview_check.blockSignals(False)
                self.status_label.setText("Сначала выберите игру из пресетов")
                return
            self._stop_effect()
            self._preview_only = True
            self.active_effect = effect
            self._frame = 0.0
            self._elapsed = 0.0
            self._last_tick = None
            self._sparkle_keys.clear()
            self._snake_path = None
            self._ripples.clear()
            self._prev_keys.clear()
            if effect == "Амбилайт":
                self._ensure_ambi_worker()
            elif effect in AUDIO_EFFECTS and not self._ensure_audio_worker():
                self.preview_check.blockSignals(True)
                self.preview_check.setChecked(False)
                self.preview_check.blockSignals(False)
                self.active_effect = None
                self._preview_only = False
                self.effect_timer.stop()
                self.status_label.setText(
                    "Аудио недоступно: установите soundcard и numpy")
                self.status_label.set_ok(False)
                return
            self.effect_timer.start()
        else:
            self._stop_effect()

    def _effect_tick(self):
        if self.active_effect is None:
            return
        now = time.monotonic()
        if self._last_tick is None:
            dt = 1.0 / FRAME_HZ
        else:
            dt = now - self._last_tick
        self._last_tick = now
        dt = max(0.0, min(0.25, dt))
        self._elapsed += dt
        self._frame = self._elapsed * FRAME_HZ
        if self.active_effect == "Амбилайт":
            self._ensure_ambi_worker()
        elif self.active_effect in AUDIO_EFFECTS:
            self._ensure_audio_worker()
        colors = self._compute_effect(dt)
        if self.excl_right_check.isChecked():
            for led in self._excluded_leds:
                if 0 <= led < len(colors):
                    colors[led] = (0, 0, 0)
        if self.keyboard is not None and not self._preview_only:
            try:
                self.keyboard.set_led_colors(colors)
            except (kb.KbError, OSError):
                self._stop_effect()
                self.status_label.setText("Устройство недоступно")
                self.status_label.set_ok(False)
                return
        if self._preview_only or self.isVisible():
            self._preview_effect(colors)

    def _preview_effect(self, colors):
        tokens = self._tokens
        for led, (r, g, b) in enumerate(colors):
            name = self.led_to_name.get(led)
            if name is None:
                continue
            btn = self.key_buttons.get(name)
            if btn is None:
                continue
            btn.setStyleSheet(keycap_qss(tokens, r, g, b))

    def _compute_effect(self, dt=None):
        effect = self.active_effect
        if self.keyboard is not None:
            n = self.keyboard.led_count
        else:
            n = kb.LAYOUTS[kb.DEFAULT_LAYOUT]["led_count"]
        t = self._elapsed
        speed = self.speed_slider.value() / 5.0
        direction = -1 if self.reverse_check.isChecked() else 1
        r0, g0, b0 = self.effect_color
        colors = [(0, 0, 0)] * n

        if effect in AUDIO_EFFECTS:
            return self._compute_audio(effect, n)
        if effect == "Статичный":
            if self._rainbow_mode:
                for idx in range(n):
                    colors[idx] = self._color_for_led(idx)
                return colors
            return [(r0, g0, b0)] * n
        if effect == "Дыхание":
            amp = 0.5 + 0.5 * math.sin(t * speed * 2.0)
            v = 0.15 + 0.85 * amp
            if self._rainbow_mode:
                for idx in range(n):
                    cr, cg, cb = self._color_for_led(idx)
                    colors[idx] = (int(cr * v), int(cg * v), int(cb * v))
                return colors
            c = (int(r0 * v), int(g0 * v), int(b0 * v))
            return [c] * n
        if effect == "Радуга":
            for idx in range(n):
                x = self.led_pos.get(idx, (0, 0))[0]
                hue = (x * 0.35 + t * 60.0 * speed * direction) % 360
                colors[idx] = hsv_to_rgb(hue, 1.0, 1.0)
            return colors
        if effect == "Волна":
            for idx in range(n):
                x = self.led_pos.get(idx, (0, 0))[0]
                wave = 0.5 + 0.5 * math.sin(x * 0.15 - t * 8.0 * speed * direction)
                v = 0.2 + 0.8 * wave
                if self._rainbow_mode:
                    cr, cg, cb = self._color_for_led(idx)
                    colors[idx] = (int(cr * v), int(cg * v), int(cb * v))
                else:
                    colors[idx] = (int(r0 * v), int(g0 * v), int(b0 * v))
            return colors
        if effect == "Амбилайт":
            grid = self._ambi_grid
            if grid is None:
                if _mss is None or not self._ensure_ambi_worker():
                    return self._legacy_ambi(n)
                return [(0, 0, 0)] * n
            if len(self._ambi_current) != len(grid):
                self._ambi_current = list(grid)
            k = self.ambi_smooth_slider.value() / 100.0
            sat = self.ambi_sat_slider.value() / 100.0
            bright = self.ambi_bright_slider.value() / 100.0
            out = []
            for i, target in enumerate(grid):
                cur = self._ambi_current[i]
                cur = tuple(int(cur[j] + (target[j] - cur[j]) * k) for j in range(3))
                self._ambi_current[i] = cur
                out.append(grade_zone(cur, sat, bright))
            if not self.led_zone:
                return [out[0]] * n
            return [out[self.led_zone.get(idx, 0) % len(out)] for idx in range(n)]
        if effect == "Игра":
            colors = [(0, 0, 0)] * n
            for name, (r, g, b) in self.painted.items():
                led = resolve_led_index(name)
                if led is not None and 0 <= led < n:
                    colors[led] = (r, g, b)
            return colors
        if effect == "Змейка":
            if self._snake_path is None:
                self._snake_path = sorted(
                    range(n),
                    key=lambda idx: (self.led_pos.get(idx, (0, 0))[1] // 36,
                                     self.led_pos.get(idx, (0, 0))[0]),
                )
            path = self._snake_path
            head = int(self._frame * speed * 3.0 * direction) % len(path)
            trail_len = min(20, len(path))
            for i in range(trail_len):
                pos = (head - i) % len(path)
                fade = max(0, 1.0 - i / trail_len)
                if self._rainbow_mode:
                    cr, cg, cb = self._color_for_led(path[pos])
                    colors[path[pos]] = (int(cr * fade), int(cg * fade), int(cb * fade))
                else:
                    colors[path[pos]] = (int(r0 * fade), int(g0 * fade), int(b0 * fade))
            return colors
        if effect == "Звёздный дождь":
            for led in list(self._sparkle_keys):
                sr, sg, sb, life = self._sparkle_keys[led]
                life -= (dt if dt is not None else 1.0 / FRAME_HZ) * 0.8
                if life <= 0:
                    del self._sparkle_keys[led]
                else:
                    self._sparkle_keys[led] = (sr, sg, sb, life)
                    colors[led] = (int(sr * life), int(sg * life), int(sb * life))
            if random.random() < speed * 0.35:
                led = random.randrange(n)
                hue = (self._frame * 25 + random.randrange(60)) % 360
                sr, sg, sb = hsv_to_rgb(hue, 1.0, 1.0)
                self._sparkle_keys[led] = (sr, sg, sb, 1.0)
            return colors
        if effect == "Цветовой цикл":
            offset = (self._frame * speed * 1.8 * direction) % 360
            for idx in range(n):
                x = self.led_pos.get(idx, (0, 0))[0]
                hue = (offset + x * 0.35) % 360
                colors[idx] = hsv_to_rgb(hue, 1.0, 1.0)
            return colors
        if effect == "Пульс":
            cx, cy = KEYBOARD_W // 2, KEYBOARD_H // 2
            ring = self._frame * 0.6 * speed
            for idx in range(n):
                x, y = self.led_pos.get(idx, (cx, cy))
                dist = math.sqrt((x - cx) ** 2 + (y - cy) ** 2)
                wave = 0.5 + 0.5 * math.sin((dist * 0.1 - ring) * direction)
                v = 0.15 + 0.85 * wave
                if self._rainbow_mode:
                    cr, cg, cb = self._color_for_led(idx)
                    colors[idx] = (int(cr * v), int(cg * v), int(cb * v))
                else:
                    colors[idx] = (int(r0 * v), int(g0 * v), int(b0 * v))
            return colors
        if effect == "Сканер":
            bar = (self._frame * speed * 3.0 * direction) % (KEYBOARD_W + 100)
            bar_width = 60
            for idx in range(n):
                x = self.led_pos.get(idx, (0, 0))[0]
                dist = abs(x - bar)
                if dist < bar_width:
                    v = 1.0 - (dist / bar_width)
                    v = v ** 1.5
                    if self._rainbow_mode:
                        cr, cg, cb = self._color_for_led(idx)
                        colors[idx] = (int(cr * v), int(cg * v), int(cb * v))
                    else:
                        colors[idx] = (int(r0 * v), int(g0 * v), int(b0 * v))
            return colors
        if effect == "Реактивный":
            self._poll_keys()
            for rx, ry, start_frame, ripple_hue in self._ripples:
                age = self._frame - start_frame
                if age > 40:
                    continue
                radius = age * 6.0 * speed
                for idx in range(n):
                    kx, ky = self.led_pos.get(idx, (0, 0))
                    dist = math.sqrt((kx - rx) ** 2 + (ky - ry) ** 2)
                    ring_width = 20.0
                    ring_dist = abs(dist - radius)
                    if ring_dist < ring_width:
                        intensity = (1.0 - ring_dist / ring_width) * (1.0 - age / 40.0)
                        if self._rainbow_mode and ripple_hue is not None:
                            key_hue = (ripple_hue + dist * 0.2) % 360
                            cr, cg, cb = hsv_to_rgb(key_hue, 1.0, 1.0)
                        else:
                            cr, cg, cb = r0, g0, b0
                        er, eg, eb = colors[idx]
                        colors[idx] = (min(255, er + int(cr * intensity)),
                                       min(255, eg + int(cg * intensity)),
                                       min(255, eb + int(cb * intensity)))
            self._ripples = [(rx, ry, s, h) for rx, ry, s, h in self._ripples
                             if self._frame - s <= 40]
            return colors
        return colors

    def _sample_screen(self):
        """Average colour of the selected screen (1x1 downsample)."""
        try:
            idx = self.screen_combo.currentIndex()
            screen = self.screens[idx] if 0 <= idx < len(self.screens) else None
            if screen is None:
                return self._ambi_target
            pixmap = screen.grabWindow(0)
            small = pixmap.scaled(
                1, 1,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
            color = small.toImage().pixelColor(0, 0)
            return (color.red(), color.green(), color.blue())
        except Exception:
            return self._ambi_target

    # -- Keepalive -------------------------------------------------------
    def _keepalive(self):
        if self.keyboard is None:
            return
        self._tick += 1
        # Re-arming direct mode mid-effect causes a visible flash, so only do it
        # while nothing is streaming.
        if self._tick % 25 == 0 and self.active_effect is None:
            try:
                self.keyboard.enable_direct_mode()
            except Exception:
                pass
        if self.painted and self.active_effect is None:
            self._send()

    # -- Tray ------------------------------------------------------------
    def _make_tray_icon(self):
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setBrush(QColor(77, 158, 255))
        painter.setPen(QColor(10, 15, 28))
        painter.drawEllipse(2, 2, 28, 28)
        painter.end()
        return QIcon(pixmap)

    def _setup_tray(self):
        self.tray = QSystemTrayIcon(self._make_tray_icon(), self)
        self.tray.setToolTip("Wakizashi V2 — RGB Paint")
        menu = QMenu()
        act_show = menu.addAction("Показать")
        act_show.triggered.connect(self._restore_from_tray)
        menu.addSeparator()
        act_quit = menu.addAction("Выход")
        act_quit.triggered.connect(self._quit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _restore_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._restore_from_tray()

    def _quit_app(self):
        self._force_close = True
        self.tray.hide()
        self.close()

    def eventFilter(self, obj, event):
        if obj is self.background and self.selection_mode:
            etype = event.type()
            if etype == event.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._sel_origin = event.pos()
                self._rubber_band.setGeometry(QRect(self._sel_origin, QSize()))
                self._rubber_band.show()
                return True
            if etype == event.Type.MouseMove and self._rubber_band.isVisible():
                self._rubber_band.setGeometry(
                    QRect(self._sel_origin, event.pos()).normalized())
                return True
            if etype == event.Type.MouseButtonRelease and self._rubber_band.isVisible():
                self._rubber_band.hide()
                sel_rect = QRect(self._sel_origin, event.pos()).normalized()
                if sel_rect.width() > 4 and sel_rect.height() > 4:
                    if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                        self.selected.clear()
                    for name, btn in self.key_buttons.items():
                        if sel_rect.intersects(btn.geometry()):
                            self.selected.add(name)
                    self._restyle_all()
                self._sel_origin = None
                return True
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        if self.tray.isVisible() and not self._force_close:
            if self.tray_check.isChecked():
                event.ignore()
                self.hide()
                return
            reply = QMessageBox.question(
                self,
                "Закрытие",
                "Свернуть в трей?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                event.ignore()
                self.hide()
                return
            self.tray.hide()
        self.timer.stop()
        self.effect_timer.stop()
        self._stop_ambi_worker()
        self._stop_audio_worker()
        if self.keyboard is not None:
            self.keyboard.close()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(build_qss(DARK))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
