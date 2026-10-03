// EvidenceTrail "Investigator" tab. All server data is rendered via textContent / DOM nodes
// (never innerHTML) because tool-returned free text is untrusted. Synthetic data only.

const inv = {
    scenarios: [], caseId: null, run: null, runId: null, starting: false,
    selected: [], replayCount: null, replayTimer: null, pollTimer: null,
    reviewOpen: false, contextOpen: false, error: null, reports: [], report: null, reportCmd: null, reportError: null,
    alerts: [], alertFilter: "open", alertsError: null, handoffAsk: {}, alertTimer: null,
    source: "scenarios", seedCases: [], seedNote: null, seedLoading: false, seedExp: null, seedTimer: null,
};

const TOOL_LABELS = {
    get_behavior_profile: "Checked customer behavior",
    inspect_device: "Inspected device and session",
    inspect_recipient: "Inspected recipient account",
    search_relationship_graph: "Searched recipient relationships",
    assess_with_jev: "Requested Jev risk assessment",
    finish_investigation: "Submitted recommendation",
    alert_triage: "Jev alert triage",
};
const AGENT_LABELS = {
    orchestrator: "Orchestrator", behavior_device: "Behavior & Device analyst",
    recipient_network: "Recipient & Network analyst", risk_judge: "Risk judge (Jev)", investigator: "Investigator", alert_triage: "Alert triage (Jev)",
};
const SEVERITY_TEXT = { high: "High", medium: "Medium", low: "Low" };
const SOURCE_TEXT = { jev: "Jev", policy: "Policy" };
const DISAGREEMENT_TEXT = {
    jev_suspicious_policy_allow: "Jev found this suspicious but policy v1 would allow it. The alert comes from Jev alone and the simulated action is unchanged.",
    policy_flagged_jev_not_suspicious: "Policy routed this for attention although Jev did not find it suspicious. The alert stands: Jev cannot suppress a policy alert.",
    jev_unavailable: "Jev triage was unavailable, so this alert comes from the policy alone.",
};
const ACTION_TEXT = { ALLOW: "Allow", CONTEXT_CHECK: "Context check", REVIEW: "Review" };

function el(tag, props, ...kids) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(props || {})) {
        if (v === false || v == null) continue;
        if (k === "class") e.className = v;
        else if (k === "text") e.textContent = v;
        else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
        else e.setAttribute(k, v === true ? "" : v);
    }
    for (const kid of kids.flat(Infinity)) {
        if (kid == null || kid === false) continue;
        e.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
    }
    return e;
}

function svgEl(tag, attrs, ...kids) {
    const e = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, v);
    for (const kid of kids.flat()) if (kid != null) e.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
    return e;
}

const json = o => JSON.stringify(o, null, 2);
const fmtMoney = (n, cur) => `${Number(n).toLocaleString("en-US", { minimumFractionDigits: Number.isInteger(Number(n)) ? 0 : 2, maximumFractionDigits: 2 })} ${cur || "SEK"}`;
const allCases = () => inv.scenarios.concat(inv.seedCases);
const findCase = id => allCases().find(x => x.case_id === id);
const currentList = () => (inv.source === "seed" ? inv.seedCases : inv.scenarios);
function runTransaction() {
    const started = ((inv.run && inv.run.events) || []).find(e => e.event_type === "run_started");
    return started && started.result_snapshot && started.result_snapshot.transaction;
}
const isRunning = r => !r || r.state === "queued" || r.state === "running";

async function invApi(path, body) {
    const opts = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
    const res = await fetch(path, opts);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { const err = new Error(data.error || `HTTP ${res.status}`); err.status = res.status; err.data = data; throw err; }
    return data;
}

// ---------------------------------------------------------------- derived (replay-aware) views
function visibleEvents() {
    const events = inv.run ? inv.run.events || [] : [];
    return inv.replayCount == null ? events : events.slice(0, inv.replayCount);
}
function visibleEvidenceIds() {
    const ids = new Set();
    visibleEvents().forEach(e => (e.output_evidence_ids || []).forEach(i => ids.add(i)));
    return ids;
}
function evidenceById(id) {
    return ((inv.run && inv.run.evidence) || []).find(e => e.evidence_id === id);
}
function finalVisible() {
    return !!(inv.run && inv.run.final) && visibleEvents().some(e => e.event_type === "final_decision" || e.event_type === "run_failed");
}
function selectEvidence(ids) { inv.selected = ids; renderEvidence(); renderClaims(); renderGraph(); renderTrace(); }

function chip(id, onClick) {
    const known = evidenceById(id);
    const c = el("button", { class: "inv-chip" + (inv.selected.includes(id) ? " active" : "") + (known ? "" : " missing"),
        type: "button", title: known ? (EVIDENCE_LABEL[known.type] || known.type) : "Not found in this run", text: id });
    c.addEventListener("click", ev => { ev.stopPropagation(); (onClick || selectEvidence)([id]); });
    return c;
}

// ---------------------------------------------------------------- init
function initInvestigator() {
    const root = document.getElementById("inv-root");
    if (!root) return;
    root.append(
        el("div", { class: "inv-banner", text: "All scenarios and data here are synthetic. Nothing is a real transfer, and no money is moved or blocked." }),
        el("div", { class: "inv-controls", id: "inv-controls" }),
        el("div", { class: "inv-grid" },
            el("div", { class: "inv-col" }, el("div", { id: "inv-tx", class: "inv-card" }), el("div", { id: "inv-final", class: "inv-card" }), el("div", { id: "inv-claims", class: "inv-card" })),
            el("div", { class: "inv-col" }, el("div", { id: "inv-trace", class: "inv-card" })),
            el("div", { class: "inv-col" }, el("div", { id: "inv-graph", class: "inv-card" }), el("div", { id: "inv-evidence", class: "inv-card" }))),
        el("div", { id: "inv-alerts", class: "inv-card inv-alerts" }),
        el("div", { class: "inv-quality" },
            el("div", { id: "inv-seedbatch", class: "inv-card" }), el("div", { id: "inv-risk", class: "inv-card" }), el("div", { id: "inv-quality", class: "inv-card" }), el("div", { id: "inv-consistency", class: "inv-card" })));
    loadAlerts();
    loadConsistency();
    invApi("/api/scenarios").then(d => {
        inv.scenarios = d.scenarios;
        inv.caseId = inv.caseId || (d.scenarios[0] && d.scenarios[0].case_id);
        renderAll();
    }).catch(e => { inv.error = `Could not load scenarios: ${e.message}`; renderAll(); });
    renderAll();
}

function renderAll() {
    renderControls(); renderTx(); renderTrace(); renderGraph(); renderFinal(); renderClaims();
    renderEvidence(); renderRisk(); renderQuality(); renderConsistency(); renderAlerts(); renderSeedBatch();
}

// ---------------------------------------------------------------- controls
function renderControls() {
    const box = document.getElementById("inv-controls");
    if (!box) return;
    const busy = inv.starting || (inv.run && isRunning(inv.run));
    const select = el("select", { id: "inv-case", disabled: busy, onchange: e => { inv.caseId = e.target.value; resetRun(); renderAll(); } },
        currentList().map(s => el("option", { value: s.case_id, selected: s.case_id === inv.caseId }, s.name)));
    const start = el("button", { class: "btn-primary inv-start", type: "button", disabled: busy || !inv.caseId, onclick: startRun },
        busy ? "Investigating…" : (inv.run && inv.run.state === "failed" ? "Retry investigation" : "Start investigation"));
    const replay = el("button", { class: "page-btn", type: "button", disabled: !inv.run || isRunning(inv.run) || !(inv.run.events || []).length, onclick: startReplay },
        "▶ Replay recorded trace");
    const exportBtn = el("button", { class: "page-btn", type: "button", disabled: !inv.runId || !inv.run || isRunning(inv.run), onclick: exportTrace,
        title: "Redacted JSON of the recorded audit trail" }, "⬇ Export trace");
    const source = el("select", { id: "inv-source", disabled: busy, "aria-label": "Data source", title: "Data source", onchange: e => switchSource(e.target.value) },
        el("option", { value: "scenarios", selected: inv.source === "scenarios" }, "Hand-built scenarios"),
        el("option", { value: "seed", selected: inv.source === "seed" }, "FRAML data seed"));
    const kids = [el("label", { class: "inv-label" }, "Data"), source, el("label", { class: "inv-label" }, "Case"), select, start, replay, exportBtn, runBadges()];
    if (inv.error) kids.push(el("div", { class: "inv-error", role: "alert" }, inv.error));
    box.replaceChildren(...kids);
}

