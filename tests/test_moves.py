"""Перебор мест: все достижимые места через поиск по состояниям фигуры, нажатия до
каждого места. Закон: нажатия, сыгранные в настоящей партии, ставят фигуру ровно туда,
куда обещал поиск."""
import random
from collections import deque

from hypothesis import given
from hypothesis import strategies as st

from game.ai import moves as M
from game.core import blocks as B
from game.core.blocks import HEIGHT, T, Game


def random_board(rng, rows=None):
    rows = rows if rows is not None else rng.randrange(0, 14)
    b = [0] * HEIGHT
    for r in range(rows):
        b[r] = rng.getrandbits(10) | rng.getrandbits(10)
        if b[r] == B.FULL:
            b[r] &= ~(1 << rng.randrange(10))
    # навесы: иногда пустые клетки под заполненными
    for r in range(rows - 1):
        if rng.random() < 0.3:
            b[r] &= rng.getrandbits(10)
    return b


def game_at(board, kind):
    g = Game(seed=0, gravity=False)
    g.board = list(board)
    g._spawn(kind)
    return g


def play_path(board, kind, path):
    g = game_at(board, kind)
    before = g.pieces
    for key in path[:-1]:
        assert g.press(key), (key, path)
    final = g.piece()
    assert path[-1] == "hd"
    d = B.drop_distance(g.board, *final)
    landed = (final[0], final[1], final[2], final[3] - d)
    g.press("hd")
    assert g.pieces == before + 1
    return landed, g


def brute_force_finals(board, kind):
    """Независимый перебор: обход состояний настоящей партии по одной клавише, мягкое
    падение - по ряду. Итог - все места, где фигура может зафиксироваться."""
    start = B.spawn_state(board, kind)
    seen = {start}
    todo = deque([start])
    finals = set()
    while todo:
        rot, x, y = todo.popleft()
        if not B.fits(board, kind, rot, x, y - 1):
            finals.add((rot, x, y))
        nxt = []
        for dx in (-1, 1):
            if B.fits(board, kind, rot, x + dx, y):
                nxt.append((rot, x + dx, y))
        for d in (1, -1):
            r = B.try_rotate(board, kind, rot, x, y, d)
            if r:
                nxt.append(r[:3])
        if B.fits(board, kind, rot, x, y - 1):
            nxt.append((rot, x, y - 1))
        for s in nxt:
            if s not in seen:
                seen.add(s)
                todo.append(s)
    return {M.cells_key(kind, *f) for f in finals}


@given(st.integers(0, 10 ** 9), st.sampled_from(range(7)))
def test_path_lands_where_search_promised(seed, kind):
    rng = random.Random(seed)
    board = random_board(rng)
    if B.spawn_state(board, kind) is None:
        return
    for p in M.all_placements(board, kind):
        landed, g = play_path(board, kind, p.path)
        assert landed == (kind, p.rot, p.x, p.y)
        after, rows = B.lock(board, kind, p.rot, p.x, p.y)
        assert g.board == after or g.over


@given(st.integers(0, 10 ** 9), st.sampled_from(range(7)))
def test_search_finds_every_reachable_place(seed, kind):
    rng = random.Random(seed)
    board = random_board(rng)
    if B.spawn_state(board, kind) is None:
        return
    found = {p.key for p in M.all_placements(board, kind)}
    assert found == brute_force_finals(board, kind)


@given(st.integers(0, 10 ** 9), st.sampled_from(range(7)))
def test_drop_placements_are_reachable_and_paths_work(seed, kind):
    rng = random.Random(seed)
    board = random_board(rng)
    if B.spawn_state(board, kind) is None:
        return
    drops = M.drop_placements(board, kind)
    keys = [p.key for p in drops]
    assert len(keys) == len(set(keys))
    assert set(keys) <= {p.key for p in M.all_placements(board, kind)}
    for p in drops:
        landed, _ = play_path(board, kind, p.path)
        assert landed == (kind, p.rot, p.x, p.y)


