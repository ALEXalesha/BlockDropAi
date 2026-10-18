"""Стартовое меню «Блоков с ИИ» - «неоновый игровой зал».

Свой стиль (правило автора 17.10: у каждой игры своё меню, и боковые панели тоже): тёмный зал,
внизу - неоновая сетка пола в перспективе, бегущая на зрителя; по бокам падают и поворачиваются
светящиеся фигуры. В центре - заголовок, где каждая буква своего цвета фигуры с объёмной тенью
(Segoe UI, начертание Black), переключатели-«пилюли» с неоновой обводкой и толстые аркадные кнопки трёх
цветов с нижней гранью. Светлая тема - леденцовый зал. Боковая панель партии - как экран
игрового автомата: неоновая рамка, крупные цифры, кнопки той же формы.

Общее из aikit.menu - только живой фон (Backdrop), заголовок Title и законы раскладки.
"""
import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QLinearGradient, QPen
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QVBoxLayout

from aikit.menu import Backdrop, Title
from aikit.widgets import button, fit_segments, label, segmented
from game.core import blocks as B

PALETTES = {
    "dark": {
        "bg": "#0c0918", "bg2": "#1a0f33", "floor": "#ff3fa4", "horizon": "#ff7a3d", "text": "#f6f0ff",
        "muted": "#b9a9d6", "neon": "#ff3fa4", "neon2": "#36e2ff", "panel": "rgba(18, 12, 38, 230)",
        "panel_line": "#5a3c8f", "well": "#120c26", "grid_line": "#2a1d4a", "shade": "#07040f",
        "buttons": (("#ffb020", "#c06d00", "#1a0f00"), ("#36e2ff", "#1588a8", "#04141a"),
                    ("#b06bff", "#6b34b8", "#ffffff")),
    },
    "light": {
        "bg": "#fff3df", "bg2": "#ffe1ef", "floor": "#ff5aa8", "horizon": "#ff9a3d", "text": "#2a1840",
        "muted": "#6b5585", "neon": "#e0287f", "neon2": "#0f9fc4", "panel": "rgba(255, 250, 244, 238)",
        "panel_line": "#e0b3cf", "well": "#fffaf3", "grid_line": "#f0d9e6", "shade": "#d9c3a8",
        "buttons": (("#ffb020", "#c47a00", "#2a1500"), ("#2fc6e8", "#1489a6", "#04202a"),
                    ("#9b55f0", "#6a2fb8", "#ffffff")),
    },
}

PIECE_COLORS = ("#2ec4d6", "#3a6fd8", "#f08a24", "#f2c934", "#3cbf5a", "#a259d9", "#e04848")


def palette(name):
    return PALETTES.get(name, PALETTES["dark"])


def board_palette(base, name):
    """Цвета поля партии: aikit-палитра + стакан и сетка зала (BoardView берёт surface/grid/border)."""
    p = palette(name)
    out = dict(base)
    out.update({"surface": p["well"], "grid": p["grid_line"], "border": p["neon"], "accent": p["neon2"]})
    return out


def rain(seed=7, count=18):
    """Падающие фигуры фона: (вид, полоса 0..1, скорость клеток/с, сдвиг, такт поворота)."""
    rng = random.Random(seed)
    return [(rng.randrange(7), rng.random(), rng.uniform(1.2, 3.2), rng.uniform(0, 40), rng.uniform(1.6, 3.4))
            for _ in range(count)]


def paint_floor(p, w, h, t, pal):
    """Неоновый пол в перспективе и горизонт (фон меню и страниц)."""
    top = h * 0.70
    glow = QLinearGradient(0, top - h * 0.12, 0, top)
    hz = QColor(pal["horizon"])
    hz.setAlpha(0)
    glow.setColorAt(0, hz)
    hz.setAlpha(90)
    glow.setColorAt(1, hz)
    p.fillRect(QRectF(0, top - h * 0.12, w, h * 0.12), glow)
    line = QColor(pal["floor"])
    cx = w / 2
    for k in range(-14, 15):
        line.setAlpha(110)
        p.setPen(QPen(line, 1.6))
        p.drawLine(QPointF(cx + k * w * 0.02, top), QPointF(cx + k * w * 0.16, h))
    phase = (t * 0.6) % 1.0
    for k in range(12):
        f = ((k + phase) / 12.0) ** 2.2           # ближе к зрителю - реже
        y = top + (h - top) * f
        line.setAlpha(round(40 + 150 * f))
        p.setPen(QPen(line, 1.0 + 2.0 * f))
        p.drawLine(QPointF(0, y), QPointF(w, y))
    p.setPen(QPen(QColor(pal["horizon"]), 2.0))
    p.drawLine(QPointF(0, top), QPointF(w, top))


