"""The single-window UI, styled after a late-80s / early-90s Japanese race car cockpit:
gunmetal dash, tach gauge, amber 7-segment readouts, italic livery type, katakana,
red/white/blue stripes and a halftone "gradation" strip. All artwork is drawn in code.
"""
from __future__ import annotations

import html
import math
import os
import threading
import time

from PyQt6.QtCore import QByteArray, QPointF, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (QColor, QFont, QFontDatabase, QFontMetrics, QIcon, QLinearGradient,
                         QPainter, QPen, QPolygonF, QRadialGradient)
from PyQt6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame,
                             QHBoxLayout, QInputDialog, QLabel, QMainWindow, QPushButton,
                             QScrollArea, QSizePolicy, QSlider, QSpinBox, QVBoxLayout, QWidget)

from . import config
from .audio import list_output_devices
from .engine import Engine

ASSETS = os.path.join(os.path.dirname(__file__), "assets")

# Cockpit palette
BLACK, PANEL, STEEL, STEEL_HI = "#0C0D10", "#15171C", "#2A2E35", "#4A5059"
WHITE, GREY, DIMGREY = "#F2F2F0", "#9AA0A8", "#5E646C"
RED, RED_HI, BLUE, BLUE_HI = "#E10600", "#FF2A1F", "#1446C8", "#2F6BFF"
AMBER, NEEDLE = "#FFB000", "#FF5A00"
SPEAKER_COLORS = ["#FF2A1F", "#2F6BFF", "#FFD400", "#F2F2F0", "#FF8A00",
                  "#21D4C2", "#C04BFF", "#7CFF4F"]

MODELS = [("tiny", "Tiny · fastest, rough"), ("base", "Base · quick"),
          ("small", "Small · best pick"), ("medium", "Medium · sharper"),
          ("large-v3", "Large · heavy")]
LANGS = [("es", "Spanish  »  English"), ("pt", "Portuguese  »  English"),
         ("fr", "French  »  English"), ("de", "German  »  English"),
         ("it", "Italian  »  English"), ("ru", "Russian  »  English"),
         ("", "Any language  »  English")]

UI, JP, SEG = "Chakra Petch", "Dela Gothic One", "DSEG7 Classic"


def load_fonts():
    fdir = os.path.join(ASSETS, "fonts")
    for f in os.listdir(fdir):
        if f.endswith(".ttf"):
            QFontDatabase.addApplicationFont(os.path.join(fdir, f))


def speaker_color(idx: int) -> str:
    return SPEAKER_COLORS[idx % len(SPEAKER_COLORS)]


def ui_font(px: int, bold=True, italic=True, spacing=0.0) -> QFont:
    f = QFont(UI)
    f.setPixelSize(px)
    f.setWeight(QFont.Weight.Bold if bold else QFont.Weight.Normal)
    f.setItalic(italic)
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return f


def _readable_on(bg: str) -> QColor:
    c = QColor(bg)
    lum = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
    return QColor("#0C0D10" if lum > 150 else "#FFFFFF")


