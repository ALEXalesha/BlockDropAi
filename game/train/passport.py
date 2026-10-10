"""Паспорт модели (spec §4): проверка силы уровней с зёрнами.

- Партии: на каждом уровне games партий, зерно партии i - 1000 + i (у всех уровней одни
  и те же фигуры), до конца игры или до предела линий уровня (сильный ИИ иначе играет
  бесконечно): новичок и средний - cap, сильный - strong_cap.
  Итог - среднее и медиана линий, сколько партий дошло до предела.
- Дуэли: уровни парами, у обоих одна очередь фигур, ходят по фигуре по очереди (кто
  первый - чередуется), очищенные линии шлют мусор (как в окне). Партия до проигрыша или
  до duel_pieces фигур у каждого; тогда побеждает тот, кто прислал больше мусора.
- Пробы: первые партии каждого уровня с маленьким пределом - их тесты пересчитывают до
  линии.

Работа долгая, поэтому каждая готовая партия сразу пишется строкой в results.jsonl, и
прерванный подсчёт продолжается с того же места. Работников - не больше двух по умолчанию.
"""
import json
import os
import statistics
import time

from game.ai import player as P
from game.core import blocks as B

MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
MODEL_PATH = os.path.join(MODEL_DIR, "blockdrop-cem.json")
LEVELS = ("novice", "medium", "strong")
PAIRS = (("novice", "medium"), ("novice", "strong"), ("medium", "strong"))
SEED0 = 1000
PROBE_GAMES = 3
PROBE_CAP = 200