function runBadges() {
    const wrap = el("div", { class: "inv-badges" });
    const r = inv.run;
    if (!r) return wrap;
    if (inv.replayCount != null) wrap.append(el("span", { class: "inv-tag recorded" }, "Recorded replay – no inference"));
    else if (!isRunning(r)) wrap.append(el("span", { class: "inv-tag fresh" }, "Fresh run"));
    wrap.append(el("span", { class: "inv-tag state-" + r.state }, `State: ${r.state}`));
    const hdr = r.run_header;
    if (hdr && hdr.architecture === "team") wrap.append(el("span", { class: "inv-tag", title: Object.keys(hdr.roster).map(k => AGENT_LABELS[k]).join(", ") },
        `Agent team: orchestrator + ${Object.keys(hdr.roster).length} specialists` + (r.consultation_count != null ? ` · ${r.consultation_count} consultations` : "")));
    const mc = r.run_header && r.run_header.model_configuration;
    if (mc) wrap.append(el("span", { class: "inv-tag" + (r.failure ? " bad" : "") }, r.failure ? "Provider unavailable" : `${r.run_header.run_mode}: ${mc.provider} / ${mc.requested_model || "n/a"}`));
    if (r.recorded_audit_trail_verified === true) wrap.append(el("span", { class: "inv-tag" }, "Recorded audit trail – hash chain verified"));
    return wrap;
}

