"""Метод перекрёстной энтропии: среднее число линий растёт за несколько поколений,
журнал пишется, снимок продолжается с того же места, потоки ограничены."""
import json
import os

import numpy as np
import pytest

from game.ai import features as F
from game.train import cem

SMALL = dict(population=12, elite=3, games=2, ceiling=6, max_lines=80, eval_games=4, seed=3)


def test_lines_grow_over_generations(tmp_path):
    t = cem.Trainer(str(tmp_path / "run"), **SMALL)
    for _ in range(4):
        t.generation()
    first = t.history[0]
    last = t.history[-1]
    assert last["mean_eval"] > first["population_mean"] * 2
    assert last["mean_eval"] > first["mean_eval"]
    assert len(t.mean) == F.N


def test_log_and_snapshot_resume_same_result(tmp_path):
    a = cem.Trainer(str(tmp_path / "a"), **SMALL)
    for _ in range(3):
        a.generation()
    b = cem.Trainer(str(tmp_path / "b"), **SMALL)
    b.generation()
    b.generation()
    c = cem.Trainer(str(tmp_path / "b"), **SMALL)
    assert c.load_snapshot() and c.gen == 2
    c.generation()
    assert np.allclose(a.mean, c.mean) and np.allclose(a.std, c.std)
    assert [h["mean_eval"] for h in a.history] == [h["mean_eval"] for h in c.history]
    log = open(os.path.join(str(tmp_path / "b"), "train.log"), encoding="utf-8").read()
    assert log.count("поколение") >= 3


def test_snapshot_keeps_weights_of_every_generation(tmp_path):
    t = cem.Trainer(str(tmp_path / "r"), **SMALL)
    t.generation()
    t.generation()
    snap = cem.load(str(tmp_path / "r"))
    assert len(snap["history"]) == 2
    assert all(len(h["weights"]) == F.N for h in snap["history"])
    json.dumps(snap["history"])


def test_workers_use_one_blas_thread(monkeypatch):
    for var in cem.THREAD_VARS:
        monkeypatch.setenv(var, "8")
    cem.worker_init()
    assert all(os.environ[v] == "1" for v in cem.THREAD_VARS)


def test_pool_size_is_limited():
    assert cem.pick_workers(None) <= 6
    assert cem.pick_workers(100) <= max(1, (os.cpu_count() or 2) // 2)


@pytest.mark.slow
def test_parallel_equals_serial(tmp_path):
    a = cem.Trainer(str(tmp_path / "a"), **SMALL)
    a.generation()
    b = cem.Trainer(str(tmp_path / "b"), workers=2, **SMALL)
    try:
        b.generation()
    finally:
        b.close()
    assert np.allclose(a.mean, b.mean)
