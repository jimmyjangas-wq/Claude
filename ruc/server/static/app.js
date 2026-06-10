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
  updateEstimate();
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

  if (!token()) {
    showSetup();
  } else {
    loadProfile().then(showMain).catch(() => showSetup());
  }
}

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}

init();
