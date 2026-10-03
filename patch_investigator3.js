const fs = require('fs');
let content = fs.readFileSync('web/investigator.html', 'utf8');

const oldDossierHeader = `                <div class="dossier-header">
                    <div>
                        <h2 class="dossier-title" id="d-title">Customer CUST-00000</h2>
                        <div class="dossier-meta" id="d-meta">Transaction Amt: $0.00 &middot; Generated via Google ADK</div>
                    </div>
                </div>`;

const newDossierHeader = `                <div class="dossier-header" style="margin-bottom: 24px;">
                    <div>
                        <h2 class="dossier-title" id="d-title">Customer CUST-00000</h2>
                        <div class="dossier-meta" id="d-meta">Transaction Amt: $0.00 &middot; Investigated by AI Swarm</div>
                    </div>
                </div>

                <div class="tx-graph-container" style="background: rgba(10,10,12,0.6); border: 1px solid var(--border-subtle); border-radius: 12px; padding: 24px; margin-bottom: 32px; display: flex; align-items: center; justify-content: space-between; position: relative;">
                    <!-- Line connecting them -->
                    <div style="position: absolute; left: 100px; right: 100px; top: 50%; height: 2px; background: rgba(255,255,255,0.1); z-index: 1;">
                        <div class="tx-particle" style="position: absolute; top: -3px; width: 8px; height: 8px; border-radius: 50%; background: var(--accent-brand); box-shadow: 0 0 10px var(--accent-brand); animation: tx-flow 2s infinite linear;"></div>
                    </div>
                    
                    <style>
                        @keyframes tx-flow {
                            0% { left: 0; opacity: 0; }
                            10% { opacity: 1; }
                            90% { opacity: 1; }
                            100% { left: 100%; opacity: 0; }
                        }
                        .node { z-index: 2; display: flex; flex-direction: column; align-items: center; gap: 8px; width: 120px; text-align: center; }
                        .node-circle { width: 64px; height: 64px; border-radius: 50%; background: #172033; border: 2px solid var(--border-active); display: flex; align-items: center; justify-content: center; font-size: 1.5rem; }
                        .node-name { font-size: 0.85rem; font-weight: 600; }
                        .node-sub { font-size: 0.7rem; color: var(--text-muted); }
                        
                        .tx-info { z-index: 2; background: var(--bg-base); padding: 8px 16px; border-radius: 99px; border: 1px solid var(--border-subtle); text-align: center; }
                    </style>

                    <div class="node">
                        <div class="node-circle" style="border-color: #6fb3ff;">🏛️</div>
                        <div class="node-name" id="graph-src-name">Source</div>
                        <div class="node-sub" id="graph-src-sub">Account</div>
                    </div>
                    
                    <div class="tx-info">
                        <div style="font-weight: 700; font-size: 1.1rem; color: #fff;" id="graph-amt">$0.00</div>
                        <div style="font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase;" id="graph-type">TRANSFER</div>
                    </div>

                    <div class="node">
                        <div class="node-circle" style="border-color: #ff5f6d;">👤</div>
                        <div class="node-name" id="graph-dst-name">Destination</div>
                        <div class="node-sub" id="graph-dst-sub">Account</div>
                    </div>
                </div>`;

content = content.replace(oldDossierHeader, newDossierHeader);

const oldSelectCase = `            document.getElementById('d-title').textContent = 'Customer ' + c.id;
            document.getElementById('d-meta').textContent = 'Transaction Amt: $' + c.amount + ' · Investigated by AI Swarm';`;

const newSelectCase = `            document.getElementById('d-title').textContent = (c.row && c.row.customer_id) ? 'Customer ' + c.row.customer_id : 'Case ' + c.id;
            document.getElementById('d-meta').textContent = 'Transaction Amt: $' + c.amount + ' · Investigated by AI Swarm';
            
            if (c.row) {
                const isOutbound = c.row.direction === 'OUTBOUND';
                const mainName = 'Customer ' + c.row.customer_id;
                const cpName = c.row.counterparty_name || c.row.counterparty_account || 'Unknown';
                
                document.getElementById('graph-src-name').textContent = isOutbound ? mainName : cpName;
                document.getElementById('graph-src-sub').textContent = isOutbound ? 'Internal' : 'External';
                
                document.getElementById('graph-dst-name').textContent = isOutbound ? cpName : mainName;
                document.getElementById('graph-dst-sub').textContent = isOutbound ? 'External' : 'Internal';
                
                document.getElementById('graph-amt').textContent = '$' + c.amount;
                document.getElementById('graph-type').textContent = (c.row.transaction_type || 'TRANSFER').replace('_', ' ');
            }`;

content = content.replace(oldSelectCase, newSelectCase);

fs.writeFileSync('web/investigator.html', content);
console.log("Patched investigator graph");
