"""Признаки поля для оценки «после хода» (spec §3) и быстрый перебор сбросов.

Признаки (как у Дельяши и в работах по методу перекрёстной энтропии):

- landing - высота, на которую легла фигура (середина её клеток);
- eroded - линии x клетки фигуры в этих линиях;
- row_transitions, col_transitions - переходы «занято/пусто» по рядам и столбцам
  (стены и пол считаются занятыми);
- holes - пустые клетки под занятыми, hole_rows - рядов с дырами;
- wells - колодцы: открытая клетка с занятыми соседями слева и справа, глубина
  считается сверху, колодец глубины d даёт 1 + 2 + ... + d;
- bumpiness - неровность, сумма разниц высот соседних столбцов;
- height - сумма высот столбцов, max_height - высота стопки;
- lines - очищенные линии.

Всё считается на битах ряда: ряд - целое число, проход идёт только по занятым рядам.
"""
from game.core import blocks as B

NAMES = ("landing", "eroded", "row_transitions", "col_transitions", "holes", "wells",
         "hole_rows", "bumpiness", "height", "max_height", "lines")
N = len(NAMES)

FULL = B.FULL
_RIGHT_WALL = 1 << (B.WIDTH - 1)


def _row_transitions(row):
    p = (row << 1) | 1 | (1 << (B.WIDTH + 1))
    return ((p ^ (p >> 1)) & ((1 << (B.WIDTH + 1)) - 1)).bit_count()


ROW_TRANS = tuple(_row_transitions(r) for r in range(1 << B.WIDTH))


def _top(board, start=B.HEIGHT):
    for r in range(start - 1, -1, -1):
        if board[r]:
            return r + 1
    return 0


def board_part(board, top=None):
    """Признаки самого поля: (row_trans, col_trans, holes, wells, hole_rows, bump,
    height, max_height, высоты столбцов)."""
    if top is None:
        top = _top(board)
    rt = 0
    ct = 0
    prev = FULL
    for r in range(top):
        row = board[r]
        rt += ROW_TRANS[row]
        ct += (prev ^ row).bit_count()
        prev = row
    ct += prev.bit_count()              # над стопкой пусто
    covered = 0
    holes = hole_rows = wells = 0
    c0 = c1 = c2 = c3 = c4 = 0          # счётчики глубины колодцев по столбцам, по битам
    heights = [0] * B.WIDTH
    for r in range(top - 1, -1, -1):
        row = board[r]
        h = covered & ~row
        if h:
            holes += h.bit_count()
            hole_rows += 1
        w = ~row & ((row << 1) | 1) & ((row >> 1) | _RIGHT_WALL) & FULL & ~covered
        if w or c0 | c1 | c2 | c3 | c4:
            c0 &= w
            c1 &= w
            c2 &= w
            c3 &= w
            c4 &= w
            carry = w
            c0, carry = c0 ^ carry, c0 & carry
            c1, carry = c1 ^ carry, c1 & carry
            c2, carry = c2 ^ carry, c2 & carry
            c3, carry = c3 ^ carry, c3 & carry
            c4 = c4 ^ carry
            wells += (c0.bit_count() + 2 * c1.bit_count() + 4 * c2.bit_count()
                      + 8 * c3.bit_count() + 16 * c4.bit_count())
        new = row & ~covered
        while new:
            low = new & -new
            heights[low.bit_length() - 1] = r + 1
            new ^= low
        covered |= row
    bump = 0
    for i in range(B.WIDTH - 1):
        d = heights[i] - heights[i + 1]
        bump += d if d > 0 else -d
    return rt, ct, holes, wells, hole_rows, bump, sum(heights), top, heights


def board_features(board):
    """Признаки поля без хода: landing, eroded и lines - нули."""
    rt, ct, holes, wells, hole_rows, bump, height, top, _ = board_part(board)
    return [0.0, 0, rt, ct, holes, wells, hole_rows, bump, height, top, 0]


def place(board, kind, rot, x, y, top=None):
    """Поставить фигуру: (признаки, поле после хода, линий). top - высота стопки до хода,
    если известна (иначе считается)."""
    masks = B.MASKS[kind][rot][x + 3]
    lo = y + masks[0][0]
    hi = y + masks[-1][0]
    after, rows = B.lock(board, kind, rot, x, y)
    n = len(rows)
    eroded = 0
    if n:
        for dy, m in masks:
            if y + dy in rows:
                eroded += m.bit_count()
        eroded *= n
    if top is None:
        top = _top(board)
    # верх стопки - выше фигуры или выше прежнего верха; линии могли его опустить
    top = _top(after, min(max(hi + 1, top), B.HEIGHT))
    rt, ct, holes, wells, hole_rows, bump, height, top, _ = board_part(after, top)
    return [(lo + hi) / 2, eroded, rt, ct, holes, wells, hole_rows, bump, height, top, n], after, n


def column_heights(board):
    return board_part(board)[8]


# Повороты с разными клетками - в том же порядке, в каком их оставляет drop_placements.
_UNIQUE_ROTS = {B.I: (0, 1), B.O: (0,), B.S: (0, 1), B.Z: (0, 1), B.J: (0, 1, 2, 3),
                B.L: (0, 1, 2, 3), B.T: (0, 1, 2, 3)}


def _profiles():
    """Для поворота: [(x, ((столбец, нижняя клетка), ...))] по всем допустимым x."""
    out = {}
    for kind in range(7):
        for rot in range(4):
            low = {}
            for cx, cy in B.CELLS[kind][rot]:
                low[cx] = min(low.get(cx, 99), cy)
            xs = [x for x in range(-3, B.WIDTH) if B.MASKS[kind][rot][x + 3] is not None]
            out[kind, rot] = [(x, tuple((x + c, l) for c, l in sorted(low.items()))) for x in xs]
    return out


_PROFILES = _profiles()
FAST_TOP = 16       # ниже этой высоты стопки поворот и сдвиг у места появления всегда свободны


def drop_spots(board, kind, heights=None):
    """Места быстрого перебора (поворот у места появления, сдвиг, сброс) как (rot, x, y).
    На невысокой стопке сброс сверху ложится на верх столбцов - хватает высот; на высокой
    - честный drop_placements."""
    if heights is None:
        part = board_part(board)
        top, heights = part[7], part[8]
    else:
        top = max(heights)
    if top > FAST_TOP:
        from game.ai.moves import drop_placements
        return [(p.rot, p.x, p.y) for p in drop_placements(board, kind)]
    out = []
    for rot in _UNIQUE_ROTS[kind]:
        for x, cols in _PROFILES[kind, rot]:
            y = -99
            for col, low in cols:
                v = heights[col] - low
                if v > y:
                    y = v
            out.append((rot, x, y))
    return out
