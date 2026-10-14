// WhatsApp Web Multi-Account Dashboard Controller

let activeQrPollingInterval = null;
let currentQrSessionId = null;
let autoRefreshTimer = null;

// Initialize when DOM ready
document.addEventListener("DOMContentLoaded", () => {
    fetchSessions();
    fetchStats();
    fetchDbStatus();
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

        let statusInfo = statusMap[session.status] || { text: session.status, icon: "❓", class: "OFFLINE" };
        if (session.status === "OFFLINE" && session.has_saved_session) {
            statusInfo = { text: "جاهز للـ API (0% RAM) ⚡", icon: "💤", class: "CONNECTED" };
        }
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
                                ${session.has_saved_session ? 'نعم (ربط دائم)' : 'جديدة'}
                            </span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">المتصفح:</span>
                            <span class="detail-val">${session.is_running ? 'يعمل حالياً' : 'نائم (توفير 100% RAM)'}</span>
                        </div>
                    </div>
                </div>

                <div class="card-actions">
                    ${!session.is_running ? `
                        <button class="btn btn-secondary btn-sm" onclick="startSession('${session.session_id}')">
                            ▶️ تشغيل
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

                    ${session.status === 'CONNECTED' || session.has_saved_session ? `
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
        sessions.filter(s => s.status === "CONNECTED" || s.has_saved_session).forEach(s => {
            const opt = document.createElement("option");
            opt.value = s.session_id;
            opt.innerText = `${s.name} (${s.session_id}) - ${s.is_running ? 'نشط' : 'جاهز للـ API'}`;
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

// MongoDB Database Controllers
let currentDbData = null;

async function fetchDbStatus() {
    try {
        const res = await fetch("/api/database/status");
        const json = await res.json();
        if (json.success) {
            currentDbData = json.data;
            updateDbNavbarBadge(json.data.is_connected);
        }
    } catch (e) {
        console.error("DB status fetch error:", e);
    }
}

function updateDbNavbarBadge(isConnected) {
    const dot = document.getElementById("db-status-dot");
    const btn = document.getElementById("btn-db-status");
    if (!dot || !btn) return;

    if (isConnected) {
        dot.innerText = "🟢";
        btn.title = "MongoDB متصل بنجاح";
    } else {
        dot.innerText = "🔴";
        btn.title = "MongoDB غير متصل (اضغط لتعديل الرابط)";
    }
}

async function openDbModal() {
    openModal("modal-db");
    const banner = document.getElementById("db-status-banner");
    const input = document.getElementById("mongo-uri-input");

    if (currentDbData) {
        input.value = currentDbData.raw_uri || "";
        renderDbBanner(currentDbData);
    } else {
        banner.style.background = "rgba(134, 150, 160, 0.15)";
        banner.style.border = "1px solid rgba(134, 150, 160, 0.3)";
        banner.style.color = "#8696a0";
        banner.innerHTML = "<span>⏳</span><span>جاري التحقق من حالة الاتصال...</span>";
    }

    await fetchDbStatus();
    if (currentDbData) {
        input.value = currentDbData.raw_uri || "";
        renderDbBanner(currentDbData);
    }
}

function renderDbBanner(data) {
    const banner = document.getElementById("db-status-banner");
    if (!banner || !data) return;

    if (data.is_connected) {
        banner.style.background = "rgba(37, 211, 102, 0.15)";
        banner.style.border = "1px solid rgba(37, 211, 102, 0.3)";
        banner.style.color = "#25d366";
        banner.innerHTML = "<span>🟢</span><span><strong>متصل بنجاح:</strong> قاعدة البيانات جاهزة وتعمل على حفظ البيانات وسجلات الرسائل.</span>";
    } else {
        banner.style.background = "rgba(239, 68, 68, 0.15)";
        banner.style.border = "1px solid rgba(239, 68, 68, 0.3)";
        banner.style.color = "#ef4444";
        const err = data.last_error ? `(${data.last_error})` : "";
        banner.innerHTML = `<span>⚠️</span><span><strong>غير متصل:</strong> يرجى التأكد من كلمة المرور في Database Access ${err}</span>`;
    }
}

document.getElementById("db-settings-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const uri = document.getElementById("mongo-uri-input").value.trim();
    const btn = document.getElementById("btn-save-db");

    btn.disabled = true;
    btn.innerText = "جاري اختبار الاتصال...";

    try {
        const res = await fetch("/api/database/update", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ mongo_uri: uri })
        });
        const json = await res.json();
        if (json.success) {
            showToast("تم الاتصال بقاعدة البيانات وحفظ الإعدادات بنجاح! 🎉", "success");
            closeModal("modal-db");
            fetchDbStatus();
        } else {
            showToast(json.detail || "فشل الاتصال بقاعدة البيانات", "error");
            openDbModal();
        }
    } catch (err) {
        showToast("خطأ أثناء الاتصال بالخادم", "error");
    } finally {
        btn.disabled = false;
        btn.innerText = "💾 اختبار وتحديث الرابط";
    }
});

// Message Logs Modal
async function openLogsModal() {
    openModal("modal-logs");
    fetchMessageLogs();
}

async function fetchMessageLogs() {
    const container = document.getElementById("logs-table-container");
    container.innerHTML = `<div style="text-align:center;padding:30px;color:#8696a0;">جاري تحميل سجل الرسائل...</div>`;

    try {
        const res = await fetch("/api/database/logs");
        const json = await res.json();
        if (json.success && json.data.length > 0) {
            container.innerHTML = `
                <table style="width:100%;border-collapse:collapse;font-size:0.85rem;text-align:right;">
                    <thead>
                        <tr style="border-bottom:1px solid var(--border-color);color:var(--text-muted);">
                            <th style="padding:10px;">الحساب</th>
                            <th style="padding:10px;">المستلم</th>
                            <th style="padding:10px;">الرسالة</th>
                            <th style="padding:10px;">الحالة</th>
                            <th style="padding:10px;">الوقت</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${json.data.map(log => `
                            <tr style="border-bottom:1px solid var(--border-color);">
                                <td style="padding:10px;font-family:monospace;">${escapeHtml(log.session_id || '')}</td>
                                <td style="padding:10px;direction:ltr;text-align:right;">${escapeHtml(log.phone || '')}</td>
                                <td style="padding:10px;max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(log.message || '')}</td>
                                <td style="padding:10px;">
                                    <span style="color:${log.status === 'SENT' ? '#25d366' : '#ef4444'};font-weight:700;">
                                        ${log.status === 'SENT' ? '✓ تم الإرسال' : '✗ فشل'}
                                    </span>
                                </td>
                                <td style="padding:10px;color:var(--text-muted);font-size:0.75rem;">${new Date(log.created_at).toLocaleString('ar-EG')}</td>
                            </tr>
                        `).join("")}
                    </tbody>
                </table>
            `;
        } else {
            container.innerHTML = `<div style="text-align:center;padding:40px;color:#8696a0;">لا توجد رسائل مسجلة في السجل حتى الآن.</div>`;
        }
    } catch (e) {
        container.innerHTML = `<div style="text-align:center;padding:30px;color:#ef4444;">تعذر جلب السجل (تأكد من اتصال MongoDB).</div>`;
    }
}

// Smart OTP Gateway Controllers
function openOtpModal() {
    openModal("modal-otp");
    // Generate cURL example
    const origin = window.location.origin;
    const curl = `curl -X POST "${origin}/api/otp/send" \\
  -H "Content-Type: application/json" \\
  -d '{
    "phone": "966500000000",
    "otp": "849201"
  }'`;
    document.getElementById("code-otp-curl").innerText = curl;
    fetchOtpReports();
}

document.getElementById("otp-send-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const phone = document.getElementById("otp-phone").value.trim();
    const otp = document.getElementById("otp-code").value.trim();
    const message = document.getElementById("otp-custom-msg").value.trim();
    const btn = document.getElementById("btn-submit-otp");
    const resultBox = document.getElementById("otp-live-result");

    btn.disabled = true;
    btn.innerText = "⏳ جاري الإرسال وتجربة الحسابات بالتتابع...";
    resultBox.style.display = "block";
    resultBox.innerHTML = `
        <div style="display:flex;align-items:center;gap:10px;color:#34b7f1;">
            <span style="font-size:1.4rem;animation:spin 1s linear infinite;">🔄</span>
            <span>جاري فحص الحسابات وإرسال رمز التحقق...</span>
        </div>
    `;

    try {
        const res = await fetch("/api/otp/send", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ phone, otp, message: message || null })
        });
        const json = await res.json();

        if (json.success) {
            const data = json.data;
            showToast("تم تسليم رمز الـ OTP بنجاح! 🎉", "success");
            resultBox.innerHTML = `
                <div style="color:#25d366;font-weight:700;font-size:1rem;margin-bottom:8px;">
                    ✅ ${escapeHtml(json.message)}
                </div>
                <div style="font-size:0.85rem;color:var(--text-muted);margin-bottom:10px;">
                    الحساب الذي تم الإرسال منه: <strong style="color:#fff;">${escapeHtml(data.sent_by_account)}</strong> | إجمالي المحاولات: <strong style="color:#fff;">${data.attempts_count}</strong>
                </div>
                <div style="border-top:1px solid var(--border-color);padding-top:8px;">
                    <strong style="font-size:0.8rem;color:#8696a0;">سجل المحاولات:</strong>
                    <div style="margin-top:5px;font-size:0.82rem;display:flex;flex-direction:column;gap:4px;">
                        ${data.attempts.map((att, idx) => `
                            <div style="display:flex;justify-content:space-between;background:var(--bg-primary);padding:6px 10px;border-radius:4px;">
                                <span>محاولة #${idx + 1} (${escapeHtml(att.account_id)}):</span>
                                <span style="color:${att.status === 'SUCCESS' ? '#25d366' : '#ef4444'};">
                                    ${att.status === 'SUCCESS' ? '✓ تم الإرسال بنجاح' : '✗ فشل: ' + escapeHtml(att.error || '')}
                                </span>
                            </div>
                        `).join("")}
                    </div>
                </div>
            `;
            fetchOtpReports();
        } else {
            const data = json.data || { attempts: [] };
            showToast("فشلت جميع المحاولات", "error");
            resultBox.innerHTML = `
                <div style="color:#ef4444;font-weight:700;font-size:1rem;margin-bottom:8px;">
                    ❌ ${escapeHtml(json.message)}
                </div>
                <div style="margin-top:8px;font-size:0.82rem;display:flex;flex-direction:column;gap:4px;">
                    ${(data.attempts || []).map((att, idx) => `
                        <div style="display:flex;justify-content:space-between;background:rgba(239,68,68,0.1);padding:6px 10px;border-radius:4px;">
                            <span>حساب (${escapeHtml(att.account_id)}):</span>
                            <span style="color:#ef4444;">${escapeHtml(att.error || 'فشل الاتصال')}</span>
                        </div>
                    `).join("")}
                </div>
            `;
        }
    } catch (err) {
        showToast("خطأ أثناء الاتصال بالسيرفر", "error");
        resultBox.innerHTML = `<div style="color:#ef4444;">تعذر الاتصال بالسيرفر.</div>`;
    } finally {
        btn.disabled = false;
        btn.innerText = "⚡ إرسال رمز الـ OTP الآن";
    }
});

