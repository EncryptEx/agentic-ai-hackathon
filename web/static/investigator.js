// EvidenceTrail "Investigator" tab. All server data is rendered via textContent / DOM nodes
// (never innerHTML) because tool-returned free text is untrusted. Synthetic data only.

const inv = {
    scenarios: [], caseId: null, run: null, runId: null, starting: false,
    selected: [], replayCount: null, replayTimer: null, pollTimer: null,
    reviewOpen: false, contextOpen: false, exp: null, expKind: null, expTimer: null, error: null,
    alerts: [], alertFilter: "open", alertsError: null, architecture: "team", handoffAsk: {}, alertTimer: null,
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
const fmtSek = n => `${Number(n).toLocaleString("en-US")} SEK`;
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
        type: "button", title: known ? `${known.type} (${known.source})` : "Not found in this run", text: id });
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
            el("div", { id: "inv-risk", class: "inv-card" }), el("div", { id: "inv-quality", class: "inv-card" }), el("div", { id: "inv-consistency", class: "inv-card" })));
    loadAlerts();
    invApi("/api/scenarios").then(d => {
        inv.scenarios = d.scenarios;
        inv.caseId = inv.caseId || (d.scenarios[0] && d.scenarios[0].case_id);
        renderAll();
    }).catch(e => { inv.error = `Could not load scenarios: ${e.message}`; renderAll(); });
    renderAll();
}

function renderAll() {
    renderControls(); renderTx(); renderTrace(); renderGraph(); renderFinal(); renderClaims();
    renderEvidence(); renderRisk(); renderQuality(); renderConsistency(); renderAlerts();
}

