"""Куда можно поставить фигуру и какими нажатиями туда дойти.

ИИ играет кнопками, как человек: для каждого места известна последовательность клавиш
('L', 'R', 'cw', 'ccw', 'sd', 'hd'), и партия ведётся именно ими, без телепорта.

Два перебора:

- drop_placements - быстрый: повернуть у места появления, сдвинуть, сбросить. Им учится
  метод перекрёстной энтропии - там важна скорость.
- all_placements - полный поиск по состояниям фигуры (поворот, x, y): сдвиги, повороты со
  сдвигами SRS и мягкое падение по ряду. Находит места под навесами и крутки (T-spin).
  Над стопкой всё поле свободно, поэтому там фигура опускается сразу до верха стопки:
  состояния на разной высоте в пустом небе ничем не отличаются.
"""
from collections import deque, namedtuple

from game.core import blocks as B

Placement = namedtuple("Placement", "kind rot x y path key")

_ROT_PATHS = ((0, ()), (1, ("cw",)), (2, ("cw", "cw")), (3, ("ccw",)))
_MIN_DY = {k: tuple(min(cy for _, cy in B.CELLS[k][r]) for r in range(4)) for k in range(7)}


def cells_key(kind, rot, x, y):
    """Клетки фигуры на поле как ((ряд, маска), ...): одинаковые клетки - один ключ, даже
    если повороты разные (у I, S, Z, O)."""
    return tuple((y + dy, m) for dy, m in B.MASKS[kind][rot][x + 3])


def _landed(board, kind, rot, x, y):
    return y - B.drop_distance(board, kind, rot, x, y)


def drop_placements(board, kind, start=None):
    """Повернуть, сдвинуть, сбросить. Места без повторов, с нажатиями."""
    start = start or B.spawn_state(board, kind)
    if start is None:
        return []
    out = []
    seen = set()
    for _, rot_path in _ROT_PATHS:
        rot, x, y = start
        ok = True
        for key in rot_path:
            r = B.try_rotate(board, kind, rot, x, y, 1 if key == "cw" else -1)
            if r is None:
                ok = False
                break
            rot, x, y, _ = r
        if not ok:
            continue
        for step, key in ((0, None), (-1, "L"), (1, "R")):
            cx = x
            shifts = ()
            while True:
                if step:
                    if not B.fits(board, kind, rot, cx + step, y):
                        break
                    cx += step
                    shifts += (key,)
                fy = _landed(board, kind, rot, cx, y)
                k = cells_key(kind, rot, cx, fy)
                if k not in seen:
                    seen.add(k)
                    out.append(Placement(kind, rot, cx, fy, rot_path + shifts + ("hd",), k))
                if not step:
                    break
    return out


def all_placements(board, kind, start=None):
    """Все места, где фигура может зафиксироваться, и кратчайшие (по числу действий)
    нажатия до каждого. Поиск в ширину по состояниям (поворот, x, y)."""
    start = start or B.spawn_state(board, kind)
    if start is None:
        return []
    sky = B.stack_height(board)
    min_dy = _MIN_DY[kind]
    paths = {start: ()}
    todo = deque([start])
    out = []
    seen = set()
    fits = B.fits
    while todo:
        state = todo.popleft()
        rot, x, y = state
        path = paths[state]
        fy = _landed(board, kind, rot, x, y)
        k = cells_key(kind, rot, x, fy)
        if k not in seen:
            seen.add(k)
            out.append(Placement(kind, rot, x, fy, path + ("hd",), k))
        nxt = []
        if fits(board, kind, rot, x - 1, y):
            nxt.append(((rot, x - 1, y), ("L",)))
        if fits(board, kind, rot, x + 1, y):
            nxt.append(((rot, x + 1, y), ("R",)))
        for d, key in ((1, "cw"), (-1, "ccw")):
            r = B.try_rotate(board, kind, rot, x, y, d)
            if r is not None:
                nxt.append((r[:3], (key,)))
        if fy < y:
            bottom = y + min_dy[rot]
            # в небе над стопкой - сразу до её верха, ниже - по ряду
            down = bottom - sky if bottom > sky else 1
            nxt.append(((rot, x, y - down), ("sd",) * down))
        for s, keys in nxt:
            if s not in paths:
                paths[s] = path + keys
                todo.append(s)
    return out
