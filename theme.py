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
    "bg_base": "#0A0F1C",
    "grad_top": "#0C1222",
    "grad_bot": "#06090F",
    "glow1": "#1D4ED8",
    "glow2": "#4F46E5",
    "glow3": "#0EA5E9",
    "glass_fill": "rgba(255,255,255,0.055)",
    "glass_fill_strong": "rgba(255,255,255,0.09)",
    "glass_border": "rgba(255,255,255,0.13)",
    "glass_highlight": "rgba(255,255,255,0.35)",
    "panel": "#101728",
    "text": "#D6DEEB",
    "text_dim": "#7E8BA3",
    "text_muted": "#5A6780",
    "accent": "#4D9EFF",
    "accent_hi": "#7AB8FF",
    "accent_dim": "#1D4ED8",
    "accent_text": "#071018",
    "danger": "#FF5C7A",
    "ok": "#3BE38B",
    "btn_bg": "rgba(255,255,255,0.06)",
    "btn_hover_bg": "rgba(77,158,255,0.18)",
    "input_bg": "rgba(255,255,255,0.05)",
    "input_border": "rgba(255,255,255,0.14)",
    "key_top": "#2A3348",
    "key_mid": "#202940",
    "key_bot": "#161D2E",
    "key_border": "#3A4664",
    "key_border_bottom": "#10141F",
    "key_text": "#AEB9CE",
    "scroll_bg": "rgba(255,255,255,0.04)",
    "scroll_handle": "rgba(255,255,255,0.18)",
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
QWidget { color: $text; font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif; font-size: 12px; }
QToolTip { background-color: $panel; color: $text; border: 1px solid $glass_border; border-radius: 6px; padding: 4px 8px; }

QTabWidget::pane { border: 1px solid $glass_border; border-radius: 14px; background-color: $glass_fill; top: -1px; }
QTabWidget::tab-bar { left: 6px; }
QTabBar { qproperty-drawBase: 0; background: transparent; }
QTabBar::tab { background: transparent; border: 1px solid transparent; border-radius: 10px; padding: 7px 18px; margin-right: 4px; color: $text_dim; font-weight: 600; }
QTabBar::tab:selected { background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 $accent_hi, stop:1 $accent); color: $accent_text; border: 1px solid $accent; }
QTabBar::tab:hover:!selected { color: $text; background-color: $glass_fill_strong; border: 1px solid $glass_border; }

QPushButton { background-color: $btn_bg; border: 1px solid $glass_border; border-radius: 10px; padding: 6px 16px; color: $text; font-weight: 600; }
QPushButton:hover { background-color: $btn_hover_bg; border-color: $accent; color: $text; }
QPushButton:pressed { background-color: $accent_dim; color: $accent_text; }
QPushButton:disabled { color: $text_muted; border-color: $glass_border; }

QToolButton { background-color: $btn_bg; border: 1px solid $glass_border; border-radius: 10px; padding: 6px 14px; color: $text; font-weight: 600; }
QToolButton:hover { background-color: $btn_hover_bg; border-color: $accent; }
QToolButton::menu-indicator { image: none; }

QSlider::groove:horizontal { background: $scroll_bg; height: 6px; border-radius: 3px; }
QSlider::sub-page:horizontal { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 $accent_dim, stop:1 $accent); border-radius: 3px; }
QSlider::handle:horizontal { background: #FFFFFF; border: 2px solid $accent; width: 14px; height: 14px; margin: -6px 0; border-radius: 8px; }
QSlider::handle:horizontal:hover { border-color: $accent_hi; }

QComboBox { background-color: $input_bg; border: 1px solid $input_border; border-radius: 10px; padding: 5px 10px; min-width: 80px; color: $text; }
QComboBox:hover { border-color: $accent; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background-color: $panel; border: 1px solid $glass_border; border-radius: 8px; selection-background-color: $btn_hover_bg; selection-color: $accent; outline: none; }

QSpinBox { background-color: $input_bg; border: 1px solid $input_border; border-radius: 10px; padding: 4px 6px; color: $text; }
QSpinBox:hover { border-color: $accent; }

QCheckBox { spacing: 8px; color: $text; }
QCheckBox::indicator { width: 16px; height: 16px; border: 2px solid $input_border; border-radius: 5px; background-color: $input_bg; }
QCheckBox::indicator:checked { background-color: $accent; border-color: $accent; }
QCheckBox::indicator:hover { border-color: $accent; }

QMenu { background-color: $panel; border: 1px solid $glass_border; border-radius: 10px; padding: 5px; }
QMenu::item { padding: 6px 24px; border-radius: 6px; }
QMenu::item:selected { background-color: $btn_hover_bg; color: $accent; }
QMenu::separator { height: 1px; background: $glass_border; margin: 4px 8px; }

QLabel { background: transparent; color: $text; }
QMessageBox { background-color: $bg_base; }
QColorDialog { background-color: $bg_base; }
QDialog { background-color: $bg_base; }

QScrollBar:vertical { background: $scroll_bg; width: 10px; border-radius: 5px; margin: 0; }
QScrollBar::handle:vertical { background: $scroll_handle; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: $accent; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar:horizontal { background: $scroll_bg; height: 10px; border-radius: 5px; }
QScrollBar::handle:horizontal { background: $scroll_handle; border-radius: 5px; min-width: 30px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
""")


def build_qss(tokens):
    return _QSS_TEMPLATE.substitute(**tokens)


# --------------------------------------------------------------------------
# Keycap stylesheets
# --------------------------------------------------------------------------
_KEY_BASE = Template("""
QPushButton {
  background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 $key_top, stop:0.55 $key_mid, stop:1 $key_bot);
  border: 1px solid $key_border;
  border-bottom: 3px solid $key_border_bottom;
  border-radius: 7px;
  color: $key_text;
  font-size: 9px;
  font-weight: 600;
  padding-top: 1px;
}
QPushButton:hover {
  border: 1px solid $accent;
  border-bottom: 3px solid $accent_dim;
  color: $text;
}
""")

_KEY_PAINTED = Template("""
QPushButton {
  background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba($hr,$hg,$hb,0.95), stop:0.55 rgba($r,$g,$b,0.82), stop:1 rgba($r,$g,$b,0.50));
  border: $border;
  border-bottom: 3px solid rgb($rd,$gd,$bd);
  border-radius: 7px;
  color: #FFFFFF;
  font-size: 9px;
  font-weight: 700;
  padding-top: 1px;
}
""")


def keycap_base_qss(tokens):
    return _KEY_BASE.substitute(**tokens)


def keycap_qss(tokens, r, g, b, selected=False):
    hr, hg, hb = min(255, r + 80), min(255, g + 80), min(255, b + 80)
    rd, gd, bd = max(0, r - 80), max(0, g - 80), max(0, b - 80)
    border = f"2px solid {tokens['accent']}" if selected else f"1px solid rgb({r},{g},{b})"
    return _KEY_PAINTED.substitute(hr=hr, hg=hg, hb=hb, r=r, g=g, b=b,
                                   rd=rd, gd=gd, bd=bd, border=border)


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
