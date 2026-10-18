"""Виджет игры (create_widget по контракту): меню, поле, статистика, настройки.

Окно ему даёт оболочка (aikit.run_standalone или ИИ-Игротека). Тема и язык приходят из
ctx и меняются на лету по ctx.changed. Файлы - только в ctx.data_dir.

Часы: таймер окна лишь будит логику раз в ~16 мс, а сколько прошло - берётся из
time.monotonic; скорость игры от частоты кадров не зависит.
"""
import random
import time

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
                               QLabel, QScrollArea, QSlider, QStackedWidget, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from aikit import settings as st
from aikit import gamelog, theme
from aikit.charts import GameCharts, LineChart
from aikit.storage import load_json, save_json
from aikit.skin import SettingsList, SkinPage, StatTiles
from aikit.widgets import Combo, button, card, label, restyle, segmented
from game.ai import player as P
from game.core import blocks as B
from game.train import passport as PP
from game.ui import session as S
from game.ui.ai_thread import AiWorker, make_agents
from game.ui.board import COLOR_SETS, BoardView, PiecePanel
from game.ui.i18n import translator
from game.ui.menu import MenuPage, board_palette, page_qss, side_qss
from game.ui.menu import palette as arcade_palette
from game.ui.skin import SKIN
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


# --- поле ---


class BoardColumn(QWidget):
    """Одно поле с hold слева, очередью справа и цифрами снизу; имя - над всем полем (в узкой
    дуэли имя «ИИ: Средний» в левой колонке обрезалось и раздвигало её - проверка 17.10)."""

    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)
        self.name = label("", "section")
        outer.addWidget(self.name)
        row = QHBoxLayout()
        row.setSpacing(10)
        self.row = row
        outer.addLayout(row, 1)
        left = QVBoxLayout()
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
        self.compact = False

    def set_compact(self, on):
        """Узкая колонка (дуэль в окне 900x700): hold и очередь уже, цифры мельче - стакан
        целиком в колонке (проверка 17.10: правый край обоих стаканов срезан)."""
        if on == self.compact:
            return
        self.compact = on
        k = 0.66 if on else 1.0
        self.hold.setFixedSize(round(96 * k), round(70 * k))
        self.next.setFixedSize(round(96 * k), round(62 * k) * B.PREVIEW)
        self.row.setSpacing(6 if on else 10)
        for _, val in self.numbers.values():
            restyle(val, "bigNumberSmall" if on else "bigNumber")

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
        self.fit_compact()
        self.fit_labels()

    def fit_compact(self):
        """Две колонки и боковая панель не помещаются - колонки компактные."""
        both = all(not c.isHidden() for c in self.cols)
        free = self.width() - 28 - 14 * 2 - self.side.width()
        on = both and free / 2 < 420
        for c in self.cols:
            c.set_compact(on)

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


