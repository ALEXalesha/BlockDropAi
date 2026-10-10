"""Правила падающих блоков: поле, 7 фигур, мешок из 7, вращение SRS, hold, задержка
фиксации, линии, очки, уровни. Чистый Python, без Qt и numpy.

Поле - список из HEIGHT целых чисел, ряд 0 внизу. Бит x ряда - клетка в столбце x
(0 - левый). Видимы ряды 0..VISIBLE-1, выше - скрытые: там появляются фигуры.

Координаты фигуры (kind, rot, x, y) - левый нижний угол её рамки (3x3 у J L S T Z, 4x4 у
I и O). Ось y смотрит вверх, как в таблицах SRS. Повороты: 0 - как появилась, 1 - по
часовой (R), 2 - перевёрнута, 3 - против часовой (L).

Время игры - от часов: Game.update(dt) получает прошедшие секунды и сам делит их между
падением и задержкой фиксации. Сколько кадров ушло на эти секунды, не важно.
"""
import random

WIDTH = 10
VISIBLE = 20
HEIGHT = 40
FULL = (1 << WIDTH) - 1

KINDS = "IJLOSTZ"
I, J, L, O, S, T, Z = range(7)

# Клетки в повороте 0 (рамка, ось y вверх; верхний ряд рамки - y = n-1).
_SPAWN_CELLS = {
    I: (4, ((0, 2), (1, 2), (2, 2), (3, 2))),
    J: (3, ((0, 2), (0, 1), (1, 1), (2, 1))),
    L: (3, ((2, 2), (0, 1), (1, 1), (2, 1))),
    O: (4, ((1, 1), (2, 1), (1, 2), (2, 2))),
    S: (3, ((1, 2), (2, 2), (0, 1), (1, 1))),
    T: (3, ((1, 2), (0, 1), (1, 1), (2, 1))),
    Z: (3, ((0, 2), (1, 2), (1, 1), (2, 1))),
}


def _rotate_cw(cells, n):
    """Поворот по часовой внутри рамки n x n (ось y вверх): (x, y) -> (y, n-1-x)."""
    return tuple(sorted((y, n - 1 - x) for x, y in cells))


def _build_cells():
    table = {}
    for kind, (n, cells) in _SPAWN_CELLS.items():
        rots = [tuple(sorted(cells))]
        for _ in range(3):
            rots.append(rots[-1] if kind == O else _rotate_cw(rots[-1], n))
        table[kind] = tuple(rots)
    return table


CELLS = _build_cells()

# Смещения SRS (offset data) по поворотам 0, R, 2, L; ось y вверх. Сдвиги от стен
# считаются из них: сдвиг i при повороте a -> b = смещение[a][i] - смещение[b][i]. У I
# смещения содержат ещё и перенос центра вращения; он равен первому сдвигу и вычитается,
# потому что здесь фигура вращается внутри своей рамки 4x4.
_OFFSETS_JLSTZ = (
    ((0, 0), (0, 0), (0, 0), (0, 0), (0, 0)),
    ((0, 0), (1, 0), (1, -1), (0, 2), (1, 2)),
    ((0, 0), (0, 0), (0, 0), (0, 0), (0, 0)),
    ((0, 0), (-1, 0), (-1, -1), (0, 2), (-1, 2)),
)
_OFFSETS_I = (
    ((0, 0), (-1, 0), (2, 0), (-1, 0), (2, 0)),
    ((-1, 0), (0, 0), (0, 0), (0, 1), (0, -2)),
    ((-1, 1), (1, 1), (-2, 1), (1, 0), (-2, 0)),
    ((0, 1), (0, 1), (0, 1), (0, -1), (0, 2)),
)


def _kicks(offsets, a, b):
    raw = [(offsets[a][i][0] - offsets[b][i][0], offsets[a][i][1] - offsets[b][i][1]) for i in range(5)]
    bx, by = raw[0]
    return tuple((dx - bx, dy - by) for dx, dy in raw)


