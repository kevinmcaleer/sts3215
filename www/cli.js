"use strict";

// Self-contained command-line panel for the Buddy web UI.
//
// Grammar:
//   move <joint> <degrees> [speed]   → POST /api/joint/<joint>
//   pose <x> <y> <z> [roll pitch yaw] → POST /api/pose
//   torque on|off                    → POST /api/torque
//   gripper open|close|<percent>     → POST /api/gripper (percent unsupported)
//   status                           → GET  /api/status   (pretty-printed)
//   home                             → POST /api/home (parks every joint at 0°)
//
// History: in-memory only (no localStorage). Tab completes joint names from
// the list cached by the most recent /api/status response.

(function () {
  const els = {
    input: document.getElementById("cli-input"),
    log:   document.getElementById("cli-log"),
  };

  if (!els.input || !els.log) return;  // panel not on page

  // Joint names cached from /api/status. Refreshed lazily on tab/status calls.
  let knownJoints = [];

  // Command history. Newest at the end; `historyIdx` walks backwards from
  // the end as the user presses Up.
  const history = [];
  let historyIdx = -1;     // -1 = "after the newest entry" (i.e. blank)
  let pendingDraft = "";   // preserve in-progress text when scrolling history

  function logLine(msg) {
    const ts = new Date().toLocaleTimeString();
    els.log.textContent = ("[" + ts + "] " + msg + "\n" + els.log.textContent)
      .slice(0, 8000);
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

  function jsonPost(path, payload) {
    return api(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  }

  function parseNumber(token, label) {
    const v = Number(token);
    if (!Number.isFinite(v)) {
      throw new Error("invalid number for " + label + ": " + token);
    }
    return v;
  }

  // --- command handlers --------------------------------------------------

  async function cmdMove(args) {
    if (args.length < 2) throw new Error("usage: move <joint> <degrees> [speed]");
    const joint = args[0];
    const degrees = parseNumber(args[1], "degrees");
    const payload = { degrees };
    if (args.length >= 3) payload.speed = parseNumber(args[2], "speed");
    const res = await jsonPost("/api/joint/" + encodeURIComponent(joint), payload);
    logLine("ok: " + JSON.stringify(res));
  }

  async function cmdPose(args) {
    if (args.length !== 3 && args.length !== 6) {
      throw new Error("usage: pose <x> <y> <z> [roll pitch yaw]");
    }
    const payload = {
      x: parseNumber(args[0], "x"),
      y: parseNumber(args[1], "y"),
      z: parseNumber(args[2], "z"),
    };
    if (args.length === 6) {
      payload.roll  = parseNumber(args[3], "roll");
      payload.pitch = parseNumber(args[4], "pitch");
      payload.yaw   = parseNumber(args[5], "yaw");
    }
    const res = await jsonPost("/api/pose", payload);
    logLine("ok: " + JSON.stringify(res));
  }

  async function cmdTorque(args) {
    if (args.length !== 1 || (args[0] !== "on" && args[0] !== "off")) {
      throw new Error("usage: torque on|off");
    }
    const res = await jsonPost("/api/torque", { enable: args[0] === "on" });
    logLine("ok: " + JSON.stringify(res));
  }

  async function cmdGripper(args) {
    if (args.length !== 1) throw new Error("usage: gripper open|close|<percent>");
    const arg = args[0];
    if (arg === "open" || arg === "close") {
      const res = await jsonPost("/api/gripper", { state: arg });
      logLine("ok: " + JSON.stringify(res));
      return;
    }
    // Numeric => percent (not yet wired through to the server).
    const pct = Number(arg);
    if (Number.isFinite(pct)) {
      logLine("percent gripper control not yet supported");
      return;
    }
    throw new Error("usage: gripper open|close|<percent>");
  }

  async function cmdStatus() {
    const res = await api("/api/status");
    if (res && res.positions) knownJoints = Object.keys(res.positions);
    logLine(JSON.stringify(res, null, 2));
  }

  async function cmdHome() {
    // /api/home introspects the live joint config on the server, so this
    // works for custom joint sets too.
    const res = await jsonPost("/api/home", { duration_ms: 1500 });
    if (res && res.angles && window.BuddyState) {
      window.BuddyState.applyAngles(res.angles, { optimistic: true });
    }
    logLine("ok: " + JSON.stringify(res));
  }

  const COMMANDS = {
    move:    cmdMove,
    pose:    cmdPose,
    torque:  cmdTorque,
    gripper: cmdGripper,
    status:  cmdStatus,
    home:    cmdHome,
  };

  async function runLine(line) {
    const trimmed = line.trim();
    if (!trimmed) return;
    logLine("> " + trimmed);
    const tokens = trimmed.split(/\s+/);
    const name = tokens[0].toLowerCase();
    const args = tokens.slice(1);
    const handler = COMMANDS[name];
    if (!handler) {
      logLine("unknown command: " + name +
              " (try: move, pose, torque, gripper, status, home)");
      return;
    }
    try {
      await handler(args);
    } catch (err) {
      logLine("error: " + err.message);
    }
  }

  // --- history & tab completion -----------------------------------------

  function recallHistory(direction) {
    if (history.length === 0) return;
    if (direction < 0) {  // Up: walk to older entries
      if (historyIdx === -1) {
        pendingDraft = els.input.value;
        historyIdx = history.length - 1;
      } else if (historyIdx > 0) {
        historyIdx -= 1;
      }
      els.input.value = history[historyIdx];
    } else {              // Down: walk forward toward the draft
      if (historyIdx === -1) return;
      if (historyIdx < history.length - 1) {
        historyIdx += 1;
        els.input.value = history[historyIdx];
      } else {
        historyIdx = -1;
        els.input.value = pendingDraft;
        pendingDraft = "";
      }
    }
    // Cursor to end after recall.
    const len = els.input.value.length;
    els.input.setSelectionRange(len, len);
  }

  // Refresh the joint cache opportunistically. Called on tab; also after
  // explicit `status`. Failures are silent — completion just won't help.
  async function refreshJoints() {
    try {
      const res = await api("/api/status");
      if (res && res.positions) knownJoints = Object.keys(res.positions);
    } catch (_) { /* ignore */ }
  }

  function completeJoint() {
    const value = els.input.value;
    const tokens = value.split(/\s+/);
    // Only complete the joint argument of `move <joint> ...`.
    if (tokens.length !== 2 || tokens[0].toLowerCase() !== "move") return;
    const partial = tokens[1];
    const matches = knownJoints.filter(n => n.startsWith(partial));
    if (matches.length === 1) {
      els.input.value = tokens[0] + " " + matches[0] + " ";
    } else if (matches.length > 1) {
      logLine("matches: " + matches.join(" "));
    }
  }

  // --- input wiring ------------------------------------------------------

  els.input.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") {
      ev.preventDefault();
      const line = els.input.value;
      els.input.value = "";
      if (line.trim()) {
        history.push(line);
        // Cap history to keep memory bounded.
        if (history.length > 200) history.shift();
      }
      historyIdx = -1;
      pendingDraft = "";
      runLine(line);
    } else if (ev.key === "ArrowUp") {
      ev.preventDefault();
      recallHistory(-1);
    } else if (ev.key === "ArrowDown") {
      ev.preventDefault();
      recallHistory(1);
    } else if (ev.key === "Tab") {
      ev.preventDefault();
      // Refresh joints in the background then attempt completion. If the
      // cache is empty wait for the refresh; otherwise complete immediately
      // and let the next tab pick up any newly-arrived names.
      if (knownJoints.length === 0) {
        refreshJoints().then(completeJoint);
      } else {
        completeJoint();
        refreshJoints();
      }
    }
  });

  // Prime the joint cache so the first Tab works without a round-trip.
  refreshJoints();
})();
