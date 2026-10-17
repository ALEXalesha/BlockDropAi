# Мутанты для tools/mutate.py: (имя, файл, было, стало, проверки).
E = "game/core/blocks.py"
TB = "tests/test_blocks.py"
MUTANTS = [
    ("rules: I без переноса центра", E, "return tuple((dx - bx, dy - by) for dx, dy in raw)",
     "return tuple(raw)", TB),
    ("rules: смещение R неверно", E, "((0, 0), (1, 0), (1, -1), (0, 2), (1, 2)),",
     "((0, 0), (1, 0), (1, 1), (0, 2), (1, 2)),", TB),
    ("rules: поворот не туда", E, "return tuple(sorted((y, n - 1 - x) for x, y in cells))",
     "return tuple(sorted((n - 1 - y, x) for x, y in cells))", TB),
    ("rules: без сдвигов от стен", E, "for i, (dx, dy) in enumerate(KICKS[kind][(rot, to)]):",
     "for i, (dx, dy) in enumerate(KICKS[kind][(rot, to)][:1]):", TB),
    ("rules: сдвиги с конца", E, "for i, (dx, dy) in enumerate(KICKS[kind][(rot, to)]):",
     "for i, (dx, dy) in reversed(list(enumerate(KICKS[kind][(rot, to)]))):", TB),
    ("rules: мешок не мешок", E, "self.pool = list(range(7))",
     "self.pool = [self.rng.randrange(7) for _ in range(7)]", TB),
    ("rules: ряд не очищается", E, "        if b[r] == FULL:\n", "        if b[r] == FULL - 1:\n", TB),
    ("rules: очки за четыре", E, "LINE_SCORES = (0, 100, 300, 500, 800)",
     "LINE_SCORES = (0, 100, 300, 500, 1200)", TB),
    ("rules: уровень не растёт", E, "self.level = self.start_level + self.lines // LINES_PER_LEVEL",
     "self.level = self.start_level", TB),
    ("rules: hold без ограничения", E, "if self.over or self.hold_used:", "if self.over:", TB),
    ("rules: hold не возвращается", E, "        self.hold_used = False\n        self.events.append((\"lock\", n, kind, rot, x, y))",
     "        self.events.append((\"lock\", n, kind, rot, x, y))", TB),
    ("rules: задержка не копится", E, "need = LOCK_DELAY - self.lock_timer", "need = LOCK_DELAY", TB),
    ("rules: бесконечные отсрочки", E, "if self.resets < MAX_RESETS:", "if True:", TB),
    ("rules: время от кадров", E,
     "                if t >= need:\n                    t -= need\n                    self.fall_acc = 0.0",
     "                if t >= need:\n                    t = 0.0\n                    self.fall_acc = 0.0", TB),
    ("rules: нет конца при появлении", E,
     "    if not fits(board, kind, 0, SPAWN_X, y):\n        return None", "    if False:\n        return None", TB),
    ("rules: линии не гасят мусор", E, "self._cancel_garbage(GARBAGE_FOR[n])", "pass", TB),
    ("rules: четыре линии шлют три", E, "GARBAGE_FOR = (0, 0, 1, 2, 4)", "GARBAGE_FOR = (0, 0, 1, 2, 3)", TB),
    ("rules: жёсткое падение по 1", E, "self.score += 2 * d", "self.score += d", TB),
    ("rules: скорость уровня", E, "return max((0.8 - (level - 1) * 0.007) ** (level - 1), 0.0005)",
     "return max((0.8 - (level - 1) * 0.007) ** level, 0.0005)", TB),
    ("rules: пол дырявый", E, "if r < 0 or r >= HEIGHT or board[r] & mask:",
     "if r >= HEIGHT or board[r] & mask:", TB),
    ("rules: мусор без дырки", E, "row = FULL & ~(1 << hole)", "row = FULL", TB),
]
MV = "game/ai/moves.py"
TM = "tests/test_moves.py"
MUTANTS += [
    ("moves: без поворота против часовой", MV, "for d, key in ((1, \"cw\"), (-1, \"ccw\")):",
     "for d, key in ((1, \"cw\"),):", TM),
    ("moves: небо до пола", MV, "down = bottom - sky if bottom > sky else 1", "down = y - fy", TM),
    ("moves: без мягкого падения ниже неба", MV, "down = bottom - sky if bottom > sky else 1",
     "down = bottom - sky if bottom > sky else 0", TM),
    ("moves: сброс без сдвига вправо", MV, "for step, key in ((0, None), (-1, \"L\"), (1, \"R\")):",
     "for step, key in ((0, None), (-1, \"L\")):", TM),
    ("moves: ключ по повороту", MV, "return tuple((y + dy, m) for dy, m in B.MASKS[kind][rot][x + 3])",
     "return (rot,) + tuple((y + dy, m) for dy, m in B.MASKS[kind][rot][x + 3])", TM),
    ("moves: путь без сдвигов", MV, "rot_path + shifts + (\"hd\",)", "rot_path + (\"hd\",)", TM),
]
FT = "game/ai/features.py"
TF = "tests/test_features.py"
MUTANTS += [
    ("features: дыры без накрытия", FT, "        h = covered & ~row\n", "        h = ~row & FULL & covered >> 1\n", TF),
    ("features: колодец и под накрытием", FT, "& FULL & ~covered", "& FULL", TF),
    ("features: глубина колодца не растёт", FT, "            c1, carry = c1 ^ carry, c1 & carry\n",
     "            c1, carry = c1, 0\n", TF),
    ("features: столбец над стопкой", FT, "    ct += prev.bit_count()              # над стопкой пусто\n", "", TF),
    ("features: верх по фигуре", FT, "top = _top(after, min(max(hi + 1, top), B.HEIGHT))",
     "top = _top(after, min(hi + 1, B.HEIGHT))", TF),
    ("features: эрозия без линий", FT, "        eroded *= n\n", "", TF),
    ("features: сброс по нижней клетке", FT, "                v = heights[col] - low\n",
     "                v = heights[col] - low - 1\n", TF),
]
C = "game/train/cem.py"
TC = "tests/test_cem.py"
MUTANTS += [
    ("cem: лучшие - худшие", C, "order = np.argsort(-fitness, kind=\"stable\")",
     "order = np.argsort(fitness, kind=\"stable\")", TC),
    ("cem: среднее не обновляется", C, "        self.mean = elite.mean(axis=0)\n", "", TC),
    ("cem: снимок без поколения", C, "        self.gen = snap[\"gen\"]\n", "", TC),
    ("cem: работник в 8 потоков", C, "        os.environ[var] = \"1\"", "        os.environ[var] = \"8\"", TC),
]
TDF = "game/train/td.py"
TT = "tests/test_td.py"
MUTANTS += [
    ("td: цель без награды", TDF, "target = r + self.gamma * np.where(done, 0.0, self.net.predict(xn))",
     "target = self.gamma * np.where(done, 0.0, self.net.predict(xn))", TT),
    ("td: ход по худшему", TDF, "else int(np.argmax(q))", "else int(np.argmin(q))", TT),
    ("td: шаг обучения не делается", TDF, "            self.adam.step()\n", "", TT),
    ("td: снимок без Adam", TDF, "        self.adam.t = meta[\"adam_t\"]\n", "", TT),
]
SE = "game/ui/session.py"
TS = "tests/test_session.py"
TU = "tests/test_ui.py"
MUTANTS += [
    ("session: думает только после паузы", SE, "            self._plan(now)\n        if now < self.ready_at:",
     "        if now < self.ready_at:", TU + " -k thoughts_visible"),
    ("session: задержка автоповтора вдвое короче", SE, "        if held_for < self.das:",
     "        if held_for < self.das / 2:", TS),
    ("session: ARR 0 по одному", SE, "            return B.WIDTH + 1                   # мгновенно до стены",
     "            return 1", TS),
    ("session: ИИ без предела скорости", SE, "            self.ready_at = max(self.ready_at, now) + self.think",
     "            self.ready_at = max(self.ready_at, now)", TS),
    ("session: мусор не уходит", SE, "                other.receive_garbage(new)", "                pass", TS),
    ("session: без перепланирования", SE, "                self._plan(now, replan=True)", "                pass", TS),
    ("ui: подсказка остаётся у следующей фигуры", "game/ui/widget.py",
     "        self.seen_pieces = [g.pieces for g in self.games]\n        self.timer.start()",
     "        self.seen_pieces = None\n        self.timer.start()", TU + " -k before_first_tick"),
]

