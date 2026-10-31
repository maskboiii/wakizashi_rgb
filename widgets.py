"""Custom-painted widgets that give the app its glassmorphism look.

Qt stylesheets cannot blur what is behind a widget, so the "glass" here is
faux-glass: translucent fills, a light hairline border and a top highlight,
layered over a painted aurora background. Keeping the aurora on a dedicated
widget means every translucent panel above it composites correctly.
"""

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PyQt6.QtWidgets import QWidget

from theme import draw_glass, qcolor


# (x_fraction, y_fraction, radius_fraction_of_diagonal, token_key)
_GLOWS = (
    (0.14, 0.02, 0.55, "glow1"),
    (0.92, 0.10, 0.50, "glow2"),
    (0.50, 1.10, 0.62, "glow3"),
)


class AuroraBackground(QWidget):
    """Deep gradient with soft coloured glows and a faint grid, cached to a pixmap."""

    def __init__(self, tokens, parent=None):
        super().__init__(parent)
        self._t = tokens
        self._cache = None

    def set_tokens(self, tokens):
        self._t = tokens
        self._cache = None
        self.update()

    def resizeEvent(self, event):
        self._cache = None
        super().resizeEvent(event)

    def paintEvent(self, event):
        if self._cache is None or self._cache.size() != self.size():
            self._cache = self._render()
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._cache)

    def _render(self):
        w = max(1, self.width())
        h = max(1, self.height())
        pm = QPixmap(w, h)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, qcolor(self._t["grad_top"]))
        grad.setColorAt(1.0, qcolor(self._t["grad_bot"]))
        p.fillRect(0, 0, w, h, grad)

        diag = (w * w + h * h) ** 0.5
        base_alpha = 44 if self._t.get("name") == "dark" else 90
        for fx, fy, fr, key in _GLOWS:
            col = qcolor(self._t[key])
            col.setAlpha(base_alpha)
            cx, cy, radius = w * fx, h * fy, diag * fr
            rg = QRadialGradient(cx, cy, max(1.0, radius))
            rg.setColorAt(0.0, col)
            edge = QColor(col)
            edge.setAlpha(0)
            rg.setColorAt(1.0, edge)
            p.fillRect(0, 0, w, h, rg)

        grid = qcolor(self._t["glass_highlight"])
        grid.setAlpha(6)
        p.setPen(grid)
        step = 48
        for x in range(0, w, step):
            p.drawLine(x, 0, x, h)
        for y in range(0, h, step):
            p.drawLine(0, y, w, y)

        p.end()
        return pm


class KeyboardCanvas(QWidget):
    """Transparent host for the keycap buttons: draws a soft glass plate behind them."""

    def __init__(self, tokens, parent=None):
        super().__init__(parent)
        self._t = tokens
        self._ambient = None

    def set_tokens(self, tokens):
        self._t = tokens
        self.update()

    def set_ambient(self, rgb):
        """Tint the halo under the plate with the armed LED colour."""
        self._ambient = tuple(rgb) if rgb else None
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(38, 8, self.width() - 76, self.height() - 24)

        base = QColor(*self._ambient) if self._ambient else qcolor(self._t["accent"])
        halo = QColor(base)
        halo.setAlpha(52)
        rg = QRadialGradient(rect.center(), max(1.0, rect.width() * 0.62))
        rg.setColorAt(0.0, halo)
        rg.setColorAt(1.0, QColor(base.red(), base.green(), base.blue(), 0))
        painter.fillRect(self.rect(), rg)

        core = QColor(base)
        core.setAlpha(36)
        rg2 = QRadialGradient(rect.center(), max(1.0, rect.width() * 0.34))
        rg2.setColorAt(0.0, core)
        rg2.setColorAt(1.0, QColor(base.red(), base.green(), base.blue(), 0))
        painter.fillRect(self.rect(), rg2)

        draw_glass(painter, rect, 16, self._t,
                   fill=self._t["glass_fill"], highlight=True)

        edge = qcolor(self._t["glass_highlight"])
        edge.setAlpha(38)
        painter.setPen(QPen(edge, 1))
        painter.drawLine(QPointF(rect.left() + 14, rect.top() + 0.5),
                         QPointF(rect.right() - 14, rect.top() + 0.5))


