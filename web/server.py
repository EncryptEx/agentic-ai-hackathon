"""Comprehensive HTTP server integrating KYC, AML, Fraud (FRAML), Simulation, Generation, and Data Export."""

import http.server
import socketserver
import json
import os
import urllib.parse
from typing import Dict, Any

from storage.database import DatabaseManager
from generator.customer_generator import CustomerGenerator, ARCHETYPE_CONFIGS
from generator.transaction_generator import TransactionGenerator
from engine.risk_engine import RiskEngine
from models.customer import CustomerProfile, PEPStatus, AdverseMedia, SanctionStatus
from models.transaction import Transaction, TransactionType, TransactionDirection
from evidencetrail import api as evidencetrail_api

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
EXPORTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "exports"))

class ComplianceHandler(http.server.SimpleHTTPRequestHandler):
    """Integrated HTTP handler serving REST APIs, data services, and interactive web dashboard."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query = urllib.parse.parse_qs(parsed_url.query)

        if evidencetrail_api.handles(path):
            status, body = evidencetrail_api.handle_get(path)
            self._send_json(body, status)
            return

        if path == "/api/portfolio":
            self._handle_portfolio()
        elif path == "/api/customers":
            self._handle_customers(query)
        elif path == "/api/customer":
            cust_id = query.get("id", [""])[0]
            self._handle_customer_360(cust_id)
        elif path == "/api/transactions":
            self._handle_transactions(query)
        elif path == "/api/alerts":
            self._handle_alerts(query)
        elif path == "/api/archetypes":
            self._send_json(list(ARCHETYPE_CONFIGS.keys()))
        elif path == "/api/download":
            filename = query.get("file", [""])[0]
            self._handle_download(filename)
        else:
            # Fall back to static files
            if path == "/" or not os.path.exists(os.path.join(STATIC_DIR, path.lstrip("/"))):
                self.path = "/index.html"
            super().do_GET()

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except Exception as e:
            self._send_error(400, f"Invalid JSON payload: {str(e)}")
            return

        if evidencetrail_api.handles(path):
            status, body = evidencetrail_api.handle_post(path, payload)
            self._send_json(body, status)
            return

        if path == "/api/simulate":
            self._handle_simulate(payload)
        elif path == "/api/generate":
            self._handle_generate(payload)
        elif path == "/api/export":
            self._handle_export()
        else:
            self._send_error(404, "Endpoint not found")

    def _handle_portfolio(self):
        db = DatabaseManager()
        summary = db.get_portfolio_summary()
        self._send_json(summary)

    def _handle_customers(self, query):
        db = DatabaseManager()
        customers = db.get_all_customers_with_assessments()

        # Optional filtering by tier
        tier = query.get("tier", [None])[0]
        if tier and tier.upper() != "ALL":
            customers = [c for c in customers if c.get("risk_tier") == tier.upper()]

        # Optional search query
        q = query.get("q", [None])[0]
        if q:
            q_lower = q.lower()
            customers = [
                c for c in customers
                if q_lower in c["first_name"].lower()
                or q_lower in c["last_name"].lower()
                or q_lower in c["customer_id"].lower()
                or q_lower in c["citizenship"].lower()
                or q_lower in c["occupation"].lower()
                or q_lower in c["archetype"].lower()
            ]

        self._send_json({"total": len(customers), "customers": customers})

    def _handle_customer_360(self, customer_id: str):
        if not customer_id:
            self._send_error(400, "Missing customer ID parameter")
            return

        db = DatabaseManager()
        data = db.get_customer_360(customer_id)
        if not data:
            self._send_error(404, f"Customer {customer_id} not found")
            return

        self._send_json(data)

    def _handle_transactions(self, query):
        db = DatabaseManager()
        page = int(query.get("page", [1])[0])
        page_size = int(query.get("page_size", [25])[0])
        search = query.get("q", [None])[0]
        direction = query.get("dir", ["ALL"])[0]
        fraud_only = query.get("fraud_only", ["false"])[0].lower() in ["true", "1"]
        aml_only = query.get("aml_only", ["false"])[0].lower() in ["true", "1"]
        cust_id = query.get("customer_id", [None])[0]

        result = db.query_transactions(
            page=page,
            page_size=page_size,
            search=search,
            direction=direction,
            fraud_only=fraud_only,
            aml_only=aml_only,
            customer_id=cust_id
        )
        self._send_json(result)

    def _handle_alerts(self, query):
        db = DatabaseManager()
        alert_type = query.get("type", ["ALL"])[0]
        severity = query.get("severity", [None])[0]
        cust_id = query.get("customer_id", [None])[0]

        alerts = db.query_alerts(alert_type=alert_type, severity=severity, customer_id=cust_id)
        self._send_json({"total": len(alerts), "alerts": alerts})

    def _handle_download(self, filename: str):
        safe_name = os.path.basename(filename)
        file_path = os.path.join(EXPORTS_DIR, safe_name)

        if not os.path.exists(file_path):
            self._send_error(404, f"File {safe_name} not found in exports directory.")
            return

        with open(file_path, "rb") as f:
            content = f.read()

        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{safe_name}"')
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _handle_export(self):
        db = DatabaseManager()
        db.export_to_csv(EXPORTS_DIR)
        self._send_json({
            "status": "success",
            "message": "CSV exports generated successfully",
            "files": [
                "/api/download?file=customers.csv",
                "/api/download?file=transactions.csv",
                "/api/download?file=risk_assessments.csv",
                "/api/download?file=alerts.csv"
            ]
        })

    def _handle_generate(self, payload: Dict[str, Any]):
        """Generates a new synthetic customer cohort directly from the web application."""
        count = int(payload.get("count", 100))
        days = int(payload.get("days", 90))
        seed = int(payload.get("seed", 42))

        cg = CustomerGenerator(seed=seed)
        tg = TransactionGenerator(seed=seed)
        engine = RiskEngine()
        db = DatabaseManager()

        customers = cg.generate_batch(count=count)
        tx_map = {}
        assessments = []

        for c in customers:
            c_txs = tg.generate_customer_transactions(c, days_history=days)
            tx_map[c.customer_id] = c_txs
            assessment = engine.evaluate_customer(c, c_txs)
            assessments.append(assessment)

        db.reset_database()
        db.save_batch(customers, tx_map, assessments)
        db.export_to_csv(EXPORTS_DIR)

        # Also trigger standalone HTML regeneration
        try:
            from build_visualization import build_standalone_html
            build_standalone_html()
        except Exception:
            pass

        summary = db.get_portfolio_summary()
        self._send_json({
            "status": "success",
            "message": f"Successfully generated and evaluated {count} customers with {len(assessments)} FRAML assessments.",
            "summary": summary
        })

    def _handle_simulate(self, payload: Dict[str, Any]):
        """Runs the live FRAML Risk Engine on custom simulation inputs."""
        engine = RiskEngine()
        cust_data = payload.get("customer", {})

        customer = CustomerProfile(
            customer_id=cust_data.get("customer_id", "SIM-001"),
            first_name=cust_data.get("first_name", "Test"),
            last_name=cust_data.get("last_name", "User"),
            date_of_birth=cust_data.get("date_of_birth", "1985-05-15"),
            age=int(cust_data.get("age", 40)),
            citizenship=cust_data.get("citizenship", "US"),
            dual_citizenship=cust_data.get("dual_citizenship"),
            residence_country=cust_data.get("residence_country", "US"),
            tax_residence_country=cust_data.get("tax_residence_country", "US"),
            address_city=cust_data.get("address_city", "New York"),
            address_postal_code=cust_data.get("address_postal_code", "10001"),
            address_line=cust_data.get("address_line", "100 Broadway"),
            occupation=cust_data.get("occupation", "Software Engineer"),
            occupation_risk_key=cust_data.get("occupation_risk_key", "SOFTWARE_ENGINEER"),
            industry=cust_data.get("industry", "Technology"),
            employer_name=cust_data.get("employer_name", "Tech Corp"),
            source_of_funds=cust_data.get("source_of_funds", "Salary"),
            source_of_wealth=cust_data.get("source_of_wealth", "Savings"),
            annual_income_usd=float(cust_data.get("annual_income_usd", 120000)),
            net_worth_usd=float(cust_data.get("net_worth_usd", 350000)),
            declared_expected_monthly_turnover_usd=float(cust_data.get("declared_expected_monthly_turnover_usd", 8000)),
            declared_expected_max_single_tx_usd=float(cust_data.get("declared_expected_max_single_tx_usd", 3000)),
            declared_purpose_nature=cust_data.get("declared_purpose_nature", "SALARY_AND_LIVING_EXPENSES"),
            onboarding_channel=cust_data.get("onboarding_channel", "DIGITAL_EKYC_BIOMETRIC"),
            onboarding_date=cust_data.get("onboarding_date", "2025-01-01"),
            products_held=cust_data.get("products_held", ["CURRENT_ACCOUNT"]),
            pep_status=PEPStatus(cust_data.get("pep_status", "NONE")),
            adverse_media=AdverseMedia(cust_data.get("adverse_media", "NONE")),
            sanction_status=SanctionStatus(cust_data.get("sanction_status", "CLEAN")),
            email_address=cust_data.get("email_address"),
            email_domain_type=cust_data.get("email_domain_type", "PUBLIC_FREE"),
            phone_number=cust_data.get("phone_number"),
            phone_line_type=cust_data.get("phone_line_type", "MOBILE"),
            device_primary_id=cust_data.get("device_primary_id", "DEV-SIM-PRIMARY"),
            primary_ip_address=cust_data.get("primary_ip_address", "192.168.1.1"),
            primary_ip_country=cust_data.get("primary_ip_country", cust_data.get("residence_country", "US")),
            synthetic_identity_score=float(cust_data.get("synthetic_identity_score", 10.0)),
            synthetic_id_indicators=cust_data.get("synthetic_id_indicators", []),
            archetype=cust_data.get("archetype", "CUSTOM_SIMULATION")
        )

        txs_data = payload.get("transactions", [])
        transactions = []
        for i, t in enumerate(txs_data):
            transactions.append(Transaction(
                transaction_id=t.get("transaction_id", f"SIM-TXN-{i+1:04d}"),
                customer_id=customer.customer_id,
                timestamp=t.get("timestamp", "2026-09-01T12:00:00"),
                transaction_type=TransactionType(t.get("transaction_type", "ACH_DEPOSIT")),
                direction=TransactionDirection(t.get("direction", "INBOUND")),
                amount_usd=float(t.get("amount_usd", 1000.0)),
                counterparty_name=t.get("counterparty_name", "Counterparty"),
                counterparty_country=t.get("counterparty_country", "US"),
                counterparty_category=t.get("counterparty_category", "RETAILER"),
                channel=t.get("channel", "ACH"),
                reference_narrative=t.get("reference_narrative", "Simulation Transaction"),
                device_id=t.get("device_id", customer.device_primary_id),
                ip_address=t.get("ip_address", customer.primary_ip_address),
                ip_country=t.get("ip_country", customer.primary_ip_country),
                card_entry_mode=t.get("card_entry_mode"),
                auth_status=t.get("auth_status", "AUTHORIZED"),
                is_new_payee=bool(t.get("is_new_payee", False))
            ))

        assessment = engine.evaluate_customer(customer, transactions)
        self._send_json(assessment.model_dump())

    def _send_json(self, data: Any, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status: int, message: str):
        self._send_json({"error": message}, status=status)

def run_server(port: int = 8080):
    """Starts the local FRAML compliance server."""
    os.makedirs(STATIC_DIR, exist_ok=True)
    os.makedirs(EXPORTS_DIR, exist_ok=True)
    server_address = ("", port)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(server_address, ComplianceHandler) as httpd:
        print(f"\n=================================================================")
        print(f"  VALIANT BANK • INTEGRATED FRAML RISK & GENERATION PLATFORM")
        print(f"  Live Server URL: http://localhost:{port}")
        print(f"=================================================================\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")

if __name__ == "__main__":
    run_server(8080)