QSS = f"""
QMainWindow, #root {{ background: {BLACK}; }}
QLabel {{ color: {WHITE}; font-family: '{UI}'; }}
#caption {{ font-family: '{UI}'; font-size: 10px; font-weight: 700; font-style: italic;
  letter-spacing: 2px; color: {GREY}; }}
#status {{ font-family: '{UI}'; font-size: 13px; font-weight: 600; color: {AMBER};
  background: #0A0906; border: 1px solid {STEEL}; border-radius: 2px; padding: 5px 10px; }}
#transcript {{ background: {PANEL}; border: 1px solid {STEEL}; border-top: 2px solid {RED};
  border-radius: 2px; }}
#transcript QWidget#lines {{ background: transparent; }}
#placeholder {{ font-family: '{UI}'; color: {GREY}; font-size: 15px; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 6px 2px; }}
QScrollBar::handle:vertical {{ background: {STEEL_HI}; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {RED}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

#dash {{
  background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #30343B, stop:0.08 #23262C,
      stop:1 #17191D);
  border: 1px solid #3A3F47; border-left: 4px solid {RED}; border-radius: 2px;
}}
QComboBox {{
  font-family: '{UI}'; font-size: 14px; font-weight: 600; color: {WHITE};
  background: {BLACK}; border: 1px solid #3A3F47; border-left: 3px solid {RED};
  border-radius: 1px; padding: 5px 24px 5px 9px; min-width: 100px;
}}
QComboBox:hover {{ border-color: {STEEL_HI}; border-left-color: {RED_HI}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ image: url(__ARROW__); width: 12px; height: 8px; margin-right: 8px; }}
QComboBox QAbstractItemView {{
  font-family: '{UI}'; font-size: 14px; background: {BLACK}; color: {WHITE};
  selection-background-color: {RED}; border: 1px solid {STEEL_HI}; outline: 0; padding: 2px;
}}
QDialog {{ background: {PANEL}; }}
QDialog QLabel {{ font-size: 14px; font-weight: 600; }}
QSpinBox {{ font-family: '{UI}'; font-size: 14px; color: {WHITE}; background: {BLACK};
  border: 1px solid #3A3F47; border-left: 3px solid {RED}; padding: 3px 8px; }}
QSlider::groove:horizontal {{ height: 4px; background: {BLACK}; }}
QSlider::sub-page:horizontal {{ background: {RED}; }}
QSlider::handle:horizontal {{ width: 10px; margin: -8px 0; background: {WHITE}; }}
QDialogButtonBox QPushButton, QInputDialog QPushButton {{
  font-family: '{UI}'; font-size: 13px; font-weight: 700; font-style: italic; color: {WHITE};
  background: {STEEL}; border: 1px solid {STEEL_HI}; border-radius: 1px; padding: 6px 18px;
  min-width: 70px; }}
QDialogButtonBox QPushButton:hover, QInputDialog QPushButton:hover {{ background: {RED}; }}
QInputDialog QLineEdit {{ font-family: '{UI}'; font-size: 15px; color: {WHITE};
  background: {BLACK}; border: 1px solid {STEEL_HI}; border-left: 3px solid {RED};
  padding: 4px 8px; }}
QToolTip {{ font-family: '{UI}'; color: {WHITE}; background: {BLACK};
  border: 1px solid {RED}; }}
"""


# ============================================================================ painted parts

class SlantButton(QPushButton):
    """Parallelogram button / race-number tag."""

    STYLES = {  # kind: (top, bottom, border, text)
        "start": ("#FF3B2F", "#B10500", "#FF8A80", WHITE),
        "live": ("#3B78FF", "#0F33A0", "#9DB8FF", WHITE),
        "steel": ("#454A53", "#24272D", "#6A717B", WHITE),
        "ghost": (None, None, STEEL_HI, GREY),
    }

    def __init__(self, text="", kind="steel", px=14, pad=16, vpad=7, skew=9, color=None,
                 parent=None):
        super().__init__(text, parent)
        self.kind, self.color, self.pad, self.vpad, self.skew = kind, color, pad, vpad, skew
        self.setFont(ui_font(px, spacing=1.5))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def sizeHint(self):
        fm = QFontMetrics(self.font())
        return QSize(fm.horizontalAdvance(self.text()) + 2 * self.pad + self.skew,
                     fm.height() + 2 * self.vpad)

    minimumSizeHint = sizeHint

    def set_kind(self, kind: str):
        self.kind = kind
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h, s = self.width() - 1, self.height() - 1, self.skew
        poly = QPolygonF([QPointF(s, 0.5), QPointF(w, 0.5), QPointF(w - s, h), QPointF(0.5, h)])
        hover = self.underMouse() and self.isEnabled()
        if self.kind == "tag":
            c = QColor(self.color)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c.lighter(115) if hover else c)
            p.drawPolygon(poly)
            txt = _readable_on(self.color)
        else:
            top, bot, border, txt = self.STYLES[self.kind]
            if top:
                g = QLinearGradient(0, 0, 0, h)
                g.setColorAt(0, QColor(top).lighter(112) if hover else QColor(top))
                g.setColorAt(1, QColor(bot))
                p.setBrush(g)
            else:
                p.setBrush(QColor(RED) if hover else Qt.BrushStyle.NoBrush)
                if hover:
                    txt = WHITE
            p.setPen(QPen(QColor(border), 1))
            p.drawPolygon(poly)
            if top:  # specular line
                p.setPen(QPen(QColor(255, 255, 255, 70), 1))
                p.drawLine(QPointF(s + 2, 2), QPointF(w - 2, 2))
            txt = QColor(txt)
        if self.isDown():
            p.translate(0, 1)
        p.setPen(txt)
        p.setFont(self.font())
        p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, self.text())


