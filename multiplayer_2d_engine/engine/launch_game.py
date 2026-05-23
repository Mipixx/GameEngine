#!/usr/bin/env python3
"""
Game Client Launcher
Launch the game with various options
"""

import argparse
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.game_engine import GameEngine


def main():
    parser = argparse.ArgumentParser(
        description="Multiplayer 2D Game Client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                              # Start in single-player mode
  %(prog)s --multiplayer                # Connect to server
  %(prog)s -m --host 192.168.1.100      # Connect to specific server
  %(prog)s -m --name "MyPlayer"         # Set player name
        """
    )
    
    parser.add_argument(
        "--width", 
        type=int, 
        default=1280,
        help="Screen width (default: 1280)"
    )
    
    parser.add_argument(
        "--height", 
        type=int, 
        default=720,
        help="Screen height (default: 720)"
    )
    
    parser.add_argument(
        "--title", 
        type=str, 
        default="2D Multiplayer Game",
        help="Window title"
    )
    
    parser.add_argument(
        "-m", "--multiplayer",
        action="store_true",
        help="Enable multiplayer mode"
    )
    
    parser.add_argument(
        "--host", 
        type=str, 
        default="localhost",
        help="Server host (default: localhost)"
    )
    
    parser.add_argument(
        "--port", 
        type=int, 
        default=8765,
        help="Server port (default: 8765)"
    )
    
    parser.add_argument(
        "--name", 
        type=str, 
        default="Player",
        help="Player name (default: Player)"
    )
    
    parser.add_argument(
        "--load-level",
        type=str,
        default=None,
        help="Load level from JSON file"
    )
    
    parser.add_argument(
        "--fullscreen",
        action="store_true",
        help="Start in fullscreen mode"
    )
    
    args = parser.parse_args()
    
    # Create engine
    engine = GameEngine(
        screen_width=args.width,
        screen_height=args.height,
        title=args.title
    )
    
    # Load level if specified
    if args.load_level:
        if os.path.exists(args.load_level):
            try:
                import json
                with open(args.load_level, 'r') as f:
                    level_data = json.load(f)
                engine.load_level(level_data)
                print(f"Loaded level from {args.load_level}")
            except Exception as e:
                print(f"Error loading level: {e}")
        else:
            print(f"Level file not found: {args.load_level}")
    
    # Enable multiplayer if requested
    if args.multiplayer:
        print(f"Connecting to server at {args.host}:{args.port}...")
        engine.set_multiplayer(
            host=args.host,
            port=args.port,
            player_name=args.name
        )
    else:
        print("Starting in single-player mode")
        print("Use --multiplayer to enable multiplayer")
    
    print("\nControls:")
    print("  WASD or Arrow Keys - Move")
    print("  ESC - Quit")
    print("=" * 60)
    
    # Run game
    engine.run()


if __name__ == "__main__":
    main()
