"""Кадры для README и списка игр: окно без экрана в нескольких режимах.

    python tools/make_previews.py [папка]     # по умолчанию docs/

Кадры - только программой (Qt offscreen), никогда снимком экрана.
"""
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from aikit import offscreen  # noqa: E402

offscreen.setup(force=True)
HOME = tempfile.mkdtemp(prefix="blockdrop-previews-")


def spin(app, seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)


def until(app, cond, limit=60):
    end = time.time() + limit
    while not cond() and time.time() < end:
        app.processEvents()
        time.sleep(0.005)


def main(out):
    from PySide6.QtWidgets import QApplication

    from aikit.host import make_window
    from game import APP_NAME, GAME_INFO, create_widget

    os.makedirs(out, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    window, ctx = make_window(GAME_INFO, create_widget, APP_NAME, root=HOME)
    window.resize(1280, 800)
    window.show()
    g = window.game
    shots = []
    for theme_name in ("dark", "light"):
        ctx.set_theme(theme_name)
        sfx = "" if theme_name == "dark" else "_light"
        g.show_page("menu")
        spin(app, 0.2)
        shots.append(("preview_menu" + sfx, window.grab()))
        # ИИ играет сам, с «Мыслями ИИ»
        g.change("mode", "ai")
        g.change("level", "strong")
        g.change("speed", "max")
        g.change("show_thoughts", True)
        g.start_game(seed=11)
        until(app, lambda: g.games[0].lines >= 60)
        g.change("speed", "real")
        spin(app, 1.5)
        shots.append(("preview_ai" + sfx, window.grab()))
        # дуэль
        g.change("show_thoughts", False)
        g.change("mode", "duel")
        g.change("level", "medium")
        g.start_game(seed=4)
        me = g.games[0]
        for i in range(14):
            for key in (("L", "L", "cw") if i % 3 == 0 else ("R", "R") if i % 3 == 1 else ("ccw",)):
                me.press(key)
            me.press("hd")
            spin(app, 0.35)
        spin(app, 1.0)
        shots.append(("preview_duel" + sfx, window.grab()))
        g.show_page("stats")
        spin(app, 0.2)
        shots.append(("preview_stats" + sfx, window.grab()))
    ctx.set_theme("dark")
    for name, pix in shots:
        pix.save(os.path.join(out, name + ".png"))
        print(os.path.join(out, name + ".png"))
    # кадр для списка игр 16:9
    preview = [p for n, p in shots if n == "preview_ai"][0]
    preview.save(os.path.join(out, "preview.png"))
    g.shutdown()
    window.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "docs"))
