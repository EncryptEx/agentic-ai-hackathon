"""Unified Command-Line Interface for KYC, AML, Fraud (FRAML) & Agent Investigations."""

import argparse
import asyncio
import json
import os
import sys
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.table import Table
    from rich.text import Text
    console = Console()
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

from engine.risk_engine import RiskEngine
from generator.customer_generator import CustomerGenerator
from generator.transaction_generator import TransactionGenerator
from storage.database import DatabaseManager


def print_banner():
    banner = """
========================================================================
   FINANCIAL CRIME INVESTIGATION PLATFORM (FRAML + AI AGENTS)
      Multi-Pillar KYC, AML & Fraud Detection + Autonomous ADK Agents
========================================================================
    """
    if HAS_RICH:
        console.print(f"[bold cyan]{banner}[/bold cyan]")
    else:
        print(banner)


def get_tier_color(tier: str) -> str:
    if tier == "CRITICAL":
        return "bold red"
    elif tier == "HIGH":
        return "bold orange3"
    elif tier == "MEDIUM":
        return "bold yellow"
    else:
        return "bold green"


def handle_generate(args):
    """Generates synthetic cohort, evaluates 5-pillar risk, saves to DB, and exports CSVs."""
    print_banner()
    count = args.count
    days = args.days
    seed = args.seed

    if HAS_RICH:
        console.print(f"[cyan]Initializing generation for [bold]{count}[/bold] individual customers ({days} days history, seed={seed})...[/cyan]")
    else:
        print(f"Initializing generation for {count} individual customers ({days} days history, seed={seed})...")

    cg = CustomerGenerator(seed=seed)
    tg = TransactionGenerator(seed=seed)
    engine = RiskEngine()
    db = DatabaseManager()

    # 1. Generate Customers
    customers = cg.generate_batch(count=count)

    # 2. Generate Transactions & Evaluate Multi-Pillar Risk
    tx_map = {}
    assessments = []

    if HAS_RICH:
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as progress:
            task = progress.add_task("[cyan]Processing transactions, AML rules, and Fraud detection...", total=count)
            for c in customers:
                c_txs = tg.generate_customer_transactions(c, days_history=days)
                tx_map[c.customer_id] = c_txs
                assessment = engine.evaluate_customer(c, c_txs)
                assessments.append(assessment)
                progress.advance(task)
    else:
        for c in customers:
            c_txs = tg.generate_customer_transactions(c, days_history=days)
            tx_map[c.customer_id] = c_txs
            assessment = engine.evaluate_customer(c, c_txs)
            assessments.append(assessment)

    # 3. Save to Unified Database
    db.save_batch(customers, tx_map, assessments)
    total_txs = sum(len(t) for t in tx_map.values())
    total_aml_alts = sum(len(a.alerts) for a in assessments)
    total_fr_alts = sum(len(a.fraud_alerts) for a in assessments)

    if HAS_RICH:
        console.print(
            f"\n[green]✓ Successfully persisted {len(customers)} customers, {total_txs} transactions, "
            f"{total_aml_alts} AML alerts, and {total_fr_alts} Fraud alerts to SQLite database.[/green]"
        )
    else:
        print(
            f"\nSuccessfully persisted {len(customers)} customers, {total_txs} transactions, "
            f"{total_aml_alts} AML alerts, and {total_fr_alts} Fraud alerts."
        )

    # 4. Export CSVs
    if args.export:
        db.export_to_csv("exports")
        if HAS_RICH:
            console.print("[green]✓ CSV tables exported to ./exports/[/green]")
        else:
            print("CSV tables exported to ./exports/")

    # 5. Display Summary
    handle_summary(args)


