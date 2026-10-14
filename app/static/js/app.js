// WhatsApp Web Multi-Account Dashboard Controller

let activeQrPollingInterval = null;
let currentQrSessionId = null;
let autoRefreshTimer = null;

// Initialize when DOM ready
document.addEventListener("DOMContentLoaded", () => {
    fetchSessions();
    fetchStats();
    // Auto-refresh sessions state every 4 seconds
    autoRefreshTimer = setInterval(fetchSessions, 4000);
});

// Toast Notifications
function showToast(message, type = "success") {
    const container = document.getElementById("toast-container");
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    const icon = type === "success" ? "✅" : "⚠️";
    toast.innerHTML = `<span>${icon}</span><span>${message}</span>`;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = "0";
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// Fetch and Render Sessions
async function fetchSessions() {
    try {
        const res = await fetch("/api/sessions");
        const json = await res.json();
        if (json.success) {
            renderSessions(json.data);
            updateStatsCounts(json.data);
            populateAccountSelects(json.data);
        }
    } catch (e) {
        console.error("Error fetching sessions:", e);
    }
}

// Fetch Server Health & Stats
async function fetchStats() {
    try {
        const res = await fetch("/api/health");
        const data = await res.json();
        document.getElementById("stat-total").innerText = data.total_accounts || 0;
        document.getElementById("stat-connected").innerText = data.connected_sessions || 0;
        document.getElementById("stat-running").innerText = data.running_sessions || 0;
    } catch (e) {
        console.error("Error fetching stats:", e);
    }
}

function updateStatsCounts(sessions) {
    const total = sessions.length;
    const connected = sessions.filter(s => s.status === "CONNECTED").length;
    const waiting = sessions.filter(s => s.status === "SCAN_QR" || s.status === "LOGGING_IN").length;
    const offline = sessions.filter(s => s.status === "OFFLINE").length;

    document.getElementById("stat-total").innerText = total;
    document.getElementById("stat-connected").innerText = connected;
    document.getElementById("stat-waiting").innerText = waiting;
    document.getElementById("stat-offline").innerText = offline;
}

function renderSessions(sessions) {
    const grid = document.getElementById("sessions-grid");
    const emptyState = document.getElementById("empty-state");

    if (!sessions || sessions.length === 0) {
        grid.innerHTML = "";
        emptyState.style.display = "block";
        return;
    }

    emptyState.style.display = "none";

    grid.innerHTML = sessions.map(session => {
        const statusMap = {
            "CONNECTED": { text: "متصل جاهز", icon: "🟢", class: "CONNECTED" },
            "SCAN_QR": { text: "امسح رمز QR", icon: "🟡", class: "SCAN_QR" },
            "LOGGING_IN": { text: "جاري تسجيل الدخول", icon: "🔵", class: "LOGGING_IN" },
            "STARTING": { text: "جاري بدء المتصفح", icon: "⏳", class: "STARTING" },
            "OFFLINE": { text: "متوقف (محفوظ)", icon: "⚪", class: "OFFLINE" },
            "DISCONNECTED": { text: "تم تسجيل الخروج", icon: "🔴", class: "DISCONNECTED" },
            "ERROR": { text: "خطأ", icon: "❌", class: "ERROR" }
        };

        const statusInfo = statusMap[session.status] || { text: session.status, icon: "❓", class: "OFFLINE" };
        const phone = session.phone_number ? `+${session.phone_number}` : "غير معروف";

        return `
            <div class="session-card" id="card-${session.session_id}">
                <div>
                    <div class="card-top">
                        <div class="session-meta">
                            <div class="session-avatar">📱</div>
                            <div>
                                <div class="session-name">${escapeHtml(session.name)}</div>
                                <div class="session-id">ID: ${escapeHtml(session.session_id)}</div>
                            </div>
                        </div>
                        <span class="status-badge ${statusInfo.class}">
                            <span class="status-dot"></span>
                            ${statusInfo.text}
                        </span>
                    </div>

                    <div class="card-details">
                        <div class="detail-row">
                            <span class="detail-label">رقم الهاتف:</span>
                            <span class="detail-val">${phone}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">الجلسة المحفوظة:</span>
                            <span class="detail-val" style="color: ${session.has_saved_session ? '#25d366' : '#8696a0'}">
                                ${session.has_saved_session ? 'نعم (دخول تلقائي)' : 'جديدة'}
                            </span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">المتصفح:</span>
                            <span class="detail-val">${session.is_running ? 'يعمل في الخلفية' : 'متوقف'}</span>
                        </div>
                    </div>
                </div>

                <div class="card-actions">
                    ${!session.is_running ? `
                        <button class="btn btn-primary btn-sm" onclick="startSession('${session.session_id}')">
                            ▶️ تشغيل الجلسة
                        </button>
                    ` : `
                        <button class="btn btn-secondary btn-sm" onclick="stopSession('${session.session_id}')">
                            ⏹️ إيقاف
                        </button>
                    `}

                    ${session.status === 'SCAN_QR' ? `
                        <button class="btn btn-primary btn-sm" style="background: #eab308; color: #000;" onclick="openQrModal('${session.session_id}')">
                            📷 مسح QR
                        </button>
                    ` : ''}

                    ${session.status === 'CONNECTED' ? `
                        <button class="btn btn-primary btn-sm" onclick="openSendModal('${session.session_id}')">
                            💬 إرسال رسالة
                        </button>
                    ` : ''}

                    ${session.is_running ? `
                        <button class="btn btn-secondary btn-sm" title="معاينة شاشة المتصفح الحية" onclick="openScreenshotModal('${session.session_id}')">
                            🖼️ شاشة حية
                        </button>
                    ` : ''}

                    <button class="btn btn-secondary btn-sm" title="أكواد الربط البرمجي API" onclick="openApiDocsModal('${session.session_id}')">
                        ⚡ API
                    </button>

                    <button class="btn btn-danger btn-sm" title="حذف الحساب" onclick="deleteSession('${session.session_id}')">
                        🗑️
                    </button>
                </div>
            </div>
        `;
    }).join("");
}

function populateAccountSelects(sessions) {
    const selects = [document.getElementById("send-session-select"), document.getElementById("bulk-session-select")];
    selects.forEach(sel => {
        if (!sel) return;
        const currentVal = sel.value;
        sel.innerHTML = '<option value="">-- اختر حساب الواتساب --</option>';
        sessions.filter(s => s.status === "CONNECTED").forEach(s => {
            const opt = document.createElement("option");
            opt.value = s.session_id;
            opt.innerText = `${s.name} (${s.session_id})`;
            if (s.session_id === currentVal) opt.selected = true;
            sel.appendChild(opt);
        });
    });
}

// Session Actions
async function startSession(sessionId) {
    try {
        showToast("جاري بدء تشغيل الجلسة...", "success");
        const res = await fetch(`/api/sessions/${sessionId}/start`, { method: "POST" });
        const json = await res.json();
        if (json.success) {
            showToast("تم بدء تشغيل الجلسة بنجاح!");
            fetchSessions();
            // If new session, automatically open QR modal
            setTimeout(() => {
                openQrModal(sessionId);
            }, 1500);
        } else {
            showToast(json.detail || "فشل تشغيل الجلسة", "error");
        }
    } catch (e) {
        showToast("خطأ في الاتصال بالخادم", "error");
    }
}

async function stopSession(sessionId) {
    try {
        const res = await fetch(`/api/sessions/${sessionId}/stop`, { method: "POST" });
        const json = await res.json();
        if (json.success) {
            showToast("تم إيقاف الجلسة وحفظ بيانات الدخول");
            fetchSessions();
        }
    } catch (e) {
        showToast("خطأ أثناء الإيقاف", "error");
    }
}

async function deleteSession(sessionId) {
    if (!confirm(`هل أنت متأكد من حذف الحساب '${sessionId}' نهائياً ومسح ملفات جلسته؟`)) return;
    try {
        const res = await fetch(`/api/sessions/${sessionId}`, { method: "DELETE" });
        const json = await res.json();
        if (json.success) {
            showToast("تم حذف الحساب بنجاح");
            fetchSessions();
        } else {
            showToast(json.detail || "فشل الحذف", "error");
        }
    } catch (e) {
        showToast("خطأ في الاتصال", "error");
    }
}

// Modal Controllers
function openModal(id) {
    document.getElementById(id).classList.add("active");
}

function closeModal(id) {
    document.getElementById(id).classList.remove("active");
    if (id === "modal-qr") {
        clearInterval(activeQrPollingInterval);
        currentQrSessionId = null;
    }
}

// Add Account
document.getElementById("add-account-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const sessionId = document.getElementById("new-session-id").value.trim();
    const name = document.getElementById("new-session-name").value.trim();
    const description = document.getElementById("new-session-desc").value.trim();
    const autoStart = document.getElementById("new-session-autostart").checked;

    try {
        const res = await fetch("/api/sessions", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: sessionId, name, description })
        });
        const json = await res.json();
        if (json.success) {
            showToast("تم إنشاء الحساب بنجاح!");
            closeModal("modal-add-account");
            document.getElementById("add-account-form").reset();
            fetchSessions();

            if (autoStart) {
                startSession(sessionId);
            }
        } else {
            showToast(json.detail || "فشل إنشاء الحساب", "error");
        }
    } catch (err) {
        showToast("حدث خطأ أثناء الإنشاء", "error");
    }
});

