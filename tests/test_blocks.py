"""Правила: SRS по стандартным таблицам, мешок из 7, линии 1-4, очки, hold, задержка
фиксации, время от часов, мусор, конец игры."""
import random

import pytest
from hypothesis import given
from hypothesis import strategies as st

from game.core import blocks as B
from game.core.blocks import FULL, HEIGHT, I, J, L, O, S, T, Z, Game

# Стандартные таблицы сдвигов SRS (гайдлайн падающих блоков), ось y вверх. Переписаны из
# описания системы, а не из кода: код считает их из таблиц смещений.
SRS_JLSTZ = {
    (0, 1): ((0, 0), (-1, 0), (-1, 1), (0, -2), (-1, -2)),
    (1, 0): ((0, 0), (1, 0), (1, -1), (0, 2), (1, 2)),
    (1, 2): ((0, 0), (1, 0), (1, -1), (0, 2), (1, 2)),
    (2, 1): ((0, 0), (-1, 0), (-1, 1), (0, -2), (-1, -2)),
    (2, 3): ((0, 0), (1, 0), (1, 1), (0, -2), (1, -2)),
    (3, 2): ((0, 0), (-1, 0), (-1, -1), (0, 2), (-1, 2)),
    (3, 0): ((0, 0), (-1, 0), (-1, -1), (0, 2), (-1, 2)),
    (0, 3): ((0, 0), (1, 0), (1, 1), (0, -2), (1, -2)),
}
SRS_I = {
    (0, 1): ((0, 0), (-2, 0), (1, 0), (-2, -1), (1, 2)),
    (1, 0): ((0, 0), (2, 0), (-1, 0), (2, 1), (-1, -2)),
    (1, 2): ((0, 0), (-1, 0), (2, 0), (-1, 2), (2, -1)),
    (2, 1): ((0, 0), (1, 0), (-2, 0), (1, -2), (-2, 1)),
    (2, 3): ((0, 0), (2, 0), (-1, 0), (2, 1), (-1, -2)),
    (3, 2): ((0, 0), (-2, 0), (1, 0), (-2, -1), (1, 2)),
    (3, 0): ((0, 0), (1, 0), (-2, 0), (1, -2), (-2, 1)),
    (0, 3): ((0, 0), (-1, 0), (2, 0), (-1, 2), (2, -1)),
}

# Повороты по картинкам SRS: строки сверху вниз, рамка 3x3 или 4x4.
PICTURES = {
    T: ([".#.", "###", "..."], [".#.", ".##", ".#."], ["...", "###", ".#."], [".#.", "##.", ".#."]),
    I: (["....", "####", "....", "...."], ["..#.", "..#.", "..#.", "..#."],
        ["....", "....", "####", "...."], [".#..", ".#..", ".#..", ".#.."]),
    S: ([".##", "##.", "..."], [".#.", ".##", "..#"], ["...", ".##", "##."], ["#..", "##.", ".#."]),
    Z: (["##.", ".##", "..."], ["..#", ".##", ".#."], ["...", "##.", ".##"], [".#.", "##.", "#.."]),
    J: (["#..", "###", "..."], [".##", ".#.", ".#."], ["...", "###", "..#"], [".#.", ".#.", "##."]),
    L: (["..#", "###", "..."], [".#.", ".#.", ".##"], ["...", "###", "#.."], ["##.", ".#.", ".#."]),
    O: (["....", ".##.", ".##.", "...."],) * 4,
}


def cells_from_picture(rows):
    n = len(rows)
    return tuple(sorted((x, n - 1 - r) for r, line in enumerate(rows) for x, ch in enumerate(line) if ch == "#"))


def empty():
    return [0] * HEIGHT


def board_from(lines):
    """Ряды снизу вверх строками '#.'."""
    b = empty()
    for r, line in enumerate(lines):
        b[r] = sum(1 << x for x, ch in enumerate(line) if ch == "#")
    return b


# --- SRS ---


def test_kick_tables_match_standard_srs():
    for kind in (J, L, S, T, Z):
        assert B.KICKS[kind] == SRS_JLSTZ, B.KINDS[kind]
    assert B.KICKS[I] == SRS_I
    assert all(k == ((0, 0),) for k in B.KICKS[O].values())


def test_rotation_states_match_srs_pictures():
    for kind, pics in PICTURES.items():
        for rot in range(4):
            assert B.CELLS[kind][rot] == cells_from_picture(pics[rot]), (B.KINDS[kind], rot)


def test_i_kicks_off_left_wall():
    # I стоит вертикально (L) у левой стены; поворот в 0 не влезает без сдвига, тест 2 (+1, 0)
    b = empty()
    assert B.fits(b, I, 3, -1, 5)
    assert not B.fits(b, I, 0, -1, 5)
    assert B.try_rotate(b, I, 3, -1, 5, +1) == (0, 0, 5, 1)


