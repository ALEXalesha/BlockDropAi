"""Строки окна на русском и английском."""
from aikit.i18n import Translator

RU = {
    "app_title": "Блоки с ИИ",
    "app_sub": "Падающие блоки и ИИ, который сам научился в них играть",
    "mode": "Режим", "mode_solo": "Играю сам", "mode_ai": "Играет ИИ", "mode_duel": "Дуэль с ИИ",
    "level": "ИИ", "novice": "Новичок", "medium": "Средний", "strong": "Сильный",
    "play": "Играть", "stats": "Статистика", "settings": "Настройки", "menu": "В меню",
    "again": "Заново", "pause": "Пауза", "resume": "Дальше",
    "hint": "Подсказка", "thoughts": "Мысли ИИ",
    "thoughts_hint": "Контуры трёх лучших мест для фигуры по оценке ИИ; лучшее - ярче. "
                     "Числа - оценка поля после хода.",
    "speed": "Скорость", "speed_real": "Как человек", "speed_x3": "×3", "speed_x10": "×10",
    "speed_max": "Максимум",
    "next": "Дальше", "hold": "Hold", "score": "Очки", "lines": "Линии", "level_n": "Уровень",
    "pieces": "Фигур", "pps": "Фигур/с", "garbage": "Мусор",
    "you": "Вы", "ai_name": "ИИ: {level}",
    "game_over": "Игра окончена", "paused": "Пауза",
    "duel_win": "Вы победили!", "duel_loss": "ИИ победил", "duel_draw": "Ничья",
    "solo_text": "Клавиши - в настройках. Подсказка покажет, куда положил бы ИИ.",
    "ai_text": "ИИ играет сам: смотрит на поле, очередь и hold и жмёт клавиши.",
    "duel_text": "Линии отправляют сопернику мусорные ряды. ИИ не быстрее {pps} фигур в секунду.",
    "stats_title": "Статистика", "your_records": "Ваши рекорды", "ai_records": "Рекорды ИИ в окне",
    "col_mode": "Режим", "col_games": "Партий", "col_best_lines": "Лучшее по линиям",
    "col_best_score": "Лучшее по очкам", "col_wins": "Побед", "col_losses": "Поражений",
    "passport": "Паспорт модели", "not_ready": "Паспорт ещё не посчитан.",
    "passport_text": "{games} партий на уровень с зёрнами, партия до конца игры или до предела линий ({cap}) "
                     "(сильный ИИ иначе играет бесконечно). Обучение: метод перекрёстной энтропии, "
                     "{gens} поколений, {time}.",
    "col_level": "Уровень", "col_mean": "Среднее линий", "col_median": "Медиана",
    "col_capped": "До предела", "duels": "Дуэли уровней", "col_pair": "Пара", "col_result": "Счёт",
    "evolution": "Эволюция весов", "evolution_hint": "Среднее число линий популяции по поколениям "
                                                     "(обучение на укороченном поле).",
    "settings_title": "Настройки",
    "theme": "Тема", "dark": "Тёмная", "light": "Светлая", "language": "Язык",
    "colors": "Цвета фигур", "colors_classic": "Классические", "colors_pastel": "Пастель",
    "colors_mono": "Контраст",
    "das": "Задержка автоповтора", "das_hint": "Сколько держать клавишу сдвига до автоповтора: {ms} мс.",
    "arr": "Скорость автоповтора", "arr_hint": "Пауза между сдвигами при удержании: {ms} мс (0 - сразу до стены).",
    "start_level": "Начальный уровень", "ghost": "Тень фигуры",
    "volume": "Громкость", "keys": "Клавиши", "keys_hint": "Нажмите на клавишу и затем новую клавишу.",
    "press_key": "Нажмите клавишу…",
    "act_left": "Влево", "act_right": "Вправо", "act_soft": "Мягкое падение", "act_hard": "Сброс",
    "act_cw": "Поворот по часовой", "act_ccw": "Поворот против", "act_hold": "Hold", "act_pause": "Пауза",
    "saved_note": "Настройки сохраняются сразу.",
    "footer": "Блоки с ИИ {v} · PySide6 и numpy · MIT",
    "seconds": "{n} с", "minutes": "{n} мин", "hours": "{n} ч",
}

