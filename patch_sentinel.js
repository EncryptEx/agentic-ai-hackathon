const fs = require('fs');
let content = fs.readFileSync('web/sentinel.html', 'utf8');

const newOnMessage = `    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.status || payload.error) return; // stream status or error
        
        if (payload.msg_type === 'jev_triage') {
            const row = payload.row;
            if (payload.suspicion === 'SUSPICIOUS') {
                const li = document.createElement('div');
                li.className = 'case enter flash';
                li.id = 'case-' + row.customer_id;
                li.innerHTML = \`
                    <div class="row1">
                        <span class="cstat">TRIAGED</span>
                        <span class="cid">Customer \${row.customer_id}</span>
                        <span class="camt">\${payload.suspicion}</span>
                    </div>
                    <div class="row2">Jev triggered investigation</div>
                \`;
                caseList.prepend(li);
                if (caseList.children.length > 5) caseList.lastChild.remove();
                
                let srcCust = getOrCreateCounterparty(row.customer_id);
                srcCust.suspicious = true;
                srcCust.riskScore = Math.max(srcCust.riskScore, 0.8);
            }
            return;
        } else if (payload.msg_type === 'investigation_started') {
            const li = document.getElementById('case-' + payload.customer_id);
            if (li) {
                li.querySelector('.cstat').innerText = 'INVESTIGATING';
                li.querySelector('.row2').innerText = 'Agents are analyzing evidence...';
            }
            return;
        } else if (payload.msg_type === 'investigation_finished') {
            const li = document.getElementById('case-' + payload.customer_id);
            if (li) {
                li.querySelector('.cstat').innerText = 'CLOSED';
                li.querySelector('.cstat').style.background = 'rgba(79, 224, 160, 0.14)';
                li.querySelector('.cstat').style.color = '#7fe0ab';
                li.querySelector('.row2').innerText = 'Investigation complete';
            }
            return;
        } else if (payload.msg_type === 'investigation_error') {
            return;
        }

        const custId = payload.customer_id;
        const cpName = payload.counterparty_name || payload.counterparty_account || 'Unknown';
        const direction = payload.direction;
        const amount = parseFloat(payload.amount_usd || payload.amount || 0);
        
        let srcCust = getOrCreateCounterparty(custId);
        let dstCust = getOrCreateCounterparty(cpName);
        
        if (direction === 'INBOUND') {
          const temp = srcCust;
          srcCust = dstCust;
          dstCust = temp;
        }
        
        const e = {
          a: srcCust, b: dstCust,
          amount,
          t: time,
          life: CONFIG.edgeLife,
          alpha: 0,
          suspicious: false,
          reason: null,
          score: 0,
          sanction: false,
          layer: false,
          leg: null,
        };
        
        // Add to recent feed
        if (txListEl) {
          const li = document.createElement('li');
          li.innerHTML = \`
            <span class="tx-parties">\${srcCust.name} &rarr; \${dstCust.name}</span>
            <span class="tx-amt">$\${amount.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</span>
          \`;
          txListEl.prepend(li);
          if (txListEl.children.length > 5) txListEl.lastChild.remove();
        }

        if (!srcCust.outTo) srcCust.outTo = new Set();
        if (!dstCust.inFrom) dstCust.inFrom = new Set();
        if (!srcCust.counterparties) srcCust.counterparties = new Set();
        if (!dstCust.counterparties) dstCust.counterparties = new Set();
        srcCust.outTo.add(dstCust.id);
        dstCust.inFrom.add(srcCust.id);
        srcCust.counterparties.add(dstCust.id);
        dstCust.counterparties.add(srcCust.id);
        if (!srcCust.recent) srcCust.recent = [];
        if (!dstCust.recent) dstCust.recent = [];
        srcCust.recent.push(time);
        dstCust.recent.push(time);
        
        txTotal++;
        edges.push(e);
        
      } catch (err) {
        console.error("WS error:", err);
      }
    };`;

content = content.replace(/ws\.onmessage = \(event\) => \{[\s\S]*?\} catch \(err\) \{\n        console\.error\("WS error:", err\);\n      \}\n    \};/, newOnMessage);

fs.writeFileSync('web/sentinel.html', content);