async function exportTrace() {
    try {
        const data = await invApi(`/api/investigations/${inv.runId}/export`);
        const url = URL.createObjectURL(new Blob([json(data)], { type: "application/json" }));
        const a = el("a", { href: url, download: `evidencetrail-${inv.runId}.json` });
        document.body.append(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    } catch (e) { inv.error = `Export failed: ${e.message}`; renderControls(); }
}

async function switchSource(source) {
    inv.source = source;
    resetRun();
    if (source === "seed" && !inv.seedCases.length) {
        inv.seedLoading = true; renderAll();
        try {
            const d = await invApi("/api/evidencetrail/seed/transactions");
            inv.seedCases = d.items; inv.seedNote = d.available ? d.note : d.note;
            if (!d.available) inv.error = d.note;
        } catch (e) { inv.error = `Could not load seed transactions: ${e.message}`; }
        inv.seedLoading = false;
    }
    const list = currentList();
    inv.caseId = list.length ? list[0].case_id : null;
    renderAll();
}

function resetRun() {
    stopReplay(); clearInterval(inv.pollTimer);
    Object.assign(inv, { run: null, runId: null, selected: [], reviewOpen: false, contextOpen: false, error: null });
}

async function startRun() {
    if (inv.starting || (inv.run && isRunning(inv.run))) return; // prevent duplicate starts
    resetRun(); inv.starting = true; renderAll();
    try {
        const d = await invApi("/api/investigations", { caseId: inv.caseId, configuration: {} });
        inv.runId = d.runId;
        inv.run = { state: "queued", events: [], evidence: [] };
        inv.starting = false;
        pollRun();
    } catch (e) {
        inv.starting = false; inv.error = `Could not start investigation: ${e.message}`;
    }
    renderAll();
}

function pollRun() {
    clearInterval(inv.pollTimer);
    const tick = async () => {
        try {
            inv.run = await invApi(`/api/investigations/${inv.runId}`);
            const evalRunning = inv.run.evaluation && inv.run.evaluation.state === "running";
            if (!isRunning(inv.run) && !evalRunning) { clearInterval(inv.pollTimer); loadAlerts(); }
        } catch (e) { inv.error = `Lost contact with the run: ${e.message}`; clearInterval(inv.pollTimer); }
        renderAll();
    };
    inv.pollTimer = setInterval(tick, 900);
    tick();
}

// ---------------------------------------------------------------- recorded replay (no network)
function startReplay() {
    stopReplay();
    inv.replayCount = 0; inv.selected = []; renderAll();
    const total = (inv.run.events || []).length;
    inv.replayTimer = setInterval(() => {
        inv.replayCount += 1;
        if (inv.replayCount >= total) stopReplay();
        renderAll();
    }, 700);
}
function stopReplay() {
    clearInterval(inv.replayTimer); inv.replayTimer = null;
    inv.replayCount = null;
}

// ---------------------------------------------------------------- transaction + final
function renderTx() {
    const box = document.getElementById("inv-tx");
    if (!box) return;
    const s = findCase(inv.caseId);
    if (!s) { box.replaceChildren(el("h3", {}, "Transaction"), el("p", { class: "inv-muted" }, inv.seedLoading ? "Loading seed transactions…" : "Pick a case to begin.")); return; }
    const t = Object.assign({}, s.transaction, runTransaction() || {});
    const rows = [["Transaction", t.transaction_id], ["Customer", t.customer_id], ["Recipient", t.recipient_name || t.recipient_id], ["Channel", t.channel]];
    if (t.transaction_type) rows.push(["Type", t.transaction_type.replaceAll("_", " ").toLowerCase()]);
    if (t.recipient_category) rows.push(["Recipient kind", `${t.recipient_category.toLowerCase()} · ${t.recipient_country || "n/a"}`]);
    if (t.payment_reference) rows.push(["Reference", t.payment_reference]);
    rows.push(["Time (UTC)", t.timestamp]);
    box.replaceChildren(el("h3", {}, "Transaction summary"), el("div", { class: "inv-amount" }, fmtMoney(t.amount, t.currency)), kv(rows),
        el("span", { class: "inv-tag" + (inv.source === "seed" ? " recorded" : "") }, inv.source === "seed" ? "FRAML data seed (synthetic)" : "Hand-built scenario (synthetic)"),
        el("p", { class: "inv-muted" }, inv.source === "seed"
            ? "A real row from the project's data seed. The agents see only what happened before this transaction; the generator's answer key stays hidden until the run is over."
            : "Synthetic scenario. Expected outcomes are hidden from the agent."));
}

function kv(pairs) {
    return el("dl", { class: "inv-kv" }, pairs.map(([k, v]) => [el("dt", {}, k), el("dd", {}, v == null ? "–" : String(v))]));
}

function renderFinal() {
    const box = document.getElementById("inv-final");
    if (!box) return;
    box.replaceChildren(el("h3", {}, "Recommendation"));
    const r = inv.run;
    if (!r) { box.append(el("p", { class: "inv-muted" }, "Start an investigation to see a recommendation.")); return; }
    if (isRunning(r) && inv.replayCount == null) { box.append(el("p", { class: "inv-muted" }, "Investigation in progress…")); return; }
    if (!finalVisible()) { box.append(el("p", { class: "inv-muted" }, "No decision yet.")); return; }
    const f = r.final;
    const incomplete = f.status === "INCOMPLETE";
    box.append(el("div", { class: "inv-decision act-" + f.simulated_action },
        el("div", { class: "inv-decision-action" }, `${ACTION_TEXT[f.simulated_action] || f.simulated_action}`),
        el("div", { class: "inv-muted" }, "Simulated intervention – no real money moved or blocked")));
    if (incomplete) box.append(el("div", { class: "inv-warn", role: "alert" }, "Investigation incomplete – routed to review. Missing evidence is not treated as reassuring. ", f.explanation));
    else box.append(el("p", { class: "inv-explain" }, f.explanation));
    if (r.failure && !(f.explanation || "").includes(r.failure)) box.append(el("div", { class: "inv-error", role: "alert" }, r.failure));
    box.append(...alertBanner(r));
    if (r.seed_ground_truth && !isRunning(r) && inv.replayCount == null) {
        const g = r.seed_ground_truth, said = f.simulated_action !== "ALLOW";
        box.append(el("details", { class: "inv-details" }, el("summary", {}, "Seed answer key (hidden from the agents)"),
            kv([["Generator tag", g.tag || "none: ordinary activity"], ["Seed says suspicious", g.flagged ? "yes" : "no"],
                ["System flagged it", said ? `yes (${ACTION_TEXT[f.simulated_action]})` : "no (Allow)"],
                ["Verdict", g.flagged === said ? "agrees with the seed" : (g.flagged ? "missed (nothing suspicious was knowable at that moment, or the policy thresholds did not fire)" : "false alarm")]]),
            el("p", { class: "inv-muted" }, "Tags come from the synthetic data generator. They say nothing about real-world accuracy.")));
    }
    const actions = el("div", { class: "inv-actions" });
    if (f.simulated_action === "ALLOW") actions.append(el("button", { class: "btn-primary", type: "button", onclick: () => { inv.reviewOpen = !inv.reviewOpen; renderFinal(); } }, inv.reviewOpen ? "Hide decision" : "View decision"));
    if (f.simulated_action === "CONTEXT_CHECK" || (f.context_check && f.context_check.answer)) actions.append(el("button", { class: "btn-primary", type: "button", onclick: () => { inv.contextOpen = !inv.contextOpen; renderFinal(); } }, "Open context check"));
    if (f.simulated_action === "REVIEW") actions.append(el("button", { class: "btn-primary", type: "button", onclick: () => { inv.reviewOpen = !inv.reviewOpen; renderFinal(); } }, inv.reviewOpen ? "Close case" : "Review case"));
    if (r.state === "failed" || incomplete) actions.append(el("button", { class: "page-btn", type: "button", onclick: startRun }, "Retry"));
    box.append(actions);
    if (inv.contextOpen && f.context_check) box.append(contextCheck(f));
    if (inv.reviewOpen) box.append(decisionDetails(f));
    box.append(el("details", { class: "inv-details" }, el("summary", {}, "Technical details"),
        kv([["Policy version", f.policy_version], ["Rule", f.rule], ["Reason code", f.reason_code], ["Status", f.status],
            ["Agent recommended", f.agent_recommendation && f.agent_recommendation.recommended_action],
            ["Agent vs policy", f.agent_escalation ? "agent was more cautious and was kept (escalation enabled)" :
                f.agent_disagreement === "agent_more_cautious" ? "agent was more cautious; policy took precedence" :
                f.agent_disagreement === "agent_less_cautious" ? "agent was less cautious; policy took precedence" : "agree"],
            ["Reference validity", f.reference_validity ? `${f.reference_validity.valid}/${f.reference_validity.cited} cited IDs exist` : "n/a"]]),
        el("p", { class: "inv-muted" }, "Valid evidence IDs do not establish that a claim is semantically supported.")));
}

function contextCheck(f) {
    const cc = f.context_check;
    const box = el("div", { class: "inv-context" }, el("p", { class: "inv-question" }, cc.question));
    if (cc.answer) { box.append(el("p", {}, `Simulated customer answer: ${cc.answer}.`)); return box; }
    const answer = async a => {
        try { await invApi(`/api/investigations/${inv.runId}/context-answer`, { answer: a }); inv.run = await invApi(`/api/investigations/${inv.runId}`); }
        catch (e) { inv.error = e.message; }
        renderAll();
    };
    box.append(el("div", { class: "inv-actions" },
        el("button", { class: "page-btn", type: "button", onclick: () => answer("yes") }, "Simulate answer: Yes"),
        el("button", { class: "page-btn", type: "button", onclick: () => answer("no") }, "Simulate answer: No")),
        el("p", { class: "inv-muted" }, "“No” does not clear the other supported signals."));
    return box;
}

function decisionDetails(f) {
    const signals = Object.entries(f.signals || {});
    return el("div", { class: "inv-review" }, el("h4", {}, "Supported signals"),
        signals.length ? signals.map(([k, v]) => el("div", { class: "inv-signal" }, el("strong", {}, k.replaceAll("_", " ")), ` – ${v.detail} `, v.evidence_ids.map(i => chip(i))))
            : el("p", { class: "inv-muted" }, "No elevated signals were supported by recorded evidence."));
}

// ---------------------------------------------------------------- trace
// ---------------------------------------------------------------- plain-language evidence
// Bank staff should never have to read field names or JSON. Each evidence record is turned into a one-line
// finding, a few labelled facts and short lists. The raw record stays under "Technical details".
const EVIDENCE_LABEL = {
    behavior_profile: "Customer behavior", device_inspection: "Device and session", recipient_inspection: "Recipient account",
    relationship_graph: "Recipient relationships", jev_assessment: "Jev risk assessment", alert_triage: "Jev alert triage",
    tool_error: "A check that could not be completed",
};
const CHECK_LABEL = {
    get_behavior_profile: "customer behavior", inspect_device: "device and session", inspect_recipient: "recipient account",
    search_relationship_graph: "recipient relationships", assess_with_jev: "Jev risk assessment", alert_triage: "Jev alert triage",
};
const CHECK_PURPOSE = {
    get_behavior_profile: "To see whether the amount and the recipient fit this customer's normal behavior.",
    inspect_device: "To see whether the payment came from a familiar device and a normal session.",
    inspect_recipient: "To see how old and how active the receiving account is.",
    search_relationship_graph: "To see whether the recipient is connected to other customers, devices or flagged accounts.",
    assess_with_jev: "To get Jev's structured judgment on the evidence gathered so far.",
};
const ANOMALY_TEXT = {
    ip_country_differs_from_profile: "Signed in from a country that is not the customer's usual one",
    rapid_country_change: "The location jumped to another country within minutes",
    device_seen_on_other_customers: "The same device has been used by other customers",
    repeated_micro_charges: "Several tiny, test-sized charges in a short time (typical of card testing)",
    follows_micro_charge_probing: "A larger charge straight after tiny test charges (typical of card testing)",
    issuer_declined_as_suspected_fraud: "The card issuer declined a charge as suspected fraud",
    remote_access_tool_detected: "A remote-access tool was running on the device",
    login_from_new_country: "Signed in from a new country",
};
const CHANNEL_TEXT = { WEB_PORTAL: "online banking (web)", MOBILE_APP: "mobile app", BRANCH_TELLER: "branch", ATM: "ATM", SWIFT: "international wire", ACH: "bank transfer" };
const ENTRY_TEXT = { CNP_ECOMMERCE: "card not present (online purchase)", CHIP_EMV: "card chip", CONTACTLESS: "contactless card", MAGSTRIPE: "magnetic stripe" };
function howPaid(auth) {
    return String(auth || "").split(" / ").map(x => CHANNEL_TEXT[x] || ENTRY_TEXT[x] || words(x)).join(", ");
}
const NEXT_STEP_TEXT = { CHECK_BEHAVIOR: "check the customer's behavior", CHECK_DEVICE: "check the device and session",
    CHECK_RECIPIENT: "check the recipient account", CHECK_GRAPH: "check the recipient's connections", FINISH: "finish: enough has been checked" };

const sentence = s => s.charAt(0).toUpperCase() + s.slice(1);
const words = s => String(s || "").replaceAll("_", " ").toLowerCase();
const shortTime = ts => (ts || "").replace("T", " ").slice(0, 16);
const plural = (n, one, many) => `${n} ${n === 1 ? one : (many || one + "s")}`;
const currentTx = () => Object.assign({}, (findCase(inv.caseId) || {}).transaction, runTransaction() || {});

function ageText(days) {
    if (days == null) return null;
    if (days < 1 / 24) return "under an hour";
    if (days < 1) return plural(Math.round(days * 24), "hour");
    return plural(Math.round(days), "day");
}

function anomalyText(a) {
    const base = ANOMALY_TEXT[a.type] || sentence(words(a.type));
    const detail = a.detail && !/^[A-Z0-9_]+$/.test(a.detail) ? ` (${a.detail})` : "";
    return `${a.severity === "meaningful" ? "Important" : "Minor"}: ${base}${detail}.`;
}

function entityLabel(id, kinds, tx) {
    if (id === tx.recipient_id) return tx.recipient_name ? `the recipient (${tx.recipient_name})` : "the recipient";
    const kind = kinds[id];
    return kind === "customer" ? `customer ${id}` : kind === "device" ? `device ${id}` : kind === "account" ? `account ${id}` : id;
}

function linkSentence(l, kinds, flagged, tx) {
    const prov = l.provenance ? ` (transaction ${l.provenance.record_id}, ${shortTime(l.provenance.observed_at)})` : "";
    let text;
    if (l.via === "also_paid_recipient") text = `${sentence(entityLabel(l.to, kinds, tx))} also paid this recipient`;
    else if (l.via === "used_device") text = `${sentence(entityLabel(l.from, kinds, tx))} used ${entityLabel(l.to, kinds, tx)}`;
    else if (l.via === "shared_device") text = `${sentence(entityLabel(l.from, kinds, tx))} shares a device with ${entityLabel(l.to, kinds, tx)}`;
    else text = `${sentence(entityLabel(l.from, kinds, tx))} is connected to ${entityLabel(l.to, kinds, tx)} (${words(l.via)})`;
    const flaggedEnd = [l.from, l.to].filter(x => flagged.includes(x));
    return text + prov + (flaggedEnd.length ? `. Already flagged by the rule engine: ${flaggedEnd.join(", ")}` : "") + ".";
}

// returns { headline, rows: [[label, value]], lists: [{ title, items }] }
function evidenceFacts(ev) {
    const p = ev.payload || {}, tx = currentTx(), rows = [], lists = [];
    const cur = tx.currency || p.currency || "";
    switch (ev.type) {
    case "behavior_profile": {
        const amount = Number(tx.amount), max = p.typical_amount_max, min = p.typical_amount_min;
        const known = (p.known_recipient_ids || []).includes(tx.recipient_id);
        const cmp = !isFinite(amount) || max == null ? null : (amount > max ? `${(amount / Math.max(max, 0.01)).toFixed(1)}× the usual maximum` : (amount < min ? "below the usual minimum" : "within the usual range"));
        rows.push(["Usual payment size", `${fmtMoney(min, cur)} to ${fmtMoney(max, cur)}`]);
        if (cmp) rows.push(["This transfer", `${fmtMoney(amount, cur)}: ${cmp}`]);
        rows.push(["Recipients the customer has paid before", String((p.known_recipient_ids || []).length)]);
        rows.push(["Is this recipient one of them?", known ? "Yes" : "No, this is a new recipient for the customer"]);
        if (p.history_summary) rows.push(["Recent history", sentence(p.history_summary)]);
        if (p.declared_max_single_transaction) rows.push(["Largest single payment the customer declared", fmtMoney(p.declared_max_single_transaction, cur)]);
        const inb = p.recent_inbound_48h;
        if (inb) rows.push(["Money received in the last 2 days", inb.count ? `${plural(inb.count, "deposit")}, ${fmtMoney(inb.total_usd, "USD")} in total (largest ${fmtMoney(inb.largest_usd, "USD")})` : "None"]);
        if (p.range_basis) rows.push(["How the usual range was worked out", sentence(p.range_basis)]);
        return { headline: `Usually pays ${fmtMoney(min, cur)} to ${fmtMoney(max, cur)}; ${known ? "has paid this recipient before" : "has not paid this recipient before"}${cmp ? `. This transfer is ${cmp}` : ""}.`, rows, lists };
    }
    case "device_inspection": {
        if (p.telemetry_available === false) {
            rows.push(["Device information", "Not recorded for this channel"], ["Bank authorization", p.authorization_status === "AUTHORIZED" ? "Authorized" : sentence(words(p.authorization_status))]);
            return { headline: "No device information is recorded for this channel, which is neither reassuring nor alarming on its own.", rows, lists };
        }
        const an = p.session_anomalies || [], important = an.filter(a => a.severity === "meaningful").length;
        rows.push(["Device", p.device_known ? "Familiar: the customer has used it before" : "New for this customer" + (p.device_first_seen_hours_ago != null ? ` (first seen ${p.device_first_seen_hours_ago < 1 ? "under an hour" : Math.round(p.device_first_seen_hours_ago) + " hours"} before this transfer)` : "")]);
        if (p.ip_country) rows.push(["Signed in from", `${p.ip_country}${p.profile_ip_country ? ` (the customer's usual country is ${p.profile_ip_country})` : ""}`]);
        if (p.authentication) rows.push(["How the payment was made", sentence(howPaid(p.authentication))]);
        if (p.authorization_status) rows.push(["Bank authorization", p.authorization_status === "AUTHORIZED" ? "Authorized" : p.authorization_status.startsWith("DECLINED") ? "Declined by the card issuer as suspected fraud" : sentence(words(p.authorization_status))]);
        if (an.length) lists.push({ title: "Warning signs", items: an.map(anomalyText) });
        return { headline: `${p.device_known ? "A device the customer has used before" : "A device the customer has not used before"}; ${an.length ? `${plural(an.length, "warning sign")}${important ? `, ${important} important` : ""}` : "no warning signs"}.`, rows, lists };
    }
    case "recipient_inspection": {
        const age = ageText(p.account_age_days), n = p.incoming_transfers_last_90_min;
        if (tx.recipient_name || p.category) rows.push(["Recipient", [tx.recipient_name, p.category && `${words(p.category)}${p.country ? ", " + p.country : ""}`].filter(Boolean).join(" · ")]);
        rows.push(["Account age", age ? `${age}${p.age_basis && p.age_basis.startsWith("payee_first") ? "" : ""}` : "Not recorded"]);
        rows.push(["Transfers received in the last 90 minutes", String(n)]);
        if (p.distinct_other_payers_before != null) rows.push(["Other customers who have paid them", String(p.distinct_other_payers_before)]);
        if (p.flagged_share_of_payers) rows.push(["Already-flagged customers among those payers", p.flagged_share_of_payers.endsWith("/0") ? "No other customers have paid them yet" : p.flagged_share_of_payers.replace("/", " of ") + (p.prior_synthetic_flags ? ": a significant share" : ": not a significant share")]);
        else if (p.prior_synthetic_flags != null) rows.push(["Earlier fraud flags on this recipient", String(p.prior_synthetic_flags)]);
        if (p.is_new_payee_for_customer != null) rows.push(["First payment from this customer?", p.is_new_payee_for_customer ? "Yes" : "No"]);
        return { headline: `${age ? `The recipient was first seen ${age} ago` : "The recipient's age is not recorded"}; ${plural(n, "transfer")} received in the last 90 minutes${p.prior_synthetic_flags ? "; linked to previously flagged customers" : ""}.`, rows, lists };
    }
    case "relationship_graph": {
        const nodes = p.nodes || [], links = p.links || [], flagged = p.synthetically_flagged_node_ids || [];
        const kinds = Object.fromEntries(nodes.map(n => [n.id, n.kind]));
        const customers = nodes.filter(n => n.kind === "customer"), devices = nodes.filter(n => n.kind === "device");
        rows.push(["How far the search went", `Up to ${plural(p.max_hops, "step")} from the recipient`]);
        rows.push(["Other customers connected to this recipient", customers.length ? `${customers.length} (${customers.slice(0, 6).map(n => n.id).join(", ")}${customers.length > 6 ? ", …" : ""})` : "None found"]);
        if (devices.length) rows.push(["Devices connected", String(devices.length)]);
        rows.push(["Already flagged by the rule engine", flagged.length ? flagged.join(", ") : "None"]);
        if (links.length) lists.push({ title: "Connections found", items: links.slice(0, 8).map(l => linkSentence(l, kinds, flagged, tx)).concat(links.length > 8 ? [`…and ${links.length - 8} more`] : []) });
        if (p.note) rows.push(["Please note", "These connections are indicators for an investigator to weigh. They are not proof that anyone is a criminal."]);
        return { headline: links.length ? `${plural(customers.length || links.length, customers.length ? "other customer" : "connection")} linked to this recipient${flagged.length ? `, ${flagged.length} already flagged` : ""}.` : `No connections to other customers, devices or flagged accounts were found within ${plural(p.max_hops, "step")}.`, rows, lists };
    }
    case "jev_assessment": {
        const n = p.normalized || {};
        if (n.recipient_risk) rows.push(["Recipient risk", RISK_TEXT[n.recipient_risk] || n.recipient_risk]);
        if (n.evidence_sufficiency) rows.push(["Enough evidence to recommend?", n.evidence_sufficiency === "SUFFICIENT_FOR_RECOMMENDATION" ? "Yes, enough to recommend" : "No, more evidence is needed"]);
        if (n.next_step) rows.push(["Suggested next step", NEXT_STEP_TEXT[n.next_step] || words(n.next_step)]);
        if (n.manipulation_indicators != null) rows.push(["Signs the payer is being manipulated", `${Number(n.manipulation_indicators).toFixed(2)} on a 0 to 1 scale (higher means more consistent with manipulation)`]);
        rows.push(["Based on", (p.input_evidence_ids || []).join(", ") || "the evidence supplied"], ["Please note", "Jev's scores are model judgments, not calibrated fraud probabilities, and Jev never decides the outcome by itself."]);
        return { headline: n.recipient_risk ? `Jev rates the recipient risk as ${(RISK_TEXT[n.recipient_risk] || n.recipient_risk).toLowerCase()}${n.manipulation_indicators != null ? `; signs of payer manipulation ${Number(n.manipulation_indicators).toFixed(2)} on a 0 to 1 scale` : ""}.` : "Jev's structured judgment on the evidence gathered.", rows, lists };
    }
    case "alert_triage": {
        if (p.status !== "ok") return { headline: p.status === "skipped" ? "Jev triage was skipped because no evidence had been gathered." : "Jev triage could not be completed.", rows: [["Why", p.reason || "unknown"]], lists };
        const sev = ["Routine", "Notable", "Serious"][p.severity_level] || "unrated";
        return { headline: `Jev finds the case ${words(p.suspicion)}; urgency: ${sev.toLowerCase()}.`, rows: [["Jev's view", sentence(words(p.suspicion))], ["Urgency", sev]], lists };
    }
    case "tool_error": {
        rows.push(["Check", sentence(CHECK_LABEL[p.tool] || words(p.tool))], ["What went wrong", p.error || "unknown"], ["What this means", "Treated as missing evidence, never as reassurance."]);
        return { headline: `The ${CHECK_LABEL[p.tool] || "check"} could not be completed. ${p.error || ""}`.trim(), rows, lists };
    }
    default:
        return { headline: sentence(words(ev.type)), rows: [["Source", ev.source]], lists };
    }
}

function factsView(facts) {
    return [el("p", { class: "inv-headline" }, facts.headline), kv(facts.rows),
        facts.lists.map(l => [el("h4", {}, l.title), el("ul", { class: "inv-facts" }, l.items.map(i => el("li", {}, i)))])];
}

function foundLine(e) {
    if (!["tool_call", "tool_error"].includes(e.event_type)) return null;
    const ev = evidenceById((e.output_evidence_ids || [])[0]);
    return ev ? evidenceFacts(ev).headline : null;
}

function whyLine(e) {
    const text = e.brief_justification;
    switch (e.event_type) {
    case "consultation": return ["Asked", text];
    case "specialist_report": return ["Reported", text];
    case "final_decision": return ["Decision basis", text];
    case "tool_call": case "tool_error": return ["Why", text || CHECK_PURPOSE[e.tool_name]];
    case "run_failed": return ["What happened", text];
    case "alert_triage": case "alert_created": case "alert_not_created": return ["Basis", text];
    default: return [null, null];
    }
}

function renderTrace() {
    const box = document.getElementById("inv-trace");
    if (!box) return;
    box.replaceChildren(el("h3", {}, "Investigation trace"));
    const events = visibleEvents().filter(e => e.event_type !== "model_turn");
    if (!events.length) { box.append(el("p", { class: "inv-muted" }, inv.run ? "Waiting for the first step…" : "No investigation yet.")); return; }
    const list = el("ol", { class: "inv-timeline" });
    events.forEach((e, idx) => {
        const isErr = e.event_type === "tool_error" || e.event_type === "run_failed";
        const title = e.event_type === "run_started" ? "Investigation started" : e.event_type === "run_failed" ? "Investigation stopped"
            : e.event_type === "final_decision" ? "Policy decision" : e.event_type === "alert_created" ? "Alert created"
            : e.event_type === "alert_not_created" ? "No alert raised"
            : e.event_type === "consultation" ? `Orchestrator asked ${AGENT_LABELS[e.validated_arguments.specialist] || e.validated_arguments.specialist}`
            : e.event_type === "specialist_report" ? `${AGENT_LABELS[e.agent] || e.agent} reported findings`
            : (TOOL_LABELS[e.tool_name] || e.tool_name);
        const why = whyLine(e), found = foundLine(e);
        const li = el("li", { class: "inv-step" + (isErr ? " err" : "") },
            el("div", { class: "inv-step-head" }, el("span", { class: "inv-step-n", title: `trace event ${e.sequence}` }, idx + 1), el("strong", {}, title),
                e.agent && e.agent !== "investigator" && e.event_type !== "consultation" ? el("span", { class: "inv-tag agent-" + e.agent }, AGENT_LABELS[e.agent] || e.agent) : null,
                isErr ? el("span", { class: "inv-tag bad" }, "could not be completed") : null,
                e.duration_ms != null ? el("span", { class: "inv-muted" }, ` ${e.duration_ms} ms`) : null),
            why[1] ? el("div", { class: "inv-why" }, el("span", { class: "inv-why-label" }, why[0] + ": "), why[1]) : null,
            found ? el("div", { class: "inv-found" }, el("span", { class: "inv-why-label" }, "Found: "), found) : null,
            el("div", { class: "inv-chips" }, (e.input_evidence_ids || []).length ? el("span", { class: "inv-muted" }, "used ") : null,
                (e.input_evidence_ids || []).map(i => chip(i)),
                (e.output_evidence_ids || []).length ? el("span", { class: "inv-muted" }, " produced ") : null,
                (e.output_evidence_ids || []).map(i => chip(i))),
            el("details", { class: "inv-details" }, el("summary", {}, "Technical details"),
                el("pre", { class: "inv-pre" }, json({ arguments: e.validated_arguments, result: e.result_snapshot, error: e.error,
                    provider: e.provider, returned_model_version: e.returned_model_version, reason_code: e.reason_code, event_hash: e.event_hash }))));
        list.append(li);
    });
    box.append(list);
}

// ---------------------------------------------------------------- hand-off to the ADK specialist team
const HANDOFF_SOURCE = {
    adk_agents: "Written by the ADK specialist agents",
    specialist_tools_fallback: "Synthesized from the specialist data tools (no LLM ran)",
};

function handoffButton(a) {
    const h = a.handoff;
    if (h && h.status === "running") return el("button", { class: "page-btn", type: "button", disabled: true }, "ADK team investigating…");
    return el("button", { class: "page-btn", type: "button", onclick: () => startHandoff(a.alert_id) },
        h ? "Hand off again" : "Hand off to ADK team");
}

function handoffBlock(a) {
    const out = [], h = a.handoff, ask = inv.handoffAsk[a.alert_id];
    if (ask) {
        const input = el("input", { type: "text", placeholder: "FRAML customer ID, e.g. CUST-00015", "aria-label": "FRAML customer ID", class: "inv-input" });
        out.push(el("div", { class: "inv-warn", role: "alert" }, ask,
            el("div", { class: "inv-actions" }, input,
                el("button", { class: "page-btn", type: "button", onclick: () => startHandoff(a.alert_id, input.value.trim()) }, "Send"),
                el("button", { class: "page-btn", type: "button", onclick: () => { delete inv.handoffAsk[a.alert_id]; renderAlerts(); } }, "Cancel"))));
    }
    if (!h) return out;
    if (h.status === "running") out.push(el("div", { class: "inv-muted" }, `ADK investigation team is reviewing ${h.customer_id}…`));
    else if (h.status === "failed") out.push(el("div", { class: "inv-error", role: "alert" }, `Hand-off failed (${h.error}). It can be retried.`));
    else out.push(el("details", { class: "inv-details" },
        el("summary", {}, `ADK team report for ${h.customer_id} · ${h.risk_tier || "tier n/a"}`),
        el("span", { class: "inv-tag" + (h.report_source === "adk_agents" ? " fresh" : "") }, HANDOFF_SOURCE[h.report_source] || h.report_source),
        el("div", { class: "inv-muted" }, h.note),
        h.customer_mismatch ? el("div", { class: "inv-warn", role: "note" }, `Customer chosen manually: the alert's transfer is not in ${h.customer_id}'s transaction history, so this is a customer-level review only.`) : null,
        el("pre", { class: "inv-pre" }, h.report)));
    return out;
}

async function startHandoff(alertId, customerId) {
    inv.alertsError = null;
    try {
        await invApi(`/api/evidencetrail/alerts/${alertId}/handoff`, customerId ? { customerId } : {});
        delete inv.handoffAsk[alertId];
    } catch (e) {
        if (e.status === 409 && e.data && e.data.needs_customer_id) inv.handoffAsk[alertId] = e.message;
        else inv.alertsError = `Hand-off failed: ${e.message}`;
    }
    loadAlerts();
}

// ---------------------------------------------------------------- relationship graph
function renderGraph() {
    const box = document.getElementById("inv-graph");
    if (!box) return;
    box.replaceChildren(el("h3", {}, "Recipient relationships"));
    const vis = visibleEvidenceIds();
    const ev = ((inv.run && inv.run.evidence) || []).filter(e => e.type === "relationship_graph" && vis.has(e.evidence_id)).pop();
    const recipient = (findCase(inv.caseId) || { transaction: {} }).transaction.recipient_id;
    if (!ev) { box.append(el("p", { class: "inv-muted" }, "Relationships not searched yet. The agent decides whether to check them.")); return; }
    const p = ev.payload, nodes = p.nodes || [], links = p.links || [];
    if (!links.length) {
        box.append(el("p", { class: "inv-muted" }, `No links found within ${p.max_hops} hop(s) of ${recipient}.`), chip(ev.evidence_id));
        return;
    }
    const depth = { [p.recipient_id]: 0 };
    links.forEach(l => { depth[l.to] = l.hops; });
    const cols = {};
    Object.keys(depth).forEach(id => { (cols[depth[id]] = cols[depth[id]] || []).push(id); });
    const pos = {};
    Object.entries(cols).forEach(([d, ids]) => ids.forEach((id, i) => { pos[id] = { x: 50 + d * 120, y: 40 + i * 60 }; }));
    const byId = Object.fromEntries(nodes.map(n => [n.id, n]));
    const svg = svgEl("svg", { viewBox: "0 0 330 150", class: "inv-svg", role: "img", "aria-label": "Recipient relationship graph" });
    links.forEach(l => {
        const a = pos[l.from], b = pos[l.to];
        if (!a || !b) return;
        const line = svgEl("line", { x1: a.x, y1: a.y, x2: b.x, y2: b.y, class: "inv-edge" }, svgEl("title", {}, `${l.via} · provenance ${l.provenance.record_id} (${l.provenance.source})`));
        svg.append(line, svgEl("text", { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 - 4, class: "inv-edge-label", "text-anchor": "middle" }, l.via.replace("_", " ")));
    });
    Object.keys(pos).forEach(id => {
        const n = byId[id] || {}, flagged = !!n.synthetic_flag;
        const g = svgEl("g", { class: "inv-node" + (flagged ? " flagged" : "") + (id === p.recipient_id ? " root" : ""), tabindex: 0, style: "cursor:pointer" },
            svgEl("circle", { cx: pos[id].x, cy: pos[id].y, r: 14 }),
            svgEl("text", { x: pos[id].x, y: pos[id].y + 28, "text-anchor": "middle" }, id),
            svgEl("title", {}, `${n.kind || "node"}${flagged ? " – synthetically flagged" : ""}`));
        g.addEventListener("click", () => selectEvidence([ev.evidence_id]));
        svg.append(g);
    });
    box.append(svg, el("p", { class: "inv-muted" }, "Links are indicators from synthetic data, not proof that anyone is a criminal. Hover an edge for its provenance."), chip(ev.evidence_id));
}

// ---------------------------------------------------------------- claims + evidence
function renderClaims() {
    const box = document.getElementById("inv-claims");
    if (!box) return;
    box.replaceChildren(el("h3", {}, "Claims"));
    if (!finalVisible() || !inv.run.final.claims.length) { box.append(el("p", { class: "inv-muted" }, "Claims appear with the final recommendation. Click one to see its supporting evidence.")); return; }
    inv.run.final.claims.forEach(c => {
        const active = c.supporting_evidence_ids.length && c.supporting_evidence_ids.every(i => inv.selected.includes(i));
        box.append(el("button", { class: "inv-claim" + (active ? " active" : ""), type: "button", onclick: () => selectEvidence(c.supporting_evidence_ids) },
            el("div", {}, c.text), el("div", { class: "inv-muted" }, `${c.claim_id} · cites ${c.supporting_evidence_ids.join(", ") || "nothing"}`),
            c.invalid_evidence_ids.length ? el("div", { class: "inv-error" }, `Invalid references: ${c.invalid_evidence_ids.join(", ")}`) : null));
    });
}

function renderEvidence() {
    const box = document.getElementById("inv-evidence");
    if (!box) return;
    box.replaceChildren(el("h3", {}, "Evidence details"));
    if (!inv.selected.length) { box.append(el("p", { class: "inv-muted" }, "Select an evidence ID, a claim or a graph node to see what was found, in plain language.")); return; }
    inv.selected.forEach(id => {
        const e = evidenceById(id);
        if (!e) { box.append(el("div", { class: "inv-error" }, `${id} was not found in this run.`)); return; }
        const facts = evidenceFacts(e);
        box.append(el("div", { class: "inv-evidence-item" },
            el("strong", {}, `${e.evidence_id} · ${EVIDENCE_LABEL[e.type] || sentence(words(e.type))}`),
            el("div", { class: "inv-muted" }, `Checked ${shortTime(e.observed_at)} UTC${CHECK_LABEL[e.source] ? ` · ${CHECK_LABEL[e.source]} check` : ""}`),
            factsView(facts),
            el("details", { class: "inv-details" }, el("summary", {}, "Technical details"),
                kv([["Evidence ID", e.evidence_id], ["Type", e.type], ["Source tool", e.source], ["Source record", e.source_record_id], ["Snapshot hash", e.snapshot_hash]]),
                el("pre", { class: "inv-pre" }, json(e.payload)))));
    });
}

// ---------------------------------------------------------------- risk assessment (Jev)
const RISK_TEXT = { LOW: "Low", ELEVATED: "Elevated", HIGH: "High", UNKNOWN: "Unknown – material evidence missing" };
function renderRisk() {
    const box = document.getElementById("inv-risk");
    if (!box) return;
    box.replaceChildren(el("h3", {}, "Risk assessment"));
    const vis = visibleEvidenceIds();
    const evs = ((inv.run && inv.run.evidence) || []).filter(e => vis.has(e.evidence_id));
    const jev = evs.filter(e => e.type === "jev_assessment").pop();
    const unavailable = evs.filter(e => e.type === "tool_error" && e.source === "assess_with_jev").pop();
    if (!jev) {
        box.append(el("p", { class: "inv-muted" }, unavailable ? `Jev assessment unavailable: ${unavailable.payload.error}` : "Jev was not consulted in this run."));
        return;
    }
    const n = jev.payload.normalized || {};
    box.append(kv([["Recipient risk", RISK_TEXT[n.recipient_risk] || n.recipient_risk || "not asked"],
        ["Enough evidence to recommend", n.evidence_sufficiency ? n.evidence_sufficiency.replaceAll("_", " ").toLowerCase() : "not asked"],
        ["Suggested next step", n.next_step ? n.next_step.replaceAll("_", " ").toLowerCase() : "not asked"],
        ["Manipulation indicators", n.manipulation_indicators != null ? String(n.manipulation_indicators) : "not asked"]]),
        chip(jev.evidence_id),
        el("p", { class: "inv-muted" }, "Jev informs the investigation; it never approves or blocks a transfer by itself. Probabilities are uncalibrated model outputs."),
        el("details", { class: "inv-details" }, el("summary", {}, "Technical details"), el("pre", { class: "inv-pre" }, json({ model: jev.payload.model, usage: jev.payload.usage, raw: jev.payload.raw }))));
}

// ---------------------------------------------------------------- explanation quality (G-Eval)
function renderQuality() {
    const box = document.getElementById("inv-quality");
    if (!box) return;
    box.replaceChildren(el("h3", {}, "Explanation quality"));
    const r = inv.run, done = r && !isRunning(r) && r.final;
    const evalState = r && r.evaluation;
    const evalRunning = evalState && evalState.state === "running";
    const passes = el("select", { id: "inv-judge-passes", disabled: !done || evalRunning, "aria-label": "Judge passes" },
        [1, 3, 5].map(n => el("option", { value: n, selected: n === (inv.judgePasses || 1) }, n === 1 ? "1 judge pass" : `${n} judge passes`)));
    passes.addEventListener("change", e => { inv.judgePasses = Number(e.target.value); });
    box.append(el("div", { class: "inv-actions" },
        el("button", { class: "page-btn", type: "button", disabled: !done || evalRunning, onclick: runEvaluation },
            evalRunning ? "Evaluating…" : (evalState ? "Re-run evaluation" : "Evaluate explanation")), passes));
    if (!evalState) { box.append(el("p", { class: "inv-muted" }, "Not evaluated yet. Scores come from G-Eval (a model-based judge), measured after the decision. Several judge passes show how much the judge itself varies.")); return; }
    if (evalRunning) { box.append(el("p", { class: "inv-muted" }, "Evaluation running…")); return; }
    if (evalState.state === "failed") { box.append(el("div", { class: "inv-error", role: "alert" }, evalState.error)); return; }
    Object.values(evalState.geval).forEach(m => {
        const row = el("div", { class: "inv-metric" }, el("strong", {}, m.label));
        if (m.status === "scored") {
            row.append(el("span", { class: "inv-score" + (m.passed ? " pass" : " fail") }, m.score.toFixed(2)));
            if (m.passes_attempted > 1) row.append(el("span", { class: "inv-muted" }, ` mean of ${m.passes_successful}/${m.passes_attempted} passes (range ${m.score_min.toFixed(2)}–${m.score_max.toFixed(2)})`));
            row.append(el("div", { class: "inv-muted" }, m.reason));
        } else row.append(el("span", { class: "inv-tag bad" }, m.status === "error" ? "Judge error" : "Unavailable"), el("div", { class: "inv-muted" }, m.reason));
        box.append(row);
    });
    const d = evalState.deterministic;
    box.append(el("h4", {}, "Deterministic checks"), kv([
        ["Matches policy label", d.policy_label_match == null ? "n/a" : (d.policy_label_match ? "yes" : "no") + " (1 synthetic case; illustrative label)"],
        ["Evidence references valid", d.reference_validity ? `${d.reference_validity.valid}/${d.reference_validity.cited}` : "n/a"],
        ["Tool calls", d.tool_call_count], ["Errors", d.error_count]]),
        d.seed_check ? kv([["Seed answer key", `${d.seed_check.seed_tag || "ordinary"} · ${d.seed_check.agrees ? "agrees" : "disagrees"} with the system`]]) : null,
        el("details", { class: "inv-details" }, el("summary", {}, "Technical details"),
            el("pre", { class: "inv-pre" }, json({ rubric_version: evalState.rubric_version, judge: evalState.judge, note: evalState.judge_note,
                scores: Object.fromEntries(Object.entries(evalState.geval).map(([k, m]) => [k, m.scores])),
                steps: Object.fromEntries(Object.entries(evalState.geval).map(([k, m]) => [k, m.evaluation_steps])) }))));
}

async function runEvaluation() {
    try { await invApi(`/api/investigations/${inv.runId}/evaluate`, { repeats: inv.judgePasses || 1 }); inv.run = await invApi(`/api/investigations/${inv.runId}`); pollRun(); }
    catch (e) { inv.error = `Evaluation failed to start: ${e.message}`; }
    renderAll();
}

// ---------------------------------------------------------------- decision consistency (read-only report)
// A recorded check, not a control: it is generated by `python -m evidencetrail.consistency`, once for a demo and
// periodically afterwards if the company decides to. Nothing here can start a run.
async function loadConsistency() {
    try {
        const d = await invApi("/api/evidencetrail/consistency");
        inv.reports = d.reports; inv.report = d.latest; inv.reportCmd = d.run_command; inv.reportError = null;
    } catch (e) { inv.reportError = `Could not load the consistency report: ${e.message}`; }
    renderConsistency();
}

async function openReport(id) {
    try { inv.report = await invApi(`/api/evidencetrail/consistency/${id}`); inv.reportError = null; }
    catch (e) { inv.reportError = `Could not open report: ${e.message}`; }
    renderConsistency();
}

function countsText(counts) {
    const parts = Object.entries(counts || {}).map(([k, n]) => `${n}× ${k.replace("CONTEXT_CHECK", "Context check").replace("ALLOW", "Allow").replace("REVIEW", "Review")}`);
    return parts.length ? parts.join(", ") : "–";
}

function renderConsistency() {
    const box = document.getElementById("inv-consistency");
    if (!box) return;
    const head = [el("h3", {}, "Decision consistency"),
        el("p", { class: "inv-muted" }, "A recorded check, not a button. It is generated once for the demo and can be repeated periodically (for example monthly) to confirm the decisions are still stable.")];
    box.replaceChildren(...head);
    if (inv.reportError) { box.append(el("div", { class: "inv-error", role: "alert" }, inv.reportError)); return; }
    const r = inv.report;
    if (!r) {
        box.append(el("p", { class: "inv-muted" }, "No report has been generated yet. To create one, run this on the server:"),
            el("pre", { class: "inv-pre" }, inv.reportCmd || "python -m evidencetrail.consistency"));
        return;
    }
    if ((inv.reports || []).length > 1) {
        box.append(el("select", { "aria-label": "Report", onchange: e => openReport(e.target.value) },
            inv.reports.map(m => el("option", { value: m.report_id, selected: m.report_id === r.report_id }, m.generated_at.replace("T", " ").slice(0, 16) + " UTC"))));
    }
    const c = r.configuration, o = r.overall;
    const allGood = o.fully_consistent === o.scenarios && o.failed_runs === 0;
    box.append(el("div", { class: "inv-decision " + (allGood ? "act-ALLOW" : "act-CONTEXT_CHECK") },
        el("div", { class: "inv-decision-action" }, `${o.fully_consistent} of ${o.scenarios} scenarios fully consistent`),
        el("div", { class: "inv-muted" }, `${o.match_policy_labels} of ${o.scenarios} match the illustrative policy labels · ${o.failed_runs} failed runs`)),
        kv([["Generated", r.generated_at.replace("T", " ").slice(0, 19) + " UTC"], ["Took", `${r.duration_s} s`],
            ["Fresh runs per scenario", c.repetitions], ["Agent model", `${c.agent_model_requested}${c.agent_models_returned.length ? " (returned " + c.agent_models_returned.join(", ") + ")" : ""}`],
            ["Jev model", `${c.jev_model_requested}${c.jev_models_returned.length ? " (returned " + c.jev_models_returned.join(", ") + ")" : ""}`],
            ["Code", c.code && c.code.commit ? c.code.commit.slice(0, 8) + (c.code.dirty ? " (uncommitted changes)" : "") : "unknown"],
            ["Versions", `policy ${c.versions.policy} · prompts ${c.versions.team_prompt}`]]));
    const table = el("table", { class: "inv-table" }, el("thead", {}, el("tr", {}, ["Scenario", "Expected", `${c.repetitions} fresh runs`, "Frozen evidence (decision · Jev)", "Result"].map(h => el("th", {}, h)))));
    const body = el("tbody");
    r.scenarios.forEach(e => {
        const f = e.fixed_evidence || {};
        body.append(el("tr", {},
            el("td", {}, e.name),
            el("td", {}, e.expected_action ? ACTION_TEXT[e.expected_action] : "–"),
            el("td", {}, countsText(e.repeat.outcome_counts) + (e.repeat.failed.length ? ` · ${e.repeat.failed.length} failed` : "")),
            el("td", {}, f.attempted ? `${countsText(f.outcome_counts)} · Jev ${f.jev_successful}/${f.jev_attempted}${f.all_agree ? " unanimous" : " varied"}` : "–"),
            el("td", {}, e.consistent ? "✓ consistent" : "⚠ varied", e.matches_policy_label ? "" : " · differs from label")));
    });
    table.append(body);
    box.append(el("div", { class: "inv-table-wrap" }, table));
    if (r.sensitivity && r.sensitivity.length) {
        box.append(el("h4", {}, "Does the decision follow the evidence?"));
        r.sensitivity.forEach(x => box.append(el("div", { class: "inv-muted" },
            `${x.change}: ${countsText(x.outcome_counts)} (was ${x.baseline_outcome ? x.baseline_outcome.replace("CONTEXT_CHECK", "Context check").replace("ALLOW", "Allow").replace("REVIEW", "Review") : "n/a"}) · ${x.action_changed ? "the action changed" : "no change"}`)));
        box.append(el("p", { class: "inv-muted" }, "A change shows sensitivity under this intervention; it does not prove causal correctness."));
    }
    if (r.ablation && r.ablation.arms) {
        const a = r.ablation.arms;
        box.append(el("h4", {}, "Approach comparison"),
            kv([["Rules only", `${a.rules.matched}/${a.rules.eligible} cases matched`],
                ["Agent team without Jev", `${a.no_jev.matched_runs}/${a.no_jev.eligible_runs} runs matched`],
                ["Agent team with Jev", `${a.with_jev.matched_runs}/${a.with_jev.eligible_runs} runs matched`]]));
    }
    box.append(el("p", { class: "inv-muted" }, r.interpretation),
        el("details", { class: "inv-details" }, el("summary", {}, "Technical details"), el("pre", { class: "inv-pre" }, json(r))),
        el("p", { class: "inv-muted" }, "Re-run on the server with: ", el("code", {}, inv.reportCmd || "python -m evidencetrail.consistency")));
}

// ---------------------------------------------------------------- alerts
function alertBanner(r) {
    const evs = visibleEvents();
    const created = evs.some(e => e.event_type === "alert_created");
    const none = evs.some(e => e.event_type === "alert_not_created");
    if (created && r.alert) {
        const a = r.alert;
        return [el("div", { class: "inv-alert sev-" + a.severity, role: "status" },
            el("div", { class: "inv-alert-head" }, el("strong", {}, `Alert raised · ${SEVERITY_TEXT[a.severity]} severity`),
                a.sources.map(src => el("span", { class: "inv-tag" }, SOURCE_TEXT[src])), el("span", { class: "inv-muted" }, a.alert_id)),
            el("div", {}, a.title), el("div", { class: "inv-muted" }, a.summary),
            a.disagreement ? el("div", { class: "inv-muted" }, DISAGREEMENT_TEXT[a.disagreement]) : null,
            r.alert_error ? el("div", { class: "inv-error", role: "alert" }, r.alert_error) : null,
            el("div", { class: "inv-muted" }, a.notice))];
    }
    if (none) return [el("div", { class: "inv-alert none" }, "No alert raised: neither Jev nor the deterministic policy flagged this case.")];
    return [];
}

async function loadAlerts() {
    try {
        const q = inv.alertFilter === "all" ? "" : `?status=${inv.alertFilter}`;
        inv.alerts = (await invApi(`/api/evidencetrail/alerts${q}`)).alerts; inv.alertsError = null;
    } catch (e) { inv.alertsError = `Could not load alerts: ${e.message}`; }
    renderAlerts();
}

async function setAlertStatus(id, status) {
    try { await invApi(`/api/evidencetrail/alerts/${id}/status`, { status }); }
    catch (e) { inv.alertsError = `Could not update alert: ${e.message}`; }
    loadAlerts();
}

function openAlertRun(a) {
    stopReplay(); clearInterval(inv.pollTimer);
    Object.assign(inv, { caseId: a.case_id, runId: a.run_id, run: { state: "running", events: [], evidence: [] }, selected: [], reviewOpen: false, contextOpen: false, error: null });
    pollRun(); renderAll();
    document.getElementById("inv-controls").scrollIntoView({ behavior: "smooth" });
}

function renderAlerts() {
    const box = document.getElementById("inv-alerts");
    if (!box) return;
    const filter = el("select", { "aria-label": "Alert filter", onchange: e => { inv.alertFilter = e.target.value; loadAlerts(); } },
        [["open", "Open"], ["acknowledged", "Acknowledged"], ["dismissed", "Dismissed"], ["all", "All"]].map(([v, t]) => el("option", { value: v, selected: v === inv.alertFilter }, t)));
    box.replaceChildren(el("div", { class: "inv-alert-bar" }, el("h3", {}, `Alert queue (${inv.alerts.length})`), filter),
        el("p", { class: "inv-muted" }, "Alerts are raised when Jev finds a finished investigation suspicious or the policy routes it away from Allow. They are notifications for an analyst and never move or block money."));
    if (inv.alertsError) box.append(el("div", { class: "inv-error", role: "alert" }, inv.alertsError));
    if (!inv.alerts.length) { box.append(el("p", { class: "inv-muted" }, "No alerts in this view.")); return; }
    const list = el("ul", { class: "inv-alert-list" });
    inv.alerts.forEach(a => {
        const name = (findCase(a.case_id) || {}).name || a.case_id;
        list.append(el("li", { class: "inv-alert-row sev-" + a.severity },
            el("div", { class: "inv-alert-head" }, el("strong", {}, a.title), el("span", { class: "inv-tag" }, SEVERITY_TEXT[a.severity]),
                a.sources.map(src => el("span", { class: "inv-tag" }, SOURCE_TEXT[src])), el("span", { class: "inv-tag" }, a.status)),
            el("div", { class: "inv-muted" }, `${name} · ${a.transaction.amount.toLocaleString("en-US")} ${a.transaction.currency} to ${a.transaction.recipient_id} · ${a.created_at.replace("T", " ").slice(0, 19)} UTC`),
            el("div", { class: "inv-muted" }, a.summary),
            a.disagreement ? el("div", { class: "inv-muted" }, DISAGREEMENT_TEXT[a.disagreement]) : null,
            handoffBlock(a),
            el("div", { class: "inv-actions" },
                el("button", { class: "page-btn", type: "button", onclick: () => openAlertRun(a) }, "Open investigation"),
                handoffButton(a),
                a.status === "open" ? el("button", { class: "page-btn", type: "button", onclick: () => setAlertStatus(a.alert_id, "acknowledged") }, "Acknowledge") : null,
                a.status !== "dismissed" ? el("button", { class: "page-btn", type: "button", onclick: () => setAlertStatus(a.alert_id, "dismissed") }, "Dismiss") : null)));
    });
    box.append(list);
    clearTimeout(inv.alertTimer);
    if (inv.alerts.some(x => x.handoff && x.handoff.status === "running")) inv.alertTimer = setTimeout(loadAlerts, 2000);
}

// ---------------------------------------------------------------- seed batch
function renderSeedBatch() {
    const box = document.getElementById("inv-seedbatch");
    if (!box) return;
    const busy = inv.seedExp && inv.seedExp.state === "running";
    const n = el("select", { id: "inv-seed-n", disabled: busy, "aria-label": "Batch size" }, [10, 20, 40, 58].map(v => el("option", { value: v, selected: v === 20 }, `${v} transactions`)));
    box.replaceChildren(el("h3", {}, "FRAML seed batch"),
        el("p", { class: "inv-muted" }, "Runs a mixed sample of real seed transactions through the agent team and Jev triage, then compares with the generator's hidden answer key. Counts only; a sample says nothing about real-world accuracy."),
        el("div", { class: "inv-actions" }, n, el("button", { class: "page-btn", type: "button", disabled: busy, onclick: startSeedBatch }, busy ? "Running…" : "Run seed batch")));
    const e = inv.seedExp;
    if (!e) return;
    if (e.error) { box.append(el("div", { class: "inv-error", role: "alert" }, e.error)); return; }
    const s = e.summary;
    if (!s) { box.append(el("p", { class: "inv-muted" }, "Starting runs…")); return; }
    const prog = e.progress ? `${e.progress.done}/${e.progress.total} finished` : "";
    const f = s.answer_key_flagged, c = s.answer_key_clean;
    box.append(el("span", { class: "inv-tag fresh" }, e.state === "running" ? `Running… ${prog}` : "Completed"),
        kv([["Attempted / completed / failed", `${s.attempted} / ${s.completed} / ${s.failed}` + (s.pending ? ` (${s.pending} pending)` : "")],
            ["Seed says suspicious: not allowed", `${f.non_allow} of ${f.runs}`],
            ["…and an alert was raised", `${f.alerted} of ${f.runs} (Jev ${f.alerted_by_jev}, policy ${f.alerted_by_policy})`],
            ["Seed says ordinary: allowed", `${c.allowed} of ${c.runs}`],
            ["…and no alert raised", `${c.runs - c.alerted} of ${c.runs}`]]));
    if (Object.keys(s.by_tag).length) {
        box.append(el("h4", {}, "By seed tag"), kv(Object.entries(s.by_tag).map(([tag, v]) => [tag.replaceAll("_", " ").toLowerCase(), `${v.non_allow}/${v.runs} not allowed · ${v.alerted}/${v.runs} alerted`])));
    }
    const table = el("table", { class: "inv-table" }, el("thead", {}, el("tr", {}, ["Transaction", "System", "Alert", "Seed answer key"].map(h => el("th", {}, h)))));
    const body = el("tbody");
    s.rows.forEach(r => {
        const c0 = findCase(r.case_id), tx = c0 && c0.transaction;
        const verdict = r.action == null ? "–" : (r.seed_flagged === (r.action !== "ALLOW") ? "✓" : "✗");
        body.append(el("tr", {}, el("td", {}, el("button", { class: "inv-link", type: "button", onclick: () => openSeedRun(r) }, r.transaction_id), tx ? ` ${fmtMoney(tx.amount, tx.currency)}` : ""),
            el("td", {}, r.action ? `${ACTION_TEXT[r.action]}${r.status === "INCOMPLETE" ? " (incomplete)" : ""}` : (r.state === "failed" ? "failed" : "running")),
            el("td", {}, r.alert_sources ? `${r.alert_severity} · ${r.alert_sources.map(x => SOURCE_TEXT[x]).join("+")}` : "none"),
            el("td", {}, `${verdict} ${r.seed_tag ? r.seed_tag.replaceAll("_", " ").toLowerCase() : "ordinary"}`)));
    });
    table.append(body);
    box.append(el("div", { class: "inv-table-wrap" }, table));
    if (s.failures.length) box.append(el("div", { class: "inv-error", role: "alert" }, `${s.failures.length} run(s) failed: ${s.failures[0].reason}`));
    box.append(el("p", { class: "inv-muted" }, s.note));
}

function openSeedRun(row) {
    inv.source = "seed"; stopReplay(); clearInterval(inv.pollTimer);
    Object.assign(inv, { caseId: row.case_id, runId: row.run_id, run: { state: "running", events: [], evidence: [] }, selected: [], reviewOpen: false, contextOpen: false, error: null });
    pollRun(); renderAll();
    document.getElementById("inv-controls").scrollIntoView({ behavior: "smooth" });
}

async function startSeedBatch() {
    inv.error = null;
    try {
        if (!inv.seedCases.length) {
            const d = await invApi("/api/evidencetrail/seed/transactions"); inv.seedCases = d.items;
        }
        const limit = Number(document.getElementById("inv-seed-n").value);
        const d = await invApi("/api/experiments/seed-batch", { limit });
        inv.seedExp = { state: "running", summary: null };
        clearInterval(inv.seedTimer);
        const tick = async () => {
            try { inv.seedExp = await invApi(`/api/experiments/${d.experimentId}`); if (inv.seedExp.state !== "running") clearInterval(inv.seedTimer); }
            catch (e) { inv.seedExp = { state: "failed", error: e.message }; clearInterval(inv.seedTimer); }
            renderSeedBatch();
        };
        inv.seedTimer = setInterval(tick, 2500); tick();
    } catch (e) { inv.error = `Seed batch failed to start: ${e.message}`; }
    renderAll();
}

document.addEventListener("DOMContentLoaded", initInvestigator);
