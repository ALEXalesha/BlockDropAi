"""Вид страниц «Настройки» и «Статистика» BlockDrop - «неоновый игровой зал», как стартовое меню
(правило автора 17.10: настройки и статистика у каждой игры свои).

Фон страниц - неподвижный зал: неоновый пол в перспективе с полосой горизонта и застывшие фигуры у
краёв. Карточки - экраны автоматов со светящейся неоновой рамкой (glow), кнопки - толстые
аркадные с нижней гранью (arcade), переключатели - пилюли; заголовок - буквы цвета фигур с объёмной
тенью, как в меню; числа - Consolas, подписи - Trebuchet MS.

Механизм общий (aikit.skin), здесь - только стиль BlockDrop.
"""
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QLinearGradient, QPen

from aikit.skin import Skin
from game.core import blocks as B
from game.ui.menu import PIECE_COLORS, paint_floor
from game.ui.menu import palette as arcade_palette


def _pal(name):
    a = arcade_palette(name)
    (btn, btn_lo, btn_t), (b2, _, _), _ = a["buttons"]
    dark = name == "dark"
    # светлый зал - «леденцовый»: экраны автоматов розовые, а не белые (иначе карточки как у общей светлой темы)
    return {"bg": a["bg"], "surface": a["well"] if dark else "#fbdcee", "surface2": a["bg2"], "border": a["panel_line"],
            "text": a["text"], "muted": a["muted"], "accent": a["neon"], "accent_text": "#ffffff",
            "good": "#3cbf5a", "bad": "#e04848", "warn": btn, "grid": a["grid_line"],
            "button": "#5a3c8f" if dark else "#b9a0e8", "button_text": "#ffffff" if dark else "#2a1840",
            "field": a["bg2"], "stripe": a["neon2"]}


class ArcadeSkin(Skin):
    key = "blockdrop-arcade"
    palettes = {"dark": _pal("dark"), "light": _pal("light")}
    heading_family = "Segoe UI"
    heading_px = 40
    heading_weight = QFont.Weight.Black
    heading_upper = True
    heading_spacing = 0.03
    section_family = "Segoe UI"
    section_color = "accent"
    body_family = "Trebuchet MS"
    mono_family = "Consolas"
    radius = 18
    control_radius = 14
    card_style = "glow"
    button_style = "arcade"
    card_alpha = 235

    def extra_qss(self, p, theme):
        a = arcade_palette(theme)
        (btn, btn_lo, btn_t), _, _ = a["buttons"]
        return f"""
QLabel#section {{ font-weight: 900; }}
QLabel#tileValue {{ color: {a['neon2']}; }}
QLabel#skinTag {{ color: {a['neon2']}; }}
QLabel#skinGroup {{ color: {a['neon2']}; }}
QPushButton {{ font-family: "Segoe UI"; font-weight: 900; }}
QPushButton#primary {{ background: {btn}; color: {btn_t}; border-bottom-color: {btn_lo}; }}
QPushButton#seg {{ border-radius: 14px; border: 2px solid {a['neon']}; background: transparent; }}
QPushButton#seg:checked {{ background: {a['neon']}; color: #ffffff; }}
QHeaderView::section {{ font-family: "Segoe UI"; font-weight: 900; border-bottom: 2px solid {a['neon2']}; }}
QTableWidget {{ font-family: "Consolas"; }}
"""

    def paint_backdrop(self, p, w, h, pal, theme):
        a = arcade_palette(theme)
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0, QColor(a["bg"]))
        g.setColorAt(0.7, QColor(a["bg2"]))
        g.setColorAt(1, QColor(a["bg"]))
        p.fillRect(0, 0, w, h, g)
        paint_floor(p, w, h, 0.35, a)
        c = max(16.0, h / 34.0)
        for i, (kind, rot, fx, fy) in enumerate(((0, 1, 0.012, 0.18), (5, 0, 0.955, 0.10), (2, 2, 0.94, 0.44),
                                                  (3, 0, 0.015, 0.52), (6, 1, 0.96, 0.78), (1, 3, 0.02, 0.84))):
            col = QColor(PIECE_COLORS[kind])
            x, y = fx * w, fy * h
            for cx, cy in B.CELLS[kind][rot]:
                r = QRectF(x + cx * c - (c * 3 if fx > 0.5 else 0), y + (3 - cy) * c, c, c).adjusted(1, 1, -1, -1)
                fill = QColor(col)
                fill.setAlpha(110 if theme == "dark" else 150)
                p.setPen(QPen(QColor(col.red(), col.green(), col.blue(), 50), 4))
                p.setBrush(fill)
                p.drawRoundedRect(r, c * 0.18, c * 0.18)

    def paint_heading(self, p, rect, text, font, pal, align):
        """Буквы цвета фигур с объёмной тенью - как заголовок меню."""
        p.setFont(font)
        fm = QFontMetricsF(font)
        x = rect.x()
        base = rect.y() + (rect.height() + fm.ascent() - fm.descent()) / 2
        depth = max(2.0, font.pixelSize() * 0.07)
        shade = QColor("#07040f" if pal["bg"] == _pal("dark")["bg"] else "#d9c3a8")
        k = 0
        for ch in text:
            adv = fm.horizontalAdvance(ch)
            if not ch.isspace():
                p.setPen(shade)
                p.drawText(QPointF(x + depth, base + depth), ch)
                p.setPen(QColor(PIECE_COLORS[k % 7]))
                p.drawText(QPointF(x, base), ch)
                k += 1
            x += adv


SKIN = ArcadeSkin()
