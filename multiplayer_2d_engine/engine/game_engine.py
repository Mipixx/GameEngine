"""
2D Top-Down Multiplayer Game Engine
Core engine module with networking support
"""

import pygame
import asyncio
import websockets
import json
import threading
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum


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
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "x": self.x,
            "y": self.y,
            "color": self.color,
            "name": self.name,
            "speed": self.speed
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Player':
        return cls(
            id=data["id"],
            x=data["x"],
            y=data["y"],
            color=tuple(data["color"]),
            name=data["name"],
            speed=data.get("speed", 200.0)
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
                return True
            return False
        except Exception as e:
            print(f"Connection error: {e}")
            return False
    
    async def send_message(self, message: dict):
        if self.connected and self.websocket:
            await self.websocket.send(json.dumps(message))
    
    async def receive_messages(self):
        """Continuously receive messages from server"""
        if not self.connected or not self.websocket:
            return
        
        try:
            async for message in self.websocket:
                data = json.loads(message)
                await self.message_queue.put(data)
        except websockets.exceptions.ConnectionClosed:
            self.connected = False
            print("Disconnected from server")
    
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
                # Create local player
                self.local_player = Player(
                    id=self.network_client.player_id,
                    x=self.world_width // 2,
                    y=self.world_height // 2,
                    color=(0, 255, 0),
                    name=self.player_name
                )
                self.players[self.local_player.id] = self.local_player
            return connected
        return False
    
    def handle_events(self):
        """Handle pygame events"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            
            elif event.type == pygame.KEYDOWN:
                self.keys_pressed.add(event.key)
                
            elif event.type == pygame.KEYUP:
                if event.key in self.keys_pressed:
                    self.keys_pressed.remove(event.key)
    
    def update(self, dt: float):
        """Update game state"""
        # Update local player position
        if self.local_player:
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
            
            self.local_player.x += dx * self.local_player.speed * dt
            self.local_player.y += dy * self.local_player.speed * dt
            
            # Clamp to world bounds
            self.local_player.x = max(0, min(self.local_player.x, self.world_width))
            self.local_player.y = max(0, min(self.local_player.y, self.world_height))
            
            # Send position to server
            if self.is_multiplayer and self.network_client and self.network_client.connected:
                asyncio.create_task(
                    self.network_client.send_move(self.local_player.x, self.local_player.y)
                )
        
        # Update camera to follow local player
        if self.local_player:
            self.camera_x = self.local_player.x - self.screen_width // 2
            self.camera_y = self.local_player.y - self.screen_height // 2
            
            # Clamp camera
            self.camera_x = max(0, min(self.camera_x, self.world_width - self.screen_width))
            self.camera_y = max(0, min(self.camera_y, self.world_height - self.screen_height))
    
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
        
        # Draw game objects
        for obj in self.game_objects:
            screen_x = obj.x - self.camera_x
            screen_y = obj.y - self.camera_y
            
            if obj.object_type == "rectangle":
                color = obj.properties.get("color", (100, 100, 100))
                rect = pygame.Rect(screen_x, screen_y, obj.width, obj.height)
                pygame.draw.rect(self.screen, color, rect)
        
        # Draw other players
        for player_id, player in self.players.items():
            if player_id != self.local_player.id if self.local_player else True:
                screen_x = player.x - self.camera_x
                screen_y = player.y - self.camera_y
                
                # Draw player circle
                pygame.draw.circle(self.screen, player.color, (int(screen_x), int(screen_y)), 20)
                
                # Draw player name
                font = pygame.font.Font(None, 24)
                text = font.render(player.name, True, (255, 255, 255))
                text_rect = text.get_rect(center=(screen_x, screen_y - 30))
                self.screen.blit(text, text_rect)
        
        # Draw local player
        if self.local_player:
            screen_x = self.local_player.x - self.camera_x
            screen_y = self.local_player.y - self.camera_y
            
            pygame.draw.circle(self.screen, self.local_player.color, (int(screen_x), int(screen_y)), 20)
            
            # Draw indicator
            pygame.draw.circle(self.screen, (255, 255, 0), (int(screen_x), int(screen_y)), 25, 2)
            
            # Draw player name
            font = pygame.font.Font(None, 24)
            text = font.render(f"{self.local_player.name} (You)", True, (255, 255, 0))
            text_rect = text.get_rect(center=(screen_x, screen_y - 30))
            self.screen.blit(text, text_rect)
        
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
        
        pygame.display.flip()
    
    async def network_update(self):
        """Update network state"""
        if self.is_multiplayer and self.network_client and self.network_client.connected:
            await self.network_client.receive_messages()
            await self.network_client.process_messages()
            
            # Sync local player
            if self.local_player and self.local_player.id in self.network_client.players:
                network_player = self.network_client.players[self.local_player.id]
                self.local_player.x = network_player.x
                self.local_player.y = network_player.y
            
            # Update all players
            self.players = self.network_client.players.copy()
            if self.local_player:
                self.players[self.local_player.id] = self.local_player
            
            # Update game objects
            self.game_objects = list(self.network_client.game_objects.values())
    
    async def run_async(self):
        """Main async game loop"""
        self.running = True
        
        # Connect to server if multiplayer
        if self.is_multiplayer:
            connected = await self.connect_to_server()
            if not connected:
                print("Failed to connect to server, running in single-player mode")
                self.is_multiplayer = False
        
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
