import asyncio
import csv
import json
import logging
import os
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Real-Time Data Streaming API",
    description="Streams synthetic CSV data (e.g. transactions) for agentic swarms to process in real-time.",
    version="1.0.0",
)

DATA_FILE = os.environ.get("TRANSACTIONS_CSV", "../exports/transactions.csv")

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Client connected. Active connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"Client disconnected. Active connections: {len(self.active_connections)}")

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"Failed to send to client: {e}")

manager = ConnectionManager()

@app.get("/")
async def root():
    # Serve a simple dashboard to view the incoming stream
    html_path = os.path.join(os.path.dirname(__file__), "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return {"message": "Welcome to the Real-Time Streaming Layer. Connect to /ws/transactions to receive the data stream."}

@app.websocket("/ws/transactions")
async def websocket_transactions(websocket: WebSocket, speed_ms: int = 1000):
    """
    WebSocket endpoint that streams rows from the transactions CSV.
    :param speed_ms: Time in milliseconds to wait between sending each row (simulating real-time).
    """
    await manager.connect(websocket)
    try:
        if not os.path.exists(DATA_FILE):
            await websocket.send_text(json.dumps({"error": f"Data file {DATA_FILE} not found."}))
            return

        with open(DATA_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            # Send events iteratively
            for row in reader:
                # We could perform sorting by timestamp if needed, but for now we stream as-is
                payload = json.dumps(row)
                await websocket.send_text(payload)
                await asyncio.sleep(speed_ms / 1000.0)
                
        await websocket.send_text(json.dumps({"status": "Stream completed."}))
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"Error in websocket stream: {e}")
        manager.disconnect(websocket)
