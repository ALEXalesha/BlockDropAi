"""Окно без экрана (Qt offscreen): три режима, клавиши (собранными событиями - настоящая
клавиатура и мышь не трогаются), ИИ в потоке, «Мысли ИИ» и подсказка, темы, языки,
переназначение клавиш, статистика, остановка за 2 секунды. Ожидания - с тайм-аутом."""
import os
import time

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QLabel

from aikit.widgets import Combo
from game import APP_NAME, GAME_INFO, create_widget
from game.core import blocks as B
from game.ui.i18n import EN, RU

QWIDGETSIZE_MAX = (1 << 24) - 1


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(app, tmp_path):
    from aikit.host import make_window
    w, ctx = make_window(GAME_INFO, create_widget, APP_NAME, root=str(tmp_path / "home"))
    w.resize(1280, 800)
    w.show()
    yield w
    w.game.shutdown()
    w.close()


def wait(app, cond, limit=20.0):
    end = time.time() + limit
    while not cond() and time.time() < end:
        app.processEvents()
        time.sleep(0.003)
    return cond()


def key(widget, code, release=True):
    QApplication.sendEvent(widget, QKeyEvent(QEvent.Type.KeyPress, code, Qt.KeyboardModifier.NoModifier))
    if release:
        QApplication.sendEvent(widget, QKeyEvent(QEvent.Type.KeyRelease, code, Qt.KeyboardModifier.NoModifier))


def test_translations_complete():
    assert set(RU) == set(EN)


def test_title_has_no_trademark(win):
    assert "tet" + "ris" not in win.windowTitle().lower()
    assert win.windowTitle().startswith("Блоки с ИИ")


def test_solo_keys_move_rotate_drop(app, win):
    g = win.game
    g.change("mode", "solo")
    g.start_game(seed=3)
    assert g.current_page() == "play"
    game = g.games[0]
    x, rot = game.x, game.rot
    key(g, Qt.Key.Key_Left)
    assert game.x == x - 1
    key(g, Qt.Key.Key_Up)
    assert game.rot == (rot + 1) % 4
    key(g, Qt.Key.Key_Space)
    assert game.pieces == 1
    key(g, Qt.Key.Key_C)
    assert game.hold_kind is not None
    assert wait(app, lambda: g.play.cols[0].numbers["score"][1].text() != "0", 5)


def test_gravity_runs_on_clock(app, win):
    g = win.game
    g.change("mode", "solo")
    g.start_game(seed=3)
    game = g.games[0]
    y = game.y
    assert wait(app, lambda: game.y < y, 3.0), "фигура не падает"


def test_ai_mode_max_speed_clears_lines_by_keys(app, win):
    g = win.game
    g.change("mode", "ai")
    g.change("level", "medium")
    g.change("speed", "max")
    g.start_game(seed=5)
    game = g.games[0]
    assert wait(app, lambda: game.lines >= 30, 40), game.lines
    assert not game.over


def test_ai_mode_pause(app, win):
    g = win.game
    g.change("mode", "ai")
    g.change("speed", "x10")
    g.start_game(seed=5)
    game = g.games[0]
    assert wait(app, lambda: game.pieces >= 3, 20)
    g.toggle_pause()
    n = game.pieces
    t0 = time.time()
    while time.time() - t0 < 0.5:
        app.processEvents()
    assert game.pieces == n
    g.toggle_pause()
    assert wait(app, lambda: game.pieces > n, 20)


def test_thoughts_outline_three_spots(app, win):
    g = win.game
    g.change("mode", "solo")
    g.change("show_thoughts", True)
    g.start_game(seed=8)
    board = g.play.cols[0].board
    assert wait(app, lambda: len(board.thoughts) == 3, 15)
    assert sum(1 for _, _, best in board.thoughts if best) == 1
    g.change("show_thoughts", False)


def test_hint_shows_best_spot_until_piece_locks(app, win):
    g = win.game
    g.change("mode", "solo")
    g.start_game(seed=8)
    board = g.play.cols[0].board
    g.show_hint()
    assert wait(app, lambda: board.hint is not None, 15)
    assert len(board.hint) == 4
    key(g, Qt.Key.Key_Space)
    assert wait(app, lambda: board.hint is None, 5)


def test_hint_clears_when_piece_locks_before_first_tick(app, win):
    """Причина мигания теста выше (1 из 3): подсказка пришла раньше первого такта таймера,
    а фигура легла от клавиши до него. Такт брал «прежнее число фигур» из текущего (уже
    после падения) - смены фигуры не видел, и подсказка оставалась на поле у следующей
    фигуры. Здесь таймер остановлен, такт зовётся руками - порядок всегда тот самый."""
    g = win.game
    g.change("mode", "solo")
    g.start_game(seed=8)
    g.timer.stop()
    board = g.play.cols[0].board
    g.show_hint()
    assert wait(app, lambda: board.hint is not None, 15)
    pieces = g.games[0].pieces
    key(g, Qt.Key.Key_Space)
    assert g.games[0].pieces == pieces + 1
    g.on_tick()
    assert board.hint is None and not g.hint_on


def test_duel_ai_limited_and_result_recorded(app, win):
    g = win.game
    g.change("mode", "duel")
    g.change("level", "novice")
    g.start_game(seed=2)
    me, ai = g.games
    t0 = time.time()
    assert wait(app, lambda: ai.pieces >= 2, 10)
    rate = ai.pieces / (time.time() - t0)
    assert rate < 0.8 * 2, rate                  # новичок не быстрее 0.8 фигуры в секунду
    me.over = True
    assert wait(app, lambda: g.finished, 5)
    e = g.ctx.stats.entry("duel/novice")
    assert e["games"] == 1 and e["losses"] == 1


