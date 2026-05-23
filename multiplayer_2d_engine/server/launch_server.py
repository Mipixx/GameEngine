#!/usr/bin/env python3
"""
Server Launcher Utility
Command-line utility to start the game server with options
"""

import argparse
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.game_server import run_server


def main():
    parser = argparse.ArgumentParser(
        description="Multiplayer 2D Game Server Launcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Start server on default port 8765
  %(prog)s --port 9000              # Start server on port 9000
  %(prog)s --host 192.168.1.100     # Bind to specific IP
  %(prog)s --public                 # Make server publicly accessible
        """
    )
    
    parser.add_argument(
        "--host", 
        type=str, 
        default="0.0.0.0",
        help="Host address to bind to (default: 0.0.0.0 - all interfaces)"
    )
    
    parser.add_argument(
        "--port", 
        type=int, 
        default=8765,
        help="Port to listen on (default: 8765)"
    )
    
    parser.add_argument(
        "--public",
        action="store_true",
        help="Make server publicly accessible (binds to 0.0.0.0)"
    )
    
    parser.add_argument(
        "--localhost",
        action="store_true",
        help="Only allow local connections (binds to 127.0.0.1)"
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output"
    )
    
    args = parser.parse_args()
    
    # Determine host
    if args.localhost:
        host = "127.0.0.1"
    elif args.public:
        host = "0.0.0.0"
    else:
        host = args.host
    
    # Print server info
    print("=" * 60)
    print("       MULTIPLAYER 2D GAME SERVER")
    print("=" * 60)
    print(f"Host: {host}")
    print(f"Port: {args.port}")
    print(f"Address: ws://{host}:{args.port}")
    
    if host == "0.0.0.0":
        print("\n[INFO] Server is publicly accessible")
        print("       Players can connect from other machines")
    elif host == "127.0.0.1":
        print("\n[INFO] Server is localhost only")
        print("       Only players on this machine can connect")
    else:
        print(f"\n[INFO] Server bound to {host}")
    
    print("\nControls:")
    print("  Press Ctrl+C to stop the server")
    print("=" * 60)
    print()
    
    if args.verbose:
        print("[DEBUG] Starting server...")
    
    try:
        run_server(host, args.port)
    except KeyboardInterrupt:
        print("\n\n[INFO] Server shutdown requested")
    except Exception as e:
        print(f"\n[ERROR] Server failed to start: {e}")
        sys.exit(1)
    
    print("[INFO] Server stopped")


if __name__ == "__main__":
    main()