def handle_summary(args):
    """Displays portfolio summary metrics."""
    db = DatabaseManager()
    summary = db.get_portfolio_summary()

    if summary["total_customers"] == 0:
        print("No customers in database. Run 'python cli.py generate' first.")
        return

    if HAS_RICH:
        console.print("\n[bold underline]PORTFOLIO RISK DISTRIBUTION[/bold underline]")
        tier_table = Table(title="Risk Rating Tiers", show_header=True, header_style="bold magenta")
        tier_table.add_column("Risk Tier", style="dim", width=12)
        tier_table.add_column("Customer Count", justify="right", width=16)
        tier_table.add_column("% of Portfolio", justify="right", width=16)
        tier_table.add_column("Avg Composite Score", justify="right", width=22)

        tot = summary["total_customers"]
        for tier in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]:
            stat = summary["tier_distribution"].get(tier, {"count": 0, "avg_score": 0.0, "avg_aml": 0.0, "avg_fraud": 0.0})
            cnt = stat["count"]
            pct = (cnt / tot * 100) if tot > 0 else 0
            tier_color = get_tier_color(tier)
            tier_table.add_row(
                f"[{tier_color}]{tier}[/{tier_color}]",
                f"{cnt:,}",
                f"{pct:.1f}%",
                f"{stat['avg_score']:.1f} / 100"
            )
        console.print(tier_table)

        if summary["top_alerts"]:
            console.print("\n[bold underline]FINANCIAL CRIME (AML & FRAUD) ALERT TYPOLOGIES[/bold underline]")
            alert_table = Table(title="Top Triggered Typology Rules", show_header=True, header_style="bold yellow")
            alert_table.add_column("Rule Name", width=42)
            alert_table.add_column("Type", justify="center", width=10)
            alert_table.add_column("Severity", justify="center", width=12)
            alert_table.add_column("Alert Count", justify="right", width=14)

            for alt in summary["top_alerts"][:8]:
                sev_color = get_tier_color(alt["severity"])
                atype = alt.get("alert_type") or "AML"
                atype_color = "cyan" if atype == "AML" else "magenta"
                alert_table.add_row(
                    alt["rule_name"],
                    f"[{atype_color}]{atype}[/{atype_color}]",
                    f"[{sev_color}]{alt['severity']}[/{sev_color}]",
                    f"{alt['cnt']:,}"
                )
            console.print(alert_table)

        # High Risk Leaderboard
        customers = db.get_all_customers_with_assessments()
        console.print("\n[bold underline]HIGHEST RISK CUSTOMERS (PRIORITY EDD / SAR / FRAUD ACTION)[/bold underline]")
        lead_table = Table(title="Top High/Critical Risk Customers (FRAML)", show_header=True, header_style="bold red")
        lead_table.add_column("Customer ID", width=13)
        lead_table.add_column("Name", width=20)
        lead_table.add_column("Archetype", width=26)
        lead_table.add_column("Tier", justify="center", width=10)
        lead_table.add_column("FRAML", justify="right", width=8)
        lead_table.add_column("AML", justify="right", width=8)
        lead_table.add_column("Fraud", justify="right", width=8)
        lead_table.add_column("Alerts", justify="right", width=8)

        for c in customers[:8]:
            sev_color = get_tier_color(c["risk_tier"])
            comp_s = float(c.get('composite_score') or 0.0)
            aml_s = float(c.get('aml_score') or 0.0)
            fr_s = float(c.get('fraud_score') or 0.0)
            total_alts = int(c.get("alert_count") or 0) + int(c.get("fraud_alert_count") or 0)
            lead_table.add_row(
                c["customer_id"],
                f"{c.get('first_name', '')} {c.get('last_name', '')}".strip() or c.get("name", ""),
                c["archetype"],
                f"[{sev_color}]{c['risk_tier']}[/{sev_color}]",
                f"{comp_s:.1f}",
                f"{aml_s:.1f}",
                f"{fr_s:.1f}",
                str(total_alts)
            )
        console.print(lead_table)

    else:
        print("\nPortfolio Summary:")
        print(f"Total Customers: {summary['total_customers']}")
        print(f"Total Transactions: {summary['total_transactions']}")
        print(f"Total Alerts: {summary['total_alerts']}")
        print("Tiers:", summary["tier_distribution"])


