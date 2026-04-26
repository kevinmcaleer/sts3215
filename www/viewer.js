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

// Link lengths in millimetres. MUST stay in sync with kinematics.py.
const L1 = 60.0;   // base column
const L2 = 110.0;  // upper arm
const L3 = 110.0;  // forearm
const L4 = 40.0;   // wrist
const L5 = 70.0;   // gripper / tool

const POLL_MS = 250;
const LINK_RADIUS = 14;          // mm — looks chunky enough on a phone
const JOINT_RADIUS = 18;         // mm — knuckle accents at each joint
const COLOR_LINK = 0x6da6ff;
const COLOR_JOINT = 0xf2c14e;
const COLOR_GRIPPER = 0xff8a5b;
const COLOR_BASE_PLATE = 0x35404f;

// Each joint name maps to an Object3D pivot. Setting `.rotation.<axis>`
// on these is the only thing the poll loop has to do.
const pivots = {};
// Materials we tint when torque is disabled.
const linkMaterials = [];

const viewerEl = document.getElementById("viewer");
if (!viewerEl) {
  // The page wasn't built with a viewer slot — nothing to do.
  console.warn("viewer.js: no #viewer element found, skipping init");
} else {
  init(viewerEl);
}

function init(container) {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0a0c11);

  // The arm in robot frame is built upright (+z up). We rotate the whole
  // rig so the robot-z axis aligns with world-y for three.js display.
  const rig = new THREE.Group();
  rig.rotation.x = -Math.PI / 2;
  scene.add(rig);

  // Soft lighting — one key light, one fill, plus a subtle ambient term.
  scene.add(new THREE.AmbientLight(0xffffff, 0.35));
  const key = new THREE.DirectionalLight(0xffffff, 0.9);
  key.position.set(200, 400, 300);
  scene.add(key);
  const fill = new THREE.DirectionalLight(0x88aaff, 0.4);
  fill.position.set(-300, 200, -200);
  scene.add(fill);

  // A faint floor grid for spatial reference. 50 mm cells, 10 cells wide.
  const grid = new THREE.GridHelper(500, 10, 0x223044, 0x1a232f);
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

  function animate() {
    controls.update();
    renderer.render(scene, camera);
    requestAnimationFrame(animate);
  }
  requestAnimationFrame(animate);

  // Independent poll loop — does not share state with app.js.
  pollStatus();
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

  // Gripper sits at the tip. Pivot exists so we can hint at "open" later;
  // for now we just visualise it as a small box at the end-effector.
  const gripper = new THREE.Object3D();
  gripper.position.z = L5;
  wristRoll.add(gripper);
  pivots.gripper = gripper;
  const gripGeom = new THREE.BoxGeometry(36, 18, 22);
  const gripMat = new THREE.MeshStandardMaterial({
    color: COLOR_GRIPPER, roughness: 0.45,
  });
  const gripMesh = new THREE.Mesh(gripGeom, gripMat);
  // Box is symmetric around its origin — no offset needed.
  gripper.add(gripMesh);
  linkMaterials.push(gripMat);
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
  // gripper position isn't part of the kinematic chain.
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

async function pollStatus() {
  try {
    const r = await fetch("/api/status", { cache: "no-store" });
    if (r.ok) {
      const data = await r.json();
      applyAngles(data.positions);
      setTorqueDim(data.torque_enabled !== false);
    }
  } catch (_err) {
    // Swallow errors — the next tick will retry. app.js owns the
    // user-visible "offline" pill.
  } finally {
    setTimeout(pollStatus, POLL_MS);
  }
}
