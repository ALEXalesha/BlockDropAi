"""Поле и панели фигур - своим рисованием (QPainter).

BoardView рисует партию: сетку, клетки, тень, текущую фигуру с плавным падением (доля
пути до следующего ряда - из часов игры), вспышку очищенных линий, контуры «Мыслей ИИ»
и подсказки. Ряды выше видимого поля не рисуются, кроме фигуры, которая там появилась.
"""
import time

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from game.core import blocks as B

# цвета фигур по наборам; порядок как B.KINDS: I J L O S T Z
COLOR_SETS = {
    "classic": ("#2ec4d6", "#3a6fd8", "#f08a24", "#f2c934", "#3cbf5a", "#a259d9", "#e04848"),
    "pastel": ("#8fd9e3", "#9db7f0", "#f5bd8a", "#f6e08f", "#9fdcaa", "#cfa8ec", "#f0a3a3"),
    "mono": ("#f0f0f0", "#c8c8c8", "#a8a8a8", "#e0e0e0", "#b8b8b8", "#d8d8d8", "#989898"),
}
GARBAGE = "#7d8494"
FLASH_SECONDS = 0.28


def piece_color(kind, scheme="classic"):
    return QColor(COLOR_SETS.get(scheme, COLOR_SETS["classic"])[kind])


def draw_cell(p, rect, color, ghost=False):
    if ghost:
        pen = QPen(color, max(1.0, rect.width() * 0.08))
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        r = rect.adjusted(rect.width() * 0.12, rect.height() * 0.12, -rect.width() * 0.12, -rect.height() * 0.12)
        p.drawRoundedRect(r, 3, 3)
        return
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    r = rect.adjusted(1, 1, -1, -1)
    p.drawRoundedRect(r, rect.width() * 0.14, rect.width() * 0.14)
    p.setBrush(QColor(255, 255, 255, 46))
    p.drawRoundedRect(QRectF(r.x(), r.y(), r.width(), r.height() * 0.32), rect.width() * 0.14, rect.width() * 0.14)


