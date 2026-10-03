const fs = require('fs');
let content = fs.readFileSync('web/realtime.html', 'utf8');

content = content.replace(/--bg-body: [^;]+;/, '--bg-body: #050505;');
content = content.replace(/--bg-surface: [^;]+;/, '--bg-surface: rgba(15, 15, 17, 0.7);');
content = content.replace(/--bg-card: [^;]+;/, '--bg-card: rgba(15, 15, 17, 0.9);');
content = content.replace(/--bg-card-hover: [^;]+;/, '--bg-card-hover: rgba(255, 255, 255, 0.03);');
content = content.replace(/--border-subtle: [^;]+;/, '--border-subtle: rgba(255, 255, 255, 0.08);');

fs.writeFileSync('web/realtime.html', content);