class StatsPage(SkinPage):
    """Статистика в стиле «неонового зала» (aikit.skin, game/ui/skin.py): пол зала на фоне,
    экраны автоматов с неоновой рамкой, плитки с крупными числами."""

    def __init__(self, gw):
        super().__init__(SKIN, back=lambda: gw.show_page("menu"))
        self.gw = gw
        self.menu_button = self.back_button
        col = self.col
        self.tiles = StatTiles(4, min_tile=170)
        col.addWidget(self.tiles)
        self.sections = {}
        for key in ("your_records", "ai_records", "passport", "hard", "duels", "evolution"):
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
            if key == "your_records":
                col.addWidget(self._charts_card())
        col.addStretch(1)

    def refresh_tiles(self):
        gw, t = self.gw, self.gw.t
        solo = gw.records.entry("solo")
        duels = [gw.ctx.stats.entry("duel/" + lv) for lv in LEVELS]
        played = sum(e["games"] for e in duels)
        won = sum(e["wins"] for e in duels)
        self.tiles.set_tile(0, number(solo["best_lines"]), t("tile_lines"), t("tile_lines_note", n=solo["games"]))
        self.tiles.set_tile(1, number(solo["best_score"]), t("tile_score"))
        self.tiles.set_tile(2, played, t("tile_duels"), t("tile_duel_wins", n=won) if played else "")
        self.tiles.set_tile(3, max((e["best_streak"] for e in duels), default=0), t("tile_streak"))
        self.set_tag(t("tag_stats"))

    def _charts_card(self):
        """Графики (правило автора 10.10 - графики в статистике всех игр с ИИ): дуэли против ИИ -
        доля побед, итоги по уровням, линии за дуэль, очки с рекордом; одиночная игра - очки с
        рекордом; паспорт - среднее число линий каждого уровня."""
        box = card()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(10)
        self.charts_title = label("", "section")
        lay.addWidget(self.charts_title)
        self.charts = GameCharts(LEVELS, length_key="lines", score_key="score", passport=True)
        self.charts.passport.percent = False
        self.solo_chart = self.charts.add(LineChart(percent=False))
        self.solo_chart.color_key, self.solo_chart.second_key = "accent", "warn"
        self.solo_chart.stepped = {1}
        self.solo_chart.integer = True
        # паспорт (на всю ширину) - последним: иначе одиночная игра стояла под ним одна в
        # половину ширины, а справа было пусто
        items = self.charts.items
        items.append(items.pop([c for c, _ in items].index(self.charts.passport)))
        lay.addWidget(self.charts)
        return box

    def refresh_charts(self):
        gw, t = self.gw, self.gw.t
        self.charts_title.setText(t("charts"))
        self.charts.set_theme(gw.ctx.theme)
        games = gw.history.games
        # свои номера у дуэлей и у одиночных игр: в общем журнале они перемешаны
        duels = [dict(g, n=i + 1) for i, g in enumerate(x for x in games if x.get("mode") == "duel")]
        solo = [dict(g, n=i + 1) for i, g in enumerate(x for x in games if x.get("mode") == "solo")]
        # паспорт - проверка на трудном поле: там у всех уровней один предел и средние сравнимы
        # (в обычной проверке средний и сильный упираются в разные пределы 10 000 и 20 000)
        hard = ((gw.model.get("passport") or {}).get("hard") or {}).get("levels") or {}
        passport = None
        if hard:
            lv = [x for x in LEVELS if x in hard]
            passport = ([t(x) for x in lv], [(t("ch_mean_lines"), "accent", [hard[x]["mean"] for x in lv])])
        self.charts.refresh(duels, gw.ctx.lang, {x: t(x) for x in LEVELS},
                            labels={"share": t("ch_share"), "share_empty": t("ch_share_empty"),
                                    "levels": t("ch_levels"), "game_no": t("ch_duel_no"),
                                    "length": t("ch_lines"), "length_empty": t("ch_lines_empty"),
                                    "length_y": t("ch_lines_y"), "score": t("ch_score"),
                                    "score_empty": t("ch_score_empty"), "score_y": t("ch_points"),
                                    "points": t("ch_points"), "passport": t("ch_passport"),
                                    "passport_empty": t("not_ready")},
                            passport=passport)
        c = self.solo_chart
        c.set_texts(t("ch_solo"), t("ch_solo_empty"), t("ch_game_no"), t("ch_points"))
        c.names = (t("ch_points"), t("ch_record"))
        c.set_points(gamelog.series(solo, "score"), gamelog.best_curve(solo, "score"))

    def refresh(self):
        gw, t = self.gw, self.gw.t
        self.refresh_tiles()
        self.refresh_charts()
        title, text, tw = self.sections["your_records"]
        title.setText(t("your_records"))
        rows = []
        solo = gw.records.entry("solo")
        rows.append([t("mode_solo"), solo["games"], number(solo["best_lines"]), number(solo["best_score"])])
        text.setText("")
        fill(tw, [t("col_mode"), t("col_games"), t("col_best_lines"), t("col_best_score")], rows)
        title, text, tw = self.sections["ai_records"]
        title.setText(t("ai_records"))
        ai_rows = []
        for lv in LEVELS:
            e = gw.records.entry("ai/" + lv)
            ai_rows.append([f"{t('mode_ai')} · {t(lv)}", e["games"], number(e["best_lines"]), number(e["best_score"])])
        text.setText("")
        fill(tw, [t("col_mode"), t("col_games"), t("col_best_lines"), t("col_best_score")], ai_rows)
        title, text, tw = self.sections["duels"]
        title.setText(t("duels"))
        pp = gw.model.get("passport")
        rows = [[f"{t('mode_duel')} · {t(lv)} ({t('you')})", gw.ctx.stats.entry("duel/" + lv)["games"],
                 f"{gw.ctx.stats.entry('duel/' + lv)['wins']} : {gw.ctx.stats.entry('duel/' + lv)['losses']}", ""]
                for lv in LEVELS]
        if pp:
            text.setText(t("duels_text", n=pp["duels"], pieces=number(pp["duel_pieces"])))
            for d in pp["duel"]:
                rows.append([f"{t(d['a'])} – {t(d['b'])}", d["duels"], f"{d['wins_a']} : {d['wins_b']}",
                             d["by_cap"]])
        else:
            text.setText("")
        fill(tw, [t("col_pair"), t("col_games"), t("col_result"), t("col_by_cap")], rows)
        title, text, tw = self.sections["hard"]
        title.setText(t("hard"))
        hard = (pp or {}).get("hard", {})
        if hard.get("levels"):
            n = next(iter(hard["levels"].values()))["games"]
            text.setText(t("hard_text", rows=hard["ceiling"], games=n))
            fill(tw, [t("col_level"), t("col_mean"), t("col_median"), t("col_capped")],
                 [[t(lv), f"{s['mean']:.1f}", f"{s['median']:g}", s["capped"]] for lv, s in hard["levels"].items()])
        else:
            text.setText(t("not_ready"))
            fill(tw, [t("col_level"), t("col_mean"), t("col_median"), t("col_capped")], [])
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