class GlassPanel(QWidget):
    """Reusable rounded faux-glass container."""

    def __init__(self, tokens, radius=16, parent=None):
        super().__init__(parent)
        self._t = tokens
        self._radius = radius
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def set_tokens(self, tokens):
        self._t = tokens
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        draw_glass(painter, rect, self._radius, self._t)


class SpectrumWidget(QWidget):
    """Live audio display: spectrum bars, waveform or a level pulse."""

    def __init__(self, tokens, parent=None):
        super().__init__(parent)
        self._t = tokens
        self._bands = []
        self._wave = []
        self._level = 0.0
        self._peak = 0.0
        self._mode = "bars"

    def set_tokens(self, tokens):
        self._t = tokens
        self.update()

    def set_mode(self, mode):
        self._mode = mode
        self.update()

    def set_data(self, bands, wave, level, peak=0.0):
        self._bands = list(bands or [])
        self._wave = list(wave or [])
        self._level = float(level or 0.0)
        self._peak = float(peak or 0.0)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        draw_glass(painter, rect, 10, self._t, fill=self._t["glass_fill"])
        inner = rect.adjusted(8, 6, -8, -6)
        if inner.width() <= 1 or inner.height() <= 1:
            painter.end()
            return
        if self._mode == "wave":
            self._paint_wave(painter, inner)
        elif self._mode == "pulse":
            self._paint_pulse(painter, inner)
        else:
            self._paint_bars(painter, inner)
        painter.end()

    def _gradient(self, rect):
        grad = QLinearGradient(0, rect.bottom(), 0, rect.top())
        grad.setColorAt(0.0, qcolor(self._t["accent_dim"]))
        grad.setColorAt(0.55, qcolor(self._t["accent"]))
        grad.setColorAt(1.0, qcolor(self._t["glow3"]))
        return grad

    def _paint_bars(self, painter, rect):
        bands = self._bands
        if not bands:
            return
        n = len(bands)
        gap = 2.0 if n <= 32 else 1.0
        bar_w = max(1.0, (rect.width() - gap * (n - 1)) / n)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._gradient(rect))
        radius = min(2.5, bar_w / 2.0)
        for i, value in enumerate(bands):
            value = max(0.0, min(1.0, float(value)))
            bar_h = max(1.5, value * rect.height())
            x = rect.left() + i * (bar_w + gap)
            painter.drawRoundedRect(
                QRectF(x, rect.bottom() - bar_h, bar_w, bar_h), radius, radius)

    def _paint_wave(self, painter, rect):
        wave = self._wave
        if len(wave) < 2:
            return
        mid = rect.center().y()
        half = rect.height() / 2.0
        pen = QPen(qcolor(self._t["accent"]), 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        points = []
        steps = len(wave)
        for i, sample in enumerate(wave):
            x = rect.left() + rect.width() * i / (steps - 1)
            y = mid - max(-1.0, min(1.0, float(sample))) * half
            points.append(QPointF(x, y))
        painter.drawPolyline(points)

    def _paint_pulse(self, painter, rect):
        level = max(0.0, min(1.0, self._level))
        peak = max(0.0, min(1.0, self._peak))
        pen = QPen(qcolor(self._t["glass_border"]), 1)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 4, 4)
        fill = QRectF(rect.left(), rect.top(), rect.width() * level,
                      rect.height())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._gradient(rect))
        painter.drawRoundedRect(fill, 4, 4)
        if peak > 0:
            painter.setPen(QPen(qcolor(self._t["accent_hi"]), 1.5))
            x = rect.left() + rect.width() * peak
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))


