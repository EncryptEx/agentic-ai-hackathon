"""Synthetic scenarios and data fixtures for EvidenceTrail.
All data is strictly synthetic for hackathon demonstration.
"""

from typing import Dict, Any, List
import datetime

SCENARIOS: Dict[str, Dict[str, Any]] = {
    "case-1": {
        "id": "case-1",
        "title": "Familiar Payment (600 SEK)",
        "subtitle": "Routine transfer to recurring contact",
        "expected_action": "ALLOW",
        "customer": {
            "id": "CUST-1042",
            "name": "Alice Lindqvist",
            "age": 34,
            "account_created": "2021-04-12",
            "typical_min": 200,
            "typical_max": 2000,
            "known_recipients": ["REC-441", "REC-109", "REC-873"],
            "known_devices": ["DEV-901"]
        },
        "transaction": {
            "id": "TX-8901",
            "amount": 600,
            "currency": "SEK",
            "timestamp": "2026-10-03T11:45:00Z",
            "recipient_id": "REC-441",
            "recipient_name": "Erik Berg",
            "device_id": "DEV-901",
            "auth_type": "BankID_Biometric",
            "channel": "MobileApp"
        },
        "device": {
            "id": "DEV-901",
            "fingerprint": "fp_ios_18_iphone15_trusted",
            "is_known": True,
            "first_seen": "2023-09-15",
            "os": "iOS 18.2",
            "session_anomalies": []
        },
        "recipient": {
            "id": "REC-441",
            "name": "Erik Berg",
            "account_age_days": 820,
            "incoming_transfers_90min": 1,
            "total_incoming_volume_today": 600,
            "synthetic_flags": []
        },
        "graph": {
            "nodes": [
                {"id": "CUST-1042", "label": "Alice Lindqvist (Payer)", "type": "customer", "risk": "low"},
                {"id": "REC-441", "label": "Erik Berg (Recipient)", "type": "recipient", "risk": "low"},
                {"id": "DEV-901", "label": "Alice's iPhone 15", "type": "device", "risk": "low"}
            ],
            "links": [
                {"source": "CUST-1042", "target": "DEV-901", "relation": "authenticated_with"},
                {"source": "CUST-1042", "target": "REC-441", "relation": "regular_transfers_x12"}
            ]
        }
    },
    "case-2": {
        "id": "case-2",
        "title": "Account Takeover (8,000 SEK)",
        "subtitle": "New device + synthetic session anomaly",
        "expected_action": "REVIEW",
        "customer": {
            "id": "CUST-2089",
            "name": "Johan Holm",
            "age": 47,
            "account_created": "2019-11-03",
            "typical_min": 300,
            "typical_max": 3500,
            "known_recipients": ["REC-312", "REC-889"],
            "known_devices": ["DEV-204"]
        },
        "transaction": {
            "id": "TX-8902",
            "amount": 8000,
            "currency": "SEK",
            "timestamp": "2026-10-03T11:58:00Z",
            "recipient_id": "REC-902",
            "recipient_name": "Digital Vault AB",
            "device_id": "DEV-334",
            "auth_type": "SMS_OTP_Fallback",
            "channel": "WebBrowser"
        },
        "device": {
            "id": "DEV-334",
            "fingerprint": "fp_win_headless_chrome_suspicious",
            "is_known": False,
            "first_seen": "2026-10-03T11:50:00Z (8 min ago)",
            "os": "Windows 11 / Automated Chromium",
            "session_anomalies": [
                "IP geolocation jump from Stockholm to Frankfurt within 4 minutes (impossible travel)",
                "User-Agent indicates headless browser environment",
                "Password reset completed 6 minutes prior to transaction"
            ]
        },
        "recipient": {
            "id": "REC-902",
            "name": "Digital Vault AB",
            "account_age_days": 12,
            "incoming_transfers_90min": 4,
            "total_incoming_volume_today": 32000,
            "synthetic_flags": ["New business account with rapid volume increase"]
        },
        "graph": {
            "nodes": [
                {"id": "CUST-2089", "label": "Johan Holm (Payer)", "type": "customer", "risk": "low"},
                {"id": "DEV-334", "label": "Unknown Device (Frankfurt IP)", "type": "device", "risk": "high"},
                {"id": "REC-902", "label": "Digital Vault AB", "type": "recipient", "risk": "medium"}
            ],
            "links": [
                {"source": "CUST-2089", "target": "DEV-334", "relation": "session_anomaly_detected"},
                {"source": "DEV-334", "target": "REC-902", "relation": "funds_routing"}
            ]
        }
    },
    "case-3": {
        "id": "case-3",
        "title": "Manipulated Payer / Safe Account Scam (24,500 SEK)",
        "subtitle": "Authorised push payment with social engineering signals",
        "expected_action": "CONTEXT_CHECK",
        "customer": {
            "id": "CUST-3912",
            "name": "Elin Nygren",
            "age": 62,
            "account_created": "2018-02-19",
            "typical_min": 200,
            "typical_max": 2000,
            "known_recipients": ["REC-119", "REC-442", "REC-991"],
            "known_devices": ["DEV-112"]
        },
        "transaction": {
            "id": "TX-8903",
            "amount": 24500,
            "currency": "SEK",
            "timestamp": "2026-10-03T12:10:00Z",
            "recipient_id": "REC-558",
            "recipient_name": "Säkerhetskonto Nord (Security Hold)",
            "device_id": "DEV-112",
            "auth_type": "BankID_Biometric",
            "channel": "MobileApp"
        },
        "device": {
            "id": "DEV-112",
            "fingerprint": "fp_ios_17_iphone13_trusted",
            "is_known": True,
            "first_seen": "2022-06-11",
            "os": "iOS 17.5",
            "session_anomalies": []
        },
        "recipient": {
            "id": "REC-558",
            "name": "Säkerhetskonto Nord (Security Hold)",
            "account_age_days": 3,
            "incoming_transfers_90min": 14,
            "total_incoming_volume_today": 342000,
            "synthetic_flags": [
                "High-velocity mule burst pattern: 14 incoming transfers in 90 minutes",
                "Account title mimics official bank security terminology ('Säkerhetskonto Nord')"
            ]
        },
        "graph": {
            "nodes": [
                {"id": "CUST-3912", "label": "Elin Nygren (Payer)", "type": "customer", "risk": "low"},
                {"id": "DEV-112", "label": "Elin's Trusted iPhone 13", "type": "device", "risk": "low"},
                {"id": "REC-558", "label": "Säkerhetskonto Nord (Mule)", "type": "recipient", "risk": "high"},
                {"id": "DEV-SHARED-88", "label": "Shared Device #88 (Android emulator)", "type": "device", "risk": "critical"},
                {"id": "REC-FLAGGED-09", "label": "Flagged Account #09 (Prior fraud report)", "type": "recipient", "risk": "critical"}
            ],
            "links": [
                {"source": "CUST-3912", "target": "DEV-112", "relation": "authenticated_with"},
                {"source": "CUST-3912", "target": "REC-558", "relation": "pending_transfer_24500"},
                {"source": "REC-558", "target": "DEV-SHARED-88", "relation": "shared_login_telemetry"},
                {"source": "DEV-SHARED-88", "target": "REC-FLAGGED-09", "relation": "linked_mule_cluster"}
            ]
        }
    }
}

