"""Виджет игры (create_widget по контракту): меню, поле, статистика, настройки.

Окно ему даёт оболочка (aikit.run_standalone или ИИ-Игротека). Тема и язык приходят из
ctx и меняются на лету по ctx.changed. Файлы - только в ctx.data_dir.

Часы: таймер окна лишь будит логику раз в ~16 мс, а сколько прошло - берётся из
time.monotonic; скорость игры от частоты кадров не зависит.
"""
import json
import os
import random
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
                               QLabel, QPushButton, QScrollArea, QSlider, QStackedWidget, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from aikit import settings as st
from aikit import theme
from aikit.storage import load_json, save_json
from aikit.widgets import Combo, button, card, label, restyle, segmented
from game.ai import player as P
from game.core import blocks as B
from game.train import passport as PP
from game.ui import session as S
from game.ui.ai_thread import AiWorker, make_agents
from game.ui.board import COLOR_SETS, BoardView, PiecePanel
from game.ui.i18n import translator
from game.version import VERSION

LEVELS = PP.LEVELS
ACTIONS = ("left", "right", "soft", "hard", "cw", "ccw", "hold", "pause")
DEFAULT_KEYS = {"left": int(Qt.Key.Key_Left), "right": int(Qt.Key.Key_Right), "soft": int(Qt.Key.Key_Down),
                "hard": int(Qt.Key.Key_Space), "cw": int(Qt.Key.Key_Up), "ccw": int(Qt.Key.Key_Z),
                "hold": int(Qt.Key.Key_C), "pause": int(Qt.Key.Key_Escape)}
# скорость ИИ в режиме «Играет ИИ»: (секунд на раздумье, секунд между клавишами)
SPEEDS = {"real": (0.35, 0.07), "x3": (0.1, 0.02), "x10": (0.02, 0.005), "max": (0.0, 0.0)}
# дуэль: ИИ не быстрее стольких фигур в секунду, клавиши - с паузой
DUEL_PPS = {"novice": 0.8, "medium": 1.4, "strong": 2.0}
DUEL_KEY = {"novice": 0.09, "medium": 0.06, "strong": 0.045}
TICK_MS = 16


def _keys_ok(v):
    return (isinstance(v, dict) and set(v) == set(ACTIONS)
            and all(isinstance(k, int) and not isinstance(k, bool) for k in v.values())
            and len(set(v.values())) == len(v))


SCHEMA = {
    "mode": ("solo", st.choice("solo", "ai", "duel")),
    "level": ("medium", st.choice(*LEVELS)),
    "speed": ("x3", st.choice(*SPEEDS)),
    "colors": ("classic", st.choice(*COLOR_SETS)),
    "das_ms": (167, st.int_range(40, 400)),
    "arr_ms": (33, st.int_range(0, 120)),
    "start_level": (1, st.int_range(1, 15)),
    "ghost": (True, st.boolean()),
    "show_thoughts": (False, st.boolean()),
    "keys": (dict(DEFAULT_KEYS), _keys_ok),
}


def fit_bold(buttons):
    """Выбранная кнопка-переключатель пишется жирным (тема aikit), а ширину Qt считает по
    обычному шрифту - текст обрезается по краям. Минимальная ширина - по жирному."""
    from PySide6.QtGui import QFont, QFontMetrics
    for b in buttons:
        f = QFont(b.font())
        f.setBold(True)
        b.setMinimumWidth(QFontMetrics(f).horizontalAdvance(b.text()) + 26)


