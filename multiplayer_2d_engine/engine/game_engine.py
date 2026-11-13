"""
2D Top-Down Multiplayer Game Engine
Core engine module with networking support
"""

import pygame
import asyncio
import math
import websockets
import json
import threading
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum

try:
    from engine.scripting import ScriptManager
except ImportError:  # запуск напрямую из папки engine/
    from scripting import ScriptManager


class MessageType(Enum):
    PLAYER_JOIN = "player_join"
    PLAYER_LEAVE = "player_leave"
    PLAYER_MOVE = "player_move"
    PLAYER_UPDATE = "player_update"
    GAME_STATE = "game_state"
    CHAT_MESSAGE = "chat_message"


@dataclass
class Player:
    id: str
    x: float
    y: float
    color: Tuple[int, int, int]
    name: str
    speed: float = 200.0
    hp: float = 100.0
    max_hp: float = 100.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "x": self.x,
            "y": self.y,
            "color": self.color,
            "name": self.name,
            "speed": self.speed,
            "hp": self.hp,
            "max_hp": self.max_hp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Player':
        return cls(
            id=data["id"],
            x=data["x"],
            y=data["y"],
            color=tuple(data["color"]),
            name=data["name"],
            speed=data.get("speed", 200.0),
            hp=data.get("hp", 100.0),
            max_hp=data.get("max_hp", 100.0),
        )


@dataclass
class GameObject:
    id: str
    x: float
    y: float
    width: float
    height: float
    object_type: str
    properties: dict
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'GameObject':
        return cls(**data)


class NetworkClient:
    """Client for multiplayer networking"""
    
    def __init__(self, host: str = "localhost", port: int = 8765):
        self.host = host
        self.port = port
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.connected = False
        self.player_id: Optional[str] = None
        self.message_queue: asyncio.Queue = asyncio.Queue()
        self.players: Dict[str, Player] = {}
        self.game_objects: Dict[str, GameObject] = {}
        
    async def connect(self, player_name: str) -> bool:
        try:
            uri = f"ws://{self.host}:{self.port}"
            self.websocket = await websockets.connect(uri)
            self.connected = True
            
            # Send join message
            join_msg = {
                "type": MessageType.PLAYER_JOIN.value,
                "name": player_name
            }
            await self.websocket.send(json.dumps(join_msg))
            
            # Receive player ID
            response = await self.websocket.recv()
            data = json.loads(response)
            if data["type"] == "player_id":
                self.player_id = data["id"]
                print(f"Connected as player {self.player_id}")
                
                # Create local player immediately with spawn position
                self.players[self.player_id] = Player(
                    id=self.player_id,
                    x=1000.0,  # Spawn position (same as server)
                    y=1000.0,
                    color=(0, 255, 0),
                    name=player_name
                )
                return True
            return False
        except Exception as e:
            print(f"Connection error: {e}")
            self.connected = False
            return False
    
    async def send_message(self, message: dict):
        if self.connected and self.websocket:
            await self.websocket.send(json.dumps(message))
    
    async def receive_messages(self):
        """Continuously receive messages from server (non-blocking)"""
        if not self.connected or not self.websocket:
            return
        
        try:
            # Try to receive with a short timeout
            message = await asyncio.wait_for(
                self.websocket.recv(),
                timeout=0.001
            )
            data = json.loads(message)
            await self.message_queue.put(data)
        except asyncio.TimeoutError:
            pass  # No message available
        except websockets.exceptions.ConnectionClosed:
            self.connected = False
            print("Disconnected from server")
        except Exception as e:
            print(f"Receive error: {e}")
    
    async def process_messages(self):
        """Process messages from the queue"""
        while not self.message_queue.empty():
            msg = await self.message_queue.get()
            msg_type = msg.get("type")
            
            if msg_type == MessageType.PLAYER_UPDATE.value:
                players_data = msg.get("players", {})
                self.players = {pid: Player.from_dict(pdata) for pid, pdata in players_data.items()}
            
            elif msg_type == MessageType.GAME_STATE.value:
                objects_data = msg.get("objects", {})
                self.game_objects = {oid: GameObject.from_dict(odata) for oid, odata in objects_data.items()}
                
                players_data = msg.get("players", {})
                self.players = {pid: Player.from_dict(pdata) for pid, pdata in players_data.items()}
            
            elif msg_type == MessageType.PLAYER_LEAVE.value:
                player_id = msg.get("player_id")
                if player_id in self.players:
                    del self.players[player_id]

            elif msg_type == MessageType.CHAT_MESSAGE.value:
                await self.message_queue.put(
                    {"type": "_chat_local",
                     "name": msg.get("name", "?"),
                     "message": msg.get("message", ""),
                     "player_id": msg.get("player_id")})

            elif msg_type == "script_event":
                await self.message_queue.put(
                    {"type": "_script_event_local",
                     "event": msg.get("event"),
                     "data": msg.get("data")})

            elif msg_type == "spawn_point":
                self.spawn_override = (msg.get("x", 1000.0), msg.get("y", 1000.0))
    
    async def send_move(self, x: float, y: float):
        if self.player_id:
            await self.send_message({
                "type": MessageType.PLAYER_MOVE.value,
                "player_id": self.player_id,
                "x": x,
                "y": y
            })
    
    async def disconnect(self):
        if self.websocket:
            await self.websocket.close()
        self.connected = False


