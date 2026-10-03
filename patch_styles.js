const fs = require('fs');

function patchSentinel() {
    let content = fs.readFileSync('web/sentinel.html', 'utf8');
    
    // Add Inter
    if (!content.includes('fonts.googleapis.com/css2?family=Inter')) {
        content = content.replace('<head>', '<head>\n<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">');
    }
    
    // Replace roots
    content = content.replace(/--bg: [^;]+;/, '--bg: #050505;');
    content = content.replace(/--ink: [^;]+;/, '--ink: #f4f4f5;');
    content = content.replace(/--dim: [^;]+;/, '--dim: #a1a1aa;');
    content = content.replace(/--line: [^;]+;/, '--line: rgba(255, 255, 255, 0.08);');
    content = content.replace(/--panel: [^;]+;/, '--panel: rgba(15, 15, 17, 0.7);');
    content = content.replace(/--crit: [^;]+;/, '--crit: #ef4444;');
    content = content.replace(/--high: [^;]+;/, '--high: #f59e0b;');
    content = content.replace(/--med: [^;]+;/, '--med: #3b82f6;');
    content = content.replace(/--ok: [^;]+;/, '--ok: #10b981;');
    
    // Replace font family
    content = content.replace(/font-family: ui-monospace, SFMono-Regular, Menlo, monospace;/, "font-family: 'Inter', -apple-system, sans-serif;");
    
    // Some extra tweaks for modern look
    content = content.replace(/backdrop-filter: blur\(10px\);/, "backdrop-filter: blur(12px);");
    content = content.replace(/border-radius: 12px;/, "border-radius: 16px;");
    
    fs.writeFileSync('web/sentinel.html', content);
    console.log("Patched sentinel");
}

function patchVisualization() {
    let content = fs.readFileSync('web/visualization.html', 'utf8');
    
    // Add Inter
    if (!content.includes('fonts.googleapis.com/css2?family=Inter')) {
        content = content.replace('<head>', '<head>\n    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">');
    }
    
    // Replace roots
    content = content.replace(/--bg-body: [^;]+;/, '--bg-body: #050505;');
    content = content.replace(/--bg-surface: [^;]+;/, '--bg-surface: rgba(15, 15, 17, 0.7);');
    content = content.replace(/--bg-card: [^;]+;/, '--bg-card: rgba(15, 15, 17, 0.9);');
    content = content.replace(/--bg-card-hover: [^;]+;/, '--bg-card-hover: rgba(255, 255, 255, 0.03);');
    content = content.replace(/--border-subtle: [^;]+;/, '--border-subtle: rgba(255, 255, 255, 0.08);');
    
    // Font family
    content = content.replace(/font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;/, "font-family: 'Inter', -apple-system, sans-serif;");
    
    fs.writeFileSync('web/visualization.html', content);
    console.log("Patched visualization");
}

function patchRealtime() {
    if (fs.existsSync('web/realtime.html')) {
        let content = fs.readFileSync('web/realtime.html', 'utf8');
        
        // Add Inter
        if (!content.includes('fonts.googleapis.com/css2?family=Inter')) {
            content = content.replace('<head>', '<head>\n    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">');
        }
        
        // Replace styles
        content = content.replace(/background-color: #05070c;/, 'background-color: #050505;');
        content = content.replace(/font-family: [^;]+;/, "font-family: 'Inter', -apple-system, sans-serif;");
        
        fs.writeFileSync('web/realtime.html', content);
        console.log("Patched realtime");
    }
}

patchSentinel();
patchVisualization();
patchRealtime();
