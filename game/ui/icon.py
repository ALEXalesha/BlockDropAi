"""Иконка программы: фигура из четырёх блоков на фоне поля, тем же кодом, что поле.
Её же собирает в .ico build.py."""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPainterPath, QPixmap

from game.core import blocks as B
from game.ui.board import draw_cell, piece_color


def render(size=256):
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(0, 0, size, size), size * 0.2, size * 0.2)
    p.setClipPath(clip)
    p.fillRect(QRectF(0, 0, size, size), QColor("#1f242e"))
    s = size / 4.4
    ox = (size - 3 * s) / 2
    # нижний ряд: L и S, сверху T - узнаваемая стопка
    cells = [((0, 0), B.L), ((1, 0), B.L), ((2, 0), B.S), ((0, 1), B.L), ((1, 1), B.T), ((2, 1), B.S),
             ((1, 2), B.T)]
    oy = size - s * 0.7
    for (x, y), kind in cells:
        draw_cell(p, QRectF(ox + x * s, oy - (y + 1) * s, s, s), piece_color(kind))
    p.end()
    return img


def app_icon():
    icon = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(QPixmap.fromImage(render(s)))
    return icon
