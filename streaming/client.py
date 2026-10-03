import asyncio
import websockets
import json
import argparse
from rich.console import Console

console = Console()

async def listen_to_stream(url: str):
    console.print(f"[bold green]Connecting to {url}...[/bold green]")
    try:
        async with websockets.connect(url) as websocket:
            console.print("[bold green]Connected! Listening for transactions...[/bold green]")
            while True:
                message = await websocket.recv()
                data = json.loads(message)
                if "error" in data:
                    console.print(f"[bold red]Error from server: {data['error']}[/bold red]")
                    break
                if "status" in data and data["status"] == "Stream completed.":
                    console.print("[bold yellow]Server finished streaming.[/bold yellow]")
                    break
                
                # Format output nicely for the user
                console.print(
                    f"🟢 [cyan]{data.get('timestamp')}[/cyan] | "
                    f"TXN: [bold]{data.get('transaction_id')}[/bold] | "
                    f"AMT: [red]{data.get('amount_usd')} {data.get('currency')}[/red] | "
                    f"TYPE: {data.get('transaction_type')} | "
                    f"FRAUD_FLAG: {data.get('is_fraud_synthetic')}"
                )
    except Exception as e:
        console.print(f"[bold red]Connection closed or failed: {e}[/bold red]")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Consume real-time transaction stream.")
    parser.add_argument("--url", default="ws://localhost:8000/ws/transactions?speed_ms=500", help="WebSocket URL")
    args = parser.parse_args()
    
    asyncio.run(listen_to_stream(args.url))
