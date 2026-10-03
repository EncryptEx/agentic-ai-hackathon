// Client-side controller for FRAML KYC, AML & Fraud Compliance Dashboard

let currentTierFilter = "ALL";
let searchQuery = "";
let portfolioData = null;

// Transactions state
let txPage = 1;
const txPageSize = 25;
let txSearchTerm = "";
let txDirection = "ALL";
let txFraudOnly = false;
let txAmlOnly = false;

// Chart references
let chartTiers = null;
let chartTypologies = null;
let chartChannels = null;

document.addEventListener("DOMContentLoaded", () => {
    initTabs();
    initControls();
    loadPortfolio();
    loadCustomers();
    loadTransactions();
    initSimulator();
    initGenerator();
    initVideoPersona();
    initCustomerCall();
});

function initTabs() {
    const tabs = document.querySelectorAll(".nav-tab");
    tabs.forEach(tab => {
        tab.addEventListener("click", () => {
            tabs.forEach(t => t.classList.remove("active"));
            tab.classList.add("active");
            
            const target = tab.dataset.target;
            document.querySelectorAll(".tab-content").forEach(el => el.style.display = "none");
            document.getElementById(target).style.display = "block";

            if (target === "tab-transactions") {
                loadTransactions();
            } else if (target === "tab-audit") {
                loadAuditTrail();
            } else if (target === "tab-call") {
                initVideoPersona();
            }
        });
    });

    const refreshAuditBtn = document.getElementById("btn-refresh-audit");
    if (refreshAuditBtn) {
        refreshAuditBtn.addEventListener("click", () => loadAuditTrail());
    }
}

function initControls() {
    // Customer search
    const searchInput = document.getElementById("search-input");
    let debounceTimer;
    searchInput.addEventListener("input", (e) => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            searchQuery = e.target.value.trim();
            loadCustomers();
        }, 250);
    });

    // Customer tier filters
    const filterButtons = document.querySelectorAll(".filter-btn");
    filterButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            filterButtons.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            currentTierFilter = btn.dataset.tier;
            loadCustomers();
        });
    });

    // Transactions filters
    const txSearchInput = document.getElementById("tx-search-input");
    let txDebounce;
    txSearchInput.addEventListener("input", (e) => {
        clearTimeout(txDebounce);
        txDebounce = setTimeout(() => {
            txSearchTerm = e.target.value.trim();
            txPage = 1;
            loadTransactions();
        }, 250);
    });

    document.getElementById("tx-dir-select").addEventListener("change", (e) => {
        txDirection = e.target.value;
        txPage = 1;
        loadTransactions();
    });

    document.getElementById("tx-fraud-check").addEventListener("change", (e) => {
        txFraudOnly = e.target.checked;
        txPage = 1;
        loadTransactions();
    });

    document.getElementById("tx-aml-check").addEventListener("change", (e) => {
        txAmlOnly = e.target.checked;
        txPage = 1;
        loadTransactions();
    });

    document.getElementById("tx-prev-btn").addEventListener("click", () => {
        if (txPage > 1) {
            txPage--;
            loadTransactions();
        }
    });

    document.getElementById("tx-next-btn").addEventListener("click", () => {
        txPage++;
        loadTransactions();
    });

    // Modal close
    document.getElementById("close-dossier").addEventListener("click", closeDossier);
    document.getElementById("modal-overlay").addEventListener("click", (e) => {
        if (e.target.id === "modal-overlay") closeDossier();
    });
}

async function loadPortfolio() {
    try {
        const res = await fetch("/api/portfolio");
        const data = await res.json();
        portfolioData = data;

        document.getElementById("kpi-total-cust").textContent = data.total_customers.toLocaleString();
        document.getElementById("kpi-total-tx").textContent = data.total_transactions.toLocaleString();
        document.getElementById("kpi-total-fraud").textContent = (data.total_fraud_alerts || 0).toLocaleString();
        document.getElementById("kpi-total-aml").textContent = (data.total_aml_alerts || 0).toLocaleString();
        
        const tiers = data.tier_distribution || {};
        const highCrit = (tiers.HIGH?.count || 0) + (tiers.CRITICAL?.count || 0);
        document.getElementById("kpi-high-crit").textContent = highCrit.toLocaleString();

        renderCharts(data);
    } catch (err) {
        console.error("Failed to load portfolio KPIs:", err);
    }
}

function renderCharts(data) {
    const tiers = data.tier_distribution || {};

    // 1. Tiers Chart
    const ctxTiers = document.getElementById("chart-tiers").getContext("2d");
    if (chartTiers) chartTiers.destroy();
    chartTiers = new Chart(ctxTiers, {
        type: "doughnut",
        data: {
            labels: ["Low Risk", "Medium Risk", "High Risk", "Critical Risk"],
            datasets: [{
                data: [
                    tiers.LOW?.count || 0,
                    tiers.MEDIUM?.count || 0,
                    tiers.HIGH?.count || 0,
                    tiers.CRITICAL?.count || 0
                ],
                backgroundColor: ["#10b981", "#f59e0b", "#f97316", "#ef4444"],
                borderWidth: 2,
                borderColor: "#101726"
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: "right", labels: { color: "#94a3b8", font: { size: 11 } } }
            }
        }
    });

    // 2. Typologies Chart
    const topRules = data.top_alerts || [];
    const ctxTypo = document.getElementById("chart-typologies").getContext("2d");
    if (chartTypologies) chartTypologies.destroy();
    chartTypologies = new Chart(ctxTypo, {
        type: "bar",
        data: {
            labels: topRules.slice(0, 6).map(r => r.rule_name.length > 20 ? r.rule_name.substring(0, 18) + "..." : r.rule_name),
            datasets: [{
                label: "Alerts Count",
                data: topRules.slice(0, 6).map(r => r.cnt),
                backgroundColor: topRules.slice(0, 6).map(r => r.alert_type === "FRAUD" ? "#d946ef" : "#3b82f6"),
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { ticks: { color: "#94a3b8", font: { size: 10 } }, grid: { display: false } },
                y: { ticks: { color: "#94a3b8" }, grid: { color: "#24324d" } }
            }
        }
    });

    // 3. Channels Mock / Default breakdown
    const ctxChan = document.getElementById("chart-channels").getContext("2d");
    if (chartChannels) chartChannels.destroy();
    chartChannels = new Chart(ctxChan, {
        type: "pie",
        data: {
            labels: ["ACH", "SWIFT Wire", "POS Retail", "Web Portal", "ATM"],
            datasets: [{
                data: [42, 28, 14, 11, 5],
                backgroundColor: ["#3b82f6", "#10b981", "#8b5cf6", "#f59e0b", "#ef4444"],
                borderWidth: 2,
                borderColor: "#101726"
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: "right", labels: { color: "#94a3b8", font: { size: 10 } } }
            }
        }
    });
}

async function loadCustomers() {
    const tbody = document.getElementById("customer-table-body");
    tbody.innerHTML = `<tr><td colspan="10" style="text-align: center; color: var(--text-muted); padding: 30px;">Loading customer cohort...</td></tr>`;

    try {
        let url = `/api/customers?tier=${currentTierFilter}`;
        if (searchQuery) url += `&q=${encodeURIComponent(searchQuery)}`;

        const res = await fetch(url);
        const data = await res.json();
        window._cachedCustomerList = data.customers;
        populateCallCustomerDropdown();

        if (data.customers.length === 0) {
            tbody.innerHTML = `<tr><td colspan="10" style="text-align: center; color: var(--text-muted); padding: 30px;">No matching customers found.</td></tr>`;
            return;
        }

        tbody.innerHTML = "";
        data.customers.forEach(c => {
            const tr = document.createElement("tr");
            tr.onclick = () => openDossier(c.customer_id);

            const score = c.composite_score ? c.composite_score.toFixed(1) : "N/A";
            const amlScore = c.aml_score !== undefined ? Number(c.aml_score).toFixed(1) : "0.0";
            const fraudScore = c.fraud_score !== undefined ? Number(c.fraud_score).toFixed(1) : "0.0";

            let alertBadge = `<span style="color: var(--text-muted);">Clean</span>`;
            if (c.fraud_alert_count > 0) {
                alertBadge = `<span class="badge badge-fraud">${c.fraud_alert_count} Fraud</span>`;
            } else if (c.alert_count > 0) {
                alertBadge = `<span class="badge badge-aml">${c.alert_count} AML</span>`;
            }

            tr.innerHTML = `
                <td style="font-weight: 700; color: var(--accent-blue);">${c.customer_id}</td>
                <td><strong>${c.first_name} ${c.last_name}</strong></td>
                <td>${c.citizenship} <span style="color: var(--text-muted); font-size: 11px;">(res: ${c.residence_country})</span></td>
                <td>${c.occupation}</td>
                <td><span style="font-family: monospace; font-size: 11px; color: var(--text-secondary);">${c.archetype}</span></td>
                <td><span class="badge badge-${c.risk_tier}">${c.risk_tier}</span></td>
                <td style="font-weight: 800;">${score}</td>
                <td style="color: #f97316; font-weight: 600;">${amlScore}</td>
                <td style="color: var(--fraud-magenta); font-weight: 600;">${fraudScore}</td>
                <td>${alertBadge}</td>
            `;
            tbody.appendChild(tr);
        });
    } catch (err) {
        console.error("Failed to load customer list:", err);
        tbody.innerHTML = `<tr><td colspan="10" style="text-align: center; color: #ef4444;">Error loading customer data.</td></tr>`;
    }
}

async function loadTransactions() {
    const tbody = document.getElementById("tx-table-body");
    tbody.innerHTML = `<tr><td colspan="10" style="text-align: center; color: var(--text-muted); padding: 30px;">Loading transactions...</td></tr>`;

    try {
        let url = `/api/transactions?page=${txPage}&page_size=${txPageSize}&dir=${txDirection}`;
        if (txSearchTerm) url += `&q=${encodeURIComponent(txSearchTerm)}`;
        if (txFraudOnly) url += `&fraud_only=true`;
        if (txAmlOnly) url += `&aml_only=true`;

        const res = await fetch(url);
        const data = await res.json();

        if (data.transactions.length === 0) {
            tbody.innerHTML = `<tr><td colspan="10" style="text-align: center; color: var(--text-muted); padding: 30px;">No transactions found matching criteria.</td></tr>`;
            document.getElementById("tx-pagination-info").textContent = "0 transactions";
            document.getElementById("tx-prev-btn").disabled = true;
            document.getElementById("tx-next-btn").disabled = true;
            return;
        }

        tbody.innerHTML = "";
        data.transactions.forEach(t => {
            const tr = document.createElement("tr");
            tr.onclick = () => openDossier(t.customer_id);

            let flagBadge = `<span style="color: var(--text-muted); font-size: 11px;">Standard</span>`;
            if (t.is_fraud_synthetic) {
                flagBadge = `<span class="badge badge-fraud">🚨 FRAUD: ${t.fraud_typology_tag || 'SUSPECTED'}</span>`;
            } else if (t.is_suspicious_synthetic) {
                flagBadge = `<span class="badge badge-aml">⚠️ AML: ${t.synthetic_typology_tag || 'SUSPICIOUS'}</span>`;
            }

            const authStyle = t.auth_status === "DECLINED_SUSPECTED_FRAUD" ? "color: #ef4444; font-weight: bold;" : "color: var(--text-muted); font-size: 11px;";

            tr.innerHTML = `
                <td style="font-family: monospace; font-size: 12px; color: var(--accent-blue);">${t.transaction_id}</td>
                <td><strong>${t.customer_id}</strong></td>
                <td style="font-size: 11px; color: var(--text-secondary);">${t.timestamp.replace("T", " ").substring(0, 16)}</td>
                <td>${t.transaction_type}</td>
                <td><span class="badge badge-${t.direction.toLowerCase()}">${t.direction}</span></td>
                <td style="font-weight: 700; color: ${t.direction === 'INBOUND' ? 'var(--tier-low)' : 'var(--text-primary)'};">$${t.amount_usd.toLocaleString(undefined, {minimumFractionDigits: 2})}</td>
                <td>${t.counterparty_name} <span style="color: var(--text-muted); font-size: 11px;">(${t.counterparty_country})</span></td>
                <td style="font-size: 11px;">${t.channel} <span style="color: var(--text-muted);">(${t.device_id || 'N/A'})</span></td>
                <td style="${authStyle}">${t.auth_status || 'AUTHORIZED'}</td>
                <td>${flagBadge}</td>
            `;
            tbody.appendChild(tr);
        });

        const start = (data.page - 1) * data.page_size + 1;
        const end = Math.min(data.page * data.page_size, data.total);
        document.getElementById("tx-pagination-info").textContent = `Showing ${start}-${end} of ${data.total.toLocaleString()} transactions (Page ${data.page} of ${data.total_pages})`;
        document.getElementById("tx-prev-btn").disabled = (data.page <= 1);
        document.getElementById("tx-next-btn").disabled = (data.page >= data.total_pages);
    } catch (err) {
        console.error("Failed to load transactions:", err);
        tbody.innerHTML = `<tr><td colspan="10" style="text-align: center; color: #ef4444;">Error loading transactions.</td></tr>`;
    }
}

async function openDossier(customerId) {
    const modal = document.getElementById("modal-overlay");
    modal.classList.add("open");

    const content = document.getElementById("dossier-content");
    content.innerHTML = `<div style="text-align: center; padding: 50px; color: var(--text-muted);">Fetching Customer 360 Dossier...</div>`;

    try {
        const res = await fetch(`/api/customer?id=${encodeURIComponent(customerId)}`);
        const data = await res.json();
        renderDossier(data);
    } catch (err) {
        content.innerHTML = `<div style="color: #ef4444; padding: 30px;">Failed to load dossier for ${customerId}.</div>`;
    }
}

function closeDossier() {
    document.getElementById("modal-overlay").classList.remove("open");
}

function renderDossier(data) {
    const { customer, assessment, alerts, fraud_alerts, transactions } = data;
    const content = document.getElementById("dossier-content");
    const checklist = assessment.action_checklist ? JSON.parse(assessment.action_checklist) : [];
    const fraudList = fraud_alerts || [];
    const amlList = alerts || [];

    content.innerHTML = `
        <!-- Header Profile -->
        <div style="background: var(--bg-card); border: 1px solid var(--border-color); padding: 18px 22px; border-radius: 8px;">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;">
                <div>
                    <h2 style="font-size: 20px;">${customer.first_name} ${customer.last_name}</h2>
                    <p style="color: var(--text-secondary); font-size: 13px;">ID: ${customer.customer_id} | ${customer.occupation} | Age: ${customer.age}</p>
                    <p style="color: var(--text-muted); font-size: 12px; margin-top: 4px;">Citizen: ${customer.citizenship} (Res: ${customer.residence_country}) | Tax: ${customer.tax_residence_country}</p>
                </div>
                <div style="text-align: right;">
                    <span class="badge badge-${assessment.risk_tier}" style="font-size: 13px; padding: 4px 10px;">${assessment.risk_tier} RISK</span>
                    <div style="font-size: 24px; font-weight: 800; margin-top: 4px;">${assessment.composite_score.toFixed(1)} <span style="font-size: 12px; color: var(--text-muted);">/ 100</span></div>
                    <div style="font-size: 11px; margin-top: 2px;">AML: <span style="color: #f97316; font-weight: bold;">${(assessment.aml_score || 0).toFixed(1)}</span> | Fraud: <span style="color: var(--fraud-magenta); font-weight: bold;">${(assessment.fraud_score || 0).toFixed(1)}</span></div>
                </div>
            </div>
            <div style="font-size: 12px; padding: 10px 14px; background: rgba(59, 130, 246, 0.1); border-left: 3px solid var(--accent-blue); border-radius: 4px; line-height: 1.5;">
                <strong>Governance Directive:</strong> ${assessment.recommended_action}
            </div>
        </div>

        <!-- Autonomous Multi-Agent AI Investigation Suite -->
        <div style="background: linear-gradient(135deg, rgba(37, 99, 235, 0.14) 0%, rgba(217, 70, 239, 0.14) 100%); border: 1px solid var(--accent-blue); padding: 16px 20px; border-radius: 8px;">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
                <div>
                    <h3 style="font-size: 14px; font-weight: 700; color: var(--text-primary); display: flex; align-items: center; gap: 8px;">
                        <span>🤖</span> Autonomous Multi-Agent Investigation Suite
                    </h3>
                    <p style="color: var(--text-secondary); font-size: 12px; margin-top: 3px;">
                        Deploys Customer, Transaction, Fraud, Ownership, and Risk specialist agents to investigate this customer's live profile, ledger, telemetry, and 5-pillar scores.
                    </p>
                </div>
                <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                    <button id="btn-run-agent-investigate" class="btn-magenta" style="padding: 9px 18px; font-size: 13px; font-weight: 700; cursor: pointer; display: flex; align-items: center; gap: 6px;">
                        <span>⚡</span> Run Multi-Agent Investigation
                    </button>
                    <button id="btn-launch-call-dossier" class="btn-primary" style="padding: 9px 18px; font-size: 13px; font-weight: 700; cursor: pointer; display: flex; align-items: center; gap: 6px; background: linear-gradient(135deg, #1d4ed8, #3b82f6);">
                        <span>📞</span> Launch Customer Video Call
                    </button>
                </div>
            </div>
            <div id="agent-investigation-output" style="display: none; margin-top: 16px; background: #0c121e; border: 1px solid var(--border-color); border-radius: 6px; padding: 20px; max-height: 520px; overflow-y: auto;">
            </div>
        </div>

        <!-- Digital Identity & Fraud Telemetry -->
        <div style="background: var(--bg-card); border: 1px solid var(--border-color); padding: 14px 18px; border-radius: 8px;">
            <h3 style="font-size: 12px; text-transform: uppercase; color: var(--fraud-magenta); margin-bottom: 8px;">Digital Footprint & Authentication Telemetry</h3>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 12px;">
                <div>• Email: <span style="color: var(--text-primary); font-weight: 600;">${customer.email_address || 'N/A'}</span> (${customer.email_domain_type || 'STANDARD'})</div>
                <div>• Phone: <span style="color: var(--text-primary); font-weight: 600;">${customer.phone_number || 'N/A'}</span> (${customer.phone_line_type || 'MOBILE'})</div>
                <div>• Primary Device ID: <span style="font-family: monospace; color: var(--accent-blue);">${customer.device_primary_id || 'N/A'}</span></div>
                <div>• Registered IP / Geo: <span style="font-family: monospace;">${customer.primary_ip_address || 'N/A'}</span> (${customer.primary_ip_country || 'N/A'})</div>
                <div>• Synthetic Identity Risk: <strong style="color: ${(customer.synthetic_identity_score || 0) > 60 ? '#ef4444' : '#10b981'};">${(customer.synthetic_identity_score || 0).toFixed(1)} / 100</strong></div>
            </div>
        </div>

        <!-- 5 Pillars Breakdown -->
        <div>
            <h3 style="font-size: 13px; text-transform: uppercase; color: var(--text-secondary); margin-bottom: 12px; letter-spacing: 0.5px;">FRAML Multi-Pillar Risk Engine Breakdown</h3>
            <div class="pillar-grid">
                <div class="pillar-card">
                    <h4><span>1. Customer KYC (20%)</span> <strong>${assessment.kyc_raw_score.toFixed(1)}/100</strong></h4>
                    <div class="pillar-score-bar"><div class="pillar-score-fill" style="width: ${assessment.kyc_raw_score}%"></div></div>
                    <div class="pillar-factor">• PEP: ${customer.pep_status} | Sanctions: ${customer.sanction_status}</div>
                    <div class="pillar-factor">• Adverse Media: ${customer.adverse_media}</div>
                </div>

                <div class="pillar-card">
                    <h4><span>2. Purpose & Nature (10%)</span> <strong>${assessment.purpose_raw_score.toFixed(1)}/100</strong></h4>
                    <div class="pillar-score-bar"><div class="pillar-score-fill" style="width: ${assessment.purpose_raw_score}%"></div></div>
                    <div class="pillar-factor">• Stated: ${customer.declared_purpose_nature}</div>
                    <div class="pillar-factor">• Income: $${customer.annual_income_usd.toLocaleString()}/yr</div>
                </div>

                <div class="pillar-card">
                    <h4><span>3. Products & Channel (10%)</span> <strong>${assessment.product_raw_score.toFixed(1)}/100</strong></h4>
                    <div class="pillar-score-bar"><div class="pillar-score-fill" style="width: ${assessment.product_raw_score}%"></div></div>
                    <div class="pillar-factor">• Channel: ${customer.onboarding_channel}</div>
                    <div class="pillar-factor">• Products: ${customer.products_held.join(", ")}</div>
                </div>

                <div class="pillar-card">
                    <h4><span>4. AML Monitoring (30%)</span> <strong>${assessment.behavioral_raw_score.toFixed(1)}/100</strong></h4>
                    <div class="pillar-score-bar"><div class="pillar-score-fill" style="width: ${assessment.behavioral_raw_score}%; background: ${assessment.behavioral_raw_score > 60 ? '#ef4444' : '#3b82f6'};"></div></div>
                    <div class="pillar-factor">• AML Alerts: ${amlList.length}</div>
                    <div class="pillar-factor">• Severity: ${assessment.highest_alert_severity || 'None'}</div>
                </div>

                <div class="pillar-card" style="grid-column: span 2;">
                    <h4><span>5. Fraud Risk & Telemetry (30%)</span> <strong style="color: var(--fraud-magenta);">${(assessment.fraud_raw_score || 0).toFixed(1)}/100</strong></h4>
                    <div class="pillar-score-bar"><div class="pillar-score-fill fraud" style="width: ${assessment.fraud_raw_score || 0}%;"></div></div>
                    <div class="pillar-factor">• Active Fraud Alerts: ${fraudList.length}</div>
                    <div class="pillar-factor">• Summary: ${fraudList.map(f => f.rule_name).join(', ') || 'No anomalous device/card attacks'}</div>
                </div>
            </div>
        </div>

        <!-- Fraud Alerts -->
        <div>
            <h3 style="font-size: 13px; text-transform: uppercase; color: var(--fraud-magenta); margin-bottom: 12px;">Triggered Fraud Alerts (${fraudList.length})</h3>
            ${fraudList.length === 0 ? '<div style="color: var(--tier-low); font-size: 13px;">✓ Zero fraud detection anomalies.</div>' : ''}
            ${fraudList.map(alt => `
                <div class="alert-item fraud">
                    <div class="alert-title">
                        <span>[${alt.rule_id}] ${alt.rule_name}</span>
                        <div style="display: flex; gap: 8px; align-items: center;">
                            <button class="btn-pick-test" onclick="triggerAlertInvestigation('${customer.customer_id}', '${alt.alert_id}')" style="font-size: 11px; padding: 2px 8px;">Investigate Alert</button>
                            <span class="badge badge-fraud">${alt.severity}</span>
                        </div>
                    </div>
                    <div class="alert-desc">${alt.summary}</div>
                </div>
            `).join('')}
        </div>

        <!-- AML Alerts -->
        <div>
            <h3 style="font-size: 13px; text-transform: uppercase; color: #f97316; margin-bottom: 12px;">Triggered AML Alerts (${amlList.length})</h3>
            ${amlList.length === 0 ? '<div style="color: var(--tier-low); font-size: 13px;">✓ Zero AML transaction monitoring breaches.</div>' : ''}
            ${amlList.map(alt => `
                <div class="alert-item ${alt.severity}">
                    <div class="alert-title">
                        <span>[${alt.rule_id}] ${alt.rule_name}</span>
                        <div style="display: flex; gap: 8px; align-items: center;">
                            <button class="btn-pick-test" onclick="triggerAlertInvestigation('${customer.customer_id}', '${alt.alert_id}')" style="font-size: 11px; padding: 2px 8px;">Investigate Alert</button>
                            <span class="badge badge-${alt.severity}">${alt.severity}</span>
                        </div>
                    </div>
                    <div class="alert-desc">${alt.summary}</div>
                </div>
            `).join('')}
        </div>

        <!-- Action Checklist -->
        <div style="background: var(--bg-card); border: 1px solid var(--border-color); padding: 18px; border-radius: 8px;">
            <h3 style="font-size: 13px; text-transform: uppercase; color: var(--tier-med); margin-bottom: 12px;">Compliance & Fraud Intervention Checklist</h3>
            ${checklist.map((item, idx) => `
                <div class="checklist-item">
                    <input type="checkbox" id="chk-${idx}">
                    <label for="chk-${idx}">${item}</label>
                </div>
            `).join('')}
        </div>

        <!-- Transactions -->
        <div>
            <h3 style="font-size: 13px; text-transform: uppercase; color: var(--text-secondary); margin-bottom: 12px;">Customer Transaction History (${transactions.length} Records)</h3>
            <div style="max-height: 280px; overflow-y: auto; border: 1px solid var(--border-color); border-radius: 6px;">
                <table>
                    <thead>
                        <tr>
                            <th>Tx ID</th>
                            <th>Timestamp</th>
                            <th>Type</th>
                            <th>Dir</th>
                            <th>Amount</th>
                            <th>Counterparty</th>
                            <th>Channel & Device</th>
                            <th>Flag</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${transactions.map(t => `
                            <tr>
                                <td style="font-family: monospace; font-size: 11px;">${t.transaction_id}</td>
                                <td style="font-size: 11px;">${t.timestamp.replace("T", " ").substring(0, 16)}</td>
                                <td>${t.transaction_type}</td>
                                <td><span class="badge badge-${t.direction.toLowerCase()}">${t.direction}</span></td>
                                <td style="font-weight: 700; color: ${t.direction === 'INBOUND' ? 'var(--tier-low)' : 'var(--text-primary)'};">$${t.amount_usd.toLocaleString(undefined, {minimumFractionDigits: 2})}</td>
                                <td>${t.counterparty_name} <span style="color: var(--text-muted); font-size: 11px;">(${t.counterparty_country})</span></td>
                                <td style="font-size: 11px;">${t.channel} (${t.device_id || 'N/A'})</td>
                                <td>${t.is_fraud_synthetic ? `<span class="badge badge-fraud">🚨 ${t.fraud_typology_tag}</span>` : t.is_suspicious_synthetic ? `<span class="badge badge-aml">⚠️ ${t.synthetic_typology_tag}</span>` : '<span style="color: var(--text-muted);">-</span>'}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        </div>
    `;

    // Attach agent trigger listener
    const agentBtn = document.getElementById("btn-run-agent-investigate");
    const agentOut = document.getElementById("agent-investigation-output");
    if (agentBtn && agentOut) {
        agentBtn.addEventListener("click", () => triggerAgentInvestigation(customer.customer_id, null, agentBtn, agentOut));
    }

    const callDossierBtn = document.getElementById("btn-launch-call-dossier");
    if (callDossierBtn) {
        callDossierBtn.addEventListener("click", () => {
            closeDossier();
            launchCustomerCallFromDossier(customer.customer_id);
        });
    }
}

async function triggerAgentInvestigation(customerId, alertId, btn, outContainer) {
    if (!btn) btn = document.getElementById("btn-run-agent-investigate");
    if (!outContainer) outContainer = document.getElementById("agent-investigation-output");

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span>⏳</span> Agents Investigating (Customer, Tx, Fraud, Ownership, Risk)...`;
    }
    if (outContainer) {
        outContainer.style.display = "block";
        outContainer.scrollIntoView({ behavior: "smooth", block: "nearest" });
        outContainer.innerHTML = `
            <div style="text-align: center; padding: 30px; color: var(--text-secondary);">
                <div style="font-size: 26px; margin-bottom: 10px;">🛡️</div>
                <div style="font-weight: 700; color: var(--accent-blue); margin-bottom: 8px;">Multi-Agent Sequential Pipeline Active</div>
                <div style="font-size: 12px; color: var(--text-muted); max-width: 520px; margin: 0 auto; line-height: 1.6; text-align: left; background: rgba(59,130,246,0.06); border: 1px solid var(--border-color); padding: 12px 16px; border-radius: 6px;">
                    <div>• <strong>Customer Agent:</strong> Profiling KYC CDD, wealth plausibility & watchlists...</div>
                    <div>• <strong>Transaction Agent:</strong> Auditing ledger velocity, structuring & corridors...</div>
                    <div>• <strong>Fraud Agent:</strong> Inspecting device telemetry, impossible travel & auth logs...</div>
                    <div>• <strong>Ownership Agent:</strong> Mapping beneficial owners (UBOs) & country risks...</div>
                    <div>• <strong>Risk Agent:</strong> Evaluating 5-pillar FRAML score & statutory overrides...</div>
                    <div>• <strong>Consolidator Agent:</strong> Synthesizing into 11-section executive dossier...</div>
                </div>
            </div>
        `;
    }

    try {
        const resp = await fetch("/api/investigate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ customer_id: customerId, alert_id: alertId })
        });
        const data = await resp.json();
        renderAgentReport(data, outContainer);
        if (btn) btn.innerHTML = `<span>✓</span> Re-run AI Investigation`;
    } catch (err) {
        if (outContainer) {
            outContainer.innerHTML = `<div style="color: #ef4444; padding: 16px;">Failed to execute multi-agent investigation: ${err.message}</div>`;
        }
        if (btn) btn.innerHTML = `<span>⚡</span> Run Multi-Agent Investigation`;
    } finally {
        if (btn) btn.disabled = false;
    }
}