class GradationStrip(QWidget):
    """Halftone dots fading blue → violet → red, the classic early-90s bucket-seat look."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(BLACK))
        stops = [QColor("#1E50FF"), QColor("#7A2BE2"), QColor("#FF1E3C")]
        step = 6
        rows = self.height() // step
        w = max(1, self.width())
        p.setPen(Qt.PenStyle.NoPen)
        for col in range(w // step + 1):
            f = col * step / w
            seg = min(1, int(f * 2))
            t = f * 2 - seg
            a, b = stops[seg], stops[seg + 1]
            c = QColor(int(a.red() + (b.red() - a.red()) * t),
                       int(a.green() + (b.green() - a.green()) * t),
                       int(a.blue() + (b.blue() - a.blue()) * t))
            p.setBrush(c)
            for row in range(rows):
                # dots swell toward the middle row and pulse along the length
                v = 1 - abs((row + 0.5) / rows - 0.5) * 2
                r = 0.35 + 2.75 * v ** 1.3
                off = step / 2 if row % 2 else 0
                p.drawEllipse(QPointF(col * step + off, row * step + step / 2), r, r)


class LiveryStripes(QWidget):
    """Red / white / blue pinstripes with a slanted cut, like a door livery."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(11)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        p.setPen(Qt.PenStyle.NoPen)
        for y, hgt, col, cut in ((0, 4, RED, 70), (5, 1.5, WHITE, 90), (7.5, 3.5, BLUE, 110)):
            p.setBrush(QColor(col))
            p.drawPolygon(QPolygonF([QPointF(0, y), QPointF(w - cut, y),
                                     QPointF(w - cut - 6, y + hgt), QPointF(0, y + hgt)]))


class RacingLogo(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.subtitle = ""
        self.setFixedHeight(92)
        self.setMinimumWidth(420)

    def set_subtitle(self, text: str):
        self.subtitle = text
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        title = ui_font(44, spacing=1)
        p.setFont(title)
        base = 50
        for dx, col in ((5, BLUE), (2.5, RED), (0, WHITE)):  # double drop-shadow decal
            p.setPen(QColor(col))
            p.drawText(QPointF(4 + dx, base + dx * 0.6), "PARTY LINE")
        tw = QFontMetrics(title).horizontalAdvance("PARTY LINE")
        # katakana plate
        jp = QFont(JP)
        jp.setPixelSize(14)
        p.setFont(jp)
        jw = QFontMetrics(jp).horizontalAdvance("パーティーライン") + 26
        y0 = base + 10
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(RED))
        p.drawPolygon(QPolygonF([QPointF(10, y0), QPointF(10 + jw, y0),
                                 QPointF(4 + jw, y0 + 22), QPointF(4, y0 + 22)]))
        p.setPen(QColor(WHITE))
        p.drawText(QRectF(4, y0, jw + 6, 22), Qt.AlignmentFlag.AlignCenter, "パーティーライン")
        p.setFont(ui_font(11, spacing=2.5))
        p.setPen(QColor(GREY))
        p.drawText(QPointF(jw + 20, y0 + 16), f"VOICE COMM SYSTEM  //  {self.subtitle}")
        # tiny version sticker after the title
        p.setFont(ui_font(10, spacing=1))
        p.setPen(QColor(DIMGREY))
        p.drawText(QPointF(tw + 16, 22), "Ver.2")


