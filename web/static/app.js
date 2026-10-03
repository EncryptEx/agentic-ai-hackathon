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
    initGoogleVoiceCopilot();
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

        <!-- Autonomous Multi-Agent AI Investigation Suite -->
        <div style="background: linear-gradient(135deg, rgba(37, 99, 235, 0.14) 0%, rgba(217, 70, 239, 0.14) 100%); border: 1px solid var(--accent-blue); padding: 16px 20px; border-radius: 8px;">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
                <div>
                    <h3 style="font-size: 14px; font-weight: 700; color: var(--text-primary); display: flex; align-items: center; gap: 8px;">
                        <span>🤖</span> Autonomous Multi-Agent Investigation Suite
                    </h3>
                    <p style="color: var(--text-secondary); font-size: 12px; margin-top: 3px;">
                        Deploys Customer, Transaction, Fraud, Ownership, and Risk specialist agents with dialectic debate and voice interrogation.
                    </p>
                </div>
                <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                    <button id="btn-run-agent-investigate" class="btn-magenta" style="padding: 9px 16px; font-size: 13px; font-weight: 700; cursor: pointer; display: flex; align-items: center; gap: 6px;">
                        <span>⚡</span> Run Investigation
                    </button>
                    <button id="btn-google-voice-call" style="background: #0891b2; color: #fff; border: 1px solid #06b6d4; border-radius: 6px; padding: 9px 16px; font-size: 13px; font-weight: 700; cursor: pointer; display: flex; align-items: center; gap: 6px;">
                        <span>🎙️</span> Google Voice Interrogation
                    </button>
                </div>
            </div>

            <!-- Google Voice Interrogation Interactive Modal/Panel -->
            <div id="voice-interrogation-panel" style="display: none; margin-top: 16px; background: linear-gradient(135deg, rgba(8,145,178,0.12), rgba(15,23,42,0.95)); border: 1px solid #06b6d4; border-radius: 8px; padding: 18px;">
                <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(6,182,212,0.3); padding-bottom: 10px; margin-bottom: 12px;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span style="font-size: 18px;">🎙️</span>
                        <div>
                            <div style="font-size: 13px; font-weight: 700; color: #67e8f9; text-transform: uppercase; font-family: monospace;">Google Voice Outcall & Testimony Console</div>
                            <div style="font-size: 11px; color: var(--text-muted);">Out-of-band verification via Google Speech Synthesis (TTS) & Google Web Speech STT</div>
                        </div>
                    </div>
                    <span id="drawer-voice-status" style="font-size: 11px; font-family: monospace; color: #22d3ee; font-weight: 700; background: rgba(6,182,212,0.2); padding: 3px 8px; border-radius: 4px; border: 1px solid #06b6d4;">READY FOR CALL</span>
                </div>

                <div style="background: rgba(0,0,0,0.4); border: 1px solid rgba(255,255,255,0.08); padding: 12px; border-radius: 6px; margin-bottom: 12px; font-size: 12px; line-height: 1.5;">
                    <div style="font-weight: 700; color: #94a3b8; font-family: monospace; font-size: 11px; text-transform: uppercase; margin-bottom: 4px;">Diagnostic Outcall Challenge:</div>
                    <div id="drawer-voice-question" style="color: #f1f5f9; font-style: italic;">
                        "Valiant Bank Fraud Prevention: We detected high-velocity outbound transfers departing your account. Are you currently speaking with someone claiming to be police or fraud staff instructing you to move money to a safe account?"
                    </div>
                </div>

                <div style="display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px;">
                    <button id="btn-drawer-tts" style="flex: 1; min-width: 140px; background: rgba(8,145,178,0.3); hover: background: rgba(8,145,178,0.5); border: 1px solid #0891b2; color: #67e8f9; padding: 8px 12px; border-radius: 6px; font-size: 12px; font-weight: 600; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 6px;">
                        <span>🔊</span> Speak Challenge (TTS)
                    </button>
                    <button id="btn-drawer-mic" style="flex: 1; min-width: 140px; background: rgba(225,29,72,0.25); border: 1px solid #f43f5e; color: #fda4af; padding: 8px 12px; border-radius: 6px; font-size: 12px; font-weight: 600; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 6px;">
                        <span id="drawer-mic-icon">🎙️</span> <span id="drawer-mic-label">Record Voice Testimony</span>
                    </button>
                    <button id="btn-drawer-preset" style="flex: 1; min-width: 140px; background: rgba(99,102,241,0.25); border: 1px solid #6366f1; color: #c7d2fe; padding: 8px 12px; border-radius: 6px; font-size: 12px; font-weight: 600; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 6px;">
                        <span>▶️</span> Play Victim Audio (1-Click)
                    </button>
                </div>

                <div id="drawer-transcript-box" style="background: rgba(0,0,0,0.6); border: 1px solid rgba(6,182,212,0.3); border-radius: 6px; padding: 12px; font-size: 12px; font-family: monospace; color: #cbd5e1; min-height: 48px; display: flex; justify-content: space-between; align-items: center;">
                    <span id="drawer-transcript-text" style="color: #94a3b8; font-style: italic;">Awaiting customer speech testimony or 1-click audio simulation...</span>
                    <button id="btn-drawer-feed-voice" style="display: none; background: #0284c7; color: #fff; border: none; padding: 6px 12px; border-radius: 4px; font-weight: 700; cursor: pointer; font-size: 11px;">
                        ⚡ Ingest to Jev & Debate
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

    // Attach Google Voice Interrogation listeners
    const voiceBtn = document.getElementById("btn-google-voice-call");
    const voicePanel = document.getElementById("voice-interrogation-panel");
    const btnTts = document.getElementById("btn-drawer-tts");
    const btnMic = document.getElementById("btn-drawer-mic");
    const btnPreset = document.getElementById("btn-drawer-preset");
    const btnFeed = document.getElementById("btn-drawer-feed-voice");
    const txtBox = document.getElementById("drawer-transcript-text");
    const statusLabel = document.getElementById("drawer-voice-status");
    const micLabel = document.getElementById("drawer-mic-label");
    const micIcon = document.getElementById("drawer-mic-icon");

    if (voiceBtn && voicePanel) {
        voiceBtn.addEventListener("click", () => {
            voicePanel.style.display = voicePanel.style.display === "none" ? "block" : "none";
            if (voicePanel.style.display === "block") {
                voicePanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
            }
        });
    }

    let drawerTranscript = "";
    let drawerIsRecording = false;

    if (btnTts) {
        btnTts.addEventListener("click", () => {
            const q = document.getElementById("drawer-voice-question")?.innerText || "Valiant Bank Fraud Prevention Outcall Challenge.";
            if ('speechSynthesis' in window) {
                window.speechSynthesis.cancel();
                const u = new SpeechSynthesisUtterance(q);
                u.rate = 1.0;
                u.pitch = 1.05;
                u.lang = "en-US";
                u.onstart = () => { if (statusLabel) statusLabel.textContent = "SPEAKING CHALLENGE (GOOGLE TTS)..."; };
                u.onend = () => { if (statusLabel) statusLabel.textContent = "CALL CONNECTED • AWAITING TESTIMONY"; };
                window.speechSynthesis.speak(u);
            }
        });
    }

    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    let drawerRec = null;
    if (SpeechRec) {
        drawerRec = new SpeechRec();
        drawerRec.continuous = false;
        drawerRec.interimResults = true;
        drawerRec.lang = "en-US";

        drawerRec.onstart = () => {
            drawerIsRecording = true;
            if (micLabel) micLabel.textContent = "Listening to Customer...";
            if (micIcon) micIcon.textContent = "🔴";
            if (statusLabel) statusLabel.textContent = "RECORDING (GOOGLE SPEECH STT)...";
            if (txtBox) txtBox.innerHTML = `<span style="color: #fda4af;">Listening... Speak now.</span>`;
        };

        drawerRec.onresult = (ev) => {
            let interim = "";
            for (let i = ev.resultIndex; i < ev.results.length; ++i) {
                if (ev.results[i].isFinal) drawerTranscript += ev.results[i][0].transcript;
                else interim += ev.results[i][0].transcript;
            }
            if (txtBox) txtBox.innerHTML = `<strong>Voice Transcript (Google Speech):</strong> "${drawerTranscript || interim}"`;
            if (btnFeed) btnFeed.style.display = "block";
        };

        drawerRec.onend = () => {
            drawerIsRecording = false;
            if (micLabel) micLabel.textContent = "Record Voice Testimony";
            if (micIcon) micIcon.textContent = "🎙️";
            if (statusLabel) statusLabel.textContent = "TESTIMONY RECORDED";
            if (drawerTranscript && btnFeed) btnFeed.style.display = "block";
        };

        if (btnMic) {
            btnMic.addEventListener("click", () => {
                if (drawerIsRecording) {
                    drawerRec.stop();
                } else {
                    drawerTranscript = "";
                    try { drawerRec.start(); } catch (e) { console.error(e); }
                }
            });
        }
    }

    if (btnPreset) {
        btnPreset.addEventListener("click", () => {
            const preset = "Yes, someone calling from the police told me my account was compromised and ordered me to transfer funds to this liquidation escrow account immediately!";
            drawerTranscript = preset;
            if ('speechSynthesis' in window) {
                window.speechSynthesis.cancel();
                const u = new SpeechSynthesisUtterance(preset);
                u.rate = 1.05;
                window.speechSynthesis.speak(u);
            }
            if (txtBox) txtBox.innerHTML = `<strong>Victim Audio Transcript:</strong> "${preset}"`;
            if (btnFeed) {
                btnFeed.style.display = "block";
                btnFeed.click();
            }
        });
    }

    if (btnFeed) {
        btnFeed.addEventListener("click", async () => {
            if (!drawerTranscript) return;
            btnFeed.disabled = true;
            btnFeed.textContent = "⚡ Ingesting #E07...";
            try {
                const res = await fetch("/api/voice/testify", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        customer_id: customer.customer_id,
                        transcript: drawerTranscript,
                        confidence: 0.98,
                        audio_duration_sec: 4.5
                    })
                });
                const data = await res.json();
                if (txtBox) {
                    txtBox.innerHTML = `✅ <span style="color: #4ade80; font-weight: 700;">Evidence #${data.evidence_id} Ingested. Jev Reasoner & Tribunal Overrode Money Mule Designation ➔ Escrow Freeze Active.</span>`;
                }
                btnFeed.style.display = "none";
                if (agentBtn) agentBtn.click();
            } catch (err) {
                if (txtBox) txtBox.innerHTML = `<span style="color: #f87171;">Error: ${err.message}</span>`;
            } finally {
                btnFeed.disabled = false;
                btnFeed.textContent = "⚡ Ingest to Jev & Debate";
            }
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
    container.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; padding-bottom: 10px; border-bottom: 1px solid var(--border-color);">
            <div style="display: flex; align-items: center; gap: 10px;">
                <span class="badge badge-${data.risk_tier || 'HIGH'}" style="font-size: 12px;">${data.risk_tier || 'CRITICAL'} CASE DOSSIER</span>
                <span style="font-size: 12px; color: var(--text-secondary);">FRAML Score: <strong>${(data.composite_score || 0).toFixed(1)}/100</strong></span>
            </div>
            <button id="btn-copy-report" class="btn-pick-test" style="display: flex; align-items: center; gap: 6px;">
                <span>📋</span> Copy 11-Section Dossier
            </button>
        </div>
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; font-size: 13px;">
            ${formatMarkdown(reportText)}
        </div>
    `;

    const copyBtn = document.getElementById("btn-copy-report");
    if (copyBtn) {
        copyBtn.addEventListener("click", () => {
            navigator.clipboard.writeText(reportText).then(() => {
                copyBtn.innerHTML = `<span>✓</span> Dossier Copied!`;
                setTimeout(() => { copyBtn.innerHTML = `<span>📋</span> Copy 11-Section Dossier`; }, 2000);
            }).catch(() => {
                alert("Failed to copy report to clipboard");
            });
        });
    }
}

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

// ---------------------------------------------------------
// ---------------------------------------------------------
// Google Voice AI Copilot (Dashboard Integrated + Floating Two-Way Voice Dialogue)
// ---------------------------------------------------------
function initGoogleVoiceCopilot() {
    // 1. Floating Modal Elements
    const launcher = document.getElementById("btn-open-voice-copilot");
    const modal = document.getElementById("voice-copilot-modal");
    const closeBtn = document.getElementById("btn-close-voice-copilot");
    const micBtn = document.getElementById("btn-copilot-mic");
    const micIcon = document.getElementById("copilot-mic-icon");
    const inputEl = document.getElementById("copilot-text-input");
    const sendBtn = document.getElementById("btn-copilot-send");
    const stream = document.getElementById("voice-dialogue-stream");
    const waveText = document.getElementById("voice-wave-text");
    const waveDot = document.getElementById("voice-wave-dot");
    const statusInd = document.getElementById("voice-status-indicator");
    const chkAutoTts = document.getElementById("chk-auto-tts");
    const modalChips = document.querySelectorAll(".voice-chip");

    // 2. Dashboard Embedded Elements
    const dashMicBtn = document.getElementById("btn-dash-mic");
    const dashMicIcon = document.getElementById("dash-mic-icon");
    const dashMicText = document.getElementById("dash-mic-text");
    const dashInput = document.getElementById("dash-voice-input");
    const dashSendBtn = document.getElementById("btn-dash-send");
    const dashWaveDot = document.getElementById("dash-wave-dot");
    const dashWaveText = document.getElementById("dash-wave-text");
    const dashTtsCheck = document.getElementById("dash-voice-tts-check");
    const dashChips = document.querySelectorAll(".dash-chip");
    const dashFeed = document.getElementById("dash-voice-feed");
    const dashLatestMsg = document.getElementById("dash-voice-latest-msg");

    // Toggle Floating Modal
    if (launcher && modal) {
        launcher.addEventListener("click", () => {
            const isHidden = modal.style.display === "none" || !modal.style.display;
            modal.style.display = isHidden ? "flex" : "none";
            if (isHidden && inputEl) inputEl.focus();
        });
    }

    if (closeBtn && modal) {
        closeBtn.addEventListener("click", () => {
            modal.style.display = "none";
            if ('speechSynthesis' in window) window.speechSynthesis.cancel();
        });
    }

    // Markdown / text formatter
    function formatAiText(text) {
        return text
            .replace(/^### (.*$)/gim, '<div style="font-size: 13px; font-weight: 700; color: #38bdf8; margin-bottom: 6px;">$1</div>')
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/`([^`]+)`/g, '<code style="background: rgba(0,0,0,0.5); color: #67e8f9; padding: 1px 4px; border-radius: 3px; font-family: monospace;">$1</code>')
            .replace(/\n/g, '<br/>');
    }

    // Helper: append to floating stream
    function appendModalMessage(sender, text, isAi = false) {
        if (!stream) return;
        const msg = document.createElement("div");
        msg.className = `voice-msg ${isAi ? 'ai-msg' : 'user-msg'}`;
        if (isAi) {
            msg.style.cssText = "align-self: flex-start; max-width: 90%; background: #0f172a; border: 1px solid #1e293b; border-radius: 12px 12px 12px 2px; padding: 10px 14px; color: #e2e8f0; font-size: 12px; line-height: 1.5;";
            msg.innerHTML = `
                <div style="font-size: 10px; font-family: monospace; color: #38bdf8; margin-bottom: 4px; font-weight: 700;">🤖 VALIANT AI INVESTIGATOR (VOICE COPILOT)</div>
                <div>${formatAiText(text)}</div>
            `;
        } else {
            msg.style.cssText = "align-self: flex-end; max-width: 85%; background: linear-gradient(135deg, #0284c7, #2563eb); border-radius: 12px 12px 2px 12px; padding: 10px 14px; color: #fff; font-size: 12px; line-height: 1.4; box-shadow: 0 4px 12px rgba(2,132,199,0.3);";
            msg.innerHTML = `
                <div style="font-size: 9px; font-family: monospace; color: rgba(255,255,255,0.8); margin-bottom: 2px;">👤 SPOKEN INQUIRY</div>
                <div>${text}</div>
            `;
        }
        stream.appendChild(msg);
        stream.scrollTop = stream.scrollHeight;
    }

    // Helper: update dashboard embedded feed
    function updateDashboardFeed(query, reply) {
        if (!dashFeed || !dashLatestMsg) return;
        dashFeed.style.display = "block";
        dashLatestMsg.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1e293b; padding-bottom: 6px; margin-bottom: 8px;">
                <span style="font-family: monospace; font-size: 11px; color: #38bdf8; font-weight: 700;">👤 USER INQUIRY: "${query}"</span>
                <span style="font-size: 10px; color: #94a3b8; font-family: monospace;">VOICE COGNITION ENGINE</span>
            </div>
            <div style="color: #f1f5f9; font-size: 12px; line-height: 1.6;">
                ${formatAiText(reply)}
            </div>
        `;
    }

    // Waveform visualizers
    let barInterval = null;
    function startWaveform(color = "#06b6d4") {
        const vBars = document.querySelectorAll(".v-bar, .d-bar");
        if (barInterval) clearInterval(barInterval);
        barInterval = setInterval(() => {
            vBars.forEach(b => {
                const h = Math.floor(Math.random() * 14) + 4;
                b.style.height = `${h}px`;
                b.style.background = color;
            });
        }, 120);
    }

    function stopWaveform() {
        if (barInterval) clearInterval(barInterval);
        barInterval = null;
        const vBars = document.querySelectorAll(".v-bar, .d-bar");
        vBars.forEach((b, idx) => {
            b.style.height = `${[6, 12, 8, 16, 9][idx % 5]}px`;
            b.style.background = "#06b6d4";
        });
    }

    // Google TTS Voice Output
    function speakAI(text) {
        const ttsEnabled = (chkAutoTts && chkAutoTts.checked) || (dashTtsCheck && dashTtsCheck.checked);
        if (!('speechSynthesis' in window) || !ttsEnabled) return;

        window.speechSynthesis.cancel();
        const u = new SpeechSynthesisUtterance(text);
        u.rate = 1.05;
        u.pitch = 1.02;
        u.lang = "en-US";

        u.onstart = () => {
            if (statusInd) {
                statusInd.textContent = "SPEAKING (GOOGLE TTS)";
                statusInd.style.color = "#38bdf8";
                statusInd.style.background = "rgba(56,189,248,0.2)";
            }
            if (waveText) waveText.textContent = "Agent speaking aloud (Google SpeechSynthesis)...";
            if (waveDot) waveDot.style.background = "#38bdf8";
            if (dashWaveText) dashWaveText.textContent = "Agent speaking aloud (Google TTS)...";
            if (dashWaveDot) dashWaveDot.style.background = "#38bdf8";
            startWaveform("#38bdf8");
        };

        u.onend = () => {
            if (statusInd) {
                statusInd.textContent = "STANDBY";
                statusInd.style.color = "#4ade80";
                statusInd.style.background = "rgba(34,197,94,0.2)";
            }
            if (waveText) waveText.textContent = "Ready. Tap mic or ask question.";
            if (waveDot) waveDot.style.background = "#22c55e";
            if (dashWaveText) dashWaveText.textContent = "Voice Standby";
            if (dashWaveDot) dashWaveDot.style.background = "#22c55e";
            stopWaveform();
        };

        window.speechSynthesis.speak(u);
    }

    // Unified Submit dialogue query
    async function sendQuery(queryText) {
        if (!queryText || !queryText.trim()) return;
        appendModalMessage("user", queryText, false);
        if (inputEl) inputEl.value = "";
        if (dashInput) dashInput.value = "";

        if (statusInd) {
            statusInd.textContent = "THINKING (MULTI-AGENT)...";
            statusInd.style.color = "#fbbf24";
            statusInd.style.background = "rgba(251,191,36,0.2)";
        }
        if (waveText) waveText.textContent = "Orchestrator deliberating across dialectic tribunal...";
        if (waveDot) waveDot.style.background = "#fbbf24";
        if (dashWaveText) dashWaveText.textContent = "Multi-agent tribunal deliberating...";
        if (dashWaveDot) dashWaveDot.style.background = "#fbbf24";
        startWaveform("#fbbf24");

        try {
            const res = await fetch("/api/voice/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: queryText })
            });
            const data = await res.json();
            stopWaveform();

            appendModalMessage("ai", data.reply, true);
            updateDashboardFeed(queryText, data.reply);

            // Execute interactive dashboard actions!
            if (data.action === "OPEN_CUSTOMER" && data.customer_id) {
                if (typeof openDossier === "function") {
                    openDossier(data.customer_id);
                } else if (typeof openCustomerDrawer === "function") {
                    openCustomerDrawer(data.customer_id);
                }
            } else if (data.action === "FILTER_TIER") {
                const tier = data.customer_id || "CRITICAL";
                const filterBtn = document.querySelector(`.filter-btn[data-tier="${tier}"]`);
                if (filterBtn) filterBtn.click();
            } else if (data.action === "SWITCH_TAB" && data.customer_id) {
                const navTab = document.querySelector(`.nav-tab[data-target="${data.customer_id}"]`);
                if (navTab) navTab.click();
            }

            // Speak response aloud via Google TTS
            if (data.spoken_reply) {
                speakAI(data.spoken_reply);
            }
        } catch (err) {
            stopWaveform();
            appendModalMessage("ai", `Error contacting agent: ${err.message}`, true);
        }
    }

    // Modal Inputs
    if (sendBtn) sendBtn.addEventListener("click", () => sendQuery(inputEl?.value));
    if (inputEl) inputEl.addEventListener("keydown", (e) => { if (e.key === "Enter") sendQuery(inputEl.value); });
    modalChips.forEach(chip => {
        chip.addEventListener("click", () => {
            const prompt = chip.getAttribute("data-prompt");
            if (prompt) sendQuery(prompt);
        });
    });

    // Dashboard Inputs
    if (dashSendBtn) dashSendBtn.addEventListener("click", () => sendQuery(dashInput?.value));
    if (dashInput) dashInput.addEventListener("keydown", (e) => { if (e.key === "Enter") sendQuery(dashInput.value); });
    dashChips.forEach(chip => {
        chip.addEventListener("click", () => {
            const q = chip.getAttribute("data-q");
            if (q) sendQuery(q);
        });
    });

    // Google Speech Recognition (STT Voice Input)
    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    let rec = null;
    let isListening = false;
    let activeSource = null; // 'modal' or 'dashboard'

    if (SpeechRec) {
        rec = new SpeechRec();
        rec.continuous = false;
        rec.interimResults = true;
        rec.lang = "en-US";

        rec.onstart = () => {
            isListening = true;
            if (activeSource === "modal" && micBtn) {
                micBtn.style.background = "#22c55e";
                micBtn.style.boxShadow = "0 0 20px rgba(34,197,94,0.6)";
                if (micIcon) micIcon.textContent = "🔴";
            }
            if (activeSource === "dashboard" && dashMicBtn) {
                dashMicBtn.style.background = "#22c55e";
                dashMicBtn.style.boxShadow = "0 0 20px rgba(34,197,94,0.6)";
                if (dashMicIcon) dashMicIcon.textContent = "🔴";
                if (dashMicText) dashMicText.textContent = "Listening (Speak Now)...";
            }
            if (statusInd) {
                statusInd.textContent = "LISTENING (SPEAK NOW)...";
                statusInd.style.color = "#f43f5e";
                statusInd.style.background = "rgba(244,63,94,0.2)";
            }
            if (waveText) waveText.textContent = "Listening to your voice (Google Speech STT)...";
            if (waveDot) waveDot.style.background = "#f43f5e";
            if (dashWaveText) dashWaveText.textContent = "Listening (Google Speech STT)...";
            if (dashWaveDot) dashWaveDot.style.background = "#f43f5e";
            startWaveform("#f43f5e");
        };

        rec.onresult = (ev) => {
            let transcript = "";
            for (let i = ev.resultIndex; i < ev.results.length; ++i) {
                transcript += ev.results[i][0].transcript;
            }
            if (activeSource === "modal" && inputEl) inputEl.value = transcript;
            if (activeSource === "dashboard" && dashInput) dashInput.value = transcript;
            if (waveText) waveText.textContent = `Heard: "${transcript}"`;
            if (dashWaveText) dashWaveText.textContent = `Heard: "${transcript}"`;
        };

        rec.onend = () => {
            isListening = false;
            if (micBtn) {
                micBtn.style.background = "#e11d48";
                micBtn.style.boxShadow = "0 0 12px rgba(225,29,72,0.4)";
                if (micIcon) micIcon.textContent = "🎙️";
            }
            if (dashMicBtn) {
                dashMicBtn.style.background = "linear-gradient(135deg, #e11d48, #be123c)";
                dashMicBtn.style.boxShadow = "0 0 15px rgba(225,29,72,0.35)";
                if (dashMicIcon) dashMicIcon.textContent = "🎙️";
                if (dashMicText) dashMicText.textContent = "Click to Speak Question";
            }
            stopWaveform();

            const finalQuery = activeSource === "modal" ? inputEl?.value?.trim() : dashInput?.value?.trim();
            if (finalQuery) {
                sendQuery(finalQuery);
            } else {
                if (statusInd) {
                    statusInd.textContent = "STANDBY";
                    statusInd.style.color = "#4ade80";
                    statusInd.style.background = "rgba(34,197,94,0.2)";
                }
                if (waveText) waveText.textContent = "Ready. Tap mic or ask question.";
                if (waveDot) waveDot.style.background = "#22c55e";
                if (dashWaveText) dashWaveText.textContent = "Voice Standby";
                if (dashWaveDot) dashWaveDot.style.background = "#22c55e";
            }
        };

        if (micBtn) {
            micBtn.addEventListener("click", () => {
                if (isListening) {
                    rec.stop();
                } else {
                    activeSource = "modal";
                    if (inputEl) inputEl.value = "";
                    try { rec.start(); } catch (e) { console.error(e); }
                }
            });
        }

        if (dashMicBtn) {
            dashMicBtn.addEventListener("click", () => {
                if (isListening) {
                    rec.stop();
                } else {
                    activeSource = "dashboard";
                    if (dashInput) dashInput.value = "";
                    try { rec.start(); } catch (e) { console.error(e); }
                }
            });
        }
    } else {
        if (micBtn) micBtn.title = "Google Speech Recognition not supported in this browser. Please use text input or prompt chips.";
        if (dashMicBtn) dashMicBtn.title = "Google Speech Recognition not supported in this browser. Please use text input or prompt chips.";
    }
}

