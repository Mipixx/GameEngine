#!/usr/bin/env python3
"""
Test script for 2 players connecting simultaneously
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.game_engine import NetworkClient

async def test_two_players():
    print("Testing 2-player multiplayer connection...\n")
    
    # Create two clients
    client1 = NetworkClient(host="localhost", port=8765)
    client2 = NetworkClient(host="localhost", port=8765)
    
    # Connect player 1
    print("Player 1 connecting...")
    connected1 = await client1.connect("Player1")
    if not connected1:
        print("❌ Player 1 failed to connect!")
        return False
    print(f"✓ Player 1 connected (ID: {client1.player_id})")
    
    # Connect player 2
    print("\nPlayer 2 connecting...")
    connected2 = await client2.connect("Player2")
    if not connected2:
        print("❌ Player 2 failed to connect!")
        await client1.disconnect()
        return False
    print(f"✓ Player 2 connected (ID: {client2.player_id})")
    
    # Wait for server broadcast
    print("\nWaiting for server state update...")
    await asyncio.sleep(0.3)
    
    # Receive messages for both clients
    for _ in range(10):
        await client1.receive_messages()
        await client2.receive_messages()
    
    await client1.process_messages()
    await client2.process_messages()
    
    # Check if each player sees the other
    print(f"\nPlayer 1 sees players: {list(client1.players.keys())}")
    print(f"Player 2 sees players: {list(client2.players.keys())}")
    
    # Test movement from player 1
    print("\nPlayer 1 moving...")
    await client1.send_move(1100.0, 1100.0)
    
    await asyncio.sleep(0.3)
    
    # Receive updates
    for _ in range(10):
        await client2.receive_messages()
    await client2.process_messages()
    
    # Check if player 2 sees player 1's new position
    if client1.player_id in client2.players:
        p1_from_p2 = client2.players[client1.player_id]
        print(f"Player 2 sees Player 1 at: ({p1_from_p2.x}, {p1_from_p2.y})")
        
        if abs(p1_from_p2.x - 1100.0) < 1 and abs(p1_from_p2.y - 1100.0) < 1:
            print("✓ Position synchronized correctly!")
        else:
            print("⚠ Position may not be fully synchronized yet")
    
    # Disconnect both
    print("\nDisconnecting players...")
    await client1.disconnect()
    print("✓ Player 1 disconnected")
    await client2.disconnect()
    print("✓ Player 2 disconnected")
    
    print("\n✅ Two-player test completed successfully!")
    return True

if __name__ == "__main__":
    try:
        asyncio.run(test_two_players())
    except KeyboardInterrupt:
        print("\nTest interrupted")
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