class Arcade(Backdrop):
    """Фон: неоновый пол в перспективе и фигуры, падающие по бокам от середины."""

    FPS = 30

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pieces = rain()
        self.lanes = (0.0, 0.0, 0.0, 0.0)       # (x0, x1) слева и справа, где фигурам можно падать

    def cell(self, h):
        return max(18.0, h / 30.0)

    def piece_boxes(self, w, h, t):
        """Где сейчас фигуры: [(вид, поворот, x, y, клетка)] - и для рисования, и для закона."""
        c = self.cell(h)
        out = []
        l0, l1, r0, r1 = self.lanes
        zones = [z for z in ((l0, l1), (r0, r1)) if z[1] - z[0] >= c * 4.5]
        if not zones:
            return out
        for i, (kind, lane, speed, off, turn) in enumerate(self.pieces):
            z0, z1 = zones[i % len(zones)]
            x = z0 + c * 0.25 + lane * (z1 - z0 - c * 4.5)
            span = h / c + 6
            y = ((t * speed + off) % span - 4) * c
            rot = int((t + off) / turn) % 4
            out.append((kind, rot, x, y, c))
        return out

    def paint_scene(self, p, w, h, t):
        pal = palette(self.theme_name)
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0, QColor(pal["bg"]))
        g.setColorAt(0.7, QColor(pal["bg2"]))
        g.setColorAt(1, QColor(pal["bg"]))
        p.fillRect(0, 0, w, h, g)
        self._floor(p, w, h, t, pal)
        for kind, rot, x, y, c in self.piece_boxes(w, h, t):
            col = QColor(PIECE_COLORS[kind])
            for cx, cy in B.CELLS[kind][rot]:
                r = QRectF(x + cx * c, y + (3 - cy) * c, c, c).adjusted(1.5, 1.5, -1.5, -1.5)
                glow = QColor(col)
                glow.setAlpha(60)
                p.setPen(QPen(glow, 5))
                fill = QColor(col)
                fill.setAlpha(150 if self.theme_name == "dark" else 190)
                p.setBrush(fill)
                p.drawRoundedRect(r, c * 0.18, c * 0.18)
                hi = QColor(255, 255, 255, 70)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(hi)
                p.drawRoundedRect(QRectF(r.x() + 2, r.y() + 2, r.width() - 4, r.height() * 0.3), 2, 2)

    def _floor(self, p, w, h, t, pal):
        paint_floor(p, w, h, t, pal)


class BlockTitle(Title):
    """Заголовок: каждая буква - цвета своей фигуры, с объёмной тенью вниз-вправо."""

    def __init__(self):
        super().__init__("Segoe UI", 72, weight=QFont.Weight.Black, spacing=0.03, min_px=30)
        self.shade = QColor("#07040f")

    def paint_text(self, p, rect, text, font):
        p.setFont(font)
        fm = QFontMetricsF(font)
        x = rect.x() + (rect.width() - fm.horizontalAdvance(text)) / 2
        base = rect.y() + (rect.height() + fm.ascent() - fm.descent()) / 2
        depth = max(2.0, font.pixelSize() * 0.07)
        k = 0
        for ch in text:
            adv = fm.horizontalAdvance(ch)
            if not ch.isspace():
                p.setPen(self.shade)
                p.drawText(QPointF(x + depth, base + depth), ch)
                p.setPen(QColor(PIECE_COLORS[k % 7]))
                p.drawText(QPointF(x, base), ch)
                k += 1
            x += adv


def button_qss(pal, k, scope=""):
    """Аркадные кнопки: толстая нижняя грань (объём), скругление, у каждой свой цвет; пилюли."""
    def px(v):
        return f"{max(1, round(v * k))}px"
    (a, a_lo, a_t), (b, b_lo, b_t), (c, c_lo, c_t) = pal["buttons"]
    s = scope
    return f"""
{s}QPushButton {{
    font-family: "Segoe UI"; font-size: {px(18)}; font-weight: 900;
    padding: {px(10)} {px(22)}; border-radius: {px(14)};
    background: {c}; color: {c_t}; border: none; border-bottom: {px(6)} solid {c_lo};
}}
{s}QPushButton:pressed {{ border-bottom-width: {px(2)}; margin-top: {px(4)}; }}
{s}QPushButton:disabled {{ background: {pal['panel_line']}; color: {pal['muted']}; border-bottom-color: {pal['shade']}; }}
{s}QPushButton#menuPrimary, {s}QPushButton#primary {{ background: {a}; color: {a_t}; border-bottom-color: {a_lo}; }}
{s}QPushButton#arcadeB {{ background: {b}; color: {b_t}; border-bottom-color: {b_lo}; }}
{s}QPushButton#seg {{
    font-family: "Trebuchet MS", "Segoe UI"; font-size: {px(14)}; font-weight: 700;
    padding: {px(5)} {px(12)}; border-radius: {px(14)};
    background: transparent; color: {pal['text']};
    border: {px(2)} solid {pal['neon']}; border-bottom: {px(2)} solid {pal['neon']};
}}
{s}QPushButton#seg:checked {{ background: {pal['neon']}; color: #ffffff; }}
{s}QPushButton#seg:pressed {{ margin-top: 0; }}
"""


