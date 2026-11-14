"""Draws the app icon (assets/icon.png + icon.ico) with Qt, in the app's own fonts."""
import os
import sys

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter, QPainterPath, QPolygonF
from PyQt6.QtWidgets import QApplication

A = os.path.join(os.path.dirname(__file__), "..", "voip_translator", "assets")
app = QApplication(sys.argv)
QFontDatabase.addApplicationFont(os.path.join(A, "fonts", "ChakraPetch-BoldItalic.ttf"))
S = 256
img = QImage(S, S, QImage.Format.Format_ARGB32)
img.fill(Qt.GlobalColor.transparent)
p = QPainter(img)
p.setRenderHint(QPainter.RenderHint.Antialiasing)
r = QRectF(8, 8, S - 16, S - 16)
p.setPen(Qt.PenStyle.NoPen)
p.setBrush(QColor("#0C0D10"))
p.drawRoundedRect(r, 40, 40)
clip = QPainterPath()
clip.addRoundedRect(r, 40, 40)
p.setClipPath(clip)
# diagonal livery stripes across the lower right
for off, width, col in ((0, 26, "#E10600"), (32, 8, "#F2F2F0"), (46, 26, "#1446C8")):
    y = 150 + off
    p.setBrush(QColor(col))
    p.drawPolygon(QPolygonF([QPointF(0, y + 60), QPointF(S, y - 40),
                             QPointF(S, y - 40 + width), QPointF(0, y + 60 + width)]))
p.setClipping(False)
f = QFont("Chakra Petch")
f.setPixelSize(118)
f.setBold(True)
f.setItalic(True)
p.setFont(f)
box = QRectF(0, 14, S, 150)
for d, col in ((9, "#1446C8"), (5, "#E10600"), (0, "#FFFFFF")):
    p.setPen(QColor(col))
    p.drawText(box.translated(d, d * 0.6), Qt.AlignmentFlag.AlignCenter, "PL")
p.end()
img.save(os.path.join(A, "icon.png"))
from PIL import Image
Image.open(os.path.join(A, "icon.png")).save(
    os.path.join(A, "icon.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("icon written")
