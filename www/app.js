"use strict";

const POLL_MS = 250;
const DEBOUNCE_MS = 120;

const els = {
  joints:    document.getElementById("joints"),
  log:       document.getElementById("status-log"),
  conn:      document.getElementById("connection"),
  torque:    document.getElementById("torque"),
  gripOpen:  document.getElementById("grip-open"),
  gripClose: document.getElementById("grip-close"),
};

const sliders = {};        // joint name → input element
const valLabels = {};      // joint name → span showing current value
const debounceTimers = {}; // joint name → setTimeout handle
let jointConfig = null;    // populated from /api/status on first poll

function setConn(state, label) {
  els.conn.className = "pill pill-" + state;
  els.conn.textContent = label;
}

function setTorqueButton(enabled) {
  if (enabled === true)  { els.torque.className = "btn on";  els.torque.textContent = "torque: on"; }
  else if (enabled === false) { els.torque.className = "btn off"; els.torque.textContent = "torque: off"; }
  else                   { els.torque.className = "btn";     els.torque.textContent = "torque: ?"; }
}

async function api(path, opts) {
  const r = await fetch(path, opts);
  const text = await r.text();
  let body = null;
  try { body = text ? JSON.parse(text) : null; } catch (_) {}
  if (!r.ok) {
    const msg = (body && body.error) || ("HTTP " + r.status);
    throw new Error(msg);
  }
  return body;
}

function buildJointRow(name, defaults) {
  const row = document.createElement("div");
  row.className = "joint";

  const label = document.createElement("label");
  label.textContent = name;

  const input = document.createElement("input");
  input.type = "range";
  input.min = defaults.min;
  input.max = defaults.max;
  input.step = 1;
  input.value = defaults.value;

  const val = document.createElement("span");
  val.className = "val";
  val.textContent = defaults.value.toFixed(0) + "°";

  input.addEventListener("input", () => {
    val.textContent = (+input.value).toFixed(0) + "°";
    debounceJoint(name, +input.value);
  });

  row.appendChild(label);
  row.appendChild(input);
  row.appendChild(val);

  sliders[name] = input;
  valLabels[name] = val;
  return row;
}

function debounceJoint(name, degrees) {
  clearTimeout(debounceTimers[name]);
  debounceTimers[name] = setTimeout(() => {
    api("/api/joint/" + encodeURIComponent(name), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ degrees }),
    }).catch(err => log("joint " + name + " failed: " + err.message));
  }, DEBOUNCE_MS);
}

function log(msg) {
  const ts = new Date().toLocaleTimeString();
  els.log.textContent = ("[" + ts + "] " + msg + "\n" + els.log.textContent).slice(0, 4000);
}

async function buildJointGrid(positions) {
  // First time: fabricate sliders. We don't know per-joint min/max from
  // /api/status alone — assume 0..360 to match Buddy's default config.
  els.joints.innerHTML = "";
  for (const name of Object.keys(positions)) {
    const value = +positions[name] || 0;
    els.joints.appendChild(buildJointRow(name, { min: 0, max: 360, value }));
  }
  jointConfig = Object.keys(positions);
}

function updateSliders(positions) {
  for (const name of Object.keys(positions)) {
    const v = +positions[name];
    if (!Number.isFinite(v)) continue;
    const slider = sliders[name];
    if (!slider) continue;
    // Don't yank the slider while the user is dragging.
    if (document.activeElement === slider) continue;
    slider.value = v;
    valLabels[name].textContent = v.toFixed(0) + "°";
  }
}

async function poll() {
  try {
    const status = await api("/api/status");
    setConn("ok", "online");
    if (!jointConfig) {
      await buildJointGrid(status.positions);
    } else {
      updateSliders(status.positions);
    }
    setTorqueButton(status.torque_enabled);
  } catch (err) {
    setConn("err", "offline");
  } finally {
    setTimeout(poll, POLL_MS);
  }
}

els.torque.addEventListener("click", async () => {
  // Toggle based on current label state.
  const next = !els.torque.classList.contains("on");
  try {
    await api("/api/torque", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enable: next }),
    });
    setTorqueButton(next);
  } catch (err) {
    log("torque toggle failed: " + err.message);
  }
});

els.gripOpen.addEventListener("click", () => {
  api("/api/gripper", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ state: "open" }),
  }).catch(err => log("gripper open failed: " + err.message));
});

els.gripClose.addEventListener("click", () => {
  api("/api/gripper", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ state: "close" }),
  }).catch(err => log("gripper close failed: " + err.message));
});

setConn("warn", "connecting…");
poll();