def menu_qss(pal, k):
    def px(v):
        return f"{max(1, round(v * k))}px"
    return f"""
QFrame#cabinet {{ background: {pal['panel']}; border: {px(2)} solid {pal['neon2']}; border-radius: {px(18)}; }}
QLabel#arcSub {{ font-family: "Trebuchet MS", "Segoe UI"; font-size: {px(16)}; color: {pal['text']}; }}
QLabel#arcCaption {{ font-family: "Trebuchet MS", "Segoe UI"; font-size: {px(14)}; font-weight: 700; color: {pal['neon2']}; }}
QLabel#arcNote {{ font-family: "Trebuchet MS", "Segoe UI"; font-size: {px(13)}; color: {pal['muted']}; }}
QLabel#arcFoot {{ font-family: "Consolas"; font-size: {px(12)}; color: {pal['muted']}; }}
""" + button_qss(pal, k)


def page_qss(pal):
    """Страница партии: фон зала, крупные неоновые цифры счёта, подписи."""
    return f"""
QWidget#page {{ background: {pal['bg']}; }}
QLabel {{ color: {pal['text']}; }}
QLabel#section {{ font-family: "Segoe UI"; font-weight: 900; font-size: 17px; color: {pal['neon']}; }}
QLabel#muted {{ font-family: "Trebuchet MS", "Segoe UI"; color: {pal['muted']}; }}
QLabel#hint {{ font-family: "Trebuchet MS", "Segoe UI"; font-size: 12px; color: {pal['muted']}; }}
QLabel#bigNumber {{ font-family: "Consolas"; font-size: 26px; font-weight: 700; color: {pal['neon2']}; }}
QLabel#bigNumberSmall {{ font-family: "Consolas"; font-size: 17px; font-weight: 700; color: {pal['neon2']}; }}
"""


def side_qss(pal):
    """Боковая панель - экран игрового автомата."""
    return f"""
QFrame#card {{ background: {pal['panel']}; border: 2px solid {pal['neon']}; border-radius: 18px; }}
QLabel {{ color: {pal['text']}; }}
QLabel#section {{ font-family: "Segoe UI"; font-weight: 900; font-size: 17px; color: {pal['neon2']}; }}
QLabel#status {{ font-family: "Segoe UI"; font-weight: 900; font-size: 20px; color: {pal['text']}; }}
QLabel#statusWin {{ font-family: "Segoe UI"; font-weight: 900; font-size: 20px; color: #3cbf5a; }}
QLabel#statusLoss {{ font-family: "Segoe UI"; font-weight: 900; font-size: 20px; color: #e04848; }}
QLabel#muted {{ font-family: "Trebuchet MS", "Segoe UI"; color: {pal['muted']}; }}
QLabel#hint {{ font-family: "Trebuchet MS", "Segoe UI"; font-size: 12px; color: {pal['muted']}; }}
QCheckBox {{ font-family: "Trebuchet MS", "Segoe UI"; font-weight: 700; color: {pal['text']}; spacing: 10px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 6px; border: 2px solid {pal['neon']}; background: transparent; }}
QCheckBox::indicator:checked {{ background: {pal['neon']}; image: none; }}
""" + button_qss(pal, 0.8)