def handle_inspect(args):
    """Inspects complete KYC & Transaction 360 profile for a single customer."""
    cust_id = args.customer_id.upper().strip()
    db = DatabaseManager()
    data = db.get_customer_360(cust_id)

    if not data:
        print(f"Customer '{cust_id}' not found.")
        return

    c = data["customer"]
    a = data["assessment"]
    alerts = data.get("alerts", [])
    fraud_alerts = data.get("fraud_alerts", [])
    txs = data.get("transactions", [])

    if HAS_RICH:
        tier_color = get_tier_color(a.get("risk_tier", "LOW"))
        console.print(f"\n[bold underline]CUSTOMER 360 DOSSIER: {cust_id} — {c.get('first_name', '')} {c.get('last_name', '')}[/bold underline]")

        kyc_info = f"""
[bold]Demographics & Citizenship:[/bold] {c.get('citizenship')} (Resident: {c.get('residence_country')}) | Age: {c.get('age')}
[bold]Occupation & Industry:[/bold] {c.get('occupation')} ({c.get('industry')}) @ {c.get('employer_name') or 'N/A'}
[bold]Wealth Profile:[/bold] Annual Income: ${c.get('annual_income_usd', 0):,.2f} | Net Worth: ${c.get('net_worth_usd', 0):,.2f}
[bold]Expected Activity:[/bold] Declared Monthly: ${c.get('declared_expected_monthly_turnover_usd', 0):,.2f} | Max Single: ${c.get('declared_expected_max_single_tx_usd', 0):,.2f}
[bold]Watchlist Status:[/bold] PEP: {c.get('pep_status')} | Sanctions: {c.get('sanction_status')} | Adverse Media: {c.get('adverse_media')}
[bold]Digital Telemetry:[/bold] Domain: {c.get('email_domain_type')} | Phone Line: {c.get('phone_line_type')} | Synthetic ID Score: {c.get('synthetic_identity_score', 0):.1f}
        """
        console.print(Panel(kyc_info.strip(), title="Identity & KYC Customer Due Diligence (CDD)"))

        score_info = f"""
[bold]Composite FRAML Score:[/bold] [{tier_color}]{a.get('composite_score', 0):.1f} / 100 ({a.get('risk_tier')})[/{tier_color}]
• AML Sub-Score: {a.get('aml_score', 0):.1f} / 100 | Fraud Sub-Score: {a.get('fraud_score', 0):.1f} / 100
• Pillar 1 (KYC Demographics): {a.get('kyc_raw_score', 0):.1f} (wt: {a.get('kyc_weighted_score', 0):.1f})
• Pillar 2 (Purpose & Wealth): {a.get('purpose_raw_score', 0):.1f} (wt: {a.get('purpose_weighted_score', 0):.1f})
• Pillar 3 (Products & Channels): {a.get('product_raw_score', 0):.1f} (wt: {a.get('product_weighted_score', 0):.1f})
• Pillar 4 (AML Transaction Monitoring): {a.get('behavioral_raw_score', 0):.1f} (wt: {a.get('behavioral_weighted_score', 0):.1f})
• Pillar 5 (Fraud & Digital Telemetry): {a.get('fraud_raw_score', 0):.1f} (wt: {a.get('fraud_weighted_score', 0):.1f})
[bold]Recommended Action:[/bold] {a.get('recommended_action')}
        """
        console.print(Panel(score_info.strip(), title="5-Pillar Risk Engine Assessment"))

        all_alts = alerts + fraud_alerts
        if all_alts:
            alt_table = Table(title=f"Triggered Alerts ({len(all_alts)})", show_header=True)
            alt_table.add_column("Type", width=8)
            alt_table.add_column("Rule ID", width=10)
            alt_table.add_column("Rule Name", width=34)
            alt_table.add_column("Severity", width=10)
            alt_table.add_column("Summary")
            for alt in all_alts:
                atype = alt.get("alert_type", "AML")
                color = "cyan" if atype == "AML" else "magenta"
                sev_color = get_tier_color(alt["severity"])
                alt_table.add_row(
                    f"[{color}]{atype}[/{color}]",
                    alt["rule_id"],
                    alt["rule_name"],
                    f"[{sev_color}]{alt['severity']}[/{sev_color}]",
                    alt.get("summary", "")[:70]
                )
            console.print(alt_table)
    else:
        print(f"Customer {cust_id}: {c.get('name')}")
        print(f"Tier: {a.get('risk_tier')}, Score: {a.get('composite_score')}")
        print(f"Total Transactions: {len(txs)}")


def handle_alerts(args):
    """Displays open alert queue for triage."""
    db = DatabaseManager()
    alerts = db.get_open_alerts(severity=args.severity, alert_type=args.type, limit=args.limit)

    if not alerts:
        print("No open alerts matching criteria.")
        return

    if HAS_RICH:
        table = Table(title=f"Alert Triage Queue (Top {len(alerts)})", show_header=True, header_style="bold yellow")
        table.add_column("Alert ID", width=14)
        table.add_column("Customer", width=22)
        table.add_column("Type", justify="center", width=8)
        table.add_column("Rule ID", width=10)
        table.add_column("Severity", justify="center", width=10)
        table.add_column("Impact", justify="right", width=8)
        table.add_column("Summary")

        for alt in alerts:
            atype = alt.get("alert_type", "AML")
            color = "cyan" if atype == "AML" else "magenta"
            sev_color = get_tier_color(alt["severity"])
            table.add_row(
                alt["alert_id"],
                f"{alt.get('customer_name', alt['customer_id'])} ({alt['customer_id']})",
                f"[{color}]{atype}[/{color}]",
                alt["rule_id"],
                f"[{sev_color}]{alt['severity']}[/{sev_color}]",
                f"+{alt.get('score_impact', 0):.1f}",
                alt.get("summary", "")[:60]
            )
        console.print(table)
    else:
        for alt in alerts:
            print(f"[{alt['severity']}] {alt['alert_id']} - {alt['customer_id']}: {alt['rule_name']}")


