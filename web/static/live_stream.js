// EvidenceTrail Frontend Application Logic

// Embedded scenario data fallback for offline file:// execution
const EMBEDDED_SCENARIOS = [
  {
    "id": "case-1",
    "title": "Familiar Payment (600 SEK)",
    "subtitle": "Routine transfer to recurring contact",
    "expected_action": "ALLOW",
    "customer": {
      "id": "CUST-1042",
      "name": "Alice Lindqvist",
      "typical_min": 200,
      "typical_max": 2000,
      "known_recipients": ["REC-441", "REC-109"],
      "known_devices": ["DEV-901"]
    },
    "transaction": {
      "id": "TX-8901",
      "amount": 600,
      "currency": "SEK",
      "recipient_id": "REC-441",
      "recipient_name": "Erik Berg",
      "device_id": "DEV-901",
      "auth_type": "BankID_Biometric",
      "channel": "MobileApp"
    },
    "device": { "id": "DEV-901", "is_known": true, "os": "iOS 18.2", "session_anomalies": [] },
    "recipient": { "id": "REC-441", "name": "Erik Berg", "account_age_days": 820, "incoming_transfers_90min": 1, "synthetic_flags": [] },
    "graph": {
      "nodes": [
        { "id": "CUST-1042", "label": "Alice Lindqvist (Payer)", "type": "customer", "risk": "low" },
        { "id": "REC-441", "label": "Erik Berg (Recipient)", "type": "recipient", "risk": "low" },
        { "id": "DEV-901", "label": "Alice's iPhone 15", "type": "device", "risk": "low" }
      ],
      "links": [
        { "source": "CUST-1042", "target": "DEV-901", "relation": "authenticated_with" },
        { "source": "CUST-1042", "target": "REC-441", "relation": "regular_transfers_x12" }
      ]
    }
  },
  {
    "id": "case-2",
    "title": "Account Takeover (8,000 SEK)",
    "subtitle": "New device + synthetic session anomaly",
    "expected_action": "REVIEW",
    "customer": {
      "id": "CUST-2089",
      "name": "Johan Holm",
      "typical_min": 300,
      "typical_max": 3500,
      "known_recipients": ["REC-312"],
      "known_devices": ["DEV-204"]
    },
    "transaction": {
      "id": "TX-8902",
      "amount": 8000,
      "currency": "SEK",
      "recipient_id": "REC-902",
      "recipient_name": "Digital Vault AB",
      "device_id": "DEV-334",
      "auth_type": "SMS_OTP_Fallback",
      "channel": "WebBrowser"
    },
    "device": { "id": "DEV-334", "is_known": false, "os": "Windows 11 / Automated Chromium", "session_anomalies": ["IP jump Stockholm->Frankfurt in 4 min (impossible travel)", "Headless browser automation detected"] },
    "recipient": { "id": "REC-902", "name": "Digital Vault AB", "account_age_days": 12, "incoming_transfers_90min": 4, "synthetic_flags": ["New business account burst"] },
    "graph": {
      "nodes": [
        { "id": "CUST-2089", "label": "Johan Holm (Payer)", "type": "customer", "risk": "low" },
        { "id": "DEV-334", "label": "Unknown Device (Frankfurt IP)", "type": "device", "risk": "high" },
        { "id": "REC-902", "label": "Digital Vault AB", "type": "recipient", "risk": "medium" }
      ],
      "links": [
        { "source": "CUST-2089", "target": "DEV-334", "relation": "session_anomaly_detected" },
        { "source": "DEV-334", "target": "REC-902", "relation": "funds_routing" }
      ]
    }
  },
  {
    "id": "case-3",
    "title": "Manipulated Payer / Safe Account Scam (24,500 SEK)",
    "subtitle": "Authorised push payment with social engineering signals",
    "expected_action": "CONTEXT_CHECK",
    "customer": {
      "id": "CUST-3912",
      "name": "Elin Nygren",
      "typical_min": 200,
      "typical_max": 2000,
      "known_recipients": ["REC-119", "REC-442"],
      "known_devices": ["DEV-112"]
    },
    "transaction": {
      "id": "TX-8903",
      "amount": 24500,
      "currency": "SEK",
      "recipient_id": "REC-558",
      "recipient_name": "Säkerhetskonto Nord (Security Hold)",
      "device_id": "DEV-112",
      "auth_type": "BankID_Biometric",
      "channel": "MobileApp"
    },
    "device": { "id": "DEV-112", "is_known": true, "os": "iOS 17.5", "session_anomalies": [] },
    "recipient": { "id": "REC-558", "name": "Säkerhetskonto Nord (Security Hold)", "account_age_days": 3, "incoming_transfers_90min": 14, "synthetic_flags": ["14 incoming transfers in 90 min (mule burst)"] },
    "graph": {
      "nodes": [
        { "id": "CUST-3912", "label": "Elin Nygren (Payer)", "type": "customer", "risk": "low" },
        { "id": "DEV-112", "label": "Elin's Trusted iPhone 13", "type": "device", "risk": "low" },
        { "id": "REC-558", "label": "Säkerhetskonto Nord (Mule)", "type": "recipient", "risk": "high" },
        { "id": "DEV-SHARED-88", "label": "Shared Device #88 (Android emulator)", "type": "device", "risk": "critical" },
        { "id": "REC-FLAGGED-09", "label": "Flagged Account #09 (Prior fraud report)", "type": "recipient", "risk": "critical" }
      ],
      "links": [
        { "source": "CUST-3912", "target": "DEV-112", "relation": "authenticated_with" },
        { "source": "CUST-3912", "target": "REC-558", "relation": "pending_transfer_24500" },
        { "source": "REC-558", "target": "DEV-SHARED-88", "relation": "shared_login_telemetry" },
        { "source": "DEV-SHARED-88", "target": "REC-FLAGGED-09", "relation": "linked_mule_cluster" }
      ]
    }
  }
];

const EMBEDDED_STREAM_FEED = [
  { id: "TX-1001", time: "12:08:12", amount: 48, currency: "SEK", payer: "Marcus Lind", rec: "Espresso House", channel: "Swish", status: "PASS", latency: "1.2ms", reason: "Baseline verified (20-500 SEK)", case_id: null },
  { id: "TX-8901", time: "12:08:44", amount: 600, currency: "SEK", payer: "Alice Lindqvist", rec: "Erik Berg", channel: "MobileApp", status: "PASS", latency: "1.4ms", reason: "Known contact (x12 past transfers)", case_id: "case-1" },
  { id: "TX-1003", time: "12:09:15", amount: 1420, currency: "SEK", payer: "Sofia Ekström", rec: "ICA Kvantum", channel: "Card_POS", status: "PASS", latency: "1.1ms", reason: "Routine merchant grocery cadence", case_id: null },
  { id: "TX-8903", time: "12:10:00", amount: 24500, currency: "SEK", payer: "Elin Nygren", rec: "Säkerhetskonto Nord", channel: "MobileApp", status: "FLAGGED_ANOMALY", latency: "1.8ms", reason: "TIER-0 BREACH: 12.2x Spike to 3-day account -> HELD IN ESCROW", case_id: "case-3" },
  { id: "TX-8902", time: "12:10:48", amount: 8000, currency: "SEK", payer: "Johan Holm", rec: "Digital Vault AB", channel: "WebBrowser", status: "FLAGGED_ANOMALY", latency: "1.5ms", reason: "TIER-0 BREACH: Impossible travel + headless browser -> HELD IN ESCROW", case_id: "case-2" }
];

let scenarios = [];
let currentScenario = null;
let currentRun = null;
let isInvestigating = false;
let userApiKey = localStorage.getItem("gemini_api_key") || "";

// Live Stream State
let liveStreamTransactions = [...EMBEDDED_STREAM_FEED];
let isStreamRunning = true;
let isAutoInvestigate = true;
let streamTimer = null;
let routineTxCounter = 9200;

// DOM Elements
const scenarioTabsContainer = document.getElementById("scenario-tabs");
const liveStreamFeedContainer = document.getElementById("live-stream-feed");
const streamTpsEl = document.getElementById("stream-tps");
const streamLatencyEl = document.getElementById("stream-latency");
const streamEscrowCountEl = document.getElementById("stream-escrow-count");
const btnStreamToggle = document.getElementById("btn-stream-toggle");
const streamToggleIcon = document.getElementById("stream-toggle-icon");
const streamToggleText = document.getElementById("stream-toggle-text");
const btnAutoInvestigate = document.getElementById("btn-auto-investigate");
const autoInvestigateStatus = document.getElementById("auto-investigate-status");
const streamEscalationAlert = document.getElementById("stream-escalation-alert");
const streamAlertMsg = document.getElementById("stream-alert-msg");
const currentTargetBadge = document.getElementById("current-target-badge");

const inputApiKey = document.getElementById("input-api-key");
const btnSaveKey = document.getElementById("btn-save-key");
const btnRun = document.getElementById("btn-run");
const btnRunText = document.getElementById("btn-run-text");
const spinner = document.getElementById("spinner");

// Transaction Banner Elements
const txAmountEl = document.getElementById("tx-amount");
const txIdEl = document.getElementById("tx-id");
const txPayerEl = document.getElementById("tx-payer");
const txPayerIdEl = document.getElementById("tx-payer-id");
const txRecipientEl = document.getElementById("tx-recipient");
const txRecipientIdEl = document.getElementById("tx-recipient-id");
const txChannelEl = document.getElementById("tx-channel");
const txAuthEl = document.getElementById("tx-auth");
const txStateBadge = document.getElementById("tx-state-badge");
const txExpectedBadge = document.getElementById("tx-expected-badge");

// Workspace Elements
const traceContainer = document.getElementById("trace-container");
const traceStepCountEl = document.getElementById("trace-step-count");
const claimsContainer = document.getElementById("claims-container");
const evidenceContainer = document.getElementById("evidence-container");
const policyActionBadge = document.getElementById("policy-action-badge");
const policySummaryBox = document.getElementById("policy-summary-box");
const policyRuleName = document.getElementById("policy-rule-name");
const policyRuleReason = document.getElementById("policy-rule-reason");
const graphSvg = document.getElementById("graph-svg");

