"""Паспорт модели: уровни, партии с зёрнами, дуэли. Малая выборка паспорта пересчитывается
и должна совпасть до линии."""
import json
import os

import pytest

from game.ai import player as P
from game.train import passport as PP

W = [-1.0, 1.0, -1.0, -1.0, -4.0, -1.0, 0.0, 0.0, 0.0, 0.0, 0.0]
EARLY = [-0.5, 0.2, -0.3, -0.2, -1.0, -0.1, 0.0, 0.0, 0.0, 0.0, 0.0]
MODEL = {"weights": W, "novice_weights": EARLY}


def test_levels_by_spec():
    nov, med, strong = (PP.level_agent(lv, MODEL) for lv in PP.LEVELS)
    assert nov.evaluator.w == EARLY and nov.search == "drop" and not nov.lookahead
    assert med.evaluator.w == W and not med.lookahead and not med.use_hold
    assert strong.lookahead and strong.use_hold and strong.evaluator.w == W


def test_level_game_is_seeded():
    a = PP.level_game(MODEL, "medium", 3, cap=40)
    b = PP.level_game(MODEL, "medium", 3, cap=40)
    assert a == b and a["lines"] >= 40 and a["capped"]


def test_duel_garbage_and_result():
    r = PP.duel(MODEL, "novice", "strong", 4, max_pieces=400)
    assert r["winner"] in ("novice", "strong", "draw")
    assert r == PP.duel(MODEL, "novice", "strong", 4, max_pieces=400)
    assert r["sent"]["strong"] >= 0 and r["pieces"] > 0


def test_summary_mean_median():
    s = PP.summarize([{"lines": 10, "capped": False}, {"lines": 30, "capped": False},
                      {"lines": 100, "capped": True}], cap=100, seconds=2.0, pieces=100)
    assert s["mean"] == pytest.approx(140 / 3, abs=0.01) and s["median"] == 30 and s["capped"] == 1


def test_strong_has_its_own_cap():
    js = PP.jobs(games=2, duels=0, cap=100, duel_pieces=10, strong_cap=300)
    caps = {j["level"]: j["cap"] for j in js if j["kind"] == "game"}
    assert caps == {"novice": 100, "medium": 100, "strong": 300}
    # пробы не зависят от пределов - их итоги из прошлого прогона годятся
    assert all(j["cap"] == PP.PROBE_CAP for j in js if j["kind"] == "probe")


def test_resume_skips_done_jobs(tmp_path):
    run = str(tmp_path / "p")
    jobs = PP.jobs(games=2, duels=2, cap=30, duel_pieces=100)
    done = PP.run_jobs(MODEL, jobs[:3], run, workers=1)
    assert len(done) == 3
    again = PP.run_jobs(MODEL, jobs, run, workers=1)
    assert len(again) == len(jobs)
    lines = open(os.path.join(run, "results.jsonl"), encoding="utf-8").read().splitlines()
    assert len(lines) == len(jobs)


def stored():
    if not os.path.exists(PP.MODEL_PATH):
        return None
    with open(PP.MODEL_PATH, encoding="utf-8") as f:
        model = json.load(f)
    return model if "passport" in model else None


@pytest.mark.slow
def test_passport_probe_recomputes_exactly():
    model = stored()
    if model is None:
        pytest.skip("паспорт ещё не посчитан")
    for level, games in model["passport"]["probe"].items():
        for g in games:
            assert PP.level_game(model, level, g["seed"], cap=g["cap"]) == g["result"], level


@pytest.mark.slow
def test_passport_novice_games_recompute():
    model = stored()
    if model is None:
        pytest.skip("паспорт ещё не посчитан")
    games = model["passport"]["levels"]["novice"]["games"][:3]
    cap = model["passport"]["caps"]["novice"]
    for g in games:
        r = PP.level_game(model, "novice", g["seed"], cap=cap)
        assert r["lines"] == g["lines"]


def test_agent_from_model_plays_by_buttons():
    r = P.play_game(PP.level_agent("strong", MODEL), seed=2, max_lines=15)
    assert r["lines"] >= 15


def test_compare_cem_and_td_same_protocol(tmp_path):
    from game.ai.net import ValueNet
    net = str(tmp_path / "v.npz")
    ValueNet(hidden=8, seed=1).save(net)
    out = PP.compare_td(MODEL, net, games=2, cap=20, workers=1, run=str(tmp_path / "c"))
    assert out["cem"]["games"] == 2 and out["td"]["games"] == 2
    assert out["cem"]["cap"] == out["td"]["cap"] == 20


def test_hard_test_ends_on_short_field():
    r = PP.hard_game(MODEL, "medium", 3, ceiling=4, cap=500)
    assert r == PP.hard_game(MODEL, "medium", 3, ceiling=4, cap=500)
    assert r["lines"] < 500 and not r["capped"]
    js = PP.jobs(games=2, duels=0, cap=10, duel_pieces=10, hard_games=3)
    assert sum(1 for j in js if j["kind"] == "hard") == 3 * len(PP.LEVELS)


def test_readme_numbers_match_passport():
    model = stored()
    if model is None:
        pytest.skip("паспорт ещё не посчитан")
    pp = model["passport"]
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    en = open(os.path.join(root, "README.md"), encoding="utf-8").read()
    ru = open(os.path.join(root, "README.ru.md"), encoding="utf-8").read()
    nov = pp["levels"]["novice"]
    assert f"| Novice | {nov['mean']:.1f} | {nov['median']:g} |" in en
    assert f"| Новичок | {nov['mean']:.1f} | {nov['median']:g} |".replace(".", ",") in ru
    for lv, name in (("novice", "Novice"), ("medium", "Medium"), ("strong", "Strong")):
        h = pp["hard"]["levels"][lv]
        assert f"| {name} | {h['mean']:.1f} | {h['median']:g} |" in en, lv
    for lv in ("medium", "strong"):
        s = pp["levels"][lv]
        assert s["capped"] == len(s["games"]) == 100
