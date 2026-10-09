"""Маленькая сеть оценки поля на numpy (второй вариант ИИ, spec §3).

Вход - те же признаки поля, что у весов CEM, плюс профиль высот столбцов, всё в
масштабе около единицы. Выход - сколько ещё линий ждать после этого хода (ценность
состояния после хода, в наградах reward). Учится TD в игре с собой (game/train/td.py).
"""
import numpy as np

from aikit.nn import io as nnio
from aikit.nn.layers import Dense, Sequential, Tanh
from game.ai import features as F
from game.core import blocks as B

# делители признаков (landing, eroded, row, col, holes, wells, hole_rows, bump, height,
# max_height, lines) и высот: вход порядка единицы
SCALE = np.array([10, 16, 60, 60, 20, 30, 10, 30, 100, 20, 4], np.float32)
INPUTS = F.N + B.WIDTH
DEATH = -2.0        # награда за ход, после которого партия кончилась


def reward(lines):
    """Награда за ход: фигура поставлена и партия идёт (+1) и линии в квадрате - так
    сеть ценит и выживание, и сбор нескольких линий разом."""
    return 1.0 + lines * lines


def encode(vecs, heights):
    """Список признаков и высот -> (n, INPUTS)."""
    a = np.asarray(vecs, np.float32) / SCALE
    h = np.asarray(heights, np.float32) / B.VISIBLE
    return np.concatenate([a, h], axis=1)


class ValueNet:
    def __init__(self, hidden=32, seed=1, dtype=np.float32):
        rng = np.random.default_rng(seed)
        self.hidden = hidden
        self.model = Sequential([Dense(INPUTS, hidden, rng, dtype), Tanh(),
                                 Dense(hidden, hidden, rng, dtype), Tanh(),
                                 Dense(hidden, 1, rng, dtype)])
        self.out_scale = 50.0      # выход сети в сотнях линий не нужен: множитель на выходе

    def params(self):
        return self.model.params()

    def predict(self, x):
        return self.model.forward(x)[:, 0] * self.out_scale

    def forward(self, x):
        return self.model.forward(x)[:, 0] * self.out_scale

    def backward(self, dvalue):
        self.model.backward((dvalue * self.out_scale)[:, None].astype(self.model.items[0].W.dtype))

    def arrays(self):
        out = {name: p for name, p, _ in self.params()}
        out["hidden"] = np.array(self.hidden)
        return out

    def save(self, path):
        nnio.save(path, self.arrays())

    def load_arrays(self, arrays):
        for name, p, _ in self.params():
            if arrays[name].shape != p.shape:
                raise ValueError(f"{name}: в файле {arrays[name].shape}, в сети {p.shape}")
            p[...] = arrays[name]

    @classmethod
    def load(cls, path):
        arrays = nnio.load(path)
        net = cls(hidden=int(arrays["hidden"]))
        net.load_arrays(arrays)
        return net