def test_t_spin_triple_uses_fifth_kick():
    # Классическая щель под T-spin triple: T сверху, поворот против часовой проходит
    # только пятым сдвигом (+1, -2) и чистит три ряда.
    b = board_from(["#####.####", "####..####", "#####.####", "..........", ".....#...."])
    assert B.fits(b, T, 0, 3, 2)
    r = B.try_rotate(b, T, 0, 3, 2, -1)
    assert r == (3, 4, 0, 4)
    after, rows = B.lock(b, T, 3, 4, 0)
    assert rows == [0, 1, 2]
    assert after[0] == 0 and after[1] == 1 << 5 and not any(after[2:])


@given(st.integers(0, 2 ** 31), st.sampled_from(range(7)), st.integers(0, 3), st.sampled_from((1, -1)))
def test_rotation_takes_first_fitting_kick(seed, kind, rot, d):
    rng = random.Random(seed)
    b = empty()
    for r in range(12):
        b[r] = rng.getrandbits(10) & rng.getrandbits(10)
    x, y = rng.randrange(-2, 9), rng.randrange(0, 14)
    if not B.fits(b, kind, rot, x, y):
        return
    to = (rot + d) % 4
    table = (SRS_I if kind == I else SRS_JLSTZ) if kind != O else {(rot, to): ((0, 0),)}
    want = None
    for i, (dx, dy) in enumerate(table[(rot, to)]):
        cells = cells_from_picture(PICTURES[kind][to])
        ok = all(0 <= x + dx + cx < 10 and 0 <= y + dy + cy < HEIGHT
                 and not b[y + dy + cy] >> (x + dx + cx) & 1 for cx, cy in cells)
        if ok:
            want = (to, x + dx, y + dy, i)
            break
    assert B.try_rotate(b, kind, rot, x, y, d) == want


# --- мешок ---


def test_bag_every_seven_are_all_different():
    for seed in range(30):
        bag = B.Bag(seed)
        seq = [bag.next() for _ in range(70)]
        for k in range(0, 70, 7):
            assert sorted(seq[k:k + 7]) == list(range(7))


def seq(seed, n=21):
    bag = B.Bag(seed)
    return [bag.next() for _ in range(n)]


def test_bag_is_seeded_and_random():
    assert seq(1) == seq(1) and seq(1) != seq(2)
    firsts = {tuple(seq(s, 7)) for s in range(50)}
    assert len(firsts) > 30


def test_game_queue_follows_bag():
    g = Game(seed=5)
    seen = [g.kind] + g.queue[:6]
    assert sorted(seen) == list(range(7))


# --- линии и очки ---


def game_with(board, kind, level=1):
    g = Game(seed=0, level=level, gravity=False)
    g.board = list(board)
    g._spawn(kind)
    return g


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_clearing_one_to_four_lines(n):
    rows = ["#########."] * n + ["#.........", "##........"]
    g = game_with(board_from(rows), I, level=2)
    g.rotate(1)                       # вертикально, столбец x+2
    while g.move(1):
        pass
    assert g.x + 2 == 9
    score0 = g.score
    drop = g.y - g.ghost_y()
    g.hard_drop()
    assert g.lines == n and g.cleared[n] == 1
    assert g.score - score0 == {1: 100, 2: 300, 3: 500, 4: 800}[n] * 2 + 2 * drop
    left = g.board
    # ряды выше очищенных опустились: на месте ряда 0 теперь бывший ряд n (плюс остаток I)
    assert left[0] & 0x1FF == 0b1
    assert left[1] & 0x1FF == 0b11
    assert ("clear", tuple(range(n))) in g.events


def test_level_grows_every_ten_lines():
    g = Game(seed=0, level=1, gravity=False)
    g.lines = 9
    g.board = board_from(["#########."])
    g._spawn(I)
    g.rotate(1)
    while g.move(1):
        pass
    g.hard_drop()
    assert g.lines == 10 and g.level == 2
    assert B.gravity_interval(2) < B.gravity_interval(1)


def test_soft_drop_scores_one_hard_drop_two_per_cell():
    g = game_with(empty(), T)
    s = g.score
    assert g.soft_drop()
    assert g.score == s + 1
    d = g.y - g.ghost_y()
    g.hard_drop()
    assert g.score == s + 1 + 2 * d


# --- hold ---