def test_empty_board_counts():
    b = [0] * HEIGHT
    count = {k: len(M.drop_placements(b, k)) for k in range(7)}
    # повороты, которые дают разные клетки: I и S/Z - 2, O - 1, J L T - 4
    assert count == {B.I: 17, B.J: 34, B.L: 34, B.O: 9, B.S: 17, B.T: 34, B.Z: 17}
    assert {k: len(M.all_placements(b, k)) for k in range(7)} == count


def test_spin_under_overhang_found_only_by_search():
    # щель под T-spin triple: сбросом сверху туда не попасть, поиском по состояниям - да
    rows = ["#####.####", "####..####", "#####.####", "..........", ".....#...."]
    b = [0] * HEIGHT
    for r, line in enumerate(rows):
        b[r] = sum(1 << x for x, ch in enumerate(line) if ch == "#")
    want = M.cells_key(T, 3, 4, 0)
    assert want not in {p.key for p in M.drop_placements(b, T)}
    spin = [p for p in M.all_placements(b, T) if p.key == want]
    assert len(spin) == 1
    path = spin[0].path
    assert path[-2] in ("cw", "ccw") and "sd" in path
    landed, g = play_path(b, T, path)
    assert g.lines == 3


def test_search_from_moved_piece():
    b = [0] * HEIGHT
    g = game_at(b, B.L)
    g.press("cw")
    g.press("R")
    ps = M.all_placements(g.board, g.kind, start=(g.rot, g.x, g.y))
    assert len(ps) == 34
    for p in ps:
        h = game_at(b, B.L)
        h.press("cw")
        h.press("R")
        for key in p.path[:-1]:
            assert h.press(key)
        d = B.drop_distance(h.board, *h.piece())
        assert (h.rot, h.x, h.y - d) == (p.rot, p.x, p.y)


def test_slide_into_side_tunnel_halfway_down_a_shaft():
    # шахта шириной 2 до пола, сбоку на середине - туннель: войти можно, только
    # остановив падение на его высоте
    rows = ["..########", "..########", "......####", "......####", "..########", "..########"]
    b = [0] * HEIGHT
    for r, line in enumerate(rows):
        b[r] = sum(1 << x for x, ch in enumerate(line) if ch == "#")
    tunnel = ((2, 0b110000), (3, 0b110000))
    assert tunnel not in {p.key for p in M.drop_placements(b, B.O)}
    found = [p for p in M.all_placements(b, B.O) if p.key == tunnel]
    assert len(found) == 1
    landed, g = play_path(b, B.O, found[0].path)
    assert landed[2:] == (found[0].x, found[0].y)


@given(st.integers(0, 10 ** 9), st.sampled_from(range(7)))
def test_without_overhangs_full_search_equals_drops(seed, kind):
    # нет пустых клеток под занятыми - нет и мест под навесом: полный поиск даёт ровно
    # те же места, что сброс (на этом стоит быстрый путь игрока)
    rng = random.Random(seed)
    heights = [rng.randrange(0, 15) for _ in range(10)]
    b = [0] * HEIGHT
    for x, h in enumerate(heights):
        for r in range(h):
            b[r] |= 1 << x
    b = [row for row in b if row != B.FULL] + [B.FULL] * 0
    b += [0] * (HEIGHT - len(b))
    assert not M.has_overhang(b)
    if B.spawn_state(b, kind) is None:
        return
    assert {p.key for p in M.drop_placements(b, kind)} == {p.key for p in M.all_placements(b, kind)}


def test_has_overhang():
    b = [0] * HEIGHT
    b[0], b[1], b[2] = 0b111, 0b011, 0b001          # лесенка
    assert not M.has_overhang(b)
    b[1], b[2] = 0b001, 0b011                       # (1,1) пусто под (1,2)
    assert M.has_overhang(b)


@given(st.integers(0, 10 ** 9), st.sampled_from(range(7)))
def test_fast_drops_equal_drop_placements_and_paths_work(seed, kind):
    rng = random.Random(seed)
    board = random_board(rng)
    if B.spawn_state(board, kind) is None:
        return
    fast = M.fast_drops(board, kind)
    assert {(p.rot, p.x, p.y) for p in fast} == {(p.rot, p.x, p.y) for p in M.drop_placements(board, kind)}
    for p in fast:
        landed, _ = play_path(board, kind, p.path)
        assert landed == (kind, p.rot, p.x, p.y)
