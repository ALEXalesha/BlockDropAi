"""Игрок-ИИ: выбор места и нажатия до него.

ИИ видит то же, что игрок (View): поле, текущую фигуру и где она сейчас, очередь из
PREVIEW фигур, hold и можно ли им пользоваться. Мешок и дальнее будущее ему не видны.

Оценка «после хода» (spec §3): каждое место ставится на копию поля, поле оценивается -
весами признаков (Linear, метод перекрёстной энтропии) или сетью (Net, TD). Лучшее
место выбирается, и до него ищутся нажатия; партия идёт ими.

- search='drop' - повернуть, сдвинуть, сбросить; 'full' - полный поиск со крутками;
- lookahead - взгляд на следующую фигуру из очереди (два хода, лучшие prune мест);
- use_hold - вариант с hold: другая фигура из hold или из очереди.
"""
from collections import namedtuple

from game.ai import features as F
from game.ai import moves as M
from game.core import blocks as B

View = namedtuple("View", "board kind start preview hold hold_used")
Choice = namedtuple("Choice", "score placement used_hold")
Decision = namedtuple("Decision", "path placement score top used_hold lookahead_used")

DEAD = -1e9


def observe(game):
    """То, что видит игрок."""
    return View(tuple(game.board), game.kind, (game.rot, game.x, game.y), tuple(game.queue[:B.PREVIEW]),
                game.hold_kind, game.hold_used)


class Linear:
    """Веса признаков: значение = сумма вес x признак."""

    def __init__(self, weights):
        self.w = [float(v) for v in weights]

    def scores(self, vecs, heights):
        w = self.w
        out = []
        for vec in vecs:
            v = 0.0
            for a, f in zip(w, vec):
                v += a * f
            out.append(v)
        return out

    def carry(self, vec):
        """Что первый ход приносит сам по себе (при взгляде на два хода): линии."""
        return self.w[1] * vec[1] + self.w[10] * vec[10]


class Net:
    """Сеть оценки: значение = награда за ход + V(после хода) (game.ai.net.reward)."""

    def __init__(self, net):
        self.net = net

    def scores(self, vecs, heights):
        from game.ai.net import encode, reward
        v = self.net.predict(encode(vecs, heights))
        return [float(a) + reward(vec[10]) for a, vec in zip(v, vecs)]

    def carry(self, vec):
        from game.ai.net import reward
        return reward(vec[10])


class Agent:
    def __init__(self, evaluator, search="drop", lookahead=False, use_hold=False, prune=5):
        self.evaluator = evaluator
        self.search = search
        self.lookahead = lookahead
        self.use_hold = use_hold
        self.prune = prune

    def _places(self, board, kind, start):
        # без навесов полный поиск даёт те же места, что сброс, - а сброс в разы быстрее;
        # фигуру, уже сдвинутую игроком, ищем полным поиском
        moved = start is not None and start != B.spawn_state(board, kind)
        if self.search == "full" and (moved or M.has_overhang(board)):
            return M.all_placements(board, kind, start)
        if moved:
            return M.drop_placements(board, kind, start)
        return M.fast_drops(board, kind)

    def _first_ply(self, board, kind, start, used_hold):
        """[(оценка одного хода, место, признаки, поле после, высота)]."""
        top = F._top(board)
        items = []
        for p in self._places(board, kind, start):
            if B.locks_out(kind, p.rot, p.y):
                continue
            vec, after, _, heights = F.place_full(board, kind, p.rot, p.x, p.y, top)
            items.append((p, vec, after, heights))
        if not items:
            return []
        scores = self.evaluator.scores([i[1] for i in items], [i[3] for i in items])
        return [(s, p, vec, after, h, used_hold) for s, (p, vec, after, h) in zip(scores, items)]

    def _second_ply(self, after, heights, kind):
        """Лучшая оценка следующей фигуры на поле после первого хода (быстрый перебор)."""
        if kind is None or B.spawn_state(after, kind) is None:
            return DEAD
        top = max(heights)
        vecs, hs = [], []
        for rot, x, y in F.drop_spots(after, kind, heights):
            if B.locks_out(kind, rot, y):
                continue
            vec, _, _, h = F.place_full(after, kind, rot, x, y, top)
            vecs.append(vec)
            hs.append(h)
        if not vecs:
            return DEAD
        return max(self.evaluator.scores(vecs, hs))

    def choose(self, view):
        board = list(view.board)
        cands = self._first_ply(board, view.kind, view.start, False)
        nxt = {False: view.preview[0] if view.preview else None}
        if self.use_hold and not view.hold_used:
            other = view.hold if view.hold is not None else (view.preview[0] if view.preview else None)
            if other is not None:
                cands += self._first_ply(board, other, None, True)
                # hold пуст - ушла фигура из очереди, следующей станет вторая
                nxt[True] = view.preview[0] if view.hold is not None else (
                    view.preview[1] if len(view.preview) > 1 else None)
        if not cands:
            return None
        if self.lookahead:
            cands.sort(key=lambda c: -c[0])
            scored = []
            for i, (s, p, vec, after, h, used) in enumerate(cands):
                if i < self.prune:
                    total = self.evaluator.carry(vec) + self._second_ply(after, h, nxt[used])
                    scored.append((total, i, p, used))
                else:
                    scored.append((DEAD * 2 + s, i, p, used))
        else:
            scored = [(c[0], i, c[1], c[5]) for i, c in enumerate(cands)]
        scored.sort(key=lambda c: (-c[0], c[1]))
        best = scored[0]
        top = [Choice(s, p, used) for s, _, p, used in scored[:3]]
        path = (("hold",) if best[3] else ()) + best[2].path
        return Decision(path, best[2], best[0], top, best[3], self.lookahead)


def play_game(agent, seed, max_lines=10 ** 9, max_pieces=10 ** 9):
    """Партия ИИ в настоящей игре без времени: только нажатия. Для паспорта и тестов."""
    g = B.Game(seed=seed, gravity=False)
    while not g.over and g.lines < max_lines and g.pieces < max_pieces:
        d = agent.choose(observe(g))
        if d is None:
            break
        for key in d.path:
            if not g.press(key) and key != "hd":
                raise RuntimeError(f"нажатие {key} не прошло: {d.path}")
    return {"lines": g.lines, "pieces": g.pieces, "score": g.score,
            "capped": g.lines >= max_lines or g.pieces >= max_pieces, "fours": g.cleared[4]}


def agent_from_weights(weights, level):
    """Уровни (spec §3): новичок - ранние веса; средний - без взгляда вперёд; сильный -
    взгляд вперёд и hold."""
    if level == "novice":
        return Agent(Linear(weights), search="drop")
    if level == "medium":
        return Agent(Linear(weights), search="full")
    return Agent(Linear(weights), search="full", lookahead=True, use_hold=True)
