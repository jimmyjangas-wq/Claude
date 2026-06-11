"use strict";

const $ = (id) => document.getElementById(id);
const TOKEN_KEY = "ruc_token";

let profile = null;

function token() {
  return localStorage.getItem(TOKEN_KEY) || "";
}

function authHeaders() {
  return { Authorization: "Bearer " + token(), "Content-Type": "application/json" };
}

function showStatus(msg, kind) {
  const el = $("status");
  el.textContent = msg;
  el.className = "status " + (kind || "");
  el.hidden = false;
}

function clearStatus() {
  $("status").hidden = true;
}

function updateEstimate() {
  if (!profile || !profile.estimate_per_unit_nzd) {
    $("estimate").textContent = "";
    return;
  }
  const units = parseInt($("units").value, 10);
  const est = units * profile.estimate_per_unit_nzd;
  $("estimate").textContent =
    `Estimated ≈ $${est.toFixed(2)} (NZTA charges the exact amount).`;
}

async function loadProfile() {
  const res = await fetch("/api/profile", { headers: authHeaders() });
  if (res.status === 401) {
    localStorage.removeItem(TOKEN_KEY);
    showSetup();
    throw new Error("unauthorized");
  }
  if (!res.ok) throw new Error("profile failed: " + res.status);
  profile = await res.json();
  $("plate").textContent = profile.plate;
  if (profile.default_units) $("units").value = String(profile.default_units);
  if (profile.default_rego_months) $("rego-months").value = String(profile.default_rego_months);
  updateEstimate();
  maybeShowPushButton();
}

const LEVEL_TEXT = {
  expired: "EXPIRED",
  urgent: "due very soon",
  warn: "due soon",
  ok: "ok",
  unknown: "unknown",
};

function statusLine(item) {
  let when = "";
  if (item.days_until === null) when = item.expiry ? `expires ${item.expiry}` : "not found";
  else if (item.days_until < 0) when = `expired ${-item.days_until} days ago`;
  else when = `${item.days_until} days (${item.expiry})`;
  return `<li class="lvl-${item.level}"><span>${item.label}</span><span>${when}</span></li>`;
}

async function loadStatus(refresh) {
  $("status-list").innerHTML = '<li class="muted">Checking NZTA…</li>';
  try {
    const res = await fetch("/api/status" + (refresh ? "?refresh=1" : ""), { headers: authHeaders() });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      $("status-list").innerHTML = `<li class="muted">${data.detail || "Status unavailable"}</li>`;
      return;
    }
    $("status-list").innerHTML = data.items.map(statusLine).join("");
  } catch (err) {
    $("status-list").innerHTML = `<li class="muted">Network error: ${err.message}</li>`;
  }
}

async function renewRego() {
  clearStatus();
  const months = parseInt($("rego-months").value, 10);
  if (!confirm(`Renew rego for ${profile.plate}, ${months} months?`)) return;
  $("renew-rego").disabled = true;
  showStatus("Renewing rego… this can take 20–40 seconds.", "busy");
  try {
    const res = await fetch("/api/renew-rego", {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ months }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) showStatus(data.detail || `Failed (${res.status}).`, "err");
    else {
      showStatus(data.message || "Done.", "ok");
      loadStatus(true);
    }
  } catch (err) {
    showStatus("Network error: " + err.message, "err");
  } finally {
    $("renew-rego").disabled = false;
  }
}

function showSetup() {
  $("setup").hidden = false;
  $("main").hidden = true;
}

function showMain() {
  $("setup").hidden = true;
  $("main").hidden = false;
}

async function buy() {
  clearStatus();
  const odo = parseInt($("odometer").value, 10);
  const units = parseInt($("units").value, 10);
  if (!Number.isFinite(odo) || odo <= 0) {
    showStatus("Enter a valid odometer reading first.", "err");
    return;
  }
  const est = profile && profile.estimate_per_unit_nzd
    ? ` (≈ $${(units * profile.estimate_per_unit_nzd).toFixed(2)})`
    : "";
  if (!confirm(`Buy ${units * 1000} km of RUC for ${profile.plate} at ${odo} km${est}?`)) {
    return;
  }

  $("buy").disabled = true;
  showStatus("Purchasing… this can take 20–40 seconds.", "busy");
  try {
    const res = await fetch("/api/purchase", {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ odometer: odo, units }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      showStatus(data.detail || `Failed (${res.status}).`, "err");
    } else {
      showStatus(data.message || "Done.", "ok");
      $("odometer").value = "";
    }
  } catch (err) {
    showStatus("Network error: " + err.message, "err");
  } finally {
    $("buy").disabled = false;
  }
}

function urlBase64ToUint8Array(base64) {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const raw = atob((base64 + padding).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

function pushSupported() {
  return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

async function enablePush() {
  if (!profile || !profile.vapid_public_key) return;
  if (!pushSupported()) {
    showStatus("This browser can't do push. On iPhone: Add to Home Screen first, then open that.", "err");
    return;
  }
  try {
    const perm = await Notification.requestPermission();
    if (perm !== "granted") {
      showStatus("Notifications not allowed.", "err");
      return;
    }
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(profile.vapid_public_key),
    });
    const res = await fetch("/api/subscribe", {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify(sub),
    });
    if (res.ok) {
      showStatus("Reminders enabled on this iPhone.", "ok");
      $("enable-push").hidden = true;
    } else {
      showStatus("Could not register for push.", "err");
    }
  } catch (err) {
    showStatus("Push setup failed: " + err.message, "err");
  }
}

function maybeShowPushButton() {
  const show = profile && profile.vapid_public_key && pushSupported();
  $("enable-push").hidden = !show;
}

function init() {
  $("save-token").addEventListener("click", async () => {
    const t = $("token").value.trim();
    if (!t) return;
    localStorage.setItem(TOKEN_KEY, t);
    $("token").value = "";
    try {
      await loadProfile();
      showMain();
      clearStatus();
      loadStatus(false);
    } catch {
      showStatus("That token didn't work.", "err");
    }
  });

  $("change-token").addEventListener("click", () => {
    localStorage.removeItem(TOKEN_KEY);
    showSetup();
  });

  $("units").addEventListener("change", updateEstimate);
  $("buy").addEventListener("click", buy);
  $("renew-rego").addEventListener("click", renewRego);
  $("refresh").addEventListener("click", () => loadStatus(true));
  $("enable-push").addEventListener("click", enablePush);

  if (!token()) {
    showSetup();
  } else {
    loadProfile().then(() => { showMain(); loadStatus(false); }).catch(() => showSetup());
  }
}

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}

init();