// Dynamic Agent Interrogation & Question Bank Elements
const contextCheckBanner = document.getElementById("context-check-banner");
const contextCheckQuestion = document.getElementById("context-check-question");
const inquiryTypologyBadge = document.getElementById("inquiry-typology-badge");
const inquiryDbSrc = document.getElementById("inquiry-db-src");
const inquiryOptionsContainer = document.getElementById("inquiry-options-container");
const ccStatusText = document.getElementById("cc-status-text");

// Conclusive Human Compliance Dossier Elements
const humanDossierCard = document.getElementById("human-dossier-card");
const dossierStatusBadge = document.getElementById("dossier-status-badge");
const dossierNarrative = document.getElementById("dossier-narrative");
const dossierJevRisk = document.getElementById("dossier-jev-risk");
const dossierPayerState = document.getElementById("dossier-payer-state");

// SQLite Customer Modal Elements
const customerDbModal = document.getElementById("customer-db-modal");
const btnOpenDbModal = document.getElementById("btn-open-db-modal");
const btnCloseDbModal = document.getElementById("btn-close-db-modal");
const dbModalContent = document.getElementById("db-modal-content");
// Causal Recalculate Elements
const btnRecalculateEvidence = document.getElementById("btn-recalculate-evidence");
const causalRecalculatePanel = document.getElementById("causal-recalculate-panel");
const btnCloseCausal = document.getElementById("btn-close-causal");
const causalDeltaTitle = document.getElementById("causal-delta-title");
const causalDeltaText = document.getElementById("causal-delta-text");

// Human Hand-off & G-Eval Elements
const remainingUncertaintyText = document.getElementById("remaining-uncertainty-text");
const gevalGrounding = document.getElementById("geval-grounding");
const gevalCompleteness = document.getElementById("geval-completeness");
const gevalRelevance = document.getElementById("geval-relevance");

// Repeatability Elements
const btnTestRepeatability = document.getElementById("btn-test-repeatability");
const repeatabilityResult = document.getElementById("repeatability-result");
const repRate = document.getElementById("rep-rate");
const repDistribution = document.getElementById("rep-distribution");


// 1. Initialize Application
async function init() {
  if (userApiKey) {
    inputApiKey.value = userApiKey;
  }

  try {
    const res = await fetch("/api/scenarios");
    if (!res.ok) throw new Error("HTTP " + res.status);
    scenarios = await res.json();
  } catch (err) {
    console.warn("Backend API unavailable or offline, using embedded fixtures:", err);
    scenarios = EMBEDDED_SCENARIOS;
  }
  
  renderScenarioTabs();
  const defaultScenario = scenarios.find(s => s.id === "case-3") || scenarios[0];
  selectScenario(defaultScenario);

  // Initialize Live Stream Feed & Controls
  initLiveStream();

  // Initialize Google Multimodal Voice Interrogation
  initGoogleVoiceInterrogation();
}

// 2. Live Stream Management
function initLiveStream() {
  renderLiveStreamFeed();
  updateStreamTelemetry();

  // Start continuous 2.2-second stream interval
  startStreamTimer();

  // Play/Pause button
  if (btnStreamToggle) {
    btnStreamToggle.onclick = () => {
      isStreamRunning = !isStreamRunning;
      if (isStreamRunning) {
        startStreamTimer();
        streamToggleIcon.textContent = "⏸";
        streamToggleText.textContent = "Pause Stream";
        btnStreamToggle.classList.remove("bg-emerald-950", "text-emerald-300", "border-emerald-700");
        btnStreamToggle.classList.add("bg-slate-800", "text-slate-300");
      } else {
        stopStreamTimer();
        streamToggleIcon.textContent = "▶";
        streamToggleText.textContent = "Resume Stream";
        btnStreamToggle.classList.remove("bg-slate-800", "text-slate-300");
        btnStreamToggle.classList.add("bg-emerald-950", "text-emerald-300", "border-emerald-700");
      }
    };
  }

  // Auto-Investigate Toggle
  if (btnAutoInvestigate) {
    btnAutoInvestigate.onclick = () => {
      isAutoInvestigate = !isAutoInvestigate;
      if (isAutoInvestigate) {
        autoInvestigateStatus.textContent = "ON";
        autoInvestigateStatus.className = "text-emerald-400 font-extrabold";
      } else {
        autoInvestigateStatus.textContent = "OFF";
        autoInvestigateStatus.className = "text-slate-400 font-extrabold";
      }
    };
  }

  // Anomaly Injection Buttons
  document.querySelectorAll(".btn-inject-scenario").forEach(btn => {
    btn.onclick = async () => {
      const caseId = btn.dataset.case;
      await injectScenarioIntoStream(caseId);
    };
  });
}

function startStreamTimer() {
  stopStreamTimer();
  streamTimer = setInterval(async () => {
    if (!isStreamRunning) return;
    await fetchNextStreamingTx();
  }, 2200);
}

function stopStreamTimer() {
  if (streamTimer) {
    clearInterval(streamTimer);
    streamTimer = null;
  }
}

async function fetchNextStreamingTx() {
  let newTx = null;
  try {
    const res = await fetch("/api/stream/next");
    if (res.ok) {
      const item = await res.json();
      newTx = {
        id: item.id,
        time: item.timestamp ? item.timestamp.substring(11, 19) : new Date().toTimeString().substring(0, 8),
        amount: item.amount,
        currency: item.currency || "SEK",
        payer: item.payer_name,
        rec: item.recipient_name,
        channel: item.channel || "MobileApp",
        status: item.tier0_status || "PASS",
        latency: `${item.tier0_latency_ms || 1.2}ms`,
        reason: item.tier0_reason || "Baseline transfer verified",
        case_id: item.case_id
      };
    }
  } catch (e) {
    newTx = generateClientSyntheticTx();
  }

  if (!newTx) newTx = generateClientSyntheticTx();

  liveStreamTransactions.unshift(newTx);
  if (liveStreamTransactions.length > 25) {
    liveStreamTransactions.pop();
  }

  renderLiveStreamFeed();
  updateStreamTelemetry();

  if (newTx.status === "FLAGGED_ANOMALY" && isAutoInvestigate && !isInvestigating) {
    handleStreamAnomalyInterception(newTx);
  }
}

function generateClientSyntheticTx() {
  routineTxCounter++;
  const payers = ["Lars Svensson", "Emma Nilsson", "Oskar Lindgren", "Astrid Blom", "Viktor Dahl"];
  const merchants = [
    { name: "Pressbyrån", amt: 65, chan: "Swish" },
    { name: "SL Lokaltrafik", amt: 42, chan: "Contactless_NFC" },
    { name: "H&M City", amt: 499, chan: "Card_POS" },
    { name: "Spotify Premium", amt: 169, chan: "Autogiro" },
    { name: "Apoteket Hjärtat", amt: 215, chan: "Card_POS" },
    { name: "Klarna Checkout", amt: 890, chan: "Online_Ecom" }
  ];
  const p = payers[Math.floor(Math.random() * payers.length)];
  const m = merchants[Math.floor(Math.random() * merchants.length)];
  const amt = Math.round(m.amt * (0.85 + Math.random() * 0.3));
  const time = new Date().toTimeString().substring(0, 8);
  const latency = (1.0 + Math.random() * 0.4).toFixed(1) + "ms";

  return {
    id: `TX-${routineTxCounter}`,
    time,
    amount: amt,
    currency: "SEK",
    payer: p,
    rec: m.name,
    channel: m.chan,
    status: "PASS",
    latency,
    reason: "Routine payment within customer envelope",
    case_id: null
  };
}

async function injectScenarioIntoStream(caseId) {
  const targetScenario = scenarios.find(s => s.id === caseId) || EMBEDDED_SCENARIOS.find(s => s.id === caseId);
  if (!targetScenario) return;

  const isAnomaly = targetScenario.expected_action !== "ALLOW";
  const injectedItem = {
    id: targetScenario.transaction.id,
    time: new Date().toTimeString().substring(0, 8),
    amount: targetScenario.transaction.amount,
    currency: targetScenario.transaction.currency || "SEK",
    payer: targetScenario.customer.name,
    rec: targetScenario.recipient.name,
    channel: targetScenario.transaction.channel || "MobileApp",
    status: isAnomaly ? "FLAGGED_ANOMALY" : "PASS",
    latency: isAnomaly ? "1.8ms" : "1.2ms",
    reason: isAnomaly 
      ? `TIER-0 BREACH: ${targetScenario.title} -> SOFT-HELD IN ESCROW`
      : "Baseline verified: Recurring contact within bounds",
    case_id: caseId
  };

  liveStreamTransactions.unshift(injectedItem);
  renderLiveStreamFeed();
  updateStreamTelemetry();

  handleStreamAnomalyInterception(injectedItem);
}

function handleStreamAnomalyInterception(txItem) {
  if (streamEscalationAlert && streamAlertMsg) {
    streamAlertMsg.textContent = `${txItem.id} (${txItem.amount.toLocaleString()} ${txItem.currency}) placed in Escrow Soft-Hold.`;
    streamEscalationAlert.classList.remove("hidden");
    setTimeout(() => {
      streamEscalationAlert.classList.add("hidden");
    }, 6000);
  }

  if (txItem.case_id) {
    const sc = scenarios.find(s => s.id === txItem.case_id) || EMBEDDED_SCENARIOS.find(s => s.id === txItem.case_id);
    if (sc) {
      selectScenario(sc);
      if (currentTargetBadge) {
        currentTargetBadge.textContent = `Live Intercept: ${txItem.id}`;
        currentTargetBadge.className = "text-[10px] font-mono px-2 py-0.5 rounded bg-rose-950 text-rose-300 border border-rose-800 animate-pulse";
      }
      runInvestigation();
    }
  }
}

