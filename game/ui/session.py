"""Логика окна без Qt: человек с клавиатуры, ИИ кнопками, дуэль. Время - от часов
(now в секундах, time.monotonic в окне), а не от кадров.

- HumanSession: нажатия и отпускания действий, автоповтор сдвига по DAS/ARR, мягкое
  падение пока клавиша зажата, пауза.
- AiDriver: ИИ смотрит на партию как игрок (player.observe), решает, сколько думать
  (think - секунд на фигуру, отсюда «ходов в секунду»), и жмёт клавиши по одной через
  key_interval. Если клавиша не прошла (сила тяжести сдвинула фигуру), решает заново от
  того места, где фигура сейчас. Решение можно считать в потоке: decide - функция,
  которая получает View и возвращает Decision (или None, пока не готово).
- Duel: две партии, мусор от очищенных линий уходит сопернику.
"""
import math

from game.ai import player as P
from game.core import blocks as B

ACTIONS = ("left", "right", "soft", "hard", "cw", "ccw", "hold")
# за один такт ИИ нажимает не больше стольких клавиш: при нулевых паузах без часов
# (скорость «максимум» без бюджета) иначе один такт играл бы партию бесконечно
MAX_STEPS_PER_TICK = 400
KEY_OF = {"cw": "cw", "ccw": "ccw", "hard": "hd", "hold": "hold"}


class HumanSession:
    def __init__(self, game, das=0.167, arr=0.033, now=0.0):
        self.game = game
        self.das, self.arr = das, arr
        self.last = now
        self.held = {}              # направление -> время нажатия
        self.attempts = {"left": 0, "right": 0}
        self.done = {}              # сколько сдвигов уже сделано за это нажатие
        self.paused = False

    def _shift(self, side):
        self.attempts[side] += 1
        return self.game.move(-1 if side == "left" else 1)

    def press(self, action, now):
        if self.paused or self.game.over:
            return
        self.tick(now)
        if action in ("left", "right"):
            other = "right" if action == "left" else "left"
            self.held.pop(other, None)          # последнее нажатие главнее
            self.held[action] = now
            self.done[action] = 1
            self._shift(action)
        elif action == "soft":
            self.game.set_soft(True)
        else:
            self.game.press(KEY_OF[action])

    def release(self, action, now):
        self.tick(now)
        if action in ("left", "right"):
            self.held.pop(action, None)
        elif action == "soft":
            self.game.set_soft(False)

    def _due(self, held_for):
        """Сколько сдвигов положено за held_for секунд удержания (включая первый)."""
        if held_for < self.das:
            return 1
        if self.arr <= 0:
            return B.WIDTH + 1                   # мгновенно до стены
        return 2 + int(math.floor((held_for - self.das) / self.arr))

    def tick(self, now):
        if self.paused:
            self.last = now
            return
        for side, since in list(self.held.items()):
            due = self._due(now - since)
            while self.done[side] < due:
                self.done[side] += 1
                if not self._shift(side) and self.arr <= 0:
                    self.done[side] = due
                    break
        dt = now - self.last
        self.last = now
        if dt > 0:
            self.game.update(dt)

    def pause(self, now):
        self.tick(now)
        self.paused = True

    def resume(self, now):
        self.paused = False
        self.last = now
        for side in self.held:
            self.held[side] = now
            self.done[side] = 1


class AiDriver:
    """think=0 и key_interval=0 - «максимум»: tick(now, budget) играет, пока не кончится
    budget секунд настоящего времени."""

    def __init__(self, game, agent=None, key_interval=0.05, think=0.25, now=0.0, decide=None):
        self.game = game
        self.agent = agent
        self.decide = decide or (lambda view: agent.choose(view))
        self.key_interval, self.think = key_interval, think
        self.keys = []
        self.piece_no = -1
        self.ready_at = now          # когда можно нажать следующую клавишу
        self.last = now
        self.replans = 0
        self.paused = False
        self.waiting = False
        self.decision = None

    def _plan(self, now, replan=False):
        d = self.decide(P.observe(self.game))
        if d is None:                     # решение считается в потоке
            self.waiting = True
            return False
        self.waiting = False
        self.decision = d
        self.keys = list(d.path)
        if replan:
            self.replans += 1
        return True

    def deliver(self, decision, now):
        """Ответ потока для текущей фигуры."""
        if decision is not None and self.waiting:
            self.waiting = False
            self.decision = decision
            self.keys = list(decision.path)

    def _step(self, now):
        g = self.game
        if g.pieces != self.piece_no:
            self.piece_no = g.pieces
            self.keys = []
            self.decision = None
            self.ready_at = max(self.ready_at, now) + self.think
            self.waiting = False
            # думать начинает сразу (решение и «Мысли ИИ» готовы заранее), а клавиши
            # жмёт не раньше, чем пройдёт время на раздумье - отсюда предел фигур в секунду
            self._plan(now)
        if now < self.ready_at:
            return False
        if not self.keys:
            if self.waiting or not self._plan(now):
                return False
        key = self.keys.pop(0)
        before = g.pieces
        ok = g.press(key)
        if not ok and key != "hd":
            self.keys = []
            if g.pieces == before:
                self._plan(now, replan=True)
        self.ready_at = now + self.key_interval
        return True

    def tick(self, now, budget=0.0):
        if self.paused or self.game.over:
            self.last = now
            return
        if budget > 0:
            # максимум: без часов игры, пока не кончится время кадра
            import time
            end = time.perf_counter() + budget
            while not self.game.over and time.perf_counter() < end:
                self.ready_at = now
                if not self._step(now) and self.waiting:
                    break
            self.last = now
            return
        t = max(self.last, now - 1.0)    # после долгой паузы окна - не догонять больше секунды
        steps = 0
        while not self.game.over and steps < MAX_STEPS_PER_TICK:
            steps += 1
            step_at = max(self.ready_at, t)
            if step_at > now:
                break
            if self.game.gravity:
                self.game.update(step_at - t)
            t = step_at
            if not self._step(t) and (self.waiting or self.ready_at <= t):
                break
        if self.game.gravity and not self.game.over:
            self.game.update(now - t)
        self.last = now


class Duel:
    """Две партии; exchange() после каждого шага отправляет новый мусор сопернику."""

    def __init__(self, a, b):
        self.a, self.b = a, b
        self.sent = {"a": a.garbage_sent, "b": b.garbage_sent}

    def exchange(self):
        for side, g, other in (("a", self.a, self.b), ("b", self.b, self.a)):
            new = g.garbage_sent - self.sent[side]
            if new > 0:
                other.receive_garbage(new)
                self.sent[side] = g.garbage_sent

    def winner(self):
        if self.a.over and self.b.over:
            return "draw"
        if self.a.over:
            return "b"
        if self.b.over:
            return "a"
        return None
