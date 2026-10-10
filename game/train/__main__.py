"""Обучение по команде:

    python -m game.train cem --trial                 # два поколения во временной папке и прогноз
    python -m game.train cem --gens 30 --workers 6   # обучение весов (runs/cem)
    python -m game.train cem --gens 40 --resume      # продолжить со снимка
    python -m game.train td --trial                  # пробный круг сети TD и прогноз
    python -m game.train td --rounds 60 --minutes 60 # сеть оценки TD (runs/td), один поток
    python -m game.train export                      # веса из снимка CEM -> game/models
    python -m game.train passport --trial            # пробы и прогноз времени паспорта
    python -m game.train passport                    # паспорт модели (runs/passport)
    python -m game.train compare                     # CEM против сети TD одним протоколом

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


def passport_args(sub):
    p = sub.add_parser("export", help="веса из снимка CEM в game/models")
    p.add_argument("--cem-run", default=os.path.join("runs", "cem"))
    p.add_argument("--novice-gen", type=int, default=0, help="поколение, чьи веса у новичка")
    p = sub.add_parser("passport", help="паспорт модели: партии уровней и дуэли")
    p.add_argument("--run", default=os.path.join("runs", "passport"))
    p.add_argument("--games", type=int, default=100)
    p.add_argument("--cap", type=int, default=10000, help="предел линий: новичок и средний")
    p.add_argument("--strong-cap", type=int, default=20000, help="предел линий сильного")
    p.add_argument("--duels", type=int, default=20, help="дуэлей на пару уровней")
    p.add_argument("--duel-pieces", type=int, default=1500)
    p.add_argument("--hard-games", type=int, default=100, help="партий трудной проверки на уровень")
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--trial", action="store_true", help="пробы и прогноз времени")


def compare_args(sub):
    p = sub.add_parser("compare", help="CEM против сети TD одним протоколом")
    p.add_argument("--net", default=os.path.join("runs", "td", "td-value.npz"))
    p.add_argument("--games", type=int, default=20)
    p.add_argument("--cap", type=int, default=10000)
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--run", default=os.path.join("runs", "compare"))


def run_compare(a):
    from aikit.trainlog import TrainLog
    from game.train import passport as PP
    model = PP.load_model()
    out = PP.compare_td(model, a.net, a.games, a.cap, a.workers, a.run,
                        log=TrainLog(os.path.join(a.run, "compare.log")))
    td_meta = {}
    snap = os.path.join(os.path.dirname(a.net), "td.npz")
    from aikit.trainlog import load_snapshot
    got = load_snapshot(snap)
    if got is not None:
        td_meta = {"rounds": got[1]["rounds"], "steps": got[1]["steps"], "seconds": round(got[1]["seconds"], 1)}
    model["comparison"] = {"protocol": f"средний уровень, {a.games} партий, до {a.cap} линий",
                           "cem": out["cem"], "td": {**out["td"], "training": td_meta},
                           "chosen": "cem" if out["cem"]["mean"] >= out["td"]["mean"] else "td"}
    tmp = PP.MODEL_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline=chr(10)) as f:
        json.dump(model, f, ensure_ascii=False, indent=1)
    os.replace(tmp, PP.MODEL_PATH)
    print(json.dumps(model["comparison"], ensure_ascii=False))
    return 0


def run_export(a):
    from game.train import passport as PP
    m = PP.export_model(a.cem_run, a.novice_gen)
    print(f"{PP.MODEL_PATH}: {m['training']['generations']} поколений", flush=True)
    return 0


def run_passport(a):
    from aikit.trainlog import TrainLog
    from game.train import passport as PP
    model = PP.load_model()
    log = TrainLog(os.path.join(a.run, "passport.log"))
    todo = PP.jobs(a.games, a.duels, a.cap, a.duel_pieces, a.strong_cap, a.hard_games)
    if a.trial:
        probes = [j for j in todo if j["kind"] == "probe"]
        recs = PP.run_jobs(model, probes, a.run, workers=1, log=log)
        ms = {}
        for lv in PP.LEVELS:
            rs = [r for r in recs if r["job"]["level"] == lv]
            ms[lv] = sum(r["seconds"] for r in rs) / max(sum(r["result"]["pieces"] for r in rs), 1)
        novice_pieces = sum(r["result"]["pieces"] for r in recs if r["job"]["level"] == "novice") / PP.PROBE_GAMES
        cpu = {"novice": a.games * novice_pieces * ms["novice"],
               "medium": a.games * a.cap * PIECES_PER_LINE * ms["medium"],
               "strong": a.games * a.strong_cap * PIECES_PER_LINE * ms["strong"]}
        duel_cpu = a.duels * a.duel_pieces * (ms["novice"] + 2 * ms["medium"] + 3 * ms["strong"])
        total = (sum(cpu.values()) + duel_cpu) / a.workers
        print(json.dumps({"ms_per_piece": {k: round(v * 1000, 2) for k, v in ms.items()},
                          "cpu_hours": {k: round(v / 3600, 2) for k, v in cpu.items()},
                          "duel_cpu_hours": round(duel_cpu / 3600, 2), "workers": a.workers,
                          "forecast_hours": round(total / 3600, 2)}, ensure_ascii=False))
        return 0
    recs = PP.run_jobs(model, todo, a.run, workers=a.workers, log=log)
    model["passport"] = PP.build(model, recs, a.games, a.cap, a.duels, a.duel_pieces, a.strong_cap)
    tmp = PP.MODEL_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline=chr(10)) as f:
        json.dump(model, f, ensure_ascii=False, indent=1)
    os.replace(tmp, PP.MODEL_PATH)
    for lv, s in model["passport"]["levels"].items():
        print(f"{lv}: среднее {s['mean']}, медиана {s['median']}, до предела {s['capped']}/{len(s['games'])}")
    for d in model["passport"]["duel"]:
        print(f"дуэль {d['a']}-{d['b']}: {d['wins_a']}:{d['wins_b']}, ничьих {d['draws']}, до предела {d['by_cap']}")
    for lv, s in model["passport"]["hard"]["levels"].items():
        print(f"трудная {lv}: среднее {s['mean']}, медиана {s['median']}, до предела {s['capped']}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m game.train")
    sub = ap.add_subparsers(dest="cmd", required=True)
    cem_args(sub)
    td_args(sub)
    passport_args(sub)
    compare_args(sub)
    a = ap.parse_args(argv)
    started = time.time()
    code = {"cem": run_cem, "td": run_td, "export": run_export, "passport": run_passport,
            "compare": run_compare}[a.cmd](a)
    print(f"готово за {time.time() - started:.0f} с", flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