// ---------------------------------------------------------------- controls
function renderControls() {
    const box = document.getElementById("inv-controls");
    if (!box) return;
    const busy = inv.starting || (inv.run && isRunning(inv.run));
    const select = el("select", { id: "inv-case", disabled: busy, onchange: e => { inv.caseId = e.target.value; resetRun(); renderAll(); } },
        inv.scenarios.map(s => el("option", { value: s.case_id, selected: s.case_id === inv.caseId }, s.name)));
    const start = el("button", { class: "btn-primary inv-start", type: "button", disabled: busy || !inv.caseId, onclick: startRun },
        busy ? "Investigating…" : (inv.run && inv.run.state === "failed" ? "Retry investigation" : "Start investigation"));
    const replay = el("button", { class: "page-btn", type: "button", disabled: !inv.run || isRunning(inv.run) || !(inv.run.events || []).length, onclick: startReplay },
        "▶ Replay recorded trace");
    const exportBtn = el("button", { class: "page-btn", type: "button", disabled: !inv.runId || !inv.run || isRunning(inv.run), onclick: exportTrace,
        title: "Redacted JSON of the recorded audit trail" }, "⬇ Export trace");
    const arch = el("select", { id: "inv-arch", disabled: busy, "aria-label": "Agent architecture", title: "Agent architecture",
        onchange: e => { inv.architecture = e.target.value; } },
        el("option", { value: "team", selected: inv.architecture === "team" }, "Agent team"),
        el("option", { value: "single", selected: inv.architecture === "single" }, "Single agent"));
    const kids = [el("label", { class: "inv-label" }, "Case"), select, arch, start, replay, exportBtn, runBadges()];
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
    else if (hdr && hdr.architecture === "single") wrap.append(el("span", { class: "inv-tag" }, "Single agent"));
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

function resetRun() {
    stopReplay(); clearInterval(inv.pollTimer); clearInterval(inv.expTimer);
    Object.assign(inv, { run: null, runId: null, selected: [], reviewOpen: false, contextOpen: false, exp: null, expKind: null, error: null });
}

async function startRun() {
    if (inv.starting || (inv.run && isRunning(inv.run))) return; // prevent duplicate starts
    resetRun(); inv.starting = true; renderAll();
    try {
        const d = await invApi("/api/investigations", { caseId: inv.caseId, configuration: { architecture: inv.architecture } });
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
    const s = inv.scenarios.find(x => x.case_id === inv.caseId);
    if (!s) { box.replaceChildren(el("h3", {}, "Transaction"), el("p", { class: "inv-muted" }, "Loading scenarios…")); return; }
    const t = s.transaction;
    box.replaceChildren(el("h3", {}, "Transaction summary"), el("div", { class: "inv-amount" }, fmtSek(t.amount)),
        kv([["Transaction", t.transaction_id], ["Customer", t.customer_id], ["Recipient", t.recipient_id], ["Channel", t.channel],
            ["Reference", t.payment_reference], ["Time (UTC)", t.timestamp]]),
        el("p", { class: "inv-muted" }, "Synthetic scenario. Expected outcomes are hidden from the agent."));
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
        const li = el("li", { class: "inv-step" + (isErr ? " err" : "") },
            el("div", { class: "inv-step-head" }, el("span", { class: "inv-step-n", title: `trace event ${e.sequence}` }, idx + 1), el("strong", {}, title),
                e.agent && e.agent !== "investigator" && e.event_type !== "consultation" ? el("span", { class: "inv-tag agent-" + e.agent }, AGENT_LABELS[e.agent] || e.agent) : null,
                isErr ? el("span", { class: "inv-tag bad" }, "error / missing evidence") : null,
                e.duration_ms != null ? el("span", { class: "inv-muted" }, ` ${e.duration_ms} ms`) : null),
            e.brief_justification ? el("div", { class: "inv-muted" }, e.brief_justification) : null,
            e.reason_code ? el("div", { class: "inv-muted" }, `Reason: ${e.reason_code}`) : null,
            el("div", { class: "inv-chips" }, (e.input_evidence_ids || []).length ? el("span", { class: "inv-muted" }, "used ") : null,
                (e.input_evidence_ids || []).map(i => chip(i)),
                (e.output_evidence_ids || []).length ? el("span", { class: "inv-muted" }, " produced ") : null,
                (e.output_evidence_ids || []).map(i => chip(i))),
            el("details", { class: "inv-details" }, el("summary", {}, "Technical details"),
                el("pre", { class: "inv-pre" }, json({ arguments: e.validated_arguments, result: e.result_snapshot, error: e.error,
                    provider: e.provider, returned_model_version: e.returned_model_version, event_hash: e.event_hash }))));
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
    const recipient = (inv.scenarios.find(s => s.case_id === inv.caseId) || { transaction: {} }).transaction.recipient_id;
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
    if (!inv.selected.length) { box.append(el("p", { class: "inv-muted" }, "Select an evidence ID, claim or graph node.")); return; }
    inv.selected.forEach(id => {
        const e = evidenceById(id);
        if (!e) { box.append(el("div", { class: "inv-error" }, `${id} was not found in this run.`)); return; }
        box.append(el("div", { class: "inv-evidence-item" }, el("strong", {}, `${e.evidence_id} · ${e.type}`),
            kv([["Source", e.source], ["Observed", e.observed_at]]), el("pre", { class: "inv-pre" }, json(e.payload)),
            el("details", { class: "inv-details" }, el("summary", {}, "Technical details"), kv([["Snapshot hash", e.snapshot_hash], ["Source record", e.source_record_id]]))));
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

// ---------------------------------------------------------------- decision consistency
function renderConsistency() {
    const box = document.getElementById("inv-consistency");
    if (!box) return;
    box.replaceChildren(el("h3", {}, "Decision consistency"));
    const busy = inv.exp && inv.exp.state === "running";
    const mode = el("select", { id: "inv-mode", disabled: busy, "aria-label": "Experiment mode" },
        el("option", { value: "end_to_end" }, "End-to-end investigations"), el("option", { value: "fixed_evidence" }, "Fixed evidence"));
    const reps = el("select", { id: "inv-reps", disabled: busy, "aria-label": "Repetitions" }, [3, 5, 10, 20].map(n => el("option", { value: n, selected: n === 5 }, `${n} fresh runs`)));
    const hasLinks = ((inv.run && inv.run.evidence) || []).some(e => e.type === "relationship_graph" && (e.payload.links || []).length);
    const noRun = inv.run && isRunning(inv.run);
    box.append(el("div", { class: "inv-actions" }, mode, reps,
        el("button", { class: "page-btn", type: "button", disabled: busy || !inv.caseId || noRun, onclick: () => startExperiment("repeat") }, "Run repeats"),
        el("button", { class: "page-btn", type: "button", disabled: busy || !hasLinks, title: hasLinks ? "" : "Needs a run that found network links",
            onclick: () => startExperiment("counterfactual") }, "Evidence-change experiment"),
        el("button", { class: "page-btn", type: "button", disabled: busy || noRun, title: "All five cases: rules vs Gemini without Jev vs Gemini with Jev",
            onclick: () => startExperiment("ablation") }, "Compare approaches")),
        el("p", { class: "inv-muted" }, "Repeats are fresh model calls (never recorded replay). “Fixed evidence” freezes one evidence bundle and asks Gemini and Jev independently several times. Agreement can be consistently wrong."));
    if (!inv.exp) return;
    if (inv.exp.error) { box.append(el("div", { class: "inv-error", role: "alert" }, inv.exp.error)); return; }
    if (inv.expKind === "fixed_evidence") return renderFixedEvidence(box);
    if (inv.expKind === "ablation") return renderAblation(box);
    renderRepeatSummary(box);
}

function renderRepeatSummary(box) {
    const s = inv.exp.summary || {};
    if (s.attempted_runs == null) { box.append(el("p", { class: "inv-muted" }, "Starting runs…")); return; }
    const elapsed = (s.elapsed_ms || []).filter(x => x != null);
    box.append(el("h4", {}, inv.expKind === "counterfactual" ? "Evidence-change experiment: network links removed" : "Repeated fresh runs"),
        el("span", { class: "inv-tag fresh" }, inv.exp.label || "Fresh runs"),
        kv([["Attempted / finished / successful", `${s.attempted_runs} / ${s.finished_runs} / ${s.successful_runs}`],
            ["Failed or incomplete", s.failed_or_incomplete_runs],
            ["Allow / Context check / Review", s.action_counts ? `${s.action_counts.ALLOW} / ${s.action_counts.CONTEXT_CHECK} / ${s.action_counts.REVIEW}` : "–"],
            ["Most common action", s.modal && s.modal.modal_action ? `${ACTION_TEXT[s.modal.modal_action]} (${s.modal.agreement} successful runs)` : "–"],
            ["Pairwise agreement", s.pairwise_agreement == null ? "n/a (needs 2+ successful runs)" : s.pairwise_agreement.toFixed(3)],
            ["Both Allow and Review seen", s.opposite_outcome_flag ? "yes – inconsistent" : "no"],
            ["Time per run", elapsed.length ? `${Math.min(...elapsed)}–${Math.max(...elapsed)} ms` : "–"]]),
        el("details", { class: "inv-details" }, el("summary", {}, "Technical details"), el("pre", { class: "inv-pre" }, json({ tool_sequences: s.tool_sequences, tool_call_counts: s.tool_call_counts, error_counts: s.error_counts, usage_totals: s.usage_totals, cost: s.cost, run_ids: inv.exp.run_ids, configuration: inv.exp.configuration }))),
        el("p", { class: "inv-muted" }, inv.expKind === "counterfactual"
            ? "A change shows sensitivity under this intervention. It does not prove causal correctness or that every risk reduction should flip an action."
            : (s.note || "")));
}

function renderFixedEvidence(box) {
    const e = inv.exp;
    if (e.state === "running") { box.append(el("p", { class: "inv-muted" }, `Running fixed-evidence calls… ${e.progress || 0}/${e.repetitions}`)); return; }
    const r = e.result, d = r.decision, j = r.jev;
    box.append(el("h4", {}, "Fixed evidence: one frozen bundle"), el("span", { class: "inv-tag fresh" }, e.label),
        el("p", { class: "inv-muted" }, `Bundle ${r.bundle.evidence_ids.join(", ")} · hash ${r.bundle.bundle_hash.slice(0, 12)}…`),
        el("h4", {}, "Gemini decision"),
        kv([["Attempted / successful", `${d.attempted} / ${d.successful}`], ["Errors or incomplete", d.incomplete_or_error],
            ["Allow / Context check / Review", `${d.action_counts.ALLOW} / ${d.action_counts.CONTEXT_CHECK} / ${d.action_counts.REVIEW}`],
            ["Most common action", d.modal.modal_action ? `${ACTION_TEXT[d.modal.modal_action]} (${d.modal.agreement})` : "–"],
            ["Pairwise agreement", d.pairwise_agreement == null ? "n/a" : d.pairwise_agreement.toFixed(3)]]),
        el("h4", {}, "Jev assessment (separate)"),
        kv([["Attempted / successful", `${j.attempted} / ${j.successful}`], ["Errors", j.errors]]),
        kv(Object.entries(j.per_question).map(([q, v]) => [q.replaceAll("_", " "), v.counts ? Object.entries(v.counts).map(([k, n]) => `${k} ×${n}`).join(", ") : (v.mean != null ? `mean ${v.mean.toFixed(2)} (range ${v.min}–${v.max})` : "–")])),
        el("details", { class: "inv-details" }, el("summary", {}, "Technical details"), el("pre", { class: "inv-pre" }, json({ decision_runs: d.runs, jev_runs: j.runs }))),
        el("p", { class: "inv-muted" }, r.note));
}

function renderAblation(box) {
    const e = inv.exp, s = e.summary;
    if (!s || !s.arms) { box.append(el("p", { class: "inv-muted" }, "Starting runs…")); return; }
    const names = { rules: "Rules only", no_jev: "Gemini without Jev", with_jev: "Gemini with Jev" };
    box.append(el("h4", {}, "Approach comparison"), el("span", { class: "inv-tag fresh" }, e.state === "running" ? "Running…" : (e.label || "")));
    const table = el("table", { class: "inv-table" }, el("thead", {}, el("tr", {}, el("th", {}, "Case"), Object.keys(names).map(k => el("th", {}, names[k])))));
    const body = el("tbody");
    e.case_ids.forEach(cid => {
        const sc = (inv.scenarios.find(x => x.case_id === cid) || {}).name || cid;
        const rules = s.arms.rules.cases[cid];
        const cell = arm => {
            const c = s.arms[arm].cases[cid], x = c.summary;
            return `${x.action_counts.ALLOW}/${x.action_counts.CONTEXT_CHECK}/${x.action_counts.REVIEW}` + (x.failed_or_incomplete_runs ? ` · ${x.failed_or_incomplete_runs} incomplete/failed` : "") + ` · ${c.matched_runs}/${c.eligible_runs} match`;
        };
        body.append(el("tr", {}, el("td", {}, sc),
            el("td", {}, `${ACTION_TEXT[rules.action]}${rules.status === "INCOMPLETE" ? " (incomplete)" : ""} · ${rules.match ? "match" : "no match"}`),
            el("td", {}, cell("no_jev")), el("td", {}, cell("with_jev"))));
    });
    table.append(body);
    const tot = arm => `${s.arms[arm].matched_runs}/${s.arms[arm].eligible_runs} matched (${s.arms[arm].attempted_runs} attempted; provider failures excluded)`;
    box.append(el("div", { class: "inv-table-wrap" }, table),
        kv([["Rules only", `${s.arms.rules.matched}/${s.arms.rules.eligible} cases matched`], ["Gemini without Jev", tot("no_jev")], ["Gemini with Jev", tot("with_jev")]]),
        el("p", { class: "inv-muted" }, "Cells show Allow/Context check/Review counts across fresh runs, then how many successful runs matched the illustrative policy label. " + s.note));
}

async function startExperiment(kind) {
    const repetitions = Number(document.getElementById("inv-reps").value);
    const mode = document.getElementById("inv-mode").value;
    try {
        let body, expKind = kind;
        if (kind === "repeat") { body = { caseId: inv.caseId, mode, repetitions }; if (mode === "fixed_evidence") expKind = "fixed_evidence"; }
        else if (kind === "counterfactual") body = { caseId: inv.caseId, patch: { remove_network_links: true }, repetitions };
        else body = { repetitions: Math.min(repetitions, 10) };
        const d = await invApi(`/api/experiments/${kind}`, body);
        inv.expKind = expKind; inv.exp = { state: "running", summary: {}, label: "Fresh runs", repetitions, progress: 0 };
        clearInterval(inv.expTimer);
        const tick = async () => {
            try { inv.exp = await invApi(`/api/experiments/${d.experimentId}`); if (inv.exp.state !== "running") clearInterval(inv.expTimer); }
            catch (e) { inv.error = e.message; clearInterval(inv.expTimer); }
            renderConsistency(); renderControls();
        };
        inv.expTimer = setInterval(tick, 1200); tick();
    } catch (e) { inv.error = `Experiment failed to start: ${e.message}`; }
    renderAll();
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
    Object.assign(inv, { caseId: a.case_id, runId: a.run_id, run: { state: "running", events: [], evidence: [] }, selected: [], reviewOpen: false, contextOpen: false, exp: null, error: null });
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
        const name = (inv.scenarios.find(x => x.case_id === a.case_id) || {}).name || a.case_id;
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

document.addEventListener("DOMContentLoaded", initInvestigator);