def handle_investigate(args):
    """Triggers autonomous Google ADK multi-agent investigation on a customer."""
    cust_id = args.customer_id.upper().strip()
    from app.alert_feed import AlertDispatcher
    from app.agent import root_agent
    from app.app_utils import services
    from google.adk.runners import Runner

    dispatcher = AlertDispatcher()
    try:
        packet = dispatcher.prepare_case_packet(cust_id, alert_id=args.alert_id)
    except Exception as e:
        print(f"Error preparing case: {e}")
        return

    prompt = dispatcher.generate_investigation_prompt(cust_id, packet.get("trigger_alert"))

    if HAS_RICH:
        trigger_rule = (packet.get("trigger_alert") or {}).get("rule_name", "Manual Risk Review")
        console.print(Panel(
            f"[bold cyan]Investigating Subject:[/bold cyan] {packet['customer_name']} ({cust_id})\n"
            f"[bold cyan]Risk Rating:[/bold cyan] {packet['risk_tier']} (Score: {packet['composite_score']:.1f})\n"
            f"[bold cyan]Trigger Alert:[/bold cyan] {trigger_rule}\n"
            f"[bold cyan]Prompt:[/bold cyan] {prompt}",
            title="[bold yellow]Triggering Autonomous ADK Agent Pipeline[/bold yellow]"
        ))
    else:
        print(f"Investigating {cust_id}: {prompt}")

    print("\nRunning specialist agents: customer_agent -> transaction_agent -> fraud_agent -> ownership_agent -> risk_agent -> consolidator_agent...")

    # Initialize ADK Runner
    from app.agent import app as adk_app
    from app.alert_feed import generate_specialist_investigation_report
    from google.genai import types

    runner = Runner(
        app=adk_app,
        session_service=services.get_session_service(),
        artifact_service=services.get_artifact_service(),
        auto_create_session=True,
    )

    async def _run():
        session = await runner.session_service.create_session(
            app_name=adk_app.name,
            user_id="compliance_officer"
        )
        new_message = types.Content(
            role="user",
            parts=[types.Part.from_text(text=prompt)]
        )
        events = []
        async for event in runner.run_async(
            user_id="compliance_officer",
            session_id=session.id,
            new_message=new_message,
        ):
            events.append(event)
        return events

    final_text = ""
    try:
        events = asyncio.run(_run())
        for ev in events:
            if hasattr(ev, "content") and ev.content and hasattr(ev.content, "parts"):
                for p in ev.content.parts:
                    if hasattr(p, "text") and p.text:
                        final_text = p.text
    except Exception as ex:
        if "No API key" in str(ex) or "API_KEY" in str(ex):
            if HAS_RICH:
                console.print("[yellow]Notice: No GEMINI_API_KEY configured. Synthesizing full 11-section specialist investigation via forensic rules engine...[/yellow]")
            else:
                print("Notice: No GEMINI_API_KEY configured. Synthesizing full 11-section specialist investigation via forensic rules engine...")
        else:
            if HAS_RICH:
                console.print(f"[yellow]ADK Runner notice: {ex}. Synthesizing 11-section report from forensic evidence...[/yellow]")
            else:
                print(f"ADK Runner notice: {ex}. Synthesizing 11-section report from forensic evidence...")
        final_text = generate_specialist_investigation_report(cust_id, trigger_alert=packet.get("trigger_alert"))

    if not final_text or not final_text.strip():
        final_text = generate_specialist_investigation_report(cust_id, trigger_alert=packet.get("trigger_alert"))

    if final_text:
        db = DatabaseManager()
        inv_id = db.log_investigation({
            "customer_id": cust_id,
            "customer_name": packet.get("customer_name"),
            "trigger_alert_id": args.alert_id,
            "trigger_rule": (packet.get("trigger_alert") or {}).get("rule_name", "Manual Risk Review"),
            "risk_tier": packet.get("risk_tier"),
            "composite_score": packet.get("composite_score", 0.0),
            "model_version": "gemini-3.8-flash",
            "raw_prompt": prompt,
            "final_report_text": final_text,
            "officer_sign_off_status": "PENDING",
        })
        log_rec = db.get_investigation_audit_log(inv_id)
        sha = log_rec.get("final_report_sha256", "") if log_rec else ""

        if HAS_RICH:
            console.print(Panel(final_text, title="[bold green]Final 13-Section Multi-Agent Case Dossier (with Arbiter Ruling & Self-Evolution Loop)[/bold green]"))
            console.print(Panel(
                f"[bold green]Audit Status:[/bold green] Recorded to Immutable Compliance Ledger\n"
                f"[bold cyan]Investigation ID:[/bold cyan] {inv_id}\n"
                f"[bold cyan]Cryptographic SHA-256 Digest:[/bold cyan] {sha}\n"
                f"[bold yellow]Officer Disposition:[/bold yellow] PENDING Human Review\n"
                f"[dim]To record review: python cli.py sign-off {inv_id} --officer \"<Name>\" --decision APPROVED_SAR_FILED[/dim]",
                title="[bold blue]Compliance Audit Trail Verification[/bold blue]"
            ))
        else:
            print("\n=== FINAL INVESTIGATIVE REPORT ===")
            print(final_text)
            print(f"\nAudit Log ID: {inv_id}")
            print(f"SHA-256 Digest: {sha}")
            print("Status: PENDING Officer Sign-Off")
    else:
        print("Investigation completed. No text output returned.")


