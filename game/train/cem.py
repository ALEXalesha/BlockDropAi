"""Метод перекрёстной энтропии (CEM) для весов признаков поля.

Поколение: из нормального распределения (mean, std) берутся population наборов весов,
каждый играет games партий (зёрна у всех одни - сравнение честнее), лучшие elite задают
новые mean и std. К дисперсии добавляется убывающий шум (Szita, Lőrincz 2006): без него
распределение сжимается раньше времени.

Учится на трудном варианте - фигуры равновероятные, а не мешком, и поле укорочено до
ceiling рядов: партии короче, разница между весами видна раньше. Проверяется (mean_eval)
средний набор весов на настоящем поле с мешком, до max_lines.

Журнал - train.log, снимок - cem.npz (атомарно, после каждого поколения), веса каждого
поколения - в истории: ранние идут уровню «новичок».
"""
import os
import time

import numpy as np

from aikit.trainlog import THREAD_VARS, TrainLog, load_snapshot, save_snapshot
from game.ai import features as F
from game.ai import sim

SNAPSHOT = "cem.npz"


def worker_init():
    """Работник считает в одном потоке BLAS: ПК делят и другие задачи."""
    for var in THREAD_VARS:
        os.environ[var] = "1"


def pick_workers(n):
    """Работников не больше половины ядер и по умолчанию не больше 6."""
    cap = max(1, (os.cpu_count() or 2) // 2)
    return max(1, min(n if n else 6, cap))


def _job(args):
    weights, seed, kw = args
    return sim.play(weights, seed, **kw)


def load(run):
    got = load_snapshot(os.path.join(run, SNAPSHOT))
    if got is None:
        return None
    arrays, meta = got
    return {"mean": arrays["mean"], "std": arrays["std"], **meta}


class Trainer:
    def __init__(self, run, population=60, elite=10, games=2, ceiling=12, max_lines=5000,
                 eval_games=10, eval_max_lines=None, init_std=5.0, noise=4.0, noise_decay=0.4,
                 seed=1, workers=1, echo=False):
        self.run = run
        os.makedirs(run, exist_ok=True)
        self.population, self.elite, self.games = population, elite, games
        self.ceiling, self.max_lines = ceiling, max_lines
        self.eval_games = eval_games
        self.eval_max_lines = eval_max_lines or max_lines
        self.noise, self.noise_decay = noise, noise_decay
        self.seed = seed
        self.mean = np.zeros(F.N)
        self.std = np.full(F.N, float(init_std))
        self.gen = 0
        self.history = []
        self.seconds = 0.0
        self.log = TrainLog(os.path.join(run, "train.log"), echo=echo)
        self.workers = pick_workers(workers) if workers > 1 else 1
        self.pool = None

    @property
    def snapshot_path(self):
        return os.path.join(self.run, SNAPSHOT)

    def _map(self, jobs):
        if self.workers > 1:
            if self.pool is None:
                import multiprocessing as mp
                self.pool = mp.get_context("spawn").Pool(self.workers, initializer=worker_init)
            return self.pool.map(_job, jobs, chunksize=1)
        return [_job(j) for j in jobs]

    def close(self):
        if self.pool is not None:
            self.pool.close()
            self.pool.join()
            self.pool = None

    def generation(self):
        started = time.perf_counter()
        rng = np.random.default_rng([self.seed, self.gen])
        cands = self.mean + self.std * rng.standard_normal((self.population, F.N))
        seeds = [int(s) for s in rng.integers(0, 2 ** 31, self.games)]
        train_kw = {"ceiling": self.ceiling, "max_lines": self.max_lines, "bag": False}
        jobs = [(list(map(float, w)), s, train_kw) for w in cands for s in seeds]
        res = self._map(jobs)
        fitness = np.array([np.mean([r["lines"] for r in res[i * self.games:(i + 1) * self.games]])
                            for i in range(self.population)])
        order = np.argsort(-fitness, kind="stable")
        elite = cands[order[:self.elite]]
        extra = max(self.noise - self.noise_decay * self.gen, 0.0)
        self.mean = elite.mean(axis=0)
        self.std = np.sqrt(elite.var(axis=0) + extra)
        # проверка среднего набора весов на настоящем поле с мешком
        eval_seeds = [10 ** 6 + i for i in range(self.eval_games)]
        eval_kw = {"max_lines": self.eval_max_lines, "bag": True}
        ev = self._map([(list(map(float, self.mean)), s, eval_kw) for s in eval_seeds])
        eval_lines = [r["lines"] for r in ev]
        secs = time.perf_counter() - started
        self.seconds += secs
        rec = {"gen": self.gen, "population_mean": round(float(fitness.mean()), 2),
               "elite_mean": round(float(fitness[order[:self.elite]].mean()), 2),
               "best": float(fitness[order[0]]),
               "mean_eval": round(float(np.mean(eval_lines)), 2),
               "eval_capped": int(sum(r["lines"] >= self.eval_max_lines for r in ev)),
               "pieces": int(sum(r["pieces"] for r in res) + sum(r["pieces"] for r in ev)),
               "seconds": round(secs, 2),
               "weights": [round(float(w), 4) for w in self.mean]}
        self.history.append(rec)
        self.gen += 1
        self.log(f"поколение {rec['gen']}: популяция {rec['population_mean']}, лучшие {rec['elite_mean']}, "
                 f"веса на поле с мешком {rec['mean_eval']} линий ({rec['eval_capped']} до предела), "
                 f"{secs:.1f} с")
        self.save_snapshot()
        return rec

    def config(self):
        return {"population": self.population, "elite": self.elite, "games": self.games,
                "ceiling": self.ceiling, "max_lines": self.max_lines, "eval_games": self.eval_games,
                "eval_max_lines": self.eval_max_lines, "noise": self.noise,
                "noise_decay": self.noise_decay, "seed": self.seed}

    def save_snapshot(self):
        save_snapshot(self.snapshot_path, {"mean": self.mean, "std": self.std},
                      {"gen": self.gen, "history": self.history, "seconds": self.seconds,
                       "config": self.config(), "features": list(F.NAMES)})

    def load_snapshot(self):
        snap = load(self.run)
        if snap is None:
            return False
        self.mean = np.array(snap["mean"], float)
        self.std = np.array(snap["std"], float)
        self.gen = snap["gen"]
        self.history = snap["history"]
        self.seconds = snap.get("seconds", 0.0)
        return True
