"""
Level Editor for 2D Multiplayer Game
Visual editor for creating and editing game levels
"""

import pygame
import json
import sys
import os
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
import uuid


@dataclass
class EditableObject:
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
    def from_dict(cls, data: dict) -> 'EditableObject':
        return cls(**data)
    
    def get_rect(self) -> pygame.Rect:
        return pygame.Rect(self.x, self.y, self.width, self.height)


class LevelEditor:
    """Visual level editor with GUI"""
    
    def __init__(self, screen_width: int = 1280, screen_height: int = 720):
        pygame.init()
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.screen = pygame.display.set_mode((screen_width, screen_height))
        pygame.display.set_caption("2D Game Level Editor")
        self.clock = pygame.time.Clock()
        self.running = False
        self.fps = 60
        
        # Editor state
        self.objects: List[EditableObject] = []
        self.selected_object: Optional[EditableObject] = None
        self.camera_x = 0
        self.camera_y = 0
        self.zoom = 1.0
        
        # World settings
        self.world_width = 2000
        self.world_height = 2000
        
        # UI panels
        self.panel_width = 250
        self.show_grid = True
        self.grid_size = 50
        
        # Tools
        self.current_tool = "select"  # select, move, resize, create
        self.create_type = "rectangle"
        self.create_width = 100
        self.create_height = 100
        self.create_color = (100, 100, 100)
        
        # Mouse state
        self.mouse_pos = (0, 0)
        self.mouse_pressed = False
        self.drag_start = None
        self.is_dragging = False
        
        # Colors
        self.colors = {
            "bg": (30, 30, 30),
            "panel": (40, 40, 40),
            "grid": (50, 50, 50),
            "selection": (255, 255, 0),
            "text": (255, 255, 255),
            "button": (60, 60, 60),
            "button_hover": (80, 80, 80),
            "world_border": (100, 100, 100)
        }
        
        # Fonts
        self.font = pygame.font.Font(None, 24)
        self.title_font = pygame.font.Font(None, 32)
        
        # Buttons
        self.buttons = []
        self.setup_buttons()
        
    def setup_buttons(self):
        """Setup UI buttons"""
        panel_x = self.screen_width - self.panel_width + 10
        
        self.buttons = [
            {"rect": pygame.Rect(panel_x, 70, 110, 30), "text": "Select", "action": lambda: setattr(self, 'current_tool', 'select')},
            {"rect": pygame.Rect(panel_x + 120, 70, 110, 30), "text": "Create", "action": lambda: setattr(self, 'current_tool', 'create')},
            
            {"rect": pygame.Rect(panel_x, 120, 110, 30), "text": "Rectangle", "action": lambda: setattr(self, 'create_type', 'rectangle')},
            {"rect": pygame.Rect(panel_x + 120, 120, 110, 30), "text": "Spawn Point", "action": lambda: setattr(self, 'create_type', 'spawn')},
            
            {"rect": pygame.Rect(panel_x, 180, 110, 30), "text": "Save Level", "action": self.save_level},
            {"rect": pygame.Rect(panel_x + 120, 180, 110, 30), "text": "Load Level", "action": self.load_level},
            
            {"rect": pygame.Rect(panel_x, 230, 110, 30), "text": "Toggle Grid", "action": lambda: setattr(self, 'show_grid', not self.show_grid)},
            {"rect": pygame.Rect(panel_x + 120, 230, 110, 30), "text": "Delete", "action": self.delete_selected},
            
            {"rect": pygame.Rect(panel_x, 280, 230, 30), "text": "Export to JSON", "action": self.export_json},
        ]
        
    def world_to_screen(self, x: float, y: float) -> tuple:
        """Convert world coordinates to screen coordinates"""
        screen_x = int((x - self.camera_x) * self.zoom)
        screen_y = int((y - self.camera_y) * self.zoom)
        return screen_x, screen_y
    
    def screen_to_world(self, x: int, y: int) -> tuple:
        """Convert screen coordinates to world coordinates"""
        world_x = (x / self.zoom) + self.camera_x
        world_y = (y / self.zoom) + self.camera_y
        return world_x, world_y
    
    def handle_events(self):
        """Handle pygame events"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            
            elif event.type == pygame.MOUSEBUTTONDOWN:
                self.mouse_pressed = True
                self.mouse_pos = pygame.mouse.get_pos()
                
                # Check button clicks
                if self.mouse_pos[0] >= self.screen_width - self.panel_width:
                    for button in self.buttons:
                        if button["rect"].collidepoint(self.mouse_pos):
                            button["action"]()
                            return
                
                # Handle tool actions
                world_x, world_y = self.screen_to_world(self.mouse_pos[0], self.mouse_pos[1])
                
                if self.current_tool == "select":
                    # Select object
                    self.selected_object = None
                    for obj in reversed(self.objects):
                        if obj.get_rect().collidepoint(world_x, world_y):
                            self.selected_object = obj
                            self.drag_start = (world_x - obj.x, world_y - obj.y)
                            break
                
                elif self.current_tool == "create":
                    # Create new object
                    new_obj = EditableObject(
                        id=str(uuid.uuid4())[:8],
                        x=world_x,
                        y=world_y,
                        width=self.create_width,
                        height=self.create_height,
                        object_type=self.create_type,
                        properties={"color": list(self.create_color)}
                    )
                    self.objects.append(new_obj)
                    self.selected_object = new_obj
            
            elif event.type == pygame.MOUSEBUTTONUP:
                self.mouse_pressed = False
                self.is_dragging = False
                self.drag_start = None
            
            elif event.type == pygame.MOUSEMOTION:
                self.mouse_pos = pygame.mouse.get_pos()
                
                if self.mouse_pressed and self.mouse_pos[0] < self.screen_width - self.panel_width:
                    if self.current_tool == "select" and self.selected_object and self.drag_start:
                        # Move selected object
                        world_x, world_y = self.screen_to_world(self.mouse_pos[0], self.mouse_pos[1])
                        self.selected_object.x = world_x - self.drag_start[0]
                        self.selected_object.y = world_y - self.drag_start[1]
                        self.is_dragging = True
                    
                    elif not self.is_dragging:
                        # Pan camera
                        dx, dy = event.rel
                        self.camera_x -= dx / self.zoom
                        self.camera_y -= dy / self.zoom
            
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_DELETE or event.key == pygame.K_BACKSPACE:
                    self.delete_selected()
                
                elif event.key == pygame.K_g:
                    self.show_grid = not self.show_grid
                
                elif event.key == pygame.K_EQUALS or event.key == pygame.K_KP_PLUS:
                    self.zoom = min(3.0, self.zoom + 0.1)
                
                elif event.key == pygame.K_MINUS or event.key == pygame.K_KP_MINUS:
                    self.zoom = max(0.1, self.zoom - 0.1)
                
                elif event.key == pygame.K_ESCAPE:
                    self.selected_object = None
    
    def delete_selected(self):
        """Delete the selected object"""
        if self.selected_object:
            if self.selected_object in self.objects:
                self.objects.remove(self.selected_object)
            self.selected_object = None
    
    def save_level(self):
        """Save level to file"""
        filename = "level.json"
        level_data = {
            "world_width": self.world_width,
            "world_height": self.world_height,
            "objects": [obj.to_dict() for obj in self.objects]
        }
        
        with open(filename, 'w') as f:
            json.dump(level_data, f, indent=2)
        
        print(f"Level saved to {filename}")
    
    def load_level(self):
        """Load level from file"""
        filename = "level.json"
        if not os.path.exists(filename):
            print(f"No level file found at {filename}")
            return
        
        try:
            with open(filename, 'r') as f:
                level_data = json.load(f)
            
            self.world_width = level_data.get("world_width", 2000)
            self.world_height = level_data.get("world_height", 2000)
            self.objects = [EditableObject.from_dict(obj) for obj in level_data.get("objects", [])]
            self.selected_object = None
            
            print(f"Level loaded from {filename}")
        except Exception as e:
            print(f"Error loading level: {e}")
    
    def export_json(self):
        """Export level data as JSON string"""
        level_data = {
            "world_width": self.world_width,
            "world_height": self.world_height,
            "objects": [obj.to_dict() for obj in self.objects]
        }
        
        json_str = json.dumps(level_data, indent=2)
        print("\n=== LEVEL DATA ===")
        print(json_str)
        print("==================\n")
    
    def draw_panel(self):
        """Draw the side panel"""
        panel_rect = pygame.Rect(self.screen_width - self.panel_width, 0, self.panel_width, self.screen_height)
        pygame.draw.rect(self.screen, self.colors["panel"], panel_rect)
        
        # Draw title
        title = self.title_font.render("Editor Panel", True, self.colors["text"])
        self.screen.blit(title, (self.screen_width - self.panel_width + 10, 10))
        
        # Draw section labels
        sections = [
            (60, "Tools"),
            (110, "Object Type"),
            (170, "Actions"),
            (220, "View"),
            (270, "Export")
        ]
        
        for y, text in sections:
            label = self.font.render(text, True, self.colors["text"])
            self.screen.blit(label, (self.screen_width - self.panel_width + 10, y))
        
        # Draw buttons
        mouse_pos = pygame.mouse.get_pos()
        for button in self.buttons:
            color = self.colors["button_hover"] if button["rect"].collidepoint(mouse_pos) else self.colors["button"]
            pygame.draw.rect(self.screen, color, button["rect"])
            pygame.draw.rect(self.screen, self.colors["text"], button["rect"], 1)
            
            text = self.font.render(button["text"], True, self.colors["text"])
            text_rect = text.get_rect(center=button["rect"].center)
            self.screen.blit(text, text_rect)
        
        # Draw info
        info_y = 330
        info_lines = [
            f"Objects: {len(self.objects)}",
            f"Camera: ({int(self.camera_x)}, {int(self.camera_y)})",
            f"Zoom: {self.zoom:.1f}x",
            f"Tool: {self.current_tool}",
            "",
            "Controls:",
            "WASD/Arrows - Pan",
            "+/- - Zoom",
            "Del - Delete",
            "G - Toggle Grid"
        ]
        
        for line in info_lines:
            text = self.font.render(line, True, self.colors["text"])
            self.screen.blit(text, (self.screen_width - self.panel_width + 10, info_y))
            info_y += 20
        
        # Draw selected object properties
        if self.selected_object:
            info_y += 10
            props_title = self.font.render("Selected Object:", True, self.colors["selection"])
            self.screen.blit(props_title, (self.screen_width - self.panel_width + 10, info_y))
            info_y += 25
            
            props = [
                f"ID: {self.selected_object.id}",
                f"Type: {self.selected_object.object_type}",
                f"X: {int(self.selected_object.x)}",
                f"Y: {int(self.selected_object.y)}",
                f"W: {int(self.selected_object.width)}",
                f"H: {int(self.selected_object.height)}"
            ]
            
            for prop in props:
                text = self.font.render(prop, True, self.colors["text"])
                self.screen.blit(text, (self.screen_width - self.panel_width + 10, info_y))
                info_y += 20
    
    def draw(self):
        """Render the editor"""
        self.screen.fill(self.colors["bg"])
        
        # Draw grid
        if self.show_grid:
            start_x = int(self.camera_x / self.grid_size) * self.grid_size
            start_y = int(self.camera_y / self.grid_size) * self.grid_size
            
            for x in range(int(start_x), int(self.camera_x + self.screen_width / self.zoom), int(self.grid_size)):
                screen_x = int((x - self.camera_x) * self.zoom)
                pygame.draw.line(self.screen, self.colors["grid"], 
                               (screen_x, 0), (screen_x, self.screen_height))
            
            for y in range(int(start_y), int(self.camera_y + self.screen_height / self.zoom), int(self.grid_size)):
                screen_y = int((y - self.camera_y) * self.zoom)
                pygame.draw.line(self.screen, self.colors["grid"], 
                               (0, screen_y), (self.screen_width, screen_y))
        
        # Draw world border
        top_left = self.world_to_screen(0, 0)
        bottom_right = self.world_to_screen(self.world_width, self.world_height)
        world_rect = pygame.Rect(top_left[0], top_left[1], 
                                int(self.world_width * self.zoom), int(self.world_height * self.zoom))
        pygame.draw.rect(self.screen, self.colors["world_border"], world_rect, 2)
        
        # Draw objects
        for obj in self.objects:
            screen_x, screen_y = self.world_to_screen(obj.x, obj.y)
            screen_w = int(obj.width * self.zoom)
            screen_h = int(obj.height * self.zoom)
            
            color = obj.properties.get("color", self.colors["button"])
            rect = pygame.Rect(screen_x, screen_y, screen_w, screen_h)
            pygame.draw.rect(self.screen, color, rect)
            pygame.draw.rect(self.screen, self.colors["text"], rect, 1)
            
            # Draw selection highlight
            if obj == self.selected_object:
                highlight_rect = pygame.Rect(screen_x - 2, screen_y - 2, screen_w + 4, screen_h + 4)
                pygame.draw.rect(self.screen, self.colors["selection"], highlight_rect, 2)
            
            # Draw object type label
            label = self.font.render(obj.object_type, True, self.colors["text"])
            self.screen.blit(label, (screen_x + 5, screen_y + 5))
        
        # Draw panel
        self.draw_panel()
        
        # Draw cursor position
        world_x, world_y = self.screen_to_world(self.mouse_pos[0], self.mouse_pos[1])
        cursor_text = self.font.render(f"({int(world_x)}, {int(world_y)})", True, self.colors["text"])
        self.screen.blit(cursor_text, (10, 10))
        
        pygame.display.flip()
    
    def run(self):
        """Start the editor"""
        self.running = True
        
        while self.running:
            self.handle_events()
            self.draw()
            self.clock.tick(self.fps)
        
        pygame.quit()


def run_editor():
    """Run the level editor"""
    editor = LevelEditor()
    editor.run()


if __name__ == "__main__":
    run_editor()
