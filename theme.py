"""Design tokens and stylesheet builders for the Wakizashi RGB UI.

One shared QSS template is rendered from a token dict, so the dark and the
"frosted light" themes stay structurally identical and differ only by colour.
Custom-painted widgets (see widgets.py) pull the same tokens, which keeps the
glass panels, the aurora background and the keycaps visually in sync.
"""

import re
from string import Template

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QLinearGradient, QPainterPath, QPen


# --------------------------------------------------------------------------
# Token palettes
# --------------------------------------------------------------------------
DARK = {
    "name": "dark",
    "bg_base": "#06070B",
    "grad_top": "#0B0E16",
    "grad_bot": "#05060A",
    "glow1": "#123B6B",
    "glow2": "#0B4F6C",
    "glow3": "#0E2A47",
    "glass_fill": "rgba(255,255,255,0.04)",
    "glass_fill_strong": "rgba(255,255,255,0.07)",
    "glass_border": "rgba(255,255,255,0.10)",
    "glass_highlight": "rgba(255,255,255,0.22)",
    "panel": "#0E1118",
    "text": "#E7ECF5",
    "text_dim": "#A6B0C2",
    "text_muted": "#7C879B",
    "accent": "#5CC8FF",
    "accent_hi": "#8FDBFF",
    "accent_dim": "#1F6E96",
    "accent_text": "#04121A",
    "danger": "#FF5C7A",
    "ok": "#3BE38B",
    "btn_bg": "rgba(255,255,255,0.05)",
    "btn_hover_bg": "rgba(92,200,255,0.14)",
    "input_bg": "rgba(255,255,255,0.045)",
    "input_border": "rgba(255,255,255,0.12)",
    "tab_active_bg": "rgba(92,200,255,0.14)",
    "key_top": "#232A36",
    "key_mid": "#1A202B",
    "key_bot": "#12161E",
    "key_border": "#333C4C",
    "key_border_bottom": "#0A0D12",
    "key_text": "#B9C3D4",
    "scroll_bg": "rgba(255,255,255,0.035)",
    "scroll_handle": "rgba(255,255,255,0.16)",
}

LIGHT = {
    "name": "light",
    "bg_base": "#EEF3FA",
    "grad_top": "#F6F9FE",
    "grad_bot": "#D8E3F2",
    "glow1": "#93C5FD",
    "glow2": "#A5B4FC",
    "glow3": "#BAE6FD",
    "glass_fill": "rgba(255,255,255,0.62)",
    "glass_fill_strong": "rgba(255,255,255,0.88)",
    "glass_border": "rgba(148,163,184,0.45)",
    "glass_highlight": "rgba(255,255,255,0.95)",
    "panel": "#FFFFFF",
    "text": "#1E293B",
    "text_dim": "#64748B",
    "text_muted": "#94A3B8",
    "accent": "#2563EB",
    "accent_hi": "#3B82F6",
    "accent_dim": "#1D4ED8",
    "accent_text": "#FFFFFF",
    "danger": "#E11D48",
    "ok": "#16A34A",
    "btn_bg": "rgba(255,255,255,0.72)",
    "btn_hover_bg": "rgba(37,99,235,0.12)",
    "input_bg": "rgba(255,255,255,0.80)",
    "input_border": "rgba(148,163,184,0.50)",
    "tab_active_bg": "rgba(37,99,235,0.10)",
    "key_top": "#FFFFFF",
    "key_mid": "#EEF2F8",
    "key_bot": "#D9E1EE",
    "key_border": "#BCC8DA",
    "key_border_bottom": "#AAB7CC",
    "key_text": "#475569",
    "scroll_bg": "rgba(148,163,184,0.15)",
    "scroll_handle": "rgba(100,116,139,0.40)",
}


def qcolor(value):
    """QColor from '#RRGGBB' or a CSS 'rgb()/rgba()' string."""
    if isinstance(value, QColor):
        return value
    m = re.match(r"rgba?\(([^)]+)\)", str(value).strip())
    if m:
        parts = [p.strip() for p in m.group(1).split(",")]
        r, g, b = (int(float(parts[i])) for i in range(3))
        a = int(float(parts[3]) * 255) if len(parts) > 3 else 255
        return QColor(r, g, b, a)
    return QColor(value)