def handle_audit(args):
    """View immutable investigation audit logs."""
    db = DatabaseManager()
    logs = db.get_investigation_audit_logs(customer_id=args.customer_id, limit=args.limit)
    if not logs:
        print("No investigation audit records found.")
        return

    if HAS_RICH:
        table = Table(title="Compliance Investigation Audit Trail", show_header=True, header_style="bold magenta")
        table.add_column("Investigation ID", style="cyan")
        table.add_column("Timestamp", style="dim")
        table.add_column("Customer", style="bold")
        table.add_column("Trigger Rule", style="yellow")
        table.add_column("Risk Tier", style="bold")
        table.add_column("Status", style="bold")
        table.add_column("Officer", style="green")
        table.add_column("SHA-256 Digest", style="dim")

        for l in logs:
            tier_col = get_tier_color(l.get("risk_tier", "LOW"))
            table.add_row(
                l["investigation_id"],
                (l.get("timestamp") or "")[:19],
                f"{l.get('customer_name', '')} ({l['customer_id']})",
                l.get("trigger_rule") or "Manual Review",
                f"[{tier_col}]{l.get('risk_tier', '')}[/{tier_col}]",
                l.get("officer_sign_off_status") or "PENDING",
                l.get("officer_name") or "Unassigned",
                (l.get("final_report_sha256") or "")[:12] + "..."
            )
        console.print(table)
    else:
        for l in logs:
            print(f"{l['investigation_id']} | {l['customer_id']} | {l.get('risk_tier')} | {l.get('officer_sign_off_status')} | SHA: {l.get('final_report_sha256')[:12]}")


def handle_sign_off(args):
    """Record compliance officer sign-off on an investigation audit log."""
    db = DatabaseManager()
    ok = db.update_audit_sign_off(
        investigation_id=args.investigation_id,
        officer_sign_off_status=args.decision,
        officer_name=args.officer,
        officer_notes=args.notes,
        officer_action_taken=args.action or args.decision
    )
    if not ok:
        print(f"Error: Investigation ID '{args.investigation_id}' not found.")
        return
    updated = db.get_investigation_audit_log(args.investigation_id)
    if HAS_RICH:
        console.print(Panel(
            f"[bold green]Sign-Off Confirmed![/bold green]\n"
            f"[bold cyan]Investigation ID:[/bold cyan] {args.investigation_id}\n"
            f"[bold cyan]Decision / Status:[/bold cyan] {updated.get('officer_sign_off_status')}\n"
            f"[bold cyan]Reviewing Officer:[/bold cyan] {updated.get('officer_name')}\n"
            f"[bold cyan]Notes:[/bold cyan] {updated.get('officer_notes')}\n"
            f"[bold cyan]Reviewed At:[/bold cyan] {updated.get('reviewed_at')}",
            title="[bold green]Human-in-the-Loop Sign-Off Recorded[/bold green]"
        ))
    else:
        print(f"Sign-off recorded for {args.investigation_id}: {args.decision} by {args.officer}")


