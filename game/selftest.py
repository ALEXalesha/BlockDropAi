"""Самопроверка без экрана: python main.py --selftest итог.txt.

Нужна прежде всего собранному exe: он без консоли, поэтому итог пишется в файл. Окно
создаётся offscreen, данные игрока - во временной папке, его настройки и статистику она
не трогает. Проверяется: правила (случайные партии с законами), модель, ИИ кнопками,
окно в трёх режимах, остановка за 2 секунды.
"""
import os
import random
import tempfile
import time
import traceback


def selftest(out_path):
    lines = []
    code = 0
    try:
        from aikit import offscreen
        offscreen.setup(force=True)
        home = tempfile.mkdtemp(prefix="blockdrop-selftest-")
        os.environ["BLOCKDROPAI_HOME"] = home
        from PySide6.QtWidgets import QApplication

        import aikit
        from aikit.host import make_window
        from game import APP_NAME, GAME_INFO, create_widget
        from game.ai import player as P
        from game.core import blocks as B
        from game.train import passport as PP
        from game.version import VERSION

        lines.append(f"BlockDropAi {VERSION} самопроверка (aikit {aikit.__version__})")
        lines.append(f"собранная версия: {'да' if aikit.frozen() else 'нет'}")
        t0 = time.time()
        rng = random.Random(1)
        keys = ["L", "R", "cw", "ccw", "sd", "hd", "hold"]
        for seed in range(30):
            g = B.Game(seed=seed, level=1 + seed % 10)
            for _ in range(300):
                if g.over:
                    break
                g.press(rng.choice(keys))
                g.update(rng.random() * 0.2)
                if not g.over and not B.fits(g.board, *g.piece()):
                    raise RuntimeError("фигура внутри стопки")
                if any(r == B.FULL for r in g.board):
                    raise RuntimeError("полный ряд остался")
        lines.append(f"правила: 30 случайных партий без нарушений, {time.time() - t0:.2f} с")
        model = PP.load_model()
        pp = model.get("passport")
        lines.append("модель: " + (f"веса CEM, {model['training']['generations']} поколений"
                                    + (", паспорт есть" if pp else ", паспорта нет")))
        t0 = time.time()
        r = P.play_game(PP.level_agent("strong", model), seed=7, max_lines=100)
        lines.append(f"сильный ИИ кнопками: {r['lines']} линий за {r['pieces']} фигур, {time.time() - t0:.2f} с")

        app = QApplication.instance() or QApplication([])
        window, ctx = make_window(GAME_INFO, create_widget, APP_NAME, root=home)
        window.resize(1280, 800)
        window.show()
        g = window.game
        app.processEvents()
        from aikit.menu import layout_problems
        if g.current_page() != "menu":
            raise RuntimeError("окно открылось не меню")
        bad = layout_problems(g.menu)
        if bad:
            raise RuntimeError("меню обрезано: " + "; ".join(bad[:3]))
        lines.append("меню: открыто первым, раскладка цела")

        def spin(cond, limit):
            end = time.time() + limit
            while not cond() and time.time() < end:
                app.processEvents()
                time.sleep(0.003)
            return cond()

        g.change("mode", "solo")
        g.start_game(seed=3)
        game = g.games[0]
        y = game.y
        if not spin(lambda: game.y < y, 3):
            raise RuntimeError("фигура не падает по часам")
        game.press("hd")
        lines.append("играю сам: фигура падает по часам, сброс работает")
        g.change("mode", "ai")
        g.change("level", "medium")
        g.change("speed", "max")
        g.start_game(seed=5)
        game = g.games[0]
        t0 = time.time()
        if not spin(lambda: game.lines >= 50 or game.over, 60):
            raise RuntimeError("ИИ не набрал 50 линий за минуту")
        lines.append(f"играет ИИ (максимум): {game.lines} линий, {game.pieces} фигур, {time.time() - t0:.2f} с")
        g.change("mode", "duel")
        g.change("level", "strong")
        g.start_game(seed=2)
        me, ai = g.games
        if not spin(lambda: ai.pieces >= 2, 10):
            raise RuntimeError("ИИ в дуэли не ходит")
        image = window.grab().toImage()
        if image.isNull() or image.width() < 300:
            raise RuntimeError("окно не нарисовалось")
        lines.append(f"дуэль: ИИ поставил {ai.pieces} фигуры, кадр {image.width()}x{image.height()}")
        t0 = time.time()
        if not g.shutdown():
            raise RuntimeError("поток ИИ не остановился за 2 секунды")
        window.close()
        app.processEvents()
        lines.append(f"окно закрыто за {time.time() - t0:.2f} с")
        lines.append("ИТОГ: работает")
    except Exception:  # noqa: BLE001 - любая ошибка должна попасть в файл
        lines.append("ИТОГ: ошибка")
        lines.append(traceback.format_exc())
        code = 1
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return code
