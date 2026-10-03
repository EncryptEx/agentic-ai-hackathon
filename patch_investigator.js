const fs = require('fs');
let content = fs.readFileSync('web/investigator.html', 'utf8');

// Add marked.js to head
if (!content.includes('marked.min.js')) {
    content = content.replace('</head>', '    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>\n</head>');
}

// Replace how c.report is rendered
const oldRender = `                <div class="case-body">\${c.report || 'Waiting for agent investigation...'}</div>`;
const newRender = `                <div class="case-body">\${c.report ? marked.parse(c.report) : 'Waiting for agent investigation...'}</div>`;

if (content.includes(oldRender)) {
    content = content.replace(oldRender, newRender);
}

// Add message listener for highlight
const oldScriptEnd = `        };
    </script>
</body>`;
const newScriptEnd = `        };

        window.addEventListener('message', (event) => {
            if (event.data && event.data.type === 'highlight_case') {
                const el = document.getElementById('inv-case-' + event.data.customer_id);
                if (el) {
                    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    el.style.transition = 'box-shadow 0.5s, transform 0.5s';
                    el.style.transform = 'scale(1.02)';
                    el.style.boxShadow = '0 0 20px rgba(111, 179, 255, 0.5)';
                    setTimeout(() => {
                        el.style.transform = 'scale(1)';
                        el.style.boxShadow = '0 4px 6px rgba(0,0,0,0.3)';
                    }, 2000);
                }
            }
        });
    </script>
</body>`;

if (content.includes(oldScriptEnd)) {
    content = content.replace(oldScriptEnd, newScriptEnd);
}

// Add styling for markdown
const cssInjection = `
        .case-body h1, .case-body h2, .case-body h3 { margin-top: 0; color: #fff; }
        .case-body p { margin-top: 0; }
        .case-body ul, .case-body ol { margin-top: 0; padding-left: 20px; }
        .case-body code { background: rgba(0,0,0,0.3); padding: 2px 4px; border-radius: 3px; }
        .case-body blockquote { border-left: 3px solid #3b82f6; margin-left: 0; padding-left: 10px; color: #94a3b8; }
        .no-cases`;
content = content.replace('.no-cases', cssInjection);

fs.writeFileSync('web/investigator.html', content);
console.log("Patched investigator.html");
