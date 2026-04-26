// 3D viewer for the Buddy 6-DOF arm.
//
// Uses three.js (loaded from unpkg via the importmap declared in index.html)
// plus OrbitControls for camera interaction. Polls /api/status every ~250 ms
// and pushes the joint angles into a parented Object3D chain that mirrors
// the kinematic chain in kinematics.py.
//
// Coordinate-frame conversion
// ---------------------------
// kinematics.py is +z-up: the home pose extends along +z, base rotates about
// world z, shoulder/elbow/wrist_pitch about y, wrist_roll about z (the
// approach axis at home). three.js is +y-up by convention. To keep the
// authoring code 1-to-1 with kinematics.py we build the arm in a +z-up
// "robot" frame and then rotate the entire rig -90° about the world x axis
// at the top level, which maps robot-z onto world-y. Inside the rig, every
// joint axis matches kinematics.py exactly:
//   base        -> rotateZ
//   shoulder    -> rotateY
//   elbow       -> rotateY
//   wrist_pitch -> rotateY
//   wrist_roll  -> rotateZ (the approach axis at home)
"use strict";

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { TransformControls } from "three/addons/controls/TransformControls.js";
import { setupViewCube } from "/viewcube.js";

// Link lengths in millimetres. MUST stay in sync with kinematics.py.
const L1 = 60.0;   // base column
const L2 = 110.0;  // upper arm
const L3 = 110.0;  // forearm
const L4 = 40.0;   // wrist
const L5 = 70.0;   // gripper / tool

const LINK_RADIUS = 14;          // mm — looks chunky enough on a phone
const JOINT_RADIUS = 18;         // mm — knuckle accents at each joint
const SCENE_BG = 0xe8ecf2;
const COLOR_LINK = 0x4d7dc4;
const COLOR_JOINT = 0xd9a637;
const COLOR_GRIPPER = 0xd16639;
const COLOR_BASE_PLATE = 0xb7c0cc;
const GRID_MAJOR = 0xb6bdc9;
const GRID_MINOR = 0xd2d8e0;
const COLOR_HANDLE = 0x88ddff;
const COLOR_HANDLE_HOVER = 0xfff4a1;
const COLOR_HANDLE_ERROR = 0xff6a6a;
const HANDLE_RADIUS = 22;        // mm — picks up easily on phone screens
const HANDLE_GRACE_MS = 250;     // keep gizmo open this long after mouse leaves

// Each joint name maps to an Object3D pivot. Setting `.rotation.<axis>`
// on these is the only thing the poll loop has to do.
const pivots = {};
// Materials we tint when torque is disabled.
const linkMaterials = [];
// Gripper-finger meshes whose x position we slide based on the live
// gripper-joint angle: [left, right]. Populated by buildArm.
const gripperFingers = [];

// Visual gripper travel: degrees → finger spacing in mm.
// Beyond GRIPPER_OPEN_DEG the fingers stay at the open spacing.
const GRIPPER_OPEN_DEG = 90;
const GRIPPER_HALF_CLOSED = 5;   // finger half-spacing when fully closed
const GRIPPER_HALF_OPEN = 22;    // finger half-spacing when fully open

const viewerEl = document.getElementById("viewer");
if (!viewerEl) {
  // The page wasn't built with a viewer slot — nothing to do.
  console.warn("viewer.js: no #viewer element found, skipping init");
} else {
  init(viewerEl);
}