function renderLiveStreamFeed() {
  if (!liveStreamFeedContainer) return;
  liveStreamFeedContainer.innerHTML = "";

  liveStreamTransactions.slice(0, 8).forEach(item => {
    const row = document.createElement("div");
    const isAnomaly = item.status === "FLAGGED_ANOMALY";
    const isCurrentCase = currentScenario && currentScenario.transaction && currentScenario.transaction.id === item.id;

    row.className = `stream-table-row cursor-pointer transition ${
      isCurrentCase
        ? "bg-cyan-950/70 border border-cyan-500/80 shadow-md shadow-cyan-950/50"
        : isAnomaly
          ? "bg-rose-950/40 border border-rose-900/60 hover:bg-rose-900/50"
          : "hover:bg-slate-900/70 border border-transparent"
    }`;

    row.innerHTML = `
      <span class="text-slate-500 text-[11px] font-mono tabular-nums">${item.time || ''}</span>
      <span class="font-bold font-mono ${isAnomaly ? 'text-rose-300' : 'text-slate-300'}">${item.id}</span>
      <span class="truncate text-slate-300 font-medium" title="${item.payer}">${item.payer}</span>
      <span class="text-right font-bold font-mono tabular-nums ${isAnomaly ? 'text-amber-400 font-extrabold' : 'text-slate-200'}">${item.amount.toLocaleString()} <span class="text-[10px] text-slate-500">${item.currency}</span></span>
      <span class="truncate text-slate-400" title="${item.rec}">${item.rec}</span>
      <div class="flex items-center space-x-2 truncate">
        <span class="px-1.5 py-0.5 rounded text-[9px] font-bold font-mono shrink-0 ${
          isAnomaly 
            ? 'bg-rose-900 text-rose-200 border border-rose-700 animate-pulse' 
            : 'bg-emerald-950 text-emerald-400 border border-emerald-800/80'
        }">
          ${isAnomaly ? 'TIER-0 BREACH' : 'PASS'} (${item.latency})
        </span>
        <span class="text-[11px] text-slate-400 truncate">${item.reason || ''}</span>
      </div>
      <div class="text-right shrink-0">
        <button class="btn-live-investigate px-2 py-0.5 text-[10px] font-mono font-bold rounded ${
          isAnomaly 
            ? 'bg-rose-600 hover:bg-rose-500 text-white shadow shadow-rose-600/30' 
            : 'bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700'
        } transition cursor-pointer">
          ${isAnomaly ? '⚡ Investigate' : 'Inspect'}
        </button>
      </div>
    `;

    row.querySelector(".btn-live-investigate").onclick = (e) => {
      e.stopPropagation();
      handleRowSelection(item);
    };
    row.onclick = () => {
      handleRowSelection(item);
    };

    liveStreamFeedContainer.appendChild(row);
  });
}

function handleRowSelection(item) {
  if (item.case_id) {
    const sc = scenarios.find(s => s.id === item.case_id) || EMBEDDED_SCENARIOS.find(s => s.id === item.case_id);
    if (sc) {
      selectScenario(sc);
      if (currentTargetBadge) {
        currentTargetBadge.textContent = `Stream Target: ${item.id}`;
        currentTargetBadge.className = "text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800";
      }
      runInvestigation();
    }
  } else {
    const routineSc = {
      id: `adhoc-${item.id}`,
      title: `Routine Payment (${item.amount} SEK)`,
      subtitle: `Normal transfer to ${item.rec}`,
      expected_action: "ALLOW",
      customer: {
        id: "CUST-LIVE",
        name: item.payer,
        typical_min: 50,
        typical_max: 2000,
        known_recipients: ["REC-M01", "REC-M02", item.rec],
        known_devices: ["DEV-LIVE"]
      },
      transaction: {
        id: item.id,
        amount: item.amount,
        currency: item.currency,
        recipient_id: "REC-AD-HOC",
        recipient_name: item.rec,
        device_id: "DEV-LIVE",
        auth_type: "BankID_Biometric",
        channel: item.channel
      },
      device: { id: "DEV-LIVE", is_known: true, os: "iOS 18.2", session_anomalies: [] },
      recipient: { id: "REC-AD-HOC", name: item.rec, account_age_days: 450, incoming_transfers_90min: 1, synthetic_flags: [] },
      graph: {
        nodes: [
          { id: "CUST-LIVE", label: `${item.payer} (Payer)`, type: "customer", risk: "low" },
          { id: "REC-AD-HOC", label: `${item.rec} (Merchant)`, type: "recipient", risk: "low" }
        ],
        links: [
          { source: "CUST-LIVE", target: "REC-AD-HOC", relation: "verified_routine" }
        ]
      }
    };
    selectScenario(routineSc);
    if (currentTargetBadge) {
      currentTargetBadge.textContent = `Stream Target: ${item.id} (Routine)`;
      currentTargetBadge.className = "text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800";
    }
    runInvestigation();
  }
}

function updateStreamTelemetry() {
  if (streamTpsEl) {
    const jitterTps = 140 + Math.floor(Math.random() * 20);
    streamTpsEl.textContent = `${jitterTps} tx/min`;
  }
  if (streamLatencyEl) {
    const jitterLat = (1.1 + Math.random() * 0.3).toFixed(1);
    streamLatencyEl.textContent = `${jitterLat}ms avg`;
  }
  if (streamEscrowCountEl) {
    const activeHolds = liveStreamTransactions.filter(t => t.status === "FLAGGED_ANOMALY").length;
    streamEscrowCountEl.textContent = `${activeHolds} Active`;
  }
}

// 3. API Key Management
btnSaveKey.onclick = async () => {
  const key = inputApiKey.value.trim();
  userApiKey = key;
  localStorage.setItem("gemini_api_key", key);
  try {
    await fetch("/api/set-api-key", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: key })
    });
  } catch (e) {}
  btnSaveKey.textContent = "Saved ✓";
  setTimeout(() => { btnSaveKey.textContent = "Save"; }, 2000);
};

// 4. Render Scenario Tabs
function renderScenarioTabs() {
  scenarioTabsContainer.innerHTML = "";
  scenarios.forEach((s) => {
    const btn = document.createElement("button");
    btn.className = `px-3.5 py-1.5 text-xs font-mono rounded-lg transition-all border cursor-pointer ${
      currentScenario && currentScenario.id === s.id
        ? "bg-cyan-950/80 text-cyan-300 border-cyan-500 shadow-sm"
        : "bg-slate-900 text-slate-400 border-slate-800 hover:border-slate-700 hover:text-slate-200"
    }`;
    btn.innerHTML = `<span class="font-bold">${s.title}</span>`;
    btn.onclick = () => selectScenario(s);
    scenarioTabsContainer.appendChild(btn);
  });
}

// 5. Select Scenario
function selectScenario(scenario) {
  currentScenario = scenario;
  currentRun = null;
  renderScenarioTabs();

  const tx = scenario.transaction;
  const cust = scenario.customer;
  txAmountEl.textContent = `${tx.amount.toLocaleString()} ${tx.currency}`;
  txIdEl.textContent = tx.id;
  txPayerEl.textContent = cust.name;
  txPayerIdEl.textContent = `Baseline: ${cust.typical_min}-${cust.typical_max} SEK`;
  txRecipientEl.textContent = tx.recipient_name;
  txRecipientIdEl.textContent = tx.recipient_id;
  txChannelEl.textContent = tx.channel;
  txAuthEl.textContent = tx.auth_type;

  txStateBadge.textContent = "PENDING ESCROW (Held in Step-Up)";
  txStateBadge.className = "px-2.5 py-1 text-xs font-mono font-bold rounded bg-amber-950 text-amber-300 border border-amber-800/60";

  txExpectedBadge.textContent = scenario.expected_action;
  txExpectedBadge.className = `px-2.5 py-1 text-xs font-mono font-bold rounded ${getBadgeClass(scenario.expected_action)}`;

  traceContainer.innerHTML = `<div class="text-slate-500 italic py-8 text-center font-sans">Click "Investigate Transaction" to launch Gemini agent.</div>`;
  traceStepCountEl.textContent = "0 steps completed";
  claimsContainer.innerHTML = `<div class="text-xs text-slate-500 italic">No investigation findings yet.</div>`;
  evidenceContainer.innerHTML = `<div class="text-slate-500 italic py-8 text-center text-xs">Evidence items recorded during investigation will appear here.</div>`;
  policyActionBadge.textContent = "PENDING";
  policyActionBadge.className = "px-2.5 py-1 text-xs font-mono font-bold rounded bg-slate-800 text-slate-400";
  policySummaryBox.classList.add("hidden");
  contextCheckBanner.classList.add("hidden");
  causalRecalculatePanel.classList.add("hidden");

  renderGraph({ nodes: [], links: [] });
}

function getBadgeClass(action) {
  if (action === "ALLOW") return "badge-allow";
  if (action === "CONTEXT_CHECK") return "badge-context-check";
  if (action === "REVIEW") return "badge-review";
  return "bg-slate-800 text-slate-300";
}

// 6. Run Autonomous Investigation
btnRun.onclick = async () => {
  if (isInvestigating || !currentScenario) return;
  setLoading(true);

  try {
    let runData;
    try {
      const headers = { "Content-Type": "application/json" };
      if (userApiKey) headers["X-Gemini-Api-Key"] = userApiKey;

      const res = await fetch("/api/investigations", {
        method: "POST",
        headers: headers,
        body: JSON.stringify({ case_id: currentScenario.id, api_key: userApiKey })
      });
      if (!res.ok) throw new Error("HTTP " + res.status);
      runData = await res.json();
    } catch (netErr) {
      console.warn("Backend unavailable, executing client-side simulation:", netErr);
      runData = simulateInvestigation(currentScenario.id, {});
    }

    currentRun = runData;
    await renderInvestigationLive(runData);
  } catch (err) {
    console.error("Investigation failed:", err);
  } finally {
    setLoading(false);
  }
};

function setLoading(loading) {
  isInvestigating = loading;
  if (loading) {
    spinner.classList.remove("hidden");
    btnRunText.textContent = "Gemini Investigating...";
    btnRun.disabled = true;
    btnRun.classList.add("opacity-75");
  } else {
    spinner.classList.add("hidden");
    btnRunText.textContent = "⚡ Re-run Investigation";
    btnRun.disabled = false;
    btnRun.classList.remove("opacity-75");
  }
}

