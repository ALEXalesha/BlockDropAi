"""Сеть оценки на numpy и обучение TD в игре с собой."""
import os

import numpy as np

from aikit.nn.gradcheck import check_layer
from game.ai import features as F
from game.ai import net as N
from game.core import blocks as B
from game.train import td

SMALL = dict(ceiling=8, max_lines=150, eval_games=6, eval_max_lines=150, seed=2,
             hidden=16, lr=3e-3, batch=128, buffer=20000, steps_per_update=200, updates=20, eps=0.05)


def test_encode_shape_and_scale():
    b = [0] * B.HEIGHT
    for r in range(5):
        b[r] = 0b1011111111
    vec, after, n, heights = F.place_full(b, B.I, 1, 6, 0)     # I в щель столбца 8
    x = N.encode([vec], [heights])
    assert x.shape == (1, N.INPUTS)
    assert np.all(np.abs(x) <= 3.0)


def test_value_net_gradients():
    net = N.ValueNet(hidden=6, seed=1, dtype=np.float64)
    rng = np.random.default_rng(0)
    check_layer(net.model, rng.normal(size=(5, N.INPUTS)), rng)


def test_save_load_roundtrip(tmp_path):
    net = N.ValueNet(hidden=8, seed=3)
    path = str(tmp_path / "v.npz")
    net.save(path)
    other = N.ValueNet.load(path)
    x = np.random.default_rng(1).normal(size=(4, N.INPUTS)).astype(np.float32)
    assert np.allclose(net.predict(x), other.predict(x))


def test_td_learning_beats_untrained_net(tmp_path):
    # зёрна те же - прогон тот же: необученная сеть 0 линий, после 20 малых кругов ~118
    t = td.Trainer(str(tmp_path / "td"), **{**SMALL, "steps_per_update": 100})
    before = t.evaluate()
    for _ in range(20):
        t.round(games=10)
    after = t.evaluate()
    assert after > before + 50, (before, after)


def test_snapshot_resume(tmp_path):
    cfg = {**SMALL, "steps_per_update": 10, "batch": 16}      # чтобы Adam успел сделать шаги
    a = td.Trainer(str(tmp_path / "a"), **cfg)
    a.round(games=3)
    b = td.Trainer(str(tmp_path / "a"), **cfg)
    assert b.load_snapshot()
    assert b.rounds == 1 and b.steps == a.steps
    assert b.adam.t == a.adam.t > 0
    assert all(np.array_equal(m1, m2) for m1, m2 in zip(a.adam.m, b.adam.m))
    x = np.random.default_rng(1).normal(size=(4, N.INPUTS)).astype(np.float32)
    assert np.allclose(a.net.predict(x), b.net.predict(x))
    assert os.path.exists(os.path.join(str(tmp_path / "a"), "train.log"))
