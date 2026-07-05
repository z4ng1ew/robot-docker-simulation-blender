# -*- coding: utf-8 -*-
"""
engine.py — слой совместимости с SimPy.

Если библиотека `simpy` установлена (входит в перечень допустимого ПО хакатона),
используется она. Если нет — включается встроенный мини-движок дискретно-событийного
моделирования (DES) на стандартной библиотеке Python с тем же интерфейсом
в используемом подмножестве:

    env = Environment()
    env.process(generator)
    env.timeout(delay)
    env.event() -> .succeed(value) / yield
    env.run(until=T)
    env.now

Семантика идентична SimPy для этого подмножества (FIFO-порядок при равном времени),
поэтому результаты воспроизводимы в обеих средах.
"""

try:  # pragma: no cover
    import simpy  # type: ignore

    Environment = simpy.Environment
    BACKEND = "simpy %s" % getattr(simpy, "__version__", "?")

except ImportError:  # ---- встроенный мини-движок ----
    import heapq
    from itertools import count

    BACKEND = "builtin-minides"

    class _Event:
        __slots__ = ("env", "callbacks", "triggered", "value")

        def __init__(self, env):
            self.env = env
            self.callbacks = []
            self.triggered = False
            self.value = None

        def succeed(self, value=None):
            if self.triggered:
                raise RuntimeError("event already triggered")
            self.triggered = True
            self.value = value
            self.env._schedule(0.0, self)
            return self

    class _Timeout(_Event):
        __slots__ = ()

        def __init__(self, env, delay, value=None):
            super().__init__(env)
            self.triggered = True
            self.value = value
            env._schedule(delay, self)

    class _Process(_Event):
        __slots__ = ("gen",)

        def __init__(self, env, gen):
            super().__init__(env)
            self.gen = gen
            # старт процесса — немедленное событие
            boot = _Event(env)
            boot.triggered = True
            boot.callbacks.append(self._resume)
            env._schedule(0.0, boot)

        def _resume(self, ev):
            try:
                target = self.gen.send(ev.value)
            except StopIteration as si:
                if not self.triggered:
                    self.triggered = True
                    self.value = getattr(si, "value", None)
                    self.env._schedule(0.0, self)
                return
            if not isinstance(target, _Event):
                raise TypeError("process yielded non-event: %r" % (target,))
            target.callbacks.append(self._resume)

    class Environment:
        def __init__(self):
            self._q = []
            self._ids = count()
            self.now = 0.0

        # --- API, совместимый с SimPy ---
        def timeout(self, delay, value=None):
            if delay < 0:
                raise ValueError("negative delay")
            return _Timeout(self, float(delay), value)

        def event(self):
            return _Event(self)

        def process(self, gen):
            return _Process(self, gen)

        def run(self, until=None):
            q = self._q
            if until is None:
                until = float("inf")
            while q:
                t, _, ev = q[0]
                if t > until:
                    break
                heapq.heappop(q)
                self.now = t
                cbs, ev.callbacks = ev.callbacks, []
                for cb in cbs:
                    cb(ev)
            if until != float("inf"):
                self.now = until

        # --- внутреннее ---
        def _schedule(self, delay, ev):
            heapq.heappush(self._q, (self.now + delay, next(self._ids), ev))


# ---------------------------------------------------------------------------
# Общие примитивы поверх Environment (работают и с simpy, и с мини-движком).
# Реализованы сами, чтобы не зависеть от simpy.Resource/Store и иметь
# полностью одинаковую семантику в обеих средах.
# ---------------------------------------------------------------------------

class Slot:
    """Ресурс с ёмкостью capacity и очередью FIFO (аналог simpy.Resource).

    Использование:
        yield slot.acquire()
        ...
        slot.release()
    """

    __slots__ = ("env", "capacity", "busy", "queue")

    def __init__(self, env, capacity=1):
        self.env = env
        self.capacity = capacity
        self.busy = 0
        self.queue = []

    def acquire(self):
        ev = self.env.event()
        if self.busy < self.capacity:
            self.busy += 1
            ev.succeed()
        else:
            self.queue.append(ev)
        return ev

    def release(self):
        # capacity могла быть уменьшена на лету (сценарии отказов):
        # тогда освобождение «поглощается» до возврата в норму.
        if self.busy > self.capacity:
            self.busy -= 1
        elif self.queue:
            ev = self.queue.pop(0)
            ev.succeed()
        else:
            self.busy -= 1

    def set_capacity(self, new_cap):
        """Изменение ёмкости на лету; при росте будим ожидающих."""
        self.capacity = new_cap
        while self.queue and self.busy < self.capacity:
            self.busy += 1
            self.queue.pop(0).succeed()

    @property
    def qlen(self):
        return len(self.queue)


class Buffer:
    """Очередь предметов с блокирующим получением (аналог simpy.Store)."""

    __slots__ = ("env", "items", "getters")

    def __init__(self, env):
        self.env = env
        self.items = []
        self.getters = []

    def put(self, item):
        if self.getters:
            ev = self.getters.pop(0)
            ev.succeed(item)
        else:
            self.items.append(item)

    def get(self):
        ev = self.env.event()
        if self.items:
            ev.succeed(self.items.pop(0))
        else:
            self.getters.append(ev)
        return ev

    def __len__(self):
        return len(self.items)
