"""The single-window UI: retro-diner styled transcript + controls."""
from __future__ import annotations

import html
import math
import os
import threading
import time

from PyQt6.QtCore import QByteArray, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (QColor, QFont, QFontDatabase, QIcon, QLinearGradient, QPainter,
                         QPainterPath, QPen, QPixmap, QRadialGradient)
from PyQt6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame,
                             QGraphicsDropShadowEffect, QHBoxLayout, QInputDialog, QLabel,
                             QMainWindow, QPushButton, QScrollArea, QSizePolicy, QSlider,
                             QSpinBox, QVBoxLayout, QWidget)

from . import config
from .audio import list_output_devices
from .engine import Engine

ASSETS = os.path.join(os.path.dirname(__file__), "assets")

# Diner-after-dark palette
NIGHT, PANEL, PANEL2 = "#121C26", "#1A2834", "#223443"
CREAM, DIM, INK = "#F3E6C8", "#8FA1AE", "#14202B"
CHERRY, NEON, TEAL, MUSTARD = "#D93445", "#FF5C6C", "#3EC6B8", "#F2B33D"
SPEAKER_COLORS = ["#3EC6B8", "#F2B33D", "#FF7A8A", "#7EC8F2", "#9BE3C2",
                  "#F28C3D", "#C7A2F0", "#F3E6C8"]

MODELS = [("tiny", "Tiny · fastest, rough"), ("base", "Base · quick"),
          ("small", "Small · balanced (best pick)"), ("medium", "Medium · sharper, heavier"),
          ("large-v3", "Large · best, very heavy")]
LANGS = [("es", "Spanish  »  English"), ("pt", "Portuguese  »  English"),
         ("fr", "French  »  English"), ("de", "German  »  English"),
         ("it", "Italian  »  English"), ("ru", "Russian  »  English"),
         ("", "Any language  »  English")]

SCRIPT, DISPLAY, TYPE = "Yellowtail", "Oswald", "Courier Prime"


def load_fonts():
    fdir = os.path.join(ASSETS, "fonts")
    for f in os.listdir(fdir):
        if f.endswith(".ttf"):
            QFontDatabase.addApplicationFont(os.path.join(fdir, f))


def speaker_color(idx: int) -> str:
    return SPEAKER_COLORS[idx % len(SPEAKER_COLORS)]