# графики статистики (aikit.charts)
W = "game/ui/widget.py"
TSC = "tests/test_stats_charts.py"
MUTANTS += [
    ("charts: дуэль не в журнале", W, '            self.history.record({"mode": "duel"', '            ({"mode": "duel"', TSC),
    ("charts: одиночная не в журнале", W, '                self.history.record({"mode": "solo"', '                ({"mode": "solo"', TSC),
    ("charts: одиночные в доле побед", W, 'enumerate(x for x in games if x.get("mode") == "duel")]', 'enumerate(games)]', TSC),
    ("charts: рекорд одиночной не копится", W, '        c.set_points(gamelog.series(solo, "score"), gamelog.best_curve(solo, "score"))',
     '        c.set_points(gamelog.series(solo, "score"), gamelog.series(solo, "score"))', TSC),
    ("charts: одиночная под паспортом одна", W,
     "        items.append(items.pop([c for c, _ in items].index(self.charts.passport)))", "        pass", TSC + " -k passport_is_last"),
]

# стартовое меню, боковая панель в его стиле, настройки на всю ширину (автор 17.10)
MN = "game/ui/menu.py"
TM = "tests/test_menu.py"
WU = "game/ui/widget.py"
MUTANTS += [
    ("menu: фигуры на кнопках", MN, "        self.lanes = (m * 0.5, left - gap, left + w + gap, self.width() - m * 0.5)",
     "        self.lanes = (m * 0.5, left + w, left, self.width() - m * 0.5)", TM + " -k keep_off"),
    ("menu: фигуры за краем", MN, "            x = z0 + c * 0.25 + lane * (z1 - z0 - c * 4.5)",
     "            x = z0 + c * 0.25 + lane * (z1 - z0)", TM + " -k keep_off"),
    ("menu: узкая полоса без фигур не пропускается", MN, "if z[1] - z[0] >= c * 4.5]", "if z[1] - z[0] >= 0]",
     TM + " -k 'keep_off or narrow'"),
    ("menu: не растёт на 4K", MN, "        return round(max(1.0, min(2.4, w / 1280, h / 800)), 2)", "        return 1.0",
     TM + " -k scales"),
    ("menu: колонка шире окна", MN, "        return round(min(620 * self.scale, max(520, self.width() * 0.6)))",
     "        return round(620 * self.scale * 1.5)", TM + " -k whole"),
    # «пилюли уже текста» не мутируется: пилюля жирная и выбранной, и невыбранной, ширину ей даёт
    # сам Qt по шрифту из таблицы стилей - fit_segments тут лишь запас, мутант был бы равносильным.
    ("menu: боковая панель общего вида", WU, "        self.play.side.setStyleSheet(side_qss(arc))", "        pass",
     TM + " -k side_panel"),
    ("menu: стакан в общих цветах", WU, "            c.set_theme(board_palette(pal, self.ctx.theme), self.settings[\"colors\"])",
     "            c.set_theme(pal, self.settings[\"colors\"])", TM + " -k side_panel"),
    ("menu: заголовок не прописными", MN, '        self.title.setText(t("app_title").upper())',
     '        self.title.setText(t("app_title"))', TM + " -k own_style"),
]
