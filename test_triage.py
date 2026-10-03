import asyncio
import json
from evidencetrail.jev import JevClient, ALERT_QUESTIONS, ProviderUnavailable

async def main():
    jev_client = JevClient()
    if not jev_client.available():
        print("Jev is not available!")
        return

    row = {"customer_id": "CUST123", "amount": 9000, "counterparty_name": "Bob"}
    # The state should be plain text
    state = f"type=transaction source=realtime payload={json.dumps(row)}"
    
    try:
        res = await asyncio.to_thread(jev_client.assess, state, ALERT_QUESTIONS)
        print(json.dumps(res, indent=2))
    except ProviderUnavailable as e:
        print(f"Jev error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
