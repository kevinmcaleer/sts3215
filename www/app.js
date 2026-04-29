"use strict";

const POLL_MS = 250;

const els = {
  joints:    document.getElementById("joints"),
  log:       document.getElementById("status-log"),
  conn:      document.getElementById("connection"),
  torque:    document.getElementById("torque"),
  homeArm:   document.getElementById("home-arm"),
  gripOpen:  document.getElementById("grip-open"),
  gripClose: document.getElementById("grip-close"),
};

const sliders = {};        // joint name → input element
const valLabels = {};      // joint name → span showing current value
let jointConfig = null;    // populated from /api/status on first poll

// In-flight network state per joint. Slider input dispatches the optimistic
// UI event immediately; the network call goes through `sendJointSoon`,
// which keeps at most one request in flight per joint and queues the
// latest target value to send on completion. Last-write-wins, no debounce
// delay between drag and command.
const inFlight = {};
const pending  = {};

// Public hook: any other script (or even devtools) can call
// `BuddyState.applyAngles({elbow: 45})` to push an optimistic update into
// the 3D view + sliders without waiting on the next poll.
window.BuddyState = {
  positions: {},
  torque_enabled: null,
  applyAngles(angles, opts) {
    const optimistic = !!(opts && opts.optimistic);
    Object.assign(this.positions, angles);
    if (optimistic) {
      // Don't fight the slider the user is dragging.
      updateSliders(angles, { skipActive: true });
    } else {
      updateSliders(angles, { skipActive: true });
    }
    document.dispatchEvent(new CustomEvent("buddy:angles", {
      detail: { angles, optimistic },
    }));
  },
};

function setConn(state, label) {
  els.conn.className = "pill pill-" + state;
  els.conn.textContent = label;
}

function setTorqueButton(enabled) {
  if (enabled === true) {
    els.torque.className = "btn on";
    els.torque.textContent = "torque: on";
  } else if (enabled === false) {
    els.torque.className = "btn off";
    els.torque.textContent = "torque: off";
  } else {
    els.torque.className = "btn";
    els.torque.textContent = "torque: ?";
  }
  window.BuddyState.torque_enabled = enabled;
  document.dispatchEvent(new CustomEvent("buddy:torque", {
    detail: { enabled },
  }));
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
    const v = +input.value;
    val.textContent = v.toFixed(0) + "°";
    // Fire the optimistic event before the network call so the 3D viewer
    // can update on the same frame as the slider.
    window.BuddyState.positions[name] = v;
    document.dispatchEvent(new CustomEvent("buddy:angles", {
      detail: { angles: { [name]: v }, optimistic: true },
    }));
    sendJointSoon(name, v);
  });

  row.appendChild(label);
  row.appendChild(input);
  row.appendChild(val);

  sliders[name] = input;
  valLabels[name] = val;
  return row;
}

function sendJointSoon(name, degrees) {
  pending[name] = degrees;
  if (inFlight[name]) return;            // request in progress; will pick up
  inFlight[name] = drainJoint(name);
}

async function drainJoint(name) {
  while (pending[name] !== undefined) {
    const value = pending[name];
    delete pending[name];
    try {
      await api("/api/joint/" + encodeURIComponent(name), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ degrees: value }),
      });
    } catch (err) {
      log("joint " + name + " failed: " + err.message);
    }
  }
  delete inFlight[name];
}

function log(msg) {
  const ts = new Date().toLocaleTimeString();
  els.log.textContent =
    ("[" + ts + "] " + msg + "\n" + els.log.textContent).slice(0, 4000);
}

function buildJointGrid(positions) {
  els.joints.innerHTML = "";
  for (const name of Object.keys(positions)) {
    const value = +positions[name] || 0;
    els.joints.appendChild(buildJointRow(name, { min: 0, max: 360, value }));
  }
  jointConfig = Object.keys(positions);
}

function updateSliders(positions, opts) {
  const skipActive = !!(opts && opts.skipActive);
  for (const name of Object.keys(positions)) {
    const v = +positions[name];
    if (!Number.isFinite(v)) continue;
    const slider = sliders[name];
    if (!slider) continue;
    // Don't yank the slider the user is currently dragging.
    if (skipActive && document.activeElement === slider) continue;
    slider.value = v;
    valLabels[name].textContent = v.toFixed(0) + "°";
  }
}

async function poll() {
  try {
    const status = await api("/api/status");
    setConn("ok", "online");
    if (!jointConfig) {
      buildJointGrid(status.positions);
    }
    Object.assign(window.BuddyState.positions, status.positions);
    updateSliders(status.positions, { skipActive: true });
    setTorqueButton(status.torque_enabled);
    document.dispatchEvent(new CustomEvent("buddy:status", {
      detail: { status },
    }));
  } catch (err) {
    setConn("err", "offline");
  } finally {
    setTimeout(poll, POLL_MS);
  }
}

els.torque.addEventListener("click", async () => {
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

els.homeArm.addEventListener("click", async () => {
  els.homeArm.disabled = true;
  try {
    const result = await api("/api/home", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ duration_ms: 1500 }),
    });
    // Apply the target angles immediately so sliders + 3D view jump to
    // the home pose without waiting for the next status poll.
    if (result && result.angles) {
      window.BuddyState.applyAngles(result.angles, { optimistic: true });
    }
  } catch (err) {
    log("home failed: " + err.message);
  } finally {
    els.homeArm.disabled = false;
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
