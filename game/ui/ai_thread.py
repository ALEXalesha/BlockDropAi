"""Решения ИИ в отдельном потоке: окно не подвисает, даже когда сильный ИИ ищет крутки.

В поток уходит только View (то, что видит игрок). Запросы с номером (token): ответ на
устаревший запрос (фигура уже другая, партию начали заново) окно выбрасывает. Если
пришло несколько запросов, пока поток занят, считается только последний. Остановка -
флагом; shutdown() ждёт поток не дольше 2 секунд (контракт aikit).
"""
import queue
import threading

from PySide6.QtCore import QObject, Signal

from game.ai import player as P


class AiWorker(QObject):
    ready = Signal(object, object)          # token, Decision (или исключение)

    def __init__(self, agents, parent=None):
        """agents: {уровень: Agent}."""
        super().__init__(parent)
        self.agents = agents
        self.jobs = queue.Queue()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, name="ai", daemon=True)
        self.thread.start()

    def request(self, token, view, level):
        self.jobs.put((token, view, level))

    def _run(self):
        while not self.stop.is_set():
            try:
                job = self.jobs.get(timeout=0.1)
            except queue.Empty:
                continue
            while True:                       # только последний запрос
                try:
                    job = self.jobs.get_nowait()
                except queue.Empty:
                    break
            if job is None or self.stop.is_set():
                break
            token, view, level = job
            try:
                result = self.agents[level].choose(view)
            except Exception as e:  # noqa: BLE001 - ошибку покажет окно, поток не падает молча
                result = e
            if not self.stop.is_set():
                self.ready.emit(token, result)

    def shutdown(self, timeout=2.0):
        self.stop.set()
        self.jobs.put(None)
        self.thread.join(timeout)
        return not self.thread.is_alive()


def make_agents(model):
    from game.train import passport as PP
    return {lv: PP.level_agent(lv, model) for lv in PP.LEVELS}


__all__ = ["AiWorker", "make_agents", "P"]
