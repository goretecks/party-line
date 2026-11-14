"""Draws the app icon (assets/icon.png + icon.ico) with Qt, in the app's own fonts."""
import os
import sys

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QApplication

A = os.path.join(os.path.dirname(__file__), "..", "voip_translator", "assets")
app = QApplication(sys.argv)
QFontDatabase.addApplicationFont(os.path.join(A, "fonts", "Yellowtail-Regular.ttf"))
S = 256
img = QImage(S, S, QImage.Format.Format_ARGB32)
img.fill(Qt.GlobalColor.transparent)
p = QPainter(img)
p.setRenderHint(QPainter.RenderHint.Antialiasing)
r = QRectF(8, 8, S - 16, S - 16)
p.setPen(Qt.PenStyle.NoPen)
p.setBrush(QColor("#121C26"))
p.drawRoundedRect(r, 52, 52)
clip = QPainterPath()
clip.addRoundedRect(r, 52, 52)
p.setClipPath(clip)
sq = 20
for row in range(2):  # checker strip
    for i in range(S // sq + 1):
        p.fillRect(i * sq, S - 8 - 2 * sq + row * sq, sq, sq,
                   QColor("#F3E6C8" if (i + row) % 2 else "#0B1117"))
p.setClipping(False)
for w, a in ((22, 40), (14, 70), (8, 120)):  # neon ring glow
    c = QColor("#FF5C6C"); c.setAlpha(a)
    p.setPen(QPen(c, w)); p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(r.adjusted(14, 14, -14, -14), 40, 40)
p.setPen(QPen(QColor("#FFD9DC"), 4))
p.drawRoundedRect(r.adjusted(14, 14, -14, -14), 40, 40)
f = QFont("Yellowtail", 78)
p.setFont(f)
for off, col in ((5, QColor(255, 92, 108, 110)), (0, QColor("#FFF1E8"))):
    p.setPen(col)
    p.drawText(QRectF(off - 6, off - 6, S, S - 40), Qt.AlignmentFlag.AlignCenter, "PL")
p.end()
img.save(os.path.join(A, "icon.png"))
from PIL import Image
Image.open(os.path.join(A, "icon.png")).save(
    os.path.join(A, "icon.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("icon written")