class SettingsPage(SkinPage):
    """Настройки в стиле «неонового зала»: экраны автоматов на всю ширину (как статистика; автор
    17.10), группы - вид и звук, игра, клавиши."""

    def __init__(self, gw):
        super().__init__(SKIN, back=lambda: gw.show_page("menu"))
        self.gw = gw
        self.menu_button = self.back_button
        box = SettingsList()
        self.box = box                       # на всю ширину страницы, как статистика (закон)
        self.caps = {}

        def row(key, widget, hint=False):
            title, h = box.add(key, widget)
            self.caps[key] = title
            if hint:
                self.caps[key + "_hint"] = h
            else:
                h.hide()

        box.group("")
        w, self.theme_buttons = segmented({"dark": "", "light": ""}, gw.ctx.set_theme)
        row("theme", w)
        w, self.lang_buttons = segmented({"ru": "Русский", "en": "English"}, gw.ctx.set_lang)
        row("language", w)
        self.colors = Combo()
        self.colors.currentIndexChanged.connect(self._colors_changed)
        row("colors", self.colors)
        self.volume = self._slider(0, 100, gw.ctx.set_volume)
        row("volume", self.volume)
        box.group("")
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
        self.col.addWidget(box)
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
        self.col.addWidget(keys)
        self.note = label("", "hint")
        self.col.addWidget(self.note)
        self.col.addStretch(1)

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
        self.set_tag(t("tag_settings"))
        self.box.set_group(0, t("group_view"))
        self.box.set_group(1, t("group_game"))
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
        self.assisted = False           # одиночная с подсказкой или «Мыслями ИИ» - не в рекорды
        self.started = 0.0
        self.seen_pieces = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack)
        self.menu = MenuPage(self)
        self.play = PlayPage(self)
        self.history = gamelog.GameLog(ctx.file("games.json"))      # журнал для графиков
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
        if key == "speed":
            self.play.speed_buttons[value].setChecked(True)
            if self.mode == "ai" and self.drivers:
                self._set_speed(self.drivers[0])
        if key == "show_thoughts":
            if value and self.mode == "solo" and self.games and not self.finished:
                self.assisted = True    # «Мысли ИИ» посреди одиночной игры - она не в рекордах
                self._update_status()
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
        arc = arcade_palette(self.ctx.theme)
        self.menu.set_theme(self.ctx.theme)
        # поле, цифры и боковая панель - в стиле меню (автор 17.10: и боковые панели свои)
        self.play.setStyleSheet(page_qss(arc))
        self.play.side.setStyleSheet(side_qss(arc))
        for c in self.play.cols:
            c.set_theme(board_palette(pal, self.ctx.theme), self.settings["colors"])
            c.board.ghost = self.settings["ghost"]
        # настройки и статистика - в стиле «неонового зала» (aikit.skin; автор 17.10)
        self.stats.set_theme(self.ctx.theme)
        self.settings_page.set_theme(self.ctx.theme)
        self.stats.refresh()

    def retranslate(self):
        for p in self.pages.values():
            p.retranslate()
        self._update_status()

    def menu_note(self, s):
        t = self.t
        text = {"solo": t("solo_text"), "ai": t("ai_text"),
                "duel": t("duel_text", pps=str(DUEL_PPS[s["level"]]).replace(".", "," if self.ctx.lang == "ru" else "."))}
        return text[s["mode"]]

    def menu_foot(self):
        best = max((e.get("best_lines", 0) for e in self.records.data.values()), default=0)
        tail = self.t("menu_best", n=number(best)) if best else self.t("menu_no_best")
        return self.t("footer", v=VERSION) + " · " + tail

    def in_progress(self):
        """Игра на поле начата и не кончена (её можно продолжить из меню)."""
        return bool(self.games) and not self.finished

    def menu_play(self):
        """Главная кнопка меню: начатая игра - вернуться в неё (на паузе), иначе новая."""
        if self.in_progress():
            self.stack.setCurrentWidget(self.play)
            self.setFocus()
        else:
            self.start_game()

    def auto_pause(self):
        """Игра встаёт на паузу сама: ушли в меню, свернули окно, переключились на другое окно
        или вкладку оболочки (проверка 17.10: свёрнутая игра шла дальше и кончалась)."""
        if self.in_progress() and not self.paused:
            self.toggle_pause()

    def abandon(self):
        """Брошенная дуэль (новая игра, закрытие окна) после первой вашей фигуры - поражение, как в
        Дураке и КНБ; одиночная игра - просто кончается без рекорда."""
        if self.in_progress() and self.duel is not None and self.games[0].pieces > 0:
            self.ctx.stats.record("duel/" + self.level, "loss")
            me = self.games[0]
            self.history.record({"mode": "duel", "level": self.level, "outcome": "loss",
                                 "lines": me.lines, "score": me.score, "abandoned": 1})
        self.finished = True

    def pause(self):
        """Вкладку оболочки скрыли: игра на паузе, фон меню стоит."""
        self.auto_pause()
        self.menu.pause()
        self.timer.stop()

    def resume(self):
        self.menu.resume()
        if self.in_progress():
            self.timer.start()          # игра ждёт на паузе - «Продолжить» нажимает человек

    def changeEvent(self, event):
        if event.type() == QEvent.Type.ActivationChange and not self.isActiveWindow():
            self.auto_pause()
        elif event.type() == QEvent.Type.WindowStateChange and self.window().isMinimized():
            self.auto_pause()
        super().changeEvent(event)

    def show_page(self, name):
        if name == "menu":
            self.menu.sync(self.settings)
        if name != "play":
            self.auto_pause()           # игра ждёт на паузе - «Продолжить» в меню
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
        self.abandon()
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
        # одиночная с «Мыслями ИИ» с самого начала - не в рекорды (решение автора 17.10)
        self.assisted = self.mode == "solo" and s["show_thoughts"]
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
        # число фигур «до такта» - с самого начала: подсказка может прийти раньше первого
        # такта, а фигура лечь от клавиши до него (тогда смену фигуры такт не увидит)
        self.seen_pieces = [g.pieces for g in self.games]
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
        if not self.games[0].over:
            self.assisted = True        # с подсказкой игра не идёт в рекорды (как в Сапёре)
            self._update_status()
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
        before = self.seen_pieces
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
            me = self.games[0]
            self.history.record({"mode": "duel", "level": self.level, "outcome": result,
                                 "lines": me.lines, "score": me.score})
            self.ctx.sound.play("win" if result == "win" else "loss" if result == "loss" else "draw")
            self._finish({"win": "duel_win", "loss": "duel_loss", "draw": "duel_draw"}[result])
        elif self.games and self.games[0].over:
            g = self.games[0]
            key = "solo" if self.mode == "solo" else "ai/" + self.level
            helped = self.mode == "solo" and self.assisted
            if not helped:                              # с подсказкой или «Мыслями ИИ» - мимо рекордов
                self.records.add(key, g.lines, g.score)
            if self.mode == "solo" and not helped:      # одиночная игра всегда кончается «стаканом»
                self.history.record({"mode": "solo", "level": "solo", "outcome": "loss",
                                     "lines": g.lines, "score": g.score})
            self.ctx.sound.play("loss" if self.mode == "solo" else "draw")
            self._finish("game_over_assisted" if helped else "game_over")

    def _finish(self, text_key):
        self.finished = True
        self.timer.stop()
        self.play.cols[0].board.banner = self.t("game_over" if text_key == "game_over_assisted" else text_key)
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
        if self.mode == "solo" and getattr(self, "assisted", False) and not final:
            info += " " + t("assisted_note")
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
            if code == int(Qt.Key.Key_Escape):
                # Esc - отмена назначения (проверка 17.10: назначал Esc и менял местами с паузой)
                self.capturing = None
                self.settings_page.sync()
                return
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
        """Остановить таймер и поток ИИ за 2 секунды (контракт aikit). Начатая дуэль - поражение."""
        self.abandon()
        self.stop_game()
        return self.worker.shutdown(2.0)

    def minimumSizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(900, 700)