class GameEngine:
    """Main game engine class"""
    
    def __init__(self, screen_width: int = 1280, screen_height: int = 720, title: str = "2D Multiplayer Game"):
        pygame.init()
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.screen = pygame.display.set_mode((screen_width, screen_height))
        pygame.display.set_caption(title)
        self.clock = pygame.time.Clock()
        self.running = False
        self.fps = 60
        
        # Game state
        self.players: Dict[str, Player] = {}
        self.game_objects: List[GameObject] = []
        self.local_player: Optional[Player] = None
        
        # Networking
        self.network_client: Optional[NetworkClient] = None
        self.is_multiplayer = False
        
        # Camera
        self.camera_x = 0
        self.camera_y = 0
        
        # Input
        self.keys_pressed = set()
        
        # World size
        self.world_width = 2000
        self.world_height = 2000

        # ===== Roblox-like features =====
        # Chat
        self.chat_active = False
        self.chat_input = ""
        self.chat_log: List[dict] = []          # {name, text, time}
        self.chat_font = pygame.font.Font(None, 22)

        # Damage popups / notifications / particles
        self.popups: List[dict] = []            # floating texts
        self.notifications: List[dict] = []     # center toasts
        self.particles: List[dict] = []

        # Physics / collision
        self.gravity = 0.0                      # px/s^2 (для platformer-режимов)
        self.jump_velocity = -350.0
        self.player_radius = 20

        # Sounds (synthesized)
        self.sounds_enabled = True
        self._sound_cache: dict = {}

        # Scripting (LocalScripts)
        self.script_manager = ScriptManager(self, scripts_dir="scripts")
        self.script_context = self.script_manager.context

        # Server-provided spawn point
        self.spawn_point = (1000.0, 1000.0)
        
    def set_multiplayer(self, host: str = "localhost", port: int = 8765, player_name: str = "Player"):
        """Enable multiplayer mode"""
        self.network_client = NetworkClient(host, port)
        self.is_multiplayer = True
        self.player_name = player_name
        
    async def connect_to_server(self) -> bool:
        """Connect to multiplayer server"""
        if self.network_client:
            connected = await self.network_client.connect(self.player_name)
            if connected:
                # Get player position from network client (already set there)
                network_player = self.network_client.players.get(self.network_client.player_id)
                spawn_x = network_player.x if network_player else self.world_width // 2
                spawn_y = network_player.y if network_player else self.world_height // 2
                
                # Create local player with position from server
                self.local_player = Player(
                    id=self.network_client.player_id,
                    x=spawn_x,
                    y=spawn_y,
                    color=(0, 255, 0),
                    name=self.player_name
                )
                self.players[self.local_player.id] = self.local_player
            return connected
        return False
    
    # ==================== Roblox-like helpers ====================
    def play_sound(self, name: str):
        """Синтезированные звуки: beep / coin / hit / jump / chat."""
        if not self.sounds_enabled:
            return
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(44100, -16, 1, 256)
            if name in self._sound_cache:
                sound = self._sound_cache[name]
            else:
                freqs = {
                    "beep": [660],
                    "coin": [880, 1320],
                    "hit": [160, 110],
                    "jump": [440, 660],
                    "chat": [990],
                }.get(name, [440])
                samples = bytearray()
                for f in freqs:
                    n = int(44100 * 0.07)
                    amp = 0.25 if name != "hit" else 0.4
                    for i in range(n):
                        v = int(32767 * amp * math.sin(2 * math.pi * f * i / 44100))
                        samples += v.to_bytes(2, "little", signed=True)
                sound = pygame.mixer.Sound(buffer=bytes(samples))
                self._sound_cache[name] = sound
            sound.play()
        except Exception:
            pass  # звук не критичен

    def add_notification(self, text: str, duration: float = 3.0):
        self.notifications.append({"text": text, "time": duration})

    def add_popup(self, text: str, x: float, y: float, color=(255, 80, 80)):
        """Всплывающий текст в мире (урон, +монеты и т.п.)."""
        self.popups.append({"text": text, "x": x, "y": y,
                            "color": color, "time": 1.2})

    def spawn_particles(self, x: float, y: float, color=(255, 200, 0), count: int = 10):
        import random
        for _ in range(count):
            ang = random.uniform(0, 2 * math.pi)
            spd = random.uniform(40, 160)
            self.particles.append({
                "x": x, "y": y,
                "vx": math.cos(ang) * spd, "vy": math.sin(ang) * spd,
                "color": color, "time": random.uniform(0.3, 0.8),
            })

    # ---------- scripting bridge ----------
    def script_send_chat(self, text: str):
        self._add_chat_line(self.local_player.name if self.local_player else "You", text)
        if self.is_multiplayer and self.network_client and self.network_client.connected:
            asyncio.ensure_future(self.network_client.send_message({
                "type": MessageType.CHAT_MESSAGE.value,
                "player_id": self.network_client.player_id,
                "name": self.local_player.name if self.local_player else "?",
                "message": text,
            }))

    def script_fire_event(self, name: str, data):
        if self.is_multiplayer and self.network_client and self.network_client.connected:
            asyncio.ensure_future(self.network_client.send_message({
                "type": "script_event",
                "event": name,
                "data": data,
            }))

    def _add_chat_line(self, name: str, text: str):
        import time as _t
        self.chat_log.append({"name": name, "text": text, "time": _t.time()})
        self.chat_log = self.chat_log[-8:]

    # ---------- collision ----------
    def solid_rects(self) -> List[pygame.Rect]:
        rects = []
        for obj in self.game_objects:
            if obj.object_type in ("wall", "rectangle", "block", "solid"):
                props = obj.properties or {}
                if not props.get("solid", True):
                    continue
                rects.append(pygame.Rect(obj.x, obj.y, obj.width, obj.height))
        return rects

    def circle_collides(self, x: float, y: float, r: float) -> bool:
        pt = pygame.Vector2(x, y)
        for rect in self.solid_rects():
            if rect.collidepoint(pt):
                return True
        return False

    def move_with_collision(self, player: Player, dx: float, dy: float):
        """Раздельное движение по осям со скольжением вдоль стен."""
        r = self.player_radius
        nx = max(r, min(player.x + dx, self.world_width - r))
        if not self.circle_collides(nx, player.y, r):
            player.x = nx
        ny = max(r, min(player.y + dy, self.world_height - r))
        if not self.circle_collides(player.x, ny, r):
            player.y = ny

    def find_spawn(self, level_data: dict) -> Tuple[float, float]:
        for obj in level_data.get("objects", []):
            if obj.get("object_type") == "spawn":
                return (obj["x"] + obj.get("width", 0) / 2,
                        obj["y"] + obj.get("height", 0) / 2)
        return (self.world_width / 2, self.world_height / 2)

    # ---------- combat ----------
    def damage_local(self, amount: float, source_name: str = ""):
        p = self.local_player
        if not p:
            return
        p.hp = max(0.0, p.hp - amount)
        self.add_popup(f"-{amount:g}", p.x, p.y - 30, (255, 80, 80))
        self.play_sound("hit")
        if p.hp <= 0:
            self.respawn_local(source_name)

    def heal_local(self, amount: float):
        p = self.local_player
        if not p:
            return
        p.hp = min(p.max_hp, p.hp + amount)
        self.add_popup(f"+{amount:g}", p.x, p.y - 30, (80, 255, 80))

    def respawn_local(self, killer: str = ""):
        p = self.local_player
        if not p:
            return
        p.hp = p.max_hp
        p.x, p.y = self.spawn_point
        msg = f"Вы возрождены" + (f" ({killer} победил вас)" if killer else "")
        self.add_notification(msg)
        self.sync_position_to_server()

    def sync_position_to_server(self):
        if self.is_multiplayer and self.network_client and self.network_client.connected \
                and self.local_player:
            asyncio.ensure_future(self.network_client.send_move(
                self.local_player.x, self.local_player.y))

    def handle_events(self):
        """Handle pygame events"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False

            elif event.type == pygame.KEYDOWN:
                # ---- chat mode ----
                if self.chat_active:
                    if event.key == pygame.K_ESCAPE:
                        self.chat_active = False
                        self.chat_input = ""
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        text = self.chat_input.strip()
                        if text:
                            self.script_send_chat(text)
                            self.play_sound("chat")
                        self.chat_active = False
                        self.chat_input = ""
                    elif event.key == pygame.K_BACKSPACE:
                        self.chat_input = self.chat_input[:-1]
                    else:
                        if event.unicode.isprintable() and len(self.chat_input) < 120:
                            self.chat_input += event.unicode
                    continue  # в режиме чата остальные клавиши не управляют игроком

                if event.key == pygame.K_t or event.key == pygame.K_RETURN:
                    self.chat_active = True
                    self.chat_input = ""
                    continue
                if event.key == pygame.K_F5:
                    self.script_manager.reload_all()
                    continue
                if event.key == pygame.K_m:
                    self.sounds_enabled = not self.sounds_enabled
                    self.add_notification(
                        "Звук: " + ("вкл" if self.sounds_enabled else "выкл"))
                    continue

                self.keys_pressed.add(event.key)
                # script hook (ReceiveEvent-like)
                self.script_manager.on_key(event.key)

            elif event.type == pygame.KEYUP:
                if event.key in self.keys_pressed:
                    self.keys_pressed.remove(event.key)

    def update(self, dt: float):
        """Update game state"""
        # Update local player position
        if self.local_player and not self.chat_active:
            dx, dy = 0, 0
            if pygame.K_w in self.keys_pressed or pygame.K_UP in self.keys_pressed:
                dy = -1
            if pygame.K_s in self.keys_pressed or pygame.K_DOWN in self.keys_pressed:
                dy = 1
            if pygame.K_a in self.keys_pressed or pygame.K_LEFT in self.keys_pressed:
                dx = -1
            if pygame.K_d in self.keys_pressed or pygame.K_RIGHT in self.keys_pressed:
                dx = 1

            # Normalize diagonal movement
            if dx != 0 and dy != 0:
                dx *= 0.707
                dy *= 0.707

            shift = 2.0 if pygame.K_LSHIFT in self.keys_pressed else 1.0
            move_dx = dx * self.local_player.speed * shift * dt
            move_dy = dy * self.local_player.speed * shift * dt

            # Collision-aware movement (стены из уровня)
            self.move_with_collision(self.local_player, move_dx, move_dy)

            # Send position to server (throttled ~15 Hz)
            if self.is_multiplayer and self.network_client and self.network_client.connected:
                self._net_send_acc = getattr(self, "_net_send_acc", 0.0) + dt
                if self._net_send_acc >= 1 / 15.0:
                    self._net_send_acc = 0.0
                    asyncio.ensure_future(
                        self.network_client.send_move(self.local_player.x, self.local_player.y)
                    )

        # Triggers: check zones under local player
        self._check_triggers()

        # Popups / notifications / particles
        for popup in self.popups:
            popup["time"] -= dt
            popup["y"] -= 40 * dt
        self.popups = [p for p in self.popups if p["time"] > 0]

        for n in self.notifications:
            n["time"] -= dt
        self.notifications = [n for n in self.notifications if n["time"] > 0]

        for part in self.particles:
            part["time"] -= dt
            part["x"] += part["vx"] * dt
            part["y"] += part["vy"] * dt
        self.particles = [p for p in self.particles if p["time"] > 0]

        # Scripts update
        self.script_manager.update(dt)

        # Update camera to follow local player
        if self.local_player:
            self.camera_x = self.local_player.x - self.screen_width // 2
            self.camera_y = self.local_player.y - self.screen_height // 2
            
            # Clamp camera
            self.camera_x = max(0, min(self.camera_x, self.world_width - self.screen_width))
            self.camera_y = max(0, min(self.camera_y, self.world_height - self.screen_height))
    
    def _check_triggers(self):
        """Встроенные триггеры уровней: heal / damage / killbrick (как в Roblox)."""
        p = self.local_player
        if not p:
            return
        for obj in self.game_objects:
            if obj.object_type not in ("heal", "damage", "killbrick", "checkpoint"):
                continue
            rect = pygame.Rect(obj.x, obj.y, obj.width, obj.height)
            if not rect.collidepoint(p.x, p.y):
                continue
            props = obj.properties or {}
            if obj.object_type == "heal":
                amount = float(props.get("amount", 25))
                cd = float(props.get("cooldown", 2.0))
                last = getattr(self, "_trig_heal", 0.0)
                if pygame.time.get_ticks() / 1000 - last > cd and p.hp < p.max_hp:
                    self._trig_heal = pygame.time.get_ticks() / 1000
                    self.heal_local(amount)
                    self.play_sound("coin")
            elif obj.object_type == "damage":
                amount = float(props.get("amount", 10))
                cd = float(props.get("cooldown", 1.0))
                last = getattr(self, "_trig_dmg", {}).get(obj.id, -99)
                now = pygame.time.get_ticks() / 1000
                if now - last > cd:
                    self._trig_dmg = getattr(self, "_trig_dmg", {})
                    self._trig_dmg[obj.id] = now
                    self.damage_local(amount)
            elif obj.object_type == "killbrick":
                self.damage_local(p.hp, "Killbrick")

    def draw(self):
        """Render the game"""
        self.screen.fill((30, 30, 30))
        
        # Draw world boundary
        world_rect = pygame.Rect(-self.camera_x, -self.camera_y, self.world_width, self.world_height)
        pygame.draw.rect(self.screen, (50, 50, 50), world_rect, 2)
        
        # Draw grid
        grid_size = 50
        for x in range(0, self.world_width, grid_size):
            screen_x = x - self.camera_x
            if 0 <= screen_x <= self.screen_width:
                pygame.draw.line(self.screen, (40, 40, 40), 
                               (screen_x, -self.camera_y), 
                               (screen_x, self.world_height - self.camera_y))
        
        for y in range(0, self.world_height, grid_size):
            screen_y = y - self.camera_y
            if 0 <= screen_y <= self.screen_height:
                pygame.draw.line(self.screen, (40, 40, 40), 
                               (-self.camera_x, screen_y), 
                               (self.world_width - self.camera_x, screen_y))
        
        # Draw game objects (с поддержкой всех типов из редактора)
        TYPE_COLORS = {
            "rectangle": (100, 100, 100),
            "wall": (130, 110, 90),
            "block": (150, 120, 80),
            "spawn": (80, 200, 120),
            "heal": (80, 220, 100),
            "damage": (230, 160, 40),
            "killbrick": (230, 50, 50),
            "checkpoint": (80, 160, 255),
        }
        for obj in self.game_objects:
            screen_x = obj.x - self.camera_x
            screen_y = obj.y - self.camera_y
            if (screen_x > self.screen_width or screen_y > self.screen_height
                    or screen_x + obj.width < 0 or screen_y + obj.height < 0):
                continue  # culling

            color = tuple(obj.properties.get("color", TYPE_COLORS.get(obj.object_type, (100, 100, 100))))
            rect = pygame.Rect(screen_x, screen_y, obj.width, obj.height)

            if obj.object_type == "spawn":
                pygame.draw.rect(self.screen, color, rect, 2)
                label = self.chat_font.render("SPAWN", True, color)
                self.screen.blit(label, label.get_rect(center=rect.center))
            elif obj.object_type in ("heal", "damage", "killbrick", "checkpoint"):
                s = pygame.Surface((obj.width, obj.height), pygame.SRCALPHA)
                s.fill((*color, 90))
                self.screen.blit(s, rect.topleft)
                pygame.draw.rect(self.screen, color, rect, 2)
                icons = {"heal": "+HP", "damage": "DMG", "killbrick": "X", "checkpoint": "CP"}
                label = self.chat_font.render(icons.get(obj.object_type, ""), True, color)
                self.screen.blit(label, label.get_rect(center=rect.center))
            else:
                pygame.draw.rect(self.screen, color, rect)
                pygame.draw.rect(self.screen, tuple(min(255, c + 40) for c in color), rect, 2)

        # Particles
        for part in self.particles:
            px, py = int(part["x"] - self.camera_x), int(part["y"] - self.camera_y)
            pygame.draw.circle(self.screen, part["color"], (px, py), 3)

        # Draw other players
        font_name = pygame.font.Font(None, 24)
        for player_id, player in self.players.items():
            if player_id != self.local_player.id if self.local_player else True:
                screen_x = player.x - self.camera_x
                screen_y = player.y - self.camera_y

                # Draw player circle
                pygame.draw.circle(self.screen, player.color, (int(screen_x), int(screen_y)), 20)

                # Draw player name
                text = font_name.render(player.name, True, (255, 255, 255))
                text_rect = text.get_rect(center=(screen_x, screen_y - 30))
                self.screen.blit(text, text_rect)

                # HP bar
                if getattr(player, "max_hp", 100) > 0:
                    w = 44
                    ratio = max(0.0, min(1.0, player.hp / player.max_hp))
                    pygame.draw.rect(self.screen, (60, 60, 60),
                                     (screen_x - w // 2, screen_y + 24, w, 6))
                    hp_color = (80, 220, 80) if ratio > 0.5 else \
                               (230, 200, 60) if ratio > 0.25 else (230, 70, 70)
                    pygame.draw.rect(self.screen, hp_color,
                                     (screen_x - w // 2, screen_y + 24, int(w * ratio), 6))

        # Draw local player
        if self.local_player:
            screen_x = self.local_player.x - self.camera_x
            screen_y = self.local_player.y - self.camera_y

            pygame.draw.circle(self.screen, self.local_player.color, (int(screen_x), int(screen_y)), 20)

            # Draw indicator
            pygame.draw.circle(self.screen, (255, 255, 0), (int(screen_x), int(screen_y)), 25, 2)

            # Draw player name
            text = font_name.render(f"{self.local_player.name} (You)", True, (255, 255, 0))
            text_rect = text.get_rect(center=(screen_x, screen_y - 30))
            self.screen.blit(text, text_rect)

        # Floating popups (урон/лечение)
        for popup in self.popups:
            px = popup["x"] - self.camera_x
            py = popup["y"] - self.camera_y
            surf = font_name.render(popup["text"], True, popup["color"])
            alpha = max(0, min(255, int(popup["time"] / 1.2 * 255)))
            surf.set_alpha(alpha)
            self.screen.blit(surf, surf.get_rect(center=(px, py)))

        # Draw FPS
        font = pygame.font.Font(None, 36)
        fps_text = font.render(f"FPS: {int(self.clock.get_fps())}", True, (255, 255, 255))
        self.screen.blit(fps_text, (10, 10))

        # Draw connection status
        if self.is_multiplayer:
            status = "Connected" if self.network_client and self.network_client.connected else "Disconnected"
            color = (0, 255, 0) if self.network_client and self.network_client.connected else (255, 0, 0)
            status_text = font.render(f"Server: {status}", True, color)
            self.screen.blit(status_text, (10, 50))

        # ===== Chat UI (Roblox-style) =====
        import time as _t
        now = _t.time()
        y0 = self.screen_height - 20
        lines = [c for c in self.chat_log if now - c["time"] < 20]
        for entry in reversed(lines[-6:]):
            line = f"{entry['name']}: {entry['text']}"
            surf = self.chat_font.render(line[:100], True, (255, 255, 255))
            bg = pygame.Surface((surf.get_width() + 10, surf.get_height() + 4), pygame.SRCALPHA)
            bg.fill((0, 0, 0, 120))
            self.screen.blit(bg, (10, y0 - bg.get_height()))
            self.screen.blit(surf, (15, y0 - surf.get_height()))
            y0 -= surf.get_height() + 6

        if self.chat_active:
            prompt = self.chat_font.render("> " + self.chat_input + "▌", True, (255, 255, 120))
            bg = pygame.Surface((max(300, prompt.get_width() + 12), prompt.get_height() + 8), pygame.SRCALPHA)
            bg.fill((0, 0, 0, 170))
            self.screen.blit(bg, (10, y0 - bg.get_height()))
            self.screen.blit(prompt, (14, y0 - prompt.get_height()))
        else:
            hint = self.chat_font.render("[T] чат  [F5] скрипты  [M] звук  [Shift] бег",
                                         True, (160, 160, 160))
            self.screen.blit(hint, (10, self.screen_height - 22))

        # ===== Notifications (center toasts) =====
        ny = 90
        for n in self.notifications:
            surf = font.render(n["text"], True, (255, 255, 255))
            bg = pygame.Surface((surf.get_width() + 24, surf.get_height() + 12), pygame.SRCALPHA)
            bg.fill((20, 20, 20, 190))
            pos = bg.get_rect(midtop=(self.screen_width // 2, ny))
            self.screen.blit(bg, pos)
            self.screen.blit(surf, (pos.x + 12, pos.y + 6))
            ny += surf.get_height() + 18

        # ===== Local player HP bar (bottom center) =====
        if self.local_player:
            p = self.local_player
            w, h = 260, 18
            x = self.screen_width // 2 - w // 2
            y = self.screen_height - 60
            pygame.draw.rect(self.screen, (40, 40, 40), (x - 2, y - 2, w + 4, h + 4), border_radius=6)
            ratio = max(0.0, min(1.0, p.hp / p.max_hp))
            hp_color = (80, 220, 80) if ratio > 0.5 else (230, 200, 60) if ratio > 0.25 else (230, 70, 70)
            if ratio > 0:
                pygame.draw.rect(self.screen, hp_color, (x, y, int(w * ratio), h), border_radius=4)
            hp_text = self.chat_font.render(f"HP {p.hp:g}/{p.max_hp:g}", True, (255, 255, 255))
            self.screen.blit(hp_text, hp_text.get_rect(center=(self.screen_width // 2, y + h // 2)))

        pygame.display.flip()
    
    async def network_update(self):
        """Update network state"""
        if self.is_multiplayer and self.network_client and self.network_client.connected:
            # Receive all pending messages
            for _ in range(20):  # Limit to prevent freezing
                try:
                    await self.network_client.receive_messages()
                except:
                    break

            await self.network_client.process_messages()

            # Handle local-relay messages (chat / script events)
            q = self.network_client.message_queue
            drained = []
            while not q.empty():
                msg = await q.get()
                if msg.get("type") == "_chat_local":
                    self._add_chat_line(msg["name"], msg["message"])
                    self.script_manager.on_chat(msg.get("player_id"),
                                                msg["name"], msg["message"])
                    self.play_sound("chat")
                elif msg.get("type") == "_script_event_local":
                    self.script_manager.on_network_event(msg["event"], msg["data"])
                else:
                    drained.append(msg)
            for m in drained:
                await q.put(m)
            await self.network_client.process_messages()

            # Spawn point from server
            so = getattr(self.network_client, "spawn_override", None)
            if so:
                self.spawn_point = so

            # Sync local player position from server (authoritative)
            if self.local_player and self.local_player.id in self.network_client.players:
                network_player = self.network_client.players[self.local_player.id]
                # Only update if significantly different (reduce jitter)
                if abs(network_player.x - self.local_player.x) > 1 or abs(network_player.y - self.local_player.y) > 1:
                    self.local_player.x = network_player.x
                    self.local_player.y = network_player.y
            
            # Update all players from network
            self.players = self.network_client.players.copy()
            if self.local_player:
                self.players[self.local_player.id] = self.local_player
            
            # Update game objects
            self.game_objects = list(self.network_client.game_objects.values())
    
    async def run_async(self):
        """Main async game loop"""
        self.running = True

        # Load user scripts (LocalScripts)
        self.script_manager.load_all()

        # Connect to server if multiplayer
        if self.is_multiplayer:
            connected = await self.connect_to_server()
            if not connected:
                print("Failed to connect to server, running in single-player mode")
                self.is_multiplayer = False

        # Spawn local player (also in single-player mode)
        if not self.local_player:
            sx, sy = self.spawn_point
            self.local_player = Player(
                id="local", x=sx, y=sy,
                color=(0, 255, 0),
                name=getattr(self, "player_name", "Player"),
            )
            self.players[self.local_player.id] = self.local_player

        self.add_notification(f"\u0414\u043e\u0431\u0440\u043e \u043f\u043e\u0436\u0430\u043b\u043e\u0432\u0430\u0442\u044c! \u0418\u0433\u0440\u043e\u043a\u043e\u0432: {len(self.players)}")
        self.script_manager.start()

        last_time = pygame.time.get_ticks()
        
        while self.running:
            dt = (pygame.time.get_ticks() - last_time) / 1000.0
            last_time = pygame.time.get_ticks()
            
            self.handle_events()
            self.update(dt)
            
            if self.is_multiplayer:
                await self.network_update()
            
            self.draw()
            self.clock.tick(self.fps)
        
        # Cleanup
        if self.is_multiplayer and self.network_client:
            await self.network_client.disconnect()
        
        pygame.quit()
    
    def run(self):
        """Start the game (blocking)"""
        try:
            asyncio.run(self.run_async())
        except KeyboardInterrupt:
            self.running = False
            pygame.quit()
    
    def load_level(self, level_data: dict):
        """Load level from dictionary"""
        self.world_width = level_data.get("world_width", 2000)
        self.world_height = level_data.get("world_height", 2000)
        
        self.game_objects = []
        for obj_data in level_data.get("objects", []):
            obj = GameObject.from_dict(obj_data)
            self.game_objects.append(obj)

        # Spawn point from level + place local player there
        self.spawn_point = self.find_spawn(level_data)
        if self.local_player:
            self.local_player.x, self.local_player.y = self.spawn_point
        print(f"Level loaded. Spawn: {self.spawn_point}")
    
    def save_level(self) -> dict:
        """Save current level to dictionary"""
        return {
            "world_width": self.world_width,
            "world_height": self.world_height,
            "objects": [obj.to_dict() for obj in self.game_objects]
        }


if __name__ == "__main__":
    # Example usage
    engine = GameEngine()
    engine.run()
