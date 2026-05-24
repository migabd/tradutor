document.addEventListener("DOMContentLoaded", () => {
    // Initialize Lucide Icons
    lucide.createIcons();

    // DOM Elements
    const apiKeyInput = document.getElementById("api-key-input");
    const saveKeyBtn = document.getElementById("save-key-btn");
    const keyStatusMsg = document.getElementById("key-status-msg");
    const youtubeUrlInput = document.getElementById("youtube-url");
    const modelSelect = document.getElementById("model-select");
    const customModelWrapper = document.getElementById("custom-model-wrapper");
    const customModelInput = document.getElementById("custom-model");
    const voiceSelect = document.getElementById("voice-select");
    const audioDuckingInput = document.getElementById("audio-ducking");
    const startDubbingBtn = document.getElementById("start-dubbing-btn");

    const welcomeState = document.getElementById("welcome-state");
    const progressState = document.getElementById("progress-state");
    const resultsState = document.getElementById("results-state");

    const mainProgressBar = document.getElementById("main-progress-bar");
    const progressPercent = document.getElementById("progress-percent");
    const progressMessage = document.getElementById("progress-message");

    const dubbedPlayer = document.getElementById("dubbed-video-player");
    const originalPlayer = document.getElementById("original-video-player");
    const downloadVideoBtn = document.getElementById("download-video-btn");
    const segmentsTimeline = document.getElementById("segments-timeline");

    const toast = document.getElementById("toast");
    const toastIcon = document.getElementById("toast-icon");
    const toastMsg = document.getElementById("toast-msg");

    // Task & State variables
    let currentTaskId = null;
    let pollingInterval = null;
    let isRegenerating = false;
    let toastTimeout = null;
    let activeStopAtEnd = null;
    let syncListeners = { onPlay: null, onPause: null, onSeeking: null };

    // Load saved API Key from localStorage
    const savedKey = localStorage.getItem("gemini_api_key");
    if (savedKey) {
        apiKeyInput.value = savedKey;
        keyStatusMsg.style.display = "block";
        keyStatusMsg.textContent = "Chave de API salva localmente.";
        keyStatusMsg.style.color = "var(--accent-success)";
    }

    // Save & Verify API Key
    saveKeyBtn.addEventListener("click", async () => {
        const apiKey = apiKeyInput.value.trim();
        if (!apiKey) {
            showToast("Insira uma chave de API válida.", "danger");
            return;
        }

        saveKeyBtn.disabled = true;
        saveKeyBtn.innerHTML = '<i data-lucide="loader" class="spin"></i>';
        lucide.createIcons();

        try {
            const response = await fetch("/api/check_key", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ api_key: apiKey })
            });
            const data = await response.json();

            if (data.valid) {
                localStorage.setItem("gemini_api_key", apiKey);
                keyStatusMsg.style.display = "block";
                keyStatusMsg.textContent = "Chave de API válida!";
                keyStatusMsg.style.color = "var(--accent-success)";
                showToast("Chave de API validada e salva com sucesso!", "success");
            } else {
                keyStatusMsg.style.display = "block";
                keyStatusMsg.textContent = "Chave inválida. Verifique e tente novamente.";
                keyStatusMsg.style.color = "var(--accent-danger)";
                showToast("Erro ao validar chave: " + data.error, "danger");
            }
        } catch (err) {
            showToast("Falha na comunicação com o servidor.", "danger");
        } finally {
            saveKeyBtn.disabled = false;
            saveKeyBtn.innerHTML = '<i data-lucide="check"></i>';
            lucide.createIcons();
        }
    });

    // Populate quick test URLs
    document.querySelectorAll(".example-link-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            youtubeUrlInput.value = btn.getAttribute("data-url");
            showToast("URL de teste carregada!", "info");
        });
    });

    // Model selection custom input toggle
    modelSelect.addEventListener("change", () => {
        if (modelSelect.value === "custom") {
            customModelWrapper.classList.remove("hidden");
        } else {
            customModelWrapper.classList.add("hidden");
        }
    });

    // Start Dubbing Pipeline
    startDubbingBtn.addEventListener("click", async () => {
        const apiKey = localStorage.getItem("gemini_api_key") || apiKeyInput.value.trim();
        const url = youtubeUrlInput.value.trim();
        let model = modelSelect.value;
        const voice = voiceSelect.value;
        const ducking = audioDuckingInput.checked;

        if (model === "custom") {
            model = customModelInput.value.trim();
            if (!model) {
                showToast("Por favor, insira o ID do modelo Gemini personalizado.", "danger");
                return;
            }
        }

        if (!apiKey) {
            showToast("Por favor, configure e salve sua Gemini API Key antes de começar.", "danger");
            return;
        }
        if (!url) {
            showToast("Insira um link do YouTube válido.", "danger");
            return;
        }

        // Reset & transition states
        welcomeState.classList.add("hidden");
        resultsState.classList.add("hidden");
        progressState.classList.remove("hidden");
        
        resetStepper();
        updateProgressBar(5, "Iniciando pipeline de dublagem...");
        
        startDubbingBtn.disabled = true;
        startDubbingBtn.innerHTML = '<span>Processando...</span><i data-lucide="loader" class="spin"></i>';
        lucide.createIcons();

        try {
            const response = await fetch("/api/dub", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-Gemini-Key": apiKey
                },
                body: JSON.stringify({ url, voice, ducking, model })
            });

            if (!response.ok) {
                const errData = await response.json();
                throw new Error(errData.detail || "Erro ao iniciar dublagem.");
            }

            const data = await response.json();
            currentTaskId = data.task_id;
            
            // Start polling for progress
            startPolling(currentTaskId);

        } catch (err) {
            showToast(err.message, "danger");
            progressState.classList.add("hidden");
            welcomeState.classList.remove("hidden");
            resetStartButton();
        }
    });

    function resetStartButton() {
        startDubbingBtn.disabled = false;
        startDubbingBtn.innerHTML = '<span>Iniciar Dublagem Automática</span><i data-lucide="wand-2"></i>';
        lucide.createIcons();
    }

    function resetStepper() {
        document.querySelectorAll(".step").forEach(step => {
            step.classList.remove("active", "completed");
        });
    }

    function updateProgressBar(percent, message) {
        mainProgressBar.style.width = `${percent}%`;
        progressPercent.textContent = `${percent}%`;
        progressMessage.textContent = message;
    }

    function startPolling(taskId) {
        if (pollingInterval) clearInterval(pollingInterval);
        
        pollingInterval = setInterval(() => {
            pollTaskStatus(taskId);
        }, 2000);
    }

    async function pollTaskStatus(taskId) {
        const apiKey = localStorage.getItem("gemini_api_key");
        try {
            const response = await fetch(`/api/status/${taskId}`, {
                headers: { "X-Gemini-Key": apiKey }
            });
            const data = await response.json();

            if (data.status === "processing") {
                updateProgressBar(data.progress, data.message);
                updateStepper(data.progress);
            } else if (data.status === "completed") {
                clearInterval(pollingInterval);
                updateProgressBar(100, "Dublagem finalizada com sucesso!");
                updateStepper(100);
                showToast("Processamento finalizado!", "success");
                
                // Show results
                setTimeout(() => {
                    progressState.classList.add("hidden");
                    resultsState.classList.remove("hidden");
                    displayResults(data);
                    resetStartButton();
                }, 1000);
                
            } else if (data.status === "failed") {
                clearInterval(pollingInterval);
                showToast(`Falha no processamento: ${data.error}`, "danger");
                updateProgressBar(100, "Erro: " + data.error);
                progressMessage.style.color = "var(--accent-danger)";
                resetStartButton();
            }
        } catch (err) {
            console.error("Error polling task status:", err);
        }
    }

    function updateStepper(progress) {
        const stepDownload = document.getElementById("step-download");
        const stepExtract = document.getElementById("step-extract");
        const stepTranscribe = document.getElementById("step-transcribe");
        const stepVoice = document.getElementById("step-voice");

        if (progress >= 15 && progress < 30) {
            stepDownload.classList.add("active");
        } else if (progress >= 30 && progress < 50) {
            stepDownload.classList.remove("active");
            stepDownload.classList.add("completed");
            stepExtract.classList.add("active");
        } else if (progress >= 50 && progress < 80) {
            stepDownload.classList.add("completed");
            stepExtract.classList.remove("active");
            stepExtract.classList.add("completed");
            stepTranscribe.classList.add("active");
        } else if (progress >= 80 && progress < 100) {
            stepDownload.classList.add("completed");
            stepExtract.classList.add("completed");
            stepTranscribe.classList.remove("active");
            stepTranscribe.classList.add("completed");
            stepVoice.classList.add("active");
        } else if (progress >= 100) {
            stepDownload.classList.add("completed");
            stepExtract.classList.add("completed");
            stepTranscribe.classList.add("completed");
            stepVoice.classList.remove("active");
            stepVoice.classList.add("completed");
        }
    }

    function displayResults(data) {
        const cacheBuster = `?t=${Date.now()}`;
        dubbedPlayer.src = `${data.video_url}${cacheBuster}`;
        originalPlayer.src = `/api/download_original/${data.task_id}${cacheBuster}`;
        downloadVideoBtn.href = data.video_url;

        // Load players
        dubbedPlayer.load();
        originalPlayer.load();

        // Premium feature: Sync the video players
        syncPlayers();

        // Render Segments
        renderSegments(data.segments);
    }

    // Synchronize both players (play, pause, seek)
    function syncPlayers() {
        // Remove old listeners to prevent duplicates on repeated calls
        if (syncListeners.onPlay) {
            dubbedPlayer.removeEventListener("play", syncListeners.onPlay);
            dubbedPlayer.removeEventListener("pause", syncListeners.onPause);
            dubbedPlayer.removeEventListener("seeking", syncListeners.onSeeking);
        }

        let isSyncing = false;

        syncListeners.onPlay = () => {
            if (isSyncing) return;
            isSyncing = true;
            originalPlayer.play().catch(() => {});
            isSyncing = false;
        };

        syncListeners.onPause = () => {
            if (isSyncing) return;
            isSyncing = true;
            originalPlayer.pause();
            isSyncing = false;
        };

        syncListeners.onSeeking = () => {
            if (isSyncing) return;
            isSyncing = true;
            originalPlayer.currentTime = dubbedPlayer.currentTime;
            isSyncing = false;
        };

        dubbedPlayer.addEventListener("play", syncListeners.onPlay);
        dubbedPlayer.addEventListener("pause", syncListeners.onPause);
        dubbedPlayer.addEventListener("seeking", syncListeners.onSeeking);
    }

    function formatTime(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        const ms = Math.floor((seconds % 1) * 10);
        return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}.${ms}`;
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function renderSegments(segments) {
        segmentsTimeline.innerHTML = "";
        
        if (!segments || segments.length === 0) {
            segmentsTimeline.innerHTML = '<div class="no-segments">Nenhum segmento de fala detectado.</div>';
            return;
        }

        segments.forEach(seg => {
            const card = document.createElement("div");
            card.className = "segment-card";
            card.id = `segment-card-${seg.id}`;
            card.innerHTML = `
                <div class="segment-meta-panel">
                    <span class="segment-number">Trecho #${seg.id + 1}</span>
                    <span class="segment-time"><i data-lucide="clock" class="icon-small" style="margin-right: 3px;"></i> ${formatTime(seg.start)}</span>
                </div>
                <div class="segment-content-panel">
                    <div class="segment-original">${escapeHtml(seg.original_text)}</div>
                    <div class="segment-translation-wrapper">
                        <textarea class="translation-textarea" id="textarea-${seg.id}">${escapeHtml(seg.translation)}</textarea>
                    </div>
                    <div class="segment-card-actions">
                        <button class="action-btn secondary play-segment-btn" data-start="${seg.start}" data-end="${seg.end}">
                            <i data-lucide="play" class="icon-small"></i> Ouvir Trecho
                        </button>
                        <button class="action-btn save-segment-btn" data-id="${seg.id}">
                            <i data-lucide="save" class="icon-small"></i> Re-gerar Voz
                        </button>
                    </div>
                </div>
            `;
            segmentsTimeline.appendChild(card);
        });

        lucide.createIcons();

        // Hook up Play segment listener
        document.querySelectorAll(".play-segment-btn").forEach(btn => {
            btn.addEventListener("click", () => {
                const start = parseFloat(btn.getAttribute("data-start"));
                const end = parseFloat(btn.getAttribute("data-end"));
                
                // Remove any previous stopAtEnd listener to prevent leaks
                if (activeStopAtEnd) {
                    dubbedPlayer.removeEventListener("timeupdate", activeStopAtEnd);
                    activeStopAtEnd = null;
                }

                // Seek dubbed player to segment start and play
                dubbedPlayer.currentTime = start;
                dubbedPlayer.play();

                // Set up a listener to pause once it hits the end timestamp
                activeStopAtEnd = () => {
                    if (dubbedPlayer.currentTime >= end) {
                        dubbedPlayer.pause();
                        dubbedPlayer.removeEventListener("timeupdate", activeStopAtEnd);
                        activeStopAtEnd = null;
                    }
                };
                
                dubbedPlayer.addEventListener("timeupdate", activeStopAtEnd);
            });
        });

        // Hook up Re-generate voice listener
        document.querySelectorAll(".save-segment-btn").forEach(btn => {
            btn.addEventListener("click", async () => {
                const segId = parseInt(btn.getAttribute("data-id"));
                const updatedText = document.getElementById(`textarea-${segId}`).value.trim();
                const apiKey = localStorage.getItem("gemini_api_key");
                const voice = voiceSelect.value;
                const ducking = audioDuckingInput.checked;

                if (!updatedText) {
                    showToast("O texto traduzido não pode estar em branco.", "danger");
                    return;
                }

                btn.disabled = true;
                btn.innerHTML = '<i data-lucide="loader" class="spin"></i> Re-gerando...';
                lucide.createIcons();
                showToast(`Solicitando regeneração do segmento #${segId + 1}...`, "info");

                try {
                    const response = await fetch("/api/regenerate_segment", {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/json",
                            "X-Gemini-Key": apiKey
                        },
                        body: JSON.stringify({
                            task_id: currentTaskId,
                            segment_id: segId,
                            updated_text: updatedText,
                            voice: voice,
                            ducking: ducking
                        })
                    });

                    if (!response.ok) {
                        const err = await response.json();
                        throw new Error(err.detail || "Erro ao solicitar regeneração.");
                    }

                    // Start monitoring the task status again!
                    isRegenerating = true;
                    startRegenPolling(currentTaskId, segId, btn);

                } catch (err) {
                    showToast(err.message, "danger");
                    btn.disabled = false;
                    btn.innerHTML = '<i data-lucide="save" class="icon-small"></i> Re-gerar Voz';
                    lucide.createIcons();
                }
            });
        });
    }

    function startRegenPolling(taskId, segId, buttonEl) {
        if (pollingInterval) clearInterval(pollingInterval);

        pollingInterval = setInterval(async () => {
            const apiKey = localStorage.getItem("gemini_api_key");
            try {
                const response = await fetch(`/api/status/${taskId}`, {
                    headers: { "X-Gemini-Key": apiKey }
                });
                const data = await response.json();

                if (data.status === "completed") {
                    clearInterval(pollingInterval);
                    showToast("Segmento re-gerado e vídeo atualizado com sucesso!", "success");
                    
                    buttonEl.disabled = false;
                    buttonEl.innerHTML = '<i data-lucide="save" class="icon-small"></i> Re-gerar Voz';
                    
                    // Reload video players with new video stream
                    const cacheBuster = `?t=${Date.now()}`;
                    dubbedPlayer.src = `${data.video_url}${cacheBuster}`;
                    dubbedPlayer.load();
                    
                    // Re-render timeline to match any changes
                    renderSegments(data.segments);
                    isRegenerating = false;
                } else if (data.status === "failed") {
                    clearInterval(pollingInterval);
                    showToast(`Falha ao regenerar segmento: ${data.error}`, "danger");
                    buttonEl.disabled = false;
                    buttonEl.innerHTML = '<i data-lucide="save" class="icon-small"></i> Re-gerar Voz';
                    lucide.createIcons();
                    isRegenerating = false;
                }
            } catch (err) {
                console.error("Error polling regeneration:", err);
            }
        }, 2000);
    }

    // Toast Notification System
    function showToast(message, type = "info") {
        toastMsg.textContent = message;
        
        // Remove existing classes
        toast.className = "toast";
        
        // Add color & icon based on type
        if (type === "success") {
            toast.style.borderLeft = "4px solid var(--accent-success)";
            toastIcon.setAttribute("data-lucide", "check-circle-2");
            toastIcon.style.color = "var(--accent-success)";
        } else if (type === "danger") {
            toast.style.borderLeft = "4px solid var(--accent-danger)";
            toastIcon.setAttribute("data-lucide", "alert-triangle");
            toastIcon.style.color = "var(--accent-danger)";
        } else {
            toast.style.borderLeft = "4px solid var(--accent-indigo)";
            toastIcon.setAttribute("data-lucide", "info");
            toastIcon.style.color = "var(--accent-indigo)";
        }

        lucide.createIcons();
        toast.classList.remove("hidden");

        // Dismiss after 4 seconds (clear previous timer to avoid stacking)
        if (toastTimeout) clearTimeout(toastTimeout);
        toastTimeout = setTimeout(() => {
            toast.classList.add("hidden");
            toastTimeout = null;
        }, 4000);
    }
});
