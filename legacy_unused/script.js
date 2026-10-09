/* ----------------------------------------------------
   SSAKSSAK MOUSE MACRO - FRONTEND CONTROLLER (script.js)
   ---------------------------------------------------- */

// Global State
let ws = null;
let currentTab = "countdown";
let lockedCoords = null; // { x, y }
let isConnecting = false;
let clockInterval = null;

// Progress Ring Configuration
const ringCircle = document.getElementById("progress-ring-circle");
const radius = ringCircle.r.baseVal.value;
const circumference = 2 * Math.PI * radius;

ringCircle.style.strokeDasharray = `${circumference} ${circumference}`;
ringCircle.style.strokeDashoffset = circumference;

// Web Audio API Synth for high-tech micro blips
let audioCtx = null;

function initAudio() {
    if (!audioCtx) {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (audioCtx.state === 'suspended') {
        audioCtx.resume();
    }
}

function playSynthSound(freq, type = "sine", duration = 0.08, volume = 0.06) {
    try {
        initAudio();
        if (!audioCtx) return;
        
        const osc = audioCtx.createOscillator();
        const gainNode = audioCtx.createGain();
        
        osc.connect(gainNode);
        gainNode.connect(audioCtx.destination);
        
        osc.type = type;
        osc.frequency.setValueAtTime(freq, audioCtx.currentTime);
        
        gainNode.gain.setValueAtTime(volume, audioCtx.currentTime);
        gainNode.gain.exponentialRampToValueAtTime(0.0001, audioCtx.currentTime + duration);
        
        osc.start();
        osc.stop(audioCtx.currentTime + duration);
    } catch (e) {
        // Fallback silently if audio fails
    }
}

// UI Sounds mapping
const SOUNDS = {
    click: () => playSynthSound(880, "sine", 0.06, 0.05),
    success: () => {
        playSynthSound(587.33, "triangle", 0.08, 0.06);
        setTimeout(() => playSynthSound(880, "triangle", 0.12, 0.06), 70);
    },
    error: () => {
        playSynthSound(220, "sawtooth", 0.15, 0.08);
        setTimeout(() => playSynthSound(180, "sawtooth", 0.2, 0.08), 100);
    },
    tick: () => playSynthSound(1200, "sine", 0.02, 0.02),
    hover: () => playSynthSound(600, "sine", 0.02, 0.01)
};

// WebSocket Management
function connectWebSocket() {
    if (isConnecting) return;
    isConnecting = true;
    
    console.log("Connecting to WebSocket backend...");
    ws = new WebSocket("ws://127.0.0.1:8001");
    
    ws.onopen = () => {
        isConnecting = false;
        appendLog("[SYSTEM] 백엔드 서버와 실시간 통신 연결에 성공했습니다.", "system");
        updateStatusBadge("idle", "연결됨 (IDLE)");
    };
    
    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            handleWSMessage(data);
        } catch (e) {
            console.error("Error reading WebSocket packet:", e);
        }
    };
    
    ws.onclose = () => {
        isConnecting = false;
        updateStatusBadge("stopped", "연결 끊김 (DISCONNECTED)");
        appendLog("[WARNING] 백엔드와 연결이 끊어졌습니다. 3초 후 재연결을 시도합니다.", "warning");
        setTimeout(connectWebSocket, 3000);
    };
    
    ws.onerror = () => {
        isConnecting = false;
    };
}

