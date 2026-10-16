"""Графики статистики из общего aikit.charts (правило автора 10.10 - графики во всех играх с ИИ).

Законы: на странице статистики графики aikit; дуэль с ИИ и одиночная игра пишутся в журнал
(режим, уровень, итог, линии, очки), игра ИИ в окне - нет; без игр - заглушки словами; подписи
целы (chart.clipped пуст) в обеих темах, на обоих языках, в широком и самом узком окне; рекорд
одиночной игры - лучшие очки к этой игре."""
from PySide6.QtCore import Qt

from aikit.charts import ChartCard, all_charts
from tests.test_ui import app, key, wait, win  # noqa: F401 - фикстуры окна


def labels_intact(app, win, g):
    for theme in ("dark", "light"):
        for lang in ("ru", "en"):
            win.ctx.set_theme(theme)
            win.ctx.set_lang(lang)
            for width in (1400, win.minimumWidth()):
                win.resize(width, 820)
                app.processEvents()
                for c in all_charts(g.stats):
                    c.grab()
                    assert c.clipped == [], (theme, lang, width, c.title, c.clipped)
                    assert c.theme == theme
    win.ctx.set_theme("dark")
    win.ctx.set_lang("ru")


def test_charts_are_aikit_and_stubs_without_games(app, win):
    g = win.game
    g.show_page("stats")
    charts = all_charts(g.stats)
    assert len(charts) >= 6 and all(isinstance(c, ChartCard) for c in charts)
    ch = g.stats.charts
    for c in (ch.share, ch.by_level, ch.length, ch.records, g.stats.solo_chart):
        c.grab()
        assert c.shown_empty and c.empty_text, c.title
    labels_intact(app, win, g)


def test_duel_and_solo_go_to_the_log(app, win):
    g = win.game
    g.change("mode", "duel")
    g.change("level", "novice")
    g.start_game(seed=2)
    me, ai = g.games
    me.over = True
    assert wait(app, lambda: g.finished, 5)
    g.change("mode", "solo")
    g.start_game(seed=1)
    game = g.games[0]
    for _ in range(200):
        if game.over:
            break
        key(g, Qt.Key.Key_Space)
    assert wait(app, lambda: g.finished, 5)
    games = g.history.games
    assert [(x["mode"], x["level"], x["outcome"]) for x in games] == [("duel", "novice", "loss"), ("solo", "solo", "loss")]
    assert games[1]["score"] == game.score and games[1]["lines"] == game.lines


def test_ai_mode_stays_out_of_the_log(app, win):
    g = win.game
    g.change("mode", "ai")
    g.start_game(seed=3)
    g.games[0].over = True
    assert wait(app, lambda: g.finished, 5)
    assert g.history.games == []


def test_charts_from_the_log_and_solo_record(app, win):
    g = win.game
    for i, (outcome, lines, score) in enumerate((("win", 12, 900), ("loss", 4, 300), ("draw", 8, 650), ("win", 15, 1200))):
        g.history.record({"mode": "duel", "level": ("novice", "medium", "strong")[i % 3], "outcome": outcome,
                          "lines": lines, "score": score})
    for score in (500, 2400, 1800):
        g.history.record({"mode": "solo", "level": "solo", "outcome": "loss", "lines": score // 100, "score": score})
    g.show_page("stats")
    ch = g.stats.charts
    for c in (ch.share, ch.by_level, ch.length, ch.records, g.stats.solo_chart):
        c.grab()
        assert not c.shown_empty, c.title
    assert [x for x, _ in ch.share.points] == [1, 2, 3, 4]      # одиночные игры не в доле побед
    assert g.stats.solo_chart.second == [(1, 500), (2, 2400), (3, 2400)]   # свои номера игр
    assert ch.passport.has_data() and not ch.passport.percent
    labels_intact(app, win, g)