// QR Code Modal & Live Polling
async function openQrModal(sessionId) {
    currentQrSessionId = sessionId;
    document.getElementById("qr-session-title").innerText = `ربط الحساب: ${sessionId}`;
    document.getElementById("qr-box").innerHTML = `
        <div style="display:flex;flex-direction:column;align-items:center;gap:10px;padding:30px;">
            <div style="font-size:2rem;animation:spin 1s linear infinite;">⏳</div>
            <p style="color:#8696a0;">جاري تحميل رمز QR من واتساب ويب...</p>
        </div>
    `;
    openModal("modal-qr");

    // Fetch immediately then poll every 2 seconds
    checkQrStatus();
    clearInterval(activeQrPollingInterval);
    activeQrPollingInterval = setInterval(checkQrStatus, 2000);
}

async function checkQrStatus() {
    if (!currentQrSessionId) return;
    try {
        const res = await fetch(`/api/sessions/${currentQrSessionId}/qr?format=json`);
        const json = await res.json();

        if (json.data && json.data.status === "CONNECTED") {
            document.getElementById("qr-box").innerHTML = `
                <div style="text-align:center;padding:30px;">
                    <div style="font-size:3rem;margin-bottom:10px;">🎉</div>
                    <h3 style="color:#25d366;margin-bottom:6px;">تم الاتصال بنجاح!</h3>
                    <p style="color:#8696a0;font-size:0.9rem;">الحساب الآن مسجل ومتصل وجاهز لإرسال الرسائل.</p>
                </div>
            `;
            clearInterval(activeQrPollingInterval);
            fetchSessions();
            return;
        }

        if (json.data && json.data.qr_code) {
            document.getElementById("qr-box").innerHTML = `
                <img src="${json.data.qr_code}" alt="WhatsApp Web QR Code" />
            `;
        }
    } catch (e) {
        console.error("QR poll error:", e);
    }
}

