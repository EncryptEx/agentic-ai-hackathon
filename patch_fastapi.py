import re

with open('app/fast_api_app.py', 'r') as f:
    content = f.read()

# Modify run_investigation_for_realtime to include structured data in the response
old_str = """
    await manager.broadcast(json.dumps({
        "msg_type": "investigation_finished",
        "customer_id": customer_id,
        "row": row,
        "report": final_report
    }))"""

new_str = """
    from storage.database import DatabaseManager
    db = DatabaseManager()
    cust_360 = db.get_customer_360(customer_id)
    
    score = 0
    tier = "UNKNOWN"
    typologies = []
    if cust_360:
        assessment = cust_360.get("assessment", {})
        if assessment:
            score = assessment.get("composite_score", 0)
            tier = assessment.get("risk_tier", "UNKNOWN")
        
        alerts = cust_360.get("alerts", []) + cust_360.get("fraud_alerts", [])
        typologies = [a.get("rule_name") or a.get("rule_id") for a in alerts]

    verdict = "ALLOW"
    if score >= 75: verdict = "BLOCK"
    elif score >= 50: verdict = "REVIEW"

    await manager.broadcast(json.dumps({
        "msg_type": "investigation_finished",
        "customer_id": customer_id,
        "row": row,
        "report": final_report,
        "score": score,
        "tier": tier,
        "typologies": typologies,
        "verdict": verdict
    }))"""

content = content.replace(old_str, new_str)
with open('app/fast_api_app.py', 'w') as f:
    f.write(content)

