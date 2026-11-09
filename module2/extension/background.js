const API_BASE = "http://localhost:8000/api/v1";

function setupAlarms() {
  chrome.alarms.create("flush_event_queue", { periodInMinutes: 1 });
  chrome.alarms.create("sync_rules_and_model", { periodInMinutes: 5 });
}

chrome.runtime.onInstalled.addListener(() => {
  setupAlarms();
  chrome.storage.local.get(["rulesetVersion", "modelVersion", "eventQueue"], (data) => {
    if (!data.rulesetVersion) chrome.storage.local.set({ rulesetVersion: 1 });
    if (!data.modelVersion) chrome.storage.local.set({ modelVersion: 1 });
    if (!data.eventQueue) chrome.storage.local.set({ eventQueue: [] });
  });
});

chrome.runtime.onStartup.addListener(() => {
  setupAlarms();
  flushEventQueue();
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "flush_event_queue") flushEventQueue();
  if (alarm.name === "sync_rules_and_model") syncConfigFromServer();
});

async function enqueueAndFlush(eventPayload) {
  try {
    const store = await chrome.storage.local.get(["eventQueue"]);
    const queue = store.eventQueue || [];
    if (!queue.some((e) => e.event_id === eventPayload.event_id)) {
      queue.push(eventPayload);
      await chrome.storage.local.set({ eventQueue: queue });
    }
    return await flushEventQueue();
  } catch (err) {
    return { ok: false, error: err.message };
  }
}

async function flushEventQueue() {
  try {
    const store = await chrome.storage.local.get(["eventQueue", "deviceToken"]);
    const queue = store.eventQueue || [];
    const token = store.deviceToken;

    if (!token || queue.length === 0) {
      return { ok: false, queued: queue.length };
    }

    const remaining = [];
    let delivered = 0;

    for (const item of queue) {
      try {
        const res = await fetch(`${API_BASE}/events/`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token}`
          },
          body: JSON.stringify(item)
        });
        if (res.ok || res.status === 400) {
          delivered++;
        } else {
          remaining.push(item);
        }
      } catch (_) {
        remaining.push(item);
      }
    }

    await chrome.storage.local.set({
      eventQueue: remaining,
      lastSyncAt: new Date().toISOString()
    });
    return { ok: remaining.length === 0, delivered, queued: remaining.length };
  } catch (err) {
    return { ok: false, error: err.message };
  }
}

async function syncConfigFromServer() {
  try {
    const store = await chrome.storage.local.get(["deviceToken", "rulesetVersion", "modelVersion"]);
    if (!store.deviceToken) return { ok: false };

    const headers = { "Authorization": `Bearer ${store.deviceToken}` };
    let curRules = store.rulesetVersion || 1;
    let curModel = store.modelVersion || 1;

    try {
      const rRes = await fetch(`${API_BASE}/config/rules?current=${curRules}`, { headers });
      if (rRes.ok) {
        const rData = await rRes.json();
        if (rData.status === "updated" && rData.version) {
          curRules = rData.version;
          await chrome.storage.local.set({ rulesetVersion: rData.version, customRulesConfig: rData.content });
        }
      }
    } catch (_) {}

    try {
      const mRes = await fetch(`${API_BASE}/config/model?current=${curModel}`, { headers });
      if (mRes.ok) {
        const mData = await mRes.json();
        if (mData.status === "updated" && mData.version) {
          curModel = mData.version;
          await chrome.storage.local.set({ modelVersion: mData.version, customModelWeights: mData.weights_json });
        }
      }
    } catch (_) {}

    const now = new Date().toISOString();
    await chrome.storage.local.set({ lastSyncAt: now });
    return { ok: true, rulesetVersion: curRules, modelVersion: curModel, lastSyncAt: now };
  } catch (err) {
    return { ok: false, error: err.message };
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "LOG_DLP_EVENT") {
    enqueueAndFlush(message.payload).then(sendResponse);
    return true;
  }
  if (message.type === "SYNC_NOW") {
    Promise.all([flushEventQueue(), syncConfigFromServer()]).then(([qRes, sRes]) => {
      sendResponse({ queue: qRes, sync: sRes });
    });
    return true;
  }
});