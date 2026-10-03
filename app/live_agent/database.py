"""Database Information and Dynamic Question Bank Module for EvidenceTrail.
Connects to SQLite KYC/AML database and provides the structured agent interrogation bank.
"""

import os
import sqlite3
import json
import datetime
from typing import Dict, Any, List, Optional

# Search paths for the SQLite database
DB_CANDIDATE_PATHS = [
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "kyc_aml.db")),
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "agentic-ai-hackathon", "data", "kyc_aml.db")),
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "agentic-ai-hackathon", "kyc_aml.db")),
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "evidencetrail.db")),
]

def get_db_connection() -> sqlite3.Connection:
    target_path = None
    for p in DB_CANDIDATE_PATHS:
        if os.path.exists(p) and os.path.getsize(p) > 0:
            target_path = p
            break
    
    if not target_path:
        # Fallback to local database in backend directory
        target_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "evidencetrail.db"))
        os.makedirs(os.path.dirname(target_path), exist_ok=True)

    conn = sqlite3.connect(target_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_question_bank_tables():
    """Initializes tables for question bank and inquiry audit logs."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # 1. Investigation Question Bank Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS investigation_question_bank (
            question_id TEXT PRIMARY KEY,
            typology TEXT NOT NULL,
            category TEXT NOT NULL,
            prompt_title TEXT NOT NULL,
            prompt_question TEXT NOT NULL,
            severity_weight REAL DEFAULT 1.0,
            options_json TEXT NOT NULL
        )
        """)

        # 2. Customer Inquiry Audit Log Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS customer_inquiry_log (
            inquiry_id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id TEXT NOT NULL,
            transaction_id TEXT NOT NULL,
            question_id TEXT NOT NULL,
            selected_option_key TEXT NOT NULL,
            customer_statement TEXT NOT NULL,
            impact_level TEXT NOT NULL,
            evidence_id TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """)

        # Populate standard question fixtures if empty
        cursor.execute("SELECT count(*) FROM investigation_question_bank")
        count = cursor.fetchone()[0]
        if count == 0:
            questions = [
                (
                    "Q_APP_SCAM_SAFE_ACCOUNT",
                    "MANIPULATED_PAYER",
                    "Authorised Push Payment (APP) / Safe Account Scam",
                    "Payer Coercion & Social Engineering Verification",
                    "Has anyone claiming to be bank security, the police, or a trusted organization instructed you to move funds to a 'safe account', keep this transfer secret, or act urgently?",
                    0.95,
                    json.dumps([
                        {
                            "key": "COERCED_PHONE",
                            "label": "Yes, I was told by phone to protect my money in a safe account",
                            "statement": "Customer confirms active voice social engineering: instructed by an impersonator to execute an urgent transfer to a designated 'safe holding account'.",
                            "risk_verdict": "CONFIRMED_COERCION",
                            "recommended_action": "REVIEW",
                            "badge_color": "rose"
                        },
                        {
                            "key": "VOLUNTARY_PERSONAL",
                            "label": "No, this is my own voluntary transfer to a familiar contact",
                            "statement": "Customer explicitly asserts voluntary intent for personal remittance without third-party caller instructions.",
                            "risk_verdict": "VOLUNTARY_UNCOERCED",
                            "recommended_action": "ALLOW",
                            "badge_color": "emerald"
                        },
                        {
                            "key": "ONLINE_INVESTMENT",
                            "label": "I was guided by an online advisor/broker promising high yields",
                            "statement": "Customer indicates online investment solicitation with promised returns, characteristic of boiler room scam.",
                            "risk_verdict": "INVESTMENT_TRAP",
                            "recommended_action": "REVIEW",
                            "badge_color": "amber"
                        }
                    ])
                ),
                (
                    "Q_ATO_UNRECOGNIZED_SESSION",
                    "ACCOUNT_TAKEOVER",
                    "Account Takeover / Unrecognized Session Telemetry",
                    "Device Authorization & Identity Verification",
                    "We detected this transaction from an unrecognized browser in Frankfurt following a password change. Did you authorize this device and initiate this transfer?",
                    0.98,
                    json.dumps([
                        {
                            "key": "ATO_UNAUTHORIZED",
                            "label": "No! I have not logged in from Frankfurt or changed my password",
                            "statement": "Customer repudiates transaction and session origin; credential compromise and unauthorized account takeover confirmed.",
                            "risk_verdict": "CONFIRMED_ATO",
                            "recommended_action": "REVIEW",
                            "badge_color": "rose"
                        },
                        {
                            "key": "ATO_AUTHORIZED_TRAVEL",
                            "label": "Yes, I am traveling with a new laptop and changed my password myself",
                            "statement": "Customer verifies physical travel and legitimate ownership of the new device session.",
                            "risk_verdict": "AUTHORIZED_LEGITIMATE",
                            "recommended_action": "ALLOW",
                            "badge_color": "emerald"
                        }
                    ])
                ),
                (
                    "Q_INVOICE_REDIRECT_BEC",
                    "INVOICE_MANIPULATION",
                    "Business Email Compromise & Supplier Account Change",
                    "Counterparty Invoice & Account Detail Verification",
                    "Did this recipient recently notify you of changed bank account details via email, text message, or messaging app?",
                    0.90,
                    json.dumps([
                        {
                            "key": "INVOICE_MODIFIED",
                            "label": "Yes, they sent updated payment details via email yesterday",
                            "statement": "Customer confirms recently modified banking details received via unverified email channel (classic Invoice BEC signal).",
                            "risk_verdict": "SUSPECTED_INVOICE_INTERCEPTION",
                            "recommended_action": "REVIEW",
                            "badge_color": "rose"
                        },
                        {
                            "key": "INVOICE_STANDING",
                            "label": "No, these are longstanding verified bank details",
                            "statement": "Customer confirms historical verified invoice remittance.",
                            "risk_verdict": "VERIFIED_SUPPLIER",
                            "recommended_action": "ALLOW",
                            "badge_color": "emerald"
                        }
                    ])
                )
            ]
            cursor.executemany("""
            INSERT INTO investigation_question_bank 
            (question_id, typology, category, prompt_title, prompt_question, severity_weight, options_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, questions)
            conn.commit()
    finally:
        conn.close()

