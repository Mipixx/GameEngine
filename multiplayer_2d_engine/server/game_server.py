"""
Multiplayer Game Server
WebSocket server for handling multiple clients
"""

import asyncio
import websockets
import json
import uuid
from typing import Dict, Set
from dataclasses import dataclass, asdict


@dataclass
class ServerPlayer:
    id: str
    name: str
    x: float
    y: float
    color: tuple
    hp: float = 100.0
    max_hp: float = 100.0
    websocket: websockets.WebSocketClientProtocol = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "x": self.x,
            "y": self.y,
            "color": self.color,
            "hp": self.hp,
            "max_hp": self.max_hp,
        }


class GameServer:
    """WebSocket game server for multiplayer support"""

    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        self.host = host
        self.port = port
        self.players: Dict[str, ServerPlayer] = {}
        self.game_objects: Dict[str, dict] = {}
        self.broadcast_interval = 0.1  # seconds
        self.level_name: str = ""      # loaded level file (for /status)

    # ---------- levels / plugins API ----------
    def load_level_file(self, path: str) -> bool:
        """Загрузить уровень (JSON из редактора). Объекты рассылаются всем клиентам."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[level] failed to load {path}: {e}")
            return False

        self.game_objects = {
            obj["id"]: obj for obj in data.get("objects", [])
        }
        self.level_name = path
        spawn = None
        for obj in data.get("objects", []):
            if obj.get("object_type") == "spawn":
                spawn = (obj["x"] + obj.get("width", 0) / 2,
                         obj["y"] + obj.get("height", 0) / 2)
                break
        if spawn:
            asyncio.ensure_future(self.broadcast({
                "type": "spawn_point", "x": spawn[0], "y": spawn[1]}))
        print(f"[level] loaded '{path}': {len(self.game_objects)} objects, "
              f"spawn={spawn or 'default'}")
        return True

    async def handle_plugin_command(self, player_id: str, data: dict):
        """Команды от плагинов/скриптов сервера (server/plugins/*.py)."""
        action = data.get("action")
        target = data.get("player_id", player_id)
        p = self.players.get(target)
        if not p:
            return
        if action == "damage":
            p.hp = max(0.0, float(p.hp) - float(data.get("amount", 10)))
            if p.hp <= 0:
                await self.respawn_player(target)
        elif action == "heal":
            p.hp = min(p.max_hp, float(p.hp) + float(data.get("amount", 25)))
        elif action == "teleport":
            p.x = float(data.get("x", p.x))
            p.y = float(data.get("y", p.y))
        elif action == "set_spawn":
            p.x = float(data.get("x", 1000))
            p.y = float(data.get("y", 1000))
            p.hp = p.max_hp

    async def respawn_player(self, player_id: str):
        p = self.players.get(player_id)
        if not p:
            return
        p.hp = p.max_hp
        spawn = (1000, 1000)
        for obj in self.game_objects.values():
            if obj.get("object_type") == "spawn":
                spawn = (obj["x"] + obj.get("width", 0) / 2,
                         obj["y"] + obj.get("height", 0) / 2)
                break
        p.x, p.y = spawn
        await self.broadcast({
            "type": "player_respawn",
            "player_id": player_id,
        })
        
    async def register(self, websocket: websockets.WebSocketClientProtocol, player_name: str) -> str:
        """Register a new player"""
        player_id = str(uuid.uuid4())[:8]

        # Generate random color
        import random
        color = (random.randint(50, 255), random.randint(50, 255), random.randint(50, 255))

        # Spawn point from loaded level (if any)
        sx, sy = 1000.0, 1000.0
        for obj in self.game_objects.values():
            if obj.get("object_type") == "spawn":
                sx = obj["x"] + obj.get("width", 0) / 2
                sy = obj["y"] + obj.get("height", 0) / 2
                break

        player = ServerPlayer(
            id=player_id,
            name=player_name,
            x=sx,
            y=sy,
            color=color,
            websocket=websocket
        )
        
        self.players[player_id] = player
        
        # Send player ID back
        await websocket.send(json.dumps({
            "type": "player_id",
            "id": player_id
        }))
        
        # Broadcast player join
        await self.broadcast({
            "type": "player_join",
            "player": player.to_dict()
        }, exclude=[player_id])
        
        print(f"Player {player_name} ({player_id}) joined")
        return player_id
    
    async def unregister(self, player_id: str):
        """Remove a player"""
        if player_id in self.players:
            player = self.players[player_id]
            del self.players[player_id]
            
            # Broadcast player leave
            await self.broadcast({
                "type": "player_leave",
                "player_id": player_id
            })
            
            print(f"Player {player.name} ({player_id}) left")
    
    async def broadcast(self, message: dict, exclude: list = None):
        """Broadcast message to all players"""
        if exclude is None:
            exclude = []
        
        message_json = json.dumps(message)
        
        for player_id, player in self.players.items():
            if player_id not in exclude and player.websocket:
                try:
                    await player.websocket.send(message_json)
                except:
                    # Player disconnected
                    await self.unregister(player_id)
    
    async def handle_player_move(self, player_id: str, x: float, y: float):
        """Handle player movement"""
        if player_id in self.players:
            self.players[player_id].x = x
            self.players[player_id].y = y
    
    async def send_game_state(self):
        """Send complete game state to all players"""
        state = {
            "type": "game_state",
            "players": {pid: p.to_dict() for pid, p in self.players.items()},
            "objects": self.game_objects
        }
        
        await self.broadcast(state)
    
    async def handle_chat(self, player_id: str, text: str):
        """Обработка чат-команд (как в Roblox). Возвращает True, если это была команда."""
        text = text.strip()
        if not text.startswith("/"):
            return False

        parts = text.split()
        cmd = parts[0].lower()
        p = self.players.get(player_id)

        async def reply(msg_text):
            if p and p.websocket:
                try:
                    await p.websocket.send(json.dumps({
                        "type": "chat_message", "player_id": "server",
                        "name": "Server", "message": msg_text}))
                except Exception:
                    pass

        if cmd == "/help":
            await reply("Команды: /help /players /status /goto <имя> /tp <x> <y> "
                        "/heal /speed <n> /level <файл.json>")
        elif cmd == "/players":
            names = ", ".join(pl.name for pl in self.players.values())
            await reply(f"Игроки ({len(self.players)}): {names}")
        elif cmd == "/status":
            await reply(f"Игроков: {len(self.players)}, объектов: "
                        f"{len(self.game_objects)}, уровень: {self.level_name or 'нет'}")
        elif cmd == "/goto" and len(parts) > 1:
            target_name = " ".join(parts[1:]).lower()
            for pl in self.players.values():
                if pl.name.lower().startswith(target_name):
                    await self.handle_plugin_command(player_id, {
                        "action": "teleport", "x": pl.x, "y": pl.y})
                    await reply(f"Телепорт к {pl.name}")
                    break
            else:
                await reply("Игрок не найден")
        elif cmd == "/tp" and len(parts) > 2:
            try:
                x, y = float(parts[1]), float(parts[2])
                await self.handle_plugin_command(player_id, {
                    "action": "teleport", "x": x, "y": y})
                await reply(f"Телепорт на ({x:g}, {y:g})")
            except ValueError:
                await reply("Использование: /tp <x> <y>")
        elif cmd == "/heal":
            await self.handle_plugin_command(player_id, {"action": "heal", "amount": 999})
            await reply("Вы вылечены")
        elif cmd == "/speed" and len(parts) > 1:
            try:
                v = float(parts[1])
                if p:
                    await p.websocket.send(json.dumps({
                        "type": "script_event", "event": "set_speed", "data": v}))
                await reply(f"Скорость -> {v:g} (установите локально)")
            except ValueError:
                await reply("Использование: /speed <число>")
        elif cmd == "/level" and len(parts) > 1:
            path = " ".join(parts[1:])
            if self.load_level_file(path):
                await reply(f"Уровень '{path}' загружен для всех игроков")
            else:
                await reply(f"Не удалось загрузить '{path}'")
        else:
            await reply(f"Неизвестная команда: {cmd}. Напишите /help")
        return True

    async def handler(self, websocket: websockets.WebSocketClientProtocol):
        """Main WebSocket handler"""
        player_id = None
        
        try:
            # First message should be player_join
            message = await asyncio.wait_for(websocket.recv(), timeout=30.0)
            data = json.loads(message)
            
            if data.get("type") == "player_join":
                player_name = data.get("name", "Unknown")
                player_id = await self.register(websocket, player_name)
            
            # Now handle continuous messages with timeout
            while True:
                try:
                    # Use wait_for to avoid blocking indefinitely
                    message = await asyncio.wait_for(websocket.recv(), timeout=0.5)
                    
                    try:
                        data = json.loads(message)
                        msg_type = data.get("type")
                        
                        if msg_type == "player_move":
                            move_player_id = data.get("player_id")
                            # security: players can only move themselves
                            if move_player_id == player_id:
                                x = data.get("x", 0)
                                y = data.get("y", 0)
                                await self.handle_player_move(move_player_id, x, y)
                        
                        elif msg_type == "chat_message":
                            text = data.get("message", "")
                            handled = await self.handle_chat(player_id, text)
                            if not handled:
                                p = self.players.get(player_id)
                                await self.broadcast({
                                    "type": "chat_message",
                                    "player_id": player_id,
                                    "name": p.name if p else "?",
                                    "message": text[:200],
                                })

                        elif msg_type == "script_event":
                            # relay custom events from scripts to all clients
                            p = self.players.get(player_id)
                            await self.broadcast({
                                "type": "script_event",
                                "event": data.get("event"),
                                "data": data.get("data"),
                                "source": player_id,
                            })

                        elif msg_type == "plugin_command":
                            # доверенные команды от серверных плагинов
                            await self.handle_plugin_command(player_id, data)
                        
                    except json.JSONDecodeError:
                        print(f"Invalid JSON from {player_id}")
                    except Exception as e:
                        print(f"Error handling message: {e}")
                
                except asyncio.TimeoutError:
                    # No message received, continue loop
                    continue
                except websockets.exceptions.ConnectionClosed:
                    # Client disconnected normally
                    break
                except Exception as e:
                    # Other connection errors
                    print(f"Connection error: {type(e).__name__}: {e}")
                    break
        
        except asyncio.TimeoutError:
            print(f"Connection timeout waiting for initial message")
        except websockets.exceptions.ConnectionClosed:
            pass  # Normal disconnection
        except Exception as e:
            print(f"Handler error: {type(e).__name__}: {e}")
        finally:
            if player_id:
                await self.unregister(player_id)
    
    async def broadcast_loop(self):
        """Continuously broadcast game state"""
        while True:
            await asyncio.sleep(self.broadcast_interval)
            await self.send_game_state()
    
    async def run(self):
        """Start the server"""
        print(f"Starting server on ws://{self.host}:{self.port}")

        # Create server
        server = await websockets.serve(self.handler, self.host, self.port)

        # Start broadcast loop
        broadcast_task = asyncio.create_task(self.broadcast_loop())

        # Load server plugins (server/plugins/*.py)
        plugin_task = None
        try:
            import importlib.util, os
            plugins_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plugins")
            if os.path.isdir(plugins_dir):
                for fname in sorted(os.listdir(plugins_dir)):
                    if fname.endswith(".py") and not fname.startswith("_"):
                        fpath = os.path.join(plugins_dir, fname)
                        spec = importlib.util.spec_from_file_location(f"plugin_{fname[:-3]}", fpath)
                        mod = importlib.util.module_from_spec(spec)
                        try:
                            spec.loader.exec_module(mod)
                            if hasattr(mod, "setup"):
                                result = mod.setup(self)
                                if asyncio.iscoroutine(result):
                                    await result
                                print(f"[plugin] loaded {fname}")
                        except Exception as e:
                            print(f"[plugin] failed {fname}: {e}")
        except Exception as e:
            print(f"[plugin] error: {e}")

        print("Server started! Press Ctrl+C to stop.")

        # Keep running
        await server.wait_closed()
        broadcast_task.cancel()


def run_server(host: str = "0.0.0.0", port: int = 8765, level: str = None):
    """Run the game server"""
    server = GameServer(host, port)

    if level:
        server.load_level_file(level)

    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        print("\nServer stopped")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Multiplayer Game Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on")
    parser.add_argument("--level", default=None, help="Level JSON file to load on start")
    
    args = parser.parse_args()
    
    run_server(args.host, args.port, args.level)