class Tachometer(QWidget):
    """Audio level shown as a tach: idles when listening, revs when people talk."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(134, 134)
        self.target = self.value = 0.0
        self.live = False
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(33)

    def set_level(self, v: float):
        self.target = v

    def set_live(self, live: bool):
        self.live = live

    def _tick(self):
        tgt = max(self.target, 0.11) if self.live else self.target  # idle rpm
        k = 0.45 if tgt > self.value else 0.07
        nv = self.value + (tgt - self.value) * k
        if abs(nv - self.value) > 0.002:
            self.value = nv
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        c = QPointF(w / 2, h / 2)
        R = w / 2 - 2
        bez = QLinearGradient(0, 0, 0, h)
        bez.setColorAt(0, QColor("#6B717A"))
        bez.setColorAt(0.5, QColor("#1E2025"))
        bez.setColorAt(1, QColor("#4A4F57"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bez)
        p.drawEllipse(c, R, R)
        face = QRadialGradient(c, R)
        face.setColorAt(0, QColor("#17191D"))
        face.setColorAt(1, QColor("#08090B"))
        p.setBrush(face)
        r = R - 5
        p.drawEllipse(c, r, r)

        def ang(v):  # 0..1 → radians, 225° → -45° clockwise
            return math.radians(225 - 270 * v)

        def pt(v, rad):
            a = ang(v)
            return QPointF(c.x() + rad * math.cos(a), c.y() - rad * math.sin(a))

        # red zone
        rz = QRectF(c.x() - r + 6, c.y() - r + 6, 2 * (r - 6), 2 * (r - 6))
        p.setPen(QPen(QColor(RED), 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        p.drawArc(rz, int(-45 * 16), int(270 * (1 - 0.8125) * 16))
        # ticks + numerals
        p.setFont(ui_font(11))
        for i in range(41):
            v = i / 40
            major = i % 5 == 0
            col = QColor(RED_HI if v >= 0.8125 else WHITE)
            p.setPen(QPen(col, 2 if major else 1))
            p.drawLine(pt(v, r - 3), pt(v, r - (11 if major else 6)))
            if major:
                q = pt(v, r - 22)
                p.drawText(QRectF(q.x() - 10, q.y() - 8, 20, 16),
                           Qt.AlignmentFlag.AlignCenter, str(i // 5))
        p.setFont(ui_font(9, spacing=1.5))
        p.setPen(QColor(RED_HI))
        p.drawText(QRectF(0, c.y() + 14, w, 12), Qt.AlignmentFlag.AlignCenter, "VOICE")
        p.setFont(ui_font(7, bold=False, spacing=0.5))
        p.setPen(QColor(GREY))
        p.drawText(QRectF(0, c.y() + 27, w, 10), Qt.AlignmentFlag.AlignCenter, "×1000 r/min")
        # needle with glow
        tip, tail = pt(self.value, r - 8), pt(self.value + 0.5, 12)
        glow = QColor(NEEDLE)
        glow.setAlpha(70)
        p.setPen(QPen(glow, 7, cap=Qt.PenCapStyle.RoundCap))
        p.drawLine(tail, tip)
        p.setPen(QPen(QColor(NEEDLE), 2.5, cap=Qt.PenCapStyle.RoundCap))
        p.drawLine(tail, tip)
        p.setPen(QPen(QColor("#555A62"), 1.5))
        p.setBrush(QColor("#1A1C20"))
        p.drawEllipse(c, 7, 7)


class SegmentReadout(QWidget):
    """Amber 7-segment LCD with unlit 'ghost' segments behind the digits."""

    def __init__(self, label: str, unit: str, parent=None):
        super().__init__(parent)
        self.label, self.unit, self.text = label, unit, "!-.-"
        self.setFixedSize(112, 52)

    def set_value(self, text: str):
        self.text = text
        self.update()

    @staticmethod
    def fmt(v: float) -> str:
        return f"{min(v, 99.9):4.1f}".replace(" ", "!")  # "!" = blank, same width as a digit

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        p.setPen(QPen(QColor(STEEL_HI), 1))
        p.setBrush(QColor("#0A0906"))
        p.drawRect(r)
        p.setFont(ui_font(8, spacing=1.5))
        p.setPen(QColor(GREY))
        p.drawText(QPointF(7, 13), self.label)
        p.drawText(QRectF(0, 3, self.width() - 7, 12), Qt.AlignmentFlag.AlignRight, self.unit)
        seg = QFont(SEG)
        seg.setPixelSize(22)
        p.setFont(seg)
        box = QRectF(6, 16, self.width() - 14, 32)
        p.setPen(QColor(255, 176, 0, 28))
        p.drawText(box, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "88.8")
        p.setPen(QColor(AMBER))
        p.drawText(box, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self.text)


class WarningLamp(QWidget):
    """Dash telltale: dark until lit."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.text, self.lit = text, False
        self.setFixedSize(112, 30)

    def set_lit(self, lit: bool):
        self.lit = lit
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        if self.lit:
            g = QRadialGradient(r.center(), r.width() * 0.6)
            g.setColorAt(0, QColor("#FF4A3D"))
            g.setColorAt(1, QColor("#B00800"))
            p.setBrush(g)
            p.setPen(QPen(QColor("#FF9D96"), 1))
            txt = QColor(WHITE)
        else:
            p.setBrush(QColor("#170807"))
            p.setPen(QPen(QColor("#3A1512"), 1))
            txt = QColor("#4A1A16")
        p.drawRect(r)
        p.setFont(ui_font(13, spacing=4))
        p.setPen(txt)
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, self.text)