# --------------------------------------------------------------------------
# Global application stylesheet (single template, themed by tokens)
# --------------------------------------------------------------------------
_QSS_TEMPLATE = Template("""
QMainWindow { background-color: $bg_base; }
QWidget { color: $text; font-family: "Inter", "Segoe UI", "Helvetica Neue", Arial, sans-serif; font-size: 12px; }
QToolTip { background-color: $panel; color: $text; border: 1px solid $glass_border; border-radius: 6px; padding: 4px 8px; }

QTabWidget::pane { border: 1px solid $glass_border; border-radius: 12px; background-color: $glass_fill; top: -1px; }
QTabWidget::tab-bar { left: 8px; }
QTabBar { qproperty-drawBase: 0; background: transparent; }
QTabBar::tab { background: transparent; border: 1px solid transparent; border-radius: 8px; padding: 6px 18px; margin-right: 2px; color: $text_dim; font-weight: 600; }
QTabBar::tab:selected { background-color: $tab_active_bg; border: 1px solid $accent_dim; color: $accent; }
QTabBar::tab:hover:!selected { color: $text; background-color: $glass_fill_strong; border: 1px solid $glass_border; }

QPushButton { background-color: $btn_bg; border: 1px solid $glass_border; border-radius: 8px; padding: 6px 14px; color: $text; font-weight: 600; }
QPushButton:hover { background-color: $btn_hover_bg; border-color: $accent; color: $text; }
QPushButton:focus { border-color: $accent; }
QPushButton:pressed { background-color: $accent_dim; color: $accent_text; }
QPushButton:disabled { color: $text_muted; border-color: $glass_border; }

QToolButton { background-color: $btn_bg; border: 1px solid $glass_border; border-radius: 8px; padding: 6px 14px; color: $text; font-weight: 600; }
QToolButton:hover { background-color: $btn_hover_bg; border-color: $accent; }
QToolButton::menu-indicator { image: none; }

QSlider::groove:horizontal { background: $scroll_bg; height: 4px; border-radius: 2px; }
QSlider::sub-page:horizontal { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 $accent_dim, stop:1 $accent); border-radius: 2px; }
QSlider::handle:horizontal { background: #FFFFFF; border: 2px solid $accent; width: 12px; height: 12px; margin: -5px 0; border-radius: 8px; }
QSlider::handle:horizontal:hover { border-color: $accent_hi; }

QComboBox { background-color: $input_bg; border: 1px solid $input_border; border-radius: 8px; padding: 5px 10px; min-width: 80px; color: $text; }
QComboBox:hover { border-color: $accent; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background-color: $panel; border: 1px solid $glass_border; border-radius: 8px; selection-background-color: $btn_hover_bg; selection-color: $accent; outline: none; }

QSpinBox { background-color: $input_bg; border: 1px solid $input_border; border-radius: 8px; padding: 4px 6px; color: $text; }
QSpinBox:hover { border-color: $accent; }

QCheckBox { spacing: 8px; color: $text; }
QCheckBox::indicator { width: 16px; height: 16px; border: 2px solid $input_border; border-radius: 4px; background-color: $input_bg; }
QCheckBox::indicator:checked { background-color: $accent; border-color: $accent; }
QCheckBox::indicator:hover { border-color: $accent; }

QMenu { background-color: $panel; border: 1px solid $glass_border; border-radius: 8px; padding: 5px; }
QMenu::item { padding: 6px 24px; border-radius: 6px; }
QMenu::item:selected { background-color: $btn_hover_bg; color: $accent; }
QMenu::separator { height: 1px; background: $glass_border; margin: 4px 8px; }

QLabel { background: transparent; color: $text; }
QMessageBox { background-color: $bg_base; }
QColorDialog { background-color: $bg_base; }
QDialog { background-color: $bg_base; }

QScrollBar:vertical { background: $scroll_bg; width: 8px; border-radius: 4px; margin: 0; }
QScrollBar::handle:vertical { background: $scroll_handle; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: $accent; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar:horizontal { background: $scroll_bg; height: 8px; border-radius: 4px; }
QScrollBar::handle:horizontal { background: $scroll_handle; border-radius: 4px; min-width: 30px; }
QScrollBar::handle:horizontal:hover { background: $accent; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }

QStackedWidget { background: transparent; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }

QPushButton#SegMode { background: transparent; border: 1px solid transparent; border-radius: 8px; padding: 7px 10px; color: $text_dim; font-weight: 600; }
QPushButton#SegMode:hover { background-color: $glass_fill_strong; color: $text; }
QPushButton#SegMode:checked { background-color: $tab_active_bg; border-color: $accent_dim; color: $accent; }

QPushButton#Primary { background-color: $accent; border: 1px solid $accent; color: $accent_text; }
QPushButton#Primary:hover { background-color: $accent_hi; border-color: $accent_hi; color: $accent_text; }
QPushButton#Primary:pressed { background-color: $accent_dim; border-color: $accent_dim; color: $accent_text; }

QPushButton#Preset { padding: 5px 8px; font-size: 11px; }

QLabel#GroupTitle { color: $text_muted; font-size: 10px; font-weight: 700; }
QLabel#MonoValue { color: $text_dim; font-family: "Cascadia Mono", "Consolas", monospace; font-size: 12px; }
QLabel#StatValue { color: $text; font-family: "Cascadia Mono", "Consolas", monospace; font-size: 20px; font-weight: 700; }
QLabel#StatText { color: $text_dim; font-size: 13px; font-weight: 600; }
QFrame#Divider { background-color: $glass_border; border: none; max-height: 1px; }
QFrame#VDivider { background-color: $glass_border; border: none; max-width: 1px; }
""")


