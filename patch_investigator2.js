const fs = require('fs');
let content = fs.readFileSync('web/investigator.html', 'utf8');

const oldScript = `
        const ws = new WebSocket(\`ws://\${window.location.host}/ws/transactions?speed_ms=1000\`);
        ws.onmessage = (event) => {
            try {
                const payload = JSON.parse(event.data);
                if (payload.msg_type === 'jev_triage' && payload.suspicion === 'SUSPICIOUS') {
                    const id = payload.customer_id;
                    if (!cases[id]) {
                        cases[id] = { 
                            id: id, 
                            amount: parseFloat(payload.row.amount || payload.row.amount_usd || 0).toLocaleString(undefined, {minimumFractionDigits: 2}),
                            status: 'suspicious'
                        };
                        renderCard(cases[id]);
                        if (!activeCaseId) selectCase(id);
                    }
                } else if (payload.msg_type === 'investigation_started') {
                    const id = payload.customer_id;
                    if (cases[id]) {
                        cases[id].status = 'ongoing';
                        renderCard(cases[id]);
                    }
                } else if (payload.msg_type === 'investigation_finished') {
                    const id = payload.customer_id;
                    if (cases[id]) {
                        cases[id].status = 'closed';
                        cases[id].report = payload.report;
                        cases[id].score = payload.score;
                        cases[id].tier = payload.tier;
                        cases[id].verdict = payload.verdict;
                        cases[id].typologies = payload.typologies;
                        renderCard(cases[id]);
                    }
                }
            } catch (err) {
                console.error(err);
            }
        };

        window.addEventListener('message', (event) => {
            if (event.data && event.data.type === 'highlight_case') {
                const id = event.data.customer_id;
                if (cases[id]) {
                    selectCase(id);
                    const el = document.getElementById('inv-case-' + id);
                    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                }
            }
        });`;

const newScript = `
        const ws = new WebSocket(\`ws://\${window.location.host}/ws/transactions?speed_ms=1000\`);
        ws.onmessage = (event) => {
            try {
                const payload = JSON.parse(event.data);
                const id = payload.tx_id || payload.customer_id;
                
                if (payload.msg_type === 'jev_triage' && payload.suspicion === 'SUSPICIOUS') {
                    if (!cases[id]) {
                        cases[id] = { 
                            id: id,
                            customer_id: payload.customer_id,
                            amount: parseFloat(payload.row.amount || payload.row.amount_usd || 0).toLocaleString(undefined, {minimumFractionDigits: 2}),
                            status: 'suspicious',
                            row: payload.row
                        };
                        renderCard(cases[id]);
                        if (!activeCaseId) selectCase(id);
                    }
                } else if (payload.msg_type === 'investigation_started') {
                    if (cases[id]) {
                        cases[id].status = 'ongoing';
                        renderCard(cases[id]);
                    }
                } else if (payload.msg_type === 'investigation_finished') {
                    if (cases[id]) {
                        cases[id].status = 'closed';
                        cases[id].report = payload.report;
                        cases[id].score = payload.score;
                        cases[id].tier = payload.tier;
                        cases[id].verdict = payload.verdict;
                        cases[id].typologies = payload.typologies;
                        renderCard(cases[id]);
                    }
                }
            } catch (err) {
                console.error(err);
            }
        };

        window.addEventListener('message', (event) => {
            if (event.data && event.data.type === 'highlight_case') {
                // Find case by customer_id if tx_id not provided
                let id = event.data.tx_id;
                if (!id) {
                    const c = Object.values(cases).find(c => c.customer_id === event.data.customer_id);
                    if (c) id = c.id;
                }
                
                if (id && cases[id]) {
                    selectCase(id);
                    const el = document.getElementById('inv-case-' + id);
                    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                }
            }
        });`;

if (content.includes(oldScript)) {
    content = content.replace(oldScript, newScript);
    fs.writeFileSync('web/investigator.html', content);
    console.log("Patched ws script");
} else {
    console.log("Could not find ws script");
}