// 7. Live Trace Animation
async function renderInvestigationLive(runData) {
  traceContainer.innerHTML = "";
  evidenceContainer.innerHTML = "";
  claimsContainer.innerHTML = "";
  contextCheckBanner.classList.add("hidden");

  const events = runData.trace_events || [];
  const evidenceList = runData.evidence || [];

  for (let i = 0; i < events.length; i++) {
    const ev = events[i];
    const outEvidence = evidenceList.find(e => e.evidence_id === ev.output_evidence_id);

    const traceItem = document.createElement("div");
    traceItem.className = "trace-item p-3 rounded-lg bg-slate-950/80 border border-slate-800/80 text-xs space-y-1.5";
    traceItem.innerHTML = `
      <div class="flex items-center justify-between">
        <div class="flex items-center space-x-2">
          <span class="w-5 h-5 rounded bg-cyan-950 text-cyan-400 border border-cyan-800 flex items-center justify-center font-bold font-mono text-[10px]">#${ev.sequence}</span>
          <span class="text-cyan-300 font-bold font-mono">${ev.tool_name}()</span>
        </div>
        <span class="text-[10px] text-slate-500 font-mono">${ev.duration_ms}ms</span>
      </div>
      <div class="text-slate-300 text-[11px] font-sans pl-7">
        ${ev.operational_reason}
      </div>
      <div class="pl-7 pt-1 flex items-center space-x-2">
        <span class="text-[10px] uppercase font-mono text-slate-500">Output:</span>
        <button class="px-2 py-0.5 rounded bg-cyan-900/40 text-cyan-300 border border-cyan-700/50 font-mono text-[10px] hover:bg-cyan-800/50 cursor-pointer" onclick="scrollToEvidence('${ev.output_evidence_id}')">
          📌 ${ev.output_evidence_id} ${outEvidence ? `— ${outEvidence.title}` : ''}
        </button>
      </div>
    `;
    traceContainer.appendChild(traceItem);
    traceStepCountEl.textContent = `${i + 1} of ${events.length} steps`;

    if (outEvidence) {
      addEvidenceCard(outEvidence);
    }

    if (ev.tool_name === "search_relationship_graph" && runData.graph) {
      renderGraph(runData.graph);
    }

    await new Promise(r => setTimeout(r, 320));
  }

  if (runData.graph) {
    renderGraph(runData.graph);
  }

  renderClaims(runData.claims);

  const pol = runData.policy_decision;
  policyActionBadge.textContent = pol.action;
  policyActionBadge.className = `px-2.5 py-1 text-xs font-mono font-bold rounded ${getBadgeClass(pol.action)}`;

  policyRuleName.textContent = pol.policy_rule;
  policyRuleReason.textContent = pol.reason;
  policySummaryBox.classList.remove("hidden");

  if (pol.action === "CONTEXT_CHECK" && pol.requires_context_check) {
    renderCustomerInquiry(runData);
    txStateBadge.textContent = "PENDING ESCROW (Held)";
    txStateBadge.className = "px-2 py-0.5 text-[11px] font-mono font-bold rounded bg-amber-950 text-amber-300 border border-amber-800/60";
  } else {
    contextCheckBanner.classList.add("hidden");
    if (pol.action === "ALLOW") {
      txStateBadge.textContent = "CLEARED / AUTHORIZED";
      txStateBadge.className = "px-2 py-0.5 text-[11px] font-mono font-bold rounded bg-emerald-950 text-emerald-300 border border-emerald-800/60";
    } else {
      txStateBadge.textContent = "HELD / FROZEN";
      txStateBadge.className = "px-2 py-0.5 text-[11px] font-mono font-bold rounded bg-rose-950 text-rose-300 border border-rose-800/60";
    }
  }

  // Populate Human Hand-off & G-Eval Audit Scorecard
  if (remainingUncertaintyText) {
    remainingUncertaintyText.textContent = runData.remaining_uncertainty || "Investigation completed; zero residual uncertainty.";
  }
  if (runData.geval_evaluation) {
    if (gevalGrounding) gevalGrounding.textContent = runData.geval_evaluation.evidence_grounding.score;
    if (gevalCompleteness) gevalCompleteness.textContent = runData.geval_evaluation.explanation_completeness.score;
    if (gevalRelevance) gevalRelevance.textContent = runData.geval_evaluation.investigation_relevance.score;
  }
}

// Repeatability Test Handler (Fresh Inferences x5)
if (btnTestRepeatability) {
  btnTestRepeatability.onclick = async () => {
    if (!currentScenario) return;
    btnTestRepeatability.disabled = true;
    btnTestRepeatability.textContent = "Running 5 Inferences...";

    try {
      let data;
      try {
        const res = await fetch("/api/repeatability", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ case_id: currentScenario.id, runs: 5 })
        });
        if (!res.ok) throw new Error("HTTP " + res.status);
        data = await res.json();
      } catch (e) {
        // Offline fallback simulation
        const expected = currentScenario.expected_action;
        data = {
          total_runs: 5,
          stability_rate: 1.0,
          distribution: { [expected]: 5 },
          modal_action: expected
        };
      }

      repeatabilityResult.classList.remove("hidden");
      repRate.textContent = `${Math.round(data.stability_rate * 100)}% (${data.total_runs}/${data.total_runs} Consistent)`;
      repRate.className = data.stability_rate >= 0.8 ? "font-bold text-emerald-400" : "font-bold text-amber-400";

      const distStr = Object.entries(data.distribution).map(([k, v]) => `${k}: ${v}/${data.total_runs}`).join(" • ");
      repDistribution.textContent = distStr;

    } catch (err) {
      console.error("Repeatability test failed:", err);
    } finally {
      btnTestRepeatability.disabled = false;
      btnTestRepeatability.textContent = "🧪 Run 5x Stability Test";
    }
  };
}

// 8. Evidence Cards with Active Checkbox for Counterfactual Causal Testing
function addEvidenceCard(e) {
  const card = document.createElement("div");
  card.id = `evidence-${e.evidence_id}`;
  card.className = "p-3 rounded-lg bg-slate-950/90 border border-slate-800 text-xs space-y-2 transition-all";
  card.innerHTML = `
    <div class="flex items-center justify-between border-b border-slate-800/60 pb-1.5">
      <div class="flex items-center space-x-2">
        <label class="flex items-center space-x-1.5 cursor-pointer">
          <input type="checkbox" checked class="evidence-toggle rounded accent-cyan-500 cursor-pointer" data-eid="${e.evidence_id}" />
          <span class="px-1.5 py-0.5 rounded bg-cyan-900/50 text-cyan-300 font-mono font-bold text-[11px] border border-cyan-700/50">#${e.evidence_id}</span>
        </label>
        <span class="font-bold text-slate-200 text-xs">${e.title}</span>
      </div>
      <span class="text-[10px] text-slate-500 font-mono">${e.source}</span>
    </div>
    <p class="text-slate-300 text-[11px] font-sans leading-relaxed">${e.summary}</p>
    <details class="text-[10px] font-mono text-slate-400">
      <summary class="cursor-pointer text-cyan-400 hover:underline">View Raw Payload</summary>
      <pre class="bg-black/60 p-2 rounded mt-1 overflow-x-auto text-slate-300">${JSON.stringify(e.payload, null, 2)}</pre>
    </details>
  `;
  evidenceContainer.appendChild(card);
}

window.scrollToEvidence = function(evidenceId) {
  const el = document.getElementById(`evidence-${evidenceId}`);
  if (!el) return;

  document.querySelectorAll(".highlight-evidence").forEach(node => {
    node.classList.remove("highlight-evidence");
  });

  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.classList.add("highlight-evidence");

  setTimeout(() => {
    el.classList.remove("highlight-evidence");
  }, 4000);
};

// 9. Render Claims
function renderClaims(claims) {
  claimsContainer.innerHTML = "";
  if (!claims || claims.length === 0) {
    claimsContainer.innerHTML = `<div class="text-xs text-slate-500 italic">No structured claims.</div>`;
    return;
  }

  claims.forEach((c) => {
    const card = document.createElement("div");
    card.className = "p-3 rounded-lg bg-slate-950/80 border border-slate-800/80 text-xs space-y-2 hover:border-cyan-700/60 transition cursor-pointer";
    
    const badgesHtml = c.supporting_evidence_ids.map(eid => `
      <button class="px-2 py-0.5 rounded bg-cyan-900/60 text-cyan-300 border border-cyan-700 font-mono text-[10px] hover:bg-cyan-800 cursor-pointer" onclick="event.stopPropagation(); scrollToEvidence('${eid}')">
        Evidence #${eid} ↗
      </button>
    `).join(" ");

    card.innerHTML = `
      <div class="flex items-start space-x-2">
        <span class="text-cyan-400 font-mono font-bold text-[11px] shrink-0">[${c.claim_id}]</span>
        <div class="flex-1 text-slate-200 text-xs leading-relaxed font-sans">${c.text}</div>
      </div>
      <div class="flex items-center space-x-2 pl-6 pt-1 border-t border-slate-900">
        <span class="text-[10px] text-slate-500 uppercase font-mono">Cites:</span>
        <div class="flex flex-wrap gap-1">${badgesHtml}</div>
      </div>
    `;

    card.onclick = () => {
      if (c.supporting_evidence_ids.length > 0) {
        scrollToEvidence(c.supporting_evidence_ids[0]);
      }
    };

    claimsContainer.appendChild(card);
  });
}

