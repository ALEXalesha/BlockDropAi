"""Своё стартовое меню, боковая панель партии в его стиле и настройки на всю ширину (автор 17.10:
у каждой игры меню своё, «боковые меню тоже разнообразить»; настройки - как статистика).

Законы:
- окно открывается меню; фон зала живёт, пока меню на экране, и стоит на других страницах;
- меню цело (ничего за краем, текст влезает, соседи не налезают) от минимального окна до 4K, в
  обеих темах, на двух языках; падающие фигуры не заходят на середину с кнопками;
- боковая панель партии - в стиле меню и цела во всех режимах и размерах;
- карточка настроек занимает почти всю ширину страницы;
- стакан партии - в цветах зала.
"""
import time

import pytest
from PySide6.QtCore import QRectF
from PySide6.QtWidgets import QApplication

from aikit.menu import SIZES, Backdrop, fill_share, layout_problems
from game import APP_NAME, GAME_INFO, create_widget
from game.core import blocks as B
from game.ui import menu as M


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


def pump(app, seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.003)


def resize(win, w, h):
    win.resize(max(w, win.minimumWidth()), max(h, win.minimumHeight()))


def test_window_opens_with_the_menu_and_arcade_lives_only_there(app, win):
    g = win.game
    assert g.current_page() == "menu"
    assert isinstance(g.menu, Backdrop) and g.menu.running()
    t0 = g.menu.t
    pump(app, 0.2)
    assert g.menu.t > t0
    g.start_game(seed=1)
    assert g.current_page() == "play" and not g.menu.running()
    g.show_page("menu")
    assert g.menu.running()


def test_menu_has_its_own_style(app, win):
    g = win.game
    assert isinstance(g.menu, M.Arcade) and isinstance(g.menu.title, M.BlockTitle)
    css = g.menu.styleSheet()
    assert "QFrame#cabinet" in css and "border-bottom" in css and "arcadeB" in css
    assert g.menu.title.text() == g.t("app_title").upper()


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("lang", ["ru", "en"])
def test_menu_is_whole_at_every_size(app, win, theme, lang):
    g = win.game
    win.ctx.set_theme(theme)
    win.ctx.set_lang(lang)
    for mode in ("solo", "duel"):
        g.change("mode", mode)
        for w, h in SIZES:
            resize(win, w, h)
            pump(app, 0.03)
            g.menu.grab()
            assert layout_problems(g.menu) == [], (theme, lang, mode, win.size())


def test_falling_pieces_keep_off_the_buttons(app, win):
    g = win.game
    for w, h in SIZES:
        resize(win, w, h)
        pump(app, 0.03)
        col = g.menu.column_rect()
        seen = 0
        for t in range(0, 60, 3):
            for kind, rot, x, y, c in g.menu.piece_boxes(g.menu.width(), g.menu.height(), float(t)):
                for cx, cy in B.CELLS[kind][rot]:
                    cell = QRectF(x + cx * c, y + (3 - cy) * c, c, c)
                    assert not cell.intersects(col), (win.size(), t)
                    assert 0 <= cell.left() and cell.right() <= g.menu.width()
                    seen += 1
        assert seen > 0, win.size()                 # фигуры падают при любом размере окна


def test_menu_scales_up_on_big_windows(app, win):
    g = win.game
    resize(win, 1280, 800)
    pump(app, 0.03)
    small = (g.menu.play_button.width(), g.menu.title.px)
    resize(win, 3840, 2160)
    pump(app, 0.03)
    assert g.menu.play_button.width() > small[0] * 1.8 and g.menu.title.px > small[1] * 1.8


def test_settings_card_stretches_like_stats(app, win):
    g = win.game
    g.show_page("settings")
    for w, h in SIZES:
        resize(win, w, h)
        pump(app, 0.03)
        page = g.settings_page
        assert fill_share(page.box, page) > 0.9, (win.size(), page.box.width(), page.width())


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("lang", ["ru", "en"])
def test_side_panel_in_menu_style_and_whole(app, win, theme, lang):
    g = win.game
    win.ctx.set_theme(theme)
    win.ctx.set_lang(lang)
    pal = M.palette(theme)
    assert "border-bottom" in g.play.side.styleSheet() and pal["neon"] in g.play.side.styleSheet()
    assert pal["bg"] in g.play.styleSheet()
    assert g.play.cols[0].board.palette_["surface"] == pal["well"]
    for mode, thoughts in (("solo", True), ("ai", False), ("duel", True)):
        g.change("mode", mode)
        g.change("show_thoughts", thoughts)
        g.start_game(seed=2)
        for w, h in SIZES:
            resize(win, w, h)
            pump(app, 0.03)
            g.play.side.grab()
            assert layout_problems(g.play.side) == [], (mode, win.size())
        g.show_page("menu")
    g.change("show_thoughts", False)


def test_narrow_lane_gets_no_pieces(app, win):
    """Полоса уже фигуры - фигур в ней нет (иначе они легли бы на кнопки или за край)."""
    g = win.game
    resize(win, 1280, 800)
    pump(app, 0.03)
    g.menu.lanes = (0.0, 30.0, 700.0, float(g.menu.width()))
    boxes = g.menu.piece_boxes(g.menu.width(), g.menu.height(), 5.0)
    assert boxes and all(x >= 700.0 for _, _, x, _, _ in boxes)
    g.menu.lanes = (0.0, 30.0, 1250.0, 1280.0)
    assert g.menu.piece_boxes(g.menu.width(), g.menu.height(), 5.0) == []
