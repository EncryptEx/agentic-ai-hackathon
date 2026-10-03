const fs = require('fs');
let content = fs.readFileSync('web/sentinel.html', 'utf8');

const oldStr = `                caseList.prepend(li);
                if (caseList.children.length > 5) caseList.lastChild.remove();
                
                let srcCust = getOrCreateCounterparty(row.customer_id);
                srcCust.suspicious = true;
                srcCust.riskScore = Math.max(srcCust.riskScore, 0.8);
            }`;
            
const newStr = `                li.style.cursor = 'pointer';
                li.onclick = () => {
                    if (window.parent && window.parent.document) {
                        const invTab = window.parent.document.querySelector('[data-target="investigator-tab"]');
                        if (invTab) invTab.click();
                        
                        const invIframe = window.parent.document.querySelector('#investigator-tab iframe');
                        if (invIframe && invIframe.contentWindow) {
                            invIframe.contentWindow.postMessage({ type: 'highlight_case', customer_id: row.customer_id }, '*');
                        }
                    }
                };
                caseList.prepend(li);
                if (caseList.children.length > 5) caseList.lastChild.remove();
                
                let srcCust = getOrCreateCounterparty(row.customer_id);
                srcCust.suspicious = true;
                srcCust.riskScore = Math.max(srcCust.riskScore, 0.8);
            }`;

if (content.includes(oldStr)) {
    content = content.replace(oldStr, newStr);
    fs.writeFileSync('web/sentinel.html', content);
    console.log("Patched sentinel.html");
} else {
    console.log("Could not find string in sentinel.html");
}