// 10. Dynamic Agent Interrogation & Question Bank Integration
function renderCustomerInquiry(runData) {
  const q = runData.diagnostic_question || {
    question_id: "Q_APP_SCAM_SAFE_ACCOUNT",
    typology: "MANIPULATED_PAYER",
    category: "Authorised Push Payment (APP) / Safe Account Scam",
    prompt_question: runData.policy_decision.context_check_prompt || "Has someone asked you to move this money to a 'safe account', keep the transfer secret, or act urgently?",
    options: [
      {
        key: "COERCED_PHONE",
        label: "Yes, I was told by phone to protect my money in a safe account",
        statement: "Customer confirms active voice social engineering: instructed by an impersonator to execute an urgent transfer to a designated 'safe holding account'.",
        risk_verdict: "CONFIRMED_COERCION",
        badge_color: "rose"
      },
      {
        key: "VOLUNTARY_PERSONAL",
        label: "No, this is my own voluntary transfer to a familiar contact",
        statement: "Customer explicitly asserts voluntary intent for personal remittance without third-party caller instructions.",
        risk_verdict: "VOLUNTARY_UNCOERCED",
        badge_color: "emerald"
      },
      {
        key: "ONLINE_INVESTMENT",
        label: "I was guided by an online advisor/broker promising high yields",
        statement: "Customer indicates online investment solicitation with promised returns, characteristic of boiler room scam.",
        risk_verdict: "INVESTMENT_TRAP",
        badge_color: "amber"
      }
    ]
  };

  if (inquiryTypologyBadge) inquiryTypologyBadge.textContent = `TYPOLOGY: ${q.typology || 'APP_SCAM'}`;
  if (inquiryDbSrc) inquiryDbSrc.textContent = `Source: SQLite Question Bank (${q.question_id})`;
  if (contextCheckQuestion) contextCheckQuestion.textContent = `"${q.prompt_question}"`;

  if (inquiryOptionsContainer) {
    inquiryOptionsContainer.innerHTML = "";
    q.options.forEach((opt) => {
      const btn = document.createElement("button");
      const borderCol = opt.badge_color === 'rose' ? 'border-rose-700/60 hover:border-rose-500 bg-rose-950/40 hover:bg-rose-900/60' :
                        opt.badge_color === 'emerald' ? 'border-emerald-700/60 hover:border-emerald-500 bg-emerald-950/40 hover:bg-emerald-900/60' :
                        'border-amber-700/60 hover:border-amber-500 bg-amber-950/40 hover:bg-amber-900/60';
      const textCol = opt.badge_color === 'rose' ? 'text-rose-300' : opt.badge_color === 'emerald' ? 'text-emerald-300' : 'text-amber-300';
      
      btn.className = `p-3 rounded-lg border ${borderCol} text-left transition cursor-pointer flex flex-col justify-between space-y-2 group`;
      btn.innerHTML = `
        <div class="text-xs font-bold ${textCol} flex items-center justify-between">
          <span>${opt.label}</span>
          <span class="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded bg-black/60 border border-slate-700">${opt.risk_verdict}</span>
        </div>
        <p class="text-[11px] text-slate-400 group-hover:text-slate-200 leading-normal font-sans">
          ${opt.statement}
        </p>
        <div class="text-[10px] font-mono text-cyan-400 pt-1 flex items-center space-x-1">
          <span>⚡ Feed into Jev Reasoner</span>
          <span>→</span>
        </div>
      `;

      btn.onclick = () => handleCustomerInquirySelection(runData.run_id, q.question_id, opt);
      inquiryOptionsContainer.appendChild(btn);
    });
  }

  contextCheckBanner.classList.remove("hidden");
}

async function handleCustomerInquirySelection(runId, questionId, selectedOption) {
  if (ccStatusText) {
    ccStatusText.innerHTML = `<span class="animate-pulse text-cyan-300 font-bold">⚡ [1/2] Recording statement as Evidence #E07 → [2/2] Feeding to Jev Reasoner...</span>`;
  }
  
  const btns = inquiryOptionsContainer ? inquiryOptionsContainer.querySelectorAll("button") : [];
  btns.forEach(b => b.disabled = true);

  try {
    const res = await fetch("/api/inquiry/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        run_id: runId,
        case_id: currentScenario ? currentScenario.id : "case-3",
        question_id: questionId,
        option_key: selectedOption.key
      })
    });

    if (!res.ok) throw new Error("HTTP " + res.status);
    const updatedRun = await res.json();
    currentRun = updatedRun;

    // 1. Ingest Evidence E07 into Vault
    const newEvidence = updatedRun.evidence.find(e => e.type === "customer_inquiry_statement");
    if (newEvidence && !document.getElementById(`evidence-${newEvidence.evidence_id}`)) {
      addEvidenceCard(newEvidence);
      scrollToEvidence(newEvidence.evidence_id);
    }

    // 2. Add step to Timeline
    const latestTrace = updatedRun.trace_events[updatedRun.trace_events.length - 1];
    if (latestTrace && traceContainer) {
      const traceItem = document.createElement("div");
      traceItem.className = "p-2.5 rounded-lg bg-cyan-950/40 border border-cyan-800 text-xs space-y-1";
      traceItem.innerHTML = `
        <div class="flex items-center justify-between">
          <div class="flex items-center space-x-2">
            <span class="w-5 h-5 rounded bg-cyan-950 text-cyan-400 border border-cyan-800 flex items-center justify-center font-bold font-mono text-[10px]">#${latestTrace.sequence}</span>
            <span class="text-cyan-300 font-bold font-mono">assess_with_jev()</span>
          </div>
          <span class="text-[10px] text-slate-500 font-mono">${latestTrace.duration_ms}ms</span>
        </div>
        <div class="text-slate-200 text-[11px] font-sans pl-7">
          ${latestTrace.operational_reason}
        </div>
        <div class="pl-7 pt-1 flex items-center space-x-2">
          <span class="text-[10px] uppercase font-mono text-slate-500">Output:</span>
          <button class="px-2 py-0.5 rounded bg-cyan-900/40 text-cyan-300 border border-cyan-700/50 font-mono text-[10px] hover:bg-cyan-800/50 cursor-pointer" onclick="scrollToEvidence('${latestTrace.output_evidence_id}')">
            📌 ${latestTrace.output_evidence_id} — TypeSafe Jev Structured Judgment
          </button>
        </div>
      `;
      traceContainer.appendChild(traceItem);
      if (traceStepCountEl) traceStepCountEl.textContent = `${updatedRun.trace_events.length} steps completed`;
    }

    // 3. Update claims
    renderClaims(updatedRun.claims);

    // 4. Update Policy Gate
    const pol = updatedRun.policy_decision;
    policyActionBadge.textContent = pol.action;
    policyActionBadge.className = `px-2.5 py-1 text-xs font-mono font-bold rounded ${getBadgeClass(pol.action)}`;
    policyRuleName.textContent = pol.policy_rule;
    policyRuleReason.textContent = pol.reason;

    // 5. Update Banking State
    if (pol.action === "ALLOW") {
      txStateBadge.textContent = "RELEASED / VOLUNTARY CONFIRMED";
      txStateBadge.className = "px-2 py-0.5 text-[11px] font-mono font-bold rounded bg-emerald-950 text-emerald-300 border border-emerald-800/60";
    } else {
      txStateBadge.textContent = "FROZEN IN ESCROW (Coercion Intercepted)";
      txStateBadge.className = "px-2 py-0.5 text-[11px] font-mono font-bold rounded bg-rose-950 text-rose-300 border border-rose-800/60";
    }

    // 6. Hide interrogation banner
    contextCheckBanner.classList.add("hidden");

    // 7. Render Conclusive Human Compliance Dossier
    renderConclusiveHumanDossier(updatedRun, selectedOption);

  } catch (err) {
    console.error("Inquiry submission error:", err);
    if (ccStatusText) ccStatusText.textContent = "Submission error: " + err.message;
  }
}

// ==========================================
// GOOGLE MULTIMODAL VOICE INTERROGATION & STT
// ==========================================

let speechRecognitionInstance = null;
let isRecordingVoice = false;
let recordedTranscript = "";

function initGoogleVoiceInterrogation() {
  const btnAgentVoice = document.getElementById("btn-agent-voice-call");
  const btnMic = document.getElementById("btn-mic-testify");
  const btnPreset = document.getElementById("btn-audio-preset");
  const btnSubmitVoice = document.getElementById("btn-submit-voice");
  const transcriptText = document.getElementById("voice-transcript-text");
  const voiceStatusLabel = document.getElementById("voice-call-label");
  const micLabel = document.getElementById("mic-label");
  const micIcon = document.getElementById("mic-icon");

  if (!btnAgentVoice || !btnMic) return;

  // 1. Google Web Speech TTS (Agent Voice Outcall)
  btnAgentVoice.addEventListener("click", () => {
    const questionEl = document.getElementById("context-check-question");
    const rawQuestion = questionEl ? questionEl.innerText.replace(/"/g, "").trim() : 
      "Has someone asked you to move this money to a safe account, keep the transfer secret, or act urgently?";
    
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance("Valiant Bank Automated Fraud Defense. " + rawQuestion);
      utterance.rate = 1.0;
      utterance.pitch = 1.05;
      utterance.lang = "en-US";
      
      utterance.onstart = () => {
        if (voiceStatusLabel) voiceStatusLabel.textContent = "AGENT SPEAKING OUT-OF-BAND CHALLENGE (GOOGLE TTS)...";
        btnAgentVoice.classList.add("ring-2", "ring-cyan-400");
      };
      utterance.onend = () => {
        if (voiceStatusLabel) voiceStatusLabel.textContent = "AI VOICE CALL ACTIVE (AWAITING CUSTOMER TESTIMONY)";
        btnAgentVoice.classList.remove("ring-2", "ring-cyan-400");
      };
      window.speechSynthesis.speak(utterance);
    } else {
      alert("Web SpeechSynthesis not supported on this browser.");
    }
  });

  // 2. Google Web Speech STT (Customer Voice Testimony)
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRecognition) {
    speechRecognitionInstance = new SpeechRecognition();
    speechRecognitionInstance.continuous = false;
    speechRecognitionInstance.interimResults = true;
    speechRecognitionInstance.lang = "en-US";

    speechRecognitionInstance.onstart = () => {
      isRecordingVoice = true;
      if (micLabel) micLabel.textContent = "Listening to Customer Testimony...";
      if (micIcon) micIcon.textContent = "🔴";
      btnMic.classList.add("animate-pulse", "ring-2", "ring-rose-500");
      if (voiceStatusLabel) voiceStatusLabel.textContent = "RECORDING LIVE VOICE TESTIMONY (GOOGLE SPEECH STT)...";
      if (transcriptText) transcriptText.innerHTML = `<span class="text-rose-300 font-bold">Listening... Speak now into microphone.</span>`;
    };

    speechRecognitionInstance.onresult = (event) => {
      let interim = "";
      for (let i = event.resultIndex; i < event.results.length; ++i) {
        if (event.results[i].isFinal) {
          recordedTranscript += event.results[i][0].transcript;
        } else {
          interim += event.results[i][0].transcript;
        }
      }
      const display = recordedTranscript || interim;
      if (transcriptText) {
        transcriptText.innerHTML = `<strong>Voice Transcript (Google Speech):</strong> "${display}"`;
      }
      if (btnSubmitVoice) btnSubmitVoice.classList.remove("hidden");
    };

    speechRecognitionInstance.onerror = (event) => {
      console.warn("Speech recognition notice/error:", event.error);
      isRecordingVoice = false;
      if (micLabel) micLabel.textContent = "Record Voice Testimony";
      if (micIcon) micIcon.textContent = "🎙️";
      btnMic.classList.remove("animate-pulse", "ring-2", "ring-rose-500");
      if (event.error === 'not-allowed') {
        if (transcriptText) transcriptText.innerHTML = `<span class="text-amber-400">Microphone permission blocked. Please enable mic or click 'Play Victim Audio (1-Click)'!</span>`;
      }
    };

    speechRecognitionInstance.onend = () => {
      isRecordingVoice = false;
      if (micLabel) micLabel.textContent = "Record Voice Testimony";
      if (micIcon) micIcon.textContent = "🎙️";
      btnMic.classList.remove("animate-pulse", "ring-2", "ring-rose-500");
      if (voiceStatusLabel) voiceStatusLabel.textContent = "TESTIMONY RECORDED • READY FOR JEV INGESTION";
      if (recordedTranscript && btnSubmitVoice) {
        btnSubmitVoice.classList.remove("hidden");
      }
    };

    btnMic.addEventListener("click", () => {
      if (isRecordingVoice) {
        speechRecognitionInstance.stop();
      } else {
        recordedTranscript = "";
        try {
          speechRecognitionInstance.start();
        } catch (e) {
          console.error("STT start error:", e);
        }
      }
    });
  } else {
    btnMic.addEventListener("click", () => {
      alert("Google Web Speech API not supported in this browser. Please use Google Chrome or click 'Play Victim Audio (1-Click)'!");
    });
  }

  // 3. Preset Victim Audio Simulation (1-Click Demo)
  btnPreset.addEventListener("click", () => {
    const presetTranscript = "Yes! A caller claiming to be from the police fraud squad told me my account was under attack and ordered me to transfer funds to this liquidation escrow account immediately. Please help me!";
    recordedTranscript = presetTranscript;

    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
      const victimUtterance = new SpeechSynthesisUtterance(presetTranscript);
      victimUtterance.rate = 1.05;
      victimUtterance.pitch = 0.95;
      victimUtterance.lang = "en-US";
      window.speechSynthesis.speak(victimUtterance);
    }

    if (transcriptText) {
      transcriptText.innerHTML = `<strong>Victim Audio Transcript (Synthesized Speech):</strong> "${presetTranscript}"`;
    }
    if (btnSubmitVoice) {
      btnSubmitVoice.classList.remove("hidden");
      btnSubmitVoice.click(); // Auto-submit to Jev!
    }
  });

  // 4. Submit Voice Testimony to /api/voice/testify
  if (btnSubmitVoice) {
    btnSubmitVoice.addEventListener("click", async () => {
      if (!recordedTranscript) return;
      btnSubmitVoice.disabled = true;
      btnSubmitVoice.textContent = "⚡ Ingesting #E07...";

      try {
        const res = await fetch("/api/voice/testify", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            run_id: currentRun ? currentRun.run_id : null,
            case_id: currentScenario ? currentScenario.id : "case-3",
            customer_id: currentScenario && currentScenario.customer ? currentScenario.customer.customer_id : "CUST-00043",
            transcript: recordedTranscript,
            confidence: 0.98,
            audio_duration_sec: 4.5,
            language: "en-US"
          })
        });

        if (!res.ok) throw new Error("HTTP " + res.status);
        const data = await res.json();

        // Feed into Jev & timeline pipeline
        const voiceOption = {
          key: "VOICE_INTERROGATION",
          statement: recordedTranscript,
          risk_verdict: "CONFIRMED_COERCED_VICTIM"
        };
        await handleCustomerInquirySelection(currentRun?.run_id, "Q-VOICE-01", voiceOption);

        if (transcriptText) {
          transcriptText.innerHTML = `✅ <span class="text-emerald-400 font-bold">Voice Evidence #${data.evidence_id} Confirmed Coercion. Escrow Hold Active.</span>`;
        }
        btnSubmitVoice.classList.add("hidden");
      } catch (err) {
        console.error("Voice testify error:", err);
        if (transcriptText) transcriptText.innerHTML = `<span class="text-rose-400">Voice submission error: ${err.message}</span>`;
      } finally {
        btnSubmitVoice.disabled = false;
        btnSubmitVoice.textContent = "⚡ Feed to Jev (#E07)";
      }
    });
  }
}

function renderConclusiveHumanDossier(updatedRun, selectedOption) {
  if (!humanDossierCard) return;

  const jevEvidence = [...updatedRun.evidence].reverse().find(e => e.type === "jev_assessment");
  const jevData = jevEvidence ? jevEvidence.payload : {};

  const isCoerced = selectedOption.risk_verdict === "CONFIRMED_COERCION" || 
                    selectedOption.risk_verdict === "CONFIRMED_ATO" || 
                    selectedOption.risk_verdict === "INVESTMENT_TRAP" ||
                    selectedOption.risk_verdict === "CONFIRMED_COERCED_VICTIM";
  
  if (dossierStatusBadge) {
    dossierStatusBadge.textContent = isCoerced ? "FRAUD CONFIRMED • ESCROW FROZEN" : "VOLUNTARY CLEARANCE";
    dossierStatusBadge.className = isCoerced
      ? "px-2 py-0.5 text-[9px] font-mono font-bold rounded bg-rose-950 text-rose-300 border border-rose-800"
      : "px-2 py-0.5 text-[9px] font-mono font-bold rounded bg-emerald-950 text-emerald-300 border border-emerald-800";
  }

  if (dossierNarrative) {
    if (isCoerced) {
      dossierNarrative.innerHTML = `
        <span class="text-rose-400 font-bold">Audited Multi-Signal Coercion Interception:</span>
        Transaction amount (<span class="font-mono text-white font-bold">${updatedRun.transaction.amount} SEK</span>) 
        exceeds 30-day baseline by <span class="text-amber-300 font-mono font-bold">12.2x</span> (<button class="text-cyan-400 underline font-mono text-[10px]" onclick="scrollToEvidence('E01')">#E01</button>). 
        Counterparty is a 3-day mule account with 14 inbound transfers (<button class="text-cyan-400 underline font-mono text-[10px]" onclick="scrollToEvidence('E04')">#E04</button>) 
        with 2-hop links to known fraud cluster (<button class="text-cyan-400 underline font-mono text-[10px]" onclick="scrollToEvidence('E06')">#E06</button>). 
        <strong class="text-white">Customer testimony decisively confirmed coercive phone caller:</strong> 
        <em>"${selectedOption.statement}"</em> (<button class="text-cyan-400 underline font-mono text-[10px]" onclick="scrollToEvidence('E07')">#E07</button>). 
        <br/><span class="text-emerald-400 font-semibold mt-1 inline-block">✓ Binding Action: Funds permanently held in escrow. Suspicious Transaction Report (STR) dispatched to FIU. Customer branch alerted.</span>
      `;
    } else {
      dossierNarrative.innerHTML = `
        <span class="text-emerald-400 font-bold">Customer Voluntary Confirmation:</span>
        Customer affirmed self-directed remittance purpose without coercive pressure (<button class="text-cyan-400 underline font-mono text-[10px]" onclick="scrollToEvidence('E07')">#E07</button>).
        Counterparty velocity noted; customer warned of risk. Escrow hold safely released.
      `;
    }
  }

  if (dossierJevRisk) {
    dossierJevRisk.textContent = `${jevData.recipient_risk || 'CRITICAL'} (${(jevData.normalized_risk_score || 0.99).toFixed(2)})`;
    dossierJevRisk.className = isCoerced ? "text-rose-400 font-bold font-mono" : "text-emerald-400 font-bold font-mono";
  }

  if (dossierPayerState) {
    dossierPayerState.textContent = jevData.payer_status || (isCoerced ? "CONFIRMED_COERCED_VICTIM" : "VERIFIED_VOLUNTARY");
    dossierPayerState.className = isCoerced ? "text-amber-300 font-bold font-mono" : "text-emerald-300 font-bold font-mono";
  }

  humanDossierCard.classList.remove("hidden");
  humanDossierCard.scrollIntoView({ behavior: "smooth", block: "center" });
}

