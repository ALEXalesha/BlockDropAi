"""Признаки поля: быстрый расчёт на битах сверяется с медленным по клеткам."""
import random

from hypothesis import given
from hypothesis import strategies as st

from game.ai import features as F
from game.ai import moves as M
from game.core import blocks as B
from game.core.blocks import HEIGHT, WIDTH


def cell(board, x, y):
    if x < 0 or x >= WIDTH or y < 0:
        return True
    if y >= HEIGHT:
        return False
    return bool(board[y] >> x & 1)


def reference(board):
    """Признаки поля по клеткам, без хитростей."""
    heights = []
    for x in range(WIDTH):
        h = 0
        for y in range(HEIGHT):
            if cell(board, x, y):
                h = y + 1
        heights.append(h)
    top = max(heights)
    row_trans = sum(cell(board, x, y) != cell(board, x + 1, y)
                    for y in range(top) for x in range(-1, WIDTH))
    col_trans = sum(cell(board, x, y) != cell(board, x, y - 1)
                    for x in range(WIDTH) for y in range(top + 1))
    holes = sum(1 for x in range(WIDTH) for y in range(heights[x]) if not cell(board, x, y))
    hole_rows = sum(1 for y in range(top)
                    if any(not cell(board, x, y) and y < heights[x] for x in range(WIDTH)))
    wells = 0
    for x in range(WIDTH):
        depth = 0
        for y in range(top - 1, -1, -1):
            open_cell = not cell(board, x, y) and y >= heights[x]
            if open_cell and cell(board, x - 1, y) and cell(board, x + 1, y):
                depth += 1
                wells += depth
            else:
                depth = 0
    bump = sum(abs(heights[i] - heights[i + 1]) for i in range(WIDTH - 1))
    return {"row_transitions": row_trans, "col_transitions": col_trans, "holes": holes,
            "hole_rows": hole_rows, "wells": wells, "bumpiness": bump, "height": sum(heights),
            "max_height": top}


def board_from(lines):
    b = [0] * HEIGHT
    for r, line in enumerate(lines):
        b[r] = sum(1 << x for x, ch in enumerate(line) if ch == "#")
    return b


def as_dict(vec):
    return dict(zip(F.NAMES, vec))


def test_names_cover_spec():
    for name in ("landing", "eroded", "row_transitions", "col_transitions", "holes", "wells",
                 "hole_rows", "bumpiness", "height", "lines"):
        assert name in F.NAMES


def test_hand_checked_board():
    #   ряд 2: #.........
    #   ряд 1: #.#.......
    #   ряд 0: ###.######
    b = board_from(["###.######", "#.#.......", "#........."])
    f = as_dict(F.board_features(b))
    assert f["row_transitions"] == 2 + 4 + 2
    assert f["col_transitions"] == 1 + 1 + 1 + 1 + 1 * 6
    assert f["holes"] == 0 and f["hole_rows"] == 0
    assert f["height"] == 3 + 1 + 2 + 0 + 1 * 6
    assert f["max_height"] == 3
    assert f["bumpiness"] == 2 + 1 + 2 + 1
    # колодцы глубины 1: (1,1) между (0,1) и (2,1), (3,0) между (2,0) и (4,0)
    assert f["wells"] == 2


@given(st.integers(0, 10 ** 9))
def test_fast_features_equal_reference(seed):
    rng = random.Random(seed)
    b = [0] * HEIGHT
    for r in range(rng.randrange(0, 18)):
        b[r] = rng.getrandbits(10) & rng.getrandbits(10) | rng.getrandbits(10) & rng.getrandbits(10)
        if b[r] == B.FULL:
            b[r] &= ~(1 << rng.randrange(10))
    got = as_dict(F.board_features(b))
    want = reference(b)
    for k, v in want.items():
        assert got[k] == v, (k, got[k], v)


@given(st.integers(0, 10 ** 9), st.sampled_from(range(7)))
def test_placement_features_landing_eroded_lines(seed, kind):
    rng = random.Random(seed)
    b = [0] * HEIGHT
    for r in range(rng.randrange(0, 8)):
        b[r] = B.FULL & ~(1 << rng.randrange(10)) if rng.random() < 0.6 else rng.getrandbits(10)
        if b[r] == B.FULL:                 # полных рядов в игре не бывает
            b[r] ^= 1 << rng.randrange(10)
    if rng.random() < 0.3:                 # башня выше места фигуры
        for r in range(rng.randrange(1, 12)):
            b[r] |= 1 << rng.randrange(10) if r == 0 else b[r - 1] & -b[r - 1] or 1
            if b[r] == B.FULL:
                b[r] ^= 2
    for p in M.drop_placements(b, kind):
        vec, after, n = F.place(b, kind, p.rot, p.x, p.y)
        ref_after, rows = B.lock(b, kind, p.rot, p.x, p.y)
        assert after == ref_after and n == len(rows)
        f = as_dict(vec)
        ys = [cy for _, cy in B.piece_cells(kind, p.rot, p.x, p.y)]
        assert f["landing"] == (min(ys) + max(ys)) / 2
        assert f["lines"] == n
        assert f["eroded"] == n * sum(1 for y in ys if y in rows)
        board_part = as_dict(F.board_features(after))
        for k, v in board_part.items():
            if k not in ("landing", "eroded", "lines"):
                assert f[k] == v


def test_fast_drops_equal_search_drops_on_low_stacks():
    rng = random.Random(5)
    for _ in range(300):
        b = [0] * HEIGHT
        for r in range(rng.randrange(0, 12)):
            b[r] = rng.getrandbits(10) | rng.getrandbits(10)
            if b[r] == B.FULL:
                b[r] ^= 1 << rng.randrange(10)
        for kind in range(7):
            want = {(p.rot, p.x, p.y) for p in M.drop_placements(b, kind)}
            got = set(F.drop_spots(b, kind))
            assert got == want


def test_place_next_to_tall_column_sees_whole_stack():
    # фигура легла низко, рядом башня выше неё: признаки считаются по всей стопке
    b = [0] * HEIGHT
    for r in range(6):
        b[r] = 1
    for p in M.drop_placements(b, B.O):
        vec, after, _ = F.place(b, B.O, p.rot, p.x, p.y)
        f = as_dict(vec)
        ref = reference(after)
        for k, v in ref.items():
            assert f[k] == v, (p.x, k, f[k], v)
