"use strict";

// IK target controls — Preview asks the server to solve IK without moving;
// Go sends the same pose to /api/pose. Errors land in the pose status pill
// and the preview output, never as alerts.

(function () {
  const els = {
    x:        document.getElementById("pose-x"),
    y:        document.getElementById("pose-y"),
    z:        document.getElementById("pose-z"),
    roll:     document.getElementById("pose-roll"),
    pitch:    document.getElementById("pose-pitch"),
    yaw:      document.getElementById("pose-yaw"),
    elbowUp:  document.getElementById("pose-elbow-up"),
    duration: document.getElementById("pose-duration"),
    preview:  document.getElementById("pose-preview"),
    go:       document.getElementById("pose-go"),
    out:      document.getElementById("pose-preview-out"),
    status:   document.getElementById("pose-status"),
  };

  function num(input, fallback) {
    const v = input.value.trim();
    if (v === "") return fallback;
    const n = Number(v);
    return Number.isFinite(n) ? n : fallback;
  }

  function readPose() {
    const yawRaw = els.yaw.value.trim();
    const body = {
      x:     num(els.x, 0),
      y:     num(els.y, 0),
      z:     num(els.z, 0),
      roll:  num(els.roll, 0),
      pitch: num(els.pitch, 0),
      elbow_up: !!els.elbowUp.checked,
    };
    if (yawRaw !== "") body.yaw = Number(yawRaw);
    return body;
  }

  function setPill(state, label) {
    els.status.className = "pill pill-" + state;
    els.status.textContent = label;
  }

  function formatAngles(angles) {
    return Object.keys(angles).sort().map(name => {
      const v = (+angles[name]).toFixed(2);
      return name.padEnd(12) + v + "°";
    }).join("\n");
  }

  async function postJSON(path, body) {
    const r = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const text = await r.text();
    let payload = null;
    try { payload = text ? JSON.parse(text) : null; } catch (_) {}
    return { ok: r.ok, status: r.status, body: payload };
  }

  els.preview.addEventListener("click", async () => {
    setPill("warn", "solving…");
    els.out.textContent = "";
    const { ok, body } = await postJSON("/api/ik", readPose());
    if (ok && body && body.reachable) {
      setPill("ok", "reachable");
      els.out.textContent = formatAngles(body.angles);
    } else {
      const msg = (body && body.error) || "unreachable";
      setPill("err", "unreachable");
      els.out.textContent = msg;
    }
  });

  els.go.addEventListener("click", async () => {
    const pose = readPose();
    const dur = num(els.duration, 1500);
    if (dur > 0) pose.duration_ms = dur;
    setPill("warn", "moving…");
    const { ok, body } = await postJSON("/api/pose", pose);
    if (ok) {
      setPill("ok", "sent");
      // Immediately apply the IK angles so sliders + 3D viewer don't wait
      // for the next /api/status poll.
      if (body && body.angles && window.BuddyState) {
        window.BuddyState.applyAngles(body.angles, { optimistic: true });
      }
    } else {
      const msg = (body && body.error) || "request failed";
      setPill("err", msg);
      els.out.textContent = msg;
    }
  });
})();