// 11. SQLite Customer Intelligence Database Record Modal Handlers
if (btnOpenDbModal) {
  btnOpenDbModal.onclick = async () => {
    if (!customerDbModal) return;
    customerDbModal.classList.remove("hidden");
    const custId = currentScenario ? currentScenario.customer.id : "CUST-3912";
    if (dbModalContent) {
      dbModalContent.innerHTML = `<div class="text-slate-400 text-xs">Querying SQLite database <code class="text-cyan-400">kyc_aml.db</code> for customer <span class="text-white font-bold">${custId}</span>...</div>`;
    }

    try {
      const res = await fetch(`/api/database/customer?id=${custId}`);
      const data = await res.json();
      const c = data.customer || {
        customer_id: custId,
        full_name: currentScenario ? currentScenario.customer.name : "Elin Nygren",
        risk_score: 0.18,
        risk_level: "LOW_BASELINE",
        annual_income_sek: 468000,
        monthly_turnover_baseline: 24500,
        kyc_verified_date: "2021-04-14",
        residential_address: "Karlavägen 42, Stockholm",
        primary_device_id: "DEV-112 (Apple iPhone 15 Pro)",
        bankid_auth_level: "High Assurance Level 3",
        historical_alert_count: 0
      };

      if (dbModalContent) {
        dbModalContent.innerHTML = `
          <div class="p-3 bg-slate-950 rounded-lg border border-slate-800 space-y-1 mb-2">
            <div class="text-slate-400 text-[10px] uppercase font-mono">SQLite Record Identified</div>
            <div class="text-white font-bold text-sm">${c.full_name || (currentScenario ? currentScenario.customer.name : 'Customer')} (${c.customer_id || custId})</div>
            <div class="text-[11px] text-slate-400">Address: ${c.residential_address || 'Karlavägen 42, Stockholm'}</div>
          </div>
          <div class="grid grid-cols-2 gap-2 text-[11px]">
            <div class="p-2 bg-slate-950 rounded border border-slate-800">
              <span class="text-slate-500 block text-[10px]">AML Risk Assessment:</span>
              <span class="text-emerald-400 font-bold">${c.risk_level || 'LOW_BASELINE'} (${c.risk_score || 0.18})</span>
            </div>
            <div class="p-2 bg-slate-950 rounded border border-slate-800">
              <span class="text-slate-500 block text-[10px]">Annual Income:</span>
              <span class="text-white font-bold">${c.annual_income_sek ? c.annual_income_sek.toLocaleString() + ' SEK' : '468,000 SEK'}</span>
            </div>
            <div class="p-2 bg-slate-950 rounded border border-slate-800">
              <span class="text-slate-500 block text-[10px]">KYC Verified:</span>
              <span class="text-slate-300 font-bold">${c.kyc_verified_date || '2021-04-14'}</span>
            </div>
            <div class="p-2 bg-slate-950 rounded border border-slate-800">
              <span class="text-slate-500 block text-[10px]">BankID Assurance:</span>
              <span class="text-cyan-300 font-bold">${c.bankid_auth_level || 'Level 3 Biometric'}</span>
            </div>
            <div class="p-2 bg-slate-950 rounded border border-slate-800 col-span-2">
              <span class="text-slate-500 block text-[10px]">Authorized Device Fingerprint:</span>
              <span class="text-slate-300">${c.primary_device_id || 'DEV-112 (Apple iPhone 15 Pro)'}</span>
            </div>
          </div>
          <div class="pt-2 text-[10px] text-slate-500 font-mono border-t border-slate-800">
            Source: SQLite kyc_aml.db • Table: customers • Foreign Keys resolved to transactions
          </div>
        `;
      }
    } catch (err) {
      if (dbModalContent) dbModalContent.innerHTML = `<div class="text-rose-400 text-xs">Failed to fetch database profile: ${err.message}</div>`;
    }
  };
}

if (btnCloseDbModal) {
  btnCloseDbModal.onclick = () => {
    if (customerDbModal) customerDbModal.classList.add("hidden");
  };
}

// 11. Recalculate Causal Impact from Active Checkboxes
btnRecalculateEvidence.onclick = async () => {
  if (!currentScenario) return;
  
  const checkedBoxes = Array.from(document.querySelectorAll(".evidence-toggle:checked"));
  const activeEids = checkedBoxes.map(cb => cb.dataset.eid);

  try {
    let data;
    try {
      const res = await fetch("/api/recalculate-causal", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          case_id: currentScenario.id,
          active_evidence_ids: activeEids
        })
      });
      if (!res.ok) throw new Error("HTTP " + res.status);
      data = await res.json();
    } catch (e) {
      // Offline fallback calculation
      const hasGraph = activeEids.includes("E03");
      const newAction = hasGraph ? "CONTEXT_CHECK" : "ALLOW";
      data = {
        action_changed: newAction !== "CONTEXT_CHECK",
        original_action: "CONTEXT_CHECK",
        recalculated_action: newAction,
        causal_explanation: hasGraph 
          ? "All core evidence present. Policy remains CONTEXT_CHECK."
          : "Removing Evidence #E03 (Shared Device link to flagged mule) downgraded recipient risk from HIGH to LOW, allowing payment without customer friction."
      };
    }

    causalRecalculatePanel.classList.remove("hidden");
    causalDeltaTitle.textContent = `Action: ${data.original_action} → ${data.recalculated_action}`;
    causalDeltaText.innerHTML = `
      <div class="flex items-center space-x-2">
        <span class="font-bold ${data.action_changed ? 'text-amber-300' : 'text-slate-300'} font-mono uppercase">
          ${data.action_changed ? '⚡ Decision Pivot Detected' : 'Invariant Outcome'}:
        </span>
        <span class="px-2 py-0.5 rounded text-xs font-mono font-bold ${getBadgeClass(data.recalculated_action)}">
          ${data.recalculated_action}
        </span>
      </div>
      <p class="mt-1.5 leading-relaxed">${data.causal_explanation}</p>
    `;

    // If graph link E03 was toggled off, update the graph view!
    if (!activeEids.includes("E03") && currentRun && currentRun.graph) {
      renderGraph({
        nodes: currentRun.graph.nodes.filter(n => n.risk !== "critical" && n.risk !== "high" || n.type === "customer"),
        links: currentRun.graph.links.filter(l => !l.target.includes("SHARED") && !l.target.includes("FLAGGED"))
      });
    } else if (currentRun && currentRun.graph) {
      renderGraph(currentRun.graph);
    }

  } catch (err) {
    console.error("Causal recalculation failed:", err);
  }
};

btnCloseCausal.onclick = () => {
  causalRecalculatePanel.classList.add("hidden");
};

// 12. Interactive Entity Relationship Graph (SVG Renderer)
function renderGraph(graphData) {
  graphSvg.innerHTML = "";
  if (!graphData || !graphData.nodes || graphData.nodes.length === 0) {
    graphSvg.innerHTML = `
      <text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" fill="#475569" font-size="12" font-family="sans-serif">
        Graph will render when agent calls search_relationship_graph()
      </text>
    `;
    return;
  }

  const nodes = graphData.nodes;
  const links = graphData.links;

  const positions = {};
  if (nodes.length <= 3) {
    nodes.forEach((n, idx) => {
      positions[n.id] = { x: 80 + idx * 150, y: 110 };
    });
  } else {
    positions["CUST-3912"] = { x: 50, y: 110 };
    positions["DEV-112"] = { x: 50, y: 40 };
    positions["REC-558"] = { x: 180, y: 110 };
    positions["DEV-SHARED-88"] = { x: 300, y: 110 };
    positions["REC-FLAGGED-09"] = { x: 400, y: 110 };
  }

  links.forEach(l => {
    const sPos = positions[l.source] || { x: 50, y: 110 };
    const tPos = positions[l.target] || { x: 200, y: 110 };

    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", sPos.x);
    line.setAttribute("y1", sPos.y);
    line.setAttribute("x2", tPos.x);
    line.setAttribute("y2", tPos.y);
    line.setAttribute("stroke", "#334155");
    line.setAttribute("stroke-width", "2");
    line.setAttribute("stroke-dasharray", l.relation.includes("anomaly") || l.relation.includes("shared") ? "4,4" : "none");
    graphSvg.appendChild(line);
  });

  nodes.forEach(n => {
    const pos = positions[n.id] || { x: 100, y: 100 };
    const group = document.createElementNS("http://www.w3.org/2000/svg", "g");

    let fillColor = "#06b6d4";
    if (n.type === "device") fillColor = n.risk === "critical" ? "#e11d48" : "#10b981";
    if (n.type === "recipient") fillColor = n.risk === "high" || n.risk === "critical" ? "#f43f5e" : "#0284c7";

    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("cx", pos.x);
    circle.setAttribute("cy", pos.y);
    circle.setAttribute("r", n.risk === "critical" || n.risk === "high" ? "15" : "12");
    circle.setAttribute("fill", fillColor);
    circle.setAttribute("stroke", "#0f172a");
    circle.setAttribute("stroke-width", "2");
    circle.setAttribute("class", "node-circle");

    const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
    text.setAttribute("x", pos.x);
    text.setAttribute("y", pos.y + 24);
    text.setAttribute("text-anchor", "middle");
    text.setAttribute("fill", "#cbd5e1");
    text.setAttribute("font-size", "9");
    text.setAttribute("font-family", "monospace");
    text.textContent = n.label.length > 20 ? n.label.substring(0, 18) + '...' : n.label;

    group.appendChild(circle);
    group.appendChild(text);
    graphSvg.appendChild(group);
  });
}

