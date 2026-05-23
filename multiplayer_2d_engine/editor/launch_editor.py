#!/usr/bin/env python3
"""
Editor Launcher
Launch the level editor
"""

import argparse
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from editor.level_editor import run_editor


def main():
    parser = argparse.ArgumentParser(
        description="2D Game Level Editor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                              # Start editor with default settings
  %(prog)s --width 1920 --height 1080   # Custom resolution
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
        "--load",
        type=str,
        default=None,
        help="Load existing level file"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("       2D GAME LEVEL EDITOR")
    print("=" * 60)
    print(f"Resolution: {args.width}x{args.height}")
    
    if args.load:
        print(f"Loading level: {args.load}")
    
    print("\nControls:")
    print("  Left Click - Select/Create objects")
    print("  Drag - Move objects / Pan camera")
    print("  WASD/Arrows - Pan camera")
    print("  +/- - Zoom in/out")
    print("  G - Toggle grid")
    print("  Delete/Backspace - Delete selected object")
    print("  ESC - Deselect")
    print("=" * 60)
    
    # Run editor
    run_editor()


if __name__ == "__main__":
    main()
