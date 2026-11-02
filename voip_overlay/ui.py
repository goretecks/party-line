"""Transparent, always-on-top, click-through caption strip."""
from __future__ import annotations

import html
import sys
import time

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QGuiApplication
from PyQt6.QtWidgets import (QGraphicsDropShadowEffect, QLabel, QTextBrowser,
                             QVBoxLayout, QWidget)

COLORS = ["#4FC3F7", "#FFB74D", "#81C784", "#F06292", "#BA68C8",
          "#FFF176", "#4DB6AC", "#E57373", "#90A4AE", "#A1887F"]


def pick_screen(index: int | None):
    """1-based monitor index (as shown at startup); None = primary."""
    screens = QGuiApplication.screens()
    primary = QGuiApplication.primaryScreen()
    for i, s in enumerate(screens, 1):
        g = s.geometry()
        print(f"[ui] screen {i}: {s.name()} {g.width()}x{g.height()}"
              + (" (primary)" if s is primary else ""))
    if index is None:
        return primary
    if not 1 <= index <= len(screens):
        print(f"[ui] screen {index} not found ({len(screens)} connected); using primary")
        return primary
    return screens[index - 1]


def format_line(idx: int, name: str, lang: str, text: str, target_lang: str, font_size: int) -> str:
    color = COLORS[idx % len(COLORS)]
    tag = (f' <span style="color:#999999;font-size:{int(font_size * .7)}px">'
           f'[{html.escape(lang)}]</span>') if lang and lang != target_lang else ""
    return (f'<span style="color:{color};font-weight:700">{html.escape(name)}</span>'
            f'{tag}<span style="color:white">: {html.escape(text)}</span>')


class Bridge(QObject):
    """Thread-safe hop from the worker thread into the Qt GUI thread."""
    line = pyqtSignal(int, str, str, str)   # speaker idx, name, lang, text


class Overlay(QWidget):
    def __init__(self, max_lines=4, ttl=8.0, font_size=18, width_frac=0.6,
                 position="top", target_lang="en", screen=None):
        super().__init__()
        self.max_lines, self.ttl, self.target_lang = max_lines, ttl, target_lang
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool
                            | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        scr = pick_screen(screen).geometry()
        w = int(scr.width() * width_frac)
        h = int(max_lines * font_size * 2.6)
        y = scr.top() + 20 if position == "top" else scr.bottom() - h - 80
        self.setGeometry(scr.left() + (scr.width() - w) // 2, y, w, h)

        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(0, 0, 0, 0)
        self.layout_.setSpacing(4)
        self.layout_.setAlignment(Qt.AlignmentFlag.AlignTop if position == "top"
                                  else Qt.AlignmentFlag.AlignBottom)
        self.font_size = font_size
        self.lines: list[tuple[float, QLabel]] = []

        t = QTimer(self)
        t.timeout.connect(self._prune)
        t.start(500)
        self.show()
        if sys.platform == "win32":
            self._win32_click_through()

    def _win32_click_through(self):
        # Belt-and-braces: make sure Windows passes clicks through to the game.
        import ctypes
        GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_NOACTIVATE = -20, 0x80000, 0x20, 0x08000000
        hwnd = int(self.winId())
        u32 = ctypes.windll.user32
        style = u32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        u32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE)

    def add_line(self, idx: int, name: str, lang: str, text: str):
        lbl = QLabel(format_line(idx, name, lang, text, self.target_lang, self.font_size))
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"background: rgba(0,0,0,140); border-radius: 6px;"
                          f"padding: 4px 10px; font-size: {self.font_size}px;")
        shadow = QGraphicsDropShadowEffect(lbl)
        shadow.setBlurRadius(6)
        shadow.setOffset(1, 1)
        shadow.setColor(QColor(0, 0, 0, 220))
        lbl.setGraphicsEffect(shadow)
        self.layout_.addWidget(lbl)
        self.lines.append((time.monotonic(), lbl))
        while len(self.lines) > self.max_lines:
            self._remove(0)
        self.raise_()

    def _remove(self, i: int):
        _, lbl = self.lines.pop(i)
        self.layout_.removeWidget(lbl)
        lbl.deleteLater()

    def _prune(self):
        now = time.monotonic()
        while self.lines and now - self.lines[0][0] > self.ttl:
            self._remove(0)
        if self.lines:
            self.raise_()  # games sometimes steal topmost; re-assert it


class Panel(QWidget):
    """Plain scrolling transcript window, meant for a second monitor while the game
    runs in exclusive fullscreen on the main one. Keeps history; nothing fades."""

    def __init__(self, font_size=20, target_lang="en", screen=None, history=300):
        super().__init__()
        self.font_size, self.target_lang = font_size, target_lang
        self.setWindowTitle("VOIP Translator")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)  # don't steal focus from the game
        self.setStyleSheet("background:#111418;")
        self.view = QTextBrowser()
        self.view.setStyleSheet(f"QTextBrowser{{background:#111418;color:white;border:none;"
                                f"font-size:{font_size}px;padding:12px;}}")
        self.view.document().setMaximumBlockCount(history)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.view)

        g = pick_screen(screen).availableGeometry()
        self.setGeometry(g.x() + 40, g.y() + 40, int(g.width() * 0.5), int(g.height() * 0.6))
        self.show()

    def add_line(self, idx: int, name: str, lang: str, text: str):
        ts = time.strftime("%H:%M:%S")
        bar = self.view.verticalScrollBar()
        at_bottom = bar.value() >= bar.maximum() - 4
        self.view.append(f'<p style="margin:0 0 8px 0"><span style="color:#666;'
                         f'font-size:{int(self.font_size * .7)}px">{ts}</span>&nbsp; '
                         + format_line(idx, name, lang, text, self.target_lang, self.font_size)
                         + "</p>")
        if at_bottom:  # only autoscroll if you weren't reading back
            bar.setValue(bar.maximum())