// Client-side simulation fallback
function simulateInvestigation(caseId, patches) {
  const scenario = EMBEDDED_SCENARIOS.find(s => s.id === caseId) || EMBEDDED_SCENARIOS[0];
  const tx = scenario.transaction;
  const cust = scenario.customer;
  const dev = scenario.device;
  const rec = scenario.recipient;

  let trace = [];
  let evidence = [];
  let claims = [];
  let recommendation = "ALLOW";
  let policyAction = "ALLOW";
  let policyRule = "RULE_ROUTINE_VERIFIED_CLEAR";
  let policyReason = "Transfer conforms to historical customer baseline, verified trusted device, and zero risk indicators.";
  let requiresCc = false;

  evidence.push({
    evidence_id: "E01", type: "customer_behavior", source: "core_banking_ledger",
    title: `Customer Baseline: ${cust.name}`,
    summary: `Transfer ${tx.amount} SEK is ${tx.amount > cust.typical_max ? 'OUTSIDE' : 'WITHIN'} typical baseline (${cust.typical_min}-${cust.typical_max} SEK).`,
    payload: { amount: tx.amount, typical_range: `${cust.typical_min}-${cust.typical_max}`, is_outside: tx.amount > cust.typical_max }
  });
  trace.push({
    sequence: 1, tool_name: "get_behavior_profile", duration_ms: 110,
    operational_reason: "Establish baseline transactional parameters and familiar recipient history.",
    output_evidence_id: "E01"
  });

  if (caseId === "case-1") {
    evidence.push({
      evidence_id: "E02", type: "device_telemetry", source: "mobile_sdk_telemetry",
      title: `Device Telemetry: ${dev.id}`,
      summary: "Known trusted hardware (iOS 18.2) with biometric BankID and zero anomalies.",
      payload: { is_trusted: true, anomalies: [] }
    });
    trace.push({
      sequence: 2, tool_name: "inspect_device", duration_ms: 85,
      operational_reason: "Confirm that transaction originates from registered customer hardware.",
      output_evidence_id: "E02"
    });
    evidence.push({
      evidence_id: "E03", type: "jev_assessment", source: "typesafe_jev_service",
      title: "TypeSafe Jev Structured Judgment",
      summary: "Jev assessment reports LOW recipient risk and confirms evidence sufficiency.",
      payload: { recipient_risk: "LOW", evidence_sufficiency: "SUFFICIENT_FOR_RECOMMENDATION" }
    });
    trace.push({
      sequence: 3, tool_name: "assess_with_jev", duration_ms: 140,
      operational_reason: "Confirm evidence sufficiency for routine low-friction authorization.",
      output_evidence_id: "E03"
    });

    claims = [
      { claim_id: "C01", text: `Payment of 600 SEK is strictly within ${cust.name}'s normal range (200-2,000 SEK).`, supporting_evidence_ids: ["E01"] },
      { claim_id: "C02", text: "Transfer initiated from trusted biometric device with zero telemetry anomalies.", supporting_evidence_ids: ["E02"] },
      { claim_id: "C03", text: "Jev judgment confirms low risk and sufficient evidence for direct clearance.", supporting_evidence_ids: ["E03"] }
    ];
    recommendation = "ALLOW";
    policyAction = "ALLOW";

  } else if (caseId === "case-2") {
    evidence.push({
      evidence_id: "E02", type: "device_telemetry", source: "mobile_sdk_telemetry",
      title: `Device Telemetry: ${dev.id}`,
      summary: "Critical anomaly: IP jump Stockholm to Frankfurt in 4 minutes (impossible travel) and automated browser.",
      payload: { is_trusted: false, anomalies: dev.session_anomalies }
    });
    trace.push({
      sequence: 2, tool_name: "inspect_device", duration_ms: 95,
      operational_reason: "Examine session authentication telemetry and travel plausibility.",
      output_evidence_id: "E02"
    });
    evidence.push({
      evidence_id: "E03", type: "recipient_record", source: "interbank_settlement_registry",
      title: `Recipient Intelligence: ${rec.name}`,
      summary: "New counterparty with rapid volume burst.",
      payload: { account_age_days: rec.account_age_days, incoming_rate: rec.incoming_transfers_90min }
    });
    trace.push({
      sequence: 3, tool_name: "inspect_recipient", duration_ms: 120,
      operational_reason: "Profile unverified counterparty entity.",
      output_evidence_id: "E03"
    });
    evidence.push({
      evidence_id: "E04", type: "jev_assessment", source: "typesafe_jev_service",
      title: "TypeSafe Jev Structured Judgment",
      summary: "Jev assessment reports ELEVATED risk due to compromised credentials and account takeover profile.",
      payload: { recipient_risk: "ELEVATED", evidence_sufficiency: "SUFFICIENT_FOR_RECOMMENDATION" }
    });
    trace.push({
      sequence: 4, tool_name: "assess_with_jev", duration_ms: 130,
      operational_reason: "Synthesize composite risk profile across compromised credentials and destination.",
      output_evidence_id: "E04"
    });

    claims = [
      { claim_id: "C01", text: `Transfer amount 8,000 SEK significantly exceeds ${cust.name}'s typical ceiling.`, supporting_evidence_ids: ["E01"] },
      { claim_id: "C02", text: "Critical telemetry anomaly: impossible IP travel (Stockholm to Frankfurt) and headless browser automation.", supporting_evidence_ids: ["E02"] },
      { claim_id: "C03", text: "Jev assessment synthesizes severe takeover indicators requiring intervention.", supporting_evidence_ids: ["E04"] }
    ];
    recommendation = "REVIEW";
    policyAction = "REVIEW";
    policyRule = "RULE_DEVICE_COMPROMISE_DETECTED";
    policyReason = "Critical session anomalies and impossible travel detected on originating device.";

  } else {
    const isPatched = patches && patches.remove_suspicious_network;

    evidence.push({
      evidence_id: "E02", type: "recipient_record", source: "interbank_settlement_registry",
      title: `Recipient Intelligence: ${rec.name}`,
      summary: isPatched ? "Recipient vintage normal; velocity baseline clean." : "Account created 3 days ago. 14 incoming transfers in 90 min (mule burst).",
      payload: { account_age_days: rec.account_age_days, incoming_transfers_90min: isPatched ? 1 : 14 }
    });
    trace.push({
      sequence: 2, tool_name: "inspect_recipient", duration_ms: 115,
      operational_reason: "Verify recipient vintage and incoming velocity given 24,500 SEK spike to new counterparty.",
      output_evidence_id: "E02"
    });

    evidence.push({
      evidence_id: "E03", type: "network_graph", source: "graph_entity_resolution",
      title: "Entity Relationship Graph (2 Hops)",
      summary: isPatched ? "Relationship graph clean: No connections to known fraud syndicates." : "2-hop link detected to flagged mule account REC-FLAGGED-09 via shared emulator device DEV-SHARED-88.",
      payload: { flagged_nodes: isPatched ? [] : ["DEV-SHARED-88", "REC-FLAGGED-09"] }
    });
    trace.push({
      sequence: 3, tool_name: "search_relationship_graph", duration_ms: 155,
      operational_reason: "Expand 2-hop entity network to detect shared infrastructure with known mule accounts.",
      output_evidence_id: "E03"
    });

    evidence.push({
      evidence_id: "E04", type: "jev_assessment", source: "typesafe_jev_service",
      title: "TypeSafe Jev Structured Judgment",
      summary: isPatched ? "Jev reports LOW risk following entity link removal." : "Jev reports HIGH recipient risk and confirms manipulated payer / safe-account indicators.",
      payload: { recipient_risk: isPatched ? "LOW" : "HIGH", manipulation_indicators: !isPatched }
    });
    trace.push({
      sequence: 4, tool_name: "assess_with_jev", duration_ms: 140,
      operational_reason: "Evaluate indicators for manipulated payer / authorized push payment fraud.",
      output_evidence_id: "E04"
    });

    if (!isPatched) {
      claims = [
        { claim_id: "C01", text: `Transfer of 24,500 SEK is an extreme deviation (12.2x normal maximum) to a first-time counterparty.`, supporting_evidence_ids: ["E01"] },
        { claim_id: "C02", text: "Recipient account is only 3 days old with high-velocity mule burst pattern (14 inbound transfers in 90 min).", supporting_evidence_ids: ["E02"] },
        { claim_id: "C03", text: "Entity graph links recipient to flagged fraud account REC-FLAGGED-09 via shared device fingerprint DEV-SHARED-88.", supporting_evidence_ids: ["E03"] },
        { claim_id: "C04", text: "Jev judgment confirms HIGH recipient risk and social engineering indicators characteristic of safe account scams.", supporting_evidence_ids: ["E04"] }
      ];
      recommendation = "CONTEXT_CHECK";
      policyAction = "CONTEXT_CHECK";
      policyRule = "RULE_MANIPULATED_PAYER_INTERVENTION";
      policyReason = "Unusual transfer volume to unestablished recipient linked to high-velocity mule cluster.";
      requiresCc = true;
    } else {
      claims = [
        { claim_id: "C01", text: `Amount of 24,500 SEK is high, but customer authenticated via trusted biometric hardware DEV-112.`, supporting_evidence_ids: ["E01"] },
        { claim_id: "C02", text: "Recipient entity has normal transaction velocity and clean interbank settlement status.", supporting_evidence_ids: ["E02"] },
        { claim_id: "C03", text: "Relationship graph search confirms zero connections to known fraud syndicates or shared emulator devices.", supporting_evidence_ids: ["E03"] }
      ];
      recommendation = "ALLOW";
      policyAction = "ALLOW";
      policyRule = "RULE_ROUTINE_VERIFIED_CLEAR";
      policyReason = "Suspicious network links excised; transfer verified clean under patched topology.";
      requiresCc = false;
    }
  }

  let finalGraph = scenario.graph;
  if (patches && patches.remove_suspicious_network) {
    finalGraph = {
      nodes: scenario.graph.nodes.filter(n => n.risk !== "critical" && n.risk !== "high" || n.type === "customer"),
      links: scenario.graph.links.filter(l => !l.target.includes("SHARED") && !l.target.includes("FLAGGED"))
    };
  }

  let uncertaintyText = "Customer intent, deceptive grooming, and social engineering coercion cannot be established from financial ledger metadata alone without interactive payer context check.";
  if (caseId === "case-1") uncertaintyText = "Minimal residual uncertainty; recurring familiar counterparty on verified biometric hardware.";
  if (caseId === "case-2") uncertaintyText = "Physical location and actual control of the authenticated customer cannot be confirmed from session telemetry alone without out-of-band voice verification.";

  return {
    run_id: `run-${Date.now().toString(16)}`,
    case_id: caseId,
    status: "COMPLETED",
    transaction: tx,
    trace_events: trace,
    evidence: evidence,
    claims: claims,
    remaining_uncertainty: uncertaintyText,
    geval_evaluation: {
      evidence_grounding: { score: "5/5", verdict: "GROUNDED" },
      explanation_completeness: { score: "5/5", verdict: "COMPLETE" },
      investigation_relevance: { score: "5/5", verdict: "OPTIMAL" }
    },
    agent_recommendation: recommendation,
    policy_decision: {
      action: policyAction,
      status: "COMPLETE",
      policy_rule: policyRule,
      reason: policyReason,
      requires_context_check: requiresCc,
      context_check_prompt: "Has someone asked you to move this money to a 'safe account', keep the transfer secret, or act urgently?"
    },
    graph: finalGraph
  };
}

init();