def test_hold_once_per_piece_and_swaps():
    g = Game(seed=3, gravity=False)
    first, nxt = g.kind, g.queue[0]
    assert g.hold()
    assert g.hold_kind == first and g.kind == nxt
    assert not g.hold()                   # второй раз за фигуру нельзя
    g.hard_drop()
    cur = g.kind
    assert g.hold()                        # после фиксации снова можно
    assert g.kind == first and g.hold_kind == cur
    assert (g.rot, g.x) == (0, B.SPAWN_X)


# --- задержка фиксации и время ---


def test_lock_delay_half_second():
    g = game_with(empty(), T)
    g.y = g.ghost_y()
    g.update(0.49)
    assert g.pieces == 0
    g.update(0.02)
    assert g.pieces == 1


def test_moving_on_ground_resets_lock_but_not_forever():
    g = game_with(empty(), T)
    g.y = g.ghost_y()
    g.lowest = g.y
    for i in range(B.MAX_RESETS):
        g.update(0.4)
        assert g.move(1 if i % 2 == 0 else -1)
        assert g.pieces == 0
    g.update(0.4)
    g.move(1)                                  # шестнадцатое движение - фиксация сразу
    assert g.pieces == 1


def test_gravity_one_row_per_second_on_level_one():
    g = Game(seed=1)
    y = g.y
    g.update(0.999)
    assert g.y == y
    g.update(0.002)
    assert g.y == y - 1


def test_same_time_same_game_whatever_the_frame_rate():
    a = Game(seed=9, level=5)
    b = Game(seed=9, level=5)
    for _ in range(64 * 30):
        a.update(1 / 64)
    for _ in range(30):
        b.update(1.0)
    assert a.board == b.board and a.pieces == b.pieces and a.piece() == b.piece()
    assert a.pieces > 3


def test_time_split_does_not_matter_between_inputs():
    a = Game(seed=2, level=3)
    b = Game(seed=2, level=3)
    for step in range(40):
        key = ("L", "cw", "R", "ccw", "sd")[step % 5]
        a.press(key)
        b.press(key)
        a.update(0.75)
        for _ in range(12):
            b.update(0.0625)
        assert a.piece() == b.piece() and a.board == b.board


# --- мусор и конец игры ---


def test_garbage_waits_for_lock_and_is_cancelled_by_lines():
    g = game_with(board_from(["#########."]), I)
    g.receive_garbage(2)
    g.receive_garbage(1)
    assert g.pending() == 3
    g.rotate(1)
    while g.move(1):
        pass
    g.hard_drop()                  # одна линия - отправляет 0, мусор не гасит
    assert g.pending() == 3
    g.hard_drop()                  # без линий - мусор встаёт снизу
    assert g.pending() == 0
    holes = [FULL & ~g.board[r] for r in range(3)]
    assert all(h and h & (h - 1) == 0 for h in holes)     # одна дырка в каждом ряду


def test_four_lines_send_four_and_cancel_pending():
    g = game_with(board_from(["#########."] * 4), I)
    g.receive_garbage(3)
    g.rotate(1)
    while g.move(1):
        pass
    g.hard_drop()
    assert g.garbage_sent == 4 and g.pending() == 0


def test_block_out_ends_game():
    b = empty()
    for r in range(B.VISIBLE - 2, B.VISIBLE + 3):
        b[r] = 0b0001111000
    g = game_with(b, T)
    assert g.over and ("over",) in g.events


def test_game_over_when_stack_reaches_spawn():
    g = Game(seed=11, gravity=False)
    n = 0
    while not g.over:
        g.hard_drop()
        n += 1
        assert n < 200
    assert 10 < n < 200


def test_lock_out_above_visible_field():
    assert B.locks_out(O, 0, B.VISIBLE - 1)
    assert not B.locks_out(O, 0, B.VISIBLE - 2)


# --- случайные партии: законы ---


@given(st.integers(0, 10 ** 6))
def test_random_play_keeps_invariants(seed):
    rng = random.Random(seed)
    g = Game(seed=seed, gravity=True, level=rng.randrange(1, 15))
    keys = ["L", "R", "cw", "ccw", "sd", "hd", "hold"]
    for _ in range(400):
        if g.over:
            break
        if rng.random() < 0.02:
            n = rng.randrange(1, 3)
            g.receive_garbage(n)
        g.press(rng.choice(keys))
        g.update(rng.random() * 0.3)
        if not g.over:
            assert B.fits(g.board, *g.piece())
        assert all(row != FULL for row in g.board)
        assert all(0 <= row <= FULL for row in g.board)
    cells = sum(bin(r).count("1") for r in g.board)
    assert cells == 4 * g.pieces - 10 * g.lines + 9 * g.garbage_rows
    assert g.lines == sum(k * c for k, c in enumerate(g.cleared))
    assert g.pieces == sum(g.cleared)
