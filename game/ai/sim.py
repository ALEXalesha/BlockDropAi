"""Быстрая партия для обучения: фигура за фигурой, лучший сброс по весам признаков.

Правила те же, что в game.core.blocks (поле, мешок, появление, конец игры), но без
времени, hold и объекта Game: обучение играет сотни тысяч фигур. Места - быстрый перебор
сбросов (features.drop_spots); у каждого из них есть путь нажатиями (moves.drop_placements
даёт те же места), так что и тут ИИ не телепортирует фигуры.
"""
import random

from game.ai import features as F
from game.core import blocks as B

NEG = float("-inf")


def best_drop(board, kind, weights, top, heights):
    """(значение, поле после хода, линий, признаки) лучшего сброса или None."""
    best = None
    best_v = NEG
    for rot, x, y in F.drop_spots(board, kind, heights):
        if B.locks_out(kind, rot, y):
            continue
        vec, after, n = F.place(board, kind, rot, x, y, top)
        v = 0.0
        for w, f in zip(weights, vec):
            v += w * f
        if v > best_v:
            best_v = v
            best = (v, after, n, vec)
    return best


class Pieces:
    """Источник фигур: мешок из 7, как в игре, или равновероятные (труднее - для обучения)."""

    def __init__(self, seed, bag=True):
        self.bag = B.Bag(seed) if bag else None
        self.rng = random.Random(seed)

    def next(self):
        return self.bag.next() if self.bag else self.rng.randrange(7)


def play(weights, seed, max_lines=10 ** 9, max_pieces=10 ** 9, ceiling=None, bag=True):
    """Партия до конца или до предела. ceiling - высота укороченного поля для обучения:
    стопка выше - конец партии. Возвращает {'lines', 'pieces', 'over'}."""
    pieces = Pieces(seed, bag)
    board = [0] * B.HEIGHT
    lines = count = 0
    top = 0
    heights = [0] * B.WIDTH
    over = False
    while lines < max_lines and count < max_pieces:
        kind = pieces.next()
        if B.spawn_state(board, kind) is None:
            over = True
            break
        r = best_drop(board, kind, weights, top, heights)
        if r is None:
            over = True
            break
        _, board, n, vec = r
        lines += n
        count += 1
        top = vec[9]
        heights = F.column_heights(board) if top else [0] * B.WIDTH
        if ceiling is not None and top > ceiling:
            over = True
            break
    return {"lines": lines, "pieces": count, "over": over}
