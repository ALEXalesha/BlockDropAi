"""Обучение по команде:

    python -m game.train cem --trial                 # два поколения во временной папке и прогноз
    python -m game.train cem --gens 30 --workers 6   # обучение весов (runs/cem)
    python -m game.train cem --gens 40 --resume      # продолжить со снимка
    python -m game.train td --trial                  # пробный круг сети TD и прогноз
    python -m game.train td --rounds 60 --minutes 60 # сеть оценки TD (runs/td), один поток

Потоки ограничены: каждый работник считает в одном потоке BLAS, работников не больше
половины ядер (по умолчанию 6). Журнал и снимок - в --run.
"""
import os

for _var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_var] = "1"

import argparse  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402

PIECES_PER_LINE = 2.5       # 10 клеток на линию, 4 клетки на фигуру
# веса Дельяши (landing, eroded, row, col, holes, wells) - для замера скорости
REFERENCE_WEIGHTS = [-1.0, 1.0, -1.0, -1.0, -4.0, -1.0, 0.0, 0.0, 0.0, 0.0, 0.0]


def cem_args(sub):
    p = sub.add_parser("cem", help="веса признаков методом перекрёстной энтропии")
    p.add_argument("--run", default=os.path.join("runs", "cem"))
    p.add_argument("--gens", type=int, default=30)
    p.add_argument("--population", type=int, default=60)
    p.add_argument("--elite", type=int, default=10)
    p.add_argument("--games", type=int, default=2)
    p.add_argument("--ceiling", type=int, default=12)
    p.add_argument("--max-lines", type=int, default=5000)
    p.add_argument("--eval-games", type=int, default=10)
    p.add_argument("--eval-max-lines", type=int, default=20000)
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--resume", action="store_true")
    p.add_argument("--trial", action="store_true", help="два поколения и прогноз времени")


def run_cem(a):
    from game.train.cem import Trainer
    kw = dict(population=a.population, elite=a.elite, games=a.games, ceiling=a.ceiling,
              max_lines=a.max_lines, eval_games=a.eval_games, eval_max_lines=a.eval_max_lines,
              seed=a.seed, workers=a.workers, echo=True)
    if a.trial:
        run = tempfile.mkdtemp(prefix="blockdrop-cem-trial-")
        t = Trainer(run, **kw)
        try:
            recs = [t.generation() for _ in range(2)]
        finally:
            t.close()
        # первые поколения играют крошечные партии, там время съедает запуск работников;
        # скорость счёта меряется длинной партией весами Дельяши: обученные веса держат
        # стопку так же низко, а высокая стопка считается медленнее
        from game.ai import sim
        t0 = time.perf_counter()
        cal = sim.play(REFERENCE_WEIGHTS, 7, max_pieces=6000, bag=True)
        pps = cal["pieces"] / (time.perf_counter() - t0) * 0.8     # запас на соседей по ПК
        worst_pieces = (a.population * a.games * a.max_lines + a.eval_games * a.eval_max_lines) * PIECES_PER_LINE
        worst_gen = worst_pieces / (pps * t.workers)
        print(json.dumps({"trial_dir": run, "workers": t.workers,
                          "pieces_per_sec_per_worker": round(pps),
                          "trial_gen_seconds": [r["seconds"] for r in recs],
                          "worst_gen_seconds": round(worst_gen),
                          "worst_total_hours": round(worst_gen * a.gens / 3600, 2)}, ensure_ascii=False))
        return 0
    t = Trainer(a.run, **kw)
    if a.resume and t.load_snapshot():
        print(f"продолжаю с поколения {t.gen}", flush=True)
    try:
        while t.gen < a.gens:
            t.generation()
    finally:
        t.close()
    return 0


def td_args(sub):
    p = sub.add_parser("td", help="сеть оценки, TD в игре с собой (один процесс)")
    p.add_argument("--run", default=os.path.join("runs", "td"))
    p.add_argument("--rounds", type=int, default=60)
    p.add_argument("--games", type=int, default=20, help="партий за круг")
    p.add_argument("--minutes", type=float, default=0, help="остановиться после стольких минут")
    p.add_argument("--ceiling", type=int, default=12)
    p.add_argument("--max-lines", type=int, default=5000)
    p.add_argument("--eval-games", type=int, default=10)
    p.add_argument("--eval-max-lines", type=int, default=20000)
    p.add_argument("--hidden", type=int, default=32)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--gamma", type=float, default=0.99)
    p.add_argument("--eps", type=float, default=0.05)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--resume", action="store_true")
    p.add_argument("--trial", action="store_true", help="один круг и прогноз времени")


def run_td(a):
    from game.train.td import Trainer
    kw = dict(ceiling=a.ceiling, max_lines=a.max_lines, eval_games=a.eval_games,
              eval_max_lines=a.eval_max_lines, hidden=a.hidden, lr=a.lr, gamma=a.gamma, eps=a.eps,
              seed=a.seed, echo=True)
    if a.trial:
        run = tempfile.mkdtemp(prefix="blockdrop-td-trial-")
        t = Trainer(run, **kw)
        r = t.round(games=a.games)
        # худший случай: каждая партия обучения и проверки - до предела линий
        steps_per_sec = max(r["steps"], 1) / r["seconds"]
        worst_round = (a.games * a.max_lines + a.eval_games * a.eval_max_lines) * PIECES_PER_LINE / steps_per_sec
        print(json.dumps({"trial_dir": run, "round": r, "steps_per_sec": round(steps_per_sec),
                          "worst_round_seconds": round(worst_round),
                          "worst_total_hours": round(worst_round * a.rounds / 3600, 2)},
                         ensure_ascii=False))
        return 0
    t = Trainer(a.run, **kw)
    if a.resume and t.load_snapshot():
        print(f"продолжаю с круга {t.rounds}", flush=True)
    started = time.time()
    while t.rounds < a.rounds:
        t.round(games=a.games)
        if a.minutes and time.time() - started > a.minutes * 60:
            print(f"время вышло: {a.minutes} мин", flush=True)
            break
    t.net.save(os.path.join(a.run, "td-value.npz"))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m game.train")
    sub = ap.add_subparsers(dest="cmd", required=True)
    cem_args(sub)
    td_args(sub)
    a = ap.parse_args(argv)
    started = time.time()
    code = {"cem": run_cem, "td": run_td}[a.cmd](a)
    print(f"готово за {time.time() - started:.0f} с", flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