// Screenshot Modal
async function openScreenshotModal(sessionId) {
    document.getElementById("screenshot-session-title").innerText = `معاينة شاشة المتصفح: ${sessionId}`;
    const img = document.getElementById("live-screenshot-img");
    img.src = "";
    img.alt = "جاري التقاط الشاشة...";
    openModal("modal-screenshot");

    // Append timestamp to prevent cache
    img.src = `/api/sessions/${sessionId}/screenshot?t=${Date.now()}`;
}

function refreshCurrentScreenshot() {
    const title = document.getElementById("screenshot-session-title").innerText;
    const sessionId = title.replace("معاينة شاشة المتصفح: ", "").trim();
    if (sessionId) {
        const img = document.getElementById("live-screenshot-img");
        img.src = `/api/sessions/${sessionId}/screenshot?t=${Date.now()}`;
    }
}

// Single Message Modal
function openSendModal(sessionId) {
    if (sessionId) {
        document.getElementById("send-session-select").value = sessionId;
    }
    openModal("modal-send");
}

document.getElementById("send-message-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const sessionId = document.getElementById("send-session-select").value;
    const phone = document.getElementById("send-phone").value.trim();
    const message = document.getElementById("send-message").value.trim();
    const btn = document.getElementById("btn-submit-send");

    if (!sessionId) {
        showToast("يرجى اختيار حساب الواتساب المرسل", "error");
        return;
    }

    btn.disabled = true;
    btn.innerText = "جاري الإرسال...";

    try {
        const res = await fetch(`/api/sessions/${sessionId}/send-message`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ phone, message })
        });
        const json = await res.json();
        if (json.success) {
            showToast("تم إرسال الرسالة بنجاح عبر واتساب! 🎉", "success");
            closeModal("modal-send");
            document.getElementById("send-message").value = "";
        } else {
            showToast(json.detail || "فشل إرسال الرسالة", "error");
        }
    } catch (err) {
        showToast("حدث خطأ أثناء إرسال الرسالة", "error");
    } finally {
        btn.disabled = false;
        btn.innerText = "إرسال الرسالة الآن";
    }
});