// Handler for WebSocket incoming packets
function handleWSMessage(data) {
    switch (data.type) {
        case "init_state":
            // Set initial state
            updateStatusBadge(data.macro_state, getStatusString(data.macro_state));
            if (data.locked_coordinates) {
                updateLockedCoords(data.locked_coordinates.x, data.locked_coordinates.y);
            }
            break;
            
        case "mouse_pos":
            // Streamed coordinate position
            document.getElementById("live-x").innerText = data.x;
            document.getElementById("live-y").innerText = data.y;
            break;
            
        case "hotkey_pressed":
            // Physical hotkey feedback
            appendLog(`[HOTKEY] 단축키 ${data.hotkey} 가 감지되었습니다.`, "system");
            SOUNDS.click();
            if (data.hotkey === "F8") {
                updateLockedCoords(data.x, data.y);
            } else if (data.hotkey === "F9") {
                // F9 triggers Start
                startMacro();
            }
            break;
            
        case "status_change":
            updateStatusBadge(data.status, data.message);
            appendLog(`[STATUS] ${data.message}`, data.status === "stopped" ? "error" : "system");
            
            if (data.status === "stopped") {
                SOUNDS.error();
                resetCountdownUI();
            } else if (data.status === "armed") {
                SOUNDS.success();
            }
            break;
            
        case "tick":
            // Countdown timer tick updates
            updateCountdownUI(data.remaining, data.progress);
            break;
            
        case "interval_count":
            // Interval repeated counts
            const maxStr = data.max === -1 ? "무한" : data.max;
            appendLog(`[반복] 클릭 실행 중: (${data.count} / ${maxStr})`, "success");
            break;
            
        case "click_executed":
            // Click visualizer
            appendLog(`[딸깍] ${data.time} - (${data.x}, ${data.y}) 좌표에 ${getClickTypeKorean(data.click_type)} 성공.`, "success");
            SOUNDS.tick();
            
            // Temporary glow element on locked coordinates display if active
            const displayBox = document.getElementById("locked-coord-display");
            displayBox.classList.add("pulse-glow-effect");
            setTimeout(() => displayBox.classList.remove("pulse-glow-effect"), 500);
            break;
    }
}

// Helpers
function getStatusString(status) {
    switch (status) {
        case "idle": return "대기 중 (IDLE)";
        case "armed": return "매크로 대기 중 (ARMED)";
        case "clicking": return "클릭 실행 중 (CLICKING)";
        case "stopped": return "중단됨 (STOPPED)";
        default: return "알 수 없음";
    }
}

function getClickTypeKorean(type) {
    switch (type) {
        case "left": return "왼쪽 클릭";
        case "right": return "오른쪽 클릭";
        case "double": return "왼쪽 더블 클릭";
        default: return "클릭";
    }
}

// Update Status Ribbon Indicator
function updateStatusBadge(status, text) {
    const badge = document.getElementById("status-badge");
    const statusText = document.getElementById("status-text");
    
    badge.className = `badge ${status}`;
    statusText.innerText = text;
}

// Lock coordinates utility
function updateLockedCoords(x, y) {
    lockedCoords = { x: parseInt(x), y: parseInt(y) };
    document.getElementById("lock-x").innerText = x;
    document.getElementById("lock-y").innerText = y;
    
    // Auto-check "Use Locked Coordinates" when F8 is pressed
    const checkbox = document.getElementById("use-locked-coords");
    checkbox.checked = true;
    
    // Sync to Python core
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
            type: "set_locked",
            x: x,
            y: y
        }));
    }
    appendLog(`[LOCK] 마우스 클릭 목표 좌표가 X: ${x}, Y: ${y} 로 지정되었습니다.`, "system");
}

// SVG Circular gauge updater
function setProgress(percent) {
    const offset = circumference - (percent * circumference);
    ringCircle.style.strokeDashoffset = offset;
}