# Live Stream Feed for demonstrating Tier-0 Identification vs Tier-1 Investigation
STREAM_FEED: List[Dict[str, Any]] = [
    {
        "id": "TX-1001",
        "timestamp": "2026-10-03T12:08:12Z",
        "payer_name": "Marcus Lind",
        "payer_id": "CUST-5501",
        "amount": 48,
        "currency": "SEK",
        "channel": "Swish",
        "recipient_name": "Espresso House",
        "recipient_id": "REC-CORP-01",
        "device": "Trusted iPhone 14",
        "tier0_status": "PASS",
        "tier0_latency_ms": 1.2,
        "tier0_reason": "Routine merchant transfer within baseline envelope (20-500 SEK)",
        "case_id": None
    },
    {
        "id": "TX-8901",
        "timestamp": "2026-10-03T12:08:44Z",
        "payer_name": "Alice Lindqvist",
        "payer_id": "CUST-1042",
        "amount": 600,
        "currency": "SEK",
        "channel": "MobileApp",
        "recipient_name": "Erik Berg",
        "recipient_id": "REC-441",
        "device": "Alice's iPhone 15",
        "tier0_status": "PASS",
        "tier0_latency_ms": 1.4,
        "tier0_reason": "Known recurring recipient (x12 past transfers) within typical range (200-2,000 SEK)",
        "case_id": "case-1"
    },
    {
        "id": "TX-1003",
        "timestamp": "2026-10-03T12:09:15Z",
        "payer_name": "Sofia Ekström",
        "payer_id": "CUST-4110",
        "amount": 1420,
        "currency": "SEK",
        "channel": "Card_POS",
        "recipient_name": "ICA Kvantum",
        "recipient_id": "REC-CORP-44",
        "device": "Trusted Samsung S23",
        "tier0_status": "PASS",
        "tier0_latency_ms": 1.1,
        "tier0_reason": "Verified corporate merchant with typical weekly grocery cadence",
        "case_id": None
    },
    {
        "id": "TX-8903",
        "timestamp": "2026-10-03T12:10:00Z",
        "payer_name": "Elin Nygren",
        "payer_id": "CUST-3912",
        "amount": 24500,
        "currency": "SEK",
        "channel": "MobileApp",
        "recipient_name": "Säkerhetskonto Nord (Security Hold)",
        "recipient_id": "REC-558",
        "device": "Elin's iPhone 13 (Biometric)",
        "tier0_status": "FLAGGED_ANOMALY",
        "tier0_latency_ms": 1.8,
        "tier0_reason": "TIER-0 BREACH: Amount spike (12.2x normal max) to newly created unverified counterparty -> ESCALATING TO EVIDENCE_TRAIL",
        "case_id": "case-3"
    },
    {
        "id": "TX-8902",
        "timestamp": "2026-10-03T12:10:48Z",
        "payer_name": "Johan Holm",
        "payer_id": "CUST-2089",
        "amount": 8000,
        "currency": "SEK",
        "channel": "WebBrowser",
        "recipient_name": "Digital Vault AB",
        "recipient_id": "REC-902",
        "device": "Unknown Device (Frankfurt IP)",
        "tier0_status": "FLAGGED_ANOMALY",
        "tier0_latency_ms": 1.5,
        "tier0_reason": "TIER-0 BREACH: Impossible travel telemetry (Stockholm -> Frankfurt in 4 min) + headless browser -> ESCALATING TO EVIDENCE_TRAIL",
        "case_id": "case-2"
    }
]