window.triggerAlertInvestigation = function(customerId, alertId) {
    triggerAgentInvestigation(customerId, alertId);
};

function formatMarkdown(text) {
    if (!text) return "";
    let html = text
        .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
        .replace(/^### (.*$)/gim, '<h3 style="font-size: 15px; color: var(--accent-blue); margin: 18px 0 8px 0; border-bottom: 1px solid var(--border-color); padding-bottom: 4px;">$1</h3>')
        .replace(/^## (.*$)/gim, '<h2 style="font-size: 17px; color: var(--text-primary); margin: 20px 0 10px 0;">$1</h2>')
        .replace(/^# (.*$)/gim, '<h1 style="font-size: 19px; color: var(--text-primary); margin: 22px 0 12px 0;">$1</h1>')
        .replace(/\*\*(.*?)\*\*/gim, '<strong style="color: var(--text-primary);">$1</strong>')
        .replace(/\*(.*?)\*/gim, '<em>$1</em>')
        .replace(/`([^`]+)`/gim, '<code style="background: rgba(59,130,246,0.15); color: #93c5fd; padding: 2px 5px; border-radius: 4px; font-family: monospace; font-size: 12px;">$1</code>')
        .replace(/^\s*-\s+\[ \]\s+\*\*Action:\*\*\s+(.*$)/gim, '<div style="display: flex; gap: 8px; margin: 6px 0;"><span style="color: var(--tier-med);">☑</span> <span>$1</span></div>')
        .replace(/^\s*-\s+(.*$)/gim, '<li style="margin: 4px 0 4px 18px; color: var(--text-secondary);">$1</li>')
        .replace(/^\s*\*\s+(.*$)/gim, '<li style="margin: 4px 0 4px 18px; color: var(--text-secondary);">$1</li>')
        .replace(/---/gim, '<hr style="border: 0; border-top: 1px solid var(--border-color); margin: 16px 0;">');
    return html.replace(/\n\n+/g, '<br><br>');
}

function renderAgentReport(data, container) {
    const reportText = data.report || "No report generated.";
    const execText = data.executive_summary || reportText;
    const invId = data.investigation_id || ("INV-" + Math.random().toString(36).substring(2, 10).toUpperCase());
    const sha = data.report_sha256 || "";
    const officerStatus = data.officer_sign_off_status || "PENDING";
    const officerName = data.officer_name || "";
    const officerNotes = data.officer_notes || "";
    const reviewedAt = data.reviewed_at || "";
    const isSignedOff = officerStatus !== "PENDING";

    let activeView = data.executive_summary ? "exec" : "full";

    container.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; padding-bottom: 10px; border-bottom: 1px solid var(--border-color); flex-wrap: wrap; gap: 8px;">
            <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
                <span class="badge badge-${data.risk_tier || 'HIGH'}" style="font-size: 12px;">${data.risk_tier || 'CRITICAL'} CASE DOSSIER</span>
                <span style="font-size: 12px; color: var(--text-secondary);">FRAML Score: <strong>${(data.composite_score || 0).toFixed(1)}/100</strong></span>
                <span style="font-size: 11px; background: rgba(59,130,246,0.15); color: #93c5fd; padding: 3px 8px; border-radius: 4px; font-family: monospace;">
                    ID: ${invId}
                </span>
            </div>
            <div style="display: flex; gap: 8px;">
                <button id="btn-copy-report" class="btn-pick-test" style="display: flex; align-items: center; gap: 6px;">
                    <span>📋</span> <span id="copy-btn-text">Copy Active Report</span>
                </button>
            </div>
        </div>

        ${data.executive_summary ? `
        <div style="display: flex; gap: 6px; margin-bottom: 14px; background: rgba(15, 23, 42, 0.6); padding: 4px; border-radius: 6px; border: 1px solid var(--border-color); width: fit-content;">
            <button id="tab-exec-${invId}" style="background: var(--accent-blue); color: #fff; font-weight: 600; padding: 5px 14px; font-size: 11px; border-radius: 4px; border: none; cursor: pointer;">
                ⚡ Executive Summary
            </button>
            <button id="tab-full-${invId}" style="background: transparent; color: var(--text-secondary); padding: 5px 14px; font-size: 11px; border-radius: 4px; border: none; cursor: pointer;">
                📋 Full 11-Section Dossier
            </button>
        </div>` : ''}

        ${sha ? `
        <div style="display: flex; align-items: center; justify-content: space-between; background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.25); border-radius: 6px; padding: 8px 12px; margin-bottom: 16px; font-size: 11px; flex-wrap: wrap; gap: 6px;">
            <div style="display: flex; align-items: center; gap: 6px; color: #34d399;">
                <span>🔒</span>
                <strong>Tamper-Evident SHA-256 Digest:</strong>
                <code style="color: #6ee7b7; font-family: monospace; font-size: 11px;">${sha}</code>
            </div>
            <span style="color: var(--text-muted); font-size: 11px;">Immutable Ledger Verified</span>
        </div>` : ''}

        <div id="report-view-${invId}" style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; font-size: 13px;">
            ${formatMarkdown(activeView === "exec" ? execText : reportText)}
        </div>

        <!-- Human-in-the-Loop Compliance Officer Sign-Off Card -->
        <div id="signoff-box-${invId}" style="margin-top: 24px; background: #0f172a; border: 1px solid var(--border-color); border-radius: 8px; padding: 18px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px;">
                <h4 style="margin: 0; color: var(--accent-blue); font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px;">
                    ⚖️ Human Compliance Officer Sign-Off & Disposition
                </h4>
                <span id="signoff-badge-${invId}" class="badge ${isSignedOff ? 'badge-LOW' : 'badge-HIGH'}" style="font-size: 11px;">
                    ${officerStatus}
                </span>
            </div>

            <div id="signoff-view-${invId}" style="${isSignedOff ? 'display: block;' : 'display: none;'} background: rgba(59,130,246,0.08); border: 1px solid var(--border-color); border-radius: 6px; padding: 12px; margin-bottom: 10px; font-size: 12px;">
                <div><strong>Reviewing Officer:</strong> <span id="signoff-officer-disp-${invId}">${officerName || 'N/A'}</span></div>
                <div style="margin-top: 4px;"><strong>Decision:</strong> <span id="signoff-decision-disp-${invId}">${officerStatus}</span></div>
                <div style="margin-top: 4px;"><strong>Officer Notes:</strong> <span id="signoff-notes-disp-${invId}">${officerNotes || 'None recorded'}</span></div>
                <div style="margin-top: 4px; font-size: 11px; color: var(--text-muted);"><strong>Timestamp:</strong> <span id="signoff-time-disp-${invId}">${reviewedAt || ''}</span></div>
            </div>

            <div id="signoff-form-${invId}" style="${isSignedOff ? 'display: none;' : 'display: block;'}">
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 12px;">
                    <div>
                        <label style="display: block; font-size: 11px; color: var(--text-muted); margin-bottom: 4px;">Officer Name / Badge</label>
                        <input type="text" id="signoff-officer-${invId}" value="Compliance Officer" style="width: 100%; background: var(--bg-primary); border: 1px solid var(--border-color); color: var(--text-primary); padding: 8px; border-radius: 4px; font-size: 12px;">
                    </div>
                    <div>
                        <label style="display: block; font-size: 11px; color: var(--text-muted); margin-bottom: 4px;">Disposition Action</label>
                        <select id="signoff-decision-${invId}" style="width: 100%; background: var(--bg-primary); border: 1px solid var(--border-color); color: var(--text-primary); padding: 8px; border-radius: 4px; font-size: 12px;">
                            <option value="APPROVED_SAR_FILED">Approved: File Suspicious Activity Report (SAR) & Restrict</option>
                            <option value="APPROVED_EDD_REQUESTED">Approved: Escalate to Enhanced Due Diligence (EDD)</option>
                            <option value="APPROVED_ACCOUNT_RESTRICTED">Approved: Restrict Outbound Wires & Hold Balance</option>
                            <option value="DISMISSED_FALSE_POSITIVE">Dismissed: Documented Legitimate Business Purpose (False Positive)</option>
                        </select>
                    </div>
                </div>
                <div style="margin-bottom: 12px;">
                    <label style="display: block; font-size: 11px; color: var(--text-muted); margin-bottom: 4px;">Regulatory Rationale & Case Notes</label>
                    <textarea id="signoff-notes-${invId}" rows="2" placeholder="State compliance justification and statutory evidence reviewed..." style="width: 100%; background: var(--bg-primary); border: 1px solid var(--border-color); color: var(--text-primary); padding: 8px; border-radius: 4px; font-size: 12px; font-family: inherit; resize: vertical;"></textarea>
                </div>
                <div style="display: flex; justify-content: flex-end; gap: 8px;">
                    <button id="btn-submit-signoff-${invId}" class="btn-magenta" style="padding: 7px 16px; font-size: 12px; font-weight: 700; cursor: pointer;">
                        <span>✍️</span> Submit Officer Sign-Off
                    </button>
                </div>
            </div>
        </div>
    `;

    const copyBtn = document.getElementById("btn-copy-report");
    const copyTextSpan = document.getElementById("copy-btn-text");
    const tabExec = document.getElementById(`tab-exec-${invId}`);
    const tabFull = document.getElementById(`tab-full-${invId}`);
    const reportView = document.getElementById(`report-view-${invId}`);

    if (tabExec && tabFull && reportView) {
        tabExec.addEventListener("click", () => {
            activeView = "exec";
            tabExec.style.background = "var(--accent-blue)";
            tabExec.style.color = "#fff";
            tabFull.style.background = "transparent";
            tabFull.style.color = "var(--text-secondary)";
            reportView.innerHTML = formatMarkdown(execText);
            if (copyTextSpan) copyTextSpan.textContent = "Copy Executive Summary";
        });
        tabFull.addEventListener("click", () => {
            activeView = "full";
            tabFull.style.background = "var(--accent-blue)";
            tabFull.style.color = "#fff";
            tabExec.style.background = "transparent";
            tabExec.style.color = "var(--text-secondary)";
            reportView.innerHTML = formatMarkdown(reportText);
            if (copyTextSpan) copyTextSpan.textContent = "Copy 11-Section Dossier";
        });
    }

    if (copyBtn) {
        copyBtn.addEventListener("click", () => {
            const textToCopy = activeView === "exec" ? execText : reportText;
            navigator.clipboard.writeText(textToCopy).then(() => {
                copyBtn.innerHTML = `<span>✓</span> Copied to Clipboard!`;
                setTimeout(() => {
                    copyBtn.innerHTML = `<span>📋</span> <span id="copy-btn-text">${activeView === "exec" ? "Copy Executive Summary" : "Copy 11-Section Dossier"}</span>`;
                }, 2000);
            }).catch(() => {
                alert("Failed to copy report to clipboard");
            });
        });
    }

    const submitSignoffBtn = document.getElementById(`btn-submit-signoff-${invId}`);
    if (submitSignoffBtn) {
        submitSignoffBtn.addEventListener("click", async () => {
            const officer = (document.getElementById(`signoff-officer-${invId}`).value || "Compliance Officer").trim();
            const decision = document.getElementById(`signoff-decision-${invId}`).value;
            const notes = document.getElementById(`signoff-notes-${invId}`).value.trim();

            submitSignoffBtn.disabled = true;
            submitSignoffBtn.innerHTML = `<span>⏳</span> Saving...`;

            try {
                const res = await fetch("/api/investigations/sign-off", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        investigation_id: invId,
                        officer_name: officer,
                        decision: decision,
                        notes: notes
                    })
                });
                const resData = await res.json();
                if (resData.status === "success") {
                    const badge = document.getElementById(`signoff-badge-${invId}`);
                    badge.textContent = decision;
                    badge.className = "badge badge-LOW";
                    document.getElementById(`signoff-officer-disp-${invId}`).textContent = officer;
                    document.getElementById(`signoff-decision-disp-${invId}`).textContent = decision;
                    document.getElementById(`signoff-notes-disp-${invId}`).textContent = notes || "None recorded";
                    document.getElementById(`signoff-time-disp-${invId}`).textContent = (resData.audit_log && resData.audit_log.reviewed_at) || new Date().toISOString();
                    document.getElementById(`signoff-form-${invId}`).style.display = "none";
                    document.getElementById(`signoff-view-${invId}`).style.display = "block";
                }
            } catch (e) {
                alert("Failed to save officer sign-off: " + e.message);
                submitSignoffBtn.disabled = false;
                submitSignoffBtn.innerHTML = `<span>✍️</span> Submit Officer Sign-Off`;
            }
        });
    }
}

