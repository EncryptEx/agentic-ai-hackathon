import asyncio
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from app.fast_api_app import app

def main():
    client = TestClient(app)
    with client.websocket_connect("/ws/transactions") as websocket:
        data = websocket.receive_text()
        print("Received:", data)
        data = websocket.receive_text()
        print("Received:", data)

main()
