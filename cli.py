"""Command-line interface for KYC & Transaction Monitoring Synthetic Platform."""

import argparse
import sys
import os
import json
from typing import Optional

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich.progress import Progress, SpinnerColumn, TextColumn
    console = Console()
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

from generator.customer_generator import CustomerGenerator
from generator.transaction_generator import TransactionGenerator
from engine.risk_engine import RiskEngine
from storage.database import DatabaseManager

def print_banner():
    banner = """
========================================================================
   SYNTHETIC BANKING KYC, AML & FRAUD RISK PLATFORM (FRAML)
             Retail / Individual Customer Risk Engine
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
    """Generates synthetic cohort, evaluates risk, saves to DB, and exports CSVs."""
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
    
    # 2. Generate Transactions & Evaluate
    tx_map = {}
    assessments = []

    if HAS_RICH:
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as progress:
            task = progress.add_task("[cyan]Processing transactions and running risk engine...", total=count)
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

    # 3. Save to Database
    db.save_batch(customers, tx_map, assessments)
    total_txs = sum(len(t) for t in tx_map.values())
    total_alerts = sum(len(a.alerts) for a in assessments)

    if HAS_RICH:
        console.print(f"\n[green]✓ Successfully persisted {len(customers)} customers, {total_txs} transactions, and {total_alerts} AML alerts to SQLite database.[/green]")
    else:
        print(f"\nSuccessfully persisted {len(customers)} customers, {total_txs} transactions, and {total_alerts} AML alerts.")

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
                f"{c['first_name']} {c['last_name']}",
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
        print(f"Customer {cust_id} not found in database.")
        return

    cust = data["customer"]
    assessment = data["assessment"]
    alerts = data["alerts"]
    transactions = data["transactions"]

    tier = assessment["risk_tier"]
    score = assessment["composite_score"]
    tier_color = get_tier_color(tier)

    if HAS_RICH:
        # Header Panel
        header_text = Text()
        header_text.append(f"CUSTOMER 360 DOSSIER: {cust['first_name']} {cust['last_name']} ({cust['customer_id']})\n", style="bold white")
        header_text.append(f"Risk Rating: {tier} | Composite Score: {score:.1f}/100\n", style=tier_color)
        header_text.append(f"Recommended Governance Action: {assessment['recommended_action']}", style="italic cyan")
        console.print(Panel(header_text, border_style=tier_color.split()[-1]))

        # KYC & Identity Details Table
        kyc_table = Table(title="KYC Demographics & Watchlist Screening", show_header=False, box=None)
        kyc_table.add_column("Field", style="bold cyan", width=24)
        kyc_table.add_column("Value", width=60)

        kyc_table.add_row("Citizenship:", f"{cust['citizenship']} (Dual: {cust.get('dual_citizenship') or 'None'})")
        kyc_table.add_row("Country of Residence:", f"{cust['residence_country']} (Tax: {cust['tax_residence_country']})")
        kyc_table.add_row("Address:", f"{cust['address_line']}, {cust['address_city']} {cust['address_postal_code']}")
        kyc_table.add_row("Age / Date of Birth:", f"{cust['age']} years ({cust['date_of_birth']})")
        kyc_table.add_row("Occupation / Industry:", f"{cust['occupation']} ({cust['industry']})")
        kyc_table.add_row("Employer:", cust['employer_name'] or "N/A (Self-employed / Retired)")
        kyc_table.add_row("Declared Annual Income:", f"${cust['annual_income_usd']:,.2f} USD")
        kyc_table.add_row("Declared Net Worth:", f"${cust['net_worth_usd']:,.2f} USD")
        kyc_table.add_row("Source of Funds / Wealth:", f"{cust['source_of_funds']} | {cust['source_of_wealth']}")
        kyc_table.add_row("Declared Expected Turnover:", f"${cust['declared_expected_monthly_turnover_usd']:,.2f}/mo (Max single: ${cust['declared_expected_max_single_tx_usd']:,.2f})")
        kyc_table.add_row("Account Purpose & Nature:", cust['declared_purpose_nature'])
        kyc_table.add_row("Onboarding Channel:", f"{cust['onboarding_channel']} (Date: {cust['onboarding_date']})")
        kyc_table.add_row("Products Held:", ", ".join(cust['products_held']))
        kyc_table.add_row("PEP Screening Status:", f"[{'red' if cust['pep_status'] != 'NONE' else 'green'}]{cust['pep_status']}[/] ({cust['pep_details'] or 'Clean'})")
        kyc_table.add_row("Adverse Media:", f"[{'red' if cust['adverse_media'] != 'NONE' else 'green'}]{cust['adverse_media']}[/] ({cust['adverse_media_details'] or 'Clean'})")
        kyc_table.add_row("Sanctions Status:", f"[{'red' if cust['sanction_status'] == 'CONFIRMED_HIT' else 'green'}]{cust['sanction_status']}[/] ({cust['sanction_details'] or 'Clean'})")
        
        # Digital Identity & Fraud Telemetry
        kyc_table.add_row("Email & Domain:", f"{cust.get('email_address') or 'N/A'} (Domain: {cust.get('email_domain_type') or 'STANDARD'})")
        kyc_table.add_row("Phone & Line Type:", f"{cust.get('phone_number') or 'N/A'} ({cust.get('phone_line_type') or 'MOBILE'})")
        kyc_table.add_row("Primary Device ID:", cust.get('device_primary_id') or 'N/A')
        kyc_table.add_row("Registered IP / Geo:", f"{cust.get('primary_ip_address') or 'N/A'} ({cust.get('primary_ip_country') or 'N/A'})")
        synth_score = cust.get('synthetic_identity_score') or 0.0
        synth_style = "red" if synth_score > 60 else "green"
        kyc_table.add_row("Synthetic Identity Risk:", f"[{synth_style}]{synth_score:.1f} / 100[/]")
        kyc_table.add_row("Synthetic Archetype:", cust['archetype'])

        console.print(Panel(kyc_table, title="[bold]Demographic, KYC & Digital Footprint File[/bold]", border_style="blue"))

        # Risk Pillars Table (FRAML)
        pillar_table = Table(title="FRAML Multi-Pillar Risk Engine Breakdown", show_header=True, header_style="bold magenta")
        pillar_table.add_column("Pillar Name", width=34)
        pillar_table.add_column("Weight", justify="center", width=10)
        pillar_table.add_column("Raw Score (0-100)", justify="right", width=18)
        pillar_table.add_column("Weighted Score", justify="right", width=16)

        pillar_table.add_row("1. Customer KYC & Demographics", "20%", f"{assessment['kyc_raw_score']:.1f}", f"{assessment['kyc_weighted_score']:.2f}")
        pillar_table.add_row("2. Purpose & Nature of Relationship", "10%", f"{assessment['purpose_raw_score']:.1f}", f"{assessment['purpose_weighted_score']:.2f}")
        pillar_table.add_row("3. Products & Onboarding Channels", "10%", f"{assessment['product_raw_score']:.1f}", f"{assessment['product_weighted_score']:.2f}")
        pillar_table.add_row("4. AML Transaction Monitoring", "30%", f"{assessment['behavioral_raw_score']:.1f}", f"{assessment['behavioral_weighted_score']:.2f}")
        fraud_raw = assessment.get('fraud_raw_score', 0.0) or 0.0
        fraud_wt = assessment.get('fraud_weighted_score', 0.0) or 0.0
        pillar_table.add_row("5. Fraud Risk & Digital Footprint", "30%", f"{fraud_raw:.1f}", f"{fraud_wt:.2f}")
        pillar_table.add_row("[bold]Composite Score (FRAML)[/bold]", "100%", "", f"[bold {tier_color}]{assessment['composite_score']:.2f}[/]")

        console.print(pillar_table)

        # Fraud Alerts Section
        fraud_alerts = data.get("fraud_alerts", [])
        if fraud_alerts:
            console.print(f"\n[bold magenta]TRIGGERED FRAUD ALERTS ({len(fraud_alerts)} ALERTS):[/bold magenta]")
            for falt in fraud_alerts:
                falt_color = get_tier_color(falt["severity"])
                falt_text = Text()
                falt_text.append(f"[{falt['rule_id']}] {falt['rule_name']} (Severity: {falt['severity']})\n", style=f"bold {falt_color}")
                falt_text.append(f"Summary: {falt['summary']}\n", style="white")
                if falt.get('supporting_transaction_ids'):
                    falt_text.append(f"Supporting Transaction IDs: {', '.join(falt['supporting_transaction_ids'])}\n", style="dim cyan")
                console.print(Panel(falt_text, border_style=falt_color.split()[-1]))
        else:
            console.print("\n[green]✓ Zero Fraud alerts detected.[/green]")

        # AML Alerts Section
        if alerts:
            console.print(f"\n[bold yellow]TRIGGERED AML TRANSACTION MONITORING ALERTS ({len(alerts)} ALERTS):[/bold yellow]")
            for alt in alerts:
                alt_color = get_tier_color(alt["severity"])
                alert_text = Text()
                alert_text.append(f"[{alt['rule_id']}] {alt['rule_name']} (Severity: {alt['severity']})\n", style=f"bold {alt_color}")
                alert_text.append(f"Summary: {alt['summary']}\n", style="white")
                if alt.get('supporting_transaction_ids'):
                    alert_text.append(f"Supporting Transaction IDs: {', '.join(alt['supporting_transaction_ids'])}\n", style="dim cyan")
                console.print(Panel(alert_text, border_style=alt_color.split()[-1]))
        else:
            console.print("\n[green]✓ Zero AML alerts triggered.[/green]")

        # Action Checklist
        console.print(f"\n[bold yellow]COMPLIANCE & EDD AUDIT ACTION CHECKLIST:[/bold yellow]")
        for item in json.loads(assessment["action_checklist"]):
            console.print(f"  [cyan]•[/cyan] {item}")

        # Recent Transactions
        console.print(f"\n[bold underline]TRANSACTION HISTORY ({len(transactions)} TOTAL)[/bold underline]")
        tx_table = Table(show_header=True, header_style="bold cyan")
        tx_table.add_column("Tx ID", width=14)
        tx_table.add_column("Timestamp", width=19)
        tx_table.add_column("Type", width=22)
        tx_table.add_column("Dir", justify="center", width=8)
        tx_table.add_column("Amount USD", justify="right", width=14)
        tx_table.add_column("Counterparty", width=28)
        tx_table.add_column("Channel", width=14)

        for t in transactions[:12]:
            amt_style = "green" if t["direction"] == "INBOUND" else "red"
            susp_mark = " [red]*[/red]" if t["is_suspicious_synthetic"] else ""
            tx_table.add_row(
                f"{t['transaction_id']}{susp_mark}",
                t["timestamp"][:19],
                t["transaction_type"],
                t["direction"],
                f"[{amt_style}]${t['amount_usd']:,.2f}[/{amt_style}]",
                f"{t['counterparty_name']} ({t['counterparty_country']})",
                t["channel"]
            )
        console.print(tx_table)

    else:
        print(f"Customer Dossier: {cust['first_name']} {cust['last_name']} ({cust['customer_id']})")
        print(f"Tier: {tier} | Composite Score: {score}")
        print(f"Alerts: {len(alerts)}")

def handle_serve(args):
    """Launches local interactive compliance web server."""
    port = args.port
    from web.server import run_server
    run_server(port=port)

def main():
    parser = argparse.ArgumentParser(description="Synthetic Banking KYC & Transaction Monitoring Risk Platform")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # generate command
    p_gen = subparsers.add_parser("generate", help="Generate synthetic individual customer cohort and run risk scoring")
    p_gen.add_argument("--count", type=int, default=100, help="Number of individual customers to generate (default: 100)")
    p_gen.add_argument("--days", type=int, default=90, help="Days of transaction history to simulate (default: 90)")
    p_gen.add_argument("--seed", type=int, default=42, help="Random seed for deterministic generation (default: 42)")
    p_gen.add_argument("--export", action="store_true", default=True, help="Export CSV tables to ./exports/ (default: True)")

    # inspect command
    p_insp = subparsers.add_parser("inspect", help="Inspect complete Customer 360 file and risk score")
    p_insp.add_argument("customer_id", type=str, help="Customer ID to inspect (e.g. CUST-00001)")

    # summary command
    subparsers.add_parser("summary", help="Display portfolio risk distribution and alert statistics")

    # export command
    subparsers.add_parser("export", help="Export existing SQLite database to CSV tables")

    # serve command
    p_srv = subparsers.add_parser("serve", help="Launch interactive compliance web dashboard")
    p_srv.add_argument("--port", type=int, default=8088, help="Port to serve dashboard on (default: 8088)")

    args = parser.parse_args()

    if args.command == "generate":
        handle_generate(args)
    elif args.command == "inspect":
        handle_inspect(args)
    elif args.command == "summary":
        handle_summary(args)
    elif args.command == "export":
        db = DatabaseManager()
        db.export_to_csv("exports")
    elif args.command == "serve":
        handle_serve(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