# ============================================================================ transcript

class LineWidget(QFrame):
    def __init__(self, entry: dict, show_lang: bool, font_px: int):
        super().__init__()
        self.idx = entry["idx"]
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 7, 14, 7)
        lay.setSpacing(12)
        ts = QLabel(time.strftime("%H:%M", time.localtime(entry["time"])))
        ts.setStyleSheet(f"color: {AMBER}; font-family: '{SEG}'; font-size: 11px;")
        ts.setAlignment(Qt.AlignmentFlag.AlignTop)
        ts.setContentsMargins(0, 6, 0, 0)
        self.badge = SlantButton(entry["name"].upper(), kind="tag", color=speaker_color(self.idx),
                                 px=max(11, font_px - 7), pad=10, vpad=3, skew=7)
        self.badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.badge.setMinimumWidth(96)
        badge_col = QVBoxLayout()
        badge_col.setContentsMargins(0, 2, 0, 0)
        badge_col.addWidget(self.badge)
        badge_col.addStretch()
        lang = entry.get("lang") or ""
        tag = (f'<span style="color:{GREY};font-size:11px">[{html.escape(lang, quote=False)}]'
               f'</span> ' if show_lang and lang and lang != "en" else "")
        text = QLabel(tag + html.escape(entry["text"], quote=False))
        text.setObjectName("lineText")
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        lay.addWidget(ts)
        lay.addLayout(badge_col)
        lay.addWidget(text, 1)

    def set_name(self, name: str):
        self.badge.setText(name.upper())
        self.badge.updateGeometry()

    def set_badge_px(self, px: int):
        self.badge.setFont(ui_font(max(11, px - 7), spacing=1.5))
        self.badge.updateGeometry()


