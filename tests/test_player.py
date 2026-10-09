"""Игрок-ИИ: видит только то, что видит человек (поле, фигура, очередь из 5, hold), играет
нажатиями через настоящую партию, взгляд вперёд и hold - у сильного."""
import random

import pytest

from game.ai import player as P
from game.core import blocks as B
from game.core.blocks import HEIGHT, Game

W = [-1.0, 1.0, -1.0, -1.0, -4.0, -1.0, 0.0, 0.0, 0.0, 0.0, 0.0]   # веса Дельяши


def board_from(lines):
    b = [0] * HEIGHT
    for r, line in enumerate(lines):
        b[r] = sum(1 << x for x, ch in enumerate(line) if ch == "#")
    return b


@pytest.mark.parametrize("cfg", [dict(), dict(search="full"), dict(search="full", lookahead=True, use_hold=True)])
def test_plays_by_buttons_and_lands_where_planned(cfg):
    agent = P.Agent(P.Linear(W), **cfg)
    g = Game(seed=4, gravity=False)
    for _ in range(120):
        if g.over:
            break
        d = agent.choose(P.observe(g))
        pieces = g.pieces
        landed = None
        for key in d.path:
            if key == "hd":
                landed = (g.kind, g.rot, g.x, g.ghost_y())
            ok = g.press(key)
            assert ok, (key, d.path)
        assert g.pieces == pieces + 1
        p = d.placement
        assert landed == (p.kind, p.rot, p.x, p.y)
    assert g.lines > 20


def test_view_shows_only_what_player_sees():
    g = Game(seed=8)
    v = P.observe(g)
    assert v.preview == tuple(g.queue[:B.PREVIEW])
    assert not hasattr(v, "bag")
    # будущее за пределами видимой очереди не меняет решения
    h = Game(seed=8)
    h.queue[B.PREVIEW:] = [(k + 3) % 7 for k in h.queue[B.PREVIEW:]]
    h.bag = B.Bag(99)
    for cfg in (dict(), dict(search="full", lookahead=True, use_hold=True)):
        a = P.Agent(P.Linear(W), **cfg)
        assert a.choose(P.observe(g)).path == a.choose(P.observe(h)).path


def test_strong_holds_for_the_i_piece():
    b = board_from(["#########."] * 4)
    g = Game(seed=1, gravity=False)
    g.board = b
    g._spawn(B.S)
    g.hold_kind = B.I
    weak = P.Agent(P.Linear(W), search="full")
    strong = P.Agent(P.Linear(W), search="full", lookahead=True, use_hold=True)
    assert weak.choose(P.observe(g)).path[0] != "hold"
    d = strong.choose(P.observe(g))
    assert d.path[0] == "hold" and d.used_hold
    for key in d.path:
        g.press(key)
    assert g.lines == 4


def test_lookahead_uses_next_piece():
    # щель глубиной 2 под O: без взгляда вперёд Z закрывает её навесом, с ним - нет
    agent = P.Agent(P.Linear(W), lookahead=True)
    g = Game(seed=2, gravity=False)
    for _ in range(40):
        d = agent.choose(P.observe(g))
        assert d.lookahead_used
        for key in d.path:
            g.press(key)
        if g.over:
            break


def test_thoughts_top_three_sorted_best_first():
    g = Game(seed=6, gravity=False)
    d = P.Agent(P.Linear(W), search="full").choose(P.observe(g))
    assert 1 <= len(d.top) <= 3
    scores = [t.score for t in d.top]
    assert scores == sorted(scores, reverse=True)
    assert d.top[0].placement.key == d.placement.key and d.top[0].score == d.score


def test_never_locks_out_when_another_place_exists():
    rng = random.Random(3)
    b = [0] * HEIGHT
    for r in range(17):
        b[r] = B.FULL & ~(1 << rng.randrange(10)) & ~(0b1111 << 3 if r > 14 else 0)
    g = Game(seed=1, gravity=False)
    g.board = b
    g._spawn(B.O)
    if g.over:
        pytest.skip("место появления занято")
    d = P.Agent(P.Linear(W), search="full").choose(P.observe(g))
    assert not B.locks_out(B.O, d.placement.rot, d.placement.y)


def test_play_game_helper_counts_lines_and_caps():
    r = P.play_game(P.Agent(P.Linear(W)), seed=5, max_lines=30)
    assert r["lines"] >= 30 and r["capped"]
    r2 = P.play_game(P.Agent(P.Linear(W)), seed=5, max_lines=30)
    assert r == r2