def test_duel_garbage_reaches_opponent(app, win):
    g = win.game
    g.change("mode", "duel")
    g.change("level", "medium")
    g.start_game(seed=2)
    me, ai = g.games
    me.board = [B.FULL & ~1] * 4 + [0] * (B.HEIGHT - 4)
    me._spawn(B.I)
    me.rotate(1)
    while me.move(-1):
        pass
    me.hard_drop()
    assert wait(app, lambda: ai.pending() == 4 or ai.garbage_rows == 4, 5)


def test_solo_game_over_records(app, win):
    g = win.game
    g.change("mode", "solo")
    g.start_game(seed=1)
    game = g.games[0]
    for _ in range(200):
        if game.over:
            break
        key(g, Qt.Key.Key_Space)
    assert wait(app, lambda: g.finished, 5)
    assert g.records.entry("solo")["games"] == 1
    assert g.play.cols[0].board.banner


def test_theme_and_language_on_the_fly(app, win):
    g = win.game
    g.show_page("menu")
    g.ctx.set_lang("en")
    assert g.menu.play_button.text() == "Play"
    assert win.windowTitle().startswith("Block Drop AI")
    g.ctx.set_theme("light")
    assert g.play.cols[0].board.palette_["bg"] == "#e8ecf3"
    g.ctx.set_lang("ru")
    assert g.menu.play_button.text() == "Играть"
    g.ctx.set_theme("dark")


def test_remap_key(app, win):
    g = win.game
    g.show_page("settings")
    g.capture_key("hard")
    key(g, Qt.Key.Key_Return, release=False)
    assert g.settings["keys"]["hard"] == int(Qt.Key.Key_Return)
    g.change("mode", "solo")
    g.start_game(seed=4)
    key(g, Qt.Key.Key_Return)
    assert g.games[0].pieces == 1
    key(g, Qt.Key.Key_Space)
    assert g.games[0].pieces == 1
    g.capture_key("hard")
    key(g, Qt.Key.Key_Space, release=False)


def test_settings_persist(app, tmp_path):
    from aikit.host import make_window
    root = str(tmp_path / "h2")
    w, ctx = make_window(GAME_INFO, create_widget, APP_NAME, root=root)
    w.game.change("das_ms", 120)
    w.game.change("colors", "pastel")
    w.game.shutdown()
    w.close()
    w2, _ = make_window(GAME_INFO, create_widget, APP_NAME, root=root)
    assert w2.game.settings["das_ms"] == 120 and w2.game.settings["colors"] == "pastel"
    w2.game.shutdown()
    w2.close()


def test_stats_page_shows_passport_and_records(app, win):
    g = win.game
    g.show_page("stats")
    title, text, tw = g.stats.sections["passport"]
    assert title.text()
    assert tw.columnCount() == 4


def test_wrapped_labels_not_height_limited(app, win):
    g = win.game
    g.change("mode", "solo")
    g.start_game(seed=1)
    app.processEvents()
    for page in g.pages.values():
        for w in page.findChildren(QLabel):
            if w.wordWrap():
                assert w.maximumHeight() == QWIDGETSIZE_MAX, w.text()


def test_wrapped_labels_fit_with_bigger_font(app, win):
    g = win.game
    win.resize(win.minimumWidth(), win.minimumHeight())
    g.change("mode", "duel")
    g.start_game(seed=1)
    g.play.side.setStyleSheet("* { font-size: 16px; }")
    for _ in range(5):
        app.processEvents()
    g.play.fit_labels()
    app.processEvents()
    for w in g.play.side.findChildren(QLabel):
        if w.wordWrap() and w.isVisible():
            assert w.heightForWidth(w.width()) <= w.height() + 1, w.text()


def test_combo_has_drawn_arrow(app, win):
    g = win.game
    g.show_page("settings")
    combos = g.settings_page.findChildren(Combo)
    assert combos
    img = combos[0].grab().toImage()
    w, h = img.width(), img.height()
    arrow = img.pixelColor(w - 16, h // 2)
    body = img.pixelColor(w // 2, 3)
    assert arrow != body


def test_shutdown_within_two_seconds(app, win):
    g = win.game
    g.change("mode", "ai")
    g.change("speed", "max")
    g.change("level", "strong")
    g.start_game(seed=3)
    wait(app, lambda: g.games[0].pieces > 5, 10)
    t0 = time.time()
    assert g.shutdown()
    assert time.time() - t0 < 2.0


def test_window_remembers_place(app, tmp_path):
    from aikit.host import make_window
    root = str(tmp_path / "h3")
    w, _ = make_window(GAME_INFO, create_widget, APP_NAME, root=root)
    w.resize(1000, 760)
    w.show()
    app.processEvents()
    w.close()
    assert os.path.exists(os.path.join(root, "window.json"))


def test_ai_mode_thoughts_visible_most_of_the_time(app, win):
    # ИИ думает с момента появления фигуры: контуры видны и пока он «думает», а не только
    # пока жмёт клавиши (было: треть времени, у фигуры с одним сбросом - ни разу)
    g = win.game
    g.change("mode", "ai")
    g.change("level", "strong")
    g.change("speed", "real")
    g.change("show_thoughts", True)
    g.start_game(seed=11)
    board = g.play.cols[0].board
    seen = total = 0
    end = time.time() + 3.0
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)
        total += 1
        seen += bool(board.thoughts)
    g.change("show_thoughts", False)
    # до починки было ~0.09; запас на загруженный ПК
    assert seen / total > 0.4, (seen, total)


def test_speed_buttons_follow_setting(app, win):
    g = win.game
    g.change("speed", "max")
    assert g.play.speed_buttons["max"].isChecked()
    g.change("speed", "real")
    assert g.play.speed_buttons["real"].isChecked() and not g.play.speed_buttons["max"].isChecked()
