const statusBadge = document.getElementById("statusBadge");
const registerForm = document.getElementById("registerForm");
const registeredView = document.getElementById("registeredView");
const deviceInfo = document.getElementById("deviceInfo");
const errorBox = document.getElementById("errorBox");

function renderState(data) {
  if (!data || !data.deviceToken) {
    statusBadge.className = "badge badge-inactive";
    statusBadge.innerText = "Status: Not Registered";
    registerForm.classList.remove("hidden");
    registeredView.classList.add("hidden");
    return;
  }

  statusBadge.className = "badge badge-active";
  statusBadge.innerText = "✓ Connected & Monitoring Active";
  registerForm.classList.add("hidden");
  registeredView.classList.remove("hidden");
  errorBox.classList.add("hidden");

  const rulesVer = data.rulesetVersion || 1;
  const modelVer = data.modelVersion || 1;
  const queueLen = (data.eventQueue || []).length;
  const syncTime = data.lastSyncAt ? new Date(data.lastSyncAt).toLocaleTimeString() : "Just now";

  deviceInfo.innerHTML = `
    <div><strong>User ID:</strong> ${data.userId || "EMP001"}</div>
    <div><strong>Device ID:</strong> ${(data.deviceId || "").slice(0, 13)}...</div>
    <div><strong>Ruleset Version:</strong> v${rulesVer} | <strong>Model Version:</strong> v${modelVer}</div>
    <div><strong>Offline Queue:</strong> ${queueLen} pending event(s)</div>
    <div><strong>Last Sync:</strong> ${syncTime}</div>
  `;
}

function refreshPopup() {
  chrome.storage.local.get(
    ["deviceToken", "deviceId", "userId", "rulesetVersion", "modelVersion", "eventQueue", "lastSyncAt"],
    (data) => renderState(data)
  );
}

document.addEventListener("DOMContentLoaded", refreshPopup);

document.getElementById("registerBtn").addEventListener("click", async () => {
  const userId = document.getElementById("userId").value.trim();
  const enrollmentCode = document.getElementById("enrollmentCode").value.trim();
  errorBox.classList.add("hidden");

  try {
    const response = await fetch("http://localhost:8000/api/v1/devices/register/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId, enrollment_code: enrollmentCode })
    });
    const data = await response.json();

    if (response.ok) {
      chrome.storage.local.set({
        deviceToken: data.device_token,
        deviceId: data.device_id,
        userId: userId,
        rulesetVersion: 1,
        modelVersion: 1,
        lastSyncAt: new Date().toISOString()
      }, refreshPopup);
    } else {
      errorBox.classList.remove("hidden");
      errorBox.innerText = "Error: " + JSON.stringify(data);
    }
  } catch (err) {
    errorBox.classList.remove("hidden");
    errorBox.innerText = "Connection failed. Ensure Django is running on port 8000.";
  }
});

document.getElementById("syncBtn").addEventListener("click", () => {
  chrome.runtime.sendMessage({ type: "SYNC_NOW" }, () => refreshPopup());
});

document.getElementById("resetBtn").addEventListener("click", () => {
  chrome.storage.local.clear(refreshPopup);
});