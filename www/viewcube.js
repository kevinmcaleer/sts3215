// View-cube widget: small cube in the top-right of the 3D viewer with
// labeled faces. Clicking a face / edge / corner animates the main
// camera to view the arm from that direction. A home button next to it
// resets to the default camera position.
//
// Implementation: one BoxGeometry rendered in its own scene + camera +
// canvas overlaid on the parent. Face labels are CanvasTextures applied
// to each face individually. The widget's camera mirrors the main
// camera's direction so the cube always shows the face the user is
// currently looking at toward the screen.
"use strict";

import * as THREE from "three";

const SIZE_PX = 96;       // cube widget canvas size
const HOME_SIZE_PX = 32;  // home button size
const ANIMATE_MS = 380;
const ZONE_THRESHOLD = 0.34;  // |coord| above this counts as "near edge"

// BoxGeometry material order is [+x, -x, +y, -y, +z, -z].
// Labels are chosen so the cube's frame matches the arm's frame:
//   robot +x = world +x → "front"
//   robot +z = world +y → "top"
//   robot -y = world +z → "right"
const FACE_LABELS = ["front", "rear", "top", "bottom", "right", "left"];

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

  // --- Cube renderer ------------------------------------------------------
  const cubeRenderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
  cubeRenderer.setPixelRatio(window.devicePixelRatio || 1);
  cubeRenderer.setSize(SIZE_PX, SIZE_PX, false);
  const cubeEl = cubeRenderer.domElement;
  cubeEl.classList.add("view-cube-canvas");
  cubeEl.setAttribute("title", "click a face / edge / corner to align the view");
  container.appendChild(cubeEl);

  // --- Home button --------------------------------------------------------
  const homeBtn = document.createElement("button");
  homeBtn.type = "button";
  homeBtn.className = "view-cube-home";
  homeBtn.title = "Home view";
  homeBtn.setAttribute("aria-label", "home view");
  homeBtn.innerHTML = HOME_ICON_SVG;
  container.appendChild(homeBtn);

  // --- Cube scene ---------------------------------------------------------
  const cubeScene = new THREE.Scene();

  const cubeCam = new THREE.PerspectiveCamera(35, 1, 0.1, 100);
  cubeCam.position.set(0, 0, 4);
  cubeCam.lookAt(0, 0, 0);

  cubeScene.add(new THREE.AmbientLight(0xffffff, 0.85));
  const cubeKey = new THREE.DirectionalLight(0xffffff, 0.45);
  cubeKey.position.set(2, 3, 4);
  cubeScene.add(cubeKey);

  const faceMaterials = FACE_LABELS.map((label) =>
    new THREE.MeshBasicMaterial({ map: makeFaceTexture(label) }));
  const cubeMesh = new THREE.Mesh(
    new THREE.BoxGeometry(1, 1, 1),
    faceMaterials,
  );
  cubeScene.add(cubeMesh);

  // Edge outline so the cube reads as a 3D shape on a light background.
  const edges = new THREE.LineSegments(
    new THREE.EdgesGeometry(cubeMesh.geometry),
    new THREE.LineBasicMaterial({ color: 0xb6bdc9 }),
  );
  cubeMesh.add(edges);

  // --- Picking ------------------------------------------------------------
  const raycaster = new THREE.Raycaster();
  const ndc = new THREE.Vector2();
  let animating = false;

  cubeEl.addEventListener("pointerdown", (ev) => {
    if (animating) return;
    const r = cubeEl.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) return;
    ndc.x =  ((ev.clientX - r.left) / r.width)  * 2 - 1;
    ndc.y = -((ev.clientY - r.top)  / r.height) * 2 + 1;
    raycaster.setFromCamera(ndc, cubeCam);
    const hits = raycaster.intersectObject(cubeMesh, false);
    if (hits.length === 0) return;
    const local = cubeMesh.worldToLocal(hits[0].point.clone());
    const dir = directionFromLocalHit(local);
    if (dir.lengthSq() === 0) return;
    animateCameraTo(dir);
  });

  homeBtn.addEventListener("click", () => {
    if (animating) return;
    animateCameraTo(null);  // null → snap to homeView
  });

  // --- Animation ----------------------------------------------------------

  function animateCameraTo(direction) {
    animating = true;
    mainControls.enabled = false;

    const target = mainControls.target.clone();
    const fromPos = mainCamera.position.clone();
    const fromUp = mainCamera.up.clone();

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
      // For pure top/bottom views, +y as up is degenerate. Pick a horizontal
      // up vector pointing toward the rear of the arm so "front" reads at
      // the bottom of the screen — the standard plan-view convention.
      const dy = direction.y;
      const dxz = Math.hypot(direction.x, direction.z);
      const isTopLike = Math.abs(dy) > 0.9 && dxz < 0.2;
      if (isTopLike) {
        toUp = new THREE.Vector3(-1, 0, 0);
      } else {
        toUp = new THREE.Vector3(0, 1, 0);
      }
    }

    const fromTarget = mainControls.target.clone();
    const t0 = performance.now();
    function step() {
      const t = Math.min((performance.now() - t0) / ANIMATE_MS, 1);
      const e = t * t * (3 - 2 * t);   // smoothstep
      mainCamera.position.lerpVectors(fromPos, toPos, e);
      mainCamera.up.copy(fromUp).lerp(toUp, e).normalize();
      mainControls.target.lerpVectors(fromTarget, toTarget, e);
      mainCamera.lookAt(mainControls.target);
      mainControls.update();
      if (t < 1) {
        requestAnimationFrame(step);
      } else {
        animating = false;
        mainControls.enabled = true;
      }
    }
    requestAnimationFrame(step);
  }

  // --- Tick ---------------------------------------------------------------

  function tick() {
    // Cube widget camera mirrors the main camera's direction so the face
    // currently aimed at the screen is always the one the user sees.
    const offset = new THREE.Vector3().subVectors(
      mainCamera.position, mainControls.target,
    );
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

function directionFromLocalHit(local) {
  // local is in [-0.5, 0.5]^3 with at least one component near ±0.5.
  // Map each axis to {-1, 0, +1} based on whether it's "near boundary".
  const dir = new THREE.Vector3();
  const components = ["x", "y", "z"];
  for (const ax of components) {
    const c = local[ax];
    if (c >  ZONE_THRESHOLD) dir[ax] = +1;
    else if (c < -ZONE_THRESHOLD) dir[ax] = -1;
  }
  // BoxGeometry's surface always has at least one component within
  // [0.499, 0.5] in absolute value; pull whichever is most extreme as a
  // safety net so even thin clicks at the centre of a face still produce
  // a face direction.
  if (dir.lengthSq() === 0) {
    let bestAx = "x", bestVal = Math.abs(local.x);
    for (const ax of components) {
      if (Math.abs(local[ax]) > bestVal) { bestAx = ax; bestVal = Math.abs(local[ax]); }
    }
    dir[bestAx] = local[bestAx] > 0 ? 1 : -1;
  }
  return dir;
}

function makeFaceTexture(label) {
  const SIZE = 256;
  const canvas = document.createElement("canvas");
  canvas.width = SIZE;
  canvas.height = SIZE;
  const ctx = canvas.getContext("2d");
  // Subtle face fill so the cube reads on a light background.
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, SIZE, SIZE);
  ctx.fillStyle = "#f1f3f7";
  ctx.fillRect(8, 8, SIZE - 16, SIZE - 16);
  // Label.
  ctx.fillStyle = "#1a1d23";
  ctx.font = "600 56px -apple-system, BlinkMacSystemFont, system-ui, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(label, SIZE / 2, SIZE / 2);
  const tex = new THREE.CanvasTexture(canvas);
  tex.anisotropy = 4;
  return tex;
}