function updateCountdownUI(remaining, progress) {
    // Format minutes and seconds
    const minutes = Math.floor(remaining / 60);
    const seconds = Math.floor(remaining % 60);
    const milliseconds = Math.floor((remaining % 1) * 10);
    
    const formatted = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}.${milliseconds}`;
    document.getElementById("time-display").innerText = formatted;
    
    // Progress is a fraction between 0.0 (start) and 1.0 (end)
    // Ring should tick down (shrink to 0) as time gets closer
    setProgress(1 - progress);
}

function resetCountdownUI() {
    setProgress(0);
    document.getElementById("time-display").innerText = "00:00.0";
}

// Appends message block to Logging console
function appendLog(message, type = "normal") {
    const logBox = document.getElementById("console-log");
    const line = document.createElement("div");
    
    // Add custom timestamp
    const now = new Date();
    const timeStr = `[${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}.${String(now.getMilliseconds()).padStart(3, '0')}]`;
    
    line.className = `log-line ${type}`;
    line.innerText = `${timeStr} ${message}`;
    logBox.appendChild(line);
    
    // Cap scroll lines
    while (logBox.children.length > 150) {
        logBox.removeChild(logBox.firstChild);
    }
    
    // Smooth scroll to bottom
    logBox.scrollTop = logBox.scrollHeight;
}

// Ultra-precise Live clock in time tab
function startLiveClock() {
    if (clockInterval) clearInterval(clockInterval);
    
    const clockEl = document.getElementById("live-clock");
    
    clockInterval = setInterval(() => {
        const now = new Date();
        const yyyy = now.getFullYear();
        const mm = String(now.getMonth() + 1).padStart(2, '0');
        const dd = String(now.getDate()).padStart(2, '0');
        
        const hh = String(now.getHours()).padStart(2, '0');
        const min = String(now.getMinutes()).padStart(2, '0');
        const sec = String(now.getSeconds()).padStart(2, '0');
        const ms = String(now.getMilliseconds()).padStart(3, '0');
        
        clockEl.innerText = `${yyyy}-${mm}-${dd} ${hh}:${min}:${sec}.${ms}`;
    }, 15);
}

// Initialize Inputs and bindings
function initInputBinds() {
    // Tab switching
    const tabBtns = document.querySelectorAll(".tab-btn");
    const tabPanes = document.querySelectorAll(".tab-pane");
    
    tabBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            SOUNDS.click();
            tabBtns.forEach(b => b.classList.remove("active"));
            tabPanes.forEach(p => p.classList.remove("active"));
            
            btn.classList.add("active");
            currentTab = btn.getAttribute("data-tab");
            document.getElementById(`pane-${currentTab}`).classList.add("active");
        });
        
        btn.addEventListener("mouseenter", () => SOUNDS.hover());
    });
    
    // Countdown slider link
    const slider = document.getElementById("delay-slider");
    const sInput = document.getElementById("delay-s");
    const mInput = document.getElementById("delay-m");
    const hInput = document.getElementById("delay-h");
    const sliderLabel = document.getElementById("slider-val-display");
    
    slider.addEventListener("input", (e) => {
        const val = parseInt(e.target.value);
        
        const h = Math.floor(val / 3600);
        const m = Math.floor((val % 3600) / 60);
        const s = val % 60;
        
        hInput.value = h;
        mInput.value = m;
        sInput.value = s;
        
        sliderLabel.innerText = `${val}초`;
    });
    
    const syncSlider = () => {
        const h = parseInt(hInput.value) || 0;
        const m = parseInt(mInput.value) || 0;
        const s = parseInt(sInput.value) || 0;
        const total = h * 3600 + m * 60 + s;
        
        slider.value = Math.min(120, total);
        sliderLabel.innerText = `${total}초`;
    };
    
    hInput.addEventListener("change", syncSlider);
    mInput.addEventListener("change", syncSlider);
    sInput.addEventListener("change", syncSlider);
    
    // Interval counts radio triggers
    const radInfinite = document.getElementById("limit-infinite");
    const radNumber = document.getElementById("limit-number");
    const countInput = document.getElementById("click-count");
    
    radInfinite.addEventListener("change", () => {
        SOUNDS.click();
        countInput.disabled = true;
    });
    
    radNumber.addEventListener("change", () => {
        SOUNDS.click();
        countInput.disabled = false;
    });
    
    // Clear log button
    document.getElementById("btn-clear-log").addEventListener("click", () => {
        SOUNDS.click();
        const logBox = document.getElementById("console-log");
        logBox.innerHTML = "";
        appendLog("[SYSTEM] 로그 콘솔을 비웠습니다.", "system");
    });
    
    // Add sounds on input hover and checkbox toggles
    document.querySelectorAll("input, select, button").forEach(el => {
        el.addEventListener("mouseenter", () => {
            // Hover sound only for interactive triggers
            if (!el.disabled && el.tagName !== "INPUT") {
                SOUNDS.hover();
            }
        });
    });
    
    const lockCheckbox = document.getElementById("use-locked-coords");
    lockCheckbox.addEventListener("change", (e) => {
        SOUNDS.click();
        if (e.target.checked && !lockedCoords) {
            appendLog("[WARNING] 고정된 마우스 좌표가 없습니다! F8 키를 누르거나 수동으로 좌표를 확인하십시오.", "warning");
        }
        
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
                type: "set_locked",
                x: (e.target.checked && lockedCoords) ? lockedCoords.x : null,
                y: (e.target.checked && lockedCoords) ? lockedCoords.y : null
            }));
        }
    });

    // Default Scheduled Date-Time Setup (Set to +1 minute)
    const dtInput = document.getElementById("schedule-date");
    const offsetDate = new Date(Date.now() + 60000); // 1 min future
    
    const yyyy = offsetDate.getFullYear();
    const mm = String(offsetDate.getMonth() + 1).padStart(2, '0');
    const dd = String(offsetDate.getDate()).padStart(2, '0');
    const hh = String(offsetDate.getHours()).padStart(2, '0');
    const min = String(offsetDate.getMinutes()).padStart(2, '0');
    
    dtInput.value = `${yyyy}-${mm}-${dd}T${hh}:${min}`;
}

// Constructs configuration and starts the macro
function startMacro() {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
        appendLog("[ERROR] 백엔드 서버와 통신이 이루어지지 않았습니다. 연결 상태를 확인해주세요.", "error");
        SOUNDS.error();
        return;
    }
    
    const clickType = document.getElementById("click-type-select").value;
    const useLocked = document.getElementById("use-locked-coords").checked;
    
    if (useLocked && !lockedCoords) {
        appendLog("[ERROR] 좌표 고정 모드가 선택되어 있으나 고정된 좌표가 존재하지 않습니다! F8 키를 눌러 좌표를 고정하십시오.", "error");
        SOUNDS.error();
        return;
    }
    
    const config = {
        macro_type: currentTab,
        click_type: clickType,
        use_locked: useLocked
    };
    
    if (currentTab === "countdown") {
        const h = parseInt(document.getElementById("delay-h").value) || 0;
        const m = parseInt(document.getElementById("delay-m").value) || 0;
        const s = parseInt(document.getElementById("delay-s").value) || 0;
        const total = h * 3600 + m * 60 + s;
        
        if (total <= 0) {
            appendLog("[ERROR] 카운트다운 시간은 0초보다 커야 합니다.", "error");
            SOUNDS.error();
            return;
        }
        config.delay_seconds = total;
        
    } else if (currentTab === "scheduled") {
        const datetimeStr = document.getElementById("schedule-date").value;
        const msOffset = parseInt(document.getElementById("schedule-ms").value) || 0;
        
        if (!datetimeStr) {
            appendLog("[ERROR] 예약 시각을 입력해주십시오.", "error");
            SOUNDS.error();
            return;
        }
        
        const dt = new Date(datetimeStr);
        const targetTimestamp = (dt.getTime() + msOffset) / 1000.0;
        
        if (targetTimestamp <= Date.now() / 1000.0) {
            appendLog("[ERROR] 예약 시각은 반드시 현재 시각보다 나중이어야 합니다.", "error");
            SOUNDS.error();
            return;
        }
        config.target_timestamp = targetTimestamp;
        
    } else if (currentTab === "interval") {
        const val = parseInt(document.getElementById("click-interval").value) || 100;
        const unit = document.getElementById("interval-unit").value;
        const totalMs = unit === "s" ? val * 1000 : val;
        
        if (totalMs < 1) {
            appendLog("[ERROR] 클릭 주기는 최소 1ms 이상이어야 합니다.", "error");
            SOUNDS.error();
            return;
        }
        
        const isInfinite = document.getElementById("limit-infinite").checked;
        const clickCount = isInfinite ? -1 : (parseInt(document.getElementById("click-count").value) || 1);
        
        config.interval_ms = totalMs;
        config.click_count = clickCount;
    }
    
    // Transmit start request
    ws.send(JSON.stringify({
        type: "start",
        config: config
    }));
}

// Halts the macro execution immediately
function stopMacro() {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
            type: "stop"
        }));
    }
}

// Setup ripple blip animation effect on action button clicks
function createRipple(event) {
    const button = event.currentTarget;
    const circle = document.createElement("span");
    const diameter = Math.max(button.clientWidth, button.clientHeight);
    const radius = diameter / 2;
    
    const rect = button.getBoundingClientRect();
    
    circle.style.width = circle.style.height = `${diameter}px`;
    circle.style.left = `${event.clientX - rect.left - radius}px`;
    circle.style.top = `${event.clientY - rect.top - radius}px`;
    circle.classList.add("btn-ripple");
    
    const ripple = button.getElementsByClassName("btn-ripple")[0];
    if (ripple) {
        ripple.remove();
    }
    
    button.appendChild(circle);
}

// Bootstrap
document.addEventListener("DOMContentLoaded", () => {
    connectWebSocket();
    initInputBinds();
    startLiveClock();
    
    // Connect Ripple event listeners
    const btnStart = document.getElementById("btn-start");
    const btnStop = document.getElementById("btn-stop");
    
    btnStart.addEventListener("click", (e) => {
        createRipple(e);
        SOUNDS.click();
        startMacro();
    });
    
    btnStop.addEventListener("click", (e) => {
        createRipple(e);
        SOUNDS.click();
        stopMacro();
    });
    
    // Unlock Audio Context on visual elements trigger
    document.body.addEventListener("click", () => {
        initAudio();
    }, { once: true });
});
