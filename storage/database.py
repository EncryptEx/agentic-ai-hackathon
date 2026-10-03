"""Database persistence and CSV/JSON export module with FRAML support."""

import sqlite3
import json
import os
import csv
from typing import List, Dict, Any, Optional
from models.customer import CustomerProfile
from models.transaction import Transaction
from models.risk_score import CustomerRiskAssessment

class DatabaseManager:
    """Manages SQLite persistence and tabular exports for KYC, AML, & Fraud data."""

    def __init__(self, db_path: str = "data/kyc_aml.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
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
                FOREIGN KEY (customer_id) REFERENCES customers (customer_id)
            )
            """)

            # Safety column additions for backwards compatibility if table existed
            def try_add_col(table, col, col_type):
                try:
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
                except sqlite3.OperationalError:
                    pass

            try_add_col("customers", "email_address", "TEXT")
            try_add_col("customers", "email_domain_type", "TEXT")
            try_add_col("customers", "phone_number", "TEXT")
            try_add_col("customers", "phone_line_type", "TEXT")
            try_add_col("customers", "device_primary_id", "TEXT")
            try_add_col("customers", "primary_ip_address", "TEXT")
            try_add_col("customers", "primary_ip_country", "TEXT")
            try_add_col("customers", "synthetic_identity_score", "REAL")
            try_add_col("customers", "synthetic_id_indicators", "TEXT")

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
                cursor.execute("""
                INSERT OR REPLACE INTO customers VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
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
                    c.archetype
                ))

            # Insert Transactions
            for cust_id, tx_list in transactions_map.items():
                for t in tx_list:
                    cursor.execute("""
                    INSERT OR REPLACE INTO transactions VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
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
                        1 if t.is_fraud_synthetic else 0, t.fraud_typology_tag
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
                    INSERT OR REPLACE INTO alerts VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
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
                    INSERT OR REPLACE INTO alerts VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
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
