const fs = require('fs');
let content = fs.readFileSync('web/sentinel.html', 'utf8');

const oldInvestigating = `        } else if (payload.msg_type === 'investigation_started') {
            const li = document.getElementById('case-' + payload.customer_id);`;
const newInvestigating = `        } else if (payload.msg_type === 'investigation_started') {
            const id = payload.tx_id || payload.customer_id;
            const li = document.getElementById('case-' + id);`;
content = content.replace(oldInvestigating, newInvestigating);

const oldFinished = `        } else if (payload.msg_type === 'investigation_finished') {
            const li = document.getElementById('case-' + payload.customer_id);`;
const newFinished = `        } else if (payload.msg_type === 'investigation_finished') {
            const id = payload.tx_id || payload.customer_id;
            const li = document.getElementById('case-' + id);`;
content = content.replace(oldFinished, newFinished);

fs.writeFileSync('web/sentinel.html', content);
