"""Database persistence and CSV/JSON export module with FRAML support."""

import sqlite3
import json
import os
import csv
from typing import List, Dict, Any, Optional
from models.customer import CustomerProfile
from models.transaction import Transaction
from models.risk_score import CustomerRiskAssessment

DEFAULT_DB_PATH = os.environ.get(
    "FIN_CRIME_DB_PATH",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "kyc_aml.db")
)

COUNTRY_RISK_SEEDS = [
    ("Democratic People's Republic of Korea", "KP", "critical", 100.0, "FATF Blacklist / Call for Action; proliferation financing."),
    ("Iran", "IR", "critical", 98.0, "FATF Blacklist / Comprehensive sanctions."),
    ("Myanmar", "MM", "critical", 95.0, "FATF Blacklist / Severe AML/CFT deficiencies."),
    ("Syria", "SY", "high", 85.0, "FATF Greylist / Ongoing conflict & TF risk."),
    ("Haiti", "HT", "high", 80.0, "FATF Greylist / Strategic AML/CFT deficiencies."),
    ("Yemen", "YE", "high", 80.0, "FATF Greylist / Conflict zone & TF exposure."),
    ("South Sudan", "SS", "high", 78.0, "FATF Greylist / Elevated corruption risk."),
    ("Panama", "PA", "high", 72.0, "Secrecy jurisdiction; limited beneficial-ownership transparency."),
    ("Cayman Islands", "KY", "high", 70.0, "Secrecy jurisdiction; offshore corporate veil."),
    ("British Virgin Islands", "VG", "high", 70.0, "Offshore secrecy / high corporate veil risk."),
    ("Bahamas", "BS", "high", 65.0, "Offshore financial secrecy haven."),
    ("Nigeria", "NG", "high", 68.0, "Elevated corruption and fraud exposure; limited AML enforcement."),
    ("Malta", "MT", "medium", 45.0, "EU member; layered corporate structures common."),
    ("Cyprus", "CY", "medium", 45.0, "EU member; historically used for holding structures."),
    ("Estonia", "EE", "medium", 40.0, "EU member; historically used for shell-company formation."),
    ("United Arab Emirates", "AE", "medium", 45.0, "Free-trade zones; variable beneficial-ownership transparency."),
    ("Italy", "IT", "low", 20.0, "EU member; standard AML framework."),
    ("Poland", "PL", "low", 20.0, "EU member; standard AML framework."),
    ("Switzerland", "CH", "low", 15.0, "Strong AML framework & banking oversight."),
    ("United States", "US", "low", 15.0, "FATF member / comprehensive AML framework."),
    ("United Kingdom", "GB", "low", 15.0, "FATF member / comprehensive AML framework."),
    ("Germany", "DE", "low", 15.0, "FATF member / robust regulatory supervision."),
]

