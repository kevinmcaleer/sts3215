// View-cube widget: small cube in the top-right of the 3D viewer with
// labeled faces, hover highlighting per zone, and a home button.
//
// The cube is built from 26 subcubes laid out in a 3×3×3 grid (the
// centre subcube is omitted). Each subcube represents one face / edge /
// corner zone — six faces (one non-zero axis), twelve edges (two
// non-zero axes), eight corners (three non-zero axes). Per-cell meshes
// give us:
//   * pixel-accurate hover highlighting (just tint that cell's material);
//   * unambiguous click direction (the cell's (i, j, k) IS the camera
//     direction the user wants to fly to).
//
// The widget's camera mirrors the main camera's direction so the face
// currently aimed at the user is always shown forward.
"use strict";

import * as THREE from "three";

const SIZE_PX = 96;
const ANIMATE_MS = 380;

const CELL = 1 / 3;       // each subcube is 1/3 of the cube side
const STEP = CELL;        // no gap — adjacent cells touch
const OUTER = CELL * 1.5; // half cube extent

// Light-theme colours per zone, with a single hover tint on top.
const COLOR_FACE   = 0xffffff;
const COLOR_EDGE   = 0xeaeef5;
const COLOR_CORNER = 0xd9dfe9;
const COLOR_HOVER  = 0xffd86b;
const COLOR_OUTLINE = 0xb6bdc9;
const COLOR_CELL_OUTLINE = 0xc8cdd6;

// BoxGeometry material order: [+x, -x, +y, -y, +z, -z].
function faceIndexFor(axis, sign) {
  if (axis === "x") return sign > 0 ? 0 : 1;
  if (axis === "y") return sign > 0 ? 2 : 3;
  return sign > 0 ? 4 : 5;
}

// Cube faces are labelled to match the arm's frame:
//   robot +x = world +x → "front"
//   robot +z = world +y → "top"
//   robot -y = world +z → "right"
const FACE_LABELS = {
  "x+": "front", "x-": "rear",
  "y+": "top",   "y-": "bottom",
  "z+": "right", "z-": "left",
};

const HOME_ICON_SVG = `
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
     stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
     aria-hidden="true">
  <path d="M3 10.5L12 3l9 7.5"/>
  <path d="M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5"/>
</svg>`;