class Transcript(QScrollArea):
    MAX_LINES = 300

    def __init__(self):
        super().__init__()
        self.setObjectName("transcript")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.inner = QWidget()
        self.inner.setObjectName("lines")
        self.vbox = QVBoxLayout(self.inner)
        self.vbox.setContentsMargins(6, 10, 6, 10)
        self.vbox.setSpacing(1)
        self.placeholder = QLabel(
            "— STANDING BY —\n\nHit START LISTENING, roll into your match, and any Spanish your "
            "teammates say shows up here in English.\n\nClick a driver's tag to name them. "
            "NEW MATCH clears the board.")
        self.placeholder.setObjectName("placeholder")
        self.placeholder.setWordWrap(True)
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._reset_layout(show_placeholder=True)
        self.setWidget(self.inner)
        self.lines: list[LineWidget] = []
        self.font_size = 19
        self.verticalScrollBar().rangeChanged.connect(self._range_changed)
        self._stick = True

    def _reset_layout(self, show_placeholder: bool):
        while self.vbox.count():
            self.vbox.takeAt(0)
        self.vbox.addStretch(1)
        if show_placeholder:
            self.vbox.addWidget(self.placeholder)
            self.vbox.addStretch(1)
            self.placeholder.show()
        else:
            self.placeholder.hide()

    def set_font_size(self, px: int):
        self.font_size = px
        self.inner.setStyleSheet(
            f"QLabel#lineText {{ font-family: '{UI}'; font-weight: 600; font-size: {px}px;"
            f" color: {WHITE}; }}")
        for w in self.lines:
            w.set_badge_px(px)

    def add(self, entry: dict, show_lang: bool):
        if self.placeholder.isVisible():
            self._reset_layout(show_placeholder=False)
        bar = self.verticalScrollBar()
        self._stick = bar.value() >= bar.maximum() - 30
        w = LineWidget(entry, show_lang, self.font_size)
        self.vbox.addWidget(w)
        self.lines.append(w)
        while len(self.lines) > self.MAX_LINES:
            old = self.lines.pop(0)
            self.vbox.removeWidget(old)
            old.deleteLater()

    def _range_changed(self, _min, mx):
        if self._stick:
            self.verticalScrollBar().setValue(mx)

    def rename(self, idx: int, name: str):
        for w in self.lines:
            if w.idx == idx:
                w.set_name(name)

    def clear(self):
        for w in self.lines:
            self.vbox.removeWidget(w)
            w.deleteLater()
        self.lines = []
        self._reset_layout(show_placeholder=True)


# ============================================================================ dialogs

class SettingsDialog(QDialog):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(430)
        form = QFormLayout(self)
        form.setContentsMargins(22, 20, 22, 16)
        form.setVerticalSpacing(14)

        def hint(text):
            h = QLabel(text)
            h.setStyleSheet(f"color:{GREY}; font-size:12px; font-weight:400;")
            return h

        self.threads = QSpinBox()
        self.threads.setRange(1, max(2, os.cpu_count() or 4))
        self.threads.setValue(int(cfg["cpu_threads"]))
        form.addRow("CPU threads for translating", self.threads)
        form.addRow("", hint("Fewer = lighter on your game, slower captions."))

        self.match = QSlider(Qt.Orientation.Horizontal)
        self.match.setRange(70, 95)
        self.match.setValue(int(round(float(cfg["threshold"]) * 100)))
        form.addRow("Voice matching (loose ↔ strict)", self.match)
        form.addRow("", hint("Two people merged into one? Slide right.\n"
                             "One person split into many? Slide left."))

        self.font = QSlider(Qt.Orientation.Horizontal)
        self.font.setRange(13, 34)
        self.font.setValue(int(cfg["font_size"]))
        form.addRow("Text size", self.font)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        logs = QPushButton("Open log folder")
        logs.clicked.connect(lambda: _open_folder(config.app_dir()))
        btns.addButton(logs, QDialogButtonBox.ButtonRole.HelpRole)
        form.addRow(btns)


def _open_folder(path: str):
    from PyQt6.QtCore import QUrl
    from PyQt6.QtGui import QDesktopServices
    QDesktopServices.openUrl(QUrl.fromLocalFile(path))


# ============================================================================ main window

