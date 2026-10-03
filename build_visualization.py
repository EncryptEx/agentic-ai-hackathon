"""Builds a standalone, fully self-contained HTML visualization of KYC, AML, & Fraud (FRAML)."""

import sqlite3
import json
import os

def build_standalone_html(db_path: str = "data/kyc_aml.db", output_html_path: str = "visualization.html"):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. Fetch Customers
    cursor.execute("""
    SELECT c.*, r.composite_score, r.risk_tier, r.kyc_raw_score, r.kyc_weighted_score,
           r.purpose_raw_score, r.purpose_weighted_score, r.product_raw_score, r.product_weighted_score,
           r.behavioral_raw_score, r.behavioral_weighted_score,
           r.fraud_raw_score, r.fraud_weighted_score,
           r.alert_count, r.highest_alert_severity,
           r.fraud_alert_count, r.highest_fraud_severity,
           r.aml_score, r.fraud_score,
           r.recommended_action, r.action_checklist, r.executive_summary
    FROM customers c
    LEFT JOIN risk_assessments r ON c.customer_id = r.customer_id
    ORDER BY r.composite_score DESC
    """)
    customers = []
    for r in cursor.fetchall():
        d = dict(r)
        d["products_held"] = json.loads(d["products_held"]) if d["products_held"] else []
        d["action_checklist"] = json.loads(d["action_checklist"]) if d["action_checklist"] else []
        d["synthetic_id_indicators"] = json.loads(d["synthetic_id_indicators"]) if d.get("synthetic_id_indicators") else []
        customers.append(d)

    # 2. Fetch Alerts (both AML and Fraud)
    cursor.execute("SELECT * FROM alerts")
    alerts = []
    for r in cursor.fetchall():
        d = dict(r)
        d["trigger_details"] = json.loads(d["trigger_details"]) if d.get("trigger_details") else {}
        d["supporting_transaction_ids"] = json.loads(d["supporting_transaction_ids"]) if d.get("supporting_transaction_ids") else []
        alerts.append(d)

    # 3. Fetch Transactions
    cursor.execute("SELECT * FROM transactions ORDER BY timestamp DESC")
    transactions = [dict(r) for r in cursor.fetchall()]

    # 4. Summary metrics
    total_customers = len(customers)
    total_tx = len(transactions)
    total_volume = sum(t["amount_usd"] for t in transactions)
    aml_alerts_count = sum(1 for a in alerts if a.get("alert_type") == "AML" or not a.get("alert_type"))
    fraud_alerts_count = sum(1 for a in alerts if a.get("alert_type") == "FRAUD")
    critical_count = sum(1 for c in customers if c.get("risk_tier") == "CRITICAL")
    high_count = sum(1 for c in customers if c.get("risk_tier") == "HIGH")
    medium_count = sum(1 for c in customers if c.get("risk_tier") == "MEDIUM")
    low_count = sum(1 for c in customers if c.get("risk_tier") == "LOW")

    # Serialize data for embedding
    cust_json = json.dumps(customers)
    tx_json = json.dumps(transactions)
    alerts_json = json.dumps(alerts)
    summary_json = json.dumps({
        "total_customers": total_customers,
        "total_transactions": total_tx,
        "total_volume_usd": total_volume,
        "total_alerts": len(alerts),
        "aml_alerts_count": aml_alerts_count,
        "fraud_alerts_count": fraud_alerts_count,
        "tier_counts": {
            "CRITICAL": critical_count,
            "HIGH": high_count,
            "MEDIUM": medium_count,
            "LOW": low_count
        }
    })

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Valiant Bank - KYC, AML & Fraud Risk Visualizer (FRAML)</title>
    <!-- Chart.js for interactive analytics -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
    <style>
        :root {{
            --bg-body: #090d16;
            --bg-surface: #101726;
            --bg-card: #172033;
            --bg-card-hover: #1e2b45;
            --border-subtle: #24324d;
            --border-focus: #3b82f6;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --text-dim: #64748b;
            --accent-blue: #3b82f6;
            --accent-purple: #8b5cf6;
            --tier-low: #10b981;
            --tier-low-bg: rgba(16, 185, 129, 0.12);
            --tier-med: #f59e0b;
            --tier-med-bg: rgba(245, 158, 11, 0.12);
            --tier-high: #f97316;
            --tier-high-bg: rgba(249, 115, 22, 0.12);
            --tier-crit: #ef4444;
            --tier-crit-bg: rgba(239, 68, 68, 0.14);
            --fraud-magenta: #d946ef;
            --fraud-magenta-bg: rgba(217, 70, 239, 0.15);
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }}

        body {{
            background-color: var(--bg-body);
            color: var(--text-main);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }}

        header {{
            background: linear-gradient(180deg, #131c2e 0%, var(--bg-surface) 100%);
            border-bottom: 1px solid var(--border-subtle);
            padding: 16px 32px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            position: sticky;
            top: 0;
            z-index: 100;
        }}

        .brand {{
            display: flex;
            align-items: center;
            gap: 14px;
        }}

        .brand-logo {{
            width: 42px;
            height: 42px;
            background: linear-gradient(135deg, #2563eb 0%, #7c3aed 50%, #d946ef 100%);
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 22px;
            box-shadow: 0 4px 14px rgba(217, 70, 239, 0.35);
        }}

        .brand-text h1 {{
            font-size: 18px;
            font-weight: 700;
            letter-spacing: 0.5px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .badge-live {{
            background: rgba(16, 185, 129, 0.2);
            color: #10b981;
            font-size: 10px;
            font-weight: 700;
            padding: 2px 8px;
            border-radius: 999px;
            border: 1px solid rgba(16, 185, 129, 0.4);
            text-transform: uppercase;
        }}

        .badge-framl {{
            background: rgba(217, 70, 239, 0.2);
            color: #d946ef;
            font-size: 10px;
            font-weight: 700;
            padding: 2px 8px;
            border-radius: 999px;
            border: 1px solid rgba(217, 70, 239, 0.4);
            text-transform: uppercase;
        }}

        .brand-text p {{
            font-size: 12px;
            color: var(--text-muted);
        }}

        .nav-tabs {{
            display: flex;
            gap: 6px;
            background: var(--bg-card);
            padding: 4px;
            border-radius: 8px;
            border: 1px solid var(--border-subtle);
        }}

        .nav-btn {{
            background: transparent;
            border: none;
            color: var(--text-muted);
            padding: 8px 16px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
        }}

        .nav-btn.active, .nav-btn:hover {{
            background: var(--accent-blue);
            color: #fff;
        }}

        main {{
            flex: 1;
            padding: 24px 32px;
            max-width: 1700px;
            width: 100%;
            margin: 0 auto;
        }}

        /* KPI Grid */
        .kpi-row {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
            gap: 16px;
            margin-bottom: 22px;
        }}

        .kpi-card {{
            background: var(--bg-surface);
            border: 1px solid var(--border-subtle);
            border-radius: 10px;
            padding: 16px 20px;
            position: relative;
            overflow: hidden;
            box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        }}

        .kpi-card::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 4px;
            height: 100%;
            background: var(--accent-blue);
        }}

        .kpi-card.low::before {{ background: var(--tier-low); }}
        .kpi-card.med::before {{ background: var(--tier-med); }}
        .kpi-card.high::before {{ background: var(--tier-high); }}
        .kpi-card.crit::before {{ background: var(--tier-crit); }}
        .kpi-card.fraud::before {{ background: var(--fraud-magenta); }}

        .kpi-title {{
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            color: var(--text-muted);
            letter-spacing: 0.6px;
        }}

        .kpi-val {{
            font-size: 26px;
            font-weight: 800;
            margin: 6px 0 2px 0;
        }}

        .kpi-desc {{
            font-size: 12px;
            color: var(--text-dim);
        }}

        /* Charts Row */
        .charts-row {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
            gap: 18px;
            margin-bottom: 24px;
        }}

        .chart-box {{
            background: var(--bg-surface);
            border: 1px solid var(--border-subtle);
            border-radius: 10px;
            padding: 18px 20px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            display: flex;
            flex-direction: column;
        }}

        .chart-box h3 {{
            font-size: 12px;
            font-weight: 700;
            text-transform: uppercase;
            color: var(--text-muted);
            margin-bottom: 12px;
            letter-spacing: 0.5px;
            display: flex;
            justify-content: space-between;
        }}

        .chart-canvas-wrap {{
            flex: 1;
            position: relative;
            min-height: 190px;
        }}

        /* Controls */
        .controls-row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 16px;
            background: var(--bg-surface);
            border: 1px solid var(--border-subtle);
            border-radius: 8px;
            padding: 12px 18px;
            margin-bottom: 16px;
            flex-wrap: wrap;
        }}

        .search-field {{
            flex: 1;
            min-width: 280px;
            position: relative;
        }}

        .search-field input {{
            width: 100%;
            background: var(--bg-card);
            border: 1px solid var(--border-subtle);
            border-radius: 6px;
            padding: 8px 14px 8px 36px;
            color: var(--text-main);
            font-size: 13px;
            outline: none;
        }}

        .search-field input:focus {{
            border-color: var(--border-focus);
        }}

        .search-field::before {{
            content: "🔍";
            position: absolute;
            left: 12px;
            top: 50%;
            transform: translateY(-50%);
            font-size: 13px;
            opacity: 0.6;
        }}

        .filter-group {{
            display: flex;
            gap: 8px;
            align-items: center;
            flex-wrap: wrap;
        }}

        .filter-pill {{
            background: var(--bg-card);
            border: 1px solid var(--border-subtle);
            color: var(--text-muted);
            padding: 6px 14px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.15s ease;
        }}

        .filter-pill.active {{
            background: var(--accent-blue);
            color: #fff;
            border-color: var(--accent-blue);
        }}

        /* Table */
        .table-wrap {{
            background: var(--bg-surface);
            border: 1px solid var(--border-subtle);
            border-radius: 10px;
            overflow-x: auto;
            box-shadow: 0 4px 16px rgba(0,0,0,0.2);
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
            text-align: left;
        }}

        thead {{
            background: #141c2c;
            border-bottom: 1px solid var(--border-subtle);
        }}

        th {{
            padding: 13px 16px;
            color: var(--text-muted);
            font-weight: 600;
            text-transform: uppercase;
            font-size: 11px;
            letter-spacing: 0.5px;
            white-space: nowrap;
        }}

        tbody tr {{
            border-bottom: 1px solid var(--border-subtle);
            cursor: pointer;
            transition: background 0.15s ease;
        }}

        tbody tr:hover {{
            background: var(--bg-card-hover);
        }}

        td {{
            padding: 12px 16px;
            white-space: nowrap;
        }}

        /* Badges */
        .badge {{
            display: inline-block;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .badge-LOW {{ background: var(--tier-low-bg); color: var(--tier-low); border: 1px solid var(--tier-low); }}
        .badge-MEDIUM {{ background: var(--tier-med-bg); color: var(--tier-med); border: 1px solid var(--tier-med); }}
        .badge-HIGH {{ background: var(--tier-high-bg); color: var(--tier-high); border: 1px solid var(--tier-high); }}
        .badge-CRITICAL {{ background: var(--tier-crit-bg); color: var(--tier-crit); border: 1px solid var(--tier-crit); }}

        .badge-inbound {{ background: rgba(16, 185, 129, 0.15); color: #10b981; font-weight: 700; }}
        .badge-outbound {{ background: rgba(239, 68, 68, 0.15); color: #ef4444; font-weight: 700; }}
        .badge-fraud {{ background: var(--fraud-magenta-bg); color: var(--fraud-magenta); border: 1px solid var(--fraud-magenta); font-weight: bold; }}
        .badge-aml {{ background: rgba(249, 115, 22, 0.15); color: #f97316; border: 1px solid #f97316; font-weight: bold; }}

        /* Slide-out Dossier */
        .modal-mask {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.75);
            backdrop-filter: blur(4px);
            z-index: 1000;
            display: flex;
            justify-content: flex-end;
            opacity: 0;
            pointer-events: none;
            transition: opacity 0.25s ease;
        }}

        .modal-mask.open {{
            opacity: 1;
            pointer-events: auto;
        }}

        .dossier-drawer {{
            background: var(--bg-surface);
            width: 920px;
            max-width: 95vw;
            height: 100vh;
            border-left: 1px solid var(--border-subtle);
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            box-shadow: -15px 0 35px rgba(0,0,0,0.6);
            transform: translateX(100%);
            transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1);
        }}

        .modal-mask.open .dossier-drawer {{
            transform: translateX(0);
        }}

        .dossier-head {{
            padding: 20px 28px;
            background: #141c2c;
            border-bottom: 1px solid var(--border-subtle);
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            position: sticky;
            top: 0;
            z-index: 20;
        }}

        .close-drawer-btn {{
            background: transparent;
            border: none;
            color: var(--text-dim);
            font-size: 26px;
            cursor: pointer;
            line-height: 1;
        }}

        .close-drawer-btn:hover {{ color: #fff; }}

        .dossier-body {{
            padding: 24px 28px;
            display: flex;
            flex-direction: column;
            gap: 22px;
        }}

        /* Pillar Grid */
        .pillar-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 12px;
        }}

        .pillar-item {{
            background: var(--bg-card);
            border: 1px solid var(--border-subtle);
            border-radius: 8px;
            padding: 14px;
        }}

        .pillar-item h4 {{
            font-size: 12px;
            color: var(--text-muted);
            display: flex;
            justify-content: space-between;
            margin-bottom: 6px;
        }}

        .score-track {{
            height: 6px;
            background: var(--bg-body);
            border-radius: 3px;
            overflow: hidden;
            margin-bottom: 8px;
        }}

        .score-fill {{
            height: 100%;
            background: var(--accent-blue);
            border-radius: 3px;
        }}

        .score-fill.fraud {{
            background: var(--fraud-magenta);
        }}

        .pillar-fact {{
            font-size: 11px;
            color: var(--text-dim);
            margin-bottom: 3px;
            line-height: 1.35;
        }}

        /* Alert Callouts */
        .alert-callout {{
            background: rgba(239, 68, 68, 0.08);
            border-left: 4px solid var(--tier-crit);
            padding: 12px 16px;
            border-radius: 0 6px 6px 0;
            margin-bottom: 10px;
        }}

        .alert-callout.fraud {{
            border-left-color: var(--fraud-magenta);
            background: var(--fraud-magenta-bg);
        }}

        .alert-callout.HIGH {{ border-left-color: var(--tier-high); background: rgba(249, 115, 22, 0.08); }}
        .alert-callout.MEDIUM {{ border-left-color: var(--tier-med); background: rgba(245, 158, 11, 0.08); }}

        .alert-headline {{
            font-weight: 700;
            font-size: 13px;
            margin-bottom: 4px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .alert-text {{
            font-size: 12px;
            color: var(--text-muted);
            line-height: 1.4;
        }}

        /* Visual Money Flow Card */
        .typology-flow {{
            background: linear-gradient(135deg, rgba(37,99,235,0.08) 0%, rgba(217,70,239,0.08) 100%);
            border: 1px dashed var(--accent-blue);
            border-radius: 8px;
            padding: 16px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin: 12px 0;
            gap: 8px;
            overflow-x: auto;
        }}

        .flow-node {{
            background: var(--bg-card);
            border: 1px solid var(--border-subtle);
            border-radius: 6px;
            padding: 10px 14px;
            text-align: center;
            min-width: 130px;
        }}

        .flow-node-title {{
            font-size: 11px;
            color: var(--text-dim);
            text-transform: uppercase;
        }}

        .flow-node-val {{
            font-size: 13px;
            font-weight: 700;
            color: var(--text-main);
            margin-top: 2px;
        }}

        .flow-arrow {{
            color: var(--accent-blue);
            font-size: 18px;
            font-weight: bold;
        }}

        /* Pagination */
        .pagination-row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 14px 18px;
            background: var(--bg-surface);
            border-top: 1px solid var(--border-subtle);
            font-size: 12px;
            color: var(--text-muted);
        }}

        .page-btn {{
            background: var(--bg-card);
            border: 1px solid var(--border-subtle);
            color: var(--text-main);
            padding: 5px 12px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
        }}

        .page-btn:disabled {{
            opacity: 0.4;
            cursor: not-allowed;
        }}
    </style>
</head>
<body>

    <header>
        <div class="brand">
            <div class="brand-logo">🛡️</div>
            <div class="brand-text">
                <h1>VALIANT BANK FRAML PLATFORM <span class="badge-framl">Fraud + AML</span> <span class="badge-live">Live</span></h1>
                <p>Integrated KYC, Anti-Money Laundering & First/Third-Party Fraud Risk Engine</p>
            </div>
        </div>
        <div class="nav-tabs">
            <button class="nav-btn active" onclick="switchView('tab-customers', this)">Customers ({total_customers})</button>
            <button class="nav-btn" onclick="switchView('tab-transactions', this)">Transactions ({total_tx:,})</button>
            <button class="nav-btn" onclick="switchView('tab-fraud', this)">Fraud Typologies ({fraud_alerts_count})</button>
            <button class="nav-btn" onclick="switchView('tab-aml', this)">AML Typologies ({aml_alerts_count})</button>
        </div>
    </header>

    <main>
        <!-- Top KPI Cards -->
        <section class="kpi-row">
            <div class="kpi-card">
                <div class="kpi-title">Total Customers Monitored</div>
                <div class="kpi-val">{total_customers}</div>
                <div class="kpi-desc">100% Individual Retail Profiles</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">Transactions Monitored</div>
                <div class="kpi-val">{total_tx:,}</div>
                <div class="kpi-desc">${total_volume:,.2f} USD Gross Flow</div>
            </div>
            <div class="kpi-card fraud">
                <div class="kpi-title">Active Fraud Alerts</div>
                <div class="kpi-val">{fraud_alerts_count}</div>
                <div class="kpi-desc">ATO, Card Testing, APP Scams, Bust-out</div>
            </div>
            <div class="kpi-card high">
                <div class="kpi-title">Active AML Alerts</div>
                <div class="kpi-val">{aml_alerts_count}</div>
                <div class="kpi-desc">Structuring, Mules, Corridors, Volume</div>
            </div>
            <div class="kpi-card crit">
                <div class="kpi-title">Critical & High Risk Clients</div>
                <div class="kpi-val">{critical_count + high_count}</div>
                <div class="kpi-desc">{critical_count} Critical (Lockdown/SAR) | {high_count} High (EDD)</div>
            </div>
        </section>

        <!-- Charts Row -->
        <section class="charts-row">
            <div class="chart-box">
                <h3><span>FRAML Risk Tier Distribution</span></h3>
                <div class="chart-canvas-wrap">
                    <canvas id="chart-tiers"></canvas>
                </div>
            </div>
            <div class="chart-box">
                <h3><span>Top Fraud & AML Typologies</span></h3>
                <div class="chart-canvas-wrap">
                    <canvas id="chart-typologies"></canvas>
                </div>
            </div>
            <div class="chart-box">
                <h3><span>Transaction Volume by Channel</span></h3>
                <div class="chart-canvas-wrap">
                    <canvas id="chart-channels"></canvas>
                </div>
            </div>
        </section>

        <!-- VIEW 1: CUSTOMERS -->
        <div id="tab-customers" class="view-panel">
            <div class="controls-row">
                <div class="search-field">
                    <input type="text" id="cust-search" placeholder="Search by name, ID, nationality, occupation, or archetype..." oninput="handleCustomerSearch()">
                </div>
                <div class="filter-group">
                    <button class="filter-pill active" onclick="filterCustomerTier('ALL', this)">All ({total_customers})</button>
                    <button class="filter-pill" onclick="filterCustomerTier('CRITICAL', this)">Critical ({critical_count})</button>
                    <button class="filter-pill" onclick="filterCustomerTier('HIGH', this)">High ({high_count})</button>
                    <button class="filter-pill" onclick="filterCustomerTier('MEDIUM', this)">Medium ({medium_count})</button>
                    <button class="filter-pill" onclick="filterCustomerTier('LOW', this)">Low ({low_count})</button>
                </div>
            </div>

            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>Customer ID</th>
                            <th>Customer Name</th>
                            <th>Citizenship / Res</th>
                            <th>Occupation & Sector</th>
                            <th>Archetype</th>
                            <th>Tier</th>
                            <th>FRAML Score</th>
                            <th>AML Score</th>
                            <th>Fraud Score</th>
                            <th>Alerts</th>
                        </tr>
                    </thead>
                    <tbody id="customers-table-body">
                        <!-- Populated by JavaScript -->
                    </tbody>
                </table>
            </div>
        </div>

        <!-- VIEW 2: TRANSACTIONS -->
        <div id="tab-transactions" class="view-panel" style="display: none;">
            <div class="controls-row">
                <div class="search-field">
                    <input type="text" id="tx-search" placeholder="Search transaction ID, counterparty, narrative, device, or customer..." oninput="handleTxSearch()">
                </div>
                <div class="filter-group">
                    <label style="display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--fraud-magenta); font-weight: 700; cursor: pointer;">
                        <input type="checkbox" id="tx-fraud-only" onchange="handleTxSearch()">
                        Fraud Only
                    </label>
                    <label style="display: flex; align-items: center; gap: 6px; font-size: 12px; color: #f97316; font-weight: 700; cursor: pointer;">
                        <input type="checkbox" id="tx-aml-only" onchange="handleTxSearch()">
                        AML Suspicious Only
                    </label>
                    <select id="tx-dir-filter" onchange="handleTxSearch()" style="background: var(--bg-card); color: var(--text-main); border: 1px solid var(--border-subtle); padding: 6px 10px; border-radius: 6px; font-size: 12px;">
                        <option value="ALL">All Directions</option>
                        <option value="INBOUND">Inbound Only</option>
                        <option value="OUTBOUND">Outbound Only</option>
                    </select>
                </div>
            </div>

            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>Tx ID</th>
                            <th>Customer</th>
                            <th>Timestamp</th>
                            <th>Type</th>
                            <th>Direction</th>
                            <th>Amount (USD)</th>
                            <th>Counterparty (Country)</th>
                            <th>Channel & Device</th>
                            <th>Auth Status</th>
                            <th>Flag / Typology</th>
                        </tr>
                    </thead>
                    <tbody id="transactions-table-body">
                        <!-- Populated by JavaScript -->
                    </tbody>
                </table>
                <div class="pagination-row">
                    <span id="tx-page-info">Showing transactions...</span>
                    <div>
                        <button class="page-btn" id="tx-prev-btn" onclick="prevTxPage()">Previous</button>
                        <button class="page-btn" id="tx-next-btn" onclick="nextTxPage()">Next</button>
                    </div>
                </div>
            </div>
        </div>

        <!-- VIEW 3: FRAUD TYPOLOGY ATTACK FLOWS -->
        <div id="tab-fraud" class="view-panel" style="display: none;">
            <div style="margin-bottom: 20px;">
                <h2 style="font-size: 18px; margin-bottom: 4px;">Fraud Typology Attack Pathways & Real-Time Controls</h2>
                <p style="color: var(--text-muted); font-size: 13px;">Examine the anatomy of first-party and third-party fraud attacks detected across retail digital channels.</p>
            </div>

            <!-- Fraud 1: ATO & Impossible Travel -->
            <div style="background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: 10px; padding: 22px; margin-bottom: 20px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                    <div>
                        <span class="badge badge-CRITICAL">Typology FR-01</span>
                        <h3 style="font-size: 16px; margin-top: 4px;">Account Takeover (ATO) & Impossible Travel Velocity</h3>
                    </div>
                    <span style="color: #ef4444; font-size: 12px; font-weight: 700;">Immediate Session Revocation Required</span>
                </div>
                <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 14px;">
                    Credential stuffing or SIM-swap leads to unauthorized web session from a foreign proxy. An impossible travel distance (>900 km/h) is recorded within 40 minutes of a legitimate customer session.
                </p>
                <div class="typology-flow">
                    <div class="flow-node">
                        <div class="flow-node-title">Legitimate User (14:10)</div>
                        <div class="flow-node-val" style="color: #10b981;">Local In-Store POS</div>
                        <div style="font-size: 10px; color: var(--text-dim);">Device DEV-390743 (GB)</div>
                    </div>
                    <div class="flow-arrow">➔ 40m later ➔</div>
                    <div class="flow-node" style="border-color: #ef4444;">
                        <div class="flow-node-title">Hostile Login (14:45)</div>
                        <div class="flow-node-val" style="color: #ef4444;">Anonymous Proxy</div>
                        <div style="font-size: 10px; color: #ef4444;">IP 185.112.93.203 (NG)</div>
                    </div>
                    <div class="flow-arrow">➔</div>
                    <div class="flow-node" style="border-color: #ef4444;">
                        <div class="flow-node-title">Hostile Wire Drain</div>
                        <div class="flow-node-val" style="color: #ef4444;">$11,728.78 Wire Out</div>
                        <div style="font-size: 10px; color: #ef4444; font-weight: 700;">Offshore Crypto Ramp</div>
                    </div>
                </div>
            </div>

            <!-- Fraud 2: Card Testing Attack -->
            <div style="background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: 10px; padding: 22px; margin-bottom: 20px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                    <div>
                        <span class="badge badge-HIGH">Typology FR-02</span>
                        <h3 style="font-size: 16px; margin-top: 4px;">Card Testing / Micro-Authorization Probing Attack</h3>
                    </div>
                    <span style="color: #f97316; font-size: 12px; font-weight: 700;">Card Compromise / Botnet Test</span>
                </div>
                <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 14px;">
                    Botnet tests stolen card numbers via sub-$2.00 micro-charges on automated digital subscription merchants, then executes a four-figure CNP purchase within minutes.
                </p>
                <div class="typology-flow">
                    <div class="flow-node">
                        <div class="flow-node-title">Probe #1 (03:12)</div>
                        <div class="flow-node-val" style="color: #f59e0b;">$0.89 CNP E-comm</div>
                        <div style="font-size: 10px; color: var(--text-dim);">Digital Service (Authorized)</div>
                    </div>
                    <div class="flow-arrow">+</div>
                    <div class="flow-node">
                        <div class="flow-node-title">Probe #2 (03:16)</div>
                        <div class="flow-node-val" style="color: #f59e0b;">$1.45 CNP E-comm</div>
                        <div style="font-size: 10px; color: var(--text-dim);">Streaming Trial (Authorized)</div>
                    </div>
                    <div class="flow-arrow">➔ 12m later ➔</div>
                    <div class="flow-node" style="border-color: #ef4444;">
                        <div class="flow-node-title">High-Dollar Drain Attempt</div>
                        <div class="flow-node-val" style="color: #ef4444;">$3,450.00 CNP</div>
                        <div style="font-size: 10px; color: #ef4444; font-weight: 700;">Declined / Suspected Fraud</div>
                    </div>
                </div>
            </div>

            <!-- Fraud 3: First-Party Bust-Out -->
            <div style="background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: 10px; padding: 22px; margin-bottom: 20px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                    <div>
                        <span class="badge badge-CRITICAL">Typology FR-04</span>
                        <h3 style="font-size: 16px; margin-top: 4px;">First-Party Bust-Out & Deposit Kiting Fraud</h3>
                    </div>
                    <span style="color: #ef4444; font-size: 12px; font-weight: 700;">ACH Settlement Race Condition</span>
                </div>
                <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 14px;">
                    Fraudster deposits unverified external ACH funds, then races against the 48-hour clearing window to extract cash at ATMs and outbound P2P transfers before the ACH deposit bounces.
                </p>
                <div class="typology-flow">
                    <div class="flow-node">
                        <div class="flow-node-title">Inbound ACH (T=0)</div>
                        <div class="flow-node-val" style="color: #3b82f6;">+$9,850.00</div>
                        <div style="font-size: 10px; color: var(--text-dim);">External Link (Unverified)</div>
                    </div>
                    <div class="flow-arrow">➔ 24h burst ➔</div>
                    <div class="flow-node" style="border-color: #ef4444;">
                        <div class="flow-node-title">Rapid ATM Withdrawals</div>
                        <div class="flow-node-val" style="color: #ef4444;">2x $1,000 Cash</div>
                        <div style="font-size: 10px; color: var(--text-dim);">Metro 24h ATM Kiosk</div>
                    </div>
                    <div class="flow-arrow">+</div>
                    <div class="flow-node" style="border-color: #ef4444;">
                        <div class="flow-node-title">Outbound Peer Drain</div>
                        <div class="flow-node-val" style="color: #ef4444;">$7,300.00 P2P</div>
                        <div style="font-size: 10px; color: #ef4444; font-weight: 700;">Account Fully Depleted</div>
                    </div>
                </div>
            </div>

            <!-- Fraud 4: Synthetic Identity -->
            <div style="background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: 10px; padding: 22px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                    <div>
                        <span class="badge badge-HIGH">Typology FR-05</span>
                        <h3 style="font-size: 16px; margin-top: 4px;">Synthetic Identity Fraud & Burner Contact Screening</h3>
                    </div>
                    <span style="color: var(--fraud-magenta); font-size: 12px; font-weight: 700;">Fabricated Digital Footprint</span>
                </div>
                <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 14px;">
                    Applicant combines real SSN elements with fabricated names, disposable temporary email domains, and virtual VoIP burner numbers to construct an artificial credit file.
                </p>
                <div class="typology-flow">
                    <div class="flow-node" style="border-color: var(--fraud-magenta);">
                        <div class="flow-node-title">Burner Domain</div>
                        <div class="flow-node-val">throwawayinbox.com</div>
                        <div style="font-size: 10px; color: var(--fraud-magenta);">Disposable Temp Mail</div>
                    </div>
                    <div class="flow-arrow">+</div>
                    <div class="flow-node" style="border-color: var(--fraud-magenta);">
                        <div class="flow-node-title">Virtual VoIP Line</div>
                        <div class="flow-node-val">+1-555-PBX-VOIP</div>
                        <div style="font-size: 10px; color: var(--fraud-magenta);">No Carrier SIM Identity</div>
                    </div>
                    <div class="flow-arrow">➔</div>
                    <div class="flow-node" style="border-color: #ef4444;">
                        <div class="flow-node-title">Synthetic Algorithm</div>
                        <div class="flow-node-val" style="color: #ef4444;">Risk Index: 88.5/100</div>
                        <div style="font-size: 10px; color: #ef4444; font-weight: 700;">CIF Freeze Required</div>
                    </div>
                </div>
            </div>
        </div>

        <!-- VIEW 4: AML TYPOLOGIES -->
        <div id="tab-aml" class="view-panel" style="display: none;">
            <div style="margin-bottom: 20px;">
                <h2 style="font-size: 18px; margin-bottom: 4px;">Anti-Money Laundering (AML) Typologies</h2>
                <p style="color: var(--text-muted); font-size: 13px;">Review transaction laundering pathways flagged under Bank Secrecy Act / FATF standards.</p>
            </div>

            <!-- Typology: Structuring -->
            <div style="background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: 10px; padding: 22px; margin-bottom: 20px;">
                <span class="badge badge-HIGH">Typology TM-01</span>
                <h3 style="font-size: 16px; margin: 4px 0 10px 0;">Currency Transaction Reporting (CTR) Structuring / Smurfing</h3>
                <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 14px;">
                    Depositing multiple cash tranches in the $8,500–$9,900 range within 14 days to evade the $10,000 threshold.
                </p>
                <div class="typology-flow">
                    <div class="flow-node"><div class="flow-node-title">Deposit 1</div><div class="flow-node-val">$9,450 Cash</div></div>
                    <div class="flow-arrow">+</div>
                    <div class="flow-node"><div class="flow-node-title">Deposit 2 (+2d)</div><div class="flow-node-val">$9,600 Cash</div></div>
                    <div class="flow-arrow">+</div>
                    <div class="flow-node"><div class="flow-node-title">Deposit 3 (+4d)</div><div class="flow-node-val">$9,800 Cash</div></div>
                    <div class="flow-arrow">➔</div>
                    <div class="flow-node" style="border-color: #ef4444;"><div class="flow-node-title">Total Cluster</div><div class="flow-node-val" style="color: #ef4444;">$28,850.00</div><div style="font-size: 10px; color: #ef4444; font-weight: 700;">CTR Evaded</div></div>
                </div>
            </div>

            <!-- Typology: Mule -->
            <div style="background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: 10px; padding: 22px;">
                <span class="badge badge-CRITICAL">Typology TM-02</span>
                <h3 style="font-size: 16px; margin: 4px 0 10px 0;">Rapid Movement of Funds / Pass-Through Mule Account</h3>
                <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 14px;">
                    Large inbound corporate wire followed by immediate disbursement (>85% of funds) within 48 hours to crypto exchanges.
                </p>
                <div class="typology-flow">
                    <div class="flow-node"><div class="flow-node-title">Inbound Wire</div><div class="flow-node-val" style="color: #10b981;">+$31,986.22</div><div style="font-size: 10px; color: var(--text-dim);">Offshore FZE</div></div>
                    <div class="flow-arrow">➔</div>
                    <div class="flow-node"><div class="flow-node-title">Mule Account</div><div class="flow-node-val">Student Account</div><div style="font-size: 10px; color: var(--text-dim);">Turnover Ratio: 30x</div></div>
                    <div class="flow-arrow">➔</div>
                    <div class="flow-node" style="border-color: #ef4444;"><div class="flow-node-title">Crypto Outflow (T+22h)</div><div class="flow-node-val" style="color: #ef4444;">-$29,997.08 (93.8%)</div><div style="font-size: 10px; color: #ef4444; font-weight: 700;">Binance P2P</div></div>
                </div>
            </div>
        </div>
    </main>

    <!-- Slide-over Customer 360 Dossier Modal -->
    <div class="modal-mask" id="dossier-mask" onclick="closeDossierOnMask(event)">
        <div class="dossier-drawer" id="dossier-drawer">
            <div class="dossier-head">
                <div>
                    <h2 style="font-size: 16px; text-transform: uppercase; color: var(--accent-blue); letter-spacing: 0.5px;">Customer 360 Dossier</h2>
                    <p style="font-size: 12px; color: var(--text-muted);" id="dossier-subhead">Individual Retail FRAML File</p>
                </div>
                <button class="close-drawer-btn" onclick="closeDossier()">&times;</button>
            </div>
            <div class="dossier-body" id="dossier-body-content">
                <!-- Dynamically loaded -->
            </div>
        </div>
    </div>

    <!-- Embedded Data Payload -->
    <script>
        const CUSTOMERS_DATA = {cust_json};
        const TRANSACTIONS_DATA = {tx_json};
        const ALERTS_DATA = {alerts_json};
        const SUMMARY_DATA = {summary_json};

        let currentTier = "ALL";
        let currentCustSearch = "";
        let txSearchTerm = "";
        let txPage = 1;
        const txPageSize = 25;

        document.addEventListener("DOMContentLoaded", () => {{
            initCharts();
            renderCustomersTable();
            renderTransactionsTable();
        }});

        function switchView(tabId, btn) {{
            document.querySelectorAll(".view-panel").forEach(p => p.style.display = "none");
            document.getElementById(tabId).style.display = "block";
            document.querySelectorAll(".nav-btn").forEach(b => b.classList.remove("active"));
            if (btn) btn.classList.add("active");
        }}

        function initCharts() {{
            // 1. Tiers Chart
            const ctxTiers = document.getElementById("chart-tiers").getContext("2d");
            new Chart(ctxTiers, {{
                type: "doughnut",
                data: {{
                    labels: ["Low Risk", "Medium Risk", "High Risk", "Critical Risk"],
                    datasets: [{{
                        data: [
                            SUMMARY_DATA.tier_counts.LOW,
                            SUMMARY_DATA.tier_counts.MEDIUM,
                            SUMMARY_DATA.tier_counts.HIGH,
                            SUMMARY_DATA.tier_counts.CRITICAL
                        ],
                        backgroundColor: ["#10b981", "#f59e0b", "#f97316", "#ef4444"],
                        borderWidth: 2,
                        borderColor: "#101726"
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{
                        legend: {{ position: "right", labels: {{ color: "#94a3b8", font: {{ size: 11 }} }} }}
                    }}
                }}
            }});

            // 2. Typology Chart (Top Fraud and AML)
            const typologyCounts = {{}};
            ALERTS_DATA.forEach(a => {{
                typologyCounts[a.rule_name] = (typologyCounts[a.rule_name] || 0) + 1;
            }});
            const sortedTypo = Object.entries(typologyCounts).sort((a,b) => b[1] - a[1]).slice(0, 6);

            const ctxTypo = document.getElementById("chart-typologies").getContext("2d");
            new Chart(ctxTypo, {{
                type: "bar",
                data: {{
                    labels: sortedTypo.map(t => t[0].length > 20 ? t[0].substring(0, 18) + "..." : t[0]),
                    datasets: [{{
                        label: "Alert Count",
                        data: sortedTypo.map(t => t[1]),
                        backgroundColor: sortedTypo.map(t => t[0].includes("Account Takeover") || t[0].includes("Card Testing") || t[0].includes("Scam") || t[0].includes("Bust-Out") || t[0].includes("Synthetic") ? "#d946ef" : "#3b82f6"),
                        borderRadius: 4
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{ legend: {{ display: false }} }},
                    scales: {{
                        x: {{ ticks: {{ color: "#94a3b8", font: {{ size: 10 }} }}, grid: {{ display: false }} }},
                        y: {{ ticks: {{ color: "#94a3b8" }}, grid: {{ color: "#24324d" }} }}
                    }}
                }}
            }});

            // 3. Channels Chart
            const channelCounts = {{}};
            TRANSACTIONS_DATA.forEach(t => {{
                channelCounts[t.channel] = (channelCounts[t.channel] || 0) + t.amount_usd;
            }});

            const ctxChan = document.getElementById("chart-channels").getContext("2d");
            new Chart(ctxChan, {{
                type: "pie",
                data: {{
                    labels: Object.keys(channelCounts),
                    datasets: [{{
                        data: Object.values(channelCounts),
                        backgroundColor: ["#3b82f6", "#10b981", "#8b5cf6", "#f59e0b", "#ec4899", "#14b8a6"],
                        borderWidth: 2,
                        borderColor: "#101726"
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{
                        legend: {{ position: "right", labels: {{ color: "#94a3b8", font: {{ size: 10 }} }} }}
                    }}
                }}
            }});
        }}

        function filterCustomerTier(tier, btn) {{
            currentTier = tier;
            document.querySelectorAll(".filter-pill").forEach(p => p.classList.remove("active"));
            btn.classList.add("active");
            renderCustomersTable();
        }}

        function handleCustomerSearch() {{
            currentCustSearch = document.getElementById("cust-search").value.toLowerCase().trim();
            renderCustomersTable();
        }}

        function renderCustomersTable() {{
            const tbody = document.getElementById("customers-table-body");
            tbody.innerHTML = "";

            const filtered = CUSTOMERS_DATA.filter(c => {{
                if (currentTier !== "ALL" && c.risk_tier !== currentTier) return false;
                if (!currentCustSearch) return true;
                return (
                    c.customer_id.toLowerCase().includes(currentCustSearch) ||
                    (c.first_name + " " + c.last_name).toLowerCase().includes(currentCustSearch) ||
                    c.citizenship.toLowerCase().includes(currentCustSearch) ||
                    c.occupation.toLowerCase().includes(currentCustSearch) ||
                    c.archetype.toLowerCase().includes(currentCustSearch)
                );
            }});

            filtered.forEach(c => {{
                const tr = document.createElement("tr");
                tr.onclick = () => openDossier(c.customer_id);

                const totalAlts = (c.alert_count || 0) + (c.fraud_alert_count || 0);
                let alertBadge = `<span style="color: var(--text-dim);">Clean</span>`;
                if (c.fraud_alert_count > 0) {{
                    alertBadge = `<span class="badge badge-fraud">${{c.fraud_alert_count}} Fraud</span>`;
                }} else if (c.alert_count > 0) {{
                    alertBadge = `<span class="badge badge-aml">${{c.alert_count}} AML</span>`;
                }}

                tr.innerHTML = `
                    <td style="font-weight: 700; color: var(--accent-blue);">${{c.customer_id}}</td>
                    <td><strong>${{c.first_name}} ${{c.last_name}}</strong></td>
                    <td>${{c.citizenship}} <span style="color: var(--text-dim); font-size: 11px;">(res: ${{c.residence_country}})</span></td>
                    <td>${{c.occupation}}</td>
                    <td><span style="font-size: 11px; color: var(--text-muted); font-family: monospace;">${{c.archetype}}</span></td>
                    <td><span class="badge badge-${{c.risk_tier}}">${{c.risk_tier}}</span></td>
                    <td style="font-weight: 800;">${{c.composite_score.toFixed(1)}}</td>
                    <td style="color: #f97316; font-weight: 600;">${{(c.aml_score || 0).toFixed(1)}}</td>
                    <td style="color: var(--fraud-magenta); font-weight: 600;">${{(c.fraud_score || 0).toFixed(1)}}</td>
                    <td>${{alertBadge}}</td>
                `;
                tbody.appendChild(tr);
            }});
        }}

        function handleTxSearch() {{
            txPage = 1;
            renderTransactionsTable();
        }}

        function prevTxPage() {{
            if (txPage > 1) {{
                txPage--;
                renderTransactionsTable();
            }}
        }}

        function nextTxPage() {{
            txPage++;
            renderTransactionsTable();
        }}

        function renderTransactionsTable() {{
            const tbody = document.getElementById("transactions-table-body");
            tbody.innerHTML = "";

            const term = document.getElementById("tx-search").value.toLowerCase().trim();
            const fraudOnly = document.getElementById("tx-fraud-only").checked;
            const amlOnly = document.getElementById("tx-aml-only").checked;
            const dir = document.getElementById("tx-dir-filter").value;

            const filtered = TRANSACTIONS_DATA.filter(t => {{
                if (fraudOnly && !t.is_fraud_synthetic) return false;
                if (amlOnly && !t.is_suspicious_synthetic) return false;
                if (dir !== "ALL" && t.direction !== dir) return false;
                if (!term) return true;
                return (
                    t.transaction_id.toLowerCase().includes(term) ||
                    t.customer_id.toLowerCase().includes(term) ||
                    t.counterparty_name.toLowerCase().includes(term) ||
                    t.counterparty_country.toLowerCase().includes(term) ||
                    t.reference_narrative.toLowerCase().includes(term) ||
                    (t.device_id && t.device_id.toLowerCase().includes(term)) ||
                    (t.fraud_typology_tag && t.fraud_typology_tag.toLowerCase().includes(term)) ||
                    (t.synthetic_typology_tag && t.synthetic_typology_tag.toLowerCase().includes(term))
                );
            }});

            const start = (txPage - 1) * txPageSize;
            const end = start + txPageSize;
            const paged = filtered.slice(start, end);

            paged.forEach(t => {{
                const tr = document.createElement("tr");
                tr.onclick = () => openDossier(t.customer_id);

                let flagBadge = `<span style="color: var(--text-dim); font-size: 11px;">Standard</span>`;
                if (t.is_fraud_synthetic) {{
                    flagBadge = `<span class="badge badge-fraud">🚨 FRAUD: ${{t.fraud_typology_tag || 'SUSPECTED'}}</span>`;
                }} else if (t.is_suspicious_synthetic) {{
                    flagBadge = `<span class="badge badge-aml">⚠️ AML: ${{t.synthetic_typology_tag || 'SUSPICIOUS'}}</span>`;
                }}

                const authStyle = t.auth_status === "DECLINED_SUSPECTED_FRAUD" ? "color: #ef4444; font-weight: bold;" : "color: var(--text-dim); font-size: 11px;";

                tr.innerHTML = `
                    <td style="font-family: monospace; font-size: 12px; color: var(--accent-blue);">${{t.transaction_id}}</td>
                    <td><strong>${{t.customer_id}}</strong></td>
                    <td style="font-size: 11px; color: var(--text-muted);">${{t.timestamp.replace("T", " ").substring(0, 16)}}</td>
                    <td>${{t.transaction_type}}</td>
                    <td><span class="badge badge-${{t.direction.toLowerCase()}}">${{t.direction}}</span></td>
                    <td style="font-weight: 700; color: ${{t.direction === 'INBOUND' ? 'var(--tier-low)' : 'var(--text-main)'}};">$${{t.amount_usd.toLocaleString(undefined, {{minimumFractionDigits: 2}})}}</td>
                    <td>${{t.counterparty_name}} <span style="color: var(--text-dim); font-size: 11px;">(${{t.counterparty_country}})</span></td>
                    <td style="font-size: 11px;">${{t.channel}} <span style="color: var(--text-dim);">(${{t.device_id || 'N/A'}})</span></td>
                    <td style="${{authStyle}}">${{t.auth_status}}</td>
                    <td>${{flagBadge}}</td>
                `;
                tbody.appendChild(tr);
            }});

            document.getElementById("tx-page-info").textContent = `Showing ${{start + 1}}-${{Math.min(end, filtered.length)}} of ${{filtered.length.toLocaleString()}} transactions (Page ${{txPage}})`;
            document.getElementById("tx-prev-btn").disabled = (txPage === 1);
            document.getElementById("tx-next-btn").disabled = (end >= filtered.length);
        }}

        function openDossier(customerId) {{
            const customer = CUSTOMERS_DATA.find(c => c.customer_id === customerId);
            if (!customer) return;

            const custTxs = TRANSACTIONS_DATA.filter(t => t.customer_id === customerId);
            const custAlerts = ALERTS_DATA.filter(a => a.customer_id === customerId);
            const fraudAlerts = custAlerts.filter(a => a.alert_type === "FRAUD");
            const amlAlerts = custAlerts.filter(a => a.alert_type !== "FRAUD");

            document.getElementById("dossier-subhead").textContent = `${{customer.first_name}} ${{customer.last_name}} • ${{customer.customer_id}} (FRAML Dossier)`;

            const container = document.getElementById("dossier-body-content");
            container.innerHTML = `
                <!-- Top Summary Card -->
                <div style="background: var(--bg-card); border: 1px solid var(--border-subtle); padding: 18px 22px; border-radius: 8px;">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;">
                        <div>
                            <h2 style="font-size: 20px;">${{customer.first_name}} ${{customer.last_name}}</h2>
                            <p style="color: var(--text-muted); font-size: 13px;">${{customer.occupation}} • Age: ${{customer.age}} • Citizen: ${{customer.citizenship}} (Res: ${{customer.residence_country}})</p>
                            <p style="color: var(--text-dim); font-size: 12px; margin-top: 4px;">Address: ${{customer.address_line}}, ${{customer.address_city}}</p>
                        </div>
                        <div style="text-align: right;">
                            <span class="badge badge-${{customer.risk_tier}}" style="font-size: 13px; padding: 4px 10px;">${{customer.risk_tier}} RISK</span>
                            <div style="font-size: 26px; font-weight: 800; margin-top: 4px;">${{customer.composite_score.toFixed(1)}} <span style="font-size: 12px; color: var(--text-dim);">/ 100</span></div>
                            <div style="font-size: 11px; margin-top: 2px;">AML: <span style="color: #f97316; font-weight: bold;">${{(customer.aml_score || 0).toFixed(1)}}</span> | Fraud: <span style="color: var(--fraud-magenta); font-weight: bold;">${{(customer.fraud_score || 0).toFixed(1)}}</span></div>
                        </div>
                    </div>
                    <div style="font-size: 12px; padding: 10px 14px; background: rgba(59, 130, 246, 0.1); border-left: 3px solid var(--accent-blue); border-radius: 4px; line-height: 1.5;">
                        <strong>Governance Directive:</strong> ${{customer.recommended_action}}
                    </div>
                </div>

                <!-- Digital Identity & Telemetry -->
                <div style="background: var(--bg-card); border: 1px solid var(--border-subtle); padding: 14px 18px; border-radius: 8px;">
                    <h3 style="font-size: 12px; text-transform: uppercase; color: var(--fraud-magenta); margin-bottom: 8px;">Digital Identity & Device Footprint</h3>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 12px;">
                        <div>• Email: <span style="color: var(--text-main); font-weight: 600;">${{customer.email_address || 'N/A'}}</span> (${{customer.email_domain_type}})</div>
                        <div>• Phone: <span style="color: var(--text-main); font-weight: 600;">${{customer.phone_number || 'N/A'}}</span> (${{customer.phone_line_type}})</div>
                        <div>• Primary Device ID: <span style="font-family: monospace; color: var(--accent-blue);">${{customer.device_primary_id || 'N/A'}}</span></div>
                        <div>• Registered IP / Geo: <span style="font-family: monospace;">${{customer.primary_ip_address || 'N/A'}}</span> (${{customer.primary_ip_country}})</div>
                        <div>• Synthetic Identity Risk: <strong style="color: ${{customer.synthetic_identity_score > 60 ? '#ef4444' : '#10b981'}};">${{(customer.synthetic_identity_score || 0).toFixed(1)}} / 100</strong></div>
                    </div>
                </div>

                <!-- 5 Pillars Breakdown -->
                <div>
                    <h3 style="font-size: 13px; text-transform: uppercase; color: var(--text-muted); margin-bottom: 12px; letter-spacing: 0.5px;">FRAML Multi-Pillar Risk Engine Breakdown</h3>
                    <div class="pillar-grid">
                        <div class="pillar-item">
                            <h4><span>1. Customer KYC (20%)</span> <strong>${{customer.kyc_raw_score.toFixed(1)}}/100</strong></h4>
                            <div class="score-track"><div class="score-fill" style="width: ${{customer.kyc_raw_score}}%"></div></div>
                            <div class="pillar-fact">• PEP: ${{customer.pep_status}} | Sanctions: ${{customer.sanction_status}}</div>
                            <div class="pillar-fact">• Adverse Media: ${{customer.adverse_media}}</div>
                        </div>
                        <div class="pillar-item">
                            <h4><span>2. Purpose & Nature (10%)</span> <strong>${{customer.purpose_raw_score.toFixed(1)}}/100</strong></h4>
                            <div class="score-track"><div class="score-fill" style="width: ${{customer.purpose_raw_score}}%"></div></div>
                            <div class="pillar-fact">• Stated: ${{customer.declared_purpose_nature}}</div>
                            <div class="pillar-fact">• Income: $${{customer.annual_income_usd.toLocaleString()}}</div>
                        </div>
                        <div class="pillar-item">
                            <h4><span>3. Products & Channel (10%)</span> <strong>${{customer.product_raw_score.toFixed(1)}}/100</strong></h4>
                            <div class="score-track"><div class="score-fill" style="width: ${{customer.product_raw_score}}%"></div></div>
                            <div class="pillar-fact">• Channel: ${{customer.onboarding_channel}}</div>
                            <div class="pillar-fact">• Products: ${{customer.products_held.join(", ")}}</div>
                        </div>
                        <div class="pillar-item">
                            <h4><span>4. AML Monitoring (30%)</span> <strong>${{customer.behavioral_raw_score.toFixed(1)}}/100</strong></h4>
                            <div class="score-track"><div class="score-fill" style="width: ${{customer.behavioral_raw_score}}%; background: ${{customer.behavioral_raw_score > 60 ? '#ef4444' : '#3b82f6'}}"></div></div>
                            <div class="pillar-fact">• AML Alerts: ${{amlAlerts.length}}</div>
                            <div class="pillar-fact">• Max Severity: ${{customer.highest_alert_severity || 'None'}}</div>
                        </div>
                        <div class="pillar-item" style="grid-column: span 2;">
                            <h4><span>5. Fraud Risk & Telemetry (30%)</span> <strong style="color: var(--fraud-magenta);">${{(customer.fraud_raw_score || 0).toFixed(1)}}/100</strong></h4>
                            <div class="score-track"><div class="score-fill fraud" style="width: ${{customer.fraud_raw_score || 0}}%"></div></div>
                            <div class="pillar-fact">• Fraud Alerts: ${{fraudAlerts.length}}</div>
                            <div class="pillar-fact">• Telemetry: ${{fraudAlerts.map(f => f.rule_name).join(', ') || 'No hostile device/card anomalies'}}</div>
                        </div>
                    </div>
                </div>

                <!-- Active Fraud Alerts -->
                <div>
                    <h3 style="font-size: 13px; text-transform: uppercase; color: var(--fraud-magenta); margin-bottom: 12px;">Triggered Fraud Detection Alerts (${{fraudAlerts.length}})</h3>
                    ${{fraudAlerts.length === 0 ? '<div style="color: var(--tier-low); font-size: 13px; padding: 6px 0;">✓ Zero fraud alerts detected on account.</div>' : ''}}
                    ${{fraudAlerts.map(alt => `
                        <div class="alert-callout fraud">
                            <div class="alert-headline">
                                <span>[${{alt.rule_id}}] ${{alt.rule_name}}</span>
                                <span class="badge badge-fraud">${{alt.severity}}</span>
                            </div>
                            <div class="alert-text">${{alt.summary}}</div>
                        </div>
                    `).join('')}}
                </div>

                <!-- Active AML Alerts -->
                <div>
                    <h3 style="font-size: 13px; text-transform: uppercase; color: #f97316; margin-bottom: 12px;">Triggered AML Alerts (${{amlAlerts.length}})</h3>
                    ${{amlAlerts.length === 0 ? '<div style="color: var(--tier-low); font-size: 13px; padding: 6px 0;">✓ Zero AML alerts on record.</div>' : ''}}
                    ${{amlAlerts.map(alt => `
                        <div class="alert-callout ${{alt.severity}}">
                            <div class="alert-headline">
                                <span>[${{alt.rule_id}}] ${{alt.rule_name}}</span>
                                <span class="badge badge-${{alt.severity}}">${{alt.severity}}</span>
                            </div>
                            <div class="alert-text">${{alt.summary}}</div>
                        </div>
                    `).join('')}}
                </div>

                <!-- Action Checklist -->
                <div style="background: var(--bg-card); border: 1px solid var(--border-subtle); padding: 18px; border-radius: 8px;">
                    <h3 style="font-size: 13px; text-transform: uppercase; color: var(--tier-med); margin-bottom: 12px;">Operational Directive & Audit Checklist</h3>
                    ${{customer.action_checklist.map((item, idx) => `
                        <div style="display: flex; gap: 10px; align-items: center; font-size: 12px; margin-bottom: 8px;">
                            <input type="checkbox" id="chk-${{idx}}">
                            <label for="chk-${{idx}}">${{item}}</label>
                        </div>
                    `).join('')}}
                </div>

                <!-- Customer's Transactions -->
                <div>
                    <h3 style="font-size: 13px; text-transform: uppercase; color: var(--text-muted); margin-bottom: 12px;">Customer Transaction History (${{custTxs.length}} Total)</h3>
                    <div style="max-height: 320px; overflow-y: auto; border: 1px solid var(--border-subtle); border-radius: 6px;">
                        <table>
                            <thead>
                                <tr>
                                    <th>Tx ID</th>
                                    <th>Timestamp</th>
                                    <th>Type</th>
                                    <th>Dir</th>
                                    <th>Amount</th>
                                    <th>Counterparty</th>
                                    <th>Device / Channel</th>
                                    <th>Flag</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${{custTxs.map(t => `
                                    <tr>
                                        <td style="font-family: monospace; font-size: 11px;">${{t.transaction_id}}</td>
                                        <td style="font-size: 11px;">${{t.timestamp.replace("T", " ").substring(0, 16)}}</td>
                                        <td>${{t.transaction_type}}</td>
                                        <td><span class="badge badge-${{t.direction.toLowerCase()}}">${{t.direction}}</span></td>
                                        <td style="font-weight: 700; color: ${{t.direction === 'INBOUND' ? 'var(--tier-low)' : 'var(--text-main)'}};">$${{t.amount_usd.toLocaleString(undefined, {{minimumFractionDigits: 2}})}}</td>
                                        <td>${{t.counterparty_name}} <span style="color: var(--text-dim); font-size: 11px;">(${{t.counterparty_country}})</span></td>
                                        <td style="font-size: 11px;">${{t.channel}} <span style="color: var(--text-dim);">(${{t.device_id || 'N/A'}})</span></td>
                                        <td>${{t.is_fraud_synthetic ? `<span class="badge badge-fraud">🚨 FRAUD: ${{t.fraud_typology_tag}}</span>` : t.is_suspicious_synthetic ? `<span class="badge badge-aml">⚠️ AML: ${{t.synthetic_typology_tag}}</span>` : '<span style="color: var(--text-dim); font-size: 11px;">-</span>'}}</td>
                                    </tr>
                                `).join('')}}
                            </tbody>
                        </table>
                    </div>
                </div>
            `;

            document.getElementById("dossier-mask").classList.add("open");
        }}

        function closeDossier() {{
            document.getElementById("dossier-mask").classList.remove("open");
        }}

        function closeDossierOnMask(event) {{
            if (event.target.id === "dossier-mask") {{
                closeDossier();
            }}
        }}
    </script>
</body>
</html>
"""

    with open(output_html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"Successfully generated standalone FRAML visualization: {output_html_path} ({os.path.getsize(output_html_path) / 1024:.1f} KB)")

if __name__ == "__main__":
    build_standalone_html()
