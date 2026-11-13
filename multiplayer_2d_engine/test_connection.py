#!/usr/bin/env python3
"""
Quick test script for multiplayer connection
"""

import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.game_engine import NetworkClient, MessageType

async def test_connection():
    print("Testing multiplayer connection...")
    
    client = NetworkClient(host="localhost", port=8765)
    
    print("Connecting to server...")
    connected = await client.connect("TestPlayer")
    
    if not connected:
        print("❌ Failed to connect!")
        return False
    
    print("✓ Connected successfully!")
    print(f"  Player ID: {client.player_id}")
    print(f"  Players in game: {list(client.players.keys())}")
    
    # Test sending movement
    print("\nSending movement update...")
    await client.send_move(1050.0, 1050.0)
    print("✓ Movement sent!")
    
    # Wait for server broadcast
    print("\nWaiting for server state update...")
    await asyncio.sleep(0.5)
    
    # Receive and process messages
    for _ in range(10):
        await client.receive_messages()
    await client.process_messages()
    
    print(f"  Players after update: {list(client.players.keys())}")
    if client.player_id in client.players:
        player = client.players[client.player_id]
        print(f"  Local player position: ({player.x}, {player.y})")
    
    # Disconnect
    print("\nDisconnecting...")
    await client.disconnect()
    print("✓ Disconnected!")
    
    print("\n✅ All tests passed!")
    return True

if __name__ == "__main__":
    try:
        asyncio.run(test_connection())
    except KeyboardInterrupt:
        print("\nTest interrupted")
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
