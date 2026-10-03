import asyncio
from app.fast_api_app import triage_transaction

async def main():
    row = {"customer_id": "CUST123", "amount": 9000, "counterparty_name": "Bob"}
    await triage_transaction(row, None, "test")

asyncio.run(main())