class BoardView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.game = None
        self.palette_ = {}
        self.scheme = "classic"
        self.ghost = True
        self.thoughts = []          # [(клетки [(x, y)], оценка, лучшая?)]
        self.hint = None            # клетки подсказки
        self.flash = []             # [(время, ряды)]
        self.banner = ""
        self.colors = {}            # (x, y) -> вид фигуры, которой клетка была занята
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(200, 400)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def set_theme(self, palette, scheme):
        self.palette_ = palette
        self.scheme = scheme
        self.update()

    def set_game(self, game):
        self.game = game
        self.colors = {}
        self.flash = []
        self.thoughts = []
        self.hint = None
        self.banner = ""
        self.update()

    # раскраска: поле хранит только биты, цвета клеток помнит вид
    def remember_lock(self, kind, rot, x, y, cleared_rows):
        for cx, cy in B.piece_cells(kind, rot, x, y):
            self.colors[(cx, cy)] = kind
        if cleared_rows:
            self.flash.append((time.monotonic(), tuple(cleared_rows)))
            keep = {}
            for (cx, cy), k in self.colors.items():
                if cy in cleared_rows:
                    continue
                below = sum(1 for r in cleared_rows if r < cy)
                keep[(cx, cy - below)] = k
            self.colors = keep

    def shift_up(self, n):
        """Мусор поднял поле на n рядов."""
        self.colors = {(x, y + n): k for (x, y), k in self.colors.items()}

    def cell_size(self):
        return max(4.0, min((self.width() - 4) / B.WIDTH, (self.height() - 4) / B.VISIBLE))

    def origin(self):
        s = self.cell_size()
        return (self.width() - s * B.WIDTH) / 2, (self.height() - s * B.VISIBLE) / 2

    def cell_rect(self, x, y):
        s = self.cell_size()
        ox, oy = self.origin()
        return QRectF(ox + x * s, oy + (B.VISIBLE - 1 - y) * s, s, s)

    def sizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(300, 600)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = self.palette_ or {"surface": "#272c36", "grid": "#333946", "border": "#3a404b",
                                "text": "#e6e8ec", "accent": "#4a7ab8", "good": "#2dd4a8", "bg": "#1f242e"}
        s = self.cell_size()
        ox, oy = self.origin()
        field = QRectF(ox, oy, s * B.WIDTH, s * B.VISIBLE)
        p.setPen(QPen(QColor(pal["border"]), 2))
        p.setBrush(QColor(pal["surface"]))
        p.drawRoundedRect(field.adjusted(-2, -2, 2, 2), 6, 6)
        p.setPen(QPen(QColor(pal["grid"]), 1))
        for x in range(1, B.WIDTH):
            p.drawLine(QPointF(ox + x * s, oy), QPointF(ox + x * s, oy + s * B.VISIBLE))
        for y in range(1, B.VISIBLE):
            p.drawLine(QPointF(ox, oy + y * s), QPointF(ox + s * B.WIDTH, oy + y * s))
        g = self.game
        if g is not None:
            p.setClipRect(field.adjusted(-1, -1, 1, 1))
            for y in range(B.VISIBLE):
                row = g.board[y]
                if not row:
                    continue
                for x in range(B.WIDTH):
                    if row >> x & 1:
                        k = self.colors.get((x, y))
                        color = piece_color(k, self.scheme) if k is not None else QColor(GARBAGE)
                        draw_cell(p, self.cell_rect(x, y), color)
            if not g.over:
                color = piece_color(g.kind, self.scheme)
                if self.ghost:
                    gy = g.ghost_y()
                    if gy != g.y:
                        for cx, cy in B.piece_cells(g.kind, g.rot, g.x, gy):
                            draw_cell(p, self.cell_rect(cx, cy), color, ghost=True)
                frac = 0.0
                if g.gravity and not g.grounded():
                    frac = min(0.95, g.fall_acc / max(g.interval(), 1e-6))
                for cx, cy in B.piece_cells(g.kind, g.rot, g.x, g.y):
                    r = self.cell_rect(cx, cy).translated(0, frac * s)
                    draw_cell(p, r, color)
            self._draw_outlines(p, pal, s)
            self._draw_flash(p, s)
            p.setClipping(False)
        if self.banner:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 150))
            band = QRectF(field.x(), field.center().y() - s * 1.4, field.width(), s * 2.8)
            p.drawRect(band)
            f = QFont(self.font())
            f.setPixelSize(int(max(12, s * 0.9)))
            f.setBold(True)
            p.setFont(f)
            p.setPen(QColor("#ffffff"))
            p.drawText(band, Qt.AlignmentFlag.AlignCenter, self.banner)
        p.end()

    def _draw_outlines(self, p, pal, s):
        f = QFont(self.font())
        f.setPixelSize(int(max(9, s * 0.38)))
        p.setFont(f)
        for cells, score, best in reversed(self.thoughts):
            color = QColor(pal["good"]) if best else QColor(pal["accent"])
            color.setAlpha(255 if best else 150)
            p.setPen(QPen(color, 3 if best else 2, Qt.PenStyle.SolidLine if best else Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            for cx, cy in cells:
                if cy < B.VISIBLE:
                    p.drawRect(self.cell_rect(cx, cy).adjusted(2, 2, -2, -2))
            top = max(cells, key=lambda c: (c[1], -c[0]))
            if top[1] < B.VISIBLE:
                r = self.cell_rect(top[0], top[1]).translated(0, -s * 0.7)
                p.setPen(color)
                p.drawText(r.adjusted(-s, 0, s, 0), Qt.AlignmentFlag.AlignCenter, f"{score:.0f}")
        if self.hint:
            color = QColor(pal["good"])
            p.setPen(QPen(color, 3))
            fill = QColor(color)
            fill.setAlpha(60)
            p.setBrush(fill)
            for cx, cy in self.hint:
                if cy < B.VISIBLE:
                    p.drawRect(self.cell_rect(cx, cy).adjusted(2, 2, -2, -2))

    def _draw_flash(self, p, s):
        now = time.monotonic()
        self.flash = [(t, rows) for t, rows in self.flash if now - t < FLASH_SECONDS]
        for t, rows in self.flash:
            a = int(220 * (1 - (now - t) / FLASH_SECONDS))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, max(0, a)))
            for r in rows:
                if r < B.VISIBLE:
                    left = self.cell_rect(0, r)
                    p.drawRect(QRectF(left.x(), left.y(), s * B.WIDTH, s))


class PiecePanel(QWidget):
    """Несколько фигур столбиком: очередь «Дальше» или hold."""

    def __init__(self, slots=1, parent=None):
        super().__init__(parent)
        self.kinds = []
        self.slots = slots
        self.dim = False
        self.scheme = "classic"
        self.palette_ = {}
        self.setMinimumSize(90, 60 * slots)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def set_kinds(self, kinds, dim=False):
        kinds = list(kinds)[:self.slots]
        if kinds != self.kinds or dim != self.dim:
            self.kinds = kinds
            self.dim = dim
            self.update()

    def set_theme(self, palette, scheme):
        self.palette_, self.scheme = palette, scheme
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        slot_h = self.height() / self.slots
        s = min(self.width() / 5, slot_h / 3)
        for i, kind in enumerate(self.kinds):
            if kind is None:
                continue
            cells = B.CELLS[kind][0]
            xs = [c[0] for c in cells]
            ys = [c[1] for c in cells]
            w = (max(xs) - min(xs) + 1) * s
            h = (max(ys) - min(ys) + 1) * s
            ox = (self.width() - w) / 2
            oy = i * slot_h + (slot_h - h) / 2
            color = piece_color(kind, self.scheme)
            if self.dim:
                color.setAlpha(90)
            for cx, cy in cells:
                r = QRectF(ox + (cx - min(xs)) * s, oy + (max(ys) - cy) * s, s, s)
                draw_cell(p, r, color)
        p.end()
