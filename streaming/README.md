# Real-Time Data Streaming Layer

This layer converts static CSV datasets (e.g. `transactions.csv`) into a real-time data stream using **WebSockets** and **FastAPI**. It is designed to act as the source of truth (the "firehose") for a swarm of AI agents investigating fraud, AML (Anti-Money Laundering), and risk in real-time.

## Setup

1. Ensure your virtual environment is active and dependencies are installed:
   ```bash
   pip install -r requirements.txt
   ```
   (We added `fastapi`, `uvicorn`, and `websockets` to `requirements.txt`).

## Running the Server

Start the streaming server using `uvicorn`:

```bash
cd streaming
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

The server will read the `exports/transactions.csv` file by default. You can point it to another file using the `TRANSACTIONS_CSV` environment variable.

## Consuming the Stream

You can connect to the stream with any WebSocket client. We've provided a simple Python client using `rich` for formatting.

Run it in a separate terminal:

```bash
cd streaming
python client.py --url "ws://localhost:8000/ws/transactions?speed_ms=1000"
```

The `speed_ms` query parameter controls the delay between rows (simulating real-time behavior).

## Agent Integration

For your future swarm of agents:
- Agents can independently connect to `ws://localhost:8000/ws/transactions` or you can have a "Router Agent" that consumes the WebSocket and delegates specific transactions to specialized agents (e.g., one agent for retail fraud, another for corporate AML).
- Because the data is sent as JSON over WebSockets, it seamlessly integrates with any language or framework (Python, Node.js, Go, etc.).