def build_qss(tokens):
    return _QSS_TEMPLATE.substitute(**tokens)


# --------------------------------------------------------------------------
# Keycap stylesheets
# --------------------------------------------------------------------------
_KEY_BASE = Template("""
QPushButton {
  background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 $key_top, stop:0.52 $key_mid, stop:1 $key_bot);
  border: 1px solid $key_border;
  border-bottom: 3px solid $key_border_bottom;
  border-radius: 6px;
  color: $key_text;
  font-size: 9px;
  font-weight: 600;
  padding: 0px 0px 1px 0px;
}
QPushButton:hover {
  border-color: $accent;
  border-bottom-color: $accent_dim;
  color: $text;
}
QPushButton:pressed {
  background-color: $key_bot;
  border-bottom-width: 1px;
  padding-top: 2px;
  color: $text;
}
""")

_KEY_PAINTED = Template("""
QPushButton {
  background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba($hr,$hg,$hb,0.98), stop:0.52 rgba($r,$g,$b,0.90), stop:1 rgba($rd,$gd,$bd,0.85));
  border: $border;
  border-bottom: 3px solid $bottom;
  border-radius: 6px;
  color: $fg;
  font-size: 9px;
  font-weight: 700;
  padding: 0px 0px 1px 0px;
}
QPushButton:hover {
  border-color: rgba(255,255,255,0.90);
}
QPushButton:pressed {
  border-bottom-width: 1px;
  padding-top: 2px;
}
""")


def _keycap_fg(r, g, b):
    """Readable label colour for a key painted with an arbitrary RGB value."""
    def channel(v):
        c = v / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    lum = 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
    return "#0A0D12" if lum > 0.179 else "#FFFFFF"


def keycap_base_qss(tokens):
    return _KEY_BASE.substitute(**tokens)


def keycap_qss(tokens, r, g, b, selected=False):
    hr, hg, hb = min(255, r + 80), min(255, g + 80), min(255, b + 80)
    rd, gd, bd = max(0, r - 80), max(0, g - 80), max(0, b - 80)
    if selected:
        border = f"2px solid {tokens['accent']}"
        bottom = tokens["accent_dim"]
    else:
        border = f"1px solid rgba({hr},{hg},{hb},0.90)"
        bottom = f"rgb({rd},{gd},{bd})"
    return _KEY_PAINTED.substitute(hr=hr, hg=hg, hb=hb, r=r, g=g, b=b,
                                   rd=rd, gd=gd, bd=bd, border=border,
                                   bottom=bottom, fg=_keycap_fg(r, g, b))


def swatch_qss(r, g, b, active=False, accent="#4D9EFF"):
    border = accent if active else "rgba(148,163,184,0.45)"
    width = "2px" if active else "1px"
    return (f"background-color: rgb({r},{g},{b});"
            f" border: {width} solid {border}; border-radius: 14px;")


# --------------------------------------------------------------------------
# Shared glass painting (used by the custom widgets)
# --------------------------------------------------------------------------
def draw_glass(painter, rect, radius, tokens, fill=None, border=None, highlight=True):
    """Paint a rounded faux-glass panel into `rect` (QRectF)."""
    rect = QRectF(rect)
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    painter.save()
    painter.setRenderHint(painter.RenderHint.Antialiasing, True)
    painter.fillPath(path, qcolor(fill or tokens["glass_fill"]))
    if highlight:
        hl = QLinearGradient(0, rect.top(), 0, rect.top() + max(1.0, rect.height() * 0.5))
        top = qcolor(tokens["glass_highlight"])
        top.setAlpha(min(top.alpha(), 70))
        hl.setColorAt(0.0, top)
        fade = QColor(tokens["glass_highlight"])
        fade.setAlpha(0)
        hl.setColorAt(1.0, fade)
        painter.save()
        painter.setClipPath(path)
        painter.fillRect(rect, hl)
        painter.restore()
    painter.setPen(QPen(qcolor(border or tokens["glass_border"]), 1))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(rect, radius, radius)
    painter.restore()
