const e = React.createElement;

function VoiceAIAssistant() {
    const [isListening, setIsListening] = React.useState(false);
    const [statusText, setStatusText] = React.useState('Tap the mic to start');
    const [transcript, setTranscript] = React.useState('');
    const [waveLevel, setWaveLevel] = React.useState(0);
    const [selectedLang, setSelectedLang] = React.useState('en-IN');

    // Ref to track latest transcript for use inside speech callbacks
    const transcriptRef = React.useRef('');
    const recognitionRef = React.useRef(null);

    const presetPrompts = [
        { text: "Show hotspots in Bengaluru South", lang: "en" },
        { text: "Summarize incidents in the last 24 hours", lang: "en" },
        { text: "\u0CAE\u0CC8\u0CB8\u0CC2\u0CB0\u0CBF\u0CA8\u0CB2\u0CCD\u0CB2\u0CBF \u0C95\u0CB3\u0CB5\u0CC1 \u0CAA\u0CCD\u0CB0\u0C95\u0CB0\u0CA3\u0C97\u0CB3\u0CC1", lang: "kn" },
        { text: "\u0CAC\u0CC6\u0C82\u0C97\u0CB3\u0CC2\u0CB0\u0CBF\u0CA8\u0CB2\u0CCD\u0CB2\u0CBF \u0CA6\u0CB0\u0CCB\u0CA1\u0CC6 \u0CAA\u0CCD\u0CB0\u0C95\u0CB0\u0CA3\u0C97\u0CB3\u0CC1", lang: "kn" },
        { text: "Dispatch nearest unit to MG Road", lang: "en" }
    ];

    // Wave animation effect
    React.useEffect(function() {
        var interval;
        if (isListening) {
            interval = setInterval(function() {
                setWaveLevel(function(prev) { return (prev + 1) % 5; });
            }, 180);
        } else {
            setWaveLevel(0);
        }
        return function() { clearInterval(interval); };
    }, [isListening]);

    var handleMicClick = function() {
        if (isListening) {
            // Stop listening
            if (recognitionRef.current) {
                try { recognitionRef.current.stop(); } catch(err) {}
            }
            setIsListening(false);
            setStatusText('Stopped. Tap the mic to start again.');
            return;
        }

        // Start listening
        setIsListening(true);
        setTranscript('');
        transcriptRef.current = '';

        var langLabel = selectedLang === 'kn-IN' ? '\u0C95\u0CA8\u0CCD\u0CA8\u0CA1 (Kannada)' : 'English';
        setStatusText('Listening in ' + langLabel + '...');

        var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) {
            setIsListening(false);
            setStatusText('Speech recognition not supported in this browser. Use Chrome.');
            return;
        }

        var recognition = new SpeechRecognition();
        recognitionRef.current = recognition;
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = selectedLang;
        recognition.maxAlternatives = 1;

        recognition.onresult = function(event) {
            var finalText = '';
            var interimText = '';
            for (var i = 0; i < event.results.length; i++) {
                if (event.results[i].isFinal) {
                    finalText += event.results[i][0].transcript + ' ';
                } else {
                    interimText += event.results[i][0].transcript;
                }
            }
            var combined = (finalText + interimText).trim();
            setTranscript(combined);
            transcriptRef.current = combined;
        };

        recognition.onend = function() {
            setIsListening(false);
            var finalText = transcriptRef.current.trim();
            if (finalText) {
                setStatusText('Transcribed! Sending to AI Assistant...');
                // Navigate to AI view and send query
                if (typeof switchToTab === 'function') switchToTab('ai-view');
                var chatInput = document.getElementById('ai-chat-input');
                if (chatInput) chatInput.value = finalText;
                if (typeof sendAIQuery === 'function') {
                    sendAIQuery(finalText);
                }
            } else {
                setStatusText('No speech detected. Tap the mic to try again.');
            }
        };

        recognition.onerror = function(event) {
            setIsListening(false);
            recognitionRef.current = null;
            if (event.error === 'not-allowed') {
                setStatusText('Microphone blocked! Allow mic permission in Chrome settings.');
            } else if (event.error === 'no-speech') {
                setStatusText('No speech heard. Tap the mic and speak clearly.');
            } else if (event.error === 'network') {
                setStatusText('Network error. Check your internet connection.');
            } else {
                setStatusText('Error: ' + event.error + '. Tap mic to retry.');
            }
        };

        try {
            recognition.start();
        } catch (err) {
            setIsListening(false);
            setStatusText('Could not start microphone. Try again.');
        }
    };

    var handlePromptClick = function(prompt) {
        setTranscript(prompt);
        setStatusText('Executing: "' + prompt + '"');
        if (typeof switchToTab === 'function') switchToTab('ai-view');
        var chatInput = document.getElementById('ai-chat-input');
        if (chatInput) chatInput.value = prompt;
        if (typeof sendAIQuery === 'function') sendAIQuery(prompt);
    };

    var handleLangChange = function(lang) {
        setSelectedLang(lang);
        // Also sync with the AI tab lang buttons
        var btnEn = document.getElementById('btn-lang-en');
        var btnKn = document.getElementById('btn-lang-kn');
        if (lang === 'kn-IN') {
            if (btnKn) { btnKn.classList.add('active'); }
            if (btnEn) { btnEn.classList.remove('active'); }
        } else {
            if (btnEn) { btnEn.classList.add('active'); }
            if (btnKn) { btnKn.classList.remove('active'); }
        }
        setStatusText(lang === 'kn-IN' ? '\u0C95\u0CA8\u0CCD\u0CA8\u0CA1\u0CA6\u0CB2\u0CCD\u0CB2\u0CBF \u0CAE\u0CBE\u0CA4\u0CA8\u0CBE\u0CA1\u0CBF - Tap mic' : 'Speak in English - Tap mic');
    };

    return e('div', { className: 'react-voice-ai-card' }, [

        // Language Toggle Buttons
        e('div', { key: 'lang-toggle', className: 'react-lang-toggle' }, [
            e('button', {
                key: 'en-btn',
                className: 'react-lang-btn ' + (selectedLang === 'en-IN' ? 'active' : ''),
                onClick: function() { handleLangChange('en-IN'); }
            }, '\uD83C\uDDEC\uD83C\uDDE7 English'),
            e('button', {
                key: 'kn-btn',
                className: 'react-lang-btn ' + (selectedLang === 'kn-IN' ? 'active' : ''),
                onClick: function() { handleLangChange('kn-IN'); }
            }, '\uD83C\uDDEE\uD83C\uDDF3 \u0C95\u0CA8\u0CCD\u0CA8\u0CA1')
        ]),

        // Mic Outer Wrapper
        e('div', { key: 'mic-wrapper', className: 'react-mic-wrapper' }, [
            e('button', {
                key: 'mic-btn',
                className: 'react-mic-circle-btn ' + (isListening ? 'listening' : ''),
                onClick: handleMicClick,
                title: 'Tap mic to start voice search'
            }, [
                isListening
                    ? e('svg', {
                        key: 'stop-icon', width: 28, height: 28, viewBox: '0 0 24 24',
                        fill: 'currentColor', stroke: 'none'
                    }, [
                        e('rect', { key: 'r', x: 6, y: 6, width: 12, height: 12, rx: 2 })
                    ])
                    : e('svg', {
                        key: 'mic-icon', width: 32, height: 32, viewBox: '0 0 24 24',
                        fill: 'none', stroke: 'currentColor', strokeWidth: 2.2,
                        strokeLinecap: 'round', strokeLinejoin: 'round'
                    }, [
                        e('path', { key: 'm1', d: 'M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z' }),
                        e('path', { key: 'm2', d: 'M19 10v2a7 7 0 0 1-14 0v-2' }),
                        e('line', { key: 'm3', x1: '12', y1: '19', x2: '12', y2: '22' })
                    ])
            ])
        ]),

        // Status Indicator
        e('div', { key: 'status-tag', className: 'react-status-tag' }, [
            e('span', { key: 'dot', className: 'react-status-dot ' + (isListening ? 'active' : '') }),
            statusText
        ]),

        // Dotted Waveform Animation
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
            e('span', { key: 'lbl', className: 't-label' },
                selectedLang === 'kn-IN' ? '\u0CA7\u0CCD\u0CB5\u0CA8\u0CBF \u0CAA\u0CB0\u0CBF\u0CB5\u0CB0\u0CCD\u0CA4\u0CA8\u0CC6: ' : 'Transcribed: '
            ),
            transcript
        ]) : null,

        // Preset Prompt Pill Buttons
        e('div', { key: 'pills-container', className: 'react-preset-pills' },
            presetPrompts.map(function(item, idx) {
                return e('button', {
                    key: idx,
                    className: 'react-prompt-pill',
                    onClick: function() { handlePromptClick(item.text); }
                }, (item.lang === 'kn' ? '\uD83C\uDDEE\uD83C\uDDF3 ' : '\uD83D\uDD0D ') + item.text);
            })
        )
    ]);
}

window.renderReactVoiceAI = function() {
    var rootEl = document.getElementById("react-voice-ai-root");
    if (rootEl && window.ReactDOM) {
        var root = ReactDOM.createRoot(rootEl);
        root.render(React.createElement(VoiceAIAssistant));
    }
};

document.addEventListener("DOMContentLoaded", function() {
    window.renderReactVoiceAI();
});