QSS = f"""
QMainWindow, #root {{ background: {NIGHT}; }}
QLabel {{ color: {CREAM}; }}
#caption {{ font-family: '{DISPLAY}'; font-size: 11px; letter-spacing: 2px; color: {DIM}; }}
#status {{ font-family: '{TYPE}'; font-size: 13px; color: {DIM}; }}
#transcript {{ background: {PANEL}; border: 2px solid {PANEL2}; border-radius: 14px; }}
#transcript QWidget#lines {{ background: transparent; }}
#placeholder {{ font-family: '{TYPE}'; color: {DIM}; font-size: 15px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 8px 2px; }}
QScrollBar::handle:vertical {{ background: {PANEL2}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

#chromebar {{
  border-top: 1px solid #FFFFFF;
  background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
      stop:0 #EEF1F3, stop:0.45 #C9D0D5, stop:0.55 #B4BDC4, stop:1 #DCE1E5);
  border-radius: 16px;
}}
#chromebar QLabel#caption {{ color: #3B4A56; }}
QComboBox {{
  font-family: '{DISPLAY}'; font-size: 14px; color: {CREAM};
  background: {INK}; border: 2px solid #5D6B76; border-radius: 10px;
  padding: 5px 26px 5px 12px; min-width: 105px;
}}
QComboBox:hover {{ border-color: {TEAL}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ image: url(__ARROW__); width: 12px; height: 8px; margin-right: 8px; }}
QComboBox QAbstractItemView {{
  font-family: '{DISPLAY}'; font-size: 14px; background: {INK}; color: {CREAM};
  selection-background-color: {CHERRY}; border: 1px solid #5D6B76; outline: 0; padding: 4px;
}}
#startBtn {{
  font-family: '{DISPLAY}'; font-size: 17px; font-weight: 600; letter-spacing: 2px;
  color: {CREAM}; background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #EE5363, stop:1 #B9273A);
  border: 3px solid #7E1B28; border-radius: 24px; padding: 10px 20px;
}}
#startBtn:hover {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #FF6676, stop:1 #CC3045); }}
#startBtn[live="true"] {{
  color: {INK}; background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #6FE0D3, stop:1 #2FA597);
  border-color: #1D6E65;
}}
#roundBtn {{
  font-family: '{DISPLAY}'; font-size: 12px; letter-spacing: 1px; color: #2C3A45;
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #FFFFFF, stop:1 #BFC7CD);
  border: 2px solid #7F8A93; border-radius: 15px; padding: 5px 12px;
}}
#roundBtn:hover {{ border-color: {CHERRY}; color: {CHERRY}; }}
#chip {{
  min-width: 80px; font-family: '{DISPLAY}'; font-size: 13px; font-weight: 600; letter-spacing: 1px;
  border-radius: 12px; padding: 3px 12px; color: {INK};
}}
#ghostBtn {{
  font-family: '{DISPLAY}'; font-size: 12px; letter-spacing: 1px; color: {DIM};
  background: transparent; border: 1px solid {PANEL2}; border-radius: 12px; padding: 3px 12px;
}}
#ghostBtn:hover {{ color: {CREAM}; border-color: {DIM}; }}
QDialog {{ background: {PANEL}; }}
QDialog QLabel {{ font-family: '{DISPLAY}'; font-size: 14px; }}
QSpinBox {{ font-family: '{DISPLAY}'; font-size: 14px; color: {CREAM}; background: {INK};
  border: 2px solid #5D6B76; border-radius: 8px; padding: 3px 8px; }}
QSlider::groove:horizontal {{ height: 6px; background: {INK}; border-radius: 3px; }}
QSlider::handle:horizontal {{ width: 18px; margin: -7px 0; border-radius: 9px;
  background: qradialgradient(cx:0.4, cy:0.35, radius:0.8, stop:0 #FFFFFF, stop:1 #9AA5AE); }}
QSlider::sub-page:horizontal {{ background: {TEAL}; border-radius: 3px; }}
QDialogButtonBox QPushButton, QInputDialog QPushButton {{
  font-family: '{DISPLAY}'; font-size: 13px; color: {INK}; background: {CREAM};
  border: none; border-radius: 10px; padding: 6px 18px; min-width: 70px; }}
QInputDialog QLineEdit {{ font-family: '{TYPE}'; font-size: 15px; color: {CREAM};
  background: {INK}; border: 2px solid {TEAL}; border-radius: 8px; padding: 4px 8px; }}
"""


# ============================================================================ decorations

class CheckerBand(QWidget):
    """Black-and-cream diner floor tiles."""

    def __init__(self, size=9, parent=None):
        super().__init__(parent)
        self.size_ = size
        self.setFixedHeight(size * 2)

    def paintEvent(self, _):
        p = QPainter(self)
        s = self.size_
        for row in range(2):
            for i in range(self.width() // s + 1):
                p.fillRect(i * s, row * s, s, s,
                           QColor(CREAM if (i + row) % 2 else "#0B1117"))


class NeonTitle(QLabel):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setFont(QFont(SCRIPT, 40))
        self.setStyleSheet(f"color: #FFD9DC;")
        glow = QGraphicsDropShadowEffect(self)
        glow.setBlurRadius(28)
        glow.setOffset(0, 0)
        glow.setColor(QColor(NEON))
        self.setGraphicsEffect(glow)
        self._glow = glow
        self._t = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._flicker)
        self._timer.start(80)

    def _flicker(self):
        # A gentle neon hum, with the occasional stutter.
        self._t += 0.08
        base = 24 + 6 * math.sin(self._t * 2.1)
        if int(self._t * 100) % 977 < 4:
            base = 6
        self._glow.setBlurRadius(base)