// Bulk Message Modal
function openBulkModal() {
    openModal("modal-bulk");
}

document.getElementById("bulk-message-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const sessionId = document.getElementById("bulk-session-select").value;
    const rawPhones = document.getElementById("bulk-phones").value.trim();
    const message = document.getElementById("bulk-message-text").value.trim();
    const delay = parseFloat(document.getElementById("bulk-delay").value) || 3.0;
    const btn = document.getElementById("btn-submit-bulk");

    if (!sessionId) {
        showToast("يرجى اختيار حساب الواتساب", "error");
        return;
    }

    const phones = rawPhones.split("\n").map(p => p.trim()).filter(p => p.length >= 7);
    if (phones.length === 0) {
        showToast("يرجى إدخال رقم هاتف واحد على الأقل", "error");
        return;
    }

    btn.disabled = true;
    btn.innerText = `جاري إرسال ${phones.length} رسالة... يرجى الانتظار`;

    try {
        const res = await fetch(`/api/sessions/${sessionId}/send-bulk`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ phones, message, delay_seconds: delay })
        });
        const json = await res.json();
        if (json.success) {
            showToast(json.message, "success");
            closeModal("modal-bulk");
            document.getElementById("bulk-phones").value = "";
            document.getElementById("bulk-message-text").value = "";
        } else {
            showToast(json.detail || "حدث خطأ في الإرسال الجماعي", "error");
        }
    } catch (err) {
        showToast("خطأ أثناء الاتصال بالخادم", "error");
    } finally {
        btn.disabled = false;
        btn.innerText = "بدء الحملة وإرسال الرسائل";
    }
});

// API Code Samples Modal
function openApiDocsModal(sessionId) {
    const origin = window.location.origin;
    const curlSample = `curl -X POST "${origin}/api/sessions/${sessionId}/send-message" \\
  -H "Content-Type: application/json" \\
  -d '{
    "phone": "966500000000",
    "message": "مرحباً، هذه رسالة تجريبية عبر الـ API!"
  }'`;

    const pythonSample = `import requests

url = "${origin}/api/sessions/${sessionId}/send-message"
payload = {
    "phone": "966500000000",
    "message": "مرحباً، هذه رسالة من كود بايثون!"
}
response = requests.post(url, json=payload)
print(response.json())`;

    document.getElementById("code-curl").innerText = curlSample;
    document.getElementById("code-python").innerText = pythonSample;
    openModal("modal-api");
}

function copyCode(elementId) {
    const text = document.getElementById(elementId).innerText;
    navigator.clipboard.writeText(text);
    showToast("تم نسخ الكود إلى الحافظة!");
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.innerText = text;
    return div.innerHTML;
}
