"""Логика окна без Qt: автоповтор сдвига (DAS/ARR) по часам, ИИ жмёт клавиши с заданной
скоростью и перепланирует, если ход не прошёл, дуэль с мусором. Время - подставные часы."""
import pytest

from game.ai import player as P
from game.core import blocks as B
from game.ui import session as S

W = [-4.9, 2.7, -4.1, -9.1, -14.0, -4.2, -7.9, -1.1, -0.55, 3.8, -5.1]


def human(das=0.15, arr=0.05, seed=3):
    g = B.Game(seed=seed, gravity=False)
    return S.HumanSession(g, das=das, arr=arr, now=0.0)


def test_das_then_arr():
    h = human()
    x0 = h.game.x
    h.press("left", 0.0)
    assert h.game.x == x0 - 1
    h.tick(0.149)
    assert h.game.x == x0 - 1
    h.tick(0.15)
    assert h.game.x == x0 - 2
    h.tick(0.199)
    assert h.game.x == x0 - 2
    h.tick(0.2)
    assert h.game.x == x0 - 3
    h.release("left", 0.21)
    h.tick(1.0)
    assert h.game.x == x0 - 3


def test_arr_zero_goes_to_wall():
    h = human(arr=0.0)
    x0 = h.game.x
    h.press("right", 0.0)
    h.tick(0.1)                      # задержка автоповтора ещё не прошла - только один сдвиг
    assert h.game.x == x0 + 1
    h.tick(0.2)
    assert not B.fits(h.game.board, h.game.kind, h.game.rot, h.game.x + 1, h.game.y)


@pytest.mark.parametrize("fps", [30, 60, 144, 1000])
def test_repeat_does_not_depend_on_frame_rate(fps):
    # числа - двоичные дроби, чтобы сравнение времени было точным
    h = human(das=0.125, arr=0.03125)
    h.press("right", 0.0)
    t = 0.0
    while t < 0.1875:
        t = min(t + 1 / fps, 0.1875)
        h.tick(t)
    # сразу 1, на DAS 1, повторы на 0.15625 и 0.1875
    assert h.attempts["right"] == 4


def test_soft_drop_hold_and_hard_drop():
    g = B.Game(seed=1)
    h = S.HumanSession(g, now=0.0)
    y = g.y
    h.press("soft", 0.0)
    h.tick(0.2)
    assert g.y < y - 2                  # мягкое падение в 20 раз быстрее
    h.release("soft", 0.2)
    h.press("hard", 0.3)
    assert g.pieces == 1


def test_pause_freezes_time():
    g = B.Game(seed=1)
    h = S.HumanSession(g, now=0.0)
    y = g.y
    h.pause(0.1)
    h.tick(5.0)
    assert g.y == y
    h.resume(5.0)
    h.tick(5.5)
    assert g.y == y


class Spy(B.Game):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.keys = []

    def press(self, key):
        self.keys.append(key)
        return super().press(key)


def run_ai(driver, seconds, step=1 / 60):
    t = 0.0
    while t < seconds and not driver.game.over:
        t += step
        driver.tick(t)
    return t


def test_ai_plays_real_time_by_keys_only():
    g = Spy(seed=2)
    d = S.AiDriver(g, P.agent_from_weights(W, "medium"), key_interval=0.02, think=0.05, now=0.0)
    run_ai(d, 60)
    assert g.lines >= 10 and not g.over
    assert g.keys and set(g.keys) <= {"L", "R", "cw", "ccw", "sd", "hd", "hold"}
    # почти каждую фигуру ставит жёсткий сброс; остальные легли сами по задержке
    # фиксации, когда падение на высоком уровне обогнало нажатия
    assert g.pieces * 0.9 <= g.keys.count("hd") <= g.pieces


def test_ai_pieces_per_second_limit():
    g = B.Game(seed=2, gravity=False)
    d = S.AiDriver(g, P.agent_from_weights(W, "strong"), key_interval=0.0, think=1.0, now=0.0)
    run_ai(d, 10.0)
    assert 8 <= g.pieces <= 11


def test_ai_replans_when_gravity_breaks_the_path():
    g = B.Game(seed=5, level=19)      # очень быстрое падение: пути ломаются
    d = S.AiDriver(g, P.agent_from_weights(W, "medium"), key_interval=0.05, think=0.0, now=0.0)
    run_ai(d, 30)
    assert g.pieces > 20
    assert d.replans > 0


def test_ai_max_speed_ignores_clock():
    g = B.Game(seed=2, gravity=False)
    d = S.AiDriver(g, P.agent_from_weights(W, "medium"), key_interval=0.0, think=0.0, now=0.0)
    d.tick(0.0, budget=0.5)
    assert g.pieces > 20


def test_duel_sends_garbage():
    a = B.Game(seed=4, gravity=False)
    b = B.Game(seed=4, gravity=False)
    duel = S.Duel(a, b)
    a.board = [B.FULL & ~1] * 4 + [0] * (B.HEIGHT - 4)
    a._spawn(B.I)
    a.rotate(1)
    while a.move(-1):
        pass
    a.hard_drop()
    duel.exchange()
    assert b.pending() == 4
    duel.exchange()
    assert b.pending() == 4
    assert duel.winner() is None
    b.over = True
    assert duel.winner() == "a"


def test_zero_pauses_without_budget_do_not_hang():
    # нулевые паузы и обычный такт (без бюджета): один такт не играет бесконечно
    g = B.Game(seed=2, gravity=False)
    d = S.AiDriver(g, P.agent_from_weights(W, "medium"), key_interval=0.0, think=0.0, now=0.0)
    d.tick(1.0)
    assert 0 < g.pieces <= S.MAX_STEPS_PER_TICK
