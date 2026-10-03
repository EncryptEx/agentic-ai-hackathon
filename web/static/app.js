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
            }
        });
    });
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
                        <span class="badge badge-fraud">${alt.severity}</span>
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
                        <span class="badge badge-${alt.severity}">${alt.severity}</span>
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
}

function initSimulator() {
    const simBtn = document.getElementById("run-simulation-btn");
    if (!simBtn) return;

    simBtn.addEventListener("click", async () => {
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
            transactions: []
        };

        const scenario = document.getElementById("sim-scenario").value;
        const now = new Date();

        if (scenario === "ATO") {
            payload.transactions.push({
                transaction_id: "SIM-ATO-LEGIT",
                timestamp: new Date(now.getTime() - 40 * 60000).toISOString(),
                transaction_type: "POS_PURCHASE",
                direction: "OUTBOUND",
                amount_usd: 28.50,
                counterparty_name: "Local Cafe Store",
                counterparty_country: payload.customer.residence_country,
                counterparty_category: "RETAILER",
                channel: "POS_TERMINAL"
            });
            payload.transactions.push({
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
                reference_narrative: "Urgent wire drain"
            });
        } else if (scenario === "CARD_TEST") {
            payload.transactions.push({
                transaction_id: "SIM-CARD-P1",
                timestamp: new Date(now.getTime() - 15 * 60000).toISOString(),
                transaction_type: "ONLINE_PURCHASE",
                direction: "OUTBOUND",
                amount_usd: 0.89,
                counterparty_name: "Trial Stream Service",
                counterparty_country: "US",
                counterparty_category: "RETAILER",
                channel: "WEB_PORTAL",
                card_entry_mode: "CNP_ECOMMERCE"
            });
            payload.transactions.push({
                transaction_id: "SIM-CARD-P2",
                timestamp: new Date(now.getTime() - 10 * 60000).toISOString(),
                transaction_type: "ONLINE_PURCHASE",
                direction: "OUTBOUND",
                amount_usd: 1.20,
                counterparty_name: "Trial Content Service",
                counterparty_country: "US",
                counterparty_category: "RETAILER",
                channel: "WEB_PORTAL",
                card_entry_mode: "CNP_ECOMMERCE"
            });
            payload.transactions.push({
                transaction_id: "SIM-CARD-DRAIN",
                timestamp: now.toISOString(),
                transaction_type: "ONLINE_PURCHASE",
                direction: "OUTBOUND",
                amount_usd: 3450.0,
                counterparty_name: "Luxury Electronics Direct",
                counterparty_country: "HK",
                counterparty_category: "RETAILER",
                channel: "WEB_PORTAL",
                card_entry_mode: "CNP_ECOMMERCE",
                auth_status: "DECLINED_SUSPECTED_FRAUD"
            });
        } else if (scenario === "STRUCTURING") {
            for (let i = 0; i < 4; i++) {
                payload.transactions.push({
                    transaction_id: `SIM-STRUC-${i+1}`,
                    timestamp: new Date(now.getTime() - (i * 2 * 24 * 3600 * 1000)).toISOString(),
                    transaction_type: "CASH_DEPOSIT",
                    direction: "INBOUND",
                    amount_usd: 9400.0 + (i * 100),
                    counterparty_name: "Branch Teller Desk",
                    counterparty_country: payload.customer.residence_country,
                    counterparty_category: "ATM_BRANCH",
                    channel: "BRANCH_TELLER",
                    reference_narrative: "Personal savings cash deposit"
                });
            }
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