export function setupViewCube({ mountEl, mainCamera, mainControls, homeView }) {
  const container = document.createElement("div");
  container.className = "view-cube-container";
  mountEl.appendChild(container);

  const cubeRenderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
  cubeRenderer.setPixelRatio(window.devicePixelRatio || 1);
  cubeRenderer.setSize(SIZE_PX, SIZE_PX, false);
  const cubeEl = cubeRenderer.domElement;
  cubeEl.classList.add("view-cube-canvas");
  cubeEl.setAttribute("title",
    "click a face / edge / corner to align the view");
  container.appendChild(cubeEl);

  const homeBtn = document.createElement("button");
  homeBtn.type = "button";
  homeBtn.className = "view-cube-home";
  homeBtn.title = "Home view";
  homeBtn.setAttribute("aria-label", "home view");
  homeBtn.innerHTML = HOME_ICON_SVG;
  container.appendChild(homeBtn);

  // --- Scene + camera ----------------------------------------------------

  const cubeScene = new THREE.Scene();
  const cubeCam = new THREE.PerspectiveCamera(35, 1, 0.1, 100);
  cubeCam.position.set(0, 0, 4);
  cubeCam.lookAt(0, 0, 0);

  cubeScene.add(new THREE.AmbientLight(0xffffff, 0.85));
  const cubeKey = new THREE.DirectionalLight(0xffffff, 0.45);
  cubeKey.position.set(2, 3, 4);
  cubeScene.add(cubeKey);

  // --- Build the 26 subcube cells ----------------------------------------

  const cells = [];                  // pickable meshes
  const labelTextureCache = {};

  for (let i = -1; i <= 1; i++) {
    for (let j = -1; j <= 1; j++) {
      for (let k = -1; k <= 1; k++) {
        if (i === 0 && j === 0 && k === 0) continue;
        const type = Math.abs(i) + Math.abs(j) + Math.abs(k);
        const baseColor =
          type === 1 ? COLOR_FACE :
          type === 2 ? COLOR_EDGE :
                       COLOR_CORNER;

        const materials = [0, 1, 2, 3, 4, 5].map(() =>
          new THREE.MeshBasicMaterial({ color: baseColor }));

        // Apply label textures only to face cells, on the outward face.
        if (type === 1) {
          const axis = i !== 0 ? "x" : (j !== 0 ? "y" : "z");
          const sign = (axis === "x" ? i : axis === "y" ? j : k);
          const key = axis + (sign > 0 ? "+" : "-");
          const label = FACE_LABELS[key];
          const tex = (labelTextureCache[label]
                    ||= makeFaceTexture(label));
          const idx = faceIndexFor(axis, sign);
          materials[idx] = new THREE.MeshBasicMaterial({
            map: tex, color: baseColor,
          });
        }

        const mesh = new THREE.Mesh(
          new THREE.BoxGeometry(CELL, CELL, CELL),
          materials,
        );
        mesh.position.set(i * STEP, j * STEP, k * STEP);
        mesh.userData.direction = new THREE.Vector3(i, j, k);
        mesh.userData.baseColor = baseColor;
        mesh.userData.materials = materials;

        // Per-cell wireframe so the user can tell where each zone is even
        // before they hover. Slightly darker than the cells so it reads
        // against the white face background.
        const wires = new THREE.LineSegments(
          new THREE.EdgesGeometry(mesh.geometry),
          new THREE.LineBasicMaterial({ color: COLOR_CELL_OUTLINE }),
        );
        mesh.add(wires);

        cubeScene.add(mesh);
        cells.push(mesh);
      }
    }
  }

  // Crisp outline around the whole cube.
  const outline = new THREE.LineSegments(
    new THREE.EdgesGeometry(new THREE.BoxGeometry(1.001, 1.001, 1.001)),
    new THREE.LineBasicMaterial({ color: COLOR_OUTLINE }),
  );
  cubeScene.add(outline);

  // --- Picking + hover ---------------------------------------------------

  const raycaster = new THREE.Raycaster();
  const ndc = new THREE.Vector2();
  let hovered = null;
  let animating = false;

  function tintCell(cell, hex) {
    for (const m of cell.userData.materials) m.color.setHex(hex);
  }
  function setHover(cell) {
    if (cell === hovered) return;
    if (hovered) tintCell(hovered, hovered.userData.baseColor);
    if (cell)    tintCell(cell, COLOR_HOVER);
    hovered = cell;
    cubeEl.style.cursor = cell ? "pointer" : "default";
  }
  function pickAt(ev) {
    const r = cubeEl.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) return null;
    ndc.x =  ((ev.clientX - r.left) / r.width)  * 2 - 1;
    ndc.y = -((ev.clientY - r.top)  / r.height) * 2 + 1;
    raycaster.setFromCamera(ndc, cubeCam);
    const hits = raycaster.intersectObjects(cells, false);
    return hits.length > 0 ? hits[0].object : null;
  }

  cubeEl.addEventListener("pointermove", (ev) => {
    setHover(pickAt(ev));
  });
  cubeEl.addEventListener("pointerleave", () => setHover(null));
  cubeEl.addEventListener("pointerdown", (ev) => {
    if (animating) return;
    const cell = pickAt(ev);
    if (!cell) return;
    animateCameraTo(cell.userData.direction);
  });

  homeBtn.addEventListener("click", () => {
    if (animating) return;
    animateCameraTo(null);
  });

  // --- Animation ---------------------------------------------------------

  function animateCameraTo(direction) {
    animating = true;
    setHover(null);
    mainControls.enabled = false;

    const target = mainControls.target.clone();
    const fromPos = mainCamera.position.clone();
    const fromUp = mainCamera.up.clone();
    const fromTarget = target.clone();

    let toPos, toUp, toTarget;
    if (direction === null) {
      toPos = new THREE.Vector3().fromArray(homeView.position);
      toTarget = new THREE.Vector3().fromArray(homeView.target);
      toUp = new THREE.Vector3(0, 1, 0);
    } else {
      const dist = fromPos.distanceTo(target);
      toPos = target.clone()
        .add(direction.clone().normalize().multiplyScalar(dist));
      toTarget = target.clone();
      const dy = direction.y;
      const dxz = Math.hypot(direction.x, direction.z);
      const isTopLike = Math.abs(dy) > 0.9 && dxz < 0.2;
      toUp = isTopLike
        ? new THREE.Vector3(-1, 0, 0)
        : new THREE.Vector3(0, 1, 0);
    }

    const t0 = performance.now();
    function step() {
      const t = Math.min((performance.now() - t0) / ANIMATE_MS, 1);
      const e = t * t * (3 - 2 * t);
      mainCamera.position.lerpVectors(fromPos, toPos, e);
      mainCamera.up.copy(fromUp).lerp(toUp, e).normalize();
      mainControls.target.lerpVectors(fromTarget, toTarget, e);
      mainCamera.lookAt(mainControls.target);
      mainControls.update();
      if (t < 1) requestAnimationFrame(step);
      else { animating = false; mainControls.enabled = true; }
    }
    requestAnimationFrame(step);
  }

  // --- Tick --------------------------------------------------------------

  function tick() {
    const offset = new THREE.Vector3().subVectors(
      mainCamera.position, mainControls.target);
    const len = offset.length();
    if (len < 1e-6) return;
    offset.multiplyScalar(4 / len);
    cubeCam.position.copy(offset);
    cubeCam.up.copy(mainCamera.up);
    cubeCam.lookAt(0, 0, 0);
    cubeRenderer.render(cubeScene, cubeCam);
  }

  return { tick, container, homeBtn };
}

// --- helpers --------------------------------------------------------------

function makeFaceTexture(label) {
  const SIZE = 256;
  const canvas = document.createElement("canvas");
  canvas.width = SIZE;
  canvas.height = SIZE;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, SIZE, SIZE);
  ctx.fillStyle = "#1a1d23";
  ctx.font = "600 56px -apple-system, BlinkMacSystemFont, system-ui, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(label, SIZE / 2, SIZE / 2);
  const tex = new THREE.CanvasTexture(canvas);
  tex.anisotropy = 4;
  return tex;
}