async function loadAuditTrail() {
    const tbody = document.getElementById("audit-table-body");
    if (!tbody) return;

    try {
        const resp = await fetch("/api/investigations/audit-trail?limit=50");
        const logs = await resp.json();

        if (!logs || logs.length === 0) {
            tbody.innerHTML = `<tr><td colspan="10" style="text-align: center; color: var(--text-muted); padding: 24px;">No multi-agent investigations logged yet. Run an investigation from any customer dossier to record audit entries.</td></tr>`;
            return;
        }

        tbody.innerHTML = logs.map(l => {
            const isSigned = l.officer_sign_off_status && l.officer_sign_off_status !== "PENDING";
            const statusBadge = isSigned 
                ? `<span class="badge badge-LOW" style="font-size: 10px;">${l.officer_sign_off_status}</span>`
                : `<span class="badge badge-HIGH" style="font-size: 10px;">PENDING</span>`;
            const shaShort = l.final_report_sha256 ? `${l.final_report_sha256.substring(0, 10)}...` : 'N/A';
            const dateStr = (l.timestamp || "").replace("T", " ").substring(0, 19);

            return `
                <tr>
                    <td style="font-family: monospace; font-size: 11px; color: var(--accent-blue); font-weight: 600;">${l.investigation_id}</td>
                    <td style="font-size: 11px; color: var(--text-muted);">${dateStr}</td>
                    <td><strong>${l.customer_name || ''}</strong> <span style="font-size: 11px; color: var(--text-muted);">(${l.customer_id})</span></td>
                    <td style="font-size: 12px;">${l.trigger_rule || 'Manual Risk Review'}</td>
                    <td><span class="badge badge-${l.risk_tier || 'LOW'}" style="font-size: 10px;">${l.risk_tier || 'LOW'} (${(l.composite_score || 0).toFixed(1)})</span></td>
                    <td style="font-size: 11px; color: var(--text-muted); font-family: monospace;">${l.model_version || 'gemini-3.8-flash'}</td>
                    <td style="font-family: monospace; font-size: 11px; color: #34d399;" title="${l.final_report_sha256}">🔒 ${shaShort}</td>
                    <td>${statusBadge}</td>
                    <td style="font-size: 12px;">${l.officer_name || '<em style="color: var(--text-muted);">Unassigned</em>'}</td>
                    <td>
                        <button class="btn-pick-test" onclick="viewAuditLogDossier('${l.investigation_id}')" style="padding: 4px 8px; font-size: 11px;">
                            View Dossier
                        </button>
                    </td>
                </tr>
            `;
        }).join("");
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="10" style="text-align: center; color: #ef4444; padding: 24px;">Failed to load audit trail: ${err.message}</td></tr>`;
    }
}

window.viewAuditLogDossier = async function(invId) {
    try {
        const res = await fetch(`/api/investigations/${invId}`);
        const log = await res.json();
        const overlay = document.getElementById("modal-overlay");
        const content = document.getElementById("dossier-content");
        if (overlay && content) {
            overlay.classList.add("active");
            content.innerHTML = `<div id="audit-dossier-container"></div>`;
            const container = document.getElementById("audit-dossier-container");
            renderAgentReport({
                investigation_id: log.investigation_id,
                report_sha256: log.final_report_sha256,
                officer_sign_off_status: log.officer_sign_off_status,
                officer_name: log.officer_name,
                officer_notes: log.officer_notes,
                reviewed_at: log.reviewed_at,
                customer_id: log.customer_id,
                customer_name: log.customer_name,
                risk_tier: log.risk_tier,
                composite_score: log.composite_score,
                report: log.final_report_text
            }, container);
        }
    } catch (e) {
        alert("Error loading dossier: " + e.message);
    }
};

// ==========================================
// FRAML SIMULATOR TYPOLOGY PRESETS & AUTO-FILL
// ==========================================

const TYPOLOGY_PRESETS = {
    "ATO": {
        title: "FR-01: Account Takeover (ATO) & Impossible Travel Velocity",
        desc: "UK corporate accountant credentials compromised; legitimate login in London followed 35 mins later by foreign proxy drain to offshore crypto ramp.",
        badgeClass: "badge-CRITICAL",
        badgeText: "CRITICAL FRAUD",
        category: "FRAUD",
        customer: {
            fname: "Eleanor", lname: "Pemberton", citizenship: "GB", residence: "GB",
            occupation: "ACCOUNTANT_CERTIFIED", income: 88000, turnover: 5500, maxtx: 2000,
            purpose: "SALARY_AND_LIVING_EXPENSES", channel: "DIGITAL_EKYC_BIOMETRIC",
            pep: "NONE", media: "NONE", sanction: "CLEAN",
            products: ["CURRENT_ACCOUNT", "SAVINGS_ACCOUNT", "INTERNATIONAL_WIRE_SERVICE"]
        },
        getTransactions: (now, c) => [
            {
                transaction_id: "SIM-ATO-LEGIT",
                timestamp: new Date(now.getTime() - 40 * 60000).toISOString(),
                transaction_type: "POS_PURCHASE",
                direction: "OUTBOUND",
                amount_usd: 28.50,
                counterparty_name: "Local High Street Cafe",
                counterparty_country: c.residence_country,
                counterparty_category: "RETAILER",
                channel: "POS_TERMINAL"
            },
            {
                transaction_id: "SIM-ATO-DRAIN",
                timestamp: now.toISOString(),
                transaction_type: "INTERNATIONAL_WIRE_OUT",
                direction: "OUTBOUND",
                amount_usd: 12500.0,
                counterparty_name: "Offshore Crypto Clearing FZE",
                counterparty_country: "SC",
                counterparty_category: "CRYPTO_EXCHANGE",
                channel: "WEB_PORTAL",
                device_id: "DEV-UNKNOWN-ATTACKER-99X",
                ip_country: "NG",
                reference_narrative: "Urgent balance transfer to unverified wallet"
            }
        ]
    },
    "CARD_TEST": {
        title: "FR-02: Card Testing / Micro-Authorization Probing Attack",
        desc: "Card details compromised via e-commerce breach. Attacker runs 2 sub-$2 authorizations to verify card is active, followed immediately by high-value CNP purchase.",
        badgeClass: "badge-HIGH",
        badgeText: "HIGH FRAUD",
        category: "FRAUD",
        customer: {
            fname: "Lucas", lname: "Mendoza", citizenship: "US", residence: "US",
            occupation: "SOFTWARE_ENGINEER", income: 98000, turnover: 5000, maxtx: 1800,
            purpose: "SALARY_AND_LIVING_EXPENSES", channel: "DIGITAL_EKYC_BIOMETRIC",
            pep: "NONE", media: "NONE", sanction: "CLEAN",
            products: ["CURRENT_ACCOUNT"]
        },
        getTransactions: (now, c) => [
            {
                transaction_id: "SIM-CARD-P1",
                timestamp: new Date(now.getTime() - 15 * 60000).toISOString(),
                transaction_type: "ONLINE_PURCHASE",
                direction: "OUTBOUND",
                amount_usd: 0.89,
                counterparty_name: "Digital Stream Trial",
                counterparty_country: "US",
                counterparty_category: "RETAILER",
                channel: "WEB_PORTAL",
                card_entry_mode: "CNP_ECOMMERCE"
            },
            {
                transaction_id: "SIM-CARD-P2",
                timestamp: new Date(now.getTime() - 10 * 60000).toISOString(),
                transaction_type: "ONLINE_PURCHASE",
                direction: "OUTBOUND",
                amount_usd: 1.45,
                counterparty_name: "Trial Content Service",
                counterparty_country: "US",
                counterparty_category: "RETAILER",
                channel: "WEB_PORTAL",
                card_entry_mode: "CNP_ECOMMERCE"
            },
            {
                transaction_id: "SIM-CARD-DRAIN",
                timestamp: now.toISOString(),
                transaction_type: "ONLINE_PURCHASE",
                direction: "OUTBOUND",
                amount_usd: 3450.0,
                counterparty_name: "Luxe High-End Electronics Direct",
                counterparty_country: "HK",
                counterparty_category: "RETAILER",
                channel: "WEB_PORTAL",
                card_entry_mode: "CNP_ECOMMERCE",
                auth_status: "DECLINED_SUSPECTED_FRAUD"
            }
        ]
    },
    "APP_SCAM": {
        title: "FR-03: Authorized Push Payment (APP) / Investment Scam",
        desc: "Retired pensioner coerced through deceptive online investment advisory into sending rapid payments to brand new unverified crypto entities.",
        badgeClass: "badge-HIGH",
        badgeText: "HIGH FRAUD",
        category: "FRAUD",
        customer: {
            fname: "Arthur", lname: "Kingsley", citizenship: "GB", residence: "GB",
            occupation: "RETIRED_PENSIONER", income: 42000, turnover: 2500, maxtx: 1500,
            purpose: "RETIREMENT_PENSION", channel: "BRANCH_IN_PERSON",
            pep: "NONE", media: "NONE", sanction: "CLEAN",
            products: ["CURRENT_ACCOUNT", "SAVINGS_ACCOUNT", "INTERNATIONAL_WIRE_SERVICE"]
        },
        getTransactions: (now, c) => [
            {
                transaction_id: "SIM-APP-1",
                timestamp: new Date(now.getTime() - 24 * 3600000).toISOString(),
                transaction_type: "P2P_TRANSFER_OUT",
                direction: "OUTBOUND",
                amount_usd: 6500.0,
                counterparty_name: "Global Alpha Arbitrage Pool Ltd",
                counterparty_country: "GB",
                counterparty_category: "INDIVIDUAL",
                channel: "MOBILE_APP",
                reference_narrative: "Urgent guaranteed return investment enrollment ref #9981",
                is_new_payee: true
            },
            {
                transaction_id: "SIM-APP-2",
                timestamp: now.toISOString(),
                transaction_type: "P2P_TRANSFER_OUT",
                direction: "OUTBOUND",
                amount_usd: 9800.0,
                counterparty_name: "VIP Capital Liquidators Escrow",
                counterparty_country: "GB",
                counterparty_category: "INDIVIDUAL",
                channel: "MOBILE_APP",
                reference_narrative: "Top-up balance to release guaranteed trade profits",
                is_new_payee: true
            }
        ]
    },
    "BUSTOUT": {
        title: "FR-04: First-Party Bust-Out & Deposit Kiting Fraud",
        desc: "Customer deposits unverified external ACH funds, then races against the 48-hour clearing window to extract cash at ATMs and outbound P2P transfers.",
        badgeClass: "badge-CRITICAL",
        badgeText: "CRITICAL FRAUD",
        category: "FRAUD",
        customer: {
            fname: "Dante", lname: "Reyes", citizenship: "US", residence: "US",
            occupation: "RETAIL_EMPLOYEE", income: 29000, turnover: 2200, maxtx: 900,
            purpose: "SALARY_AND_LIVING_EXPENSES", channel: "DIGITAL_WEB_BASIC",
            pep: "NONE", media: "NONE", sanction: "CLEAN",
            products: ["CURRENT_ACCOUNT", "CASH_DEPOSIT_SERVICE"]
        },
        getTransactions: (now, c) => [
            {
                transaction_id: "SIM-BUST-DEP",
                timestamp: new Date(now.getTime() - 18 * 3600000).toISOString(),
                transaction_type: "ACH_DEPOSIT",
                direction: "INBOUND",
                amount_usd: 9850.0,
                counterparty_name: "Apex External Bank Link",
                counterparty_country: "US",
                counterparty_category: "INDIVIDUAL",
                channel: "WEB_PORTAL",
                reference_narrative: "ACH External Link Inbound Transfer"
            },
            {
                transaction_id: "SIM-BUST-ATM1",
                timestamp: new Date(now.getTime() - 14 * 3600000).toISOString(),
                transaction_type: "ATM_WITHDRAWAL",
                direction: "OUTBOUND",
                amount_usd: 1000.0,
                counterparty_name: "ATM Cash Out #4401 - Downtown 24h",
                counterparty_country: "US",
                counterparty_category: "ATM",
                channel: "ATM",
                reference_narrative: "Immediate cash extraction prior to settlement"
            },
            {
                transaction_id: "SIM-BUST-P2P",
                timestamp: now.toISOString(),
                transaction_type: "P2P_TRANSFER_OUT",
                direction: "OUTBOUND",
                amount_usd: 7300.0,
                counterparty_name: "QuickCash Peer Transfer Account",
                counterparty_country: "US",
                counterparty_category: "PEER",
                channel: "MOBILE_APP",
                reference_narrative: "Immediate balance extraction prior to return"
            }
        ]
    },
    "SIM_SWAP": {
        title: "FR-06: SIM Swap & Outbound Wire Evacuation",
        desc: "Carrier port-out / SIM swap executed, mobile MFA intercepted, and $8,950 outbound wire executed from newly enrolled rogue handset within 30 minutes.",
        badgeClass: "badge-CRITICAL",
        badgeText: "CRITICAL FRAUD",
        category: "FRAUD",
        customer: {
            fname: "Julian", lname: "Sterling", citizenship: "US", residence: "US",
            occupation: "CORPORATE_EXECUTIVE", income: 165000, turnover: 8000, maxtx: 3500,
            purpose: "SALARY_AND_LIVING_EXPENSES", channel: "DIGITAL_EKYC_BIOMETRIC",
            pep: "NONE", media: "NONE", sanction: "CLEAN",
            products: ["CURRENT_ACCOUNT", "SAVINGS_ACCOUNT", "INTERNATIONAL_WIRE_SERVICE"]
        },
        getTransactions: (now, c) => [
            {
                transaction_id: "SIM-SWAP-OUT",
                timestamp: now.toISOString(),
                transaction_type: "DOMESTIC_WIRE_OUT",
                direction: "OUTBOUND",
                amount_usd: 8950.0,
                counterparty_name: "NeoBank Digital Escrow LLC",
                counterparty_country: "US",
                counterparty_category: "OFFSHORE_CORP",
                channel: "MOBILE_APP",
                device_id: "DEV-ROGUE-HANDSET-88A",
                reference_narrative: "SIM Swap MFA reset detected: Urgent balance evacuation to external account",
                is_new_payee: true
            }
        ]
    },
    "FRIENDLY_FRAUD": {
        title: "FR-07: Friendly Fraud / Systematic Chargeback Abuse",
        desc: "Cardholder orders four-figure electronics from trusted domestic IP and device with 3DS auth, then systematically disputes transactions as unauthorized.",
        badgeClass: "badge-HIGH",
        badgeText: "HIGH FRAUD",
        category: "FRAUD",
        customer: {
            fname: "Brandon", lname: "Cole", citizenship: "US", residence: "US",
            occupation: "STUDENT", income: 34000, turnover: 2500, maxtx: 1000,
            purpose: "SALARY_AND_LIVING_EXPENSES", channel: "DIGITAL_EKYC_BIOMETRIC",
            pep: "NONE", media: "NONE", sanction: "CLEAN",
            products: ["CURRENT_ACCOUNT"]
        },
        getTransactions: (now, c) => [
            {
                transaction_id: "SIM-FF-1",
                timestamp: new Date(now.getTime() - 8 * 86400000).toISOString(),
                transaction_type: "ONLINE_PURCHASE",
                direction: "OUTBOUND",
                amount_usd: 620.0,
                counterparty_name: "ElectroHub Consumer Tech",
                counterparty_country: "US",
                counterparty_category: "RETAILER",
                channel: "WEB_PORTAL",
                reference_narrative: "Dispute: Unauthorized transaction claim filed by cardholder after 3DS auth"
            },
            {
                transaction_id: "SIM-FF-2",
                timestamp: now.toISOString(),
                transaction_type: "ONLINE_PURCHASE",
                direction: "OUTBOUND",
                amount_usd: 1350.0,
                counterparty_name: "Luxury Watches Direct",
                counterparty_country: "US",
                counterparty_category: "RETAILER",
                channel: "WEB_PORTAL",
                reference_narrative: "Chargeback: Cardholder claims stolen identity despite chip verification"
            }
        ]
    },
    "BIN_ATTACK": {
        title: "FR-08: Automated BIN Attack & Card Testing Velocity",
        desc: "Botnet executes programmatic brute-force testing of expiration dates and CVVs across merchant gateways with rapid declines, followed by high-dollar auth.",
        badgeClass: "badge-CRITICAL",
        badgeText: "CRITICAL FRAUD",
        category: "FRAUD",
        customer: {
            fname: "Claire", lname: "Dupont", citizenship: "FR", residence: "US",
            occupation: "PHYSICIAN_DOCTOR", income: 145000, turnover: 6000, maxtx: 2000,
            purpose: "SALARY_AND_LIVING_EXPENSES", channel: "BRANCH_IN_PERSON",
            pep: "NONE", media: "NONE", sanction: "CLEAN",
            products: ["CURRENT_ACCOUNT"]
        },
        getTransactions: (now, c) => [
            {
                transaction_id: "SIM-BIN-1",
                timestamp: new Date(now.getTime() - 9 * 60000).toISOString(),
                transaction_type: "ONLINE_PURCHASE",
                direction: "OUTBOUND",
                amount_usd: 1.99,
                counterparty_name: "Global FastPay Gateway",
                counterparty_country: "US",
                counterparty_category: "RETAILER",
                channel: "WEB_PORTAL",
                auth_status: "DECLINED_INVALID_CVV",
                reference_narrative: "CVV Mismatch - automated payment gateway test #1"
            },
            {
                transaction_id: "SIM-BIN-2",
                timestamp: new Date(now.getTime() - 6 * 60000).toISOString(),
                transaction_type: "ONLINE_PURCHASE",
                direction: "OUTBOUND",
                amount_usd: 2.49,
                counterparty_name: "Global FastPay Gateway",
                counterparty_country: "US",
                counterparty_category: "RETAILER",
                channel: "WEB_PORTAL",
                auth_status: "DECLINED_EXPIRED",
                reference_narrative: "Expired card error - botnet script test #2"
            },
            {
                transaction_id: "SIM-BIN-DRAIN",
                timestamp: now.toISOString(),
                transaction_type: "ONLINE_PURCHASE",
                direction: "OUTBOUND",
                amount_usd: 850.0,
                counterparty_name: "Global FastPay Gateway",
                counterparty_country: "US",
                counterparty_category: "RETAILER",
                channel: "WEB_PORTAL",
                auth_status: "AUTHORIZED",
                reference_narrative: "High value consumer electronic purchase following brute-force auth"
            }
        ]
    },
    "BEC": {
        title: "FR-09: Executive BEC & Wire Diversion",
        desc: "Spoofed executive communication instructing urgent out-of-band wire diversion of $64,500 for strictly confidential M&A acquisition to offshore nominee.",
        badgeClass: "badge-CRITICAL",
        badgeText: "CRITICAL FRAUD",
        category: "FRAUD",
        customer: {
            fname: "Victoria", lname: "Hawthorne", citizenship: "US", residence: "US",
            occupation: "CORPORATE_EXECUTIVE", income: 240000, turnover: 15000, maxtx: 10000,
            purpose: "INVESTMENT_WEALTH_GROWTH", channel: "DIGITAL_EKYC_BIOMETRIC",
            pep: "NONE", media: "NONE", sanction: "CLEAN",
            products: ["CURRENT_ACCOUNT", "INTERNATIONAL_WIRE_SERVICE"]
        },
        getTransactions: (now, c) => [
            {
                transaction_id: "SIM-BEC-WIRE",
                timestamp: now.toISOString(),
                transaction_type: "INTERNATIONAL_WIRE_OUT",
                direction: "OUTBOUND",
                amount_usd: 64500.0,
                counterparty_name: "Meridian Global Acquisitions Nominee Ltd",
                counterparty_country: "HK",
                counterparty_category: "OFFSHORE_CORP",
                channel: "SWIFT",
                reference_narrative: "Strictly Confidential M&A Acquisition Settlement Ref #9941 / CEO Authorization Required",
                is_new_payee: true
            }
        ]
    },
    "AITM": {
        title: "FR-10: Adversary-in-the-Middle (AitM) Phishing Session Hijack",
        desc: "Reverse-proxy phishing kit steals active session cookie, replayed 25 mins later from foreign VPN IP to sweep $7,800 balance without credential change.",
        badgeClass: "badge-CRITICAL",
        badgeText: "CRITICAL FRAUD",
        category: "FRAUD",
        customer: {
            fname: "Felix", lname: "Schroeder", citizenship: "DE", residence: "US",
            occupation: "SOFTWARE_ENGINEER", income: 115000, turnover: 5500, maxtx: 2200,
            purpose: "SALARY_AND_LIVING_EXPENSES", channel: "DIGITAL_EKYC_BIOMETRIC",
            pep: "NONE", media: "NONE", sanction: "CLEAN",
            products: ["CURRENT_ACCOUNT", "SAVINGS_ACCOUNT"]
        },
        getTransactions: (now, c) => [
            {
                transaction_id: "SIM-AITM-DRAIN",
                timestamp: now.toISOString(),
                transaction_type: "DOMESTIC_WIRE_OUT",
                direction: "OUTBOUND",
                amount_usd: 7800.0,
                counterparty_name: "SwiftClear Virtual Settlement Hub",
                counterparty_country: "US",
                counterparty_category: "CRYPTO_EXCHANGE",
                channel: "WEB_PORTAL",
                ip_country: "DE",
                reference_narrative: "Reverse proxy session token replay: Instant wire out to third-party clearing wallet",
                is_new_payee: true
            }
        ]
    },
    "OVERPAYMENT": {
        title: "FR-11: Counterfeit Overpayment & Urgent Refund Scam",
        desc: "Victim receives $16,800 counterfeit check advance, tricked into immediately wiring $12,400 excess to regional courier before the check bounces.",
        badgeClass: "badge-HIGH",
        badgeText: "HIGH FRAUD",
        category: "FRAUD",
        customer: {
            fname: "Dorothy", lname: "Miller", citizenship: "US", residence: "US",
            occupation: "RETIRED_PENSIONER", income: 34000, turnover: 1800, maxtx: 800,
            purpose: "PERSONAL_SAVINGS", channel: "BRANCH_IN_PERSON",
            pep: "NONE", media: "NONE", sanction: "CLEAN",
            products: ["CURRENT_ACCOUNT", "SAVINGS_ACCOUNT"]
        },
        getTransactions: (now, c) => [
            {
                transaction_id: "SIM-OVP-DEP",
                timestamp: new Date(now.getTime() - 16 * 3600000).toISOString(),
                transaction_type: "ACH_DEPOSIT",
                direction: "INBOUND",
                amount_usd: 16800.0,
                counterparty_name: "National Corporate Disbursing Escrow",
                counterparty_country: "US",
                counterparty_category: "INDIVIDUAL",
                channel: "WEB_PORTAL",
                reference_narrative: "Executive recruitment stipend & equipment advance check"
            },
            {
                transaction_id: "SIM-OVP-REFUND",
                timestamp: now.toISOString(),
                transaction_type: "DOMESTIC_WIRE_OUT",
                direction: "OUTBOUND",
                amount_usd: 12400.0,
                counterparty_name: "Apex Logistics Logistics Agent",
                counterparty_country: "US",
                counterparty_category: "INDIVIDUAL",
                channel: "WEB_PORTAL",
                reference_narrative: "Overpayment refund of unused equipment advance to regional courier agent",
                is_new_payee: true
            }
        ]
    },
    "STRUCTURING": {
        title: "TM-01: Currency Transaction Reporting (CTR) Structuring / Smurfing",
        desc: "Used car dealer deposits 4 cash tranches of $9,400-$9,800 within 8 days across branch tellers to evade the $10,000 statutory CTR threshold.",
        badgeClass: "badge-HIGH",
        badgeText: "HIGH AML",
        category: "AML",
        customer: {
            fname: "Viktor", lname: "Kozlov", citizenship: "US", residence: "US",
            occupation: "USED_CAR_DEALER", income: 65000, turnover: 4500, maxtx: 2000,
            purpose: "PERSONAL_SAVINGS", channel: "DIGITAL_WEB_BASIC",
            pep: "NONE", media: "NONE", sanction: "CLEAN",
            products: ["CURRENT_ACCOUNT", "CASH_DEPOSIT_SERVICE"]
        },
        getTransactions: (now, c) => [
            {
                transaction_id: "SIM-STRUC-1",
                timestamp: new Date(now.getTime() - 6 * 86400000).toISOString(),
                transaction_type: "CASH_DEPOSIT",
                direction: "INBOUND",
                amount_usd: 9450.0,
                counterparty_name: "Branch Teller Desk #101",
                counterparty_country: "US",
                counterparty_category: "ATM_BRANCH",
                channel: "BRANCH_TELLER",
                reference_narrative: "Personal savings cash deposit"
            },
            {
                transaction_id: "SIM-STRUC-2",
                timestamp: new Date(now.getTime() - 4 * 86400000).toISOString(),
                transaction_type: "CASH_DEPOSIT",
                direction: "INBOUND",
                amount_usd: 9600.0,
                counterparty_name: "Branch Teller Desk #104",
                counterparty_country: "US",
                counterparty_category: "ATM_BRANCH",
                channel: "BRANCH_TELLER",
                reference_narrative: "Over-the-counter cash allocation"
            },
            {
                transaction_id: "SIM-STRUC-3",
                timestamp: new Date(now.getTime() - 2 * 86400000).toISOString(),
                transaction_type: "CASH_DEPOSIT",
                direction: "INBOUND",
                amount_usd: 9800.0,
                counterparty_name: "Branch Teller Desk #108",
                counterparty_country: "US",
                counterparty_category: "ATM_BRANCH",
                channel: "BRANCH_TELLER",
                reference_narrative: "Vehicle trade cash deposit"
            },
            {
                transaction_id: "SIM-STRUC-4",
                timestamp: now.toISOString(),
                transaction_type: "CASH_DEPOSIT",
                direction: "INBOUND",
                amount_usd: 9750.0,
                counterparty_name: "Branch Teller Desk #102",
                counterparty_country: "US",
                counterparty_category: "ATM_BRANCH",
                channel: "BRANCH_TELLER",
                reference_narrative: "Cash liquidation proceeds"
            }
        ]
    },
    "MULE": {
        title: "TM-02: Rapid Movement of Funds / Pass-Through Mule Account",
        desc: "Student account with declared $1,200/mo turnover receives $31,986 corporate wire from UAE, dissipating 93.8% to Binance crypto ramp within 22 hours.",
        badgeClass: "badge-CRITICAL",
        badgeText: "CRITICAL AML",
        category: "AML",
        customer: {
            fname: "Tariq", lname: "Okafor", citizenship: "NG", residence: "GB",
            occupation: "STUDENT", income: 16000, turnover: 1200, maxtx: 500,
            purpose: "SALARY_AND_LIVING_EXPENSES", channel: "DIGITAL_WEB_BASIC",
            pep: "NONE", media: "NONE", sanction: "CLEAN",
            products: ["CURRENT_ACCOUNT", "CRYPTO_GATEWAY_ACCESS", "INTERNATIONAL_WIRE_SERVICE"]
        },
        getTransactions: (now, c) => [
            {
                transaction_id: "SIM-MULE-IN",
                timestamp: new Date(now.getTime() - 22 * 3600000).toISOString(),
                transaction_type: "INTERNATIONAL_WIRE_IN",
                direction: "INBOUND",
                amount_usd: 31986.22,
                counterparty_name: "Apex Global Consulting FZE",
                counterparty_country: "AE",
                counterparty_category: "OFFSHORE_CORP",
                channel: "SWIFT",
                reference_narrative: "Payment for International Contract Services Ref 7721"
            },
            {
                transaction_id: "SIM-MULE-OUT",
                timestamp: now.toISOString(),
                transaction_type: "CRYPTO_PURCHASE",
                direction: "OUTBOUND",
                amount_usd: 29997.08,
                counterparty_name: "Binance P2P / Virtual Asset Ramp",
                counterparty_country: "SC",
                counterparty_category: "CRYPTO_EXCHANGE",
                channel: "WEB_PORTAL",
                reference_narrative: "USDT Purchase Settlement #88192301"
            }
        ]
    },
    "BLACKLIST": {
        title: "TM-05: FATF Blacklist / High-Risk Sanctions Wire Activity",
        desc: "Direct wire activity with entities located in FATF Call-for-Action blacklisted jurisdictions (Iran, Syria, North Korea). Mandatory statutory freeze candidate.",
        badgeClass: "badge-CRITICAL",
        badgeText: "STATUTORY AML",
        category: "AML",
        customer: {
            fname: "Hassan", lname: "Al-Mansoor", citizenship: "SY", residence: "AE",
            occupation: "IMPORT_EXPORT_TRADER", income: 140000, turnover: 12000, maxtx: 5000,
            purpose: "CROSS_BORDER_REMITTANCES", channel: "THIRD_PARTY_INTRODUCER",
            pep: "NONE", media: "NONE", sanction: "CLEAN",
            products: ["CURRENT_ACCOUNT", "MULTI_CURRENCY_WALLET", "INTERNATIONAL_WIRE_SERVICE"]
        },
        getTransactions: (now, c) => [
            {
                transaction_id: "SIM-BL-WIRE",
                timestamp: now.toISOString(),
                transaction_type: "INTERNATIONAL_WIRE_OUT",
                direction: "OUTBOUND",
                amount_usd: 48000.0,
                counterparty_name: "Tehran General Mercantile Co",
                counterparty_country: "IR",
                counterparty_category: "OFFSHORE_CORP",
                channel: "SWIFT",
                reference_narrative: "Cross-border settlement via correspondent bank / IRAN_TRANSIT"
            }
        ]
    },
    "DORMANCY": {
        title: "TM-06: Dormant Account Reactivation Surge",
        desc: "Account with 90 days zero transactional activity suddenly reactivated with consecutive five-figure incoming wires without KYC justification.",
        badgeClass: "badge-HIGH",
        badgeText: "HIGH AML",
        category: "AML",
        customer: {
            fname: "Elena", lname: "Vasiliev", citizenship: "DE", residence: "DE",
            occupation: "ACCOUNTANT_CERTIFIED", income: 72000, turnover: 3000, maxtx: 1500,
            purpose: "PERSONAL_SAVINGS", channel: "BRANCH_IN_PERSON",
            pep: "NONE", media: "NONE", sanction: "CLEAN",
            products: ["CURRENT_ACCOUNT", "SAVINGS_ACCOUNT"]
        },
        getTransactions: (now, c) => [
            {
                transaction_id: "SIM-DORM-1",
                timestamp: new Date(now.getTime() - 2 * 86400000).toISOString(),
                transaction_type: "DOMESTIC_WIRE_IN",
                direction: "INBOUND",
                amount_usd: 15000.0,
                counterparty_name: "Private Escrow Trust Alpha 1",
                counterparty_country: "DE",
                counterparty_category: "INDIVIDUAL",
                channel: "WEB_PORTAL",
                reference_narrative: "Settlement proceeds urgent release"
            },
            {
                transaction_id: "SIM-DORM-2",
                timestamp: now.toISOString(),
                transaction_type: "DOMESTIC_WIRE_IN",
                direction: "INBOUND",
                amount_usd: 22000.0,
                counterparty_name: "Private Escrow Trust Alpha 2",
                counterparty_country: "DE",
                counterparty_category: "INDIVIDUAL",
                channel: "WEB_PORTAL",
                reference_narrative: "Second tranche contract release"
            }
        ]
    },
    "TBML": {
        title: "TM-08: Trade-Based Money Laundering (TBML) Over-Invoicing",
        desc: "Retail customer receives $75,000 cross-border wire for bulk raw polymers, wiring $66,000 to Hong Kong shipping forwarder 3 days later under generic Bill of Lading.",
        badgeClass: "badge-CRITICAL",
        badgeText: "CRITICAL AML",
        category: "AML",
        customer: {
            fname: "Chen", lname: "Wei", citizenship: "SG", residence: "AE",
            occupation: "IMPORT_EXPORT_TRADER", income: 280000, turnover: 25000, maxtx: 15000,
            purpose: "CROSS_BORDER_REMITTANCES", channel: "THIRD_PARTY_INTRODUCER",
            pep: "NONE", media: "NONE", sanction: "CLEAN",
            products: ["CURRENT_ACCOUNT", "MULTI_CURRENCY_WALLET", "INTERNATIONAL_WIRE_SERVICE"]
        },
        getTransactions: (now, c) => [
            {
                transaction_id: "SIM-TBML-IN",
                timestamp: new Date(now.getTime() - 3 * 86400000).toISOString(),
                transaction_type: "INTERNATIONAL_WIRE_IN",
                direction: "INBOUND",
                amount_usd: 75000.0,
                counterparty_name: "Al-Noor Petrochem & General Trading LLC",
                counterparty_country: "AE",
                counterparty_category: "OFFSHORE_CORP",
                channel: "SWIFT",
                reference_narrative: "Consignment commercial invoice #4902 - raw industrial polymers cargo"
            },
            {
                transaction_id: "SIM-TBML-OUT",
                timestamp: now.toISOString(),
                transaction_type: "INTERNATIONAL_WIRE_OUT",
                direction: "OUTBOUND",
                amount_usd: 66000.0,
                counterparty_name: "Star Ocean Shipping Logistics Ltd",
                counterparty_country: "HK",
                counterparty_category: "OFFSHORE_CORP",
                channel: "SWIFT",
                reference_narrative: "Bill of Lading #BOL-9912 - bulk freight customs & transshipment fee"
            }
        ]
    },
    "FAN_OUT": {
        title: "TM-09: Fan-Out Layering / High-Velocity Fund Distribution",
        desc: "Single lump-sum wire of $36,000 is immediately fragmented within 24 hours into 5 rapid outbound transfers across P2P, crypto, and prepaid rails to obscure trail.",
        badgeClass: "badge-CRITICAL",
        badgeText: "CRITICAL AML",
        category: "AML",
        customer: {
            fname: "Marcus", lname: "Brody", citizenship: "US", residence: "US",
            occupation: "USED_CAR_DEALER", income: 58000, turnover: 4000, maxtx: 2000,
            purpose: "SALARY_AND_LIVING_EXPENSES", channel: "DIGITAL_WEB_BASIC",
            pep: "NONE", media: "NONE", sanction: "CLEAN",
            products: ["CURRENT_ACCOUNT", "CRYPTO_GATEWAY_ACCESS", "INTERNATIONAL_WIRE_SERVICE"]
        },
        getTransactions: (now, c) => [
            {
                transaction_id: "SIM-FAN-IN",
                timestamp: new Date(now.getTime() - 20 * 3600000).toISOString(),
                transaction_type: "DOMESTIC_WIRE_IN",
                direction: "INBOUND",
                amount_usd: 36000.0,
                counterparty_name: "Vanguard Escrow Holdings Trust",
                counterparty_country: "US",
                counterparty_category: "OFFSHORE_CORP",
                channel: "WEB_PORTAL",
                reference_narrative: "Private contract disbursement proceeds"
            },
            {
                transaction_id: "SIM-FAN-OUT1",
                timestamp: new Date(now.getTime() - 14 * 3600000).toISOString(),
                transaction_type: "P2P_TRANSFER_OUT",
                direction: "OUTBOUND",
                amount_usd: 6800.0,
                counterparty_name: "Alice Chen P2P Account",
                counterparty_country: "US",
                counterparty_category: "PEER",
                channel: "MOBILE_APP",
                reference_narrative: "Fan-out distribution leg #1 settlement",
                is_new_payee: true
            },
            {
                transaction_id: "SIM-FAN-OUT2",
                timestamp: new Date(now.getTime() - 8 * 3600000).toISOString(),
                transaction_type: "CRYPTO_PURCHASE",
                direction: "OUTBOUND",
                amount_usd: 7200.0,
                counterparty_name: "Kraken Digital Ramp",
                counterparty_country: "US",
                counterparty_category: "CRYPTO_EXCHANGE",
                channel: "MOBILE_APP",
                reference_narrative: "Fan-out distribution leg #2 settlement",
                is_new_payee: true
            },
            {
                transaction_id: "SIM-FAN-OUT3",
                timestamp: now.toISOString(),
                transaction_type: "DOMESTIC_WIRE_OUT",
                direction: "OUTBOUND",
                amount_usd: 7000.0,
                counterparty_name: "QuickPay Prepaid Settlement",
                counterparty_country: "US",
                counterparty_category: "OFFSHORE_CORP",
                channel: "MOBILE_APP",
                reference_narrative: "Fan-out distribution leg #3 settlement",
                is_new_payee: true
            }
        ]
    },
    "CUCKOO": {
        title: "TM-10: Cuckoo Smurfing / Hawala Third-Party Remittance",
        desc: "Account receives 4 unrelated cash and domestic deposits ($4,200-$4,800) from unconnected strangers across different bank branches to settle alternative remittance.",
        badgeClass: "badge-HIGH",
        badgeText: "HIGH AML",
        category: "AML",
        customer: {
            fname: "Zainab", lname: "Hashmi", citizenship: "GB", residence: "GB",
            occupation: "IMPORT_EXPORT_TRADER", income: 48000, turnover: 3500, maxtx: 1800,
            purpose: "CROSS_BORDER_REMITTANCES", channel: "BRANCH_IN_PERSON",
            pep: "NONE", media: "NONE", sanction: "CLEAN",
            products: ["CURRENT_ACCOUNT", "CASH_DEPOSIT_SERVICE"]
        },
        getTransactions: (now, c) => [
            {
                transaction_id: "SIM-CUCK-1",
                timestamp: new Date(now.getTime() - 6 * 86400000).toISOString(),
                transaction_type: "CASH_DEPOSIT",
                direction: "INBOUND",
                amount_usd: 4800.0,
                counterparty_name: "Branch Cash Deposit Counter #12",
                counterparty_country: "GB",
                counterparty_category: "ATM_BRANCH",
                channel: "BRANCH_TELLER",
                reference_narrative: "Hawala third-party remittance aggregation deposit"
            },
            {
                transaction_id: "SIM-CUCK-2",
                timestamp: new Date(now.getTime() - 4 * 86400000).toISOString(),
                transaction_type: "DOMESTIC_WIRE_IN",
                direction: "INBOUND",
                amount_usd: 4200.0,
                counterparty_name: "Sarah Jenkins Domestic Transfer",
                counterparty_country: "GB",
                counterparty_category: "INDIVIDUAL",
                channel: "ACH",
                reference_narrative: "Hawala third-party remittance aggregation deposit"
            },
            {
                transaction_id: "SIM-CUCK-3",
                timestamp: now.toISOString(),
                transaction_type: "CASH_DEPOSIT",
                direction: "INBOUND",
                amount_usd: 4600.0,
                counterparty_name: "Metro Retail Cash Counter",
                counterparty_country: "GB",
                counterparty_category: "ATM_BRANCH",
                channel: "BRANCH_TELLER",
                reference_narrative: "Hawala third-party remittance aggregation deposit"
            }
        ]
    },
    "MIXER": {
        title: "TM-11: Crypto Mixer & Privacy Protocol Interaction",
        desc: "Direct outbound wire of $18,500 to sanctioned Tornado Cash router, followed by $17,800 cleaned return hop from Wasabi CoinJoin anonymity pool.",
        badgeClass: "badge-CRITICAL",
        badgeText: "STATUTORY AML",
        category: "AML",
        customer: {
            fname: "Soren", lname: "Nielsen", citizenship: "DE", residence: "DE",
            occupation: "CRYPTO_BROKER", income: 195000, turnover: 18000, maxtx: 8000,
            purpose: "CRYPTO_ASSET_TRADING", channel: "DIGITAL_EKYC_BIOMETRIC",
            pep: "NONE", media: "NONE", sanction: "CLEAN",
            products: ["CURRENT_ACCOUNT", "CRYPTO_GATEWAY_ACCESS", "INTERNATIONAL_WIRE_SERVICE"]
        },
        getTransactions: (now, c) => [
            {
                transaction_id: "SIM-MIX-OUT",
                timestamp: new Date(now.getTime() - 48 * 3600000).toISOString(),
                transaction_type: "CRYPTO_PURCHASE",
                direction: "OUTBOUND",
                amount_usd: 18500.0,
                counterparty_name: "Tornado Cash Router 0xd90e... (Sanctioned Protocol)",
                counterparty_country: "SC",
                counterparty_category: "CRYPTO_MIXER",
                channel: "WEB_PORTAL",
                reference_narrative: "Direct deposit to zero-knowledge privacy pool / mixer contract"
            },
            {
                transaction_id: "SIM-MIX-IN",
                timestamp: now.toISOString(),
                transaction_type: "CRYPTO_CASHOUT",
                direction: "INBOUND",
                amount_usd: 17800.0,
                counterparty_name: "Wasabi CoinJoin Anonymized Aggregator",
                counterparty_country: "VG",
                counterparty_category: "CRYPTO_MIXER",
                channel: "WEB_PORTAL",
                reference_narrative: "Cleaned crypto cash-out hop from privacy tumbler pool"
            }
        ]
    },
    "TRAFFICKING": {
        title: "TM-12: Human Trafficking & Modern Slavery Red Flags",
        desc: "Centralized wage skimming from 3 workers deposited into supervisor account, followed by multiple late-night $800 ATM cash extractions at 02:40 AM.",
        badgeClass: "badge-CRITICAL",
        badgeText: "CRITICAL AML",
        category: "AML",
        customer: {
            fname: "Mateo", lname: "Silva", citizenship: "ES", residence: "US",
            occupation: "NIGHTCLUB_RESTAURANT_OWNER", income: 48000, turnover: 3000, maxtx: 1200,
            purpose: "SALARY_AND_LIVING_EXPENSES", channel: "DIGITAL_WEB_BASIC",
            pep: "NONE", media: "NONE", sanction: "CLEAN",
            products: ["CURRENT_ACCOUNT", "CASH_DEPOSIT_SERVICE"]
        },
        getTransactions: (now, c) => [
            {
                transaction_id: "SIM-HT-W1",
                timestamp: new Date(now.getTime() - 12 * 3600000).toISOString(),
                transaction_type: "P2P_TRANSFER_IN",
                direction: "INBOUND",
                amount_usd: 850.0,
                counterparty_name: "Worker Wage Credit 01",
                counterparty_country: "US",
                counterparty_category: "PEER",
                channel: "MOBILE_APP",
                reference_narrative: "Worker wage deduction for recruitment fee / centralized payroll skimming"
            },
            {
                transaction_id: "SIM-HT-W2",
                timestamp: new Date(now.getTime() - 10 * 3600000).toISOString(),
                transaction_type: "P2P_TRANSFER_IN",
                direction: "INBOUND",
                amount_usd: 850.0,
                counterparty_name: "Worker Wage Credit 02",
                counterparty_country: "US",
                counterparty_category: "PEER",
                channel: "MOBILE_APP",
                reference_narrative: "Worker wage deduction for recruitment fee / centralized payroll skimming"
            },
            {
                transaction_id: "SIM-HT-ATM",
                timestamp: now.toISOString(),
                transaction_type: "ATM_WITHDRAWAL",
                direction: "OUTBOUND",
                amount_usd: 800.0,
                counterparty_name: "Highway Border Travel Plaza ATM",
                counterparty_country: "US",
                counterparty_category: "ATM",
                channel: "ATM",
                reference_narrative: "Late-night ATM cash extraction / centralized wage pooling cashout"
            }
        ]
    },
    "LOAN_WASH": {
        title: "TM-13: Loan Collateral Laundering & Rapid Liquidation",
        desc: "Customer secures $40,000 term loan disbursement and liquidates the debt in full 10 days later using unverified offshore funds, turning dirty funds into clean bank payoff.",
        badgeClass: "badge-HIGH",
        badgeText: "HIGH AML",
        category: "AML",
        customer: {
            fname: "Derrick", lname: "Vaughn", citizenship: "US", residence: "US",
            occupation: "USED_CAR_DEALER", income: 88000, turnover: 6000, maxtx: 3000,
            purpose: "INVESTMENT_WEALTH_GROWTH", channel: "BRANCH_IN_PERSON",
            pep: "NONE", media: "NONE", sanction: "CLEAN",
            products: ["CURRENT_ACCOUNT", "INTERNATIONAL_WIRE_SERVICE"]
        },
        getTransactions: (now, c) => [
            {
                transaction_id: "SIM-LOAN-DISB",
                timestamp: new Date(now.getTime() - 10 * 86400000).toISOString(),
                transaction_type: "DOMESTIC_WIRE_IN",
                direction: "INBOUND",
                amount_usd: 40000.0,
                counterparty_name: "Valiant Commercial Credit Disbursal Unit",
                counterparty_country: "US",
                counterparty_category: "OFFSHORE_CORP",
                channel: "SWIFT",
                reference_narrative: "Term loan disbursement principal funding"
            },
            {
                transaction_id: "SIM-LOAN-PAYOFF",
                timestamp: now.toISOString(),
                transaction_type: "INTERNATIONAL_WIRE_OUT",
                direction: "OUTBOUND",
                amount_usd: 40150.0,
                counterparty_name: "Valiant Credit Loan Servicing Dept",
                counterparty_country: "US",
                counterparty_category: "OFFSHORE_CORP",
                channel: "SWIFT",
                reference_narrative: "Loan settlement full: Early payoff using offshore liquidity release"
            }
        ]
    },
    "NONE": {
        title: "Clean Retail Banking Baseline",
        desc: "Regular salaried professional with predictable domestic income, groceries, household utilities, and normal spend behavior within expected limits.",
        badgeClass: "badge-LOW",
        badgeText: "CLEAN BASELINE",
        category: "BASELINE",
        customer: {
            fname: "Alexandre", lname: "Vance", citizenship: "US", residence: "US",
            occupation: "SOFTWARE_ENGINEER", income: 95000, turnover: 6000, maxtx: 2500,
            purpose: "SALARY_AND_LIVING_EXPENSES", channel: "DIGITAL_EKYC_BIOMETRIC",
            pep: "NONE", media: "NONE", sanction: "CLEAN",
            products: ["CURRENT_ACCOUNT", "SAVINGS_ACCOUNT"]
        },
        getTransactions: (now, c) => [
            {
                transaction_id: "SIM-NORM-1",
                timestamp: new Date(now.getTime() - 15 * 86400000).toISOString(),
                transaction_type: "SALARY_CREDIT",
                direction: "INBOUND",
                amount_usd: 7916.67,
                counterparty_name: "Vance Tech Solutions Inc",
                counterparty_country: "US",
                counterparty_category: "EMPLOYER",
                channel: "ACH",
                reference_narrative: "Direct Payroll Deposit / Net Earnings"
            },
            {
                transaction_id: "SIM-NORM-2",
                timestamp: new Date(now.getTime() - 5 * 86400000).toISOString(),
                transaction_type: "POS_PURCHASE",
                direction: "OUTBOUND",
                amount_usd: 84.50,
                counterparty_name: "Whole Foods Market",
                counterparty_country: "US",
                counterparty_category: "RETAILER",
                channel: "POS_TERMINAL",
                reference_narrative: "Groceries & Household"
            }
        ]
    }
};

function applyTypologyPreset(scenarioKey) {
    const preset = TYPOLOGY_PRESETS[scenarioKey];
    if (!preset) return;

    // Update customer form fields with relevant profile
    const c = preset.customer;
    if (c) {
        const setVal = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.value = val;
        };

        setVal("sim-fname", c.fname);
        setVal("sim-lname", c.lname);
        setVal("sim-citizenship", c.citizenship);
        setVal("sim-residence", c.residence);
        setVal("sim-occupation", c.occupation);
        setVal("sim-income", c.income);
        setVal("sim-turnover", c.turnover);
        setVal("sim-maxtx", c.maxtx);
        setVal("sim-purpose", c.purpose);
        setVal("sim-channel", c.channel);
        setVal("sim-pep", c.pep);
        setVal("sim-media", c.media);
        setVal("sim-sanction", c.sanction);

        // Update product checkboxes
        document.querySelectorAll("#sim-products input").forEach(el => {
            el.checked = c.products && c.products.includes(el.value);
        });
    }

    // Update select dropdown
    const sel = document.getElementById("sim-scenario");
    if (sel && sel.value !== scenarioKey) {
        sel.value = scenarioKey;
    }

    // Update preset banner
    const bannerTitle = document.getElementById("preset-banner-title");
    const bannerDesc = document.getElementById("preset-banner-desc");
    const bannerBadge = document.getElementById("preset-banner-badge");
    if (bannerTitle) bannerTitle.textContent = `Active Preset: ${preset.title}`;
    if (bannerDesc) bannerDesc.textContent = preset.desc;
    if (bannerBadge) {
        bannerBadge.className = `badge ${preset.badgeClass}`;
        bannerBadge.textContent = preset.badgeText;
    }

    // Highlight active chip
    document.querySelectorAll(".typology-chip").forEach(chip => {
        if (chip.dataset.pick === scenarioKey) {
            chip.classList.add("active");
        } else {
            chip.classList.remove("active");
        }
    });
}

function initSimulator() {
    const simBtn = document.getElementById("run-simulation-btn");
    const scenarioSelect = document.getElementById("sim-scenario");

    // Initialize with default preset (ATO)
    applyTypologyPreset("ATO");

    // Scenario dropdown change listener
    if (scenarioSelect) {
        scenarioSelect.addEventListener("change", (e) => {
            applyTypologyPreset(e.target.value);
        });
    }

    // Quick-pick chips listener
    document.querySelectorAll(".typology-chip").forEach(chip => {
        chip.addEventListener("click", () => {
            applyTypologyPreset(chip.dataset.pick);
        });
    });

    // "Pick & Test in Simulator" buttons on Fraud and AML typology cards
    document.querySelectorAll(".btn-pick-test").forEach(btn => {
        if (btn.dataset.pick) {
            btn.addEventListener("click", () => {
                // Switch to simulator tab
                const navTabs = document.querySelectorAll(".nav-tab");
                const tabContents = document.querySelectorAll(".tab-content");
                navTabs.forEach(t => t.classList.remove("active"));
                tabContents.forEach(c => c.style.display = "none");

                const simTabBtn = document.querySelector('.nav-tab[data-target="tab-simulator"]');
                const simTabContent = document.getElementById("tab-simulator");
                if (simTabBtn) simTabBtn.classList.add("active");
                if (simTabContent) simTabContent.style.display = "block";

                // Apply the picked preset
                applyTypologyPreset(btn.dataset.pick);

                // Scroll smoothly to simulator form
                simTabContent.scrollIntoView({ behavior: "smooth" });
            });
        }
    });

    if (!simBtn) return;

    simBtn.addEventListener("click", async () => {
        const scenario = document.getElementById("sim-scenario").value;
        const now = new Date();

        const payload = {
            customer: {
                first_name: document.getElementById("sim-fname").value,
                last_name: document.getElementById("sim-lname").value,
                citizenship: document.getElementById("sim-citizenship").value,
                residence_country: document.getElementById("sim-residence").value,
                tax_residence_country: document.getElementById("sim-residence").value,
                occupation: document.getElementById("sim-occupation").value,
                occupation_risk_key: document.getElementById("sim-occupation").value,
                annual_income_usd: parseFloat(document.getElementById("sim-income").value) || 60000,
                net_worth_usd: (parseFloat(document.getElementById("sim-income").value) || 60000) * 3,
                declared_expected_monthly_turnover_usd: parseFloat(document.getElementById("sim-turnover").value) || 5000,
                declared_expected_max_single_tx_usd: parseFloat(document.getElementById("sim-maxtx").value) || 2000,
                declared_purpose_nature: document.getElementById("sim-purpose").value,
                onboarding_channel: document.getElementById("sim-channel").value,
                pep_status: document.getElementById("sim-pep").value,
                adverse_media: document.getElementById("sim-media").value,
                sanction_status: document.getElementById("sim-sanction").value,
                products_held: Array.from(document.querySelectorAll("#sim-products input:checked")).map(el => el.value)
            },
            scenario: scenario,
            transactions: []
        };

        // Populate relevant transactions for this preset
        const preset = TYPOLOGY_PRESETS[scenario];
        if (preset && typeof preset.getTransactions === "function") {
            payload.transactions = preset.getTransactions(now, payload.customer);
        }

        try {
            simBtn.textContent = "Calculating FRAML Risk Score...";
            const res = await fetch("/api/simulate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            const result = await res.json();
            renderSimulationResult(result);
        } catch (err) {
            console.error("Simulation error:", err);
        } finally {
            simBtn.textContent = "Run Real-Time FRAML Risk Engine Scoring";
        }
    });
}

function renderSimulationResult(res) {
    const out = document.getElementById("simulation-result");
    out.style.display = "block";
    out.scrollIntoView({ behavior: "smooth" });

    out.innerHTML = `
        <div style="background: var(--bg-card); border: 2px solid ${res.risk_tier === 'CRITICAL' ? 'var(--tier-crit)' : res.risk_tier === 'HIGH' ? 'var(--tier-high)' : 'var(--accent-blue)'}; border-radius: 8px; padding: 20px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                <div>
                    <h3 style="font-size: 18px;">Simulation Assessment Result</h3>
                    <p style="color: var(--text-secondary); font-size: 13px;">${res.executive_summary}</p>
                </div>
                <div style="text-align: right;">
                    <span class="badge badge-${res.risk_tier}" style="font-size: 14px; padding: 6px 12px;">${res.risk_tier} TIER</span>
                    <div style="font-size: 26px; font-weight: 800; margin-top: 4px;">${res.composite_score.toFixed(1)} / 100</div>
                    <div style="font-size: 11px;">AML: <strong>${(res.aml_score || 0).toFixed(1)}</strong> | Fraud: <strong style="color: var(--fraud-magenta);">${(res.fraud_score || 0).toFixed(1)}</strong></div>
                </div>
            </div>

            <div style="padding: 10px 14px; background: rgba(59,130,246,0.1); border-left: 3px solid var(--accent-blue); margin-bottom: 16px; font-size: 13px;">
                <strong>Governance Directive:</strong> ${res.recommended_action}
            </div>

            ${res.fraud_alerts && res.fraud_alerts.length > 0 ? `
                <div style="margin-top: 14px;">
                    <h4 style="font-size: 13px; color: var(--fraud-magenta); margin-bottom: 8px;">Triggered Fraud Alerts (${res.fraud_alerts.length}):</h4>
                    ${res.fraud_alerts.map(a => `
                        <div class="alert-item fraud">
                            <div class="alert-title"><span>[${a.rule_id}] ${a.rule_name}</span> <span class="badge badge-fraud">${a.severity}</span></div>
                            <div class="alert-desc">${a.summary}</div>
                        </div>
                    `).join('')}
                </div>
            ` : ''}

            ${res.alerts && res.alerts.length > 0 ? `
                <div style="margin-top: 14px;">
                    <h4 style="font-size: 13px; color: #f97316; margin-bottom: 8px;">Triggered AML Alerts (${res.alerts.length}):</h4>
                    ${res.alerts.map(a => `
                        <div class="alert-item ${a.severity}">
                            <div class="alert-title"><span>[${a.rule_id}] ${a.rule_name}</span> <span class="badge badge-${a.severity}">${a.severity}</span></div>
                            <div class="alert-desc">${a.summary}</div>
                        </div>
                    `).join('')}
                </div>
            ` : ''}
        </div>
    `;
}

function initGenerator() {
    const genBtn = document.getElementById("run-generator-btn");
    const statusBox = document.getElementById("gen-status-box");
    if (!genBtn) return;

    genBtn.addEventListener("click", async () => {
        const count = parseInt(document.getElementById("gen-count").value) || 100;
        const days = parseInt(document.getElementById("gen-days").value) || 90;
        const seed = parseInt(document.getElementById("gen-seed").value) || 42;

        genBtn.disabled = true;
        genBtn.textContent = "⏳ Generating Cohort & Scoring...";
        statusBox.style.display = "block";
        statusBox.style.background = "rgba(59, 130, 246, 0.1)";
        statusBox.style.color = "var(--text-primary)";
        statusBox.textContent = `Running generation pipeline for ${count} customers (${days} days history, seed ${seed}). Please wait...`;

        try {
            const res = await fetch("/api/generate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ count, days, seed })
            });
            const data = await res.json();

            if (data.status === "success") {
                statusBox.style.background = "rgba(16, 185, 129, 0.15)";
                statusBox.style.color = "#10b981";
                statusBox.textContent = `✓ ${data.message}`;

                // Reload portfolio, customers, and transactions
                loadPortfolio();
                loadCustomers();
                loadTransactions();
            } else {
                statusBox.style.background = "rgba(239, 68, 68, 0.15)";
                statusBox.style.color = "#ef4444";
                statusBox.textContent = `Error: ${data.message || 'Generation failed'}`;
            }
        } catch (err) {
            statusBox.style.background = "rgba(239, 68, 68, 0.15)";
            statusBox.style.color = "#ef4444";
            statusBox.textContent = `Network error: ${err.message}`;
        } finally {
            genBtn.disabled = false;
            genBtn.textContent = "⚡ Generate Cohort & Run FRAML Scoring";
        }
    });
}

// ==========================================================================
// AI VIDEO PERSONA & CUSTOMER OUTREACH CALL SUITE (GEMINI AUDIO & PERSONA)
// ==========================================================================

let activeCallSession = null;
let callDurationSec = 0;
let callTimerInterval = null;
let isCallAudioEnabled = true;
let isCallMicActive = false;
let callSpeechRecognition = null;

// Persona Animation State
let personaCanvas = null;
let personaCtx = null;
let waveformCanvas = null;
let waveformCtx = null;
let personaState = "DISCONNECTED"; // DISCONNECTED, RINGING, CONNECTED, SPEAKING, LISTENING, ANALYZING
let personaBlinkPhase = 0; // 0 open, 1 fully closed
let nextBlinkTime = Date.now() + 2500;
let currentViseme = "rest"; // rest, open_o, wide_e, neutral_a, closed_m, bottom_f
let visemeMouthOpening = 0.0;
let visemeQueue = [];
let visemeStartTime = 0;
let gazeDriftX = 0;
let gazeDriftY = 0;
let audioVisualizerData = new Array(16).fill(4);

function initVideoPersona() {
    personaCanvas = document.getElementById("persona-canvas");
    waveformCanvas = document.getElementById("waveform-canvas");

    if (personaCanvas) {
        personaCtx = personaCanvas.getContext("2d");
    }
    if (waveformCanvas) {
        waveformCtx = waveformCanvas.getContext("2d");
    }

    if (!window._personaAnimationStarted) {
        window._personaAnimationStarted = true;
        requestAnimationFrame(renderPersonaLoop);
    }
}

function initCustomerCall() {
    initVideoPersona();

    const startBtn = document.getElementById("btn-call-start");
    const endBtn = document.getElementById("btn-call-end");
    const micBtn = document.getElementById("btn-call-mic");
    const audioToggleBtn = document.getElementById("btn-call-audio-toggle");
    const duplexBtn = document.getElementById("btn-call-duplex");
    const interruptBtn = document.getElementById("btn-call-interrupt");
    const interruptBarBtn = document.getElementById("btn-call-interrupt-bar");
    const pipTile = document.getElementById("customer-pip-tile");
    const inputForm = document.getElementById("call-customer-input-form");
    const copyDossierBtn = document.getElementById("btn-copy-call-dossier");
    const viewAuditBtn = document.getElementById("btn-view-audit-dossier");

    if (startBtn) {
        startBtn.addEventListener("click", () => {
            if (!activeCallAudioContext) {
                activeCallAudioContext = new (window.AudioContext || window.webkitAudioContext)();
            }
            if (activeCallAudioContext.state === "suspended") {
                activeCallAudioContext.resume();
            }
            const selectEl = document.getElementById("call-target-customer");
            const customerId = selectEl ? selectEl.value : "CUST-00019";
            startCustomerCallSession(customerId);
        });
    }

    if (endBtn) {
        endBtn.addEventListener("click", () => {
            endCustomerCallSession();
        });
    }

    if (micBtn) {
        micBtn.addEventListener("click", () => {
            toggleCustomerMicrophone();
        });
    }

    if (duplexBtn) {
        duplexBtn.addEventListener("click", () => {
            toggleHandsFreeMode();
        });
    }

    const handleInterruptClick = () => {
        if (activeCallSession) {
            interruptAgentSpeech();
            startCustomerSpeechCapture(true);
        }
    };
    if (interruptBtn) interruptBtn.addEventListener("click", handleInterruptClick);
    if (interruptBarBtn) interruptBarBtn.addEventListener("click", handleInterruptClick);

    if (pipTile) {
        pipTile.addEventListener("click", () => {
            if (activeCallSession) toggleCustomerMicrophone();
        });
    }

    // Spacebar shortcut to interrupt or speak (Walkie-talkie style)
    if (!window._callKeyboardBound) {
        window._callKeyboardBound = true;
        document.addEventListener("keydown", (e) => {
            if (e.code === "Space" && e.target.tagName !== "INPUT" && e.target.tagName !== "TEXTAREA") {
                const callTab = document.getElementById("tab-call");
                if (callTab && callTab.classList.contains("active") && activeCallSession) {
                    e.preventDefault();
                    if (personaState === "SPEAKING") {
                        interruptAgentSpeech();
                        startCustomerSpeechCapture(true);
                    } else {
                        toggleCustomerMicrophone();
                    }
                }
            }
        });
    }

    if (audioToggleBtn) {
        audioToggleBtn.addEventListener("click", () => {
            isCallAudioEnabled = !isCallAudioEnabled;
            audioToggleBtn.innerHTML = isCallAudioEnabled ? "<span>🔊</span> Audio: On" : "<span>🔇</span> Audio: Muted";
            if (!isCallAudioEnabled) {
                stopActiveCallAudio();
            }
        });
    }

    if (inputForm) {
        inputForm.addEventListener("submit", (e) => {
            e.preventDefault();
            const inputEl = document.getElementById("call-customer-text-input");
            if (!inputEl) return;
            const text = inputEl.value.trim();
            if (!text) return;
            inputEl.value = "";
            sendCustomerTurn(text);
        });
    }

    if (copyDossierBtn) {
        copyDossierBtn.addEventListener("click", () => {
            const content = document.getElementById("post-call-dossier-content");
            if (content) {
                navigator.clipboard.writeText(content.innerText).then(() => {
                    copyDossierBtn.textContent = "✓ Dossier Copied!";
                    setTimeout(() => { copyDossierBtn.textContent = "📋 Copy Dossier"; }, 2000);
                });
            }
        });
    }

    if (viewAuditBtn) {
        viewAuditBtn.addEventListener("click", () => {
            const navTabs = document.querySelectorAll(".nav-tab");
            const auditTabBtn = document.querySelector('.nav-tab[data-target="tab-audit"]');
            if (auditTabBtn) {
                auditTabBtn.click();
            }
        });
    }

    // Populate customer select with loaded customers if available
    populateCallCustomerDropdown();
}

function populateCallCustomerDropdown() {
    const select = document.getElementById("call-target-customer");
    if (!select || !window._cachedCustomerList || window._cachedCustomerList.length === 0) return;

    const existingVal = select.value;
    select.innerHTML = window._cachedCustomerList.map(c => `
        <option value="${c.customer_id}">
            ${c.name || `${c.first_name} ${c.last_name}`} (${c.customer_id} — ${c.archetype || c.occupation})
        </option>
    `).join("");

    if (existingVal) {
        select.value = existingVal;
    }
}

window.quickSelectCallCustomer = function(custId) {
    const select = document.getElementById("call-target-customer");
    if (select) {
        select.value = custId;
    }
    const navTabs = document.querySelectorAll(".nav-tab");
    const callTabBtn = document.querySelector('.nav-tab[data-target="tab-call"]');
    if (callTabBtn) {
        callTabBtn.click();
    }
};

window.launchCustomerCallFromDossier = function(custId) {
    quickSelectCallCustomer(custId);
    // Auto-trigger call
    setTimeout(() => {
        startCustomerCallSession(custId);
    }, 400);
};

// ==========================================
// CALL SESSION MANAGEMENT & TURN DISPATCH
// ==========================================

async function startCustomerCallSession(customerId) {
    if (activeCallSession) {
        endCustomerCallSession();
    }

    const startBtn = document.getElementById("btn-call-start");
    const endBtn = document.getElementById("btn-call-end");
    const micBtn = document.getElementById("btn-call-mic");
    const inputEl = document.getElementById("call-customer-text-input");
    const sendBtn = document.getElementById("btn-call-send");
    const transcriptStream = document.getElementById("call-transcript-stream");
    const captionsEl = document.getElementById("call-live-captions");
    const statusBadge = document.getElementById("call-status-badge");
    const timerText = document.getElementById("call-timer-text");
    const postDossier = document.getElementById("post-call-dossier-panel");
    const voiceSelect = document.getElementById("call-voice-select");
    const selectedVoice = voiceSelect ? voiceSelect.value : "Aoede";

    if (postDossier) postDossier.style.display = "none";
    if (transcriptStream) {
        transcriptStream.innerHTML = `<div style="text-align: center; color: var(--accent-blue); padding: 20px;">Establishing secure 256-bit encrypted audio connection...</div>`;
    }

    // Play synthesized dial tone
    playDialTone();
    personaState = "RINGING";
    if (statusBadge) {
        statusBadge.textContent = "DIALING CUSTOMER...";
        statusBadge.className = "badge badge-MED";
        statusBadge.style.background = "rgba(245, 158, 11, 0.2)";
        statusBadge.style.color = "#fbbf24";
        statusBadge.style.border = "1px solid rgba(245, 158, 11, 0.4)";
    }
    if (captionsEl) {
        captionsEl.innerHTML = `<em>Dialing customer... Establishing secure verification channel with Google Gemini Neural Audio.</em>`;
    }

    if (startBtn) startBtn.style.display = "none";
    if (endBtn) endBtn.style.display = "flex";

    try {
        const resp = await fetch("/api/call/start", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ customer_id: customerId, voice_name: selectedVoice })
        });
        const data = await resp.json();

        // Connect after brief realistic ring
        setTimeout(() => {
            activeCallSession = data.session_id;
            personaState = "CONNECTED";
            callDurationSec = 0;
            if (timerText) timerText.textContent = "00:00";
            clearInterval(callTimerInterval);
            callTimerInterval = setInterval(() => {
                callDurationSec++;
                const mins = String(Math.floor(callDurationSec / 60)).padStart(2, '0');
                const secs = String(callDurationSec % 60).padStart(2, '0');
                if (timerText) timerText.textContent = `${mins}:${secs}`;
            }, 1000);

            if (statusBadge) {
                statusBadge.textContent = "LIVE CALL (ENCRYPTED)";
                statusBadge.className = "badge badge-LOW";
                statusBadge.style.background = "rgba(16, 185, 129, 0.2)";
                statusBadge.style.color = "#34d399";
                statusBadge.style.border = "1px solid rgba(16, 185, 129, 0.4)";
            }

            if (micBtn) micBtn.disabled = false;
            if (inputEl) inputEl.disabled = false;
            if (sendBtn) sendBtn.disabled = false;
            if (transcriptStream) transcriptStream.innerHTML = "";

            const duplexBtn = document.getElementById("btn-call-duplex");
            if (duplexBtn) duplexBtn.disabled = false;

            const pipName = document.getElementById("customer-pip-name");
            const pipTile = document.getElementById("customer-pip-tile");
            const pipStatus = document.getElementById("customer-pip-status-text");
            if (pipName && data.customer_name) pipName.textContent = `${data.customer_name} (You)`;
            if (pipTile) pipTile.classList.add("active");
            if (pipStatus) pipStatus.textContent = "Mic Ready • Click Talk or Space";

            // Proactively initialize customer mic permissions
            initCustomerMicrophone();

            // Render opening agent message
            appendSpeechBubble("agent", data.message);
            updateAgentEmotionUI(data.audio_emotion || "warm_reassuring");
            speakAgentMessage(data.message, data.viseme_cues, data.audio_base64, data.audio_emotion || "warm_reassuring");
        }, 1200);

    } catch (err) {
        personaState = "DISCONNECTED";
        if (statusBadge) {
            statusBadge.textContent = "FAILED TO CONNECT";
            statusBadge.className = "badge badge-HIGH";
        }
        if (captionsEl) captionsEl.textContent = `Call failed: ${err.message}`;
        if (startBtn) startBtn.style.display = "flex";
        if (endBtn) endBtn.style.display = "none";
    }
}

async function sendCustomerTurn(text, wasInterrupted = false) {
    if (!activeCallSession) return;

    appendSpeechBubble("customer", text);
    personaState = "ANALYZING";

    const captionsEl = document.getElementById("call-live-captions");
    const voiceSelect = document.getElementById("call-voice-select");
    const selectedVoice = voiceSelect ? voiceSelect.value : "Aoede";

    if (captionsEl) {
        captionsEl.innerHTML = `<em>Agent Sterling is evaluating customer statement against banking records...</em>`;
    }

    try {
        const resp = await fetch("/api/call/turn", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                session_id: activeCallSession,
                message: text,
                voice_name: selectedVoice,
                interrupted: wasInterrupted
            })
        });
        const turnData = await resp.json();

        // Update telemetry HUD
        updateCallTelemetry(turnData);
        updateAgentEmotionUI(turnData.audio_emotion);

        // Speak reply with expressive neural audio
        appendSpeechBubble("agent", turnData.agent_message);
        speakAgentMessage(turnData.agent_message, turnData.viseme_cues, turnData.audio_base64, turnData.audio_emotion);

    } catch (err) {
        personaState = "CONNECTED";
        if (captionsEl) captionsEl.textContent = `Error processing turn: ${err.message}`;
    }
}

window.sendCustomerQuickReply = function(text) {
    if (!activeCallSession) {
        alert("Please start the verification call first.");
        return;
    }
    const wasInterrupted = interruptAgentSpeech();
    sendCustomerTurn(text, wasInterrupted);
};

async function endCustomerCallSession() {
    if (!activeCallSession) return;

    clearInterval(callTimerInterval);
    stopActiveCallAudio();

    // Teardown microphone and audio capture
    if (customerMediaStream) {
        try {
            customerMediaStream.getTracks().forEach(t => t.stop());
        } catch (e) {}
        customerMediaStream = null;
    }
    if (customerAudioCtx) {
        try { customerAudioCtx.close(); } catch (e) {}
        customerAudioCtx = null;
        customerAudioAnalyser = null;
    }
    if (callSpeechRecognition && speechRecActive) {
        try { callSpeechRecognition.stop(); } catch (e) {}
        speechRecActive = false;
    }
    isCallMicActive = false;
    isHandsFreeMode = false;

    personaState = "DISCONNECTED";
    currentViseme = "rest";
    visemeMouthOpening = 0.0;

    const startBtn = document.getElementById("btn-call-start");
    const endBtn = document.getElementById("btn-call-end");
    const micBtn = document.getElementById("btn-call-mic");
    const inputEl = document.getElementById("call-customer-text-input");
    const sendBtn = document.getElementById("btn-call-send");
    const statusBadge = document.getElementById("call-status-badge");
    const captionsEl = document.getElementById("call-live-captions");
    const postDossier = document.getElementById("post-call-dossier-panel");
    const dossierContent = document.getElementById("post-call-dossier-content");
    const duplexBtn = document.getElementById("btn-call-duplex");
    const pipTile = document.getElementById("customer-pip-tile");
    const pipStatus = document.getElementById("customer-pip-status-text");
    const pipMicBadge = document.getElementById("customer-pip-mic-badge");
    const interruptBtn = document.getElementById("btn-call-interrupt");
    const interruptBarBtn = document.getElementById("btn-call-interrupt-bar");
    const alertEl = document.getElementById("call-interruption-alert");

    if (duplexBtn) {
        duplexBtn.disabled = true;
        duplexBtn.classList.remove("active");
        duplexBtn.innerHTML = "<span>🎧</span> Hands-Free: Off";
    }
    if (pipTile) {
        pipTile.classList.remove("active");
        pipTile.classList.remove("speaking");
    }
    if (pipStatus) pipStatus.textContent = "Call Ended";
    if (pipMicBadge) {
        pipMicBadge.textContent = "🎤 Muted";
        pipMicBadge.style.color = "#94a3b8";
    }
    if (interruptBtn) interruptBtn.style.display = "none";
    if (interruptBarBtn) interruptBarBtn.style.display = "none";
    if (alertEl) alertEl.style.display = "none";

    if (statusBadge) {
        statusBadge.textContent = "COMPLETED & RECORDED";
        statusBadge.className = "badge badge-LOW";
    }
    if (captionsEl) captionsEl.innerHTML = `<em>Call ended. Compiling formal customer verification dossier for case audit trail...</em>`;
    if (startBtn) startBtn.style.display = "flex";
    if (endBtn) endBtn.style.display = "none";
    if (micBtn) micBtn.disabled = true;
    if (inputEl) inputEl.disabled = true;
    if (sendBtn) sendBtn.disabled = true;

    try {
        const resp = await fetch("/api/call/complete", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: activeCallSession })
        });
        const finalData = await resp.json();

        activeCallSession = null;
        if (captionsEl) {
            captionsEl.innerHTML = `<strong>Dossier Generated:</strong> Case ${finalData.investigation_id} | SHA-256 Digest: <code>${(finalData.sha256_digest || '').substring(0, 16)}...</code>`;
        }

        if (postDossier && dossierContent) {
            postDossier.style.display = "block";
            postDossier.scrollIntoView({ behavior: "smooth" });
            dossierContent.innerHTML = `
                <div style="display: flex; gap: 10px; align-items: center; margin-bottom: 12px; background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); padding: 8px 12px; border-radius: 6px;">
                    <span style="color: #34d399; font-weight: 700;">🔒 Tamper-Evident SHA-256 Digest:</span>
                    <code style="color: #6ee7b7; font-family: monospace;">${finalData.sha256_digest}</code>
                    <span style="margin-left: auto; color: var(--text-muted); font-size: 11px;">Audit Log ID: ${finalData.investigation_id}</span>
                </div>
                ${formatMarkdown(finalData.interview_dossier)}
            `;
        }
    } catch (err) {
        if (captionsEl) captionsEl.textContent = `Failed to finalize dossier: ${err.message}`;
    }
}

function appendSpeechBubble(speaker, text) {
    const stream = document.getElementById("call-transcript-stream");
    if (!stream) return;

    const bubble = document.createElement("div");
    bubble.className = `speech-bubble ${speaker}`;
    const icon = speaker === "agent" ? "🛡️ Agent Claire Sterling" : "👤 Customer";
    bubble.innerHTML = `
        <div class="speech-sender">${icon}</div>
        <div>${text}</div>
    `;
    stream.appendChild(bubble);
    stream.scrollTop = stream.scrollHeight;

    const captionsEl = document.getElementById("call-live-captions");
    if (captionsEl) {
        captionsEl.innerHTML = `<strong>${speaker === "agent" ? "Agent Sterling" : "Customer"}:</strong> "${text}"`;
    }
}

function updateCallTelemetry(data) {
    const plausScoreText = document.getElementById("plausibility-score-text");
    const plausBar = document.getElementById("plausibility-bar");
    const plausBadge = document.getElementById("plausibility-verdict-badge");
    const sentimentText = document.getElementById("customer-sentiment-text");
    const claimsList = document.getElementById("extracted-claims-list");
    const claimsCount = document.getElementById("claims-count");
    const flagsList = document.getElementById("evasive-flags-list");
    const flagsCount = document.getElementById("flags-count");

    const score = data.plausibility_score || 75.0;
    if (plausScoreText) plausScoreText.textContent = `${score.toFixed(1)}%`;
    if (plausBar) {
        plausBar.style.width = `${Math.min(100, Math.max(5, score))}%`;
        plausBar.style.background = score >= 70 ? "var(--tier-low)" : score >= 45 ? "var(--tier-med)" : "var(--tier-crit)";
    }

    if (plausBadge) {
        plausBadge.textContent = data.plausibility_verdict || "IN_REVIEW";
        plausBadge.className = `badge ${score >= 70 ? 'badge-LOW' : score >= 45 ? 'badge-MED' : 'badge-HIGH'}`;
    }

    if (sentimentText) sentimentText.textContent = data.customer_sentiment || "COOPERATIVE";

    if (claimsList && data.extracted_facts) {
        claimsCount.textContent = data.extracted_facts.length;
        claimsList.innerHTML = data.extracted_facts.length > 0 
            ? data.extracted_facts.map(f => `<div>• ${f}</div>`).join("") 
            : "None yet";
    }

    if (flagsList && data.evasive_flags) {
        flagsCount.textContent = data.evasive_flags.length;
        flagsList.innerHTML = data.evasive_flags.length > 0 
            ? data.evasive_flags.map(f => `<div style="color: #f87171;">⚠️ ${f}</div>`).join("") 
            : "None detected";
    }
}

// ==========================================
// VOICE SYNTHESIS, MICROPHONE, BARGE-IN & VAD ENGINE
// ==========================================

let activeCallAudioContext = null;
let activeCallAudioSource = null;
let activeCallAudioAnalyser = null;

let customerMediaStream = null;
let customerMediaRecorder = null;
let customerRecordedChunks = [];
let customerAudioCtx = null;
let customerAudioAnalyser = null;
let isHandsFreeMode = false;
let wasCustomerInterrupted = false;
let lastCustomerSpeechTime = 0;
let speechRecActive = false;
let speechRecFinalText = "";

function base64ToArrayBuffer(base64) {
    const binaryString = window.atob(base64);
    const len = binaryString.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
        bytes[i] = binaryString.charCodeAt(i);
    }
    return bytes.buffer;
}

function stopActiveCallAudio() {
    if (activeCallAudioSource) {
        try { activeCallAudioSource.stop(); } catch (e) {}
        activeCallAudioSource = null;
    }
    activeCallAudioAnalyser = null;
    if (window.speechSynthesis) {
        window.speechSynthesis.cancel();
    }
    const interruptBtn = document.getElementById("btn-call-interrupt");
    const interruptBarBtn = document.getElementById("btn-call-interrupt-bar");
    if (interruptBtn) interruptBtn.style.display = "none";
    if (interruptBarBtn) interruptBarBtn.style.display = "none";
}

function showInterruptionNotice(msg = "Customer interrupted — Agent Sterling yielded to listen") {
    const alertEl = document.getElementById("call-interruption-alert");
    if (!alertEl) return;
    alertEl.innerHTML = `<span>⚡</span><span><strong>Interrupted:</strong> ${msg}</span>`;
    alertEl.style.display = "flex";
    clearTimeout(window._interruptTimeout);
    window._interruptTimeout = setTimeout(() => {
        if (alertEl) alertEl.style.display = "none";
    }, 3500);
}

function interruptAgentSpeech() {
    const wasSpeaking = (personaState === "SPEAKING" || activeCallAudioSource !== null || (window.speechSynthesis && window.speechSynthesis.speaking));
    stopActiveCallAudio();
    wasCustomerInterrupted = true;
    personaState = "INTERRUPTED";
    currentViseme = "rest";
    visemeMouthOpening = 0.0;
    simulateAudioEqualizer(0.0);
    showInterruptionNotice("Customer interrupted — Agent Claire Sterling paused to listen");

    const captionsEl = document.getElementById("call-live-captions");
    const statusBadge = document.getElementById("call-status-badge");
    if (captionsEl) {
        captionsEl.innerHTML = `<em>⚡ Interrupted! Agent Sterling yielded to listen to you. Speak now...</em>`;
    }
    if (statusBadge) {
        statusBadge.textContent = "⚡ INTERRUPTED / LISTENING";
        statusBadge.className = "badge badge-MED";
        statusBadge.style.background = "rgba(245, 158, 11, 0.2)";
        statusBadge.style.color = "#fbbf24";
    }
    return wasSpeaking;
}

function toggleHandsFreeMode() {
    isHandsFreeMode = !isHandsFreeMode;
    const btn = document.getElementById("btn-call-duplex");
    if (btn) {
        if (isHandsFreeMode) {
            btn.classList.add("active");
            btn.innerHTML = "<span>🎧</span> Hands-Free: ON";
            btn.title = "Hands-free duplex enabled. Speak naturally anytime to interrupt the agent!";
            initCustomerMicrophone();
        } else {
            btn.classList.remove("active");
            btn.innerHTML = "<span>🎧</span> Hands-Free: Off";
            btn.title = "Enable Hands-Free Live Call";
        }
    }
}

async function initCustomerMicrophone() {
    if (customerMediaStream && customerMediaStream.active) {
        return true;
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        console.warn("Microphone API not supported in this browser.");
        return false;
    }
    try {
        customerMediaStream = await navigator.mediaDevices.getUserMedia({
            audio: {
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
            }
        });

        customerAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
        if (customerAudioCtx.state === "suspended") {
            await customerAudioCtx.resume();
        }
        const source = customerAudioCtx.createMediaStreamSource(customerMediaStream);
        customerAudioAnalyser = customerAudioCtx.createAnalyser();
        customerAudioAnalyser.fftSize = 64;
        customerAudioAnalyser.smoothingTimeConstant = 0.5;
        source.connect(customerAudioAnalyser);

        const pipMicBadge = document.getElementById("customer-pip-mic-badge");
        if (pipMicBadge) {
            pipMicBadge.textContent = "🎤 Ready";
            pipMicBadge.style.color = "#34d399";
        }
        return true;
    } catch (err) {
        console.warn("Microphone access error:", err);
        const captionsEl = document.getElementById("call-live-captions");
        if (captionsEl) {
            captionsEl.innerHTML = `<span style="color: #f87171;">⚠️ Microphone permission requested. Please allow microphone access in your browser to speak directly.</span>`;
        }
        return false;
    }
}

async function startCustomerSpeechCapture(isInterruption = false) {
    if (!activeCallSession) return;

    if (personaState === "SPEAKING" || activeCallAudioSource || isInterruption) {
        interruptAgentSpeech();
    }

    const hasMic = await initCustomerMicrophone();
    if (!hasMic) return;

    isCallMicActive = true;
    personaState = "LISTENING";
    currentViseme = "rest";
    visemeMouthOpening = 0.0;

    const micBtn = document.getElementById("btn-call-mic");
    const pipTile = document.getElementById("customer-pip-tile");
    const pipStatus = document.getElementById("customer-pip-status-text");
    const pipMicBadge = document.getElementById("customer-pip-mic-badge");
    const inputEl = document.getElementById("call-customer-text-input");
    const statusBadge = document.getElementById("call-status-badge");
    const captionsEl = document.getElementById("call-live-captions");

    if (micBtn) {
        micBtn.classList.add("active");
        micBtn.innerHTML = "<span>🔴</span> Done Speaking (Send)";
        micBtn.title = "Click when finished speaking to submit your reply";
    }
    if (pipTile) {
        pipTile.classList.add("speaking");
        pipTile.classList.add("active");
    }
    if (pipStatus) pipStatus.textContent = "Listening to you...";
    if (pipMicBadge) {
        pipMicBadge.textContent = "🔴 LIVE";
        pipMicBadge.style.color = "#f87171";
    }
    if (statusBadge) {
        statusBadge.textContent = wasCustomerInterrupted ? "⚡ INTERRUPTED / LISTENING" : "LISTENING TO CUSTOMER";
        statusBadge.className = "badge badge-MED";
        statusBadge.style.background = "rgba(245, 158, 11, 0.2)";
        statusBadge.style.color = "#fbbf24";
    }
    if (captionsEl) {
        captionsEl.innerHTML = wasCustomerInterrupted
            ? `<em>⚡ You interrupted Agent Sterling. Speak now into your microphone...</em>`
            : `<em>Listening... Speak now into your microphone (or type below).</em>`;
    }

    // Start MediaRecorder for bulletproof Gemini audio transcription
    customerRecordedChunks = [];
    try {
        let mimeType = "audio/webm;codecs=opus";
        if (!MediaRecorder.isTypeSupported(mimeType)) {
            mimeType = MediaRecorder.isTypeSupported("audio/mp4") ? "audio/mp4" : "";
        }
        customerMediaRecorder = mimeType ? new MediaRecorder(customerMediaStream, { mimeType }) : new MediaRecorder(customerMediaStream);
        customerMediaRecorder.ondataavailable = (e) => {
            if (e.data && e.data.size > 0) {
                customerRecordedChunks.push(e.data);
            }
        };
        customerMediaRecorder.start(100);
    } catch (e) {
        console.warn("MediaRecorder start error:", e);
    }

    // Parallel SpeechRecognition for live interim feedback
    speechRecFinalText = "";
    if (('webkitSpeechRecognition' in window) || ('SpeechRecognition' in window)) {
        try {
            const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
            callSpeechRecognition = new SpeechRec();
            callSpeechRecognition.continuous = false;
            callSpeechRecognition.interimResults = true;
            callSpeechRecognition.lang = "en-US";

            callSpeechRecognition.onresult = (e) => {
                let interim = "";
                for (let i = e.resultIndex; i < e.results.length; ++i) {
                    if (e.results[i].isFinal) {
                        speechRecFinalText += e.results[i][0].transcript + " ";
                    } else {
                        interim += e.results[i][0].transcript;
                    }
                }
                const display = (speechRecFinalText + interim).trim();
                if (inputEl && display) {
                    inputEl.value = display;
                }
                if (captionsEl && display) {
                    captionsEl.innerHTML = `<strong>You:</strong> "${display}"`;
                }
            };

            callSpeechRecognition.onerror = (e) => {
                console.warn("SpeechRec error (recorded audio will be transcribed by Gemini):", e.error);
            };

            callSpeechRecognition.start();
            speechRecActive = true;
        } catch (e) {
            console.warn("SpeechRec init error:", e);
        }
    }
}

async function stopCustomerSpeechCaptureAndSubmit() {
    if (!isCallMicActive) return;
    isCallMicActive = false;

    const micBtn = document.getElementById("btn-call-mic");
    const pipTile = document.getElementById("customer-pip-tile");
    const pipStatus = document.getElementById("customer-pip-status-text");
    const pipMicBadge = document.getElementById("customer-pip-mic-badge");
    const inputEl = document.getElementById("call-customer-text-input");
    const captionsEl = document.getElementById("call-live-captions");

    if (micBtn) {
        micBtn.classList.remove("active");
        micBtn.innerHTML = "<span>🎤</span> Talk (Mic)";
        micBtn.title = "Click or Hold Spacebar to Speak";
    }
    if (pipTile) {
        pipTile.classList.remove("speaking");
    }
    if (pipStatus) pipStatus.textContent = "Processing reply...";
    if (pipMicBadge) {
        pipMicBadge.textContent = "🎤 Standby";
        pipMicBadge.style.color = "#94a3b8";
    }

    if (callSpeechRecognition && speechRecActive) {
        try { callSpeechRecognition.stop(); } catch (e) {}
        speechRecActive = false;
    }

    const typedText = inputEl ? inputEl.value.trim() : "";
    const spokenText = (speechRecFinalText || typedText).trim();

    if (customerMediaRecorder && customerMediaRecorder.state !== "inactive") {
        personaState = "ANALYZING";
        if (captionsEl) {
            captionsEl.innerHTML = `<em>Agent Sterling is evaluating customer statement against banking records...</em>`;
        }

        customerMediaRecorder.onstop = async () => {
            const mimeType = customerMediaRecorder.mimeType || "audio/webm";
            const audioBlob = new Blob(customerRecordedChunks, { type: mimeType });

            if (spokenText.length >= 3) {
                if (inputEl) inputEl.value = "";
                await sendCustomerTurn(spokenText, wasCustomerInterrupted);
                wasCustomerInterrupted = false;
            } else if (audioBlob.size > 800) {
                await sendCustomerAudioBlob(audioBlob, mimeType, wasCustomerInterrupted);
                wasCustomerInterrupted = false;
                if (inputEl) inputEl.value = "";
            } else {
                personaState = "CONNECTED";
                if (captionsEl) {
                    captionsEl.innerHTML = `<em>No speech detected. Click "Talk (Mic)" or type your response.</em>`;
                }
            }
        };
        customerMediaRecorder.stop();
    } else if (spokenText.length > 0) {
        if (inputEl) inputEl.value = "";
        await sendCustomerTurn(spokenText, wasCustomerInterrupted);
        wasCustomerInterrupted = false;
    } else {
        personaState = "CONNECTED";
    }
}

async function sendCustomerAudioBlob(blob, mimeType, wasInterrupted = false) {
    if (!activeCallSession) return;
    personaState = "ANALYZING";

    const voiceSelect = document.getElementById("call-voice-select");
    const selectedVoice = voiceSelect ? voiceSelect.value : "Aoede";
    const captionsEl = document.getElementById("call-live-captions");

    if (captionsEl) {
        captionsEl.innerHTML = `<em>Transcribing your voice with Google Gemini Audio Reasoning...</em>`;
    }

    const reader = new FileReader();
    reader.readAsDataURL(blob);
    reader.onloadend = async () => {
        try {
            const base64Data = reader.result.split(',')[1];
            const resp = await fetch("/api/call/audio-turn", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    session_id: activeCallSession,
                    audio_base64: base64Data,
                    audio_mime: mimeType,
                    voice_name: selectedVoice,
                    interrupted: wasInterrupted
                })
            });
            const turnData = await resp.json();

            const custText = turnData.customer_transcript || "[Customer Voice Message]";
            appendSpeechBubble("customer", custText);

            updateCallTelemetry(turnData);
            updateAgentEmotionUI(turnData.audio_emotion);

            appendSpeechBubble("agent", turnData.agent_message);
            speakAgentMessage(turnData.agent_message, turnData.viseme_cues, turnData.audio_base64, turnData.audio_emotion);
        } catch (err) {
            personaState = "CONNECTED";
            if (captionsEl) captionsEl.textContent = `Audio processing error: ${err.message}`;
        }
    };
}

function toggleCustomerMicrophone() {
    if (!activeCallSession) {
        alert("Please start the verification call first.");
        return;
    }
    if (isCallMicActive) {
        stopCustomerSpeechCaptureAndSubmit();
    } else {
        startCustomerSpeechCapture(false);
    }
}

function updateAgentEmotionUI(emotion) {
    const el = document.getElementById("agent-emotion-text");
    if (!el) return;
    const labels = {
        "warm_reassuring": "Warm & Reassuring 🌸",
        "gentle_calming": "Gentle & Calming 🕊️",
        "compassionate_probing": "Empathetic Inquiry 🔍",
        "polite_documentation": "Cordial & Attentive 📋",
        "soothing_empathy": "Soothing & Supportive 🤝",
    };
    el.textContent = labels[emotion] || "Warm & Professional 🛡️";
}

async function speakAgentMessage(text, visemeCues, audioBase64, emotion) {
    if (!isCallAudioEnabled) {
        simulateVisemes(visemeCues);
        return;
    }

    stopActiveCallAudio();

    // Show interrupt buttons while agent is speaking
    const interruptBtn = document.getElementById("btn-call-interrupt");
    const interruptBarBtn = document.getElementById("btn-call-interrupt-bar");
    if (interruptBtn) interruptBtn.style.display = "inline-flex";
    if (interruptBarBtn) interruptBarBtn.style.display = "inline-flex";

    if (audioBase64) {
        try {
            if (!activeCallAudioContext) {
                activeCallAudioContext = new (window.AudioContext || window.webkitAudioContext)();
            }
            if (activeCallAudioContext.state === "suspended") {
                await activeCallAudioContext.resume();
            }

            const arrayBuffer = base64ToArrayBuffer(audioBase64);
            const audioBuffer = await activeCallAudioContext.decodeAudioData(arrayBuffer);

            const source = activeCallAudioContext.createBufferSource();
            source.buffer = audioBuffer;

            const analyser = activeCallAudioContext.createAnalyser();
            analyser.fftSize = 64;
            analyser.smoothingTimeConstant = 0.72;

            source.connect(analyser);
            analyser.connect(activeCallAudioContext.destination);

            activeCallAudioSource = source;
            activeCallAudioAnalyser = analyser;
            personaState = "SPEAKING";

            source.onended = () => {
                if (activeCallAudioSource === source) {
                    activeCallAudioSource = null;
                    activeCallAudioAnalyser = null;
                    personaState = "CONNECTED";
                    currentViseme = "rest";
                    visemeMouthOpening = 0.0;
                    simulateAudioEqualizer(0.0);
                    if (interruptBtn) interruptBtn.style.display = "none";
                    if (interruptBarBtn) interruptBarBtn.style.display = "none";
                    const captionsEl = document.getElementById("call-live-captions");
                    if (captionsEl) {
                        captionsEl.innerHTML = `<em>Agent Sterling finished speaking. Your turn to reply or speak...</em>`;
                    }
                }
            };

            source.start(0);
            return;
        } catch (err) {
            console.warn("Neural audio playback error, falling back to speech synthesis:", err);
        }
    }

    // Fallback: Expressive SpeechSynthesis with emotion modulation
    fallbackSpeakAgentMessage(text, visemeCues, emotion);
}

function fallbackSpeakAgentMessage(text, visemeCues, emotion) {
    if (!window.speechSynthesis) {
        simulateVisemes(visemeCues);
        return;
    }

    window.speechSynthesis.cancel();
    personaState = "SPEAKING";

    const interruptBtn = document.getElementById("btn-call-interrupt");
    const interruptBarBtn = document.getElementById("btn-call-interrupt-bar");
    if (interruptBtn) interruptBtn.style.display = "inline-flex";
    if (interruptBarBtn) interruptBarBtn.style.display = "inline-flex";

    const utterance = new SpeechSynthesisUtterance(text);

    if (emotion === "gentle_calming") {
        utterance.pitch = 0.98;
        utterance.rate = 0.90;
    } else if (emotion === "compassionate_probing") {
        utterance.pitch = 1.06;
        utterance.rate = 0.94;
    } else if (emotion === "polite_documentation") {
        utterance.pitch = 1.02;
        utterance.rate = 0.98;
    } else {
        utterance.pitch = 1.04;
        utterance.rate = 0.95;
    }

    const voices = window.speechSynthesis.getVoices();
    const preferredVoice = voices.find(v => v.lang.startsWith("en") && (
        v.name.includes("Google") || v.name.includes("Natural") || v.name.includes("Samantha") ||
        v.name.includes("Victoria") || v.name.includes("Female") || v.name.includes("Karen")
    ));
    if (preferredVoice) {
        utterance.voice = preferredVoice;
    }

    visemeQueue = visemeCues || [];
    visemeStartTime = Date.now();

    utterance.onboundary = (e) => {
        visemeMouthOpening = 0.75 + Math.random() * 0.25;
        simulateAudioEqualizer(1.0);
    };

    utterance.onend = () => {
        personaState = "CONNECTED";
        currentViseme = "rest";
        visemeMouthOpening = 0.0;
        simulateAudioEqualizer(0.0);
        if (interruptBtn) interruptBtn.style.display = "none";
        if (interruptBarBtn) interruptBarBtn.style.display = "none";
    };

    utterance.onerror = () => {
        personaState = "CONNECTED";
        currentViseme = "rest";
        visemeMouthOpening = 0.0;
        simulateAudioEqualizer(0.0);
        if (interruptBtn) interruptBtn.style.display = "none";
        if (interruptBarBtn) interruptBarBtn.style.display = "none";
    };

    window.speechSynthesis.speak(utterance);
}

function simulateVisemes(visemeCues) {
    if (!visemeCues || visemeCues.length === 0) return;
    personaState = "SPEAKING";
    let idx = 0;

    const interval = setInterval(() => {
        if (idx >= visemeCues.length || personaState !== "SPEAKING") {
            clearInterval(interval);
            personaState = "CONNECTED";
            currentViseme = "rest";
            visemeMouthOpening = 0.0;
            simulateAudioEqualizer(0.0);
            return;
        }
        currentViseme = visemeCues[idx].viseme;
        visemeMouthOpening = 0.6 + Math.random() * 0.35;
        simulateAudioEqualizer(0.85);
        idx++;
    }, 180);
}

function playDialTone() {
    try {
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const osc1 = audioCtx.createOscillator();
        const osc2 = audioCtx.createOscillator();
        const gain = audioCtx.createGain();

        osc1.frequency.setValueAtTime(440, audioCtx.currentTime);
        osc2.frequency.setValueAtTime(480, audioCtx.currentTime);
        gain.gain.setValueAtTime(0.08, audioCtx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 1.2);

        osc1.connect(gain);
        osc2.connect(gain);
        gain.connect(audioCtx.destination);

        osc1.start();
        osc2.start();
        osc1.stop(audioCtx.currentTime + 1.2);
        osc2.stop(audioCtx.currentTime + 1.2);
    } catch (e) {
    }
}

function simulateAudioEqualizer(strength) {
    for (let i = 0; i < audioVisualizerData.length; i++) {
        if (strength > 0.1) {
            audioVisualizerData[i] = Math.min(28, Math.max(4, Math.floor(Math.random() * 24 * strength) + 4));
        } else {
            audioVisualizerData[i] = Math.max(3, audioVisualizerData[i] * 0.85);
        }
    }
}

function updateCustomerAudioAnalysis() {
    if (customerAudioAnalyser) {
        const freqData = new Uint8Array(customerAudioAnalyser.frequencyBinCount);
        customerAudioAnalyser.getByteFrequencyData(freqData);

        let sum = 0;
        for (let i = 0; i < freqData.length; i++) {
            sum += freqData[i];
        }
        const avgVolume = sum / (freqData.length * 255);

        // Update PIP visualizer bars
        const pipBars = document.querySelectorAll("#customer-pip-waves span");
        if (pipBars && pipBars.length > 0) {
            pipBars.forEach((bar, idx) => {
                const sample = freqData[idx * 3] || 0;
                const h = Math.max(3, Math.floor((sample / 255) * 14));
                bar.style.height = `${h}px`;
                bar.style.background = isCallMicActive ? "#10b981" : "#64748b";
            });
        }

        // Live Voice Activity Detection (VAD) & Barge-In
        if (avgVolume > 0.05) {
            if (personaState === "SPEAKING") {
                interruptAgentSpeech();
                if (!isCallMicActive) {
                    startCustomerSpeechCapture(true);
                }
            } else if (isHandsFreeMode && !isCallMicActive && personaState === "CONNECTED") {
                startCustomerSpeechCapture(false);
            }

            if (isCallMicActive) {
                lastCustomerSpeechTime = Date.now();
                simulateAudioEqualizer(avgVolume * 2);
            }
        } else if (isHandsFreeMode && isCallMicActive) {
            if (lastCustomerSpeechTime > 0 && Date.now() - lastCustomerSpeechTime > 1400) {
                lastCustomerSpeechTime = 0;
                stopCustomerSpeechCaptureAndSubmit();
            }
        }
    }
}

function updateAudioAnalysis() {
    updateCustomerAudioAnalysis();

    if (personaState === "SPEAKING" && activeCallAudioAnalyser) {
        const freqData = new Uint8Array(activeCallAudioAnalyser.frequencyBinCount);
        activeCallAudioAnalyser.getByteFrequencyData(freqData);

        let sum = 0;
        for (let i = 0; i < freqData.length; i++) {
            sum += freqData[i];
            if (i < audioVisualizerData.length) {
                const targetVal = Math.max(4, Math.floor((freqData[i] / 255) * 28));
                audioVisualizerData[i] = audioVisualizerData[i] * 0.35 + targetVal * 0.65;
            }
        }

        const avgVolume = sum / (freqData.length * 255);
        visemeMouthOpening = Math.min(1.0, avgVolume * 2.8);

        const lowEnergy = (freqData[1] || 0) + (freqData[2] || 0);
        const midEnergy = (freqData[3] || 0) + (freqData[4] || 0);
        const highEnergy = (freqData[7] || 0) + (freqData[8] || 0);

        if (avgVolume > 0.05) {
            if (lowEnergy > midEnergy * 1.25) {
                currentViseme = "open_o";
            } else if (highEnergy > lowEnergy * 1.1) {
                currentViseme = "wide_e";
            } else if (midEnergy > lowEnergy) {
                currentViseme = "neutral_a";
            } else {
                currentViseme = "bottom_f";
            }
        } else {
            currentViseme = "closed_m";
        }
    }
}

// ==========================================
// PERSONA 60FPS CANVAS RENDERING ENGINE
// ==========================================

function renderPersonaLoop(time) {
    updateAudioAnalysis();
    if (personaCanvas && personaCtx) {
        drawPersonaFrame(personaCtx, personaCanvas.width, personaCanvas.height, time);
    }
    if (waveformCanvas && waveformCtx) {
        drawWaveformFrame(waveformCtx, waveformCanvas.width, waveformCanvas.height);
    }
    requestAnimationFrame(renderPersonaLoop);
}

function drawWaveformFrame(ctx, w, h) {
    ctx.clearRect(0, 0, w, h);
    const bars = audioVisualizerData.length;
    const barWidth = (w - (bars * 3)) / bars;

    for (let i = 0; i < bars; i++) {
        const val = audioVisualizerData[i];
        const barH = Math.min(h - 4, val);
        const x = i * (barWidth + 3) + 4;
        const y = h - barH - 2;

        const grad = ctx.createLinearGradient(0, y, 0, h);
        if (personaState === "SPEAKING") {
            grad.addColorStop(0, "#38bdf8");
            grad.addColorStop(1, "#2563eb");
        } else if (personaState === "LISTENING" || isCallMicActive) {
            grad.addColorStop(0, "#34d399");
            grad.addColorStop(1, "#059669");
        } else if (personaState === "INTERRUPTED") {
            grad.addColorStop(0, "#fbbf24");
            grad.addColorStop(1, "#d97706");
        } else {
            grad.addColorStop(0, "#64748b");
            grad.addColorStop(1, "#334155");
        }
        ctx.fillStyle = grad;
        ctx.fillRect(x, y, barWidth, barH);
    }
}

function drawPersonaFrame(ctx, w, h, time) {
    ctx.clearRect(0, 0, w, h);

    // 1. Security Control Room Background
    const bgGrad = ctx.createRadialGradient(w * 0.5, h * 0.4, 40, w * 0.5, h * 0.5, w * 0.7);
    bgGrad.addColorStop(0, "#162238");
    bgGrad.addColorStop(0.6, "#0b1220");
    bgGrad.addColorStop(1, "#04070e");
    ctx.fillStyle = bgGrad;
    ctx.fillRect(0, 0, w, h);

    // Subtle Digital Surveillance Grid
    ctx.strokeStyle = "rgba(59, 130, 246, 0.08)";
    ctx.lineWidth = 1;
    for (let x = 0; x < w; x += 40) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, h);
        ctx.stroke();
    }
    for (let y = 0; y < h; y += 40) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(w, y);
        ctx.stroke();
    }

    // Corporate watermark
    ctx.fillStyle = "rgba(148, 163, 184, 0.08)";
    ctx.font = "bold 13px monospace";
    ctx.fillText("VALIANT BANK • SECURE COMPLIANCE FEED", 20, h - 20);

    // 2. Head & Breathing Kinematics
    const breatheY = Math.sin(time * 0.002) * 2;
    let headNod = 0;
    if (personaState === "LISTENING" || personaState === "INTERRUPTED") {
        headNod = Math.sin(time * 0.005) * 3;
    } else if (personaState === "SPEAKING") {
        headNod = Math.sin(time * 0.008) * 2.2;
    }

    // Blink calculation
    if (Date.now() > nextBlinkTime) {
        personaBlinkPhase += 0.22;
        if (personaBlinkPhase >= 1) {
            personaBlinkPhase = 1;
            nextBlinkTime = Date.now() + 3000 + Math.random() * 2500;
        }
    } else if (personaBlinkPhase > 0) {
        personaBlinkPhase = Math.max(0, personaBlinkPhase - 0.22);
    }

    // Gaze drift
    if (Math.random() < 0.02) {
        gazeDriftX = (Math.random() - 0.5) * 4;
        gazeDriftY = (Math.random() - 0.5) * 2;
    }

    const cx = w * 0.5;
    const cy = h * 0.44 + breatheY + headNod;

    // 3. Shoulders and Corporate Suit
    ctx.save();
    // Torso / Navy Blazer
    ctx.fillStyle = "#111c30";
    ctx.beginPath();
    ctx.moveTo(cx - 160, h);
    ctx.quadraticCurveTo(cx - 130, cy + 110, cx - 60, cy + 95);
    ctx.lineTo(cx + 60, cy + 95);
    ctx.quadraticCurveTo(cx + 130, cy + 110, cx + 160, h);
    ctx.closePath();
    ctx.fill();

    // Lapels & Collar
    ctx.fillStyle = "#1e2e4d";
    ctx.beginPath();
    ctx.moveTo(cx - 60, cy + 95);
    ctx.lineTo(cx - 24, cy + 145);
    ctx.lineTo(cx, cy + 175);
    ctx.lineTo(cx + 24, cy + 145);
    ctx.lineTo(cx + 60, cy + 95);
    ctx.lineTo(cx + 35, cy + 105);
    ctx.lineTo(cx - 35, cy + 105);
    ctx.closePath();
    ctx.fill();

    // White blouse collar inside V-neck
    ctx.fillStyle = "#f8fafc";
    ctx.beginPath();
    ctx.moveTo(cx - 28, cy + 98);
    ctx.lineTo(cx, cy + 135);
    ctx.lineTo(cx + 28, cy + 98);
    ctx.lineTo(cx + 16, cy + 95);
    ctx.lineTo(cx, cy + 115);
    ctx.lineTo(cx - 16, cy + 95);
    ctx.closePath();
    ctx.fill();

    // Lanyard & Security Badge
    ctx.strokeStyle = "#2563eb";
    ctx.lineWidth = 3.5;
    ctx.beginPath();
    ctx.moveTo(cx - 26, cy + 110);
    ctx.lineTo(cx - 10, cy + 195);
    ctx.moveTo(cx + 26, cy + 110);
    ctx.lineTo(cx + 10, cy + 195);
    ctx.stroke();

    // Badge Card
    ctx.fillStyle = "#0f172a";
    ctx.strokeStyle = "#38bdf8";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.roundRect(cx - 28, cy + 190, 56, 36, 4);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = "#38bdf8";
    ctx.font = "bold 6px sans-serif";
    ctx.fillText("VALIANT BANK", cx - 22, cy + 202);
    ctx.fillStyle = "#94a3b8";
    ctx.font = "5px monospace";
    ctx.fillText("VB-SEC-8419", cx - 22, cy + 211);
    ctx.fillStyle = "#10b981";
    ctx.fillText("VERIFIED L4", cx - 22, cy + 220);

    // 4. Neck
    ctx.fillStyle = "#f1c29e";
    ctx.beginPath();
    ctx.moveTo(cx - 22, cy + 45);
    ctx.lineTo(cx - 26, cy + 105);
    ctx.lineTo(cx + 26, cy + 105);
    ctx.lineTo(cx + 22, cy + 45);
    ctx.closePath();
    ctx.fill();

    // Neck shadow under chin
    ctx.fillStyle = "rgba(180, 110, 80, 0.25)";
    ctx.beginPath();
    ctx.ellipse(cx, cy + 52, 22, 10, 0, 0, Math.PI);
    ctx.fill();

    // 5. Hair (Back layer)
    ctx.fillStyle = "#2d1b11";
    ctx.beginPath();
    ctx.ellipse(cx, cy + 8, 68, 72, 0, 0, Math.PI * 2);
    ctx.fill();

    // 6. Face Head Contour
    const faceGrad = ctx.createLinearGradient(cx - 45, cy - 40, cx + 45, cy + 50);
    faceGrad.addColorStop(0, "#fad6be");
    faceGrad.addColorStop(0.7, "#f7c7a8");
    faceGrad.addColorStop(1, "#ebae8a");
    ctx.fillStyle = faceGrad;

    ctx.beginPath();
    ctx.moveTo(cx - 48, cy - 10);
    ctx.quadraticCurveTo(cx - 50, cy + 30, cx - 26, cy + 54);
    ctx.quadraticCurveTo(cx, cy + 62, cx + 26, cy + 54);
    ctx.quadraticCurveTo(cx + 50, cy + 30, cx + 48, cy - 10);
    ctx.quadraticCurveTo(cx + 46, cy - 56, cx, cy - 58);
    ctx.quadraticCurveTo(cx - 46, cy - 56, cx - 48, cy - 10);
    ctx.closePath();
    ctx.fill();

    // Cheekbone subtle blush
    ctx.fillStyle = "rgba(235, 120, 110, 0.16)";
    ctx.beginPath();
    ctx.arc(cx - 28, cy + 15, 12, 0, Math.PI * 2);
    ctx.arc(cx + 28, cy + 15, 12, 0, Math.PI * 2);
    ctx.fill();

    // 7. Eyebrows
    ctx.strokeStyle = "#382317";
    ctx.lineWidth = 2.8;
    ctx.lineCap = "round";

    // Eyebrow slight raise if analyzing
    const browOffset = (personaState === "ANALYZING") ? -2 : 0;
    ctx.beginPath();
    ctx.moveTo(cx - 38, cy - 18 + browOffset);
    ctx.quadraticCurveTo(cx - 24, cy - 24 + browOffset, cx - 12, cy - 19);
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(cx + 12, cy - 19);
    ctx.quadraticCurveTo(cx + 24, cy - 24 + browOffset, cx + 38, cy - 18 + browOffset);
    ctx.stroke();

    // 8. Eyes & Natural Eyelid Blinking
    const eyeSpacing = 22;
    const eyeY = cy - 8;

    [-1, 1].forEach(side => {
        const eyeX = cx + (side * eyeSpacing);

        // Sclera (Eye White)
        ctx.fillStyle = "#ffffff";
        ctx.beginPath();
        ctx.ellipse(eyeX, eyeY, 11, 7, 0, 0, Math.PI * 2);
        ctx.fill();

        // Iris
        const irisX = eyeX + gazeDriftX;
        const irisY = eyeY + gazeDriftY;
        const irisGrad = ctx.createRadialGradient(irisX, irisY, 1, irisX, irisY, 5.5);
        irisGrad.addColorStop(0, "#38bdf8");
        irisGrad.addColorStop(0.6, "#0284c7");
        irisGrad.addColorStop(1, "#0c4a6e");
        ctx.fillStyle = irisGrad;
        ctx.beginPath();
        ctx.arc(irisX, irisY, 5.5, 0, Math.PI * 2);
        ctx.fill();

        // Pupil
        ctx.fillStyle = "#030712";
        ctx.beginPath();
        ctx.arc(irisX, irisY, 2.8, 0, Math.PI * 2);
        ctx.fill();

        // Specular Shine Reflection (Catchlight)
        ctx.fillStyle = "rgba(255, 255, 255, 0.95)";
        ctx.beginPath();
        ctx.arc(irisX - 1.8, irisY - 1.8, 1.4, 0, Math.PI * 2);
        ctx.fill();

        // Natural Eyelid (Blink closure)
        if (personaBlinkPhase > 0) {
            ctx.fillStyle = "#f3c19f";
            ctx.beginPath();
            ctx.rect(eyeX - 12, eyeY - 8, 24, 16 * personaBlinkPhase);
            ctx.fill();

            // Eyelash line
            ctx.strokeStyle = "#27170e";
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            ctx.moveTo(eyeX - 11, eyeY - 8 + (16 * personaBlinkPhase));
            ctx.lineTo(eyeX + 11, eyeY - 8 + (16 * personaBlinkPhase));
            ctx.stroke();
        } else {
            // Eyelash contour
            ctx.strokeStyle = "#382317";
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            ctx.moveTo(eyeX - 11, eyeY - 2);
            ctx.quadraticCurveTo(eyeX, eyeY - 8, eyeX + 11, eyeY - 2);
            ctx.stroke();
        }
    });

    // 9. Nose
    ctx.strokeStyle = "#d69874";
    ctx.lineWidth = 1.8;
    ctx.beginPath();
    ctx.moveTo(cx - 2, cy - 6);
    ctx.lineTo(cx, cy + 14);
    ctx.quadraticCurveTo(cx - 5, cy + 18, cx - 6, cy + 17);
    ctx.moveTo(cx, cy + 14);
    ctx.quadraticCurveTo(cx + 5, cy + 18, cx + 6, cy + 17);
    ctx.stroke();

    // 10. Viseme-Synchronized Mouth
    const mouthY = cy + 34;

    if (personaState === "SPEAKING") {
        // Active mouth animation
        const openAmp = Math.max(0.2, visemeMouthOpening);
        let mouthW = 16;
        let mouthH = openAmp * 12;

        if (currentViseme === "open_o") {
            mouthW = 12;
            mouthH = openAmp * 16;
        } else if (currentViseme === "wide_e") {
            mouthW = 20;
            mouthH = openAmp * 9;
        } else if (currentViseme === "closed_m") {
            mouthW = 14;
            mouthH = 1;
        }

        // Oral cavity interior
        ctx.fillStyle = "#701a1e";
        ctx.beginPath();
        ctx.ellipse(cx, mouthY, mouthW, Math.max(1, mouthH), 0, 0, Math.PI * 2);
        ctx.fill();

        // Upper Teeth
        if (mouthH > 4) {
            ctx.fillStyle = "#ffffff";
            ctx.beginPath();
            ctx.ellipse(cx, mouthY - (mouthH * 0.45), mouthW * 0.7, 3, 0, 0, Math.PI);
            ctx.fill();
        }

        // Upper lip
        ctx.strokeStyle = "#b5534c";
        ctx.lineWidth = 2.4;
        ctx.beginPath();
        ctx.moveTo(cx - mouthW - 2, mouthY);
        ctx.quadraticCurveTo(cx, mouthY - mouthH - 2, cx + mouthW + 2, mouthY);
        ctx.stroke();

        // Lower lip
        ctx.beginPath();
        ctx.moveTo(cx - mouthW - 2, mouthY);
        ctx.quadraticCurveTo(cx, mouthY + mouthH + 3, cx + mouthW + 2, mouthY);
        ctx.stroke();

    } else {
        // Resting gentle professional smile
        ctx.strokeStyle = "#c05f58";
        ctx.lineWidth = 2.4;
        ctx.beginPath();
        ctx.moveTo(cx - 15, mouthY);
        ctx.quadraticCurveTo(cx, mouthY + 5, cx + 15, mouthY);
        ctx.stroke();

        // Lower lip shadow
        ctx.strokeStyle = "rgba(180, 95, 80, 0.3)";
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(cx, mouthY + 6, 7, 0.2, Math.PI - 0.2);
        ctx.stroke();
    }

    // 11. Front Styled Hair (Bangs & Framing)
    ctx.fillStyle = "#3e2417";
    ctx.beginPath();
    ctx.moveTo(cx - 52, cy - 10);
    ctx.quadraticCurveTo(cx - 40, cy - 65, cx, cy - 64);
    ctx.quadraticCurveTo(cx + 42, cy - 65, cx + 52, cy - 10);
    ctx.quadraticCurveTo(cx + 56, cy + 30, cx + 46, cy + 46);
    ctx.lineTo(cx + 36, cy + 10);
    ctx.quadraticCurveTo(cx + 10, cy - 40, cx - 18, cy - 35);
    ctx.quadraticCurveTo(cx - 44, cy + 20, cx - 46, cy + 46);
    ctx.quadraticCurveTo(cx - 56, cy + 30, cx - 52, cy - 10);
    ctx.closePath();
    ctx.fill();

    // Hair highlights
    ctx.strokeStyle = "rgba(150, 95, 60, 0.4)";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(cx - 30, cy - 50);
    ctx.quadraticCurveTo(cx, cy - 58, cx + 28, cy - 48);
    ctx.stroke();

    ctx.restore();
}

