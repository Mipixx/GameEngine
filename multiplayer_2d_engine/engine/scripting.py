"""
Client scripting API (Roblox-like LocalScript)
Каждый скрипт — отдельный Python-файл с функциями-хуками:

    def start(game):                  # один раз при запуске
    def update(game, dt):             # каждый кадр
    def on_key(game, key):            # нажатие клавиши
    def on_chat(game, player_id, name, text):  # сообщение в чат
    def on_event(game, name, data):   # событие из сети / other scripts

API объекта `game` (см. GameContext ниже):
    game.players                 -> dict[id] = Player (локальное представление)
    game.local_player            -> Player | None
    game.objects                 -> список GameObject уровня
    game.send_move(x, y)         -> телепорт/движение (отправка серверу)
    game.set_speed(v)            -> скорость локального игрока
    game.teleport(x, y)          -> переместить локального игрока
    game.chat(text)              -> отправить сообщение в чат
    game.notify(text)            -> показать всплывающее сообщение
    game.play_sound(name)        -> запустить звук (beep/coin/hit)
    game.on_event(name, fn)      -> подписка на сетевое событие
    game.fire_event(name, data)  -> отправить событие всем игрокам
    game.time                    -> время с запуска (сек)
"""

import os
import sys
import time
import traceback
from typing import Callable, Dict, List, Optional


class ScriptError(Exception):
    pass


class GameContext:
    """Песочница/обёртка над движком, которую видят пользовательские скрипты."""

    def __init__(self, engine):
        self._engine = engine
        self.time: float = 0.0
        self._event_handlers: Dict[str, List[Callable]] = {}
        self._pending_events: List[tuple] = []   # (name, data) -> в сеть
        self._remote_events: List[tuple] = []    # (name, data) -> из сети

    # ---------- read-only shortcuts ----------
    @property
    def players(self):
        return self._engine.players

    @property
    def local_player(self):
        return self._engine.local_player

    @property
    def objects(self):
        return self._engine.game_objects

    @property
    def world_width(self):
        return self._engine.world_width

    @property
    def world_height(self):
        return self._engine.world_height

    # ---------- actions ----------
    def set_speed(self, value: float):
        if self._engine.local_player:
            self._engine.local_player.speed = float(value)

    def teleport(self, x: float, y: float):
        p = self._engine.local_player
        if p:
            p.x = max(0, min(float(x), self._engine.world_width))
            p.y = max(0, min(float(y), self._engine.world_height))

    def chat(self, text: str):
        self._engine.script_send_chat(str(text))

    def notify(self, text: str, duration: float = 3.0):
        self._engine.add_notification(str(text), duration)

    def play_sound(self, name: str):
        self._engine.play_sound(str(name))

    def on_event(self, event_name: str, handler: Callable):
        self._event_handlers.setdefault(event_name, []).append(handler)

    def fire_event(self, event_name: str, data=None):
        """Отправить сетевое событие всем игрокам."""
        self._pending_events.append((str(event_name), data))

    # ---------- internals used by engine ----------
    def _push_remote_event(self, name: str, data):
        self._remote_events.append((name, data))

    def _drain_pending_events(self) -> List[tuple]:
        out = self._pending_events[:]
        self._pending_events.clear()
        return out

    def _dispatch_remote_events(self):
        events, self._remote_events = self._remote_events, []
        for name, data in events:
            for handler in self._event_handlers.get(name, []):
                try:
                    handler(self, data)
                except Exception:
                    traceback.print_exc()


class ScriptManager:
    """Загружает и исполняет пользовательские скрипты из папки scripts/."""

    MAX_ERRORS_BEFORE_UNLOAD = 5

    def __init__(self, engine, scripts_dir: str = "scripts"):
        self.engine = engine
        self.scripts_dir = scripts_dir
        self.context = GameContext(engine)
        self.scripts: List[dict] = []   # {path, module, errors}
        self.reload_requested = False

    # ---------- loading ----------
    def load_all(self):
        os.makedirs(self.scripts_dir, exist_ok=True)
        for fname in sorted(os.listdir(self.scripts_dir)):
            if fname.endswith(".py") and not fname.startswith("_"):
                self.load(os.path.join(self.scripts_dir, fname))

    def load(self, path: str):
        name = os.path.splitext(os.path.basename(path))[0]
        try:
            namespace = {"__name__": f"script_{name}", "__file__": path}
            with open(path, "r", encoding="utf-8") as f:
                code = compile(f.read(), path, "exec")
            exec(code, namespace)
            self.scripts.append({
                "name": name,
                "path": path,
                "ns": namespace,
                "started": False,
                "errors": 0,
            })
            print(f"[scripts] loaded '{name}' from {path}")
        except Exception:
            print(f"[scripts] FAILED to load {path}:")
            traceback.print_exc()

    def reload_all(self):
        print("[scripts] reloading...")
        self.scripts.clear()
        self.context = GameContext(self.engine)
        self.engine.script_context = self.context
        self.load_all()
        self.engine.add_notification("Скрипты перезагрушены (F5)")

    # ---------- lifecycle ----------
    def _call(self, script, hook: str, *args):
        fn = script["ns"].get(hook)
        if callable(fn):
            try:
                fn(*args)
                script["errors"] = 0
            except Exception:
                script["errors"] += 1
                print(f"[scripts] error in {script['name']}.{hook}():")
                traceback.print_exc()
                if script["errors"] >= self.MAX_ERRORS_BEFORE_UNLOAD:
                    print(f"[scripts] '{script['name']}' unloaded after "
                          f"{script['errors']} errors")
                    script["ns"] = {}

    def start(self):
        self.context.time = time.time()
        for s in self.scripts:
            self._call(s, "start", self.context)
            s["started"] = True

    def update(self, dt: float):
        self.context.time = time.time() - getattr(self, "_t0", None) or 0.0
        if not hasattr(self, "_t0"):
            self._t0 = time.time()
            self.context.time = 0.0
        else:
            self.context.time = time.time() - self._t0

        for s in self.scripts:
            self._call(s, "update", self.context, dt)

        # dispatch incoming network events
        self.context._dispatch_remote_events()

        # send outgoing events
        for name, data in self.context._drain_pending_events():
            self.engine.script_fire_event(name, data)

    def on_key(self, key):
        for s in self.scripts:
            self._call(s, "on_key", self.context, key)

    def on_chat(self, player_id, name, text):
        for s in self.scripts:
            self._call(s, "on_chat", self.context, player_id, name, text)

    def on_network_event(self, name, data):
        self.context._push_remote_event(name, data)
