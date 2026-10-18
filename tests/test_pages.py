"""Настройки и статистика в стиле «неонового зала» (aikit.skin, автор 17.10) и находки проверки
17.10: пауза при сворачивании и уходе со страницы, «Продолжить» в меню, брошенная дуэль -
поражение, дуэль 900x700 без срезанных стаканов, Esc при назначении клавиши - отмена."""
import time

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QRect, Qt
from PySide6.QtGui import QFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from aikit.menu import SIZES, Title, layout_problems
from aikit.skin import DEFAULT, SkinPage, difference, page_problems
from game import APP_NAME, GAME_INFO, create_widget
from game.ui.skin import SKIN


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
    w.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def pump(app, seconds=0.05, until=None):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        if until is not None and until():
            return True
        time.sleep(0.003)
    return until() if until is not None else True


def duel(app, g, pieces=1):
    g.change("mode", "duel")
    g.start_game(seed=3)
    me = g.games[0]
    for _ in range(pieces):
        g.human.press("hard", time.monotonic())
        g.human.release("hard", time.monotonic())
        pump(app, 2, lambda: me.pieces > 0)
    return me


def test_pages_are_skin_pages_unlike_aikit(app, win):
    g = win.game
    assert isinstance(g.stats, SkinPage) and isinstance(g.settings_page, SkinPage)
    assert g.stats.skin is SKIN and all(c.skin is SKIN for c in g.stats.charts.charts())
    assert SKIN.signature() != DEFAULT.signature()
    for theme in ("dark", "light"):
        for name in ("stats", "settings"):
            g.show_page(name)
            pump(app)
            page = g.pages[name]
            page.set_theme(theme)
            own = page.grab()
            page.skin = DEFAULT
            page.set_theme(theme)
            plain = page.grab()
            page.skin = SKIN
            page.set_theme(theme)
            assert difference(own, plain) > 0.3, (theme, name)


def test_heading_weight_is_an_enum():
    """Вес 900 числом валил Qt при смене стилей соседней страницы - теперь QFont.Weight."""
    t = Title(SKIN.heading_family, 30, weight=SKIN.heading_weight)
    assert t.make_font(30).weight() == QFont.Weight.Black


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("lang", ["ru", "en"])
def test_pages_clean_from_narrow_to_4k(app, win, theme, lang):
    g = win.game
    win.ctx.set_theme(theme)
    win.ctx.set_lang(lang)
    for name in ("stats", "settings"):
        g.show_page(name)
        for w, h in SIZES:
            win.resize(max(w, win.minimumWidth()), max(h, win.minimumHeight()))
            pump(app, 0.03)
            assert page_problems(g.pages[name]) == [], (name, w, h)


def test_settings_groups(app, win):
    g = win.game
    g.show_page("settings")
    sp = g.settings_page
    assert [x.text() for x in sp.box.groups] == [g.t("group_view").upper(), g.t("group_game").upper()]


@pytest.mark.parametrize("mode", ["solo", "duel"])
def test_wells_whole_in_their_columns_at_minimum(app, win, mode):
    """Проверка 17.10: дуэль в окне 900x700 - правый край обоих стаканов срезан, имя «ИИ: Средн»."""
    g = win.game
    g.change("mode", mode)
    g.start_game(seed=1)
    for size in ((900, 700), (1180, 780), (1920, 1080)):
        win.resize(*size)
        pump(app, 0.08)
        for c in g.play.cols[:len(g.games)]:
            box = QRect(c.board.mapTo(g.play, QPoint(0, 0)), c.board.size())
            col = QRect(c.mapTo(g.play, QPoint(0, 0)), c.size())
            assert col.contains(box), (mode, size, box, col)
            s = c.board.cell_size()
            assert s * 10 <= c.board.width() + 0.5
            assert s >= 12, (mode, size, s)              # стакан не в нитку: клетка от 12 px
            assert g.play.rect().contains(col), (mode, size)
            assert layout_problems(c) == [], (mode, size)


def test_minimize_pauses(app, win):
    """Проверка 17.10: свернул окно - игра шла дальше и кончалась."""
    g = win.game
    g.change("mode", "solo")
    g.start_game(seed=1)
    assert not g.paused
    g.changeEvent(QEvent(QEvent.Type.ActivationChange))      # окно больше не активно
    assert g.paused


def test_shell_pause_resume(app, win):
    g = win.game
    g.change("mode", "solo")
    g.start_game(seed=1)
    g.pause()
    assert g.paused and not g.timer.isActive() and not g.menu.running()
    g.resume()
    assert g.paused and g.timer.isActive()            # «Продолжить» - человек сам


def test_menu_continues_the_game(app, win):
    g = win.game
    g.change("mode", "solo")
    g.start_game(seed=1)
    game = g.games[0]
    g.show_page("menu")
    assert g.paused and g.games and g.games[0] is game
    assert g.menu.play_button.text() == g.t("continue") and g.menu.new_button.isVisibleTo(g.menu)
    g.menu.play_button.click()
    assert g.current_page() == "play" and g.games[0] is game
    g.show_page("settings")
    assert g.games and g.games[0] is game                # настройки посмотреть, не бросая игру


def test_abandoned_duel_is_a_loss(app, win):
    g = win.game
    duel(app, g, 1)
    g.show_page("menu")
    g.menu.new_button.click()
    e = g.ctx.stats.entry("duel/" + g.level)
    assert e["games"] == 1 and e["losses"] == 1
    assert g.history.games[-1].get("abandoned") == 1


def test_duel_left_before_first_piece_is_not_counted(app, win):
    g = win.game
    g.change("mode", "duel")
    g.start_game(seed=3)
    g.start_game(seed=4)
    assert g.ctx.stats.entry("duel/" + g.level)["games"] == 0


def test_closing_mid_duel_is_a_loss(app, win):
    g = win.game
    duel(app, g, 1)
    g.shutdown()
    assert g.ctx.stats.entry("duel/" + g.level)["games"] == 1


def test_escape_cancels_key_capture(app, win):
    """Проверка 17.10: Esc при назначении клавиши назначал Esc и менял местами с паузой."""
    g = win.game
    g.show_page("settings")
    before = dict(g.settings["keys"])
    g.capture_key("left")
    QTest.keyClick(g, Qt.Key.Key_Escape)
    assert g.capturing is None and dict(g.settings["keys"]) == before
    assert g.settings_page.key_buttons["left"].text() != g.t("press_key")