class OnAirSign(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.live = False
        self.setFixedSize(108, 40)
        self._pulse = 0.0
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(60)

    def set_live(self, live: bool):
        self.live = live
        self.update()

    def _tick(self):
        if self.live:
            self._pulse += 0.12
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(4, 4, self.width() - 8, self.height() - 8)
        if self.live:
            a = 0.75 + 0.25 * math.sin(self._pulse)
            for i in range(4, 0, -1):  # glow
                c = QColor(NEON)
                c.setAlphaF(0.10 * a)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(c)
                p.drawRoundedRect(r.adjusted(-i, -i, i, i), 10 + i, 10 + i)
            g = QLinearGradient(0, r.top(), 0, r.bottom())
            g.setColorAt(0, QColor("#FF6B78"))
            g.setColorAt(1, QColor("#C2283A"))
            p.setBrush(g)
            p.setPen(QPen(QColor("#FFC2C8"), 2))
            txt = QColor("#FFF4E6")
        else:
            p.setBrush(QColor("#2A1C22"))
            p.setPen(QPen(QColor("#4A2D35"), 2))
            txt = QColor("#5E3B44")
        p.drawRoundedRect(r, 10, 10)
        f = QFont(DISPLAY, 13)
        f.setWeight(QFont.Weight.DemiBold)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3)
        p.setFont(f)
        p.setPen(txt)
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, "ON AIR")