def kick_table(kind):
    """{(из, в): ((dx, dy), ...)} для поворотов на четверть в обе стороны."""
    if kind == O:
        return {(a, (a + d) % 4): ((0, 0),) for a in range(4) for d in (1, 3)}
    offsets = _OFFSETS_I if kind == I else _OFFSETS_JLSTZ
    return {(a, (a + d) % 4): _kicks(offsets, a, (a + d) % 4) for a in range(4) for d in (1, 3)}


KICKS = {kind: kick_table(kind) for kind in range(7)}


def _build_masks():
    """MASKS[kind][rot][x+3] = ((dy, маска ряда), ...) или None, если фигура при этом x
    вылезает за стены. Так проверка столкновения - пара операций с целыми."""
    masks = {}
    for kind in range(7):
        per_rot = []
        for rot in range(4):
            cells = CELLS[kind][rot]
            row = []
            for x in range(-3, WIDTH):
                if any(not 0 <= x + cx < WIDTH for cx, _ in cells):
                    row.append(None)
                    continue
                rows = {}
                for cx, cy in cells:
                    rows[cy] = rows.get(cy, 0) | (1 << (x + cx))
                row.append(tuple(sorted(rows.items())))
            per_rot.append(tuple(row))
        masks[kind] = tuple(per_rot)
    return masks


MASKS = _build_masks()

SPAWN_X = 3
SPAWN_Y = {I: 18, J: 19, L: 19, O: 19, S: 19, T: 19, Z: 19}

LOCK_DELAY = 0.5        # секунды на земле до фиксации
MAX_RESETS = 15         # сколько раз движение на земле откладывает фиксацию
SOFT_FACTOR = 20        # мягкое падение во столько раз быстрее
LINE_SCORES = (0, 100, 300, 500, 800)
LINES_PER_LEVEL = 10
PREVIEW = 5
GARBAGE_FOR = (0, 0, 1, 2, 4)   # сколько мусорных рядов отправляют 1-4 линии в дуэли


def gravity_interval(level):
    """Секунд на ряд при обычном падении (формула гайдлайна), не меньше 1/60 * 0.5."""
    level = max(1, level)
    return max((0.8 - (level - 1) * 0.007) ** (level - 1), 0.0005)


def fits(board, kind, rot, x, y):
    if not -3 <= x < WIDTH:
        return False
    m = MASKS[kind][rot][x + 3]
    if m is None:
        return False
    for dy, mask in m:
        r = y + dy
        if r < 0 or r >= HEIGHT or board[r] & mask:
            return False
    return True


def drop_distance(board, kind, rot, x, y):
    d = 0
    while fits(board, kind, rot, x, y - d - 1):
        d += 1
    return d


def try_rotate(board, kind, rot, x, y, direction):
    """Поворот с проверкой сдвигов SRS по порядку. direction: +1 по часовой, -1 против.
    Возвращает (rot, x, y, номер сдвига) или None."""
    to = (rot + direction) % 4
    for i, (dx, dy) in enumerate(KICKS[kind][(rot, to)]):
        if fits(board, kind, to, x + dx, y + dy):
            return to, x + dx, y + dy, i
    return None


def piece_cells(kind, rot, x, y):
    return [(x + cx, y + cy) for cx, cy in CELLS[kind][rot]]


def lock(board, kind, rot, x, y):
    """Поставить фигуру и убрать полные ряды. Возвращает (новое поле, номера убранных
    рядов снизу вверх - по полю до очистки)."""
    b = list(board)
    rows = []
    for dy, mask in MASKS[kind][rot][x + 3]:
        r = y + dy
        b[r] |= mask
        if b[r] == FULL:
            rows.append(r)
    if rows:
        b = [row for row in b if row != FULL]
        b.extend([0] * len(rows))
    return b, rows


def spawn_state(board, kind):
    """Где появляется фигура: (rot, x, y) или None, если места нет. Появившись, фигура
    сразу опускается на ряд, если может (гайдлайн)."""
    y = SPAWN_Y[kind]
    if not fits(board, kind, 0, SPAWN_X, y):
        return None
    if fits(board, kind, 0, SPAWN_X, y - 1):
        y -= 1
    return 0, SPAWN_X, y