def _caption(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setObjectName("caption")
    return lbl


def _labeled(caption: str, widget: QWidget) -> QVBoxLayout:
    box = QVBoxLayout()
    box.setSpacing(3)
    box.addWidget(_caption(caption))
    box.addWidget(widget)
    return box


class MainWindow(QMainWindow):
    devices_ready = pyqtSignal(list)

    def __init__(self, cfg: dict, engine: Engine):
        super().__init__()
        self.cfg, self.engine = cfg, engine
        self.setWindowTitle("Party Line · VOIP Translator")
        self.setMinimumSize(840, 520)
        self.resize(1000, 690)
        if cfg.get("geometry"):
            self.restoreGeometry(QByteArray.fromBase64(cfg["geometry"].encode()))

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(20, 12, 20, 12)
        outer.setSpacing(8)

        # --- header: logo + instrument cluster
        head = QHBoxLayout()
        self.logo = RacingLogo()
        head.addWidget(self.logo, 1, alignment=Qt.AlignmentFlag.AlignVCenter)
        cluster = QVBoxLayout()
        cluster.setSpacing(6)
        self.lag = SegmentReadout("LAG", "SEC")
        self.lamp = WarningLamp("LIVE")
        cluster.addStretch()
        cluster.addWidget(self.lag)
        cluster.addWidget(self.lamp)
        cluster.addStretch()
        head.addLayout(cluster)
        head.addSpacing(10)
        self.tach = Tachometer()
        head.addWidget(self.tach)
        outer.addLayout(head)
        outer.addWidget(GradationStrip())

        # --- drivers on the line
        crew = QHBoxLayout()
        crew.setSpacing(8)
        crew.addWidget(_caption("On the line"))
        self.chips_box = QHBoxLayout()
        self.chips_box.setSpacing(4)
        crew.addLayout(self.chips_box)
        crew.addStretch()
        new_match = SlantButton("NEW MATCH", kind="ghost", px=11, pad=12, vpad=4, skew=7)
        new_match.setToolTip("Clear the transcript and forget all voices")
        new_match.clicked.connect(self.new_match)
        crew.addWidget(new_match)
        outer.addLayout(crew)

        # --- transcript
        self.transcript = Transcript()
        self.transcript.set_font_size(int(cfg["font_size"]))
        outer.addWidget(self.transcript, 1)
        outer.addWidget(LiveryStripes())

        # --- dash controls
        bar = QFrame()
        bar.setObjectName("dash")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(14, 10, 14, 12)
        bl.setSpacing(10)
        self.start_btn = SlantButton("START LISTENING", kind="start", px=16, pad=22, vpad=12,
                                     skew=14)
        self.start_btn.setFixedWidth(180)
        self.start_btn.clicked.connect(self.toggle)
        bl.addWidget(self.start_btn, alignment=Qt.AlignmentFlag.AlignBottom)

        self.model_box = QComboBox()
        for key, label in MODELS:
            self.model_box.addItem(label, key)
        self.model_box.setCurrentIndex(max(0, self.model_box.findData(cfg["model"])))
        self.model_box.currentIndexChanged.connect(self._model_changed)
        bl.addLayout(_labeled("Model", self.model_box))

        self.lang_box = QComboBox()
        for key, label in LANGS:
            self.lang_box.addItem(label, key)
        self.lang_box.setCurrentIndex(max(0, self.lang_box.findData(cfg["only_lang"])))
        self.lang_box.currentIndexChanged.connect(self._lang_changed)
        bl.addLayout(_labeled("Translate", self.lang_box))

        self.dev_box = QComboBox()
        self.dev_box.addItem("Default output", "")
        if cfg["device"]:
            self.dev_box.addItem(cfg["device"], cfg["device"])
            self.dev_box.setCurrentIndex(1)
        self.dev_box.currentIndexChanged.connect(self._device_changed)
        bl.addLayout(_labeled("Listen to", self.dev_box), 1)

        gear = SlantButton("SETTINGS", kind="steel", px=12, pad=12, vpad=6, skew=8)
        gear.clicked.connect(self.open_settings)
        bl.addWidget(gear, alignment=Qt.AlignmentFlag.AlignBottom)
        outer.addWidget(bar)

        self.status = QLabel()
        self.status.setObjectName("status")
        outer.addWidget(self.status)

        # --- wiring
        engine.line.connect(self.on_line)
        engine.status.connect(self.on_status)
        engine.level.connect(self.tach.set_level)
        engine.running.connect(self.on_running)
        engine.speakers_changed.connect(self.refresh_chips)
        self.devices_ready.connect(self._fill_devices)
        threading.Thread(target=self._list_devices, daemon=True).start()

        self._update_subtitle()
        self.on_status("idle", "Ready when you are. Pick a model and hit START LISTENING.")

    # ---------------------------------------------------------------- engine events
    def on_line(self, entry: dict):
        self.transcript.add(entry, show_lang=not self.cfg["only_lang"])
        if "dt" in entry:
            self.lag.set_value(SegmentReadout.fmt(entry["dt"]))

    def on_status(self, kind: str, msg: str):
        dot = {"live": "#3CFF7A", "busy": AMBER, "error": RED_HI}.get(kind, DIMGREY)
        self.status.setText(f'<span style="color:{dot}">■</span>&nbsp; '
                            f'{html.escape(msg, quote=False)}')

    def on_running(self, running: bool):
        self.lamp.set_lit(running)
        self.tach.set_live(running)
        self.start_btn.setText("STOP" if running else "START LISTENING")
        self.start_btn.set_kind("live" if running else "start")

    def refresh_chips(self):
        while self.chips_box.count():
            w = self.chips_box.takeAt(0).widget()
            if w:
                w.deleteLater()
        speakers = self.engine.speakers()
        if not speakers:
            none = QLabel("nobody yet")
            none.setStyleSheet(f"color:{DIMGREY}; font-size:13px; font-style:italic;")
            self.chips_box.addWidget(none)
        for s in speakers:
            b = SlantButton(s.name.upper(), kind="tag", color=speaker_color(s.idx), px=12,
                            pad=11, vpad=3, skew=7)
            b.setToolTip("Click to rename")
            b.clicked.connect(lambda _=False, i=s.idx, n=s.name: self.rename(i, n))
            self.chips_box.addWidget(b)

    # ---------------------------------------------------------------- actions
    def toggle(self):
        if self.engine.is_running:
            self.engine.stop()
        else:
            self.engine.start()

    def new_match(self):
        self.transcript.clear()
        self.lag.set_value("!-.-")
        self.engine.reset_speakers()

    def rename(self, idx: int, current: str):
        name, ok = QInputDialog.getText(self, "Name this driver", "Who's this?", text=current)
        if ok and name.strip():
            self.engine.rename_speaker(idx, name.strip()[:24])
            self.transcript.rename(idx, name.strip()[:24])

    def open_settings(self):
        dlg = SettingsDialog(self.cfg, self)
        if dlg.exec():
            restart = dlg.threads.value() != int(self.cfg["cpu_threads"])
            self.cfg["cpu_threads"] = dlg.threads.value()
            self.cfg["threshold"] = dlg.match.value() / 100
            self.cfg["font_size"] = dlg.font.value()
            self.transcript.set_font_size(self.cfg["font_size"])
            self.engine.apply_live_settings()
            config.save(self.cfg)
            if restart:
                self.engine.restart()

    def _model_changed(self):
        self.cfg["model"] = self.model_box.currentData()
        config.save(self.cfg)
        self.engine.restart()

    def _lang_changed(self):
        self.cfg["only_lang"] = self.lang_box.currentData()
        config.save(self.cfg)
        self._update_subtitle()
        self.engine.apply_live_settings()

    def _device_changed(self):
        self.cfg["device"] = self.dev_box.currentData() or ""
        config.save(self.cfg)
        self.engine.restart()

    def _update_subtitle(self):
        self.logo.set_subtitle(self.lang_box.currentText().upper())

    def _list_devices(self):
        try:
            self.devices_ready.emit(list_output_devices())
        except Exception:  # noqa: BLE001
            self.devices_ready.emit([])

    def _fill_devices(self, names: list):
        cur = self.cfg["device"]
        self.dev_box.blockSignals(True)
        self.dev_box.clear()
        self.dev_box.addItem("Default output", "")
        for n in names:
            self.dev_box.addItem(n, n)
        if cur and self.dev_box.findData(cur) < 0:
            self.dev_box.addItem(cur, cur)
        self.dev_box.setCurrentIndex(max(0, self.dev_box.findData(cur)))
        self.dev_box.blockSignals(False)

    def closeEvent(self, e):
        self.cfg["geometry"] = bytes(self.saveGeometry().toBase64()).decode()
        config.save(self.cfg)
        self.engine.stop()
        super().closeEvent(e)


def make_icon() -> QIcon:
    path = os.path.join(ASSETS, "icon.png")
    return QIcon(path) if os.path.exists(path) else QIcon()


def apply_style(app):
    load_fonts()
    arrow = os.path.join(ASSETS, "arrow.svg").replace("\\", "/")
    app.setStyleSheet(QSS.replace("__ARROW__", arrow))
    app.setWindowIcon(make_icon())
