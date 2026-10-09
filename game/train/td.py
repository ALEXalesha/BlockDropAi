"""Обучение сети оценки TD(0) в игре с собой (второй вариант ИИ, spec §3).

Ценность состояния после хода V(s) - сумма будущих наград (net.reward: +1 за каждую
поставленную фигуру и квадрат числа линий, DEATH за ход, после которого партия кончилась).
Ход выбирается по награде сейчас + V(после хода), иногда случайно (eps). Для пары
соседних ходов цель V(s) = r' + gamma * V(s'), в конце партии - DEATH. Переходы копятся в буфере, сеть
учится пачками (Adam). Условия те же, что у CEM: равновероятные фигуры, укороченное поле;
проверка - на настоящем поле с мешком.

Журнал - train.log, снимок - td.npz (сеть и Adam), продолжение с того же места.
"""
import os
import time

import numpy as np

from aikit.nn.optim import Adam
from aikit.trainlog import TrainLog, load_snapshot, save_snapshot
from game.ai import features as F
from game.ai import sim
from game.ai.net import DEATH, ValueNet, encode, reward
from game.core import blocks as B

SNAPSHOT = "td.npz"


def candidates(board, kind, top, heights):
    """Все сбросы: (входы сети, [(после хода, линий, верх, высоты)])."""
    vecs, hs, rest = [], [], []
    for rot, x, y in F.drop_spots(board, kind, heights):
        if B.locks_out(kind, rot, y):
            continue
        vec, after, n, h = F.place_full(board, kind, rot, x, y, top)
        vecs.append(vec)
        hs.append(h)
        rest.append((after, n, vec[9], h))
    if not rest:
        return None, []
    return encode(vecs, hs), rest


def play_net(net, seed, max_lines=10 ** 9, ceiling=None, bag=True, eps=0.0, rng=None, record=None):
    """Партия по сети. record(x_prev, r, x_now, done) - для обучения."""
    pieces = sim.Pieces(seed, bag)
    board = [0] * B.HEIGHT
    top, heights = 0, [0] * B.WIDTH
    lines = count = 0
    prev = None
    while lines < max_lines:
        kind = pieces.next()
        x, rest = (None, []) if B.spawn_state(board, kind) is None else candidates(board, kind, top, heights)
        if not rest:
            if record and prev is not None:
                record(prev, DEATH, prev, True)
            break
        q = np.array([reward(r[1]) for r in rest], np.float32) + net.predict(x)
        i = int(rng.integers(len(rest))) if eps and rng.random() < eps else int(np.argmax(q))
        board, n, top, heights = rest[i]
        if record and prev is not None:
            record(prev, reward(n), x[i], False)
        prev = x[i]
        lines += n
        count += 1
        if ceiling is not None and top > ceiling:
            if record:
                record(prev, DEATH, prev, True)
            break
    return {"lines": lines, "pieces": count}


class Trainer:
    def __init__(self, run, ceiling=12, max_lines=5000, eval_games=10, eval_max_lines=20000, seed=1,
                 hidden=32, lr=1e-3, batch=256, buffer=100000, steps_per_update=500, updates=50,
                 eps=0.05, gamma=0.99, echo=False):
        self.run = run
        os.makedirs(run, exist_ok=True)
        self.ceiling, self.max_lines = ceiling, max_lines
        self.eval_games, self.eval_max_lines = eval_games, eval_max_lines
        self.seed = seed
        self.batch, self.buffer_size = batch, buffer
        self.steps_per_update, self.updates = steps_per_update, updates
        self.eps, self.gamma = eps, gamma
        self.net = ValueNet(hidden=hidden, seed=seed)
        self.adam = Adam(self.net.params(), lr=lr)
        self.rounds = 0
        self.steps = 0
        self.seconds = 0.0
        self.history = []
        self.buf = []
        self.log = TrainLog(os.path.join(run, "train.log"), echo=echo)

    @property
    def snapshot_path(self):
        return os.path.join(self.run, SNAPSHOT)

    def _record(self, x_prev, r, x_now, done):
        self.buf.append((x_prev, r, x_now, done))
        if len(self.buf) > self.buffer_size:
            del self.buf[:len(self.buf) - self.buffer_size]
        self.steps += 1
        if self.steps % self.steps_per_update == 0:
            self._learn()

    def _learn(self):
        n = len(self.buf)
        if n < self.batch:
            return
        for _ in range(self.updates):
            idx = self.rng.integers(0, n, self.batch)
            xs = np.stack([self.buf[i][0] for i in idx])
            xn = np.stack([self.buf[i][2] for i in idx])
            r = np.array([self.buf[i][1] for i in idx], np.float32)
            done = np.array([self.buf[i][3] for i in idx], bool)
            target = r + self.gamma * np.where(done, 0.0, self.net.predict(xn))
            pred = self.net.forward(xs)
            grad = 2.0 * (pred - target) / len(idx)
            self.net.backward(grad.astype(np.float32))
            self.adam.step()

    def round(self, games=20):
        started = time.perf_counter()
        self.rng = np.random.default_rng([self.seed, self.rounds])
        results = []
        for _ in range(games):
            s = int(self.rng.integers(0, 2 ** 31))
            results.append(play_net(self.net, s, self.max_lines, self.ceiling, bag=False,
                                    eps=self.eps, rng=self.rng, record=self._record))
        ev = self.evaluate()
        secs = time.perf_counter() - started
        self.seconds += secs
        rec = {"round": self.rounds, "train_lines": round(float(np.mean([r["lines"] for r in results])), 2),
               "mean_eval": ev, "steps": self.steps, "seconds": round(secs, 2)}
        self.history.append(rec)
        self.rounds += 1
        self.log(f"круг {rec['round']}: в обучении {rec['train_lines']} линий, на поле с мешком {ev}, "
                 f"шагов {self.steps}, {secs:.1f} с")
        self.save_snapshot()
        return rec

    def evaluate(self, games=None):
        games = games or self.eval_games
        lines = [play_net(self.net, 10 ** 6 + i, self.eval_max_lines, bag=True)["lines"] for i in range(games)]
        return round(float(np.mean(lines)), 2)

    def save_snapshot(self):
        arrays = {f"net.{k}": v for k, v in self.net.arrays().items()}
        for i, (m, v) in enumerate(zip(self.adam.m, self.adam.v)):
            arrays[f"adam.m{i}"] = m
            arrays[f"adam.v{i}"] = v
        save_snapshot(self.snapshot_path, arrays,
                      {"rounds": self.rounds, "steps": self.steps, "adam_t": self.adam.t,
                       "seconds": self.seconds, "history": self.history})

    def load_snapshot(self):
        got = load_snapshot(self.snapshot_path)
        if got is None:
            return False
        arrays, meta = got
        self.net.load_arrays({k[4:]: v for k, v in arrays.items() if k.startswith("net.")})
        for i in range(len(self.adam.m)):
            self.adam.m[i][...] = arrays[f"adam.m{i}"]
            self.adam.v[i][...] = arrays[f"adam.v{i}"]
        self.adam.t = meta["adam_t"]
        self.rounds, self.steps = meta["rounds"], meta["steps"]
        self.seconds, self.history = meta["seconds"], meta["history"]
        return True