_LOW = {(k, r): min(cy for _, cy in CELLS[k][r]) for k in range(7) for r in range(4)}


def locks_out(kind, rot, y):
    """Фигура целиком выше видимого поля - конец игры (lock out)."""
    return y + _LOW[kind, rot] >= VISIBLE


def stack_height(board):
    for r in range(HEIGHT - 1, -1, -1):
        if board[r]:
            return r + 1
    return 0


class Bag:
    """Мешок из 7: каждые 7 фигур подряд - все разные, порядок случайный."""

    def __init__(self, seed=None):
        self.rng = random.Random(seed)
        self.pool = []

    def next(self):
        if not self.pool:
            self.pool = list(range(7))
            self.rng.shuffle(self.pool)
            self.pool.reverse()
        return self.pool.pop()


class Game:
    """Партия одного игрока. Ввод - методы move/rotate/soft_drop/hard_drop/hold, время -
    update(dt). События для окна копятся в self.events: ("lock", линий, вид, поворот, x, y),
    ("clear", ряды), ("garbage", рядов), ("over",), ("hold",)."""

    def __init__(self, seed=None, level=1, gravity=True):
        self.board = [0] * HEIGHT
        self.bag = Bag(seed)
        self.queue = [self.bag.next() for _ in range(PREVIEW + 1)]
        self.hold_kind = None
        self.hold_used = False
        self.start_level = level
        self.level = level
        self.score = 0
        self.lines = 0
        self.pieces = 0
        self.cleared = [0, 0, 0, 0, 0]
        self.over = False
        self.gravity = gravity
        self.soft = False
        self.events = []
        self.garbage_sent = 0
        self.garbage_rows = 0           # сколько мусорных рядов встало на поле
        self.pending_garbage = []       # [(рядов, дырка)], приходят при фиксации без линий
        self.garbage_rng = random.Random(None if seed is None else seed * 7919 + 1)
        self.kind = None
        self._spawn(self._take())

    # --- очередь и появление ---

    def _take(self):
        kind = self.queue.pop(0)
        self.queue.append(self.bag.next())
        return kind

    def _spawn(self, kind):
        self.kind = kind
        self.fall_acc = 0.0
        self.lock_timer = 0.0
        self.resets = 0
        st = spawn_state(self.board, kind)
        if st is None:
            self.rot, self.x, self.y = 0, SPAWN_X, SPAWN_Y[kind]
            self._game_over()
            return
        self.rot, self.x, self.y = st
        self.lowest = self.y

    def _game_over(self):
        self.over = True
        self.events.append(("over",))

    # --- состояние фигуры ---

    def grounded(self):
        return not fits(self.board, self.kind, self.rot, self.x, self.y - 1)

    def ghost_y(self):
        return self.y - drop_distance(self.board, self.kind, self.rot, self.x, self.y)

    def piece(self):
        return self.kind, self.rot, self.x, self.y

    def _moved(self):
        """После удачного сдвига или поворота: на земле фигура получает новые полсекунды,
        но не больше MAX_RESETS раз на одной высоте."""
        if self.y < self.lowest:
            self.lowest = self.y
            self.resets = 0
        if self.grounded():
            if self.resets < MAX_RESETS:
                self.resets += 1
                self.lock_timer = 0.0
            else:
                self._lock()
        else:
            self.lock_timer = 0.0

    # --- ввод ---

    def move(self, dx):
        if self.over or not fits(self.board, self.kind, self.rot, self.x + dx, self.y):
            return False
        self.x += dx
        self._moved()
        return True

    def rotate(self, direction):
        if self.over:
            return False
        r = try_rotate(self.board, self.kind, self.rot, self.x, self.y, direction)
        if r is None:
            return False
        self.rot, self.x, self.y, _ = r
        self._moved()
        return True

    def soft_drop(self):
        """Опустить на ряд (одно нажатие мягкого падения): +1 очко."""
        if self.over or self.grounded():
            return False
        self.y -= 1
        self.score += 1
        self.fall_acc = 0.0
        if self.y < self.lowest:
            self.lowest = self.y
            self.resets = 0
        return True

    def hard_drop(self):
        if self.over:
            return 0
        d = drop_distance(self.board, self.kind, self.rot, self.x, self.y)
        self.y -= d
        self.score += 2 * d
        return self._lock()

    def hold(self):
        if self.over or self.hold_used:
            return False
        held = self.hold_kind
        self.hold_kind = self.kind
        self.hold_used = True
        self.events.append(("hold",))
        self._spawn(held if held is not None else self._take())
        return True

    def set_soft(self, on):
        self.soft = bool(on)

    def press(self, key):
        """Нажатие по имени - так играет ИИ: 'L', 'R', 'cw', 'ccw', 'sd', 'hd', 'hold'."""
        if key == "L":
            return self.move(-1)
        if key == "R":
            return self.move(1)
        if key == "cw":
            return self.rotate(1)
        if key == "ccw":
            return self.rotate(-1)
        if key == "sd":
            return self.soft_drop()
        if key == "hd":
            self.hard_drop()
            return True
        if key == "hold":
            return self.hold()
        raise ValueError(f"неизвестная клавиша {key!r}")

    # --- время ---

    def interval(self):
        base = gravity_interval(self.level)
        return base / SOFT_FACTOR if self.soft else base

    def update(self, dt):
        """Прошло dt секунд по часам. Время делится между падением и задержкой фиксации
        точно, без шага кадра: 1 раз по секунде и 64 раза по 1/64 дают одно и то же."""
        t = float(dt)
        while t > 0 and not self.over:
            if self.grounded():
                need = LOCK_DELAY - self.lock_timer
                if t >= need:
                    t -= need
                    self._lock()
                else:
                    self.lock_timer += t
                    t = 0.0
            elif not self.gravity:
                return
            else:
                interval = self.interval()
                need = interval - self.fall_acc
                if t >= need:
                    t -= need
                    self.fall_acc = 0.0
                    self.y -= 1
                    if self.soft:
                        self.score += 1
                    if self.y < self.lowest:
                        self.lowest = self.y
                        self.resets = 0
                else:
                    self.fall_acc += t
                    t = 0.0

    # --- фиксация ---

    def _lock(self):
        kind, rot, x, y = self.kind, self.rot, self.x, self.y
        out = locks_out(kind, rot, y)
        self.board, rows = lock(self.board, kind, rot, x, y)
        n = len(rows)
        self.pieces += 1
        self.cleared[n] += 1
        self.lines += n
        self.score += LINE_SCORES[n] * self.level
        self.level = self.start_level + self.lines // LINES_PER_LEVEL
        self.hold_used = False
        self.events.append(("lock", n, kind, rot, x, y))
        if n:
            self.events.append(("clear", tuple(rows)))
            self.garbage_sent += GARBAGE_FOR[n]
            self._cancel_garbage(GARBAGE_FOR[n])
        else:
            self._apply_garbage()
        if out and not n:
            self._game_over()
            return n
        if not self.over:
            self._spawn(self._take())
        return n

    # --- мусор (дуэль) ---

    def receive_garbage(self, count):
        """Соперник прислал count рядов: они встанут снизу при следующей фиксации без линий."""
        if count > 0:
            self.pending_garbage.append((count, self.garbage_rng.randrange(WIDTH)))

    def _cancel_garbage(self, count):
        while count > 0 and self.pending_garbage:
            n, hole = self.pending_garbage[0]
            take = min(n, count)
            count -= take
            if take == n:
                self.pending_garbage.pop(0)
            else:
                self.pending_garbage[0] = (n - take, hole)

    def pending(self):
        return sum(n for n, _ in self.pending_garbage)

    def _apply_garbage(self):
        while self.pending_garbage:
            n, hole = self.pending_garbage.pop(0)
            self.add_garbage(n, hole)
            if self.over:
                return

    def add_garbage(self, n, hole):
        """Поднять поле на n рядов, снизу - полные ряды с дыркой в столбце hole."""
        if any(self.board[HEIGHT - n:]):
            self._game_over()
            return
        row = FULL & ~(1 << hole)
        self.board = [row] * n + self.board[:HEIGHT - n]
        self.garbage_rows += n
        self.events.append(("garbage", n))
