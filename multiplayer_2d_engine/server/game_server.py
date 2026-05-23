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
    websocket: websockets.WebSocketClientProtocol = None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "x": self.x,
            "y": self.y,
            "color": self.color
        }


class GameServer:
    """WebSocket game server for multiplayer support"""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        self.host = host
        self.port = port
        self.players: Dict[str, ServerPlayer] = {}
        self.game_objects: Dict[str, dict] = {}
        self.broadcast_interval = 0.1  # seconds
        
    async def register(self, websocket: websockets.WebSocketClientProtocol, player_name: str) -> str:
        """Register a new player"""
        player_id = str(uuid.uuid4())[:8]
        
        # Generate random color
        import random
        color = (random.randint(50, 255), random.randint(50, 255), random.randint(50, 255))
        
        player = ServerPlayer(
            id=player_id,
            name=player_name,
            x=1000,  # Center of default world
            y=1000,
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
    
    async def handler(self, websocket: websockets.WebSocketClientProtocol):
        """Main WebSocket handler"""
        player_id = None
        
        try:
            # First message should be player_join
            message = await websocket.recv()
            data = json.loads(message)
            
            if data.get("type") == "player_join":
                player_name = data.get("name", "Unknown")
                player_id = await self.register(websocket, player_name)
            
            # Now handle continuous messages
            async for message in websocket:
                try:
                    data = json.loads(message)
                    msg_type = data.get("type")
                    
                    if msg_type == "player_move":
                        move_player_id = data.get("player_id")
                        x = data.get("x", 0)
                        y = data.get("y", 0)
                        await self.handle_player_move(move_player_id, x, y)
                    
                    elif msg_type == "chat_message":
                        await self.broadcast({
                            "type": "chat_message",
                            "player_id": player_id,
                            "message": data.get("message", "")
                        })
                    
                except json.JSONDecodeError:
                    print(f"Invalid JSON from {player_id}")
                except Exception as e:
                    print(f"Error handling message: {e}")
        
        except websockets.exceptions.ConnectionClosed:
            pass  # Normal disconnection
        except Exception as e:
            print(f"Handler error: {e}")
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
        
        print("Server started! Press Ctrl+C to stop.")
        
        # Keep running
        await server.wait_closed()
        broadcast_task.cancel()


def run_server(host: str = "0.0.0.0", port: int = 8765):
    """Run the game server"""
    server = GameServer(host, port)
    
    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        print("\nServer stopped")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Multiplayer Game Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on")
    
    args = parser.parse_args()
    
    run_server(args.host, args.port)