# Initialize tables on module import
init_question_bank_tables()

class DatabaseInformationService:
    """Provides querying of database profiles and question bank intelligence."""

    @staticmethod
    def get_all_questions() -> List[Dict[str, Any]]:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM investigation_question_bank")
            rows = cursor.fetchall()
            result = []
            for r in rows:
                result.append({
                    "question_id": r["question_id"],
                    "typology": r["typology"],
                    "category": r["category"],
                    "prompt_title": r["prompt_title"],
                    "prompt_question": r["prompt_question"],
                    "severity_weight": r["severity_weight"],
                    "options": json.loads(r["options_json"])
                })
            return result
        finally:
            conn.close()

    @staticmethod
    def get_question_by_id(question_id: str) -> Optional[Dict[str, Any]]:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM investigation_question_bank WHERE question_id = ?", (question_id,))
            r = cursor.fetchone()
            if not r:
                return None
            return {
                "question_id": r["question_id"],
                "typology": r["typology"],
                "category": r["category"],
                "prompt_title": r["prompt_title"],
                "prompt_question": r["prompt_question"],
                "severity_weight": r["severity_weight"],
                "options": json.loads(r["options_json"])
            }
        finally:
            conn.close()

    @staticmethod
    def get_question_for_scenario(case_id: str) -> Dict[str, Any]:
        """Dynamically picks the diagnostic interrogation question for a scenario."""
        if case_id == "case-2":
            q = DatabaseInformationService.get_question_by_id("Q_ATO_UNRECOGNIZED_SESSION")
        elif case_id == "case-3":
            q = DatabaseInformationService.get_question_by_id("Q_APP_SCAM_SAFE_ACCOUNT")
        else:
            q = DatabaseInformationService.get_question_by_id("Q_APP_SCAM_SAFE_ACCOUNT")
        
        return q or DatabaseInformationService.get_all_questions()[0]

    @staticmethod
    def log_customer_inquiry(case_id: str, tx_id: str, question_id: str, option_key: str, statement: str, impact: str, evidence_id: str):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO customer_inquiry_log 
            (case_id, transaction_id, question_id, selected_option_key, customer_statement, impact_level, evidence_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (case_id, tx_id, question_id, option_key, statement, impact, evidence_id, datetime.datetime.now(datetime.timezone.utc).isoformat()))
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def get_customer_profile(customer_id: str) -> Optional[Dict[str, Any]]:
        """Queries customer KYC/AML attributes from SQLite if present."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            # Check if customers table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='customers';")
            if not cursor.fetchone():
                return None
            
            cursor.execute("SELECT * FROM customers WHERE customer_id = ?", (customer_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
        finally:
            conn.close()