class MenuPage(Arcade):
    """Меню по центру: заголовок-фигуры, «кабинет» с выбором, три аркадные кнопки."""

    def __init__(self, gw):
        super().__init__()
        self.gw = gw
        self.scale = None
        root = QHBoxLayout(self)
        self.root = root
        root.addStretch(1)
        col = QVBoxLayout()
        self.column = col
        root.addLayout(col)
        root.addStretch(1)
        col.addStretch(2)
        self.title = BlockTitle()
        col.addWidget(self.title)
        self.sub = label("", "arcSub", wrap=True)
        self.sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(self.sub)
        self.cabinet = QFrame()
        self.cabinet.setObjectName("cabinet")
        grid = QGridLayout(self.cabinet)
        self.grid = grid
        self.captions = {}
        w, self.mode_buttons = segmented({m: "" for m in ("solo", "ai", "duel")}, lambda v: gw.change("mode", v))
        self._row(0, "mode", w)
        from game.train import passport as PP
        w, self.level_buttons = segmented({lv: "" for lv in PP.LEVELS}, lambda v: gw.change("level", v))
        self._row(1, "level", w)
        grid.setColumnStretch(2, 1)
        col.addWidget(self.cabinet)
        self.note = label("", "arcNote", wrap=True)
        self.note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(self.note)
        self.row = QHBoxLayout()
        self.play_button = button("", "menuPrimary", lambda: gw.menu_play())
        self.new_button = button("", "arcadeB", lambda: gw.start_game())     # при начатой игре
        self.stats_button = button("", "arcadeB", lambda: gw.show_page("stats"))
        self.settings_button = button("", None, lambda: gw.show_page("settings"))
        self.buttons = (self.play_button, self.stats_button, self.settings_button)
        col.addWidget(self.play_button)
        col.addWidget(self.new_button)
        self.new_button.hide()
        self.row.addWidget(self.stats_button, 1)
        self.row.addWidget(self.settings_button, 1)
        col.addLayout(self.row)
        col.addStretch(3)
        self.foot = label("", "arcFoot", wrap=True)
        self.foot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(self.foot)
        self.apply_scale(force=True)

    def _row(self, r, key, widget):
        cap = label("", "arcCaption")
        self.captions[key] = cap
        self.grid.addWidget(cap, r, 0)
        self.grid.addWidget(widget, r, 1)

    def scale_for(self, w, h):
        return round(max(1.0, min(2.4, w / 1280, h / 800)), 2)

    def column_width(self):
        return round(min(620 * self.scale, max(520, self.width() * 0.6)))

    def apply_scale(self, force=False):
        k = self.scale_for(max(self.width(), 900), max(self.height(), 700))
        if not force and k == self.scale:
            return
        self.scale = k
        pal = palette(self.theme_name)
        self.setStyleSheet(menu_qss(pal, k))
        self.title.px = round(72 * k)
        self.title.min_px = round(30 * k)
        self.title.shade = QColor(pal["shade"])
        self.title.updateGeometry()
        self.title.update()
        self.root.setContentsMargins(round(24 * k), round(20 * k), round(24 * k), round(18 * k))
        self.column.setSpacing(round(12 * k))
        self.row.setSpacing(round(12 * k))
        self.grid.setContentsMargins(round(20 * k), round(16 * k), round(20 * k), round(16 * k))
        self.grid.setHorizontalSpacing(round(14 * k))
        self.grid.setVerticalSpacing(round(10 * k))
        for group in (self.mode_buttons, self.level_buttons):
            fit_segments(group)          # ширина под жирный шрифт кнопки (кегль из таблицы стилей)
        self._fit()

    def _fit(self):
        w = self.column_width()
        for x in (self.title, self.sub, self.cabinet, self.note, self.foot, self.play_button, self.new_button):
            x.setFixedWidth(w)
        m = self.root.contentsMargins().left()
        left = (self.width() - w) / 2
        gap = round(16 * self.scale)
        self.lanes = (m * 0.5, left - gap, left + w + gap, self.width() - m * 0.5)

    def set_theme(self, name):
        super().set_theme(name)
        self.apply_scale(force=True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.apply_scale()
        self._fit()

    def column_rect(self):
        w = self.column_width()
        return QRectF((self.width() - w) / 2, 0, w, self.height())

    def retranslate(self):
        t = self.gw.t
        self.title.setText(t("app_title").upper())
        self.sub.setText(t("app_sub"))
        for key, cap in self.captions.items():
            cap.setText(t(key).upper())
        for m, b in self.mode_buttons.items():
            b.setText(t("mode_" + m))
        for k, b in self.level_buttons.items():
            b.setText(t(k))
        self.play_button.setText(t("play"))
        self.new_button.setText(t("new_game"))
        self.stats_button.setText(t("stats"))
        self.settings_button.setText(t("settings"))
        self.apply_scale(force=True)
        self.sync(self.gw.settings)

    def sync(self, s):
        # начатая игра ждёт на паузе: «Продолжить» и «Новая игра» (проверка 17.10: уход в меню
        # убивал игру, брошенная дуэль не считалась)
        going = self.gw.in_progress() if hasattr(self.gw, "games") else False
        self.play_button.setText(self.gw.t("continue") if going else self.gw.t("play"))
        self.new_button.setVisible(going)
        self.mode_buttons[s["mode"]].setChecked(True)
        self.level_buttons[s["level"]].setChecked(True)
        self.note.setText(self.gw.menu_note(s))
        self.foot.setText(self.gw.menu_foot())