def handle_serve(args):
    """Launches the combined FastAPI server with web dashboard and ADK agent endpoints."""
    import uvicorn
    host = args.host
    port = args.port
    print(f"Starting Financial Crime Platform Server on http://{host}:{port} ...")
    uvicorn.run("app.fast_api_app:app", host=host, port=port, reload=args.reload)


def main():
    parser = argparse.ArgumentParser(description="Financial Crime Investigation Platform (FRAML + ADK Agents)")
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Generate
    gen_parser = subparsers.add_parser("generate", help="Generate synthetic banking cohort and run 5-pillar risk engine")
    gen_parser.add_argument("--count", type=int, default=100, help="Number of individual customers (default: 100)")
    gen_parser.add_argument("--days", type=int, default=90, help="Transaction history window in days (default: 90)")
    gen_parser.add_argument("--seed", type=int, default=42, help="Random generator seed (default: 42)")
    gen_parser.add_argument("--export", action="store_true", default=True, help="Export CSV tables to exports/ folder")

    # Portfolio / Summary
    subparsers.add_parser("portfolio", help="View portfolio risk distribution and alert typologies")
    subparsers.add_parser("summary", help="Alias for portfolio")

    # Inspect
    inspect_parser = subparsers.add_parser("inspect", help="Inspect Customer 360 profile, KYC CDD, and alerts")
    inspect_parser.add_argument("customer_id", help="Customer ID (e.g., CUST-00015)")

    # Alerts
    alerts_parser = subparsers.add_parser("alerts", help="View open alert triage queue")
    alerts_parser.add_argument("--severity", choices=["CRITICAL", "HIGH", "MEDIUM", "LOW", "ALL"], default="ALL")
    alerts_parser.add_argument("--type", choices=["AML", "FRAUD", "ALL"], default="ALL")
    alerts_parser.add_argument("--limit", type=int, default=25, help="Number of alerts to display (default: 25)")

    # Investigate
    inv_parser = subparsers.add_parser("investigate", help="Run autonomous ADK multi-agent investigation on a customer")
    inv_parser.add_argument("customer_id", help="Customer ID (e.g., CUST-00015)")
    inv_parser.add_argument("--alert-id", help="Optional triggering alert ID")

    # Audit Trail
    audit_parser = subparsers.add_parser("audit", help="View immutable investigation audit trail & tamper-evident digests")
    audit_parser.add_argument("--customer-id", help="Filter by customer ID (e.g. CUST-00015)")
    audit_parser.add_argument("--limit", type=int, default=25, help="Number of audit records (default: 25)")

    # Sign-off (Human-in-the-Loop)
    signoff_parser = subparsers.add_parser("sign-off", help="Record compliance officer sign-off on an investigation")
    signoff_parser.add_argument("investigation_id", help="Investigation ID (e.g. INV-...)")
    signoff_parser.add_argument("--officer", required=True, help="Name or badge of compliance officer")
    signoff_parser.add_argument("--decision", required=True, choices=[
        "APPROVED_SAR_FILED", "APPROVED_EDD_REQUESTED", "APPROVED_ACCOUNT_RESTRICTED", "DISMISSED_FALSE_POSITIVE"
    ], help="Compliance decision")
    signoff_parser.add_argument("--notes", help="Officer rationale and justification")
    signoff_parser.add_argument("--action", help="Specific operational action taken")

    # Serve
    serve_parser = subparsers.add_parser("serve", help="Launch web dashboard and FastAPI agent server")
    serve_parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    serve_parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    serve_parser.add_argument("--reload", action="store_true", help="Enable live code reload")

    args = parser.parse_args()

    if args.command == "generate":
        handle_generate(args)
    elif args.command in ("portfolio", "summary"):
        handle_summary(args)
    elif args.command == "inspect":
        handle_inspect(args)
    elif args.command == "alerts":
        handle_alerts(args)
    elif args.command == "investigate":
        handle_investigate(args)
    elif args.command == "audit":
        handle_audit(args)
    elif args.command == "sign-off":
        handle_sign_off(args)
    elif args.command == "serve":
        handle_serve(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
