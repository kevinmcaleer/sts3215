# Buddy HTTP API

The arm runs a small HTTP server (`server.py`) that serves the static web UI
from `/www/` on flash and exposes a JSON API for arm control.

All `/api/*` endpoints accept and return JSON. Errors return
`{"error": "..."}` with a 4xx/5xx status code; success returns either a data
payload (for `GET`) or `{"ok": true}` (for `POST`).

## Endpoints

### `GET /api/status`

Snapshot of the arm.

```json
{
  "positions":     {"base": 0.0, "shoulder": 0.0, ...},
  "temperatures":  {"base": 30, "shoulder": 31, ...},
  "torque_enabled": true
}
```

`positions` are user-frame degrees (offsets stripped). `temperatures` are in
°C; entries are `null` if the bus driver lacks `read_temperature`.
`torque_enabled` is `null` until `/api/torque` has been called.

### `POST /api/joint/<name>`

Move a single joint.

```json
{ "degrees": 90, "speed": 200, "acc": 30 }
```

`speed` and `acc` are optional. `400` if `degrees` is missing or
non-numeric. `404` if the joint name is unknown.

### `POST /api/move`

Move several joints at once.

```json
{
  "joints":      {"shoulder": 30, "elbow": 60},
  "duration_ms": 1500
}
```

If `duration_ms` or `max_speed` is provided, joints are paced by
`Buddy.move_all_sync` so they arrive together. With neither, falls back to
`Buddy.move_all` (independent speeds). Specifying both fields returns 400.

### `POST /api/pose`

Drive the gripper to a Cartesian target via inverse kinematics.

```json
{
  "x": 120, "y": 0, "z": 200,
  "roll": 0, "pitch": 30,
  "yaw": null,
  "duration_ms": 1500
}
```

`x`, `y`, `z` are in millimetres. `roll`, `pitch`, `yaw` are degrees and all
optional (default 0; `yaw` defaults to `atan2(y, x)`). Returns `400` with
`"unreachable"` in the message if IK can't solve, `501` if the running build
of `Buddy` lacks `move_to_pose`.

### `POST /api/ik`

Solve inverse kinematics for a pose **without moving** — useful for
previewing the joint angles in the UI before committing.

```json
{
  "x": 120, "y": 0, "z": 200,
  "roll": 0, "pitch": 30, "yaw": null,
  "elbow_up": false
}
```

Same field meanings as `/api/pose`. Reachable: `200` with
`{"reachable": true, "angles": {...}}`. Unreachable: `400` with
`{"reachable": false, "error": "..."}`.

### `POST /api/gripper`

```json
{ "state": "open" }   // or "close"
```

### `POST /api/torque`

```json
{ "enable": true }
```

### `POST /api/home`

Drive every kinematic joint back to its 0° user-frame position via
`Buddy.home`. Useful for parking the arm at a known reference pose
after boot or to reset between routines.

```json
{ "duration_ms": 1500, "include_gripper": false }
```

Both fields are optional. Returns `{ "ok": true, "angles": {...} }`
on success — the angles dict echoes the targets the server sent so
callers can apply them optimistically. Returns `501` if the running
build of `Buddy` lacks `home`.

Echoes the new `torque_enabled` state in the response.

### `POST /api/wifi`

Save Wi-Fi credentials into `config.json` (used by AP-mode provisioning).

```json
{ "ssid": "home", "password": "letmein" }
```

A reboot is required for the new credentials to take effect.

## Static files

Any `GET` outside `/api/` serves a file from the configured `www_root`
(default `/www`). `/` maps to `/index.html`. Path traversal (`..`) is
rejected with `400`. Unknown extensions fall back to
`application/octet-stream`.