class DatabaseManager:
    """Manages SQLite persistence and tabular exports for KYC, AML, & Fraud data."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._init_tables()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Customers Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                customer_id TEXT PRIMARY KEY,
                first_name TEXT,
                last_name TEXT,
                date_of_birth TEXT,
                age INTEGER,
                citizenship TEXT,
                dual_citizenship TEXT,
                residence_country TEXT,
                tax_residence_country TEXT,
                address_city TEXT,
                address_postal_code TEXT,
                address_line TEXT,
                occupation TEXT,
                occupation_risk_key TEXT,
                industry TEXT,
                employer_name TEXT,
                source_of_funds TEXT,
                source_of_wealth TEXT,
                annual_income_usd REAL,
                net_worth_usd REAL,
                declared_expected_monthly_turnover_usd REAL,
                declared_expected_max_single_tx_usd REAL,
                declared_purpose_nature TEXT,
                onboarding_channel TEXT,
                onboarding_date TEXT,
                products_held TEXT,
                pep_status TEXT,
                pep_details TEXT,
                adverse_media TEXT,
                adverse_media_details TEXT,
                sanction_status TEXT,
                sanction_details TEXT,
                email_address TEXT,
                email_domain_type TEXT,
                phone_number TEXT,
                phone_line_type TEXT,
                device_primary_id TEXT,
                primary_ip_address TEXT,
                primary_ip_country TEXT,
                synthetic_identity_score REAL,
                synthetic_id_indicators TEXT,
                archetype TEXT
            )
            """)

            # Transactions Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id TEXT PRIMARY KEY,
                customer_id TEXT,
                timestamp TEXT,
                transaction_type TEXT,
                direction TEXT,
                amount_usd REAL,
                currency TEXT,
                counterparty_name TEXT,
                counterparty_country TEXT,
                counterparty_account TEXT,
                counterparty_category TEXT,
                channel TEXT,
                reference_narrative TEXT,
                device_id TEXT,
                ip_address TEXT,
                ip_country TEXT,
                is_card_present INTEGER,
                card_entry_mode TEXT,
                auth_status TEXT,
                is_new_payee INTEGER,
                payee_first_seen_hours REAL,
                is_suspicious_synthetic INTEGER,
                synthetic_typology_tag TEXT,
                is_fraud_synthetic INTEGER,
                fraud_typology_tag TEXT,
                FOREIGN KEY (customer_id) REFERENCES customers (customer_id)
            )
            """)

            # Risk Assessments Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS risk_assessments (
                customer_id TEXT PRIMARY KEY,
                assessment_timestamp TEXT,
                composite_score REAL,
                risk_tier TEXT,
                kyc_raw_score REAL,
                kyc_weighted_score REAL,
                purpose_raw_score REAL,
                purpose_weighted_score REAL,
                product_raw_score REAL,
                product_weighted_score REAL,
                behavioral_raw_score REAL,
                behavioral_weighted_score REAL,
                fraud_raw_score REAL,
                fraud_weighted_score REAL,
                alert_count INTEGER,
                highest_alert_severity TEXT,
                fraud_alert_count INTEGER,
                highest_fraud_severity TEXT,
                aml_score REAL,
                fraud_score REAL,
                recommended_action TEXT,
                action_checklist TEXT,
                executive_summary TEXT,
                raw_assessment_json TEXT,
                FOREIGN KEY (customer_id) REFERENCES customers (customer_id)
            )
            """)

            # Unified Alerts Table (Both AML and Fraud)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                alert_id TEXT PRIMARY KEY,
                customer_id TEXT,
                alert_type TEXT,
                rule_id TEXT,
                rule_name TEXT,
                severity TEXT,
                score_impact REAL,
                summary TEXT,
                trigger_details TEXT,
                supporting_transaction_ids TEXT,
                status TEXT DEFAULT 'OPEN',
                investigation_notes TEXT,
                FOREIGN KEY (customer_id) REFERENCES customers (customer_id)
            )
            """)

            # Ownership Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS ownership (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id TEXT NOT NULL,
                entity TEXT NOT NULL,
                country TEXT,
                stake REAL,
                role TEXT NOT NULL,
                note TEXT,
                FOREIGN KEY (customer_id) REFERENCES customers (customer_id)
            )
            """)

            # Country Risk Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS country_risk (
                country TEXT PRIMARY KEY,
                country_code TEXT,
                rating TEXT NOT NULL,
                risk_score REAL,
                rationale TEXT
            )
            """)

            # Expected Activity Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS expected_activity (
                customer_id TEXT PRIMARY KEY,
                expected_monthly_volume REAL,
                expected_monthly_count INTEGER,
                description TEXT,
                max_single_tx_usd REAL,
                FOREIGN KEY (customer_id) REFERENCES customers (customer_id)
            )
            """)

            # Safety column additions for backwards compatibility if table existed
            def try_add_col(table, col, col_type):
                try:
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
                except sqlite3.OperationalError:
                    pass

            try_add_col("customers", "name", "TEXT")
            try_add_col("customers", "type", "TEXT DEFAULT 'individual'")
            try_add_col("customers", "country", "TEXT")
            try_add_col("customers", "onboarded", "TEXT")
            try_add_col("customers", "risk_rating", "TEXT")
            try_add_col("customers", "pep", "INTEGER DEFAULT 0")
            try_add_col("customers", "notes", "TEXT")
            try_add_col("customers", "email_address", "TEXT")
            try_add_col("customers", "email_domain_type", "TEXT")
            try_add_col("customers", "phone_number", "TEXT")
            try_add_col("customers", "phone_line_type", "TEXT")
            try_add_col("customers", "device_primary_id", "TEXT")
            try_add_col("customers", "primary_ip_address", "TEXT")
            try_add_col("customers", "primary_ip_country", "TEXT")
            try_add_col("customers", "synthetic_identity_score", "REAL")
            try_add_col("customers", "synthetic_id_indicators", "TEXT")

            try_add_col("transactions", "date", "TEXT")
            try_add_col("transactions", "kind", "TEXT")
            try_add_col("transactions", "amount", "REAL")
            try_add_col("transactions", "description", "TEXT")
            try_add_col("transactions", "device_id", "TEXT")
            try_add_col("transactions", "ip_address", "TEXT")
            try_add_col("transactions", "ip_country", "TEXT")
            try_add_col("transactions", "is_card_present", "INTEGER")
            try_add_col("transactions", "card_entry_mode", "TEXT")
            try_add_col("transactions", "auth_status", "TEXT")
            try_add_col("transactions", "is_new_payee", "INTEGER")
            try_add_col("transactions", "payee_first_seen_hours", "REAL")
            try_add_col("transactions", "is_fraud_synthetic", "INTEGER")
            try_add_col("transactions", "fraud_typology_tag", "TEXT")

            try_add_col("risk_assessments", "fraud_raw_score", "REAL")
            try_add_col("risk_assessments", "fraud_weighted_score", "REAL")
            try_add_col("risk_assessments", "fraud_alert_count", "INTEGER")
            try_add_col("risk_assessments", "highest_fraud_severity", "TEXT")
            try_add_col("risk_assessments", "aml_score", "REAL")
            try_add_col("risk_assessments", "fraud_score", "REAL")

            try_add_col("alerts", "alert_type", "TEXT")
            try_add_col("alerts", "status", "TEXT DEFAULT 'OPEN'")
            try_add_col("alerts", "investigation_notes", "TEXT")

            # Pre-seed country risk
            cursor.execute("SELECT COUNT(*) FROM country_risk")
            if cursor.fetchone()[0] == 0:
                for c_name, c_code, c_rating, c_score, c_rat in COUNTRY_RISK_SEEDS:
                    cursor.execute(
                        "INSERT OR IGNORE INTO country_risk (country, country_code, rating, risk_score, rationale) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (c_name, c_code, c_rating, c_score, c_rat)
                    )

            conn.commit()

    def reset_database(self):
        """Clears all tables cleanly."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DROP TABLE IF EXISTS alerts")
            cursor.execute("DROP TABLE IF EXISTS risk_assessments")
            cursor.execute("DROP TABLE IF EXISTS transactions")
            cursor.execute("DROP TABLE IF EXISTS customers")
            conn.commit()
        self._init_tables()

    def save_batch(
        self,
        customers: List[CustomerProfile],
        transactions_map: Dict[str, List[Transaction]],
        assessments: List[CustomerRiskAssessment]
    ):
        """Saves batch of customers, transactions, and risk scores transactionally."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Insert Customers
            for c in customers:
                full_name = f"{c.first_name} {c.last_name}".strip()
                res_country = c.residence_country or c.citizenship or "US"
                is_pep = 1 if c.pep_status.value in ("DOMESTIC_PEP", "FOREIGN_PEP", "PEP_ASSOCIATE") else 0
                matching_assess = next((a for a in assessments if a.customer_id == c.customer_id), None)
                risk_rating = matching_assess.risk_tier.value.lower() if matching_assess else "low"

                cursor.execute("""
                INSERT OR REPLACE INTO customers (
                    customer_id, first_name, last_name, date_of_birth, age,
                    citizenship, dual_citizenship, residence_country, tax_residence_country,
                    address_city, address_postal_code, address_line,
                    occupation, occupation_risk_key, industry, employer_name,
                    source_of_funds, source_of_wealth, annual_income_usd, net_worth_usd,
                    declared_expected_monthly_turnover_usd, declared_expected_max_single_tx_usd,
                    declared_purpose_nature, onboarding_channel, onboarding_date,
                    products_held, pep_status, pep_details,
                    adverse_media, adverse_media_details, sanction_status,
                    sanction_details, email_address, email_domain_type, phone_number, phone_line_type,
                    device_primary_id, primary_ip_address, primary_ip_country,
                    synthetic_identity_score, synthetic_id_indicators, archetype,
                    name, type, country, onboarded, risk_rating, pep, notes
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """, (
                    c.customer_id, c.first_name, c.last_name, c.date_of_birth, c.age,
                    c.citizenship, c.dual_citizenship, c.residence_country, c.tax_residence_country,
                    c.address_city, c.address_postal_code, c.address_line,
                    c.occupation, c.occupation_risk_key, c.industry, c.employer_name,
                    c.source_of_funds, c.source_of_wealth, c.annual_income_usd, c.net_worth_usd,
                    c.declared_expected_monthly_turnover_usd, c.declared_expected_max_single_tx_usd,
                    c.declared_purpose_nature, c.onboarding_channel, c.onboarding_date,
                    json.dumps(c.products_held), c.pep_status.value, c.pep_details,
                    c.adverse_media.value, c.adverse_media_details, c.sanction_status.value,
                    c.sanction_details,
                    c.email_address, c.email_domain_type, c.phone_number, c.phone_line_type,
                    c.device_primary_id, c.primary_ip_address, c.primary_ip_country,
                    c.synthetic_identity_score, json.dumps(c.synthetic_id_indicators),
                    c.archetype,
                    full_name, "individual", res_country, c.onboarding_date, risk_rating, is_pep,
                    f"Archetype: {c.archetype}. Purpose: {c.declared_purpose_nature}."
                ))

                # Expected Activity
                cursor.execute("""
                INSERT OR REPLACE INTO expected_activity VALUES (?, ?, ?, ?, ?)
                """, (
                    c.customer_id,
                    float(c.declared_expected_monthly_turnover_usd or 5000.0),
                    12,
                    c.declared_purpose_nature or "Personal retail account operations",
                    float(c.declared_expected_max_single_tx_usd or 2500.0)
                ))

                # Ownership structure (Beneficial owner and Employer)
                cursor.execute("DELETE FROM ownership WHERE customer_id = ?", (c.customer_id,))
                cursor.execute("""
                INSERT INTO ownership (customer_id, entity, country, stake, role, note)
                VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    c.customer_id, full_name, c.citizenship or res_country, 1.00,
                    "shareholder", "Individual retail account holder and 100% beneficial owner"
                ))
                if c.employer_name:
                    cursor.execute("""
                    INSERT INTO ownership (customer_id, entity, country, stake, role, note)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        c.customer_id, c.employer_name, res_country, None,
                        "employer", f"Employer ({c.occupation}, {c.industry})"
                    ))

            # Insert Transactions
            for cust_id, tx_list in transactions_map.items():
                for t in tx_list:
                    ts = t.timestamp or "2025-06-01T12:00:00"
                    dt = ts[:10]
                    desc = t.reference_narrative or t.counterparty_name or "Transaction"

                    cursor.execute("""
                    INSERT OR REPLACE INTO transactions (
                        transaction_id, customer_id, timestamp, transaction_type,
                        direction, amount_usd, currency, counterparty_name,
                        counterparty_country, counterparty_account, counterparty_category,
                        channel, reference_narrative,
                        device_id, ip_address, ip_country,
                        is_card_present, card_entry_mode, auth_status,
                        is_new_payee, payee_first_seen_hours,
                        is_suspicious_synthetic, synthetic_typology_tag,
                        is_fraud_synthetic, fraud_typology_tag,
                        date, kind, amount, description
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?
                    )
                    """, (
                        t.transaction_id, t.customer_id, t.timestamp, t.transaction_type.value,
                        t.direction.value, t.amount_usd, t.currency, t.counterparty_name,
                        t.counterparty_country, t.counterparty_account, t.counterparty_category,
                        t.channel, t.reference_narrative,
                        t.device_id, t.ip_address, t.ip_country,
                        1 if t.is_card_present else 0 if t.is_card_present is not None else None,
                        t.card_entry_mode, t.auth_status,
                        1 if t.is_new_payee else 0, t.payee_first_seen_hours,
                        1 if t.is_suspicious_synthetic else 0, t.synthetic_typology_tag,
                        1 if t.is_fraud_synthetic else 0, t.fraud_typology_tag,
                        dt, t.transaction_type.value.lower(), t.amount_usd, desc
                    ))

            # Insert Assessments and Alerts
            for a in assessments:
                cursor.execute("""
                INSERT OR REPLACE INTO risk_assessments VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """, (
                    a.customer_id, a.assessment_timestamp, a.composite_score, a.risk_tier.value,
                    a.kyc_pillar.raw_score, a.kyc_pillar.weighted_score,
                    a.purpose_pillar.raw_score, a.purpose_pillar.weighted_score,
                    a.product_pillar.raw_score, a.product_pillar.weighted_score,
                    a.behavioral_pillar.raw_score, a.behavioral_pillar.weighted_score,
                    a.fraud_pillar.raw_score, a.fraud_pillar.weighted_score,
                    a.alert_count, a.highest_alert_severity.value if a.highest_alert_severity else None,
                    a.fraud_alert_count, a.highest_fraud_severity.value if a.highest_fraud_severity else None,
                    a.aml_score, a.fraud_score,
                    a.recommended_action, json.dumps(a.action_checklist), a.executive_summary,
                    a.model_dump_json()
                ))

                # Insert AML Alerts
                for alt in a.alerts:
                    cursor.execute("""
                    INSERT OR REPLACE INTO alerts (
                        alert_id, customer_id, alert_type, rule_id, rule_name,
                        severity, score_impact, summary, trigger_details,
                        supporting_transaction_ids, status
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN'
                    )
                    """, (
                        alt.alert_id, a.customer_id, "AML", alt.rule_id, alt.rule_name,
                        alt.severity.value, alt.score_impact, alt.summary,
                        json.dumps(alt.trigger_details),
                        json.dumps(alt.supporting_transaction_ids)
                    ))

                # Insert Fraud Alerts
                for fa in a.fraud_alerts:
                    cursor.execute("""
                    INSERT OR REPLACE INTO alerts (
                        alert_id, customer_id, alert_type, rule_id, rule_name,
                        severity, score_impact, summary, trigger_details,
                        supporting_transaction_ids, status
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN'
                    )
                    """, (
                        fa.alert_id, a.customer_id, "FRAUD", fa.rule_id, fa.rule_name,
                        fa.severity.value, fa.score_impact, fa.summary,
                        json.dumps(fa.trigger_details),
                        json.dumps(fa.supporting_transaction_ids)
                    ))

            conn.commit()

    def get_portfolio_summary(self) -> Dict[str, Any]:
        """Returns statistics on portfolio risk distribution, AML alerts, and Fraud alerts."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM customers")
            total_customers = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM transactions")
            total_transactions = cursor.fetchone()[0]

            cursor.execute("""
            SELECT risk_tier, COUNT(*) as cnt, AVG(composite_score) as avg_score,
                   AVG(aml_score) as avg_aml, AVG(fraud_score) as avg_fraud
            FROM risk_assessments
            GROUP BY risk_tier
            """)
            tier_rows = cursor.fetchall()
            tier_stats = {
                r["risk_tier"]: {
                    "count": r["cnt"],
                    "avg_score": round(r["avg_score"] or 0, 2),
                    "avg_aml": round(r["avg_aml"] or 0, 2),
                    "avg_fraud": round(r["avg_fraud"] or 0, 2),
                } for r in tier_rows
            }

            cursor.execute("SELECT COUNT(*) FROM alerts WHERE alert_type = 'AML' OR alert_type IS NULL")
            total_aml_alerts = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM alerts WHERE alert_type = 'FRAUD'")
            total_fraud_alerts = cursor.fetchone()[0]

            cursor.execute("""
            SELECT rule_name, severity, alert_type, COUNT(*) as cnt
            FROM alerts
            GROUP BY rule_name, severity, alert_type
            ORDER BY cnt DESC
            """)
            top_rules = [dict(r) for r in cursor.fetchall()]

            return {
                "total_customers": total_customers,
                "total_transactions": total_transactions,
                "total_alerts": total_aml_alerts + total_fraud_alerts,
                "total_aml_alerts": total_aml_alerts,
                "total_fraud_alerts": total_fraud_alerts,
                "tier_distribution": tier_stats,
                "top_alerts": top_rules
            }

    def get_all_customers_with_assessments(self) -> List[Dict[str, Any]]:
        """Returns list of all customers joined with risk assessments."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT c.*, r.composite_score, r.risk_tier, r.alert_count, r.highest_alert_severity,
                   r.fraud_alert_count, r.highest_fraud_severity, r.aml_score, r.fraud_score,
                   r.recommended_action
            FROM customers c
            LEFT JOIN risk_assessments r ON c.customer_id = r.customer_id
            ORDER BY r.composite_score DESC
            """)
            return [dict(r) for r in cursor.fetchall()]

    def get_customer_360(self, customer_id: str) -> Optional[Dict[str, Any]]:
        """Returns complete customer dossier: KYC profile, assessment, AML & Fraud alerts, and transactions."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM customers WHERE customer_id = ?", (customer_id,))
            cust_row = cursor.fetchone()
            if not cust_row:
                return None
            cust_dict = dict(cust_row)
            cust_dict["products_held"] = json.loads(cust_dict["products_held"]) if cust_dict.get("products_held") else []
            cust_dict["synthetic_id_indicators"] = json.loads(cust_dict["synthetic_id_indicators"]) if cust_dict.get("synthetic_id_indicators") else []

            cursor.execute("SELECT * FROM risk_assessments WHERE customer_id = ?", (customer_id,))
            risk_row = cursor.fetchone()
            risk_dict = dict(risk_row) if risk_row else None
            if risk_dict and risk_dict.get("raw_assessment_json"):
                risk_dict["parsed"] = json.loads(risk_dict["raw_assessment_json"])

            cursor.execute("SELECT * FROM alerts WHERE customer_id = ? ORDER BY score_impact DESC", (customer_id,))
            all_alerts = [dict(r) for r in cursor.fetchall()]
            aml_alerts = []
            fraud_alerts = []
            for alt in all_alerts:
                alt["trigger_details"] = json.loads(alt["trigger_details"]) if alt.get("trigger_details") else {}
                alt["supporting_transaction_ids"] = json.loads(alt["supporting_transaction_ids"]) if alt.get("supporting_transaction_ids") else []
                if alt.get("alert_type") == "FRAUD":
                    fraud_alerts.append(alt)
                else:
                    aml_alerts.append(alt)

            cursor.execute("SELECT * FROM transactions WHERE customer_id = ? ORDER BY timestamp DESC", (customer_id,))
            transactions = [dict(r) for r in cursor.fetchall()]

            return {
                "customer": cust_dict,
                "assessment": risk_dict,
                "alerts": aml_alerts,
                "fraud_alerts": fraud_alerts,
                "transactions": transactions
            }

    def query_transactions(
        self,
        page: int = 1,
        page_size: int = 25,
        search: Optional[str] = None,
        direction: str = "ALL",
        fraud_only: bool = False,
        aml_only: bool = False,
        customer_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Queries transactions with server-side pagination, text search, and flags."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            conditions = []
            params = []

            if customer_id:
                conditions.append("customer_id = ?")
                params.append(customer_id)

            if direction and direction.upper() != "ALL":
                conditions.append("direction = ?")
                params.append(direction.upper())

            if fraud_only:
                conditions.append("is_fraud_synthetic = 1")

            if aml_only:
                conditions.append("is_suspicious_synthetic = 1")

            if search:
                s = f"%{search.strip()}%"
                conditions.append(
                    "(transaction_id LIKE ? OR customer_id LIKE ? OR counterparty_name LIKE ? OR "
                    "reference_narrative LIKE ? OR device_id LIKE ? OR fraud_typology_tag LIKE ? OR synthetic_typology_tag LIKE ?)"
                )
                params.extend([s, s, s, s, s, s, s])

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            # Count total matching
            cursor.execute(f"SELECT COUNT(*) FROM transactions {where_clause}", params)
            total = cursor.fetchone()[0]

            # Fetch paged items
            offset = max(0, (page - 1) * page_size)
            cursor.execute(
                f"SELECT * FROM transactions {where_clause} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                params + [page_size, offset]
            )
            rows = [dict(r) for r in cursor.fetchall()]

            return {
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size if total > 0 else 1,
                "transactions": rows
            }

    def query_alerts(
        self,
        alert_type: str = "ALL",
        severity: Optional[str] = None,
        customer_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Queries alerts with filtering by type, severity, and customer."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            conditions = []
            params = []

            if customer_id:
                conditions.append("customer_id = ?")
                params.append(customer_id)

            if alert_type and alert_type.upper() != "ALL":
                conditions.append("alert_type = ?")
                params.append(alert_type.upper())

            if severity and severity.upper() != "ALL":
                conditions.append("severity = ?")
                params.append(severity.upper())

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            cursor.execute(f"SELECT * FROM alerts {where_clause} ORDER BY score_impact DESC", params)
            alerts = []
            for r in cursor.fetchall():
                d = dict(r)
                d["trigger_details"] = json.loads(d["trigger_details"]) if d.get("trigger_details") else {}
                d["supporting_transaction_ids"] = json.loads(d["supporting_transaction_ids"]) if d.get("supporting_transaction_ids") else []
                alerts.append(d)
            return alerts

    def get_open_alerts(
        self,
        severity: Optional[str] = None,
        alert_type: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Returns open alerts joined with customer details as an alert triage feed for agents."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            conditions = ["(a.status = 'OPEN' OR a.status IS NULL)"]
            params: list[Any] = []

            if severity and severity.upper() != "ALL":
                conditions.append("a.severity = ?")
                params.append(severity.upper())

            if alert_type and alert_type.upper() != "ALL":
                conditions.append("a.alert_type = ?")
                params.append(alert_type.upper())

            where_clause = f"WHERE {' AND '.join(conditions)}"
            query = f"""
            SELECT a.*, c.first_name, c.last_name, c.name as customer_name,
                   c.archetype, c.residence_country, c.risk_rating
            FROM alerts a
            JOIN customers c ON a.customer_id = c.customer_id
            {where_clause}
            ORDER BY
                CASE a.severity WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'MEDIUM' THEN 3 ELSE 4 END,
                a.score_impact DESC
            LIMIT ?
            """
            params.append(limit)
            cursor.execute(query, tuple(params))
            alerts = []
            for r in cursor.fetchall():
                d = dict(r)
                d["trigger_details"] = json.loads(d["trigger_details"]) if d.get("trigger_details") else {}
                d["supporting_transaction_ids"] = json.loads(d["supporting_transaction_ids"]) if d.get("supporting_transaction_ids") else []
                alerts.append(d)
            return alerts

    def export_to_csv(self, export_dir: str = "exports"):
        """Exports tables to standalone CSV files."""
        os.makedirs(export_dir, exist_ok=True)
        tables = ["customers", "transactions", "risk_assessments", "alerts"]
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for tbl in tables:
                cursor.execute(f"SELECT * FROM {tbl}")
                rows = cursor.fetchall()
                if not rows:
                    continue
                file_path = os.path.join(export_dir, f"{tbl}.csv")
                with open(file_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow([d[0] for d in cursor.description])
                    writer.writerows(rows)
                print(f"Exported {len(rows)} rows to {file_path}")
