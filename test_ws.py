import asyncio
import websockets

async def test():
    try:
        async with websockets.connect('ws://localhost:8000/ws/transactions?speed_ms=10') as websocket:
            for i in range(5):
                message = await websocket.recv()
                print(f"Received: {message[:100]}...")
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(test())