class HeaderBar(QWidget):
    """Slim instrument header: brand and the armed colour."""

    def __init__(self, tokens, parent=None):
        super().__init__(parent)
        self._t = tokens
        self._color = None
        self.setFixedHeight(42)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def set_tokens(self, tokens):
        self._t = tokens
        self.update()

    def set_color(self, rgb):
        self._color = tuple(rgb) if rgb else None
        self.update()

    def _font(self, families, size, bold=False, spacing=0.0):
        font = QFont()
        font.setFamilies(families)
        font.setPixelSize(size)
        font.setBold(bold)
        if spacing:
            font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
        return font

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()

        painter.setPen(QPen(qcolor(self._t["glass_border"]), 1))
        painter.drawLine(0, h - 1, w, h - 1)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(qcolor(self._t["accent"]))
        painter.drawRoundedRect(QRectF(16, 14, 3, 14), 1.5, 1.5)

        painter.setPen(qcolor(self._t["text"]))
        painter.setFont(self._font(["Inter", "Segoe UI"], 12, True, 2.2))
        painter.drawText(QRectF(28, 6, 300, 18),
                         int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                         "WAKIZASHI")

        painter.setPen(qcolor(self._t["text_muted"]))
        painter.setFont(self._font(["Inter", "Segoe UI"], 8, True, 1.6))
        painter.drawText(QRectF(28, 23, 300, 14),
                         int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                         "RGB PAINT")

        right = w - 14.0

        mono = self._font(["Cascadia Mono", "Consolas", "Segoe UI"], 10)
        mono_fm = QFontMetrics(mono)
        hex_text = "#%02X%02X%02X" % self._color if self._color else "—"
        cw = 20 + mono_fm.horizontalAdvance(hex_text) + 12
        color_rect = QRectF(right - cw, 10, cw, 22)
        painter.setPen(QPen(qcolor(self._t["glass_border"]), 1))
        painter.setBrush(qcolor(self._t["glass_fill_strong"]))
        painter.drawRoundedRect(color_rect, 11, 11)

        dot_c = QPointF(color_rect.left() + 12, color_rect.center().y())
        if self._color:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(*self._color))
            painter.drawEllipse(dot_c, 4.5, 4.5)
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(qcolor(self._t["text_muted"]), 1.2))
            painter.drawEllipse(dot_c, 4.0, 4.0)

        painter.setPen(qcolor(self._t["text_dim"]))
        painter.setFont(mono)
        painter.drawText(QRectF(color_rect.left() + 20, color_rect.top(),
                                color_rect.width() - 24, color_rect.height()),
                         int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                         hex_text)


class StatusBar(QWidget):
    """Glass status strip with a connection indicator dot and a text label."""

    def __init__(self, tokens, text="", parent=None):
        super().__init__(parent)
        self._t = tokens
        self._text = text
        self._ok = None

    def set_tokens(self, tokens):
        self._t = tokens
        self.update()

    def setText(self, text):
        self._text = text
        self.update()

    def text(self):
        return self._text

    def set_ok(self, ok):
        self._ok = ok
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(6, 3, self.width() - 12, self.height() - 6)
        draw_glass(painter, rect, 8, self._t, fill=self._t["glass_fill_strong"])

        if self._ok is True:
            dot = qcolor(self._t["ok"])
        elif self._ok is False:
            dot = qcolor(self._t["danger"])
        else:
            dot = qcolor(self._t["text_muted"])
        cx, cy = 22.0, self.height() / 2.0

        halo = QColor(dot)
        halo.setAlpha(70)
        rg = QRadialGradient(cx, cy, 11.0)
        rg.setColorAt(0.0, halo)
        edge = QColor(dot)
        edge.setAlpha(0)
        rg.setColorAt(1.0, edge)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(rg)
        painter.drawEllipse(QPointF(cx, cy), 11.0, 11.0)

        painter.setBrush(dot)
        painter.drawEllipse(QPointF(cx, cy), 4.5, 4.5)

        font = QFont()
        font.setFamilies(["Cascadia Mono", "Consolas", "Segoe UI"])
        font.setPixelSize(11)
        font.setBold(True)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.4)
        painter.setFont(font)
        painter.setPen(qcolor(self._t["text"]))
        text_rect = QRectF(38, 0, self.width() - 48, self.height())
        painter.drawText(text_rect,
                         int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                         self._text)