function init(container) {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(SCENE_BG);

  // The arm in robot frame is built upright (+z up). We rotate the whole
  // rig so the robot-z axis aligns with world-y for three.js display.
  const rig = new THREE.Group();
  rig.rotation.x = -Math.PI / 2;
  scene.add(rig);

  // Soft lighting tuned for a light background — strong ambient + a key
  // light from above so the cylinders read as solid rather than washed out.
  scene.add(new THREE.AmbientLight(0xffffff, 0.7));
  const key = new THREE.DirectionalLight(0xffffff, 0.7);
  key.position.set(200, 400, 300);
  scene.add(key);
  const fill = new THREE.DirectionalLight(0x88aaff, 0.25);
  fill.position.set(-300, 200, -200);
  scene.add(fill);

  // A faint floor grid for spatial reference. 50 mm cells, 10 cells wide.
  const grid = new THREE.GridHelper(500, 10, GRID_MAJOR, GRID_MINOR);
  grid.position.y = 0;
  scene.add(grid);

  buildArm(rig);

  // Camera frames the workspace: tip at home is ~390 mm above the base,
  // so place the camera comfortably outside that radius.
  const camera = new THREE.PerspectiveCamera(45, 1, 1, 5000);
  camera.position.set(420, 320, 480);
  camera.lookAt(0, 180, 0);

  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(window.devicePixelRatio || 1);
  container.appendChild(renderer.domElement);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(0, 180, 0);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.minDistance = 150;
  controls.maxDistance = 1500;

  function resize() {
    const w = container.clientWidth || 1;
    const h = container.clientHeight || 1;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  resize();
  window.addEventListener("resize", resize);

  // End-effector drag handle: hover the marker to summon arrows, drag an
  // arrow to retarget the gripper. Release sends POST /api/pose with the
  // resulting xyz (orientation is left to the server's atan2(y, x) default).
  const handleState = setUpDragHandle({
    scene, camera, renderer, controls,
    getTipWorldPosition: (out) => pivots.gripper.getWorldPosition(out),
  });

  // View cube + home button overlay. Captures the current camera position
  // and target as the "home" view so the home button can restore them.
  const viewCube = setupViewCube({
    mountEl: container,
    mainCamera: camera,
    mainControls: controls,
    homeView: {
      position: [camera.position.x, camera.position.y, camera.position.z],
      target:   [controls.target.x,  controls.target.y,  controls.target.z],
    },
  });

  function animate() {
    controls.update();
    handleState.tick();
    renderer.render(scene, camera);
    viewCube.tick();
    requestAnimationFrame(animate);
  }
  requestAnimationFrame(animate);

  // Subscribe to angle / torque events fired by app.js — both the
  // optimistic ones (slider drag, pose POST response) and the periodic
  // status poll. No separate /api/status poll inside the viewer; one
  // network call per tick beats two.
  document.addEventListener("buddy:angles", (ev) => {
    applyAngles(ev.detail.angles);
  });
  document.addEventListener("buddy:torque", (ev) => {
    setTorqueDim(ev.detail.enabled !== false);
  });
  // If app.js has already fetched a status by the time we mount, pick up
  // its cached state immediately so we don't render a frame at zero.
  if (window.BuddyState) {
    applyAngles(window.BuddyState.positions);
    setTorqueDim(window.BuddyState.torque_enabled !== false);
  }
}

// --- Drag handle ----------------------------------------------------------

function setUpDragHandle({ scene, camera, renderer, controls,
                          getTipWorldPosition }) {
  // The handle lives in world space, parented to the scene (NOT the rig),
  // so its position is read out directly without any extra matrix work.
  const handleMat = new THREE.MeshStandardMaterial({
    color: COLOR_HANDLE, transparent: true, opacity: 0.55,
    roughness: 0.35, metalness: 0.1,
  });
  const handle = new THREE.Mesh(
    new THREE.SphereGeometry(HANDLE_RADIUS, 18, 14), handleMat);
  handle.renderOrder = 2;
  scene.add(handle);

  const tc = new TransformControls(camera, renderer.domElement);
  tc.attach(handle);
  tc.setMode("translate");
  tc.setSize(0.9);
  tc.visible = false;
  tc.enabled = false;
  scene.add(tc);

  const raycaster = new THREE.Raycaster();
  const mouse = new THREE.Vector2();
  let hoverHide = 0;     // timestamp at which to hide if no further hover
  let autoTrack = true;  // pause while user is dragging

  // Initial position: right at the tip on first frame.
  getTipWorldPosition(handle.position);

  // While the user is interacting with TransformControls, pause OrbitControls
  // so the camera doesn't fight with the gizmo.
  tc.addEventListener("dragging-changed", (ev) => {
    controls.enabled = !ev.value;
    if (ev.value) {
      autoTrack = false;
      handleMat.color.setHex(COLOR_HANDLE_HOVER);
    } else {
      // Drag end → send pose. Re-enable auto-tracking only after the response
      // settles (or after a small delay if the request hangs).
      sendPose(handle.position).finally(() => {
        autoTrack = true;
        handleMat.color.setHex(COLOR_HANDLE);
      });
    }
  });

  function showGizmo() {
    tc.visible = true;
    tc.enabled = true;
    handleMat.color.setHex(COLOR_HANDLE_HOVER);
    handleMat.opacity = 0.9;
  }
  function hideGizmo() {
    if (tc.dragging) return;
    tc.visible = false;
    tc.enabled = false;
    handleMat.color.setHex(COLOR_HANDLE);
    handleMat.opacity = 0.55;
  }

  function flashError() {
    const orig = handleMat.color.getHex();
    handleMat.color.setHex(COLOR_HANDLE_ERROR);
    setTimeout(() => handleMat.color.setHex(orig), 350);
  }

  // Hover detection. We test against the handle sphere AND, if the gizmo is
  // already showing, against its arrow meshes — otherwise the user would
  // lose the gizmo the instant their cursor crossed onto an arrow.
  function onPointerMove(ev) {
    const rect = renderer.domElement.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;
    mouse.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1;
    mouse.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(mouse, camera);

    const targets = [handle];
    if (tc.visible) {
      tc.traverse((o) => { if (o.isMesh) targets.push(o); });
    }
    const hits = raycaster.intersectObjects(targets, false);
    if (hits.length > 0) {
      hoverHide = 0;
      showGizmo();
    } else if (tc.visible && !tc.dragging) {
      // Defer the hide so a quick cursor jitter from sphere → arrow doesn't
      // dismiss the gizmo.
      if (hoverHide === 0) hoverHide = performance.now() + HANDLE_GRACE_MS;
    }
  }

  renderer.domElement.addEventListener("pointermove", onPointerMove);
  renderer.domElement.addEventListener("pointerleave", () => {
    if (!tc.dragging) hoverHide = performance.now() + HANDLE_GRACE_MS;
  });

  async function sendPose(worldPos) {
    // Three is +y-up; kinematics is +z-up. The rig is rotated -90° about
    // world x at the top level, so:
    //     x_robot = x_world
    //     y_robot = -z_world
    //     z_robot = y_world
    const body = {
      x: worldPos.x,
      y: -worldPos.z,
      z: worldPos.y,
      duration_ms: 1500,
    };
    try {
      const r = await fetch("/api/pose", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        flashError();
        return;
      }
      // Apply the IK angles optimistically so the arm snaps to the new
      // pose without waiting for the next status poll.
      const data = await r.json().catch(() => null);
      if (data && data.angles && window.BuddyState) {
        window.BuddyState.applyAngles(data.angles, { optimistic: true });
      }
    } catch (_e) {
      flashError();
    }
  }

  function tick() {
    if (autoTrack && !tc.dragging) {
      getTipWorldPosition(handle.position);
    }
    if (hoverHide && !tc.dragging && performance.now() >= hoverHide) {
      hoverHide = 0;
      hideGizmo();
    }
  }

  return { tick, handle, transformControls: tc };
}

// Build the kinematic chain as parented pivots. Geometry is authored in
// the local frame of each link, with translations along +z so each child
// pivot sits at the next joint's origin.
function buildArm(rigRoot) {
  // Tiny base plate so the arm doesn't appear to float.
  const plateGeom = new THREE.CylinderGeometry(45, 50, 8, 24);
  const plateMat = new THREE.MeshStandardMaterial({
    color: COLOR_BASE_PLATE, roughness: 0.7,
  });
  const plate = new THREE.Mesh(plateGeom, plateMat);
  // CylinderGeometry is built along +y; rotate it so its axis is +z (robot up).
  plate.rotation.x = Math.PI / 2;
  plate.position.z = 4;
  rigRoot.add(plate);

  // Pivot order: base -> shoulder -> elbow -> wrist_pitch -> wrist_roll -> gripper.
  const base = new THREE.Object3D();
  rigRoot.add(base);
  pivots.base = base;
  attachJointKnuckle(base);
  attachLinkAlongZ(base, L1, "base column");

  const shoulder = new THREE.Object3D();
  shoulder.position.z = L1;
  base.add(shoulder);
  pivots.shoulder = shoulder;
  attachJointKnuckle(shoulder);
  attachLinkAlongZ(shoulder, L2, "upper arm");

  const elbow = new THREE.Object3D();
  elbow.position.z = L2;
  shoulder.add(elbow);
  pivots.elbow = elbow;
  attachJointKnuckle(elbow);
  attachLinkAlongZ(elbow, L3, "forearm");

  const wristPitch = new THREE.Object3D();
  wristPitch.position.z = L3;
  elbow.add(wristPitch);
  pivots.wrist_pitch = wristPitch;
  attachJointKnuckle(wristPitch);
  attachLinkAlongZ(wristPitch, L4, "wrist");

  const wristRoll = new THREE.Object3D();
  wristRoll.position.z = L4;
  wristPitch.add(wristRoll);
  pivots.wrist_roll = wristRoll;
  attachJointKnuckle(wristRoll);
  attachLinkAlongZ(wristRoll, L5, "tool");

  // Parallel-jaw gripper. The gripper pivot sits at the kinematic tip
  // (L5 from wrist_roll). A flat mount plate is anchored just past the
  // tip; two finger rails extend forward in +z (the approach direction)
  // and slide apart along x as the gripper joint opens.
  const gripper = new THREE.Object3D();
  gripper.position.z = L5;
  wristRoll.add(gripper);
  pivots.gripper = gripper;

  const mountGeom = new THREE.BoxGeometry(56, 30, 8);
  const mountMat = new THREE.MeshStandardMaterial({
    color: COLOR_GRIPPER, roughness: 0.45,
  });
  const mount = new THREE.Mesh(mountGeom, mountMat);
  mount.position.z = 4;             // sits just past the tip plane
  gripper.add(mount);
  linkMaterials.push(mountMat);

  const fingerGeom = new THREE.BoxGeometry(8, 22, 50);
  const fingerMat = new THREE.MeshStandardMaterial({
    color: COLOR_GRIPPER, roughness: 0.5,
  });

  function makeFinger(side) {
    const f = new THREE.Mesh(fingerGeom, fingerMat);
    f.position.z = 33;              // mount front (z=8) + finger half (25)
    f.position.x = side * GRIPPER_HALF_CLOSED;
    gripper.add(f);
    return f;
  }

  // Inner pad on each finger — the contact surface, slightly inset on x
  // so it reads as a soft gripping face rather than a flat side wall.
  const padGeom = new THREE.BoxGeometry(2, 18, 38);
  const padMat = new THREE.MeshStandardMaterial({
    color: 0x2a2f3d, roughness: 0.7,
  });
  function attachPad(finger, side) {
    const p = new THREE.Mesh(padGeom, padMat);
    p.position.x = -side * 5;       // inset toward the centre line
    p.position.z = -2;              // tucked back from the finger tip
    finger.add(p);
  }

  const fingerL = makeFinger(-1);
  const fingerR = makeFinger(+1);
  attachPad(fingerL, -1);
  attachPad(fingerR, +1);
  gripperFingers.push(fingerL, fingerR);
  linkMaterials.push(fingerMat, padMat);
}

// Place a cylinder of length `length` starting at the local origin,
// extending along +z. CylinderGeometry's native axis is +y, so we rotate.
function attachLinkAlongZ(parent, length, _label) {
  const geom = new THREE.CylinderGeometry(LINK_RADIUS, LINK_RADIUS, length, 18);
  const mat = new THREE.MeshStandardMaterial({
    color: COLOR_LINK, roughness: 0.5, metalness: 0.1,
  });
  const mesh = new THREE.Mesh(geom, mat);
  mesh.rotation.x = Math.PI / 2;     // +y -> +z
  mesh.position.z = length / 2;      // span [0, length] along +z
  parent.add(mesh);
  linkMaterials.push(mat);
}

function attachJointKnuckle(parent) {
  const geom = new THREE.SphereGeometry(JOINT_RADIUS, 18, 14);
  const mat = new THREE.MeshStandardMaterial({
    color: COLOR_JOINT, roughness: 0.4, metalness: 0.15,
  });
  const mesh = new THREE.Mesh(geom, mat);
  parent.add(mesh);
  linkMaterials.push(mat);
}

// Apply joint angles (degrees) onto the pivots. Axis assignments mirror
// kinematics.py — see the file-header comment.
function applyAngles(positions) {
  if (!positions) return;
  setRot(pivots.base,        "z", positions.base);
  setRot(pivots.shoulder,    "y", positions.shoulder);
  setRot(pivots.elbow,       "y", positions.elbow);
  setRot(pivots.wrist_pitch, "y", positions.wrist_pitch);
  setRot(pivots.wrist_roll,  "z", positions.wrist_roll);
  // Gripper isn't part of the kinematic chain — it slides the finger
  // rails apart instead of rotating.
  if (positions.gripper !== undefined) applyGripper(positions.gripper);
}

function applyGripper(degrees) {
  const v = Number(degrees);
  if (!Number.isFinite(v)) return;
  const t = Math.min(Math.max(v / GRIPPER_OPEN_DEG, 0), 1);
  const half = GRIPPER_HALF_CLOSED
             + (GRIPPER_HALF_OPEN - GRIPPER_HALF_CLOSED) * t;
  if (gripperFingers[0]) gripperFingers[0].position.x = -half;
  if (gripperFingers[1]) gripperFingers[1].position.x = +half;
}

function setRot(pivot, axis, degrees) {
  if (!pivot) return;
  const v = Number(degrees);
  if (!Number.isFinite(v)) return;
  pivot.rotation[axis] = (v * Math.PI) / 180.0;
}

function setTorqueDim(enabled) {
  // When torque is off we want the arm to read as "limp" — drop opacity
  // and desaturate slightly. Easy to spot on a dashboard.
  for (const m of linkMaterials) {
    m.transparent = true;
    m.opacity = enabled ? 1.0 : 0.45;
  }
}