import random

class LiveStreamEngine:
    """Simulates high-throughput Tier-0 real-time payment ingestion and anomaly screening."""
    _tx_counter = 9100
    _active_stream = list(STREAM_FEED)

    SAMPLE_PAYERS = [
        {"name": "Lars Svensson", "id": "CUST-6102", "device": "iPhone 14 Pro", "typical": (100, 1500)},
        {"name": "Emma Nilsson", "id": "CUST-7210", "device": "Google Pixel 8", "typical": (50, 900)},
        {"name": "Oskar Lindgren", "id": "CUST-8334", "device": "Samsung S24", "typical": (150, 2200)},
        {"name": "Astrid Blom", "id": "CUST-9441", "device": "iPhone 13 mini", "typical": (80, 1200)},
        {"name": "Viktor Dahl", "id": "CUST-1552", "device": "MacBook Air M3", "typical": (200, 3000)}
    ]

    SAMPLE_MERCHANTS = [
        ("Pressbyrån T-Centralen", "REC-M01", "Swish", 65),
        ("SL Lokaltrafik Biljett", "REC-M02", "Contactless_NFC", 42),
        ("H&M Drottninggatan", "REC-M03", "Card_POS", 499),
        ("Spotify Premium Sweden", "REC-M04", "Autogiro", 169),
        ("Klarna Checkout AB", "REC-M05", "Online_Ecom", 850),
        ("Apoteket Hjärtat", "REC-M06", "Card_POS", 215),
        ("Elgiganten Megastore", "REC-M07", "Online_Ecom", 1490)
    ]

    @classmethod
    def get_latest_stream(cls, limit: int = 15) -> List[Dict[str, Any]]:
        return cls._active_stream[-limit:]

    @classmethod
    def generate_routine_tx(cls) -> Dict[str, Any]:
        cls._tx_counter += 1
        tx_id = f"TX-{cls._tx_counter}"
        payer = random.choice(cls.SAMPLE_PAYERS)
        merchant, rec_id, channel, base_amt = random.choice(cls.SAMPLE_MERCHANTS)
        amt = int(base_amt * random.uniform(0.8, 1.4))
        
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        latency = round(random.uniform(0.9, 1.4), 1)

        item = {
            "id": tx_id,
            "timestamp": now_iso,
            "payer_name": payer["name"],
            "payer_id": payer["id"],
            "amount": amt,
            "currency": "SEK",
            "channel": channel,
            "recipient_name": merchant,
            "recipient_id": rec_id,
            "device": payer["device"],
            "tier0_status": "PASS",
            "tier0_latency_ms": latency,
            "tier0_reason": f"Routine transfer within baseline envelope ({payer['typical'][0]}-{payer['typical'][1]} SEK)",
            "case_id": None
        }
        cls._active_stream.append(item)
        if len(cls._active_stream) > 100:
            cls._active_stream.pop(0)
        return item

    @classmethod
    def inject_case_tx(cls, case_id: str) -> Dict[str, Any]:
        if case_id not in SCENARIOS:
            raise ValueError(f"Unknown case_id: {case_id}")
        sc = SCENARIOS[case_id]
        cls._tx_counter += 1
        tx_id = f"TX-{cls._tx_counter}"
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        status = "FLAGGED_ANOMALY" if sc["expected_action"] in ["REVIEW", "CONTEXT_CHECK"] else "PASS"
        latency = round(random.uniform(1.4, 1.9), 1) if status == "FLAGGED_ANOMALY" else round(random.uniform(1.0, 1.3), 1)

        item = {
            "id": tx_id,
            "timestamp": now_iso,
            "payer_name": sc["customer"]["name"],
            "payer_id": sc["customer"]["id"],
            "amount": sc["transaction"]["amount"],
            "currency": sc["transaction"]["currency"],
            "channel": sc["transaction"].get("channel", "MobileApp"),
            "recipient_name": sc["recipient"]["name"],
            "recipient_id": sc["recipient"]["id"],
            "device": sc["device"]["id"],
            "tier0_status": status,
            "tier0_latency_ms": latency,
            "tier0_reason": f"TIER-0 {'BREACH: Escalate to EvidenceTrail' if status == 'FLAGGED_ANOMALY' else 'PASS: Baseline validated'}",
            "case_id": case_id
        }
        cls._active_stream.append(item)
        if len(cls._active_stream) > 100:
            cls._active_stream.pop(0)
        return item