def seg_grid(options, slot, cols=2):
    """Переключатели сеткой - когда в ряд не влезают."""
    from PySide6.QtWidgets import QButtonGroup
    box = QWidget()
    grid = QGridLayout(box)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setSpacing(6)
    group = QButtonGroup(box)
    group.setExclusive(True)
    buttons = {}
    for i, (value, text) in enumerate(options.items()):
        b = button(text, "seg")
        b.setCheckable(True)
        b.clicked.connect(lambda _=False, v=value: slot(v))
        group.addButton(b)
        grid.addWidget(b, i // cols, i % cols)
        buttons[value] = b
    return box, buttons


def page_widget():
    w = QWidget()
    w.setObjectName("page")
    w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    return w


def number(n):
    return f"{n:,}".replace(",", " ")


def fmt_time(t, seconds):
    if seconds < 90:
        return t("seconds", n=round(seconds))
    if seconds < 5400:
        return t("minutes", n=round(seconds / 60))
    return t("hours", n=f"{seconds / 3600:.1f}")


def key_name(code):
    name = QKeySequence(code).toString()
    return name or f"#{code}"


def cells_of(placement):
    """Клетки места из ключа ((ряд, маска), ...)."""
    return [(x, row) for row, mask in placement.key for x in range(B.WIDTH) if mask >> x & 1]


class Records:
    """Рекорды по режимам: партий, лучшее по линиям и очкам. Файл records.json в data_dir."""

    def __init__(self, path):
        self.path = path
        raw = load_json(path)
        self.data = {}
        if isinstance(raw, dict):
            for k, e in raw.items():
                if isinstance(e, dict) and all(isinstance(e.get(f), int) and e[f] >= 0
                                               for f in ("games", "best_lines", "best_score")):
                    self.data[k] = {f: e[f] for f in ("games", "best_lines", "best_score")}

    def entry(self, key):
        return dict(self.data.get(key, {"games": 0, "best_lines": 0, "best_score": 0}))

    def add(self, key, lines, score):
        e = self.entry(key)
        e["games"] += 1
        e["best_lines"] = max(e["best_lines"], int(lines))
        e["best_score"] = max(e["best_score"], int(score))
        self.data[key] = e
        save_json(self.path, self.data)
        return e


# --- меню ---


class MenuPage(QWidget):
    def __init__(self, gw):
        super().__init__()
        self.gw = gw
        self.setObjectName("page")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        outer = QVBoxLayout(self)
        outer.addStretch(2)
        col = QVBoxLayout()
        col.setSpacing(10)
        col.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        from PySide6.QtGui import QPixmap
        from game.ui.icon import render
        self.logo = QLabel()
        self.logo.setPixmap(QPixmap.fromImage(render(112)))
        col.addWidget(self.logo, 0, Qt.AlignmentFlag.AlignHCenter)
        self.title = label("", "title")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(self.title)
        self.sub = label("", "muted", wrap=True)
        self.sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sub.setFixedWidth(620)
        col.addWidget(self.sub, 0, Qt.AlignmentFlag.AlignHCenter)
        col.addSpacing(12)
        box = card()
        box.setMaximumWidth(680)
        grid = QGridLayout(box)
        grid.setContentsMargins(22, 18, 22, 18)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(12)
        self.captions = {}
        w, self.mode_buttons = segmented({m: "" for m in ("solo", "ai", "duel")}, lambda v: gw.change("mode", v))
        self._row(grid, 0, "mode", w)
        w, self.level_buttons = segmented({lv: "" for lv in LEVELS}, lambda v: gw.change("level", v))
        self._row(grid, 1, "level", w)
        col.addWidget(box, 0, Qt.AlignmentFlag.AlignHCenter)
        self.note = label("", "hint", wrap=True)
        self.note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.note.setFixedWidth(620)
        col.addWidget(self.note, 0, Qt.AlignmentFlag.AlignHCenter)
        col.addSpacing(8)
        self.play_button = button("", "menuPrimary", lambda: gw.start_game())
        self.stats_button = button("", "menu", lambda: gw.show_page("stats"))
        self.settings_button = button("", "menu", lambda: gw.show_page("settings"))
        for b in (self.play_button, self.stats_button, self.settings_button):
            col.addWidget(b, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addLayout(col)
        outer.addStretch(3)
        self.foot = label("", "hint")
        self.foot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self.foot)

    def _row(self, grid, r, key, widget):
        cap = label("", "muted")
        self.captions[key] = cap
        grid.addWidget(cap, r, 0)
        grid.addWidget(widget, r, 1)

    def sync(self, s):
        self.mode_buttons[s["mode"]].setChecked(True)
        self.level_buttons[s["level"]].setChecked(True)
        t = self.gw.t
        text = {"solo": t("solo_text"), "ai": t("ai_text"),
                "duel": t("duel_text", pps=str(DUEL_PPS[s["level"]]).replace(".", "," if self.gw.ctx.lang == "ru" else "."))}
        self.note.setText(text[s["mode"]])

    def retranslate(self):
        t = self.gw.t
        self.title.setText(t("app_title"))
        self.sub.setText(t("app_sub"))
        for key, cap in self.captions.items():
            cap.setText(t(key))
        for m, b in self.mode_buttons.items():
            b.setText(t("mode_" + m))
        for k, b in self.level_buttons.items():
            b.setText(t(k))
        fit_bold(list(self.mode_buttons.values()) + list(self.level_buttons.values()))
        self.play_button.setText(t("play"))
        self.stats_button.setText(t("stats"))
        self.settings_button.setText(t("settings"))
        self.foot.setText(t("footer", v=VERSION))
        self.sync(self.gw.settings)


# --- поле ---


class BoardColumn(QWidget):
    """Одно поле с hold слева, очередью справа и цифрами снизу."""

    def __init__(self):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        left = QVBoxLayout()
        self.name = label("", "section")
        left.addWidget(self.name)
        self.hold_caption = label("", "muted")
        left.addWidget(self.hold_caption)
        self.hold = PiecePanel(1)
        self.hold.setFixedSize(96, 70)
        left.addWidget(self.hold)
        left.addSpacing(10)
        self.numbers = {}
        for key in ("score", "lines", "level_n", "pps"):
            cap = label("", "hint")
            val = label("0", "bigNumber")
            left.addWidget(cap)
            left.addWidget(val)
            self.numbers[key] = (cap, val)
        left.addStretch(1)
        row.addLayout(left)
        self.board = BoardView()
        row.addWidget(self.board, 1)
        right = QVBoxLayout()
        self.next_caption = label("", "muted")
        right.addWidget(self.next_caption)
        self.next = PiecePanel(B.PREVIEW)
        self.next.setFixedSize(96, 62 * B.PREVIEW)
        right.addWidget(self.next)
        right.addStretch(1)
        row.addLayout(right)

    def retranslate(self, t):
        self.hold_caption.setText(t("hold"))
        self.next_caption.setText(t("next"))
        for key, (cap, _) in self.numbers.items():
            cap.setText(t(key))

    def set_theme(self, pal, scheme):
        for w in (self.board, self.hold, self.next):
            w.set_theme(pal, scheme)

    def show_game(self, g, pps):
        self.hold.set_kinds([g.hold_kind], dim=g.hold_used)
        self.next.set_kinds(g.queue[:B.PREVIEW])
        vals = {"score": number(g.score), "lines": number(g.lines), "level_n": str(g.level),
                "pps": f"{pps:.1f}"}
        for key, (_, val) in self.numbers.items():
            if val.text() != vals[key]:
                val.setText(vals[key])
        self.board.update()


class PlayPage(QWidget):
    def __init__(self, gw):
        super().__init__()
        self.gw = gw
        self.setObjectName("page")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        root = QHBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(14)
        self.cols = [BoardColumn(), BoardColumn()]
        for c in self.cols:
            root.addWidget(c, 1)
        side = card()
        side.setFixedWidth(300)
        col = QVBoxLayout(side)
        col.setContentsMargins(16, 14, 16, 14)
        col.setSpacing(8)
        self.heading = label("", "section", wrap=True)
        col.addWidget(self.heading)
        self.status = label("", "status", wrap=True)
        col.addWidget(self.status)
        self.info = label("", "hint", wrap=True)
        col.addWidget(self.info)
        self.speed_caption = label("", "muted")
        col.addWidget(self.speed_caption)
        self.speed_box, self.speed_buttons = seg_grid({k: "" for k in SPEEDS}, lambda v: gw.change("speed", v))
        col.addWidget(self.speed_box)
        self.hint_button = button("", "primary", gw.show_hint)
        col.addWidget(self.hint_button)
        self.thoughts_box = QCheckBox("")
        self.thoughts_box.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.thoughts_box.toggled.connect(lambda on: gw.change("show_thoughts", on))
        col.addWidget(self.thoughts_box)
        self.thoughts_hint = label("", "hint", wrap=True)
        col.addWidget(self.thoughts_hint)
        col.addStretch(1)
        self.pause_button = button("", None, gw.toggle_pause)
        col.addWidget(self.pause_button)
        last = QHBoxLayout()
        self.again_button = button("", "primary", lambda: gw.start_game())
        self.menu_button = button("", None, lambda: gw.show_page("menu"))
        last.addWidget(self.again_button, 1)
        last.addWidget(self.menu_button, 1)
        col.addLayout(last)
        root.addWidget(side)
        self.side = side

    def fit_labels(self):
        """Подписи с переносом получают высоту по своей ширине (qt-wrapped-label-height:
        высоту не фиксировать, только минимум)."""
        for w in self.side.findChildren(QLabel):
            if w.wordWrap() and w.width() > 0:
                w.setMinimumHeight(w.heightForWidth(w.width()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_labels()

    def retranslate(self):
        t = self.gw.t
        for c in self.cols:
            c.retranslate(t)
        self.speed_caption.setText(t("speed"))
        for k, b in self.speed_buttons.items():
            b.setText(t("speed_" + k))
        fit_bold(self.speed_buttons.values())
        self.hint_button.setText(t("hint"))
        self.thoughts_box.setText(t("thoughts"))
        self.thoughts_hint.setText(t("thoughts_hint"))
        self.again_button.setText(t("again"))
        self.menu_button.setText(t("menu"))
        self.pause_button.setText(t("resume") if self.gw.paused else t("pause"))
        self.fit_labels()


# --- статистика ---


def table_widget(cols):
    tw = QTableWidget(0, cols)
    tw.verticalHeader().setVisible(False)
    tw.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    tw.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    tw.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    tw.setShowGrid(False)
    tw.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    tw.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    header = tw.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    header.setHighlightSections(False)
    return tw


def fill(tw, headers, rows):
    tw.setColumnCount(len(headers))
    tw.setHorizontalHeaderLabels(headers)
    tw.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            it = QTableWidgetItem(str(text))
            it.setTextAlignment((Qt.AlignmentFlag.AlignLeft if c == 0 else Qt.AlignmentFlag.AlignCenter)
                                | Qt.AlignmentFlag.AlignVCenter)
            tw.setItem(r, c, it)
    tw.resizeRowsToContents()
    tw.setFixedHeight(tw.horizontalHeader().height() + sum(tw.rowHeight(r) for r in range(tw.rowCount())) + 4)


class Evolution(QWidget):
    """Среднее число линий популяции по поколениям CEM (ось линий - логарифм)."""

    def __init__(self):
        super().__init__()
        self.points = []
        self.pal = theme.palette("dark")
        self.setMinimumHeight(180)

    def set_data(self, points, pal):
        self.points, self.pal = points, pal
        self.update()

    def paintEvent(self, event):
        import math
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(44, 10, self.width() - 56, self.height() - 34)
        p.setPen(QPen(QColor(self.pal["border"]), 1))
        p.drawLine(r.bottomLeft(), r.bottomRight())
        p.drawLine(r.bottomLeft(), r.topLeft())
        if len(self.points) >= 2:
            top = math.log10(max(max(self.points), 10))
            p.setPen(QColor(self.pal["muted"]))
            for k in range(0, int(top) + 1):
                y = r.bottom() - r.height() * k / top
                p.drawText(QRectF(0, y - 8, 40, 16), Qt.AlignmentFlag.AlignRight, f"1e{k}" if k > 3 else str(10 ** k))
            n = len(self.points) - 1
            poly = QPolygonF([QPointF(r.left() + r.width() * i / n,
                                      r.bottom() - r.height() * math.log10(max(v, 1)) / top)
                              for i, v in enumerate(self.points)])
            p.setPen(QPen(QColor(self.pal["accent"]), 2.5))
            p.drawPolyline(poly)
            p.setPen(QColor(self.pal["muted"]))
            p.drawText(QRectF(r.left(), r.bottom() + 4, r.width(), 18), Qt.AlignmentFlag.AlignCenter,
                       f"0 … {n}")
        p.end()


class StatsPage(QWidget):
    def __init__(self, gw):
        super().__init__()
        self.gw = gw
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)
        body = page_widget()
        scroll.setWidget(body)
        col = QVBoxLayout(body)
        col.setContentsMargins(26, 22, 26, 22)
        col.setSpacing(14)
        top = QHBoxLayout()
        self.heading = label("", "heading")
        top.addWidget(self.heading)
        top.addStretch(1)
        self.menu_button = button("", None, lambda: gw.show_page("menu"))
        top.addWidget(self.menu_button)
        col.addLayout(top)
        self.sections = {}
        for key in ("your_records", "ai_records", "passport", "duels", "evolution"):
            box = card()
            lay = QVBoxLayout(box)
            lay.setContentsMargins(18, 14, 18, 14)
            title = label("", "section")
            lay.addWidget(title)
            text = label("", "hint", wrap=True)
            lay.addWidget(text)
            widget = Evolution() if key == "evolution" else table_widget(4)
            lay.addWidget(widget)
            col.addWidget(box)
            self.sections[key] = (title, text, widget)
        col.addStretch(1)

    def refresh(self):
        gw, t = self.gw, self.gw.t
        title, text, tw = self.sections["your_records"]
        title.setText(t("your_records"))
        rows = []
        solo = gw.records.entry("solo")
        rows.append([t("mode_solo"), solo["games"], number(solo["best_lines"]), number(solo["best_score"])])
        text.setText("")
        fill(tw, [t("col_mode"), t("col_games"), t("col_best_lines"), t("col_best_score")], rows)
        duel_rows = []
        for lv in LEVELS:
            e = gw.ctx.stats.entry("duel/" + lv)
            duel_rows.append([f"{t('mode_duel')} · {t(lv)}", e["games"], e["wins"], e["losses"]])
        tw2 = self.sections["your_records"][2]
        fill(tw2, [t("col_mode"), t("col_games"), t("col_best_lines"), t("col_best_score")], rows)
        title, text, tw = self.sections["ai_records"]
        title.setText(t("ai_records"))
        ai_rows = []
        for lv in LEVELS:
            e = gw.records.entry("ai/" + lv)
            ai_rows.append([f"{t('mode_ai')} · {t(lv)}", e["games"], number(e["best_lines"]), number(e["best_score"])])
        text.setText("")
        fill(tw, [t("col_mode"), t("col_games"), t("col_best_lines"), t("col_best_score")], ai_rows)
        # дуэли игрока - в той же карточке, что и рекорды, отдельной таблицей не перегружаем
        title, text, tw = self.sections["duels"]
        title.setText(t("duels"))
        pp = gw.model.get("passport")
        rows = [[r[0], r[1], r[2], r[3]] for r in duel_rows]
        heads = [t("col_mode"), t("col_games"), t("col_wins"), t("col_losses")]
        if pp:
            for d in pp["duel"]:
                rows.append([f"{t(d['a'])} – {t(d['b'])}", d["duels"], f"{d['wins_a']} : {d['wins_b']}",
                             d["draws"]])
        text.setText("")
        fill(tw, heads, rows)
        title, text, tw = self.sections["passport"]
        title.setText(t("passport"))
        tr = gw.model.get("training", {})
        if pp:
            caps = pp["caps"]
            cap_text = " / ".join(f"{t(lv)} {number(caps[lv])}" for lv in LEVELS)
            text.setText(t("passport_text", games=pp["games"], cap=cap_text,
                           gens=tr.get("generations", "?"), time=fmt_time(t, tr.get("seconds", 0))))
            rows = [[t(lv), number(round(s["mean"])), number(round(s["median"])), f"{s['capped']}/{len(s['games'])}"]
                    for lv, s in pp["levels"].items()]
            fill(tw, [t("col_level"), t("col_mean"), t("col_median"), t("col_capped")], rows)
        else:
            text.setText(t("not_ready"))
            fill(tw, [t("col_level"), t("col_mean"), t("col_median"), t("col_capped")], [])
        title, text, ev = self.sections["evolution"]
        title.setText(t("evolution"))
        text.setText(t("evolution_hint"))
        ev.set_data([h["population_mean"] for h in tr.get("history", [])], gw.ctx.palette())

    def retranslate(self):
        self.heading.setText(self.gw.t("stats_title"))
        self.menu_button.setText(self.gw.t("menu"))
        self.refresh()


# --- настройки ---


class SettingsPage(QWidget):
    def __init__(self, gw):
        super().__init__()
        self.gw = gw
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)
        body = page_widget()
        scroll.setWidget(body)
        col = QVBoxLayout(body)
        col.setContentsMargins(26, 22, 26, 22)
        col.setSpacing(14)
        top = QHBoxLayout()
        self.heading = label("", "heading")
        top.addWidget(self.heading)
        top.addStretch(1)
        self.menu_button = button("", None, lambda: gw.show_page("menu"))
        top.addWidget(self.menu_button)
        col.addLayout(top)
        box = card()
        grid = QGridLayout(box)
        grid.setContentsMargins(20, 16, 20, 16)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(12)
        self.caps = {}
        r = 0

        def row(key, widget, hint=False):
            nonlocal r
            cap = label("", "muted")
            self.caps[key] = cap
            grid.addWidget(cap, r, 0)
            grid.addWidget(widget, r, 1)
            r += 1
            if hint:
                h = label("", "hint", wrap=True)
                self.caps[key + "_hint"] = h
                grid.addWidget(h, r, 1)
                r += 1

        w, self.theme_buttons = segmented({"dark": "", "light": ""}, gw.ctx.set_theme)
        row("theme", w)
        w, self.lang_buttons = segmented({"ru": "Русский", "en": "English"}, gw.ctx.set_lang)
        row("language", w)
        self.colors = Combo()
        self.colors.currentIndexChanged.connect(self._colors_changed)
        row("colors", self.colors)
        self.das = self._slider(40, 400, lambda v: gw.change("das_ms", v))
        row("das", self.das, hint=True)
        self.arr = self._slider(0, 120, lambda v: gw.change("arr_ms", v))
        row("arr", self.arr, hint=True)
        self.start_level = self._slider(1, 15, lambda v: gw.change("start_level", v))
        row("start_level", self.start_level, hint=True)
        self.ghost = QCheckBox("")
        self.ghost.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.ghost.toggled.connect(lambda on: gw.change("ghost", on))
        row("ghost", self.ghost)
        self.volume = self._slider(0, 100, gw.ctx.set_volume)
        row("volume", self.volume)
        col.addWidget(box)
        keys = card()
        kl = QGridLayout(keys)
        kl.setContentsMargins(20, 16, 20, 16)
        kl.setHorizontalSpacing(18)
        kl.setVerticalSpacing(8)
        self.keys_title = label("", "section")
        kl.addWidget(self.keys_title, 0, 0, 1, 2)
        self.keys_hint = label("", "hint", wrap=True)
        kl.addWidget(self.keys_hint, 1, 0, 1, 2)
        self.key_caps = {}
        self.key_buttons = {}
        for i, act in enumerate(ACTIONS):
            cap = label("", "muted")
            b = button("", None, lambda _=False, a=act: gw.capture_key(a))
            b.setMinimumWidth(180)
            kl.addWidget(cap, 2 + i, 0)
            kl.addWidget(b, 2 + i, 1)
            self.key_caps[act] = cap
            self.key_buttons[act] = b
        col.addWidget(keys)
        self.note = label("", "hint")
        col.addWidget(self.note)
        col.addStretch(1)

    @staticmethod
    def _slider(lo, hi, slot):
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(lo, hi)
        s.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        s.valueChanged.connect(slot)
        return s

    def _colors_changed(self, i):
        if 0 <= i < len(COLOR_SETS):
            self.gw.change("colors", list(COLOR_SETS)[i])

    def sync(self):
        gw, s = self.gw, self.gw.settings
        self.theme_buttons[gw.ctx.theme].setChecked(True)
        self.lang_buttons[gw.ctx.lang].setChecked(True)
        for w, v in ((self.das, s["das_ms"]), (self.arr, s["arr_ms"]), (self.start_level, s["start_level"]),
                     (self.volume, gw.ctx.sound.volume)):
            w.blockSignals(True)
            w.setValue(v)
            w.blockSignals(False)
        self.ghost.blockSignals(True)
        self.ghost.setChecked(s["ghost"])
        self.ghost.blockSignals(False)
        self.colors.blockSignals(True)
        self.colors.setCurrentIndex(list(COLOR_SETS).index(s["colors"]))
        self.colors.blockSignals(False)
        t = gw.t
        self.caps["das_hint"].setText(t("das_hint", ms=s["das_ms"]))
        self.caps["arr_hint"].setText(t("arr_hint", ms=s["arr_ms"]))
        self.caps["start_level_hint"].setText(str(s["start_level"]))
        for act, b in self.key_buttons.items():
            b.setText(t("press_key") if gw.capturing == act else key_name(s["keys"][act]))

    def retranslate(self):
        t = self.gw.t
        self.heading.setText(t("settings_title"))
        self.menu_button.setText(t("menu"))
        for key in ("theme", "language", "colors", "das", "arr", "start_level", "ghost", "volume"):
            self.caps[key].setText(t(key))
        self.theme_buttons["dark"].setText(t("dark"))
        self.theme_buttons["light"].setText(t("light"))
        fit_bold(list(self.theme_buttons.values()) + list(self.lang_buttons.values()))
        self.colors.blockSignals(True)
        self.colors.clear()
        self.colors.addItems([t("colors_" + k) for k in COLOR_SETS])
        self.colors.blockSignals(False)
        self.keys_title.setText(t("keys"))
        self.keys_hint.setText(t("keys_hint"))
        for act, cap in self.key_caps.items():
            cap.setText(t("act_" + act))
        self.note.setText(t("saved_note"))
        self.sync()


# --- сам виджет ---


class GameWidget(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.t = translator(ctx.lang)
        self.settings = st.Settings(SCHEMA, ctx.file("settings.json"))
        self.records = Records(ctx.file("records.json"))
        try:
            self.model = PP.load_model()
        except (OSError, ValueError):
            self.model = {"weights": [-1.0, 1.0, -1.0, -1.0, -4.0, -1.0, 0, 0, 0, 0, 0],
                          "novice_weights": [-1.0, 1.0, -1.0, -1.0, -4.0, -1.0, 0, 0, 0, 0, 0]}
        self.worker = AiWorker(make_agents(self.model))
        self.worker.ready.connect(self._on_ai_ready)
        self.paused = False
        self.capturing = None
        self.mode = None
        self.games = []                 # партии на поле: [(Game, водитель или HumanSession)]
        self.human = None
        self.drivers = []
        self.duel = None
        self.finished = False
        self.game_id = 0
        self.thought = None             # (token, Decision) для «Мыслей ИИ» и подсказки
        self.hint_on = False
        self.started = 0.0
        self.seen_pieces = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack)
        self.menu = MenuPage(self)
        self.play = PlayPage(self)
        self.stats = StatsPage(self)
        self.settings_page = SettingsPage(self)
        self.pages = {"menu": self.menu, "play": self.play, "stats": self.stats, "settings": self.settings_page}
        for w in self.pages.values():
            self.stack.addWidget(w)
        self.timer = QTimer(self)
        self.timer.setInterval(TICK_MS)
        self.timer.timeout.connect(self.on_tick)
        ctx.changed.connect(self.on_ctx_changed)
        self.apply_theme()
        self.retranslate()
        self.show_page("menu")

    # --- общее ---

    def change(self, key, value):
        try:
            self.settings.set(key, value)
        except ValueError:
            return
        if key in ("mode", "level"):
            self.menu.sync(self.settings)
        if key == "colors":
            self.apply_theme()
        if key == "ghost":
            for c in self.play.cols:
                c.board.ghost = value
        if key in ("das_ms", "arr_ms") and self.human is not None:
            self.human.das = self.settings["das_ms"] / 1000
            self.human.arr = self.settings["arr_ms"] / 1000
        if key == "speed" and self.mode == "ai" and self.drivers:
            self._set_speed(self.drivers[0])
        if key == "show_thoughts":
            self.thought = None
            self._update_outlines()
        self.settings_page.sync()

    def on_ctx_changed(self, what):
        if what == "theme":
            self.apply_theme()
        else:
            self.t = translator(self.ctx.lang)
            self.retranslate()

    def apply_theme(self):
        pal = self.ctx.palette()
        for c in self.play.cols:
            c.set_theme(pal, self.settings["colors"])
            c.board.ghost = self.settings["ghost"]
        self.settings_page.colors.set_arrow_color(pal["text"])
        self.stats.refresh()

    def retranslate(self):
        for p in self.pages.values():
            p.retranslate()
        self._update_status()

    def show_page(self, name):
        if name != "play":
            self.stop_game()
        if name == "stats":
            self.stats.refresh()
        if name == "settings":
            self.settings_page.sync()
        self.stack.setCurrentWidget(self.pages[name])
        self.setFocus()

    def current_page(self):
        return next(k for k, w in self.pages.items() if w is self.stack.currentWidget())

    # --- партия ---

    def stop_game(self):
        self.timer.stop()
        self.games = []
        self.human = None
        self.drivers = []
        self.duel = None
        self.seen_pieces = None
        self.game_id += 1

    def start_game(self, seed=None):
        self.stop_game()
        s = self.settings
        self.mode = s["mode"]
        self.level = s["level"]
        seed = random.randrange(2 ** 31) if seed is None else seed
        now = time.monotonic()
        self.started = now
        self.paused = False
        self.finished = False
        self.thought = None
        self.hint_on = False
        start = s["start_level"]
        if self.mode == "solo":
            g = B.Game(seed=seed, level=start)
            self.human = S.HumanSession(g, s["das_ms"] / 1000, s["arr_ms"] / 1000, now)
            self.games = [g]
        elif self.mode == "ai":
            g = B.Game(seed=seed, level=start, gravity=s["speed"] != "max")
            d = S.AiDriver(g, decide=self._decider(0), now=now)
            self._set_speed(d)
            self.drivers = [d]
            self.games = [g]
        else:
            me = B.Game(seed=seed, level=start)
            ai = B.Game(seed=seed, level=start)
            self.human = S.HumanSession(me, s["das_ms"] / 1000, s["arr_ms"] / 1000, now)
            d = S.AiDriver(ai, decide=self._decider(1), key_interval=DUEL_KEY[self.level],
                           think=1.0 / DUEL_PPS[self.level], now=now)
            self.drivers = [d]
            self.games = [me, ai]
            self.duel = S.Duel(me, ai)
        for i, c in enumerate(self.play.cols):
            c.setVisible(i < len(self.games))
            if i < len(self.games):
                c.board.set_game(self.games[i])
        names = {"solo": [self.t("you")], "ai": [self.t("ai_name", level=self.t(self.level))],
                 "duel": [self.t("you"), self.t("ai_name", level=self.t(self.level))]}[self.mode]
        for c, n in zip(self.play.cols, names):
            c.name.setText(n)
        self.play.speed_caption.setVisible(self.mode == "ai")
        self.play.speed_box.setVisible(self.mode == "ai")
        self.play.speed_buttons[s["speed"]].setChecked(True)
        self.play.hint_button.setVisible(self.mode == "solo")
        self.play.thoughts_box.blockSignals(True)
        self.play.thoughts_box.setChecked(s["show_thoughts"])
        self.play.thoughts_box.blockSignals(False)
        self.stack.setCurrentWidget(self.play)
        self._update_status()
        self.timer.start()
        self.setFocus()

    def _set_speed(self, d):
        think, key = SPEEDS[self.settings["speed"]]
        d.think, d.key_interval = think, key
        d.game.gravity = self.settings["speed"] != "max"

    def _decider(self, index):
        gid = self.game_id

        def decide(view):
            g = self.games[index] if index < len(self.games) else None
            if g is None:
                return None
            self.worker.request((gid, index, g.pieces, "move"), view, self.level)
            return None
        return decide

    def _on_ai_ready(self, token, result):
        gid, index, piece, kind = token
        if gid != self.game_id or index >= len(self.games) or isinstance(result, Exception):
            return
        g = self.games[index]
        if piece != g.pieces:
            return
        if kind == "think":
            self.thought = (token, result)
            self._update_outlines()
            return
        driver = self.drivers[0]
        if driver.game is not g:
            return
        now = time.monotonic()
        driver.deliver(result, now)
        if self.mode == "ai" and self.settings["speed"] == "max":
            driver.tick(now, budget=0.004)
        if self.settings["show_thoughts"] and result is not None and self.mode == "ai":
            self.thought = (token, result)
            self._update_outlines()

    def show_hint(self):
        if self.mode != "solo" or not self.games:
            return
        self.hint_on = True
        self._request_thoughts()
        self.setFocus()

    def _request_thoughts(self):
        g = self.games[0]
        if g.over:
            return
        self.worker.request((self.game_id, 0, g.pieces, "think"), P.observe(g), "strong")

    def _update_outlines(self):
        b = self.play.cols[0].board
        b.thoughts = []
        b.hint = None
        if self.thought is not None and self.games:
            (gid, index, piece, _), d = self.thought
            board = self.play.cols[index].board
            g = self.games[index]
            if gid == self.game_id and piece == g.pieces and d is not None:
                if self.settings["show_thoughts"]:
                    board.thoughts = [(cells_of(c.placement), c.score, i == 0) for i, c in enumerate(d.top)]
                if self.hint_on:
                    board.hint = cells_of(d.placement)
        b.update()

    def toggle_pause(self):
        if not self.games or self.finished:
            return
        now = time.monotonic()
        self.paused = not self.paused
        if self.human:
            (self.human.pause if self.paused else self.human.resume)(now)
        for d in self.drivers:
            d.paused = self.paused
            d.last = now
            d.ready_at = now
        self._update_status()
        self.play.retranslate()
        self.setFocus()

    def on_tick(self):
        if not self.games or self.paused:
            return
        now = time.monotonic()
        # число фигур - с прошлого такта: фигура могла лечь и от нажатия между тактами
        before = self.seen_pieces or [g.pieces for g in self.games]
        if self.human:
            self.human.tick(now)
        for d in self.drivers:
            if self.mode == "ai" and self.settings["speed"] == "max":
                d.tick(now, budget=0.010)
            else:
                d.tick(now)
        if self.duel:
            self.duel.exchange()
        self._drain_events()
        changed = [g.pieces != b for g, b in zip(self.games, before)]
        self.seen_pieces = [g.pieces for g in self.games]
        if any(changed):
            if self.hint_on and changed[0] and self.mode == "solo":
                self.hint_on = False
            if self.settings["show_thoughts"] and self.mode == "solo" and changed[0]:
                self._request_thoughts()
            if changed[0]:
                self._update_outlines()
        elif self.settings["show_thoughts"] and self.mode == "solo" and self.thought is None:
            self._request_thoughts()
        elapsed = max(now - self.started, 1e-6)
        for g, c in zip(self.games, self.play.cols):
            c.show_game(g, g.pieces / elapsed)
        self._check_end()

    def _drain_events(self):
        for g, c in zip(self.games, self.play.cols):
            clears = []
            for ev in g.events:
                if ev[0] == "lock":
                    _, n, kind, rot, x, y = ev
                    rows = []
                    if n:
                        rows = next((e[1] for e in g.events if e[0] == "clear"), ())
                    c.board.remember_lock(kind, rot, x, y, rows)
                    if self.mode != "ai" or self.settings["speed"] == "real":
                        self.ctx.sound.play("capture" if n else "move")
                    if n:
                        clears.append(n)
                elif ev[0] == "garbage":
                    c.board.shift_up(ev[1])
            g.events.clear()

    def _check_end(self):
        if self.finished:
            return
        if self.duel:
            w = self.duel.winner()
            if w is None:
                return
            result = {"a": "win", "b": "loss", "draw": "draw"}[w]
            self.ctx.stats.record("duel/" + self.level, result)
            self.ctx.sound.play("win" if result == "win" else "loss" if result == "loss" else "draw")
            self._finish({"win": "duel_win", "loss": "duel_loss", "draw": "duel_draw"}[result])
        elif self.games and self.games[0].over:
            g = self.games[0]
            key = "solo" if self.mode == "solo" else "ai/" + self.level
            self.records.add(key, g.lines, g.score)
            self.ctx.sound.play("loss" if self.mode == "solo" else "draw")
            self._finish("game_over")

    def _finish(self, text_key):
        self.finished = True
        self.timer.stop()
        self.play.cols[0].board.banner = self.t(text_key)
        self.play.cols[0].board.update()
        self._update_status(text_key)

    def _update_status(self, final=None):
        t = self.t
        if not self.games:
            return
        if final:
            self.play.status.setText(t(final))
        elif self.paused:
            self.play.status.setText(t("paused"))
        else:
            self.play.status.setText(t("mode_" + self.mode))
        self.play.heading.setText(t("ai_name", level=t(self.level)) if self.mode != "solo" else t("app_title"))
        info = {"solo": t("solo_text"), "ai": t("ai_text"),
                "duel": t("duel_text", pps=DUEL_PPS[self.level])}[self.mode]
        self.play.info.setText(info)
        self.play.fit_labels()

    # --- клавиатура ---

    def capture_key(self, action):
        self.capturing = action
        self.settings_page.sync()
        self.setFocus()

    def keyPressEvent(self, event):
        code = int(event.key())
        if self.capturing:
            if code != int(Qt.Key.Key_unknown):
                keys = dict(self.settings["keys"])
                old = keys[self.capturing]
                for a, k in keys.items():
                    if k == code:
                        keys[a] = old           # клавиша была у другого действия - меняются местами
                keys[self.capturing] = code
                self.capturing = None
                self.change("keys", keys)
            return
        if event.isAutoRepeat():
            return
        action = next((a for a, k in self.settings["keys"].items() if k == code), None)
        if action is None or self.current_page() != "play":
            return super().keyPressEvent(event)
        if action == "pause":
            self.toggle_pause()
            return
        if self.human and not self.paused and not self.finished:
            self.human.press(action, time.monotonic())

    def keyReleaseEvent(self, event):
        if event.isAutoRepeat():
            return
        code = int(event.key())
        action = next((a for a, k in self.settings["keys"].items() if k == code), None)
        if action and self.human:
            self.human.release(action, time.monotonic())

    # --- закрытие ---

    def shutdown(self):
        """Остановить таймер и поток ИИ за 2 секунды (контракт aikit)."""
        self.stop_game()
        return self.worker.shutdown(2.0)

    def minimumSizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(900, 700)


__all__ = ["GameWidget", "json", "os", "QPushButton", "restyle"]
