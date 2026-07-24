const e = React.createElement;

function VoiceAIAssistant() {
    const [isListening, setIsListening] = React.useState(false);
    const [statusText, setStatusText] = React.useState('Tap the mic to start');
    const [transcript, setTranscript] = React.useState('');
    const [waveLevel, setWaveLevel] = React.useState(0);

    // Use a ref to track the latest transcript value (avoids stale closure)
    const transcriptRef = React.useRef('');

    const presetPrompts = [
        "Show hotspots in Bengaluru South",
        "Summarize incidents in the last 24 hours",
        "Dispatch nearest unit to MG Road",
        "Translate this Kannada statement to English",
        "\u0CAE\u0CC8\u0CB8\u0CC2\u0CB0\u0CBF\u0CA8\u0CB2\u0CCD\u0CB2\u0CBF \u0C95\u0CB3\u0CB5\u0CC1 \u0CAA\u0CCD\u0CB0\u0C95\u0CB0\u0CA3\u0C97\u0CB3\u0CA8\u0CCD\u0CA8\u0CC1 \u0CA4\u0CCB\u0CB0\u0CBF\u0CB8\u0CBF"
    ];

    React.useEffect(() => {
        let interval;
        if (isListening) {
            interval = setInterval(() => {
                setWaveLevel(prev => (prev + 1) % 5);
            }, 180);
        } else {
            setWaveLevel(0);
        }
        return () => clearInterval(interval);
    }, [isListening]);

    const handleMicClick = () => {
        if (!isListening) {
            setIsListening(true);
            setStatusText('Listening in English / \u0C95\u0CA8\u0CCD\u0CA8\u0CA1...');
            setTranscript('');
            transcriptRef.current = '';

            const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
            if (SpeechRecognition) {
                const recognition = new SpeechRecognition();
                recognition.continuous = false;
                recognition.interimResults = true;
                const activeLangBtn = document.querySelector(".lang-btn.active");
                const activeLang = activeLangBtn && activeLangBtn.id === "btn-lang-kn" ? "kn-IN" : "en-IN";
                recognition.lang = activeLang;

                recognition.onresult = (event) => {
                    let text = '';
                    for (let i = 0; i < event.results.length; ++i) {
                        text += event.results[i][0].transcript;
                    }
                    setTranscript(text);
                    transcriptRef.current = text;
                };

                recognition.onend = () => {
                    setIsListening(false);
                    const finalText = transcriptRef.current.trim();
                    if (finalText) {
                        setStatusText('Transcribing complete. Executing query...');
                        // Navigate to AI view and send query
                        if (typeof switchToTab === 'function') switchToTab('ai-view');
                        // Also populate the AI chat input
                        const chatInput = document.getElementById('ai-chat-input');
                        if (chatInput) chatInput.value = finalText;
                        if (typeof sendAIQuery === 'function') {
                            sendAIQuery(finalText);
                        }
                    } else {
                        setStatusText('No speech detected. Tap the mic to try again.');
                    }
                };

                recognition.onerror = (event) => {
                    setIsListening(false);
                    console.warn('Voice recognition error:', event.error);
                    if (event.error === 'not-allowed') {
                        setStatusText('Microphone access denied. Please allow mic in browser settings.');
                    } else {
                        setStatusText('Voice error. Tap the mic to try again.');
                    }
                };

                try {
                    recognition.start();
                } catch (err) {
                    setIsListening(false);
                    setStatusText('Could not start mic. Try again.');
                    console.error('Recognition start error:', err);
                }
            } else {
                // No Web Speech API - show message
                setIsListening(false);
                setStatusText('Web Speech API not supported. Use the AI Assistant tab mic button instead.');
            }
        } else {
            setIsListening(false);
            setStatusText('Tap the mic to start');
        }
    };

    const handlePromptClick = (prompt) => {
        setTranscript(prompt);
        setStatusText('Executing: "' + prompt + '"');
        // Navigate to AI view and execute
        if (typeof switchToTab === 'function') switchToTab('ai-view');
        const chatInput = document.getElementById('ai-chat-input');
        if (chatInput) chatInput.value = prompt;
        if (typeof sendAIQuery === 'function') sendAIQuery(prompt);
    };

    return e('div', { className: 'react-voice-ai-card' }, [
        // Mic Outer Wrapper
        e('div', { key: 'mic-wrapper', className: 'react-mic-wrapper' }, [
            e('button', {
                key: 'mic-btn',
                className: 'react-mic-circle-btn ' + (isListening ? 'listening' : ''),
                onClick: handleMicClick,
                title: 'Tap mic to start voice search (English & Kannada)'
            }, [
                e('svg', {
                    key: 'svg-icon',
                    width: 32,
                    height: 32,
                    viewBox: '0 0 24 24',
                    fill: 'none',
                    stroke: 'currentColor',
                    strokeWidth: 2.2,
                    strokeLinecap: 'round',
                    strokeLinejoin: 'round'
                }, [
                    e('path', { key: 'm1', d: 'M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z' }),
                    e('path', { key: 'm2', d: 'M19 10v2a7 7 0 0 1-14 0v-2' }),
                    e('line', { key: 'm3', x1: '12', y1: '19', x2: '12', y2: '22' })
                ])
            ])
        ]),

        // Status Indicator Line
        e('div', { key: 'status-tag', className: 'react-status-tag' }, [
            e('span', { key: 'dot', className: 'react-status-dot ' + (isListening ? 'active' : '') }),
            statusText
        ]),

        // Dotted Waveform Line Animation
        e('div', { key: 'wave-line', className: 'react-wave-line' },
            Array.from({ length: 28 }).map(function(_, i) {
                return e('span', {
                    key: i,
                    className: 'wave-dot ' + (isListening && (i % 4 === waveLevel) ? 'active' : '')
                });
            })
        ),

        // Live Transcript Box
        transcript ? e('div', { key: 'transcript-box', className: 'react-transcript-box' }, [
            e('span', { key: 'lbl', className: 't-label' }, 'Speech Transcribed: '),
            transcript
        ]) : null,

        // Preset Prompt Pill Buttons
        e('div', { key: 'pills-container', className: 'react-preset-pills' },
            presetPrompts.map(function(prompt, idx) {
                return e('button', {
                    key: idx,
                    className: 'react-prompt-pill',
                    onClick: function() { handlePromptClick(prompt); }
                }, '"' + prompt + '"');
            })
        )
    ]);
}

window.renderReactVoiceAI = function() {
    const rootEl = document.getElementById("react-voice-ai-root");
    if (rootEl && window.ReactDOM) {
        const root = ReactDOM.createRoot(rootEl);
        root.render(React.createElement(VoiceAIAssistant));
    }
};

document.addEventListener("DOMContentLoaded", function() {
    window.renderReactVoiceAI();
});