EN = {
    "app_title": "Block Drop AI",
    "app_sub": "Falling blocks and an AI that taught itself to play",
    "mode": "Mode", "mode_solo": "I play", "mode_ai": "AI plays", "mode_duel": "Duel vs AI",
    "level": "AI", "novice": "Novice", "medium": "Medium", "strong": "Strong",
    "play": "Play", "stats": "Statistics", "settings": "Settings", "menu": "Menu",
    "again": "Restart", "pause": "Pause", "resume": "Resume",
    "hint": "Hint", "thoughts": "AI thoughts",
    "thoughts_hint": "Outlines of the AI's three best spots for the piece; the best is brighter. "
                     "Numbers are the score of the board after the move.",
    "speed": "Speed", "speed_real": "Human-like", "speed_x3": "×3", "speed_x10": "×10",
    "speed_max": "Maximum",
    "next": "Next", "hold": "Hold", "score": "Score", "lines": "Lines", "level_n": "Level",
    "pieces": "Pieces", "pps": "Pieces/s", "garbage": "Garbage",
    "you": "You", "ai_name": "AI: {level}",
    "game_over": "Game over", "paused": "Paused",
    "duel_win": "You win!", "duel_loss": "The AI wins", "duel_draw": "Draw",
    "solo_text": "Keys are in Settings. Hint shows where the AI would put the piece.",
    "ai_text": "The AI plays by itself: it sees the board, the queue and hold, and presses keys.",
    "duel_text": "Cleared lines send garbage rows to the opponent. The AI places at most {pps} pieces per second.",
    "stats_title": "Statistics", "your_records": "Your records", "ai_records": "AI records in the window",
    "col_mode": "Mode", "col_games": "Games", "col_best_lines": "Best lines",
    "col_best_score": "Best score", "col_wins": "Wins", "col_losses": "Losses",
    "passport": "Model passport", "not_ready": "The passport has not been computed yet.",
    "passport_text": "{games} seeded games per level, each until game over or the line cap ({cap}) "
                     "(otherwise the strong AI plays forever). Training: cross-entropy method, "
                     "{gens} generations, {time}.",
    "col_level": "Level", "col_mean": "Mean lines", "col_median": "Median",
    "col_capped": "Hit the cap", "duels": "Level duels", "col_pair": "Pair", "col_result": "Score",
    "evolution": "Weight evolution", "evolution_hint": "Mean lines of the population per generation "
                                                      "(training on a shortened board).",
    "settings_title": "Settings",
    "theme": "Theme", "dark": "Dark", "light": "Light", "language": "Language",
    "colors": "Piece colors", "colors_classic": "Classic", "colors_pastel": "Pastel",
    "colors_mono": "High contrast",
    "das": "Auto-repeat delay", "das_hint": "How long to hold a shift key before auto-repeat: {ms} ms.",
    "arr": "Auto-repeat rate", "arr_hint": "Pause between repeated shifts: {ms} ms (0 means straight to the wall).",
    "start_level": "Starting level", "ghost": "Ghost piece",
    "volume": "Volume", "keys": "Keys", "keys_hint": "Click a key, then press the new key.",
    "press_key": "Press a key…",
    "act_left": "Left", "act_right": "Right", "act_soft": "Soft drop", "act_hard": "Hard drop",
    "act_cw": "Rotate clockwise", "act_ccw": "Rotate counter-clockwise", "act_hold": "Hold", "act_pause": "Pause",
    "saved_note": "Settings are saved at once.",
    "footer": "Block Drop AI {v} · PySide6 and numpy · MIT",
    "seconds": "{n} s", "minutes": "{n} min", "hours": "{n} h",
}


def translator(lang):
    return Translator({"ru": RU, "en": EN}, lang)