class VUMeter(QWidget):
    """Analog needle meter with a bit of ballistics."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(150, 78)
        self.target = 0.0
        self.value = 0.0
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(33)

    def set_level(self, v: float):
        self.target = v

    def _tick(self):
        # fast attack, slow release
        k = 0.45 if self.target > self.value else 0.08
        nv = self.value + (self.target - self.value) * k
        if abs(nv - self.value) > 0.002:
            self.value = nv
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        # chrome bezel
        bez = QLinearGradient(0, 0, 0, h)
        bez.setColorAt(0, QColor("#F4F6F7"))
        bez.setColorAt(0.5, QColor("#9AA5AE"))
        bez.setColorAt(1, QColor("#E3E7EA"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bez)
        p.drawRoundedRect(QRectF(0, 0, w, h), 10, 10)
        face = QRectF(4, 4, w - 8, h - 8)
        fg = QRadialGradient(face.center().x(), face.bottom(), w * 0.8)
        fg.setColorAt(0, QColor("#FFF6DD"))
        fg.setColorAt(1, QColor("#E9D9AE"))
        p.setBrush(fg)
        p.drawRoundedRect(face, 7, 7)

        cx, cy, rad = w / 2, h - 10, h - 24
        a0, a1 = math.radians(145), math.radians(35)
        # scale arcs
        def pt(frac, r):
            a = a0 + (a1 - a0) * frac
            return QPointF(cx + r * math.cos(a), cy - r * math.sin(a))
        for i in range(11):
            frac = i / 10
            red = frac >= 0.75
            p.setPen(QPen(QColor("#C2283A" if red else "#2B2B2B"), 2 if i % 5 == 0 else 1))
            p.drawLine(pt(frac, rad), pt(frac, rad - (8 if i % 5 == 0 else 5)))
        path = QPainterPath()
        steps = 30
        for i in range(steps + 1):
            q = pt(0.75 + 0.25 * i / steps, rad + 2)
            path.moveTo(q) if i == 0 else path.lineTo(q)
        p.setPen(QPen(QColor("#C2283A"), 3))
        p.drawPath(path)
        f = QFont(DISPLAY, 9)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2)
        p.setFont(f)
        p.setPen(QColor("#5A4A2A"))
        p.drawText(QRectF(0, cy - 30, w, 14), Qt.AlignmentFlag.AlignCenter, "VU")
        # needle
        p.setPen(QPen(QColor("#1B1B1B"), 2))
        p.drawLine(QPointF(cx, cy), pt(self.value, rad + 2))
        p.setBrush(QColor("#1B1B1B"))
        p.drawEllipse(QPointF(cx, cy), 4, 4)


# ============================================================================ transcript

class LineWidget(QFrame):
    def __init__(self, entry: dict, show_lang: bool):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 8, 14, 8)
        lay.setSpacing(12)
        ts = QLabel(time.strftime("%H:%M", time.localtime(entry["time"])))
        ts.setFont(QFont(TYPE, 11))
        ts.setStyleSheet(f"color: {DIM};")
        ts.setAlignment(Qt.AlignmentFlag.AlignTop)
        ts.setContentsMargins(0, 5, 0, 0)
        self.badge = QLabel()
        self.badge.setObjectName("chip")
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.idx = entry["idx"]
        self.set_name(entry["name"])
        badge_col = QVBoxLayout()
        badge_col.addWidget(self.badge)
        badge_col.addStretch()
        lang = entry.get("lang") or ""
        tag = (f'<span style="color:{DIM};font-size:11px">[{html.escape(lang, quote=False)}]</span> '
               if show_lang and lang and lang != "en" else "")
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
        self.badge.setStyleSheet(f"background: {speaker_color(self.idx)};")


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
        self.vbox.setSpacing(2)
        self.placeholder = QLabel(
            "Nobody's talking yet.\n\nHit START LISTENING, hop into your match, and any "
            "Spanish your teammates say will show up here in English.\n\n"
            "Click a caller's name tag to give them a name. NEW MATCH clears the board.")
        self.placeholder.setObjectName("placeholder")
        self.placeholder.setWordWrap(True)
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.vbox.addStretch(1)
        self.vbox.addWidget(self.placeholder)
        self.vbox.addStretch(1)
        self.setWidget(self.inner)
        self.lines: list[LineWidget] = []
        self.font_size = 19
        self.verticalScrollBar().rangeChanged.connect(self._range_changed)
        self._stick = True

    def set_font_size(self, px: int):
        self.font_size = px
        self.inner.setStyleSheet(
            f"QLabel#lineText {{ font-family: '{TYPE}'; font-size: {px}px; color: {CREAM}; }}"
            f"QLabel#chip {{ font-size: {max(11, px - 6)}px; }}")

    def add(self, entry: dict, show_lang: bool):
        if self.placeholder.isVisible():
            self.placeholder.hide()
            while self.vbox.count():
                self.vbox.takeAt(0)
            self.vbox.addStretch(1)
        bar = self.verticalScrollBar()
        self._stick = bar.value() >= bar.maximum() - 30
        w = LineWidget(entry, show_lang)
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
        while self.vbox.count():
            self.vbox.takeAt(0)
        self.vbox.addStretch(1)
        self.vbox.addWidget(self.placeholder)
        self.vbox.addStretch(1)
        self.placeholder.show()


# ============================================================================ dialogs

class SettingsDialog(QDialog):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(420)
        form = QFormLayout(self)
        form.setContentsMargins(22, 20, 22, 16)
        form.setVerticalSpacing(14)

        self.threads = QSpinBox()
        self.threads.setRange(1, max(2, os.cpu_count() or 4))
        self.threads.setValue(int(cfg["cpu_threads"]))
        form.addRow("CPU threads for translating", self.threads)
        hint = QLabel("Fewer = lighter on your game, slower captions.")
        hint.setStyleSheet(f"color:{DIM}; font-size:12px;")
        form.addRow("", hint)

        self.match = QSlider(Qt.Orientation.Horizontal)
        self.match.setRange(70, 95)
        self.match.setValue(int(round(float(cfg["threshold"]) * 100)))
        form.addRow("Voice matching (loose ↔ strict)", self.match)
        hint2 = QLabel("Two people merged into one? Slide right.\nOne person split into many? Slide left.")
        hint2.setStyleSheet(f"color:{DIM}; font-size:12px;")
        form.addRow("", hint2)

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
        self.setMinimumSize(820, 500)
        self.resize(1000, 680)
        if cfg.get("geometry"):
            self.restoreGeometry(QByteArray.fromBase64(cfg["geometry"].encode()))

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(22, 14, 22, 14)
        outer.setSpacing(10)

        # --- marquee
        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addWidget(NeonTitle("Party Line"))
        self.subtitle = QLabel()
        self.subtitle.setFont(QFont(DISPLAY, 11))
        self.subtitle.setStyleSheet(f"color: {TEAL}; letter-spacing: 4px;")
        titles.addWidget(self.subtitle)
        head.addLayout(titles)
        head.addStretch()
        self.vu = VUMeter()
        head.addWidget(self.vu)
        head.addSpacing(14)
        self.onair = OnAirSign()
        head.addWidget(self.onair, alignment=Qt.AlignmentFlag.AlignVCenter)
        outer.addLayout(head)
        outer.addWidget(CheckerBand())

        # --- who's on the line
        crew = QHBoxLayout()
        crew.setSpacing(8)
        crew.addWidget(_caption("On the line"))
        self.chips_box = QHBoxLayout()
        self.chips_box.setSpacing(6)
        crew.addLayout(self.chips_box)
        crew.addStretch()
        new_match = QPushButton("NEW MATCH")
        new_match.setObjectName("ghostBtn")
        new_match.setToolTip("Clear the transcript and forget all voices")
        new_match.clicked.connect(self.new_match)
        crew.addWidget(new_match)
        outer.addLayout(crew)

        # --- transcript
        self.transcript = Transcript()
        self.transcript.set_font_size(int(cfg["font_size"]))
        outer.addWidget(self.transcript, 1)

        # --- chrome control bar
        bar = QFrame()
        bar.setObjectName("chromebar")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(16, 10, 16, 12)
        bl.setSpacing(12)
        self.start_btn = QPushButton("START LISTENING")
        self.start_btn.setObjectName("startBtn")
        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_btn.clicked.connect(self.toggle)
        self.start_btn.setFixedWidth(185)
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
        self.dev_box.addItem("System default output", "")
        if cfg["device"]:
            self.dev_box.addItem(cfg["device"], cfg["device"])
            self.dev_box.setCurrentIndex(1)
        self.dev_box.currentIndexChanged.connect(self._device_changed)
        bl.addLayout(_labeled("Listen to", self.dev_box), 1)

        gear = QPushButton("SETTINGS")
        gear.setObjectName("roundBtn")
        gear.setCursor(Qt.CursorShape.PointingHandCursor)
        gear.clicked.connect(self.open_settings)
        bl.addWidget(gear, alignment=Qt.AlignmentFlag.AlignBottom)
        outer.addWidget(bar)

        self.status = QLabel()
        self.status.setObjectName("status")
        outer.addWidget(self.status)

        # --- wiring
        engine.line.connect(self.on_line)
        engine.status.connect(self.on_status)
        engine.level.connect(self.vu.set_level)
        engine.running.connect(self.on_running)
        engine.speakers_changed.connect(self.refresh_chips)
        self.devices_ready.connect(self._fill_devices)
        threading.Thread(target=self._list_devices, daemon=True).start()

        _no_focus_rects(self)
        self._update_subtitle()
        self.on_status("idle", "Ready when you are. Pick a model and hit START LISTENING.")

    # ---------------------------------------------------------------- engine events
    def on_line(self, entry: dict):
        self.transcript.add(entry, show_lang=not self.cfg["only_lang"])

    def on_status(self, kind: str, msg: str):
        dot = {"live": TEAL, "busy": MUSTARD, "error": NEON}.get(kind, DIM)
        self.status.setText(f'<span style="color:{dot}">●</span>&nbsp; {html.escape(msg, quote=False)}')

    def on_running(self, running: bool):
        self.onair.set_live(running)
        self.start_btn.setText("STOP" if running else "START LISTENING")
        self.start_btn.setProperty("live", "true" if running else "false")
        self.start_btn.style().unpolish(self.start_btn)
        self.start_btn.style().polish(self.start_btn)

    def refresh_chips(self):
        while self.chips_box.count():
            w = self.chips_box.takeAt(0).widget()
            if w:
                w.deleteLater()
        speakers = self.engine.speakers()
        if not speakers:
            none = QLabel("nobody yet")
            none.setStyleSheet(f"color:{DIM}; font-family:'{TYPE}'; font-size:13px;")
            self.chips_box.addWidget(none)
        for s in speakers:
            b = QPushButton(s.name.upper())
            b.setObjectName("chip")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setToolTip("Click to rename")
            b.setStyleSheet(f"background: {speaker_color(s.idx)}; border: none;")
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
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
        self.engine.reset_speakers()

    def rename(self, idx: int, current: str):
        name, ok = QInputDialog.getText(self, "Name this caller", "Who's this?", text=current)
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
        label = self.lang_box.currentText().upper()
        self.subtitle.setText(f"VOICE CHAT  ·  {label}")

    def _list_devices(self):
        try:
            self.devices_ready.emit(list_output_devices())
        except Exception:  # noqa: BLE001
            self.devices_ready.emit([])

    def _fill_devices(self, names: list):
        cur = self.cfg["device"]
        self.dev_box.blockSignals(True)
        self.dev_box.clear()
        self.dev_box.addItem("System default output", "")
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


def _no_focus_rects(root: QWidget):
    for b in root.findChildren(QPushButton):
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)


def apply_style(app):
    load_fonts()
    arrow = os.path.join(ASSETS, "arrow.svg").replace("\\", "/")
    app.setStyleSheet(QSS.replace("__ARROW__", arrow))
    app.setWindowIcon(make_icon())