async function fetchOtpReports() {
    const container = document.getElementById("otp-reports-table-container");
    if (!container) return;
    container.innerHTML = `<div style="text-align:center;padding:15px;color:#8696a0;font-size:0.85rem;">جاري تحميل التقارير...</div>`;

    try {
        const res = await fetch("/api/otp/reports");
        const json = await res.json();
        if (json.success && json.data.length > 0) {
            container.innerHTML = `
                <table style="width:100%;border-collapse:collapse;font-size:0.82rem;text-align:right;">
                    <thead>
                        <tr style="border-bottom:1px solid var(--border-color);color:var(--text-muted);">
                            <th style="padding:8px;">المستلم</th>
                            <th style="padding:8px;">الرمز</th>
                            <th style="padding:8px;">الحساب الناجح</th>
                            <th style="padding:8px;">المحاولات</th>
                            <th style="padding:8px;">الحالة</th>
                            <th style="padding:8px;">الوقت</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${json.data.map(rep => `
                            <tr style="border-bottom:1px solid var(--border-color);">
                                <td style="padding:8px;direction:ltr;text-align:right;">${escapeHtml(rep.phone || '')}</td>
                                <td style="padding:8px;font-weight:700;color:#ffd700;">${escapeHtml(rep.otp_code || '-')}</td>
                                <td style="padding:8px;font-family:monospace;color:#34b7f1;">${escapeHtml(rep.sent_by_account || 'لا يوجد')}</td>
                                <td style="padding:8px;">${rep.total_attempts || 1}</td>
                                <td style="padding:8px;">
                                    <span style="color:${rep.success ? '#25d366' : '#ef4444'};font-weight:700;">
                                        ${rep.success ? '✓ ناجح' : '✗ فشل'}
                                    </span>
                                </td>
                                <td style="padding:8px;color:var(--text-muted);font-size:0.75rem;">${new Date(rep.created_at).toLocaleTimeString('ar-EG')}</td>
                            </tr>
                        `).join("")}
                    </tbody>
                </table>
            `;
        } else {
            container.innerHTML = `<div style="text-align:center;padding:20px;color:#8696a0;font-size:0.85rem;">لا توجد تقارير OTP سابقة بعد.</div>`;
        }
    } catch (e) {
        container.innerHTML = `<div style="text-align:center;padding:15px;color:#ef4444;font-size:0.85rem;">تعذر جلب التقارير.</div>`;
    }
}
