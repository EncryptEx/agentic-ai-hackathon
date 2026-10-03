/**
 * =========================================================================
 * Google Voice AI Copilot SDK & Component
 * Standalone, Zero-Dependency, Context-Aware Voice Dialogue Agent
 * Supports: Google Web Speech STT, Google SpeechSynthesis TTS,
 * Real-time Waveform Audio Visualizer, Context Auto-Inspection & Voice-to-Action
 * =========================================================================
 */
(function(window, document) {
    'use strict';

    // Prevent duplicate initializations
    if (window.GoogleVoiceCopilotInitialized) return;
    window.GoogleVoiceCopilotInitialized = true;

    class GoogleVoiceCopilotService {
        constructor() {
            this.isListening = false;
            this.recognition = null;
            this.activeSource = 'modal'; // 'modal' or 'embedded'
            this.waveformInterval = null;
            this.autoTtsEnabled = true;

            this.initSpeechRecognition();
            this.injectStylesIfNeeded();
            this.mountComponents();
        }

        // Auto-inject CSS stylesheet if not present in head
        injectStylesIfNeeded() {
            if (!document.getElementById('gvoice-copilot-styles')) {
                const link = document.createElement('link');
                link.id = 'gvoice-copilot-styles';
                link.rel = 'stylesheet';
                link.href = '/static/google_voice_copilot.css';
                document.head.appendChild(link);
            }
        }

        // Initialize Google Speech-to-Text Recognition
        initSpeechRecognition() {
            const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
            if (SpeechRec) {
                this.recognition = new SpeechRec();
                this.recognition.continuous = false;
                this.recognition.interimResults = true;
                this.recognition.lang = 'en-US';

                this.recognition.onstart = () => this.handleSpeechStart();
                this.recognition.onresult = (e) => this.handleSpeechResult(e);
                this.recognition.onend = () => this.handleSpeechEnd();
                this.recognition.onerror = (e) => this.handleSpeechError(e);
            } else {
                console.warn('[GoogleVoiceCopilot] Web Speech API not supported in this browser.');
            }
        }

        // Mount Floating Modal & Embedded Container if present
        mountComponents() {
            this.mountFloatingWidget();
            this.mountEmbeddedContainer();
        }

        // 1. Mount Universal Floating Widget (Bottom-Right)
        mountFloatingWidget() {
            if (document.getElementById('gvoice-floating-root')) return;

            const root = document.createElement('div');
            root.id = 'gvoice-floating-root';
            root.innerHTML = `
                <!-- Floating Launcher Button -->
                <button id="gvoice-launcher-btn" class="gvoice-launcher" title="Open Google Voice AI Copilot">
                    <span class="gvoice-launcher-icon">🎙️</span>
                    <span>Google Voice Copilot</span>
                    <span class="gvoice-live-badge">LIVE</span>
                </button>

                <!-- Floating Modal Window -->
                <div id="gvoice-modal-window" class="gvoice-modal">
                    <!-- Header -->
                    <div class="gvoice-header">
                        <div class="gvoice-title-row">
                            <span style="font-size: 18px;">🛡️</span>
                            <div>
                                <div class="gvoice-title-text">Google Voice FRAML Copilot</div>
                                <div style="font-size: 11px; color: #94a3b8;">Two-Way Spoken Agentic Dialogue</div>
                            </div>
                        </div>
                        <div class="gvoice-header-actions">
                            <span id="gvoice-status-pill" class="gvoice-status-pill">STANDBY</span>
                            <button id="gvoice-close-btn" class="gvoice-btn-close" title="Close">✕</button>
                        </div>
                    </div>

                    <!-- Audio Waveform Bar -->
                    <div class="gvoice-waveform-bar">
                        <div class="gvoice-wave-info">
                            <span id="gvoice-wave-dot" class="gvoice-wave-indicator-dot"></span>
                            <span id="gvoice-wave-text">Voice Standby</span>
                        </div>
                        <div class="gvoice-wave-bars">
                            <span class="gvoice-bar"></span>
                            <span class="gvoice-bar"></span>
                            <span class="gvoice-bar"></span>
                            <span class="gvoice-bar"></span>
                            <span class="gvoice-bar"></span>
                        </div>
                    </div>

                    <!-- Message Stream -->
                    <div id="gvoice-stream" class="gvoice-stream">
                        <div class="gvoice-msg-ai">
                            <div class="gvoice-sender-tag">🤖 VALIANT AI INVESTIGATOR (VOICE COPILOT)</div>
                            <div>
                                Hello! I am your <strong>Google Voice FRAML Investigation Copilot</strong>.<br/>
                                You can speak into your microphone to query dashboard anomalies, analyze customer profiles, inspect AML typologies, or review dialectic debate arbitrations.
                            </div>
                        </div>
                    </div>

                    <!-- Prompt Chips -->
                    <div class="gvoice-chips-container">
                        <button class="gvoice-chip" data-q="Investigate customer CUST-00043">💬 "Investigate CUST-00043"</button>
                        <button class="gvoice-chip" data-q="Explain the dialectic debate between Money Mule and Coerced Victim">💬 "Why Mule vs Victim?"</button>
                        <button class="gvoice-chip" data-q="What are the active alerts on the dashboard?">💬 "Active Alerts"</button>
                        <button class="gvoice-chip" data-q="Filter customers to show critical risk cases">💬 "Show Critical"</button>
                        <button class="gvoice-chip" data-q="How does the self-evolving loop optimize the policy rules?">💬 "Self-Evolution"</button>
                    </div>

                    <!-- Input Controls -->
                    <div class="gvoice-input-area">
                        <button id="gvoice-modal-mic" class="gvoice-btn-mic" title="Click to Speak (Google STT)">🎙️</button>
                        <input type="text" id="gvoice-modal-input" class="gvoice-input-field" placeholder="Speak via mic or type a question...">
                        <button id="gvoice-modal-send" class="gvoice-btn-send">Send</button>
                    </div>
                </div>
            `;
            document.body.appendChild(root);

            // Bind Events
            const launcher = document.getElementById('gvoice-launcher-btn');
            const modal = document.getElementById('gvoice-modal-window');
            const closeBtn = document.getElementById('gvoice-close-btn');
            const micBtn = document.getElementById('gvoice-modal-mic');
            const inputField = document.getElementById('gvoice-modal-input');
            const sendBtn = document.getElementById('gvoice-modal-send');
            const chips = root.querySelectorAll('.gvoice-chip');

            launcher.addEventListener('click', () => {
                const isHidden = modal.style.display === 'none' || !modal.style.display;
                modal.style.display = isHidden ? 'flex' : 'none';
                if (isHidden) inputField.focus();
            });

            closeBtn.addEventListener('click', () => {
                modal.style.display = 'none';
                this.stopSpeechSynthesis();
            });

            micBtn.addEventListener('click', () => this.toggleListening('modal'));

            sendBtn.addEventListener('click', () => {
                this.ask(inputField.value);
                inputField.value = '';
            });

            inputField.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    this.ask(inputField.value);
                    inputField.value = '';
                }
            });

            chips.forEach(chip => {
                chip.addEventListener('click', () => {
                    const q = chip.getAttribute('data-q');
                    if (q) this.ask(q);
                });
            });
        }

        // 2. Mount In-Page Embedded Card (If container exists in teammate's dashboard)
        mountEmbeddedContainer() {
            const container = document.getElementById('voice-copilot-container') || document.getElementById('voice-copilot-mount');
            if (!container) return;

            container.innerHTML = `
                <div class="gvoice-embedded-card">
                    <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.08); padding-bottom: 12px; margin-bottom: 14px;">
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <span style="font-size: 24px;">🎙️</span>
                            <div>
                                <h3 style="font-size: 15px; font-weight: 700; color: #f8fafc; margin: 0;">Interactive Google Voice AI Copilot</h3>
                                <div style="font-size: 12px; color: #94a3b8;">Two-way spoken investigation & dashboard anomaly copilot</div>
                            </div>
                        </div>
                        <span class="gvoice-status-pill">ACTIVE COPILOT</span>
                    </div>

                    <div style="display: flex; gap: 10px; align-items: center; margin-bottom: 12px;">
                        <button id="gvoice-embed-mic" class="gvoice-btn-mic" style="width: 40px; height: 40px; font-size: 16px;">🎙️</button>
                        <input type="text" id="gvoice-embed-input" class="gvoice-input-field" placeholder="Ask questions about any anomaly spotted on this dashboard...">
                        <button id="gvoice-embed-send" class="gvoice-btn-send">Ask</button>
                    </div>

                    <div id="gvoice-embed-feed" style="display: none; background: #030712; border: 1px solid #1e293b; border-radius: 8px; padding: 12px; font-size: 12px; line-height: 1.5; color: #e2e8f0;"></div>
                </div>
            `;

            const embedMic = document.getElementById('gvoice-embed-mic');
            const embedInput = document.getElementById('gvoice-embed-input');
            const embedSend = document.getElementById('gvoice-embed-send');

            if (embedMic) embedMic.addEventListener('click', () => this.toggleListening('embedded'));
            if (embedSend) embedSend.addEventListener('click', () => {
                this.ask(embedInput.value);
                embedInput.value = '';
            });
            if (embedInput) embedInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    this.ask(embedInput.value);
                    embedInput.value = '';
                }
            });
        }

        // Toggle Speech Recognition
        toggleListening(source = 'modal') {
            if (!this.recognition) {
                alert('Google Speech Recognition (Web Speech API) is not supported in this browser. Please type your question.');
                return;
            }

            if (this.isListening) {
                this.recognition.stop();
            } else {
                this.activeSource = source;
                const input = source === 'modal' ? document.getElementById('gvoice-modal-input') : document.getElementById('gvoice-embed-input');
                if (input) input.value = '';
                try {
                    this.recognition.start();
                } catch (e) {
                    console.error('[GoogleVoiceCopilot] Recognition start error:', e);
                }
            }
        }

        handleSpeechStart() {
            this.isListening = true;
            this.updateStatus('LISTENING...', '#f43f5e', 'rgba(244,63,94,0.2)');
            this.startWaveform('#f43f5e');

            const modalMic = document.getElementById('gvoice-modal-mic');
            const embedMic = document.getElementById('gvoice-embed-mic');
            if (modalMic && this.activeSource === 'modal') modalMic.classList.add('listening');
            if (embedMic && this.activeSource === 'embedded') embedMic.classList.add('listening');
        }

        handleSpeechResult(event) {
            let transcript = '';
            for (let i = event.resultIndex; i < event.results.length; ++i) {
                transcript += event.results[i][0].transcript;
            }

            const input = this.activeSource === 'modal'
                ? document.getElementById('gvoice-modal-input')
                : document.getElementById('gvoice-embed-input');
            if (input) input.value = transcript;

            const waveText = document.getElementById('gvoice-wave-text');
            if (waveText) waveText.textContent = `Heard: "${transcript}"`;
        }

        handleSpeechEnd() {
            this.isListening = false;
            this.stopWaveform();

            const modalMic = document.getElementById('gvoice-modal-mic');
            const embedMic = document.getElementById('gvoice-embed-mic');
            if (modalMic) modalMic.classList.remove('listening');
            if (embedMic) embedMic.classList.remove('listening');

            const input = this.activeSource === 'modal'
                ? document.getElementById('gvoice-modal-input')
                : document.getElementById('gvoice-embed-input');
            const query = input?.value?.trim();

            if (query) {
                this.ask(query);
            } else {
                this.updateStatus('STANDBY', '#4ade80', 'rgba(34,197,94,0.18)');
            }
        }

        handleSpeechError(event) {
            console.error('[GoogleVoiceCopilot] Speech error:', event.error);
            this.handleSpeechEnd();
        }

        // Automatic Context Inspector (inspects current page DOM for customer IDs, tabs, etc.)
        inspectPageContext() {
            const context = {
                pathname: window.location.pathname,
                activeTab: document.querySelector('.nav-tab.active')?.getAttribute('data-target') || 'unknown',
                customerId: null,
            };

            // Check URL search params
            const urlParams = new URLSearchParams(window.location.search);
            if (urlParams.get('customer_id')) {
                context.customerId = urlParams.get('customer_id');
            }

            // Check active customer dossier
            const dossierCustId = document.getElementById('dossier-id')?.textContent || document.getElementById('customer-id')?.textContent;
            if (dossierCustId && dossierCustId.includes('CUST-')) {
                context.customerId = dossierCustId.trim();
            }

            // Check selected table row
            const selectedRow = document.querySelector('tr.selected, tr.active');
            if (selectedRow) {
                const rowCust = selectedRow.querySelector('.cust-id')?.textContent || selectedRow.cells?.[0]?.textContent;
                if (rowCust && rowCust.includes('CUST-')) context.customerId = rowCust.trim();
            }

            return context;
        }

        // Ask the backend Voice Agent
        async ask(queryText) {
            if (!queryText || !queryText.trim()) return;

            // Append user message to modal stream
            this.appendMessage('user', queryText);

            // Update UI status to thinking
            this.updateStatus('THINKING...', '#fbbf24', 'rgba(251,191,36,0.2)');
            this.startWaveform('#fbbf24');

            const context = this.inspectPageContext();

            try {
                const res = await fetch('/api/voice/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        message: queryText,
                        customer_id: context.customerId,
                        context: context
                    })
                });

                const data = await res.json();
                this.stopWaveform();

                // Append AI response to modal stream
                this.appendMessage('ai', data.reply);

                // Update embedded feed if present
                const embedFeed = document.getElementById('gvoice-embed-feed');
                if (embedFeed) {
                    embedFeed.style.display = 'block';
                    embedFeed.innerHTML = `
                        <div style="font-weight: 700; color: #38bdf8; margin-bottom: 4px;">👤 "${queryText}"</div>
                        <div>${this.formatMarkdown(data.reply)}</div>
                    `;
                }

                // Execute Dashboard Actions
                this.executeDashboardAction(data);

                // Speak response aloud via Google TTS
                if (data.spoken_reply && this.autoTtsEnabled) {
                    this.speak(data.spoken_reply);
                } else {
                    this.updateStatus('STANDBY', '#4ade80', 'rgba(34,197,94,0.18)');
                }
            } catch (err) {
                this.stopWaveform();
                this.appendMessage('ai', `Error contacting AI agent: ${err.message}`);
                this.updateStatus('ERROR', '#ef4444', 'rgba(239,68,68,0.2)');
            }
        }

        // Voice-to-Action Interoperability
        executeDashboardAction(data) {
            if (!data.action) return;

            console.log(`[GoogleVoiceCopilot] Executing action: ${data.action}`, data.customer_id);

            if (data.action === 'OPEN_CUSTOMER' && data.customer_id) {
                if (typeof window.openDossier === 'function') {
                    window.openDossier(data.customer_id);
                } else if (typeof window.openCustomerDrawer === 'function') {
                    window.openCustomerDrawer(data.customer_id);
                }
            } else if (data.action === 'FILTER_TIER') {
                const tier = data.customer_id || 'CRITICAL';
                const filterBtn = document.querySelector(`.filter-btn[data-tier="${tier}"]`);
                if (filterBtn) filterBtn.click();
            } else if (data.action === 'SWITCH_TAB' && data.customer_id) {
                const navTab = document.querySelector(`.nav-tab[data-target="${data.customer_id}"]`);
                if (navTab) navTab.click();
            }
        }

        // Google SpeechSynthesis (TTS)
        speak(text) {
            if (!('speechSynthesis' in window)) return;
            this.stopSpeechSynthesis();

            const utterance = new SpeechSynthesisUtterance(text);
            utterance.rate = 1.05;
            utterance.pitch = 1.02;
            utterance.lang = 'en-US';

            utterance.onstart = () => {
                this.updateStatus('SPEAKING (GOOGLE TTS)', '#38bdf8', 'rgba(56,189,248,0.2)');
                this.startWaveform('#38bdf8');
            };

            utterance.onend = () => {
                this.updateStatus('STANDBY', '#4ade80', 'rgba(34,197,94,0.18)');
                this.stopWaveform();
            };

            utterance.onerror = () => {
                this.updateStatus('STANDBY', '#4ade80', 'rgba(34,197,94,0.18)');
                this.stopWaveform();
            };

            window.speechSynthesis.speak(utterance);
        }

        stopSpeechSynthesis() {
            if ('speechSynthesis' in window) {
                window.speechSynthesis.cancel();
            }
        }

        // Visual Waveform Animation
        startWaveform(color = '#06b6d4') {
            const bars = document.querySelectorAll('.gvoice-bar');
            if (this.waveformInterval) clearInterval(this.waveformInterval);
            this.waveformInterval = setInterval(() => {
                bars.forEach(bar => {
                    const h = Math.floor(Math.random() * 12) + 3;
                    bar.style.height = `${h}px`;
                    bar.style.background = color;
                });
            }, 120);
        }

        stopWaveform() {
            if (this.waveformInterval) clearInterval(this.waveformInterval);
            this.waveformInterval = null;
            const bars = document.querySelectorAll('.gvoice-bar');
            bars.forEach((bar, idx) => {
                bar.style.height = `${[4, 10, 6, 12, 7][idx % 5]}px`;
                bar.style.background = '#06b6d4';
            });
        }

        // Status pill helper
        updateStatus(text, color, bg) {
            const statusPill = document.getElementById('gvoice-status-pill');
            const waveDot = document.getElementById('gvoice-wave-dot');
            const waveText = document.getElementById('gvoice-wave-text');

            if (statusPill) {
                statusPill.textContent = text;
                statusPill.style.color = color;
                statusPill.style.background = bg;
            }
            if (waveDot) {
                waveDot.style.background = color;
                waveDot.style.boxShadow = `0 0 8px ${color}`;
            }
            if (waveText) {
                waveText.textContent = text === 'STANDBY' ? 'Voice Standby' : text;
            }
        }

        // Append message to modal dialogue stream
        appendMessage(sender, text) {
            const stream = document.getElementById('gvoice-stream');
            if (!stream) return;

            const msgEl = document.createElement('div');
            if (sender === 'user') {
                msgEl.className = 'gvoice-msg-user';
                msgEl.innerHTML = `
                    <div style="font-size: 9px; font-family: ui-monospace, monospace; color: rgba(255,255,255,0.8); margin-bottom: 2px;">👤 SPOKEN INQUIRY</div>
                    <div>${text}</div>
                `;
            } else {
                msgEl.className = 'gvoice-msg-ai';
                msgEl.innerHTML = `
                    <div class="gvoice-sender-tag">🤖 VALIANT AI INVESTIGATOR (VOICE COPILOT)</div>
                    <div>${this.formatMarkdown(text)}</div>
                `;
            }
            stream.appendChild(msgEl);
            stream.scrollTop = stream.scrollHeight;
        }

        formatMarkdown(text) {
            return text
                .replace(/^### (.*$)/gim, '<div style="font-size: 13px; font-weight: 700; color: #38bdf8; margin: 4px 0;">$1</div>')
                .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                .replace(/\*(.*?)\*/g, '<em>$1</em>')
                .replace(/`([^`]+)`/g, '<code style="background: rgba(0,0,0,0.5); color: #67e8f9; padding: 1px 4px; border-radius: 3px; font-family: monospace;">$1</code>')
                .replace(/\n/g, '<br/>');
        }

        open() {
            const modal = document.getElementById('gvoice-modal-window');
            if (modal) modal.style.display = 'flex';
        }

        close() {
            const modal = document.getElementById('gvoice-modal-window');
            if (modal) modal.style.display = 'none';
            this.stopSpeechSynthesis();
        }
    }

    // Auto-mount when DOM is ready
    function init() {
        window.GoogleVoiceCopilot = new GoogleVoiceCopilotService();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})(window, document);
