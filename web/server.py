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

# Sentinel Live Stream & Autonomous Agent Interrogation Layer
import uuid
from app.live_agent.scenarios import SCENARIOS, LiveStreamEngine
from app.live_agent.agent import AgentRun
from app.live_agent.policy import PolicyEngine
from app.live_agent.database import DatabaseInformationService

WEB_DIR = os.path.dirname(__file__)
STATIC_DIR = os.path.join(WEB_DIR, "static")
EXPORTS_DIR = os.path.abspath(os.path.join(WEB_DIR, "..", "exports"))
LIVE_STREAM_HTML = os.path.join(WEB_DIR, "live_stream.html")
SENTINEL_HTML = os.path.join(WEB_DIR, "Financialcrime.html")
VISUALIZATION_HTML = os.path.join(WEB_DIR, "visualization.html")

ACTIVE_AGENT_RUNS: Dict[str, AgentRun] = {}
RUNS: Dict[str, Dict[str, Any]] = {}

class ComplianceHandler(http.server.SimpleHTTPRequestHandler):
    """Integrated HTTP handler serving REST APIs, data services, and interactive web dashboard."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def _serve_file(self, filepath: str, content_type: str = "text/html; charset=utf-8"):
        if os.path.exists(filepath):
            with open(filepath, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(content)
        else:
            self._send_error(404, f"File {os.path.basename(filepath)} not found")

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query = urllib.parse.parse_qs(parsed_url.query)

        if path == "/live-stream" or path == "/investigator":
            self._serve_file(LIVE_STREAM_HTML, "text/html; charset=utf-8")
            return
        elif path == "/sentinel":
            self._serve_file(SENTINEL_HTML, "text/html; charset=utf-8")
            return
        elif path == "/visualizer":
            self._serve_file(VISUALIZATION_HTML, "text/html; charset=utf-8")
            return
        elif path == "/api/scenarios":
            summary_list = []
            for cid, s in SCENARIOS.items():
                summary_list.append({
                    "id": s["id"],
                    "title": s["title"],
                    "subtitle": s["subtitle"],
                    "expected_action": s["expected_action"],
                    "transaction": s["transaction"],
                    "customer": {
                        "name": s["customer"]["name"],
                        "typical_min": s["customer"]["typical_min"],
                        "typical_max": s["customer"]["typical_max"]
                    }
                })
            self._send_json(summary_list)
            return
        elif path == "/api/stream":
            self._send_json(LiveStreamEngine.get_latest_stream())
            return
        elif path == "/api/stream/next":
            self._send_json(LiveStreamEngine.generate_routine_tx())
            return
        elif path == "/api/database/questions":
            self._send_json(DatabaseInformationService.get_all_questions())
            return
        elif path.startswith("/api/database/customer"):
            cust_id = query.get("id", [""])[0]
            profile = DatabaseInformationService.get_customer_profile(cust_id) if cust_id else None
            if not profile:
                profile = {
                    "customer_id": cust_id or "CUST-3912",
                    "full_name": "Elin Nygren" if "3912" in (cust_id or "") else ("Alice Lindqvist" if "1042" in (cust_id or "") else "Johan Holm"),
                    "risk_score": 0.18,
                    "risk_level": "LOW_BASELINE",
                    "annual_income_sek": 468000,
                    "monthly_turnover_baseline": 24500,
                    "kyc_verified_date": "2021-04-14",
                    "residential_address": "Karlavägen 42, Stockholm",
                    "primary_device_id": "DEV-112 (Apple iPhone 15 Pro)",
                    "bankid_auth_level": "High Assurance Level 3 (Biometric)",
                    "historical_alert_count": 0
                }
            self._send_json({"status": "found", "customer": profile})
            return
        elif path == "/api/portfolio":
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

        if path == "/api/stream/inject":
            case_id = payload.get("caseId") or payload.get("case_id", "case-3")
            try:
                tx = LiveStreamEngine.inject_case_tx(case_id)
                self._send_json({"status": "injected", "transaction": tx})
            except Exception as e:
                self._send_error(400, str(e))
            return
        elif path == "/api/investigations":
            case_id = payload.get("case_id", "case-3")
            if case_id not in SCENARIOS:
                self._send_error(400, f"Unknown case_id: {case_id}")
                return
            run_id = f"run-{case_id}-{uuid.uuid4().hex[:6]}"
            agent_run = AgentRun(
                run_id=run_id,
                case_id=case_id,
                scenario=SCENARIOS[case_id],
                patches=payload.get("patches", {}),
                api_key=self.headers.get("X-Gemini-Api-Key") or payload.get("api_key", "")
            )
            ACTIVE_AGENT_RUNS[run_id] = agent_run
            res = agent_run.run_investigation()
            RUNS[run_id] = res
            self._send_json(res)
            return
        elif path == "/api/inquiry/submit":
            run_id = payload.get("run_id")
            question_id = payload.get("question_id")
            selected_option = payload.get("selected_option", {})
            agent_run = ACTIVE_AGENT_RUNS.get(run_id)
            if not agent_run:
                target_case = payload.get("case_id", "case-3")
                agent_run = AgentRun(
                    run_id=run_id or f"run-{target_case}-live",
                    case_id=target_case,
                    scenario=SCENARIOS.get(target_case, SCENARIOS["case-3"])
                )
                agent_run.run_investigation()
                ACTIVE_AGENT_RUNS[agent_run.run_id] = agent_run
            
            ev_res = agent_run.env.record_customer_inquiry_response(question_id, selected_option)
            new_eid = ev_res["evidence_id"]
            DatabaseInformationService.log_customer_inquiry(
                case_id=agent_run.case_id,
                tx_id=agent_run.scenario["transaction"]["id"],
                question_id=question_id,
                option_key=selected_option.get("key", "UNKNOWN"),
                statement=selected_option.get("statement", ""),
                impact=selected_option.get("risk_verdict", "CONFIRMED_COERCION"),
                evidence_id=new_eid
            )
            all_eids = [e["evidence_id"] for e in agent_run.evidence_store.get_all()]
            jev_step = agent_run.execute_tool(
                "assess_with_jev",
                {"evidence_ids": all_eids},
                f"Re-synthesizing decision with recorded customer testimony {new_eid}",
                input_evidence_ids=all_eids
            )
            agent_run.claims.append({
                "claim_id": f"C0{len(agent_run.claims) + 1}",
                "text": f"Customer statement recorded: {selected_option.get('statement')}",
                "supporting_evidence_ids": [new_eid]
            })
            agent_run.finalize_investigation()
            updated_dict = agent_run.to_dict()
            updated_dict["inquiry_resolution"] = {
                "status": "PROCESSED",
                "selected_option": selected_option,
                "jev_judgment": jev_step["data"],
                "evidence_id": new_eid,
                "conclusive_dossier": jev_step["data"].get("dossier_brief")
            }
            RUNS[agent_run.run_id] = updated_dict
            self._send_json(updated_dict)
            return
        elif path == "/api/repeatability":
            case_id = payload.get("case_id", "case-3")
            num_runs = int(payload.get("runs", 5))
            if case_id not in SCENARIOS:
                self._send_error(400, f"Unknown case_id: {case_id}")
                return
            actions = []
            for i in range(num_runs):
                run_res = AgentRun(
                    run_id=f"rep-{i+1}-{uuid.uuid4().hex[:4]}",
                    case_id=case_id,
                    scenario=SCENARIOS[case_id]
                ).run_investigation()
                actions.append(run_res["policy_decision"]["action"])
            counts = {}
            for a in actions:
                counts[a] = counts.get(a, 0) + 1
            modal_action = max(counts, key=counts.get)
            agreement_rate = counts[modal_action] / num_runs
            self._send_json({
                "case_id": case_id,
                "total_runs": num_runs,
                "actions": actions,
                "distribution": counts,
                "modal_action": modal_action,
                "stability_rate": agreement_rate,
                "is_stable": agreement_rate >= 0.8
            })
            return
        elif path == "/api/simulate":
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