def load_model(path=MODEL_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def level_agent(level, model):
    weights = model["novice_weights"] if level == "novice" else model["weights"]
    return P.agent_from_weights(weights, level)


def level_game(model, level, seed, cap):
    return P.play_game(level_agent(level, model), seed, max_lines=cap)


def duel(model, a, b, seed, max_pieces=1500):
    agents = {a: level_agent(a, model), b: level_agent(b, model)}
    games = {a: B.Game(seed=seed, gravity=False), b: B.Game(seed=seed, gravity=False)}
    order = (a, b) if seed % 2 == 0 else (b, a)
    loser = None
    while loser is None and min(g.pieces for g in games.values()) < max_pieces:
        for side in order:
            g = games[side]
            other = games[b if side == a else a]
            before = g.garbage_sent
            d = agents[side].choose(P.observe(g))
            if d is None:
                g.over = True
            else:
                for key in d.path:
                    g.press(key)
            other.receive_garbage(g.garbage_sent - before)
            if g.over:
                loser = side
                break
    sent = {k: g.garbage_sent for k, g in games.items()}
    if loser is not None:
        winner = b if loser == a else a
    elif sent[a] != sent[b]:
        winner = a if sent[a] > sent[b] else b
    else:
        winner = "draw"
    return {"winner": winner, "sent": sent, "lines": {k: g.lines for k, g in games.items()},
            "pieces": min(g.pieces for g in games.values()), "by_cap": loser is None}


def summarize(results, cap, seconds, pieces):
    lines = [r["lines"] for r in results]
    return {"games": len(lines), "cap": cap, "mean": round(statistics.mean(lines), 2),
            "median": statistics.median(lines), "min": min(lines), "max": max(lines),
            "capped": sum(1 for r in results if r["capped"]),
            "pieces_per_sec": round(pieces / seconds, 1) if seconds else None}


def level_caps(cap, strong_cap=None):
    """Предел линий по уровням. Сильный играет дольше всех - ему свой предел (решение
    Алексея 10.10: новичок и средний до 10 000, сильный до 20 000)."""
    return {lv: (strong_cap or cap) if lv == "strong" else cap for lv in LEVELS}


def jobs(games, duels, cap, duel_pieces, strong_cap=None):
    """Работы паспорта по порядку: пробы, партии уровней, дуэли."""
    caps = level_caps(cap, strong_cap)
    out = []
    for level in LEVELS:
        for i in range(PROBE_GAMES):
            out.append({"kind": "probe", "level": level, "seed": SEED0 + i, "cap": PROBE_CAP})
    for level in LEVELS:
        for i in range(games):
            out.append({"kind": "game", "level": level, "seed": SEED0 + i, "cap": caps[level]})
    for a, b in PAIRS:
        for i in range(duels):
            out.append({"kind": "duel", "a": a, "b": b, "seed": SEED0 + i, "pieces": duel_pieces})
    return out


def job_key(j):
    return json.dumps(j, sort_keys=True)


_MODEL = None


def _init(model):
    global _MODEL
    for var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[var] = "1"
    _MODEL = model


def do_job(j, model=None):
    model = model or _MODEL
    t0 = time.perf_counter()
    if j["kind"] == "duel":
        r = duel(model, j["a"], j["b"], j["seed"], j["pieces"])
    else:
        r = level_game(model, j["level"], j["seed"], j["cap"])
    return {"job": j, "result": r, "seconds": round(time.perf_counter() - t0, 3)}


def run_jobs(model, todo, run, workers=2, log=None):
    """Посчитать работы, пропуская готовые (results.jsonl в run). Возвращает все итоги
    по этим работам в их порядке."""
    os.makedirs(run, exist_ok=True)
    path = os.path.join(run, "results.jsonl")
    done = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue            # оборванная последняя строка
                done[job_key(rec["job"])] = rec
    left = [j for j in todo if job_key(j) not in done]

    def keep(rec):
        done[job_key(rec["job"])] = rec
        with open(path, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        if log:
            j, r = rec["job"], rec["result"]
            what = (f"дуэль {j['a']}-{j['b']} #{j['seed'] - SEED0}: {r['winner']}" if j["kind"] == "duel"
                    else f"{j['kind']} {j['level']} #{j['seed'] - SEED0}: {r['lines']} линий")
            log(f"{len(done)}/{len(todo)}  {what}  ({rec['seconds']:.1f} с)")

    if workers > 1 and left:
        import multiprocessing as mp
        with mp.get_context("spawn").Pool(workers, initializer=_init, initargs=(model,)) as pool:
            for rec in pool.imap_unordered(do_job, left):
                keep(rec)
    else:
        for j in left:
            keep(do_job(j, model))
    return [done[job_key(j)] for j in todo]


def build(model, records, games, cap, duels, duel_pieces, strong_cap=None):
    """Паспорт из итогов работ."""
    caps = level_caps(cap, strong_cap)
    by = {"probe": {}, "game": {}, "duel": {}}
    for rec in records:
        j = rec["job"]
        key = (j["a"], j["b"]) if j["kind"] == "duel" else j["level"]
        by[j["kind"]].setdefault(key, []).append(rec)
    levels = {}
    for level in LEVELS:
        recs = sorted(by["game"].get(level, []), key=lambda r: r["job"]["seed"])
        res = [r["result"] for r in recs]
        secs = sum(r["seconds"] for r in recs)
        s = summarize(res, caps[level], secs, sum(r["pieces"] for r in res))
        s["seconds"] = round(secs, 1)
        s["games"] = [{"seed": r["job"]["seed"], "lines": r["result"]["lines"]} for r in recs]
        levels[level] = s
    duel_out = []
    for a, b in PAIRS:
        recs = by["duel"].get((a, b), [])
        wins = {a: 0, b: 0, "draw": 0}
        for r in recs:
            wins[r["result"]["winner"]] += 1
        n = max(len(recs), 1)
        duel_out.append({"a": a, "b": b, "duels": len(recs), "wins_a": wins[a], "wins_b": wins[b],
                         "draws": wins["draw"], "share_b": round((wins[b] + wins["draw"] / 2) / n, 3),
                         "by_cap": sum(1 for r in recs if r["result"]["by_cap"])})
    probe = {lv: [{"seed": r["job"]["seed"], "cap": r["job"]["cap"], "result": r["result"]}
                  for r in sorted(by["probe"].get(lv, []), key=lambda r: r["job"]["seed"])] for lv in LEVELS}
    return {"caps": caps, "games": games, "duels": duels, "duel_pieces": duel_pieces,
            "levels": levels, "duel": duel_out, "probe": probe,
            "seconds": round(sum(r["seconds"] for r in records), 1)}


def export_model(cem_run, novice_gen=0, path=MODEL_PATH):
    """Веса из снимка CEM -> game/models/blockdrop-cem.json (паспорт допишется позже)."""
    from game.ai import features as F
    from game.train import cem
    snap = cem.load(cem_run)
    if snap is None:
        raise SystemExit(f"нет снимка CEM в {cem_run}")
    hist = snap["history"]
    model = {"features": list(F.NAMES),
             "weights": [round(float(w), 6) for w in snap["mean"]],
             "novice_weights": hist[novice_gen]["weights"], "novice_generation": novice_gen,
             "training": {"method": "CEM", "generations": snap["gen"], "seconds": round(snap["seconds"], 1),
                          "config": snap["config"],
                          "history": [{k: h[k] for k in ("gen", "population_mean", "elite_mean", "best",
                                                          "mean_eval", "eval_capped", "seconds")}
                                      for h in hist]}}
    if os.path.exists(path):
        old = load_model(path)
        if old.get("weights") == model["weights"] and "passport" in old:
            model["passport"] = old["passport"]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(model, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
    return model
