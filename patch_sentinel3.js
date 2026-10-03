const fs = require('fs');
let content = fs.readFileSync('web/sentinel.html', 'utf8');

const oldClick = `invIframe.contentWindow.postMessage({ type: 'highlight_case', customer_id: row.customer_id }, '*');`;
const newClick = `invIframe.contentWindow.postMessage({ type: 'highlight_case', customer_id: row.customer_id, tx_id: payload.tx_id || row.transaction_id || row.customer_id }, '*');`;

if (content.includes(oldClick)) {
    content = content.replace(oldClick, newClick);
    fs.writeFileSync('web/sentinel.html', content);
    console.log("Patched sentinel click");
} else {
    console.log("Not found");
}

const oldCaseList = `                li.id = 'case-' + row.customer_id;`;
const newCaseList = `                const tx_id = payload.tx_id || row.transaction_id || row.customer_id;
                li.id = 'case-' + tx_id;`;
content = content.replace(oldCaseList, newCaseList);
fs.writeFileSync('web/sentinel.html', content);
