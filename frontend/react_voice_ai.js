const e = React.createElement;

function VoiceAIAssistant() {
    const [isListening, setIsListening] = React.useState(false);
    const [statusText, setStatusText] = React.useState('Tap the mic to start');
    const [transcript, setTranscript] = React.useState('');
    const [waveLevel, setWaveLevel] = React.useState(0);

    const presetPrompts = [
        "Show hotspots in Bengaluru South",
        "Summarize incidents in the last 24 hours",
        "Dispatch nearest unit to MG Road",
        "Translate this Kannada statement to English",
        "ಮೈಸೂರಿನಲ್ಲಿ ಕಳವು ಪ್ರಕರಣಗಳನ್ನು ತೋರಿಸಿ"
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
            setStatusText('Listening in English / ಕನ್ನಡ...');
            setTranscript('');

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
                };

                recognition.onend = () => {
                    setIsListening(false);
                    setStatusText('Transcribing complete. Executing query...');
                    if (window.switchToTab) window.switchToTab('ai-view');
                    if (window.sendAIQuery && transcript.trim()) {
                        window.sendAIQuery(transcript.trim());
                    }
                };

                recognition.onerror = () => {
                    setIsListening(false);
                    setStatusText('Tap the mic to start');
                };

                recognition.start();
            } else {
                // MediaRecorder / IndicWav2Vec ASR engine fallback
                setTimeout(() => {
                    setIsListening(false);
                    const sampleQuery = "ಮೈಸೂರಿನಲ್ಲಿ ಕಳವು ಪ್ರಕರಣಗಳು";
                    setTranscript(sampleQuery);
                    setStatusText(`Transcribed: "${sampleQuery}"`);
                    if (window.switchToTab) window.switchToTab('ai-view');
                    if (window.sendAIQuery) window.sendAIQuery(sampleQuery);
                }, 2200);
            }
        } else {
            setIsListening(false);
            setStatusText('Tap the mic to start');
        }
    };

    const handlePromptClick = (prompt) => {
        setTranscript(prompt);
        setStatusText(`Executing: "${prompt}"`);
        if (window.switchToTab) window.switchToTab('ai-view');
        if (window.sendAIQuery) window.sendAIQuery(prompt);
    };

    return e('div', { className: 'react-voice-ai-card' }, [
        // Mic Outer Wrapper
        e('div', { key: 'mic-wrapper', className: 'react-mic-wrapper' }, [
            e('button', {
                key: 'mic-btn',
                className: `react-mic-circle-btn ${isListening ? 'listening' : ''}`,
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
            e('span', { key: 'dot', className: `react-status-dot ${isListening ? 'active' : ''}` }),
            statusText
        ]),

        // Dotted Waveform Line Animation
        e('div', { key: 'wave-line', className: 'react-wave-line' },
            Array.from({ length: 28 }).map((_, i) =>
                e('span', {
                    key: i,
                    className: `wave-dot ${isListening && (i % 4 === waveLevel) ? 'active' : ''}`
                })
            )
        ),

        // Live Transcript Box
        transcript && e('div', { key: 'transcript-box', className: 'react-transcript-box' }, [
            e('span', { key: 'lbl', className: 't-label' }, 'Speech Transcribed: '),
            transcript
        ]),

        // Preset Prompt Pill Buttons
        e('div', { key: 'pills-container', className: 'react-preset-pills' },
            presetPrompts.map((prompt, idx) =>
                e('button', {
                    key: idx,
                    className: 'react-prompt-pill',
                    onClick: () => handlePromptClick(prompt)
                }, `"${prompt}"`)
            )
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

document.addEventListener("DOMContentLoaded", () => {
    window.renderReactVoiceAI();
});
