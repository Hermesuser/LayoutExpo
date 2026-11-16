import { DMM_PER_CM, formatMetric } from "/ui/shared/homography.js";

const SVG_NS = "http://www.w3.org/2000/svg";
const params = new URLSearchParams(window.location.search);
const token = params.get("token") || "";

const state = {
  snapshot: null,
  selectedPlacementId: null,
  zoom: 1,
  unit: "cm",
  showDims: true,
  showAnchors: true,
  showEyeLevel: true,
  cleanMode: false,
  undoStack: [],
  redoStack: [],
  activeSnapGuides: [],
  displays: [],
  projectorOpen: false,
  capabilities: { native_dialogs: false, native_projector: false },
};

const announcer = document.getElementById("sr-announcer");
const toastBanner = document.getElementById("toast-banner");
const wallSvg = document.getElementById("wall-svg");
const catalogList = document.getElementById("catalog-list");
const wallSelect = document.getElementById("wall-select");
const projectTitleInput = document.getElementById("project-title");
const issuesBanner = document.getElementById("issues-banner");
let toastTimer = null;
let pendingMutations = 0;

function announce(msg, isError = false, options = {}) {
  if (announcer) announcer.textContent = msg;
  if (toastBanner && msg) {
    toastBanner.classList.toggle("is-error", Boolean(isError));
    if (options.undoable && state.undoStack.length > 0) {
      const span = document.createElement("span");
      span.textContent = msg;
      const undoBtn = document.createElement("button");
      undoBtn.type = "button";
      undoBtn.className = "btn btn-sm btn-secondary";
      undoBtn.textContent = "Deshacer";
      undoBtn.addEventListener("click", () => {
        toastBanner.classList.add("hidden");
        document.getElementById("btn-undo")?.click();
      });
      toastBanner.replaceChildren(span, undoBtn);
    } else {
      toastBanner.textContent = msg;
    }
    toastBanner.classList.remove("hidden");
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toastBanner.classList.add("hidden");
    }, isError ? 6000 : options.undoable ? 6000 : 4000);
  }
}

function computeFittedWallWidthPx(wall) {
  const viewport = document.getElementById("canvas-viewport");
  const availW = Math.max(360, (viewport?.clientWidth || 860) - 72);
  const availH = Math.max(260, (viewport?.clientHeight || 560) - 88);
  const aspect = wall.height_dmm / Math.max(1, wall.width_dmm);
  const fitW = Math.min(availW, availH / Math.max(0.05, aspect));
  return Math.max(240, Math.round(fitW * state.zoom));
}

function svgEl(tag, attrs = {}) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    node.setAttribute(k, String(v));
  }
  return node;
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}), "X-LayoutExpo-Token": token };
  if (options.body && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  const method = (options.method || "GET").toUpperCase();
  const isMutation = method !== "GET" && method !== "HEAD";
  if (isMutation) pendingMutations += 1;
  try {
    const res = await fetch(path, { ...options, headers });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || `Error HTTP ${res.status}`);
    }
    return data;
  } finally {
    if (isMutation) {
      setTimeout(() => {
        pendingMutations = Math.max(0, pendingMutations - 1);
      }, 250);
    }
  }
}

function pushUndoSnapshot() {
  if (!state.snapshot) return;
  const clone = structuredClone(state.snapshot.project);
  state.undoStack.push(clone);
  if (state.undoStack.length > 40) state.undoStack.shift();
  state.redoStack = [];
}

function getActiveWall() {
  if (!state.snapshot) return null;
  const walls = state.snapshot.project.walls || [];
  return walls.find((w) => w.id === state.snapshot.active_wall_id) || walls[0] || null;
}

function outerSizeDmm(art) {
  if (art.mounting_type === "direct" || art.mounting_type === "canvas") {
    return [art.image_width_dmm, art.image_height_dmm];
  }
  const w =
    art.image_width_dmm +
    art.passepartout.left_dmm +
    art.passepartout.right_dmm +
    art.frame.left_dmm +
    art.frame.right_dmm;
  const h =
    art.image_height_dmm +
    art.passepartout.top_dmm +
    art.passepartout.bottom_dmm +
    art.frame.top_dmm +
    art.frame.bottom_dmm;
  return [w, h];
}

async function commitProject(projectObj, activeWallId = state.snapshot?.active_wall_id) {
  const snap = await api("/api/project", {
    method: "PUT",
    body: JSON.stringify({ project: projectObj, active_wall_id: activeWallId }),
  });
  state.snapshot = snap;
  renderAll();
}

function renderHeader() {
  if (!state.snapshot) return;
  const proj = state.snapshot.project;
  if (projectTitleInput && document.activeElement !== projectTitleInput) {
    projectTitleInput.value = proj.title;
  }
  if (wallSelect) {
    wallSelect.replaceChildren();
    for (const wall of proj.walls) {
      const opt = document.createElement("option");
      opt.value = wall.id;
      opt.textContent = `${wall.name} (${formatMetric(wall.width_dmm, state.unit)})`;
      opt.selected = wall.id === state.snapshot.active_wall_id;
      wallSelect.appendChild(opt);
    }
  }
  const undoBtn = document.getElementById("btn-undo");
  if (undoBtn) undoBtn.disabled = state.undoStack.length === 0;
  const redoBtn = document.getElementById("btn-redo");
  if (redoBtn) redoBtn.disabled = state.redoStack.length === 0;
}

function renderCatalog() {
  if (!state.snapshot || !catalogList) return;
  const proj = state.snapshot.project;
  const placedIds = new Set(proj.walls.flatMap((w) => w.placements.map((p) => p.artwork_id)));
  const unplacedCount = proj.artworks.filter((a) => !placedIds.has(a.id)).length;
  const placePendingBtn = document.getElementById("btn-place-unplaced");
  if (placePendingBtn) {
    placePendingBtn.classList.toggle("hidden", unplacedCount === 0);
    placePendingBtn.textContent = `Colocar ${unplacedCount} obra(s) pendiente(s)`;
  }

  catalogList.replaceChildren();

  for (const art of proj.artworks) {
    const li = document.createElement("li");
    li.className = "catalog-card";

    if (art.sha256) {
      const img = document.createElement("img");
      img.className = "catalog-thumb";
      img.alt = `Miniatura de ${art.title}`;
      img.src = `/api/media/proxy/${encodeURIComponent(art.id)}?token=${encodeURIComponent(token)}`;
      li.appendChild(img);
    } else {
      const placeholder = document.createElement("div");
      placeholder.className = "catalog-thumb";
      placeholder.setAttribute("aria-hidden", "true");
      li.appendChild(placeholder);
    }

    const meta = document.createElement("div");
    meta.className = "catalog-meta";
    const name = document.createElement("p");
    name.className = "catalog-name";
    name.textContent = art.title;
    const [ow, oh] = outerSizeDmm(art);
    const dims = document.createElement("p");
    dims.className = "catalog-dims";
    dims.textContent = `${formatMetric(ow, state.unit)} × ${formatMetric(oh, state.unit)}`;
    meta.append(name, dims);
    li.appendChild(meta);

    const actions = document.createElement("div");
    actions.className = "catalog-actions";

    const placeBtn = document.createElement("button");
    placeBtn.type = "button";
    placeBtn.className = "btn btn-sm btn-secondary";
    placeBtn.textContent = placedIds.has(art.id) ? "Duplicar" : "Colocar";
    placeBtn.setAttribute("aria-label", `Colocar ${art.title} en muro activo`);
    placeBtn.addEventListener("click", () => placeArtworkOnWall(art.id));

    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "btn btn-sm btn-danger";
    delBtn.textContent = "Quitar";
    delBtn.setAttribute("aria-label", `Eliminar ${art.title} del catálogo`);
    delBtn.addEventListener("click", () => removeArtworkFromCatalog(art.id));

    actions.append(placeBtn, delBtn);
    li.appendChild(actions);

    catalogList.appendChild(li);
  }
}

function renderCanvas() {
  if (!state.snapshot || !wallSvg) return;
  const wall = getActiveWall();
  if (!wall) return;

  const proj = state.snapshot.project;
  const artsById = new Map(proj.artworks.map((a) => [a.id, a]));
  const report = state.snapshot.reports[wall.id];
  const issues = report ? report.issues : [];
  const badPlacementIds = new Set(issues.flatMap((iss) => iss.placement_ids));

  if (issuesBanner) {
    if (issues.length > 0) {
      issuesBanner.classList.remove("hidden");
      if (issues.length === 1) {
        issuesBanner.textContent = `⚠ ${issues[0].message}`;
      } else {
        const toggle = document.createElement("button");
        toggle.type = "button";
        toggle.className = "issues-toggle";
        toggle.setAttribute("aria-expanded", "false");
        toggle.textContent = `⚠ ${issues.length} alertas: ${issues[0].message} (ver todas)`;
        const list = document.createElement("ul");
        list.className = "issues-list hidden";
        for (const iss of issues) {
          const li = document.createElement("li");
          li.textContent = iss.message;
          list.appendChild(li);
        }
        toggle.addEventListener("click", () => {
          const expanded = toggle.getAttribute("aria-expanded") === "true";
          toggle.setAttribute("aria-expanded", String(!expanded));
          list.classList.toggle("hidden", expanded);
        });
        issuesBanner.replaceChildren(toggle, list);
      }
    } else {
      issuesBanner.classList.add("hidden");
      issuesBanner.replaceChildren();
    }
  }

  // Escala responsiva ajustada al ancho y alto del viewport + zoom
  const previouslyFocusedPlacementId =
    document.activeElement?.closest?.(".artwork-node")?.getAttribute?.("data-placement-id") || null;
  const basePxWidth = computeFittedWallWidthPx(wall);
  const aspect = wall.height_dmm / Math.max(1, wall.width_dmm);
  wallSvg.setAttribute("width", String(basePxWidth));
  wallSvg.setAttribute("height", String(Math.round(basePxWidth * aspect)));
  wallSvg.setAttribute("viewBox", `0 0 ${wall.width_dmm} ${wall.height_dmm}`);
  wallSvg.replaceChildren();

  const unitPx = wall.width_dmm / Math.max(1, basePxWidth);
  const toSvgY = (yDmm) => wall.height_dmm - yDmm;

function renderWallBackground(wall) {
  const w = wall.width_dmm;
  const h = wall.height_dmm;
  wallSvg.appendChild(
    svgEl("rect", {
      x: 0,
      y: 0,
      width: w,
      height: h,
      fill: wall.wall_color_hex || "#F4F3EF",
    }),
  );

  const defs = svgEl("defs");
  const tex = wall.wall_texture_preset || "none";
  if (tex !== "none") {
    const patId = `wall-tex-${wall.id}`;
    if (tex === "plaster") {
      const pat = svgEl("pattern", { id: patId, width: 2000, height: 2000, patternUnits: "userSpaceOnUse" });
      pat.appendChild(svgEl("circle", { cx: 400, cy: 500, r: 90, fill: "#000000", "fill-opacity": 0.04 }));
      pat.appendChild(svgEl("circle", { cx: 1400, cy: 1300, r: 120, fill: "#000000", "fill-opacity": 0.035 }));
      pat.appendChild(svgEl("circle", { cx: 1650, cy: 350, r: 70, fill: "#FFFFFF", "fill-opacity": 0.25 }));
      defs.appendChild(pat);
    } else if (tex === "concrete") {
      const pat = svgEl("pattern", { id: patId, width: 6000, height: 4000, patternUnits: "userSpaceOnUse" });
      pat.appendChild(svgEl("rect", { x: 0, y: 0, width: 6000, height: 4000, fill: "none", stroke: "#000000", "stroke-opacity": 0.09, "stroke-width": 40 }));
      pat.appendChild(svgEl("circle", { cx: 800, cy: 800, r: 75, fill: "#000000", "fill-opacity": 0.12 }));
      pat.appendChild(svgEl("circle", { cx: 5200, cy: 800, r: 75, fill: "#000000", "fill-opacity": 0.12 }));
      pat.appendChild(svgEl("circle", { cx: 800, cy: 3200, r: 75, fill: "#000000", "fill-opacity": 0.12 }));
      pat.appendChild(svgEl("circle", { cx: 5200, cy: 3200, r: 75, fill: "#000000", "fill-opacity": 0.12 }));
      defs.appendChild(pat);
    } else if (tex === "brick") {
      const pat = svgEl("pattern", { id: patId, width: 2400, height: 1400, patternUnits: "userSpaceOnUse" });
      pat.appendChild(svgEl("line", { x1: 0, y1: 700, x2: 2400, y2: 700, stroke: "#000000", "stroke-opacity": 0.11, "stroke-width": 45 }));
      pat.appendChild(svgEl("line", { x1: 0, y1: 1400, x2: 2400, y2: 1400, stroke: "#000000", "stroke-opacity": 0.11, "stroke-width": 45 }));
      pat.appendChild(svgEl("line", { x1: 600, y1: 0, x2: 600, y2: 700, stroke: "#000000", "stroke-opacity": 0.11, "stroke-width": 45 }));
      pat.appendChild(svgEl("line", { x1: 1800, y1: 700, x2: 1800, y2: 1400, stroke: "#000000", "stroke-opacity": 0.11, "stroke-width": 45 }));
      defs.appendChild(pat);
    } else if (tex === "wood") {
      const pat = svgEl("pattern", { id: patId, width: 1800, height: 4000, patternUnits: "userSpaceOnUse" });
      pat.appendChild(svgEl("line", { x1: 0, y1: 0, x2: 0, y2: 4000, stroke: "#5C4028", "stroke-opacity": 0.14, "stroke-width": 50 }));
      pat.appendChild(svgEl("line", { x1: 900, y1: 0, x2: 900, y2: 4000, stroke: "#5C4028", "stroke-opacity": 0.08, "stroke-width": 30 }));
      defs.appendChild(pat);
    }
  }

  if (wall.wall_image_sha256) {
    const imgHref = `/api/media/wall-proxy/${encodeURIComponent(wall.id)}?token=${encodeURIComponent(token)}&v=${encodeURIComponent(wall.wall_image_sha256.slice(0, 8))}`;
    if (wall.wall_image_fit === "tile") {
      const patId = `wall-img-tile-${wall.id}`;
      const pat = svgEl("pattern", { id: patId, width: 12000, height: 12000, patternUnits: "userSpaceOnUse" });
      pat.appendChild(svgEl("image", { href: imgHref, x: 0, y: 0, width: 12000, height: 12000, preserveAspectRatio: "xMidYMid slice" }));
      defs.appendChild(pat);
      wallSvg.appendChild(defs);
      wallSvg.appendChild(
        svgEl("rect", {
          x: 0,
          y: 0,
          width: w,
          height: h,
          fill: `url(#${patId})`,
          opacity: wall.wall_image_opacity ?? 1,
        }),
      );
      return;
    }
    if (defs.children.length > 0) wallSvg.appendChild(defs);
    wallSvg.appendChild(
      svgEl("image", {
        href: imgHref,
        x: 0,
        y: 0,
        width: w,
        height: h,
        preserveAspectRatio: wall.wall_image_fit === "contain" ? "xMidYMid meet" : "xMidYMid slice",
        opacity: wall.wall_image_opacity ?? 1,
      }),
    );
    return;
  }

  if (defs.children.length > 0) {
    wallSvg.appendChild(defs);
    wallSvg.appendChild(svgEl("rect", { x: 0, y: 0, width: w, height: h, fill: `url(#wall-tex-${wall.id})` }));
  }
}

  // Fondo del muro físico
  renderWallBackground(wall);

  // Zócalo / guardapolvo
  if (wall.baseboard_height_dmm > 0) {
    wallSvg.appendChild(
      svgEl("rect", {
        x: 0,
        y: toSvgY(wall.baseboard_height_dmm),
        width: wall.width_dmm,
        height: wall.baseboard_height_dmm,
        fill: "#000000",
        "fill-opacity": 0.08,
      }),
    );
  }

  // Eje visual (150 cm por defecto)
  if (state.showEyeLevel) {
    const eyeY = toSvgY(wall.eye_level_dmm);
    wallSvg.appendChild(
      svgEl("line", {
        x1: 0,
        y1: eyeY,
        x2: wall.width_dmm,
        y2: eyeY,
        stroke: "#0284C7",
        "stroke-width": unitPx * 1.4,
        "stroke-dasharray": `${unitPx * 8} ${unitPx * 5}`,
        "stroke-opacity": 0.85,
      }),
    );
    const eyeLbl = svgEl("text", {
      x: unitPx * 10,
      y: eyeY - unitPx * 6,
      fill: "#0369A1",
      "font-size": unitPx * 11,
      "font-family": "monospace",
    });
    eyeLbl.textContent = `Eje visual ${formatMetric(wall.eye_level_dmm, state.unit)}`;
    wallSvg.appendChild(eyeLbl);
  }

  // Obras colocadas
  for (const pl of wall.placements) {
    const art = artsById.get(pl.artwork_id);
    if (!art) continue;
    const [ow, oh] = outerSizeDmm(art);
    const outerTopY = toSvgY(pl.y_dmm + oh);
    const isSelected = pl.id === state.selectedPlacementId;
    const hasIssue = badPlacementIds.has(pl.id);

    const group = svgEl("g", {
      class: "artwork-node",
      tabindex: "0",
      role: "button",
      "data-placement-id": pl.id,
      "aria-label": `${art.title}, X=${formatMetric(pl.x_dmm, state.unit)}, Y=${formatMetric(pl.y_dmm, state.unit)}, ${formatMetric(ow, state.unit)} por ${formatMetric(oh, state.unit)}${hasIssue ? ", requiere atención" : ""}`,
    });

    // Sombra sutil de profundidad (HIG)
    group.appendChild(
      svgEl("rect", {
        x: pl.x_dmm + unitPx * 3,
        y: outerTopY + unitPx * 4,
        width: ow,
        height: oh,
        fill: "#000000",
        "fill-opacity": 0.22,
      }),
    );

    if (art.mounting_type === "framed" || art.mounting_type === "polyptych_part") {
      group.appendChild(
        svgEl("rect", {
          x: pl.x_dmm,
          y: outerTopY,
          width: ow,
          height: oh,
          fill: art.frame.color_hex || "#1C1C1E",
        }),
      );
      group.appendChild(
        svgEl("rect", {
          x: pl.x_dmm + art.frame.left_dmm,
          y: outerTopY + art.frame.top_dmm,
          width: Math.max(1, ow - art.frame.left_dmm - art.frame.right_dmm),
          height: Math.max(1, oh - art.frame.top_dmm - art.frame.bottom_dmm),
          fill: art.passepartout.color_hex || "#F7F6F2",
        }),
      );
    }

    const imgDx = art.mounting_type === "direct" || art.mounting_type === "canvas" ? 0 : art.frame.left_dmm + art.passepartout.left_dmm;
    const imgDyFromBottom = art.mounting_type === "direct" || art.mounting_type === "canvas" ? 0 : art.frame.bottom_dmm + art.passepartout.bottom_dmm;
    const imgTopY = toSvgY(pl.y_dmm + imgDyFromBottom + art.image_height_dmm);
    const imgX = pl.x_dmm + imgDx;

    if (art.sha256) {
      group.appendChild(
        svgEl("image", {
          href: `/api/media/proxy/${encodeURIComponent(art.id)}?token=${encodeURIComponent(token)}`,
          x: imgX,
          y: imgTopY,
          width: art.image_width_dmm,
          height: art.image_height_dmm,
          preserveAspectRatio: "none",
        }),
      );
    } else {
      group.appendChild(
        svgEl("rect", {
          x: imgX,
          y: imgTopY,
          width: art.image_width_dmm,
          height: art.image_height_dmm,
          fill: "#C4C4CA",
        }),
      );
    }

    // Borde de selección o alerta (nunca solo color: borde grueso + icono)
    if (isSelected || hasIssue) {
      group.appendChild(
        svgEl("rect", {
          x: pl.x_dmm,
          y: outerTopY,
          width: ow,
          height: oh,
          fill: "none",
          stroke: hasIssue ? "#D97706" : "#4DA3FF",
          "stroke-width": unitPx * 2.5,
          "stroke-dasharray": hasIssue ? `${unitPx * 5} ${unitPx * 3}` : "none",
        }),
      );
    }

    // Nodos de redimensión en las 4 esquinas cuando la obra está seleccionada y desbloqueada
    if (isSelected && !pl.locked) {
      const hs = unitPx * 9;
      const corners = [
        ["nw", pl.x_dmm, outerTopY],
        ["ne", pl.x_dmm + ow, outerTopY],
        ["se", pl.x_dmm + ow, outerTopY + oh],
        ["sw", pl.x_dmm, outerTopY + oh],
      ];
      for (const [cornerKey, cx, cy] of corners) {
        const handle = svgEl("rect", {
          x: cx - hs / 2,
          y: cy - hs / 2,
          width: hs,
          height: hs,
          rx: unitPx * 1.5,
          class: `resize-handle resize-handle-${cornerKey}`,
          "stroke-width": unitPx * 1.6,
          "data-resize-corner": cornerKey,
        });
        handle.addEventListener("pointerdown", (ev) => {
          ev.stopPropagation();
          startResizeHandleDrag(ev, pl.id, cornerKey);
        });
        group.appendChild(handle);
      }
    }

    group.addEventListener("pointerdown", (ev) => startPointerDrag(ev, pl.id));
    group.addEventListener("focus", () => {
      if (state.selectedPlacementId !== pl.id) {
        state.selectedPlacementId = pl.id;
        renderInspector();
        renderCanvasOverlayLabels();
      }
    });
    group.addEventListener("keydown", (ev) => handleArtworkKeydown(ev, pl.id));
    wallSvg.appendChild(group);
  }

  renderCanvasOverlayLabels();
  if (previouslyFocusedPlacementId) {
    wallSvg.querySelector(`[data-placement-id="${previouslyFocusedPlacementId}"]`)?.focus();
  }
}

function renderCanvasOverlayLabels() {
  if (!state.snapshot || !wallSvg) return;
  wallSvg.querySelectorAll(".overlay-layer").forEach((n) => n.remove());
  const wall = getActiveWall();
  if (!wall) return;

  const report = state.snapshot.reports[wall.id];
  if (!report) return;

  const basePxWidth = computeFittedWallWidthPx(wall);
  const unitPx = wall.width_dmm / Math.max(1, basePxWidth);
  const toSvgY = (yDmm) => wall.height_dmm - yDmm;

  const overlay = svgEl("g", { class: "overlay-layer", "pointer-events": "none" });

  // Guías activas de imán durante arrastre
  for (const guide of state.activeSnapGuides) {
    if (guide.axis === "x") {
      overlay.appendChild(
        svgEl("line", {
          x1: guide.coord_dmm,
          y1: 0,
          x2: guide.coord_dmm,
          y2: wall.height_dmm,
          stroke: "#30D158",
          "stroke-width": unitPx * 1.6,
          "stroke-dasharray": `${unitPx * 4} ${unitPx * 4}`,
        }),
      );
    } else {
      const gy = toSvgY(guide.coord_dmm);
      overlay.appendChild(
        svgEl("line", {
          x1: 0,
          y1: gy,
          x2: wall.width_dmm,
          y2: gy,
          stroke: "#30D158",
          "stroke-width": unitPx * 1.6,
          "stroke-dasharray": `${unitPx * 4} ${unitPx * 4}`,
        }),
      );
    }
  }

  // Cruces de anclaje
  if (state.showAnchors) {
    for (const item of report.items) {
      for (const a of item.anchors) {
        const ax = a.x_dmm;
        const ay = toSvgY(a.y_dmm);
        const r = unitPx * 5;
        overlay.appendChild(
          svgEl("circle", { cx: ax, cy: ay, r, fill: "none", stroke: "#DC2626", "stroke-width": unitPx * 1.4 }),
        );
        overlay.appendChild(
          svgEl("line", { x1: ax - r * 1.5, y1: ay, x2: ax + r * 1.5, y2: ay, stroke: "#DC2626", "stroke-width": unitPx * 1.4 }),
        );
        overlay.appendChild(
          svgEl("line", { x1: ax, y1: ay - r * 1.5, x2: ax, y2: ay + r * 1.5, stroke: "#DC2626", "stroke-width": unitPx * 1.4 }),
        );
      }
    }
  }

  // Cotas de la obra seleccionada y separaciones horizontales
  if (state.showDims) {
    const selectedItem = report.items.find((i) => i.placement_id === state.selectedPlacementId);
    if (selectedItem) {
      const r = selectedItem.outer_rect;
      const midX = r.x + r.width / 2;
      const bottomY = toSvgY(r.y);
      const floorY = toSvgY(0);
      overlay.appendChild(
        svgEl("line", { x1: midX, y1: bottomY, x2: midX, y2: floorY, stroke: "#18181B", "stroke-width": unitPx * 1.3 }),
      );
      const floorTxt = svgEl("text", {
        x: midX + unitPx * 6,
        y: (bottomY + floorY) / 2,
        fill: "#18181B",
        "font-size": unitPx * 11,
        "font-family": "monospace",
        "font-weight": "bold",
      });
      floorTxt.textContent = formatMetric(selectedItem.distance_from_floor_dmm, state.unit);
      overlay.appendChild(floorTxt);

      const leftLineY = toSvgY(r.y + r.height / 2);
      overlay.appendChild(
        svgEl("line", { x1: 0, y1: leftLineY, x2: r.x, y2: leftLineY, stroke: "#18181B", "stroke-width": unitPx * 1.3 }),
      );
      const leftTxt = svgEl("text", {
        x: r.x / 2,
        y: leftLineY - unitPx * 5,
        fill: "#18181B",
        "text-anchor": "middle",
        "font-size": unitPx * 11,
        "font-family": "monospace",
        "font-weight": "bold",
      });
      leftTxt.textContent = formatMetric(selectedItem.distance_from_left_wall_dmm, state.unit);
      overlay.appendChild(leftTxt);
    }

    for (const gap of report.horizontal_gaps) {
      const leftItem = report.items.find((i) => i.placement_id === gap.left_placement_id);
      const rightItem = report.items.find((i) => i.placement_id === gap.right_placement_id);
      if (!leftItem || !rightItem) continue;
      const x1 = leftItem.outer_rect.x + leftItem.outer_rect.width;
      const x2 = rightItem.outer_rect.x;
      const gy = toSvgY(wall.eye_level_dmm) + unitPx * 18;
      overlay.appendChild(
        svgEl("line", { x1, y1: gy, x2, y2: gy, stroke: "#3F3F46", "stroke-width": unitPx * 1.1 }),
      );
      const gTxt = svgEl("text", {
        x: (x1 + x2) / 2,
        y: gy + unitPx * 13,
        fill: "#18181B",
        "text-anchor": "middle",
        "font-size": unitPx * 10,
        "font-family": "monospace",
      });
      gTxt.textContent = formatMetric(gap.gap_dmm, state.unit);
      overlay.appendChild(gTxt);
    }
  }

  wallSvg.appendChild(overlay);
}

function renderInspector() {
  if (!state.snapshot) return;
  const wall = getActiveWall();
  if (!wall) return;

  // Tab Muro
  document.getElementById("wall-name").value = wall.name;
  document.getElementById("wall-w-cm").value = (wall.width_dmm / DMM_PER_CM).toFixed(1);
  document.getElementById("wall-h-cm").value = (wall.height_dmm / DMM_PER_CM).toFixed(1);
  document.getElementById("wall-baseboard-cm").value = (wall.baseboard_height_dmm / DMM_PER_CM).toFixed(1);
  document.getElementById("wall-eye-cm").value = (wall.eye_level_dmm / DMM_PER_CM).toFixed(1);
  document.getElementById("wall-color").value = wall.wall_color_hex || "#F4F3EF";
  const texEl = document.getElementById("wall-texture-preset");
  if (texEl) texEl.value = wall.wall_texture_preset || "none";
  const fitEl = document.getElementById("wall-image-fit");
  if (fitEl) fitEl.value = wall.wall_image_fit || "cover";
  const opEl = document.getElementById("wall-image-opacity");
  if (opEl) opEl.value = String(wall.wall_image_opacity ?? 1);
  document.getElementById("btn-wall-image-clear")?.classList.toggle("hidden", !wall.wall_image_sha256);
  const roleEl = document.getElementById("wall-narrative-role");
  if (roleEl) roleEl.value = wall.narrative_role || "standard";

  // Tab Proyector
  const cal = wall.calibration;
  document.getElementById("proj-color").value = cal.guide_color;
  document.getElementById("proj-stroke").value = String(cal.stroke_width_px);
  const showGridEl = document.getElementById("proj-show-grid");
  if (showGridEl) showGridEl.checked = Boolean(cal.show_calibration_grid);
  document.getElementById("proj-ghost").checked = cal.show_ghost_image;
  document.getElementById("proj-ghost-opacity").value = String(cal.ghost_opacity);
  document.getElementById("proj-tile-x-cm").value = String(Math.round(cal.viewport_x_dmm / DMM_PER_CM));
  document.getElementById("proj-tile-w-cm").value = String(Math.round(cal.viewport_width_dmm / DMM_PER_CM));
  renderKeystonePad(cal);
  renderKeystoneControls(cal);

  // Tab Obra
  const form = document.getElementById("artwork-form");
  const emptyMsg = document.getElementById("artwork-empty");
  const pl = wall.placements.find((p) => p.id === state.selectedPlacementId);
  const art = pl ? state.snapshot.project.artworks.find((a) => a.id === pl.artwork_id) : null;

  if (!pl || !art) {
    form.classList.add("hidden");
    emptyMsg.classList.remove("hidden");
    return;
  }

  form.classList.remove("hidden");
  emptyMsg.classList.add("hidden");

  document.getElementById("art-title").value = art.title;
  document.getElementById("art-author").value = art.author;
  document.getElementById("art-year").value = art.year;
  document.getElementById("art-medium").value = art.medium;
  document.getElementById("pl-x-cm").value = (pl.x_dmm / DMM_PER_CM).toFixed(1);
  document.getElementById("pl-y-cm").value = (pl.y_dmm / DMM_PER_CM).toFixed(1);
  document.getElementById("art-w-cm").value = (art.image_width_dmm / DMM_PER_CM).toFixed(1);
  document.getElementById("art-h-cm").value = (art.image_height_dmm / DMM_PER_CM).toFixed(1);
  document.getElementById("art-mounting").value = art.mounting_type;
  document.getElementById("framing-fields").classList.toggle(
    "hidden",
    art.mounting_type === "direct" || art.mounting_type === "canvas",
  );
  document.getElementById("frame-w-cm").value = (art.frame.left_dmm / DMM_PER_CM).toFixed(1);
  document.getElementById("frame-color").value = art.frame.color_hex;
  document.getElementById("pp-top-cm").value = (art.passepartout.top_dmm / DMM_PER_CM).toFixed(1);
  document.getElementById("pp-bottom-cm").value = (art.passepartout.bottom_dmm / DMM_PER_CM).toFixed(1);
  document.getElementById("pp-left-cm").value = (art.passepartout.left_dmm / DMM_PER_CM).toFixed(1);
  document.getElementById("pp-right-cm").value = (art.passepartout.right_dmm / DMM_PER_CM).toFixed(1);
  document.getElementById("hw-type").value = art.hardware.hanging_type;
  document.getElementById("hw-top-cm").value = (art.hardware.offset_from_top_dmm / DMM_PER_CM).toFixed(1);
  document.getElementById("hw-drop-cm").value = (art.hardware.wire_drop_dmm / DMM_PER_CM).toFixed(1);
  document.getElementById("hw-inset-cm").value = (art.hardware.lateral_inset_dmm / DMM_PER_CM).toFixed(1);
  const anchorEl = document.getElementById("art-is-anchor");
  if (anchorEl) anchorEl.checked = Boolean(art.is_anchor);
  document.getElementById("pl-locked").checked = pl.locked;

  const reportItem = state.snapshot.reports[wall.id]?.items.find((i) => i.placement_id === pl.id);
  const readout = document.getElementById("anchor-readout");
  if (reportItem && readout) {
    readout.textContent = reportItem.anchors
      .map(
        (a) =>
          `${a.label}: X=${formatMetric(a.x_dmm, state.unit)} · Y=${formatMetric(a.y_dmm, state.unit)} (↓${formatMetric(a.distance_from_top_edge_dmm, state.unit)})`,
      )
      .join("\n");
  }
}

function renderKeystonePad(cal) {
  const pad = document.getElementById("keystone-pad");
  if (!pad || !Array.isArray(cal.projector_points_norm) || cal.projector_points_norm.length !== 4) return;
  const W = 240;
  const H = 150;
  pad.replaceChildren();

  pad.appendChild(svgEl("rect", { x: 0, y: 0, width: W, height: H, fill: "var(--keystone-bg)" }));
  for (let gx = 1; gx < 4; gx++) {
    pad.appendChild(svgEl("line", { x1: (W * gx) / 4, y1: 0, x2: (W * gx) / 4, y2: H, stroke: "var(--keystone-grid)", "stroke-width": 1 }));
  }
  for (let gy = 1; gy < 4; gy++) {
    pad.appendChild(svgEl("line", { x1: 0, y1: (H * gy) / 4, x2: W, y2: (H * gy) / 4, stroke: "var(--keystone-grid)", "stroke-width": 1 }));
  }

  const pts = cal.projector_points_norm.map(([u, v]) => [u, v]);
  const toPtsAttr = (list) => list.map(([u, v]) => `${(u * W).toFixed(1)},${(v * H).toFixed(1)}`).join(" ");
  const poly = svgEl("polygon", {
    points: toPtsAttr(pts),
    fill: "var(--keystone-accent)",
    "fill-opacity": 0.14,
    stroke: "var(--keystone-accent)",
    "stroke-width": 1.6,
    "stroke-dasharray": "4 3",
  });
  pad.appendChild(poly);

  const cornerNames = ["P1", "P2", "P3", "P4"];
  const cornerDescriptions = ["Superior izquierda", "Superior derecha", "Inferior derecha", "Inferior izquierda"];
  const handles = [];
  const labels = [];

  pts.forEach(([u, v], idx) => {
    const cx = u * W;
    const cy = v * H;
    const circle = svgEl("circle", {
      cx: cx.toFixed(1),
      cy: cy.toFixed(1),
      r: 7,
      fill: "var(--keystone-bg)",
      stroke: "var(--keystone-accent)",
      "stroke-width": 2,
      class: "keystone-handle",
      "data-corner": String(idx),
      tabindex: "0",
      role: "slider",
      "aria-label": `Esquina ${cornerNames[idx]} (${cornerDescriptions[idx]})`,
      "aria-valuetext": `U ${u.toFixed(3)}, V ${v.toFixed(3)}`,
    });
    const text = svgEl("text", {
      x: (cx + (u > 0.75 ? -16 : 10)).toFixed(1),
      y: (cy + (v < 0.2 ? 14 : -8)).toFixed(1),
      fill: "var(--keystone-label)",
      "font-size": 10,
      "font-weight": 600,
    });
    text.textContent = cornerNames[idx];

    let activePointerId = null;
    circle.addEventListener("pointerdown", (ev) => {
      ev.preventDefault();
      activePointerId = ev.pointerId;
      circle.setPointerCapture(ev.pointerId);
    });
    circle.addEventListener("pointermove", (ev) => {
      if (activePointerId !== ev.pointerId) return;
      const rect = pad.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      const nu = Math.min(1, Math.max(0, (ev.clientX - rect.left) / rect.width));
      const nv = Math.min(1, Math.max(0, (ev.clientY - rect.top) / rect.height));
      pts[idx] = [nu, nv];
      poly.setAttribute("points", toPtsAttr(pts));
      circle.setAttribute("cx", (nu * W).toFixed(1));
      circle.setAttribute("cy", (nv * H).toFixed(1));
      circle.setAttribute("aria-valuetext", `U ${nu.toFixed(3)}, V ${nv.toFixed(3)}`);
      text.setAttribute("x", (nu * W + (nu > 0.75 ? -16 : 10)).toFixed(1));
      text.setAttribute("y", (nv * H + (nv < 0.2 ? 14 : -8)).toFixed(1));
    });
    circle.addEventListener("pointerup", async (ev) => {
      if (activePointerId !== ev.pointerId) return;
      activePointerId = null;
      circle.releasePointerCapture(ev.pointerId);
      const [nu, nv] = pts[idx];
      await updateKeystoneCornerPair(idx, nu, nv);
    });
    circle.addEventListener("keydown", async (ev) => {
      const step = ev.shiftKey ? 0.02 : 0.005;
      let du = 0;
      let dv = 0;
      if (ev.key === "ArrowLeft") du = -step;
      else if (ev.key === "ArrowRight") du = step;
      else if (ev.key === "ArrowUp") dv = -step;
      else if (ev.key === "ArrowDown") dv = step;
      else return;
      ev.preventDefault();
      const nu = Math.min(1, Math.max(0, u + du));
      const nv = Math.min(1, Math.max(0, v + dv));
      await updateKeystoneCornerPair(idx, nu, nv);
      document.querySelector(`#keystone-pad .keystone-handle[data-corner="${idx}"]`)?.focus();
    });

    handles.push(circle);
    labels.push(text);
    pad.append(circle, text);
  });
}

function renderKeystoneControls(cal) {
  const container = document.getElementById("keystone-controls");
  if (!container) return;
  container.replaceChildren();
  const labels = ["P1 Sup. Izq", "P2 Sup. Der", "P3 Inf. Der", "P4 Inf. Izq"];

  cal.projector_points_norm.forEach(([u, v], idx) => {
    const row = document.createElement("div");
    row.className = "keystone-row";
    const lbl = document.createElement("span");
    lbl.className = "keystone-label";
    lbl.textContent = labels[idx];
    row.appendChild(lbl);

    ["U", "V"].forEach((axis, axisIdx) => {
      const pair = document.createElement("div");
      pair.className = "nudge-pair";
      const input = document.createElement("input");
      input.type = "number";
      input.step = "0.005";
      input.min = "0";
      input.max = "1";
      input.value = (axisIdx === 0 ? u : v).toFixed(3);
      input.setAttribute("aria-label", `${labels[idx]} coordenada ${axis}`);
      input.addEventListener("change", () => updateKeystoneCorner(idx, axisIdx, Number(input.value)));
      pair.appendChild(input);
      row.appendChild(pair);
    });

    container.appendChild(row);
  });
}

async function updateKeystoneCornerPair(cornerIdx, newU, newV) {
  const wall = getActiveWall();
  if (!wall || !Number.isFinite(newU) || !Number.isFinite(newV)) return;
  pushUndoSnapshot();
  const nextProj = structuredClone(state.snapshot.project);
  const w = nextProj.walls.find((item) => item.id === wall.id);
  w.calibration.projector_points_norm[cornerIdx] = [
    Math.min(1, Math.max(0, Math.round(newU * 1000) / 1000)),
    Math.min(1, Math.max(0, Math.round(newV * 1000) / 1000)),
  ];
  await commitProject(nextProj, wall.id);
}

async function updateKeystoneCorner(cornerIdx, axisIdx, newVal) {
  const wall = getActiveWall();
  if (!wall || !Number.isFinite(newVal)) return;
  pushUndoSnapshot();
  const clamped = Math.min(1, Math.max(0, newVal));
  const nextProj = structuredClone(state.snapshot.project);
  const w = nextProj.walls.find((item) => item.id === wall.id);
  w.calibration.projector_points_norm[cornerIdx][axisIdx] = clamped;
  await commitProject(nextProj, wall.id);
}

function renderAll() {
  renderHeader();
  renderCatalog();
  renderCanvas();
  renderInspector();
}

async function removeArtworkFromCatalog(artworkId) {
  const proj = state.snapshot?.project;
  if (!proj) return;
  const art = proj.artworks.find((a) => a.id === artworkId);
  if (!art) return;
  const placedCount = proj.walls.reduce(
    (sum, w) => sum + w.placements.filter((p) => p.artwork_id === artworkId).length,
    0,
  );
  if (
    placedCount > 0 &&
    !window.confirm(`"${art.title}" está colocada en ${placedCount} muro(s). ¿Eliminarla del catálogo y de los muros?`)
  ) {
    return;
  }
  pushUndoSnapshot();
  const nextProj = structuredClone(proj);
  nextProj.artworks = nextProj.artworks.filter((a) => a.id !== artworkId);
  const removedPlIds = new Set();
  for (const w of nextProj.walls) {
    w.placements = w.placements.filter((p) => {
      if (p.artwork_id === artworkId) {
        removedPlIds.add(p.id);
        return false;
      }
      return true;
    });
  }
  if (removedPlIds.has(state.selectedPlacementId)) {
    state.selectedPlacementId = null;
  }
  await commitProject(nextProj);
  announce(`"${art.title}" eliminada del catálogo.`);
}

async function placeArtworksOnWall(artworkIds) {
  const wall = getActiveWall();
  if (!wall || !artworkIds?.length) return;
  pushUndoSnapshot();
  const nextProj = structuredClone(state.snapshot.project);
  const w = nextProj.walls.find((item) => item.id === wall.id);
  const artsById = new Map(nextProj.artworks.map((a) => [a.id, a]));
  const marginDmm = Math.min(DMM_PER_CM * 30, Math.round(w.width_dmm * 0.08));
  const gapDmm = DMM_PER_CM * 15;

  let placedCount = 0;
  let lastArtTitle = "";
  let lastNewId = null;

  for (const artworkId of artworkIds) {
    const art = artsById.get(artworkId);
    if (!art) continue;
    const [ow, oh] = outerSizeDmm(art);
    const maxX = Math.max(0, w.width_dmm - ow);

    const occupied = w.placements
      .map((pl) => {
        const pArt = artsById.get(pl.artwork_id);
        const [pow] = pArt ? outerSizeDmm(pArt) : [ow];
        return { start: pl.x_dmm, end: pl.x_dmm + pow };
      })
      .sort((a, b) => a.start - b.start);

    let chosenX = null;
    const candidates = [marginDmm, ...occupied.map((iv) => iv.end + gapDmm)].sort((a, b) => a - b);
    for (const cand of candidates) {
      if (cand > maxX) continue;
      const overlaps = occupied.some((iv) => !(cand + ow + DMM_PER_CM * 2 <= iv.start || cand >= iv.end + DMM_PER_CM * 2));
      if (!overlaps) {
        chosenX = cand;
        break;
      }
    }
    if (chosenX === null) {
      const stagger = (w.placements.length * DMM_PER_CM * 15) % Math.max(1, maxX - marginDmm + 1);
      chosenX = Math.min(maxX, marginDmm + stagger);
    }

    const nextY = Math.max(0, w.eye_level_dmm - Math.round(oh / 2));
    const newId = `pl-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 5)}`;
    w.placements.push({
      id: newId,
      artwork_id: artworkId,
      x_dmm: Math.round(chosenX),
      y_dmm: nextY,
      group_id: null,
      z_order: w.placements.length,
      locked: false,
    });
    lastNewId = newId;
    lastArtTitle = art.title;
    placedCount += 1;
  }

  if (!placedCount) return;
  state.selectedPlacementId = lastNewId;
  await commitProject(nextProj, wall.id);
  announce(placedCount === 1 ? `${lastArtTitle} colocada en ${w.name}.` : `${placedCount} obras colocadas en ${w.name}.`);
}

async function placeArtworkOnWall(artworkId) {
  return placeArtworksOnWall([artworkId]);
}

function startPointerDrag(ev, placementId) {
  if (ev.button !== 0) return;
  const wall = getActiveWall();
  if (!wall) return;
  const pl = wall.placements.find((p) => p.id === placementId);
  const art = pl ? state.snapshot.project.artworks.find((a) => a.id === pl.artwork_id) : null;
  if (!pl || !art) return;

  state.selectedPlacementId = placementId;
  renderInspector();
  renderCanvasOverlayLabels();
  if (pl.locked) return;

  const rect = wallSvg.getBoundingClientRect();
  const startClientX = ev.clientX;
  const startClientY = ev.clientY;
  const startX = pl.x_dmm;
  const startY = pl.y_dmm;
  const dmmPerPxX = wall.width_dmm / Math.max(1, rect.width);
  const dmmPerPxY = wall.height_dmm / Math.max(1, rect.height);
  let moved = false;
  let finalX = startX;
  let finalY = startY;

  const onMove = async (moveEv) => {
    const dxDmm = Math.round((moveEv.clientX - startClientX) * dmmPerPxX);
    const dyDmm = Math.round(-(moveEv.clientY - startClientY) * dmmPerPxY);
    if (Math.abs(dxDmm) > 2 || Math.abs(dyDmm) > 2) moved = true;
    const rawX = startX + dxDmm;
    const rawY = startY + dyDmm;
    try {
      const snapped = await api("/api/layout/snap", {
        method: "POST",
        body: JSON.stringify({
          wall_id: wall.id,
          artwork_id: art.id,
          placement_id: pl.id,
          x_dmm: rawX,
          y_dmm: rawY,
        }),
      });
      finalX = snapped.x_dmm;
      finalY = snapped.y_dmm;
      state.activeSnapGuides = snapped.guides || [];
    } catch {
      finalX = rawX;
      finalY = rawY;
    }
    pl.x_dmm = finalX;
    pl.y_dmm = finalY;
    renderCanvas();
  };

  const onUp = async () => {
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", onUp);
    state.activeSnapGuides = [];
    if (!moved) {
      renderCanvasOverlayLabels();
      return;
    }
    // Restaurar snapshot previo para undo antes de persistir
    const undoProj = structuredClone(state.snapshot.project);
    const undoPl = undoProj.walls.find((w) => w.id === wall.id)?.placements.find((p) => p.id === pl.id);
    if (undoPl) {
      undoPl.x_dmm = startX;
      undoPl.y_dmm = startY;
    }
    state.undoStack.push(undoProj);
    await commitProject(state.snapshot.project, wall.id);
    announce(`Movida a X=${formatMetric(finalX, state.unit)}, Y=${formatMetric(finalY, state.unit)}.`);
  };

  window.addEventListener("pointermove", onMove);
  window.addEventListener("pointerup", onUp);
}

function startResizeHandleDrag(ev, placementId, corner) {
  if (ev.button !== 0) return;
  const wall = getActiveWall();
  if (!wall) return;
  const pl = wall.placements.find((p) => p.id === placementId);
  const art = pl ? state.snapshot.project.artworks.find((a) => a.id === pl.artwork_id) : null;
  if (!pl || !art || pl.locked) return;

  const rect = wallSvg.getBoundingClientRect();
  const startClientX = ev.clientX;
  const startClientY = ev.clientY;
  const startImgW = art.image_width_dmm;
  const startImgH = art.image_height_dmm;
  const startX = pl.x_dmm;
  const startY = pl.y_dmm;
  const aspect = startImgW / Math.max(1, startImgH);
  const [startOuterW, startOuterH] = outerSizeDmm(art);
  const frameDx = startOuterW - startImgW;
  const frameDy = startOuterH - startImgH;
  const dmmPerPxX = wall.width_dmm / Math.max(1, rect.width);
  const dmmPerPxY = wall.height_dmm / Math.max(1, rect.height);
  const sx = corner.includes("w") ? -1 : 1;
  const sy = corner.includes("n") ? 1 : -1;
  let changed = false;

  const snap5mm = (v) => Math.round(v / 50) * 50;

  const onMove = (moveEv) => {
    const dxDmm = (moveEv.clientX - startClientX) * dmmPerPxX * sx;
    const dyDmm = -(moveEv.clientY - startClientY) * dmmPerPxY * sy;
    if (Math.abs(dxDmm) > 20 || Math.abs(dyDmm) > 20) changed = true;

    const maxImgW = Math.max(1000, wall.width_dmm - frameDx);
    const maxImgH = Math.max(1000, wall.height_dmm - frameDy);
    let newW = Math.max(1000, Math.min(maxImgW, snap5mm(startImgW + dxDmm)));
    let newH = Math.max(1000, Math.min(maxImgH, snap5mm(startImgH + dyDmm)));

    if (!moveEv.shiftKey) {
      if (Math.abs(dxDmm) >= Math.abs(dyDmm)) {
        newH = Math.max(1000, snap5mm(newW / aspect));
        if (newH > maxImgH) {
          newH = maxImgH;
          newW = Math.max(1000, snap5mm(newH * aspect));
        }
      } else {
        newW = Math.max(1000, snap5mm(newH * aspect));
        if (newW > maxImgW) {
          newW = maxImgW;
          newH = Math.max(1000, snap5mm(newW / aspect));
        }
      }
    }

    art.image_width_dmm = newW;
    art.image_height_dmm = newH;
    if (corner.includes("w")) {
      pl.x_dmm = Math.max(0, startX + (startImgW - newW));
    }
    if (corner.includes("s")) {
      pl.y_dmm = Math.max(0, startY + (startImgH - newH));
    }

    const wInput = document.getElementById("art-w-cm");
    const hInput = document.getElementById("art-h-cm");
    if (wInput) wInput.value = (newW / DMM_PER_CM).toFixed(1);
    if (hInput) hInput.value = (newH / DMM_PER_CM).toFixed(1);
    renderCanvas();
  };

  const onUp = async () => {
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", onUp);
    if (!changed) return;

    const undoProj = structuredClone(state.snapshot.project);
    const uPl = undoProj.walls.find((w) => w.id === wall.id)?.placements.find((p) => p.id === pl.id);
    const uArt = undoProj.artworks.find((a) => a.id === art.id);
    if (uPl) {
      uPl.x_dmm = startX;
      uPl.y_dmm = startY;
    }
    if (uArt) {
      uArt.image_width_dmm = startImgW;
      uArt.image_height_dmm = startImgH;
    }
    state.undoStack.push(undoProj);
    await commitProject(state.snapshot.project, wall.id);
    announce(
      `Tamaño ajustado a ${formatMetric(art.image_width_dmm, state.unit)} × ${formatMetric(art.image_height_dmm, state.unit)}.`,
    );
  };

  window.addEventListener("pointermove", onMove);
  window.addEventListener("pointerup", onUp);
}

async function handleArtworkKeydown(ev, placementId) {
  if (ev.altKey && (ev.key === "ArrowRight" || ev.key === "ArrowUp" || ev.key === "ArrowLeft" || ev.key === "ArrowDown")) {
    ev.preventDefault();
    const wall = getActiveWall();
    const pl = wall?.placements.find((p) => p.id === placementId);
    const art = pl ? state.snapshot.project.artworks.find((a) => a.id === pl.artwork_id) : null;
    if (!wall || !pl || !art || pl.locked) return;
    const delta = ev.key === "ArrowRight" || ev.key === "ArrowUp" ? 100 : -100;
    const aspect = art.image_width_dmm / Math.max(1, art.image_height_dmm);
    pushUndoSnapshot();
    const nextProj = structuredClone(state.snapshot.project);
    const nextArt = nextProj.artworks.find((a) => a.id === art.id);
    nextArt.image_width_dmm = Math.max(1000, Math.min(wall.width_dmm, nextArt.image_width_dmm + delta));
    nextArt.image_height_dmm = Math.max(1000, Math.min(wall.height_dmm, Math.round(nextArt.image_width_dmm / aspect)));
    await commitProject(nextProj, wall.id);
    announce(`Tamaño: ${formatMetric(nextArt.image_width_dmm, state.unit)} × ${formatMetric(nextArt.image_height_dmm, state.unit)}.`);
    return;
  }

  const step = ev.shiftKey ? 100 : 10; // 1 cm o 1 mm
  let dx = 0;
  let dy = 0;
  if (ev.key === "ArrowLeft") dx = -step;
  else if (ev.key === "ArrowRight") dx = step;
  else if (ev.key === "ArrowUp") dy = step;
  else if (ev.key === "ArrowDown") dy = -step;
  else if (ev.key === "Delete" || ev.key === "Backspace") {
    ev.preventDefault();
    await removeSelectedPlacement(placementId);
    return;
  } else {
    return;
  }

  ev.preventDefault();
  const wall = getActiveWall();
  if (!wall) return;
  const pl = wall.placements.find((p) => p.id === placementId);
  if (!pl || pl.locked) return;

  pushUndoSnapshot();
  const nextProj = structuredClone(state.snapshot.project);
  const targetPl = nextProj.walls.find((w) => w.id === wall.id).placements.find((p) => p.id === placementId);
  targetPl.x_dmm += dx;
  targetPl.y_dmm += dy;
  await commitProject(nextProj, wall.id);
  wallSvg?.querySelector(`[data-placement-id="${placementId}"]`)?.focus();
  announce(`Posición X=${formatMetric(targetPl.x_dmm, state.unit)}, Y=${formatMetric(targetPl.y_dmm, state.unit)}.`);
}

async function removeSelectedPlacement(placementId) {
  const wall = getActiveWall();
  if (!wall) return;
  pushUndoSnapshot();
  const nextProj = structuredClone(state.snapshot.project);
  const w = nextProj.walls.find((item) => item.id === wall.id);
  w.placements = w.placements.filter((p) => p.id !== placementId);
  if (state.selectedPlacementId === placementId) state.selectedPlacementId = null;
  await commitProject(nextProj, wall.id);
  announce("Obra retirada del muro.", false, { undoable: true });
}

async function addMeasuredArtwork() {
  pushUndoSnapshot();
  const nextProj = structuredClone(state.snapshot.project);
  const idx = nextProj.artworks.length + 1;
  const artId = `art-${Date.now().toString(36)}`;
  nextProj.artworks.push({
    id: artId,
    title: `Obra ${idx}`,
    author: "",
    year: "",
    medium: "Impresión pigmentada",
    source_path: "",
    sha256: "",
    image_width_dmm: 4000,
    image_height_dmm: 3000,
    mounting_type: "framed",
    frame: { top_dmm: 200, bottom_dmm: 200, left_dmm: 200, right_dmm: 200, depth_dmm: 200, color_hex: "#1C1C1E" },
    passepartout: { top_dmm: 500, bottom_dmm: 600, left_dmm: 500, right_dmm: 500, color_hex: "#F7F6F2" },
    hardware: { hanging_type: "single_center", offset_from_top_dmm: 300, wire_drop_dmm: 0, lateral_inset_dmm: 500 },
    is_anchor: false,
  });
  await commitProject(nextProj);
  await placeArtworkOnWall(artId);
}

function computeImportedSizeCm(item, preset) {
  const pxW = Math.max(1, Number(item.pixel_width) || 1000);
  const pxH = Math.max(1, Number(item.pixel_height) || 1000);
  if (preset === "dpi") {
    const dpiX = Number(item.dpi_x) || 300;
    const dpiY = Number(item.dpi_y) || dpiX;
    const w = Math.max(10, Math.min(200, Math.round((pxW / dpiX) * 2.54 * 10) / 10));
    const h = Math.max(10, Math.min(200, Math.round((pxH / dpiY) * 2.54 * 10) / 10));
    return [w, h];
  }
  const maxSideMap = { max40: 40, max50: 50, max70: 70 };
  const targetMaxCm = maxSideMap[preset] || 50;
  if (pxW >= pxH) {
    const w = targetMaxCm;
    const h = Math.max(10, Math.round(targetMaxCm * (pxH / pxW) * 10) / 10);
    return [w, h];
  }
  const h = targetMaxCm;
  const w = Math.max(10, Math.round(targetMaxCm * (pxW / pxH) * 10) / 10);
  return [w, h];
}

async function handleImportedMediaList(importedItems) {
  if (!importedItems.length) return;
  const preset = document.getElementById("import-size-preset")?.value || "max50";
  pushUndoSnapshot();
  const nextProj = structuredClone(state.snapshot.project);
  const createdIds = [];
  for (const item of importedItems) {
    const fileName = String(item.source_path || "Fotografía").split(/[/\\]/).pop().replace(/\.[^.]+$/, "");
    const [widthCm, heightCm] = computeImportedSizeCm(item, preset);
    const artId = `art-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 5)}`;
    createdIds.push(artId);
    nextProj.artworks.push({
      id: artId,
      title: fileName || "Fotografía",
      author: "",
      year: "",
      medium: "Fotografía",
      source_path: item.source_path,
      sha256: item.sha256,
      image_width_dmm: Math.round(widthCm * DMM_PER_CM),
      image_height_dmm: Math.round(heightCm * DMM_PER_CM),
      mounting_type: "framed",
      frame: { top_dmm: 200, bottom_dmm: 200, left_dmm: 200, right_dmm: 200, depth_dmm: 200, color_hex: "#1C1C1E" },
      passepartout: { top_dmm: 500, bottom_dmm: 600, left_dmm: 500, right_dmm: 500, color_hex: "#F7F6F2" },
      hardware: { hanging_type: "single_center", offset_from_top_dmm: 300, wire_drop_dmm: 0, lateral_inset_dmm: 500 },
      is_anchor: false,
    });
  }
  await commitProject(nextProj);
  await placeArtworksOnWall(createdIds);
  announce(`${importedItems.length} fotografía(s) importada(s) y colocada(s) en el muro.`);
}

async function uploadFiles(fileList) {
  if (!fileList || !fileList.length) return;
  try {
    const form = new FormData();
    for (const f of fileList) form.append("files", f);
    const res = await api("/api/media/upload", { method: "POST", body: form });
    await handleImportedMediaList(res.imported || []);
    if (res.errors?.length) announce(res.errors[0].error, true);
  } catch (err) {
    announce(`Error al importar fotografías: ${err.message}`, true);
  }
}

function bindInspectorForms() {
  const artworkForm = document.getElementById("artwork-form");
  artworkForm?.addEventListener("change", async () => {
    const wall = getActiveWall();
    const pl = wall?.placements.find((p) => p.id === state.selectedPlacementId);
    const art = pl ? state.snapshot.project.artworks.find((a) => a.id === pl.artwork_id) : null;
    if (!wall || !pl || !art) return;

    pushUndoSnapshot();
    const nextProj = structuredClone(state.snapshot.project);
    const w = nextProj.walls.find((item) => item.id === wall.id);
    const nextPl = w.placements.find((p) => p.id === pl.id);
    const nextArt = nextProj.artworks.find((a) => a.id === art.id);

    nextArt.title = document.getElementById("art-title").value.trim() || nextArt.title;
    nextArt.author = document.getElementById("art-author").value.trim();
    nextArt.year = document.getElementById("art-year").value.trim();
    nextArt.medium = document.getElementById("art-medium").value.trim();
    nextPl.x_dmm = Math.round(Number(document.getElementById("pl-x-cm").value) * DMM_PER_CM);
    nextPl.y_dmm = Math.round(Number(document.getElementById("pl-y-cm").value) * DMM_PER_CM);
    nextPl.locked = document.getElementById("pl-locked").checked;

    nextArt.image_width_dmm = Math.max(100, Math.round(Number(document.getElementById("art-w-cm").value) * DMM_PER_CM));
    nextArt.image_height_dmm = Math.max(100, Math.round(Number(document.getElementById("art-h-cm").value) * DMM_PER_CM));
    nextArt.mounting_type = document.getElementById("art-mounting").value;

    const fw = Math.max(0, Math.round(Number(document.getElementById("frame-w-cm").value) * DMM_PER_CM));
    nextArt.frame = {
      ...nextArt.frame,
      top_dmm: fw,
      bottom_dmm: fw,
      left_dmm: fw,
      right_dmm: fw,
      color_hex: document.getElementById("frame-color").value,
    };
    nextArt.passepartout = {
      ...nextArt.passepartout,
      top_dmm: Math.max(0, Math.round(Number(document.getElementById("pp-top-cm").value) * DMM_PER_CM)),
      bottom_dmm: Math.max(0, Math.round(Number(document.getElementById("pp-bottom-cm").value) * DMM_PER_CM)),
      left_dmm: Math.max(0, Math.round(Number(document.getElementById("pp-left-cm").value) * DMM_PER_CM)),
      right_dmm: Math.max(0, Math.round(Number(document.getElementById("pp-right-cm").value) * DMM_PER_CM)),
    };
    nextArt.hardware = {
      hanging_type: document.getElementById("hw-type").value,
      offset_from_top_dmm: Math.max(0, Math.round(Number(document.getElementById("hw-top-cm").value) * DMM_PER_CM)),
      wire_drop_dmm: Math.max(0, Math.round(Number(document.getElementById("hw-drop-cm").value) * DMM_PER_CM)),
      lateral_inset_dmm: Math.max(0, Math.round(Number(document.getElementById("hw-inset-cm").value) * DMM_PER_CM)),
    };
    const anchorInput = document.getElementById("art-is-anchor");
    if (anchorInput) nextArt.is_anchor = Boolean(anchorInput.checked);

    await commitProject(nextProj, wall.id);
  });

  document.getElementById("wall-form")?.addEventListener("change", async () => {
    const wall = getActiveWall();
    if (!wall) return;
    pushUndoSnapshot();
    const nextProj = structuredClone(state.snapshot.project);
    const w = nextProj.walls.find((item) => item.id === wall.id);
    w.name = document.getElementById("wall-name").value.trim() || w.name;
    w.width_dmm = Math.max(5000, Math.round(Number(document.getElementById("wall-w-cm").value) * DMM_PER_CM));
    w.height_dmm = Math.max(5000, Math.round(Number(document.getElementById("wall-h-cm").value) * DMM_PER_CM));
    w.baseboard_height_dmm = Math.max(0, Math.round(Number(document.getElementById("wall-baseboard-cm").value) * DMM_PER_CM));
    w.eye_level_dmm = Math.max(2000, Math.round(Number(document.getElementById("wall-eye-cm").value) * DMM_PER_CM));
    w.wall_color_hex = document.getElementById("wall-color").value;
    const texInput = document.getElementById("wall-texture-preset");
    if (texInput) w.wall_texture_preset = texInput.value || "none";
    const fitInput = document.getElementById("wall-image-fit");
    if (fitInput) w.wall_image_fit = fitInput.value || "cover";
    const opInput = document.getElementById("wall-image-opacity");
    if (opInput) w.wall_image_opacity = Number(opInput.value);
    const roleInput = document.getElementById("wall-narrative-role");
    if (roleInput) w.narrative_role = roleInput.value || "standard";
    await commitProject(nextProj, wall.id);
  });

  const applyWallImportedImage = async (item) => {
    const wall = getActiveWall();
    if (!wall || !item?.sha256) return;
    pushUndoSnapshot();
    const nextProj = structuredClone(state.snapshot.project);
    const w = nextProj.walls.find((itemWall) => itemWall.id === wall.id);
    w.wall_image_path = item.source_path || "";
    w.wall_image_sha256 = item.sha256;
    await commitProject(nextProj, wall.id);
    announce("Imagen de fondo asignada al muro.");
  };

  document.getElementById("btn-wall-image")?.addEventListener("click", async () => {
    if (state.capabilities.native_dialogs) {
      try {
        const res = await api("/api/native/choose-images", { method: "POST" });
        if (!res.cancelled && res.imported?.length) {
          await applyWallImportedImage(res.imported[0]);
        }
      } catch (err) {
        announce(`Error al cargar imagen de muro: ${err.message}`, true);
      }
    } else {
      document.getElementById("wall-image-input")?.click();
    }
  });

  document.getElementById("wall-image-input")?.addEventListener("change", async (ev) => {
    const file = ev.target.files?.[0];
    ev.target.value = "";
    if (!file) return;
    try {
      const form = new FormData();
      form.append("files", file);
      const res = await api("/api/media/upload", { method: "POST", body: form });
      if (res.imported?.length) {
        await applyWallImportedImage(res.imported[0]);
      } else if (res.errors?.length) {
        announce(res.errors[0].error, true);
      }
    } catch (err) {
      announce(`Error al subir imagen de muro: ${err.message}`, true);
    }
  });

  document.getElementById("btn-wall-image-clear")?.addEventListener("click", async () => {
    const wall = getActiveWall();
    if (!wall) return;
    pushUndoSnapshot();
    const nextProj = structuredClone(state.snapshot.project);
    const w = nextProj.walls.find((item) => item.id === wall.id);
    w.wall_image_path = "";
    w.wall_image_sha256 = "";
    await commitProject(nextProj, wall.id);
    announce("Imagen de muro eliminada.");
  });

  document.getElementById("projector-form")?.addEventListener("change", async () => {
    const wall = getActiveWall();
    if (!wall) return;
    pushUndoSnapshot();
    const nextProj = structuredClone(state.snapshot.project);
    const w = nextProj.walls.find((item) => item.id === wall.id);
    w.calibration.guide_color = document.getElementById("proj-color").value;
    w.calibration.stroke_width_px = Math.max(1, Number(document.getElementById("proj-stroke").value));
    const showGridEl = document.getElementById("proj-show-grid");
    if (showGridEl) w.calibration.show_calibration_grid = showGridEl.checked;
    w.calibration.show_ghost_image = document.getElementById("proj-ghost").checked;
    w.calibration.ghost_opacity = Number(document.getElementById("proj-ghost-opacity").value);
    w.calibration.viewport_x_dmm = Math.max(0, Math.round(Number(document.getElementById("proj-tile-x-cm").value) * DMM_PER_CM));
    w.calibration.viewport_width_dmm = Math.max(0, Math.round(Number(document.getElementById("proj-tile-w-cm").value) * DMM_PER_CM));
    await commitProject(nextProj, wall.id);
  });
}

function bindTabs() {
  const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
  const panels = Array.from(document.querySelectorAll('[role="tabpanel"]'));

  function activateTab(tab) {
    tabs.forEach((t) => {
      const selected = t === tab;
      t.setAttribute("aria-selected", String(selected));
      t.setAttribute("tabindex", selected ? "0" : "-1");
    });
    panels.forEach((p) => {
      p.classList.toggle("hidden", p.id !== tab.getAttribute("aria-controls"));
    });
  }

  tabs.forEach((tab, idx) => {
    tab.addEventListener("click", () => activateTab(tab));
    tab.addEventListener("keydown", (ev) => {
      if (ev.key === "ArrowRight") activateTab(tabs[(idx + 1) % tabs.length]);
      if (ev.key === "ArrowLeft") activateTab(tabs[(idx - 1 + tabs.length) % tabs.length]);
    });
  });
}

async function refreshDisplays() {
  try {
    const info = await api("/api/displays");
    state.displays = info.displays || [];
    state.projectorOpen = Boolean(info.projector?.projector_open);
    const sel = document.getElementById("proj-display-select");
    if (sel) {
      sel.replaceChildren();
      if (!state.displays.length) {
        const opt = document.createElement("option");
        opt.value = "";
        opt.textContent = "Detección nativa disponible en app desktop";
        sel.appendChild(opt);
      } else {
        for (const d of state.displays) {
          const opt = document.createElement("option");
          opt.value = String(d.index);
          opt.textContent = `${d.name} (${d.width}×${d.height})${d.is_primary ? " [Principal]" : " [Externa]"}`;
          sel.appendChild(opt);
        }
      }
    }
  } catch {
    // Modo headless
  }
}

function toggleCleanMode(forceVal) {
  state.cleanMode = typeof forceVal === "boolean" ? forceVal : !state.cleanMode;
  document.getElementById("app-shell")?.classList.toggle("clean-mode", state.cleanMode);
  document.getElementById("btn-clean-view")?.setAttribute("aria-pressed", String(state.cleanMode));
  document.getElementById("btn-exit-clean")?.classList.toggle("hidden", !state.cleanMode);
}

function bindTopbarAndCanvasEvents() {
  projectTitleInput?.addEventListener("change", async () => {
    pushUndoSnapshot();
    const nextProj = structuredClone(state.snapshot.project);
    nextProj.title = projectTitleInput.value.trim() || "Nueva Exposición";
    await commitProject(nextProj);
  });

  wallSelect?.addEventListener("change", async () => {
    state.selectedPlacementId = null;
    await commitProject(state.snapshot.project, wallSelect.value);
  });

  document.getElementById("btn-add-wall")?.addEventListener("click", async () => {
    pushUndoSnapshot();
    const nextProj = structuredClone(state.snapshot.project);
    const num = nextProj.walls.length + 1;
    const newWall = structuredClone(nextProj.walls[0]);
    newWall.id = `wall-${Date.now().toString(36)}`;
    newWall.name = `Muro ${num}`;
    newWall.placements = [];
    nextProj.walls.push(newWall);
    state.selectedPlacementId = null;
    await commitProject(nextProj, newWall.id);
    announce(`Creado ${newWall.name}.`);
  });

  document.getElementById("btn-add-measured")?.addEventListener("click", addMeasuredArtwork);

  document.getElementById("btn-place-unplaced")?.addEventListener("click", async () => {
    const proj = state.snapshot?.project;
    if (!proj) return;
    const placedIds = new Set(proj.walls.flatMap((w) => w.placements.map((p) => p.artwork_id)));
    const unplacedIds = proj.artworks.filter((a) => !placedIds.has(a.id)).map((a) => a.id);
    if (!unplacedIds.length) {
      announce("Todas las obras del catálogo ya están colocadas.");
      return;
    }
    await placeArtworksOnWall(unplacedIds);
  });

  document.getElementById("btn-import-photos")?.addEventListener("click", async () => {
    if (state.capabilities.native_dialogs) {
      try {
        const res = await api("/api/native/choose-images", { method: "POST" });
        if (res.cancelled) return;
        await handleImportedMediaList(res.imported || []);
        if (res.errors?.length) announce(res.errors[0].error, true);
      } catch (err) {
        announce(`Error al seleccionar imágenes: ${err.message}`, true);
      }
    } else {
      document.getElementById("file-upload-input")?.click();
    }
  });

  document.getElementById("file-upload-input")?.addEventListener("change", (ev) => {
    uploadFiles(ev.target.files);
    ev.target.value = "";
  });

  const dropzone = document.getElementById("catalog-dropzone");
  dropzone?.addEventListener("click", () => document.getElementById("btn-import-photos")?.click());
  dropzone?.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" || ev.key === " ") {
      ev.preventDefault();
      document.getElementById("btn-import-photos")?.click();
    }
  });
  dropzone?.addEventListener("dragover", (ev) => {
    ev.preventDefault();
    dropzone.classList.add("drag-active");
  });
  dropzone?.addEventListener("dragleave", () => dropzone.classList.remove("drag-active"));
  dropzone?.addEventListener("drop", (ev) => {
    ev.preventDefault();
    dropzone.classList.remove("drag-active");
    uploadFiles(ev.dataTransfer?.files);
  });

  document.getElementById("btn-save-project")?.addEventListener("click", async () => {
    if (state.capabilities.native_dialogs) {
      try {
        const res = await api("/api/native/save-project", {
          method: "POST",
          body: JSON.stringify({ default_name: "exposicion.layoutexpo" }),
        });
        if (res.cancelled) return;
        announce(`Proyecto guardado en ${res.path || "disco"}.`);
      } catch (err) {
        announce(`Error al guardar proyecto: ${err.message}`, true);
      }
    } else {
      const a = document.createElement("a");
      a.href = `/api/project/download?token=${encodeURIComponent(token)}`;
      a.download = "exposicion.layoutexpo";
      document.body.appendChild(a);
      a.click();
      a.remove();
      announce("Proyecto descargado como .layoutexpo.");
    }
  });

  document.getElementById("btn-open-project")?.addEventListener("click", async () => {
    if (state.capabilities.native_dialogs) {
      try {
        const res = await api("/api/native/open-project", { method: "POST" });
        if (res.cancelled) return;
        state.snapshot = res;
        state.selectedPlacementId = null;
        renderAll();
        announce("Proyecto cargado.");
      } catch (err) {
        announce(`Error al abrir proyecto: ${err.message}`, true);
      }
    } else {
      document.getElementById("project-upload-input")?.click();
    }
  });

  document.getElementById("project-upload-input")?.addEventListener("change", async (ev) => {
    const file = ev.target.files?.[0];
    ev.target.value = "";
    if (!file) return;
    try {
      const text = await file.text();
      const parsed = JSON.parse(text);
      pushUndoSnapshot();
      await commitProject(parsed, parsed.walls?.[0]?.id);
      announce("Proyecto importado.");
    } catch (err) {
      announce(`Error al leer archivo .layoutexpo: ${err.message}`, true);
    }
  });

  document.getElementById("btn-export-pdf")?.addEventListener("click", async () => {
    if (state.capabilities.native_dialogs) {
      try {
        const res = await api("/api/native/export-pdf", {
          method: "POST",
          body: JSON.stringify({ default_name: "montaje_expo.pdf" }),
        });
        if (res.cancelled) return;
        announce(`PDF técnico exportado en ${res.output_path || "disco"}.`);
      } catch (err) {
        announce(`Error al exportar PDF: ${err.message}`, true);
      }
    } else {
      const a = document.createElement("a");
      a.href = `/api/export/pdf/download?token=${encodeURIComponent(token)}`;
      a.download = "montaje_expo.pdf";
      document.body.appendChild(a);
      a.click();
      a.remove();
      announce("Descargando plano técnico en PDF.");
    }
  });

  document.getElementById("btn-undo")?.addEventListener("click", async () => {
    const prev = state.undoStack.pop();
    if (!prev) return;
    if (state.snapshot?.project) {
      state.redoStack.push(structuredClone(state.snapshot.project));
      if (state.redoStack.length > 40) state.redoStack.shift();
    }
    state.snapshot = await api("/api/project", {
      method: "PUT",
      body: JSON.stringify({ project: prev, active_wall_id: state.snapshot.active_wall_id }),
    });
    renderAll();
    announce("Cambio deshecho.");
  });

  document.getElementById("btn-redo")?.addEventListener("click", async () => {
    const next = state.redoStack.pop();
    if (!next) return;
    if (state.snapshot?.project) {
      state.undoStack.push(structuredClone(state.snapshot.project));
      if (state.undoStack.length > 40) state.undoStack.shift();
    }
    state.snapshot = await api("/api/project", {
      method: "PUT",
      body: JSON.stringify({ project: next, active_wall_id: state.snapshot.active_wall_id }),
    });
    renderAll();
    announce("Cambio rehecho.");
  });

  const fileMenu = document.getElementById("file-menu");
  fileMenu?.querySelectorAll("button").forEach((btn) => {
    btn.addEventListener("click", () => {
      fileMenu.open = false;
    });
  });
  document.addEventListener("pointerdown", (ev) => {
    if (fileMenu?.open && !fileMenu.contains(ev.target)) {
      fileMenu.open = false;
    }
  });

  document.getElementById("btn-align-eye")?.addEventListener("click", async () => {
    const wall = getActiveWall();
    if (!wall || !wall.placements.length) return;
    const ids = state.selectedPlacementId ? [state.selectedPlacementId] : wall.placements.map((p) => p.id);
    pushUndoSnapshot();
    state.snapshot = await api("/api/layout/align", {
      method: "POST",
      body: JSON.stringify({ wall_id: wall.id, placement_ids: ids, mode: "eye_level" }),
    });
    renderAll();
    announce("Obras alineadas al eje visual.");
  });

  document.getElementById("btn-distribute")?.addEventListener("click", async () => {
    const wall = getActiveWall();
    if (!wall || wall.placements.length < 2) return;
    pushUndoSnapshot();
    state.snapshot = await api("/api/layout/distribute", {
      method: "POST",
      body: JSON.stringify({ wall_id: wall.id, placement_ids: wall.placements.map((p) => p.id) }),
    });
    renderAll();
    announce("Obras distribuidas equitativamente.");
  });

  const closeCurationReport = () => {
    document.getElementById("curation-report")?.classList.add("hidden");
  };

  const renderCurationReport = (curation) => {
    const panel = document.getElementById("curation-report");
    const rationaleList = document.getElementById("curation-rationale-list");
    const warningsList = document.getElementById("curation-warnings-list");
    if (!panel || !rationaleList || !warningsList) return;

    rationaleList.innerHTML = "";
    for (const item of curation?.rationale || []) {
      const li = document.createElement("li");
      li.textContent = item;
      rationaleList.appendChild(li);
    }

    warningsList.innerHTML = "";
    const warnings = curation?.warnings || [];
    warningsList.classList.toggle("hidden", warnings.length === 0);
    for (const warn of warnings) {
      const li = document.createElement("li");
      li.textContent = warn;
      warningsList.appendChild(li);
    }

    panel.classList.remove("hidden");
  };

  document.getElementById("btn-reorganize")?.addEventListener("click", async () => {
    const wall = getActiveWall();
    if (!wall) return;
    const scope = document.getElementById("reorganize-scope")?.value || "active_wall";
    pushUndoSnapshot();
    const res = await api("/api/layout/reorganize", {
      method: "POST",
      body: JSON.stringify({ wall_id: wall.id, scope, allow_constellations: true }),
    });
    const { curation, ...snapshot } = res;
    state.snapshot = snapshot;
    renderAll();
    renderCurationReport(curation);
    announce("Reorganización armónica aplicada.");
  });

  const presetsPanel = document.getElementById("presets-panel");
  const presetsToggleBtn = document.getElementById("btn-presets-toggle");
  const closePresetsPanel = (restoreFocus = false) => {
    const wasOpen = presetsPanel && !presetsPanel.classList.contains("hidden");
    presetsPanel?.classList.add("hidden");
    presetsToggleBtn?.setAttribute("aria-expanded", "false");
    if (restoreFocus && wasOpen) presetsToggleBtn?.focus();
  };

  const shortcutsPanel = document.getElementById("shortcuts-panel");
  const shortcutsToggleBtn = document.getElementById("btn-shortcuts-toggle");
  const closeShortcutsPanel = (restoreFocus = false) => {
    const wasOpen = shortcutsPanel && !shortcutsPanel.classList.contains("hidden");
    shortcutsPanel?.classList.add("hidden");
    shortcutsToggleBtn?.setAttribute("aria-expanded", "false");
    if (restoreFocus && wasOpen) shortcutsToggleBtn?.focus();
  };

  const renderPresetsGrid = async () => {
    const grid = document.getElementById("presets-grid");
    if (!grid) return;
    try {
      const data = await api("/api/layout/presets");
      grid.replaceChildren();
      for (const preset of data.presets || []) {
        const card = document.createElement("button");
        card.type = "button";
        card.className = "preset-card";
        card.setAttribute("data-preset-id", preset.id);

        const pv = preset.preview;
        const pad = 6;
        const thumb = svgEl("svg", {
          class: "preset-thumb",
          viewBox: `${-pad} ${-pad} ${pv.width + pad * 2} ${pv.height + pad * 2}`,
          "aria-hidden": "true",
        });
        for (const r of pv.rects || []) {
          thumb.appendChild(
            svgEl("rect", {
              x: r.x,
              y: r.y,
              width: r.width,
              height: r.height,
              fill: "#FFFFFF",
              stroke: "#1C1C1E",
              "stroke-width": Math.max(1.2, pv.width * 0.018),
            }),
          );
        }

        const title = document.createElement("p");
        title.className = "preset-name";
        title.textContent = `${preset.name} · ${preset.category}`;

        const desc = document.createElement("p");
        desc.className = "preset-desc";
        desc.textContent = preset.description;

        card.append(thumb, title, desc);
        card.addEventListener("click", async () => {
          const wall = getActiveWall();
          if (!wall) return;
          const scaleFactor = Number(document.getElementById("preset-scale")?.value || "1");
          const preserveAspect = Boolean(document.getElementById("preset-preserve-aspect")?.checked ?? true);
          pushUndoSnapshot();
          try {
            const res = await api("/api/layout/apply-preset", {
              method: "POST",
              body: JSON.stringify({
                wall_id: wall.id,
                preset_id: preset.id,
                scale_factor: scaleFactor,
                preserve_aspect: preserveAspect,
                create_placeholders: true,
              }),
            });
            const { curation, ...snapshot } = res;
            state.snapshot = snapshot;
            state.selectedPlacementId = null;
            closePresetsPanel();
            renderAll();
            renderCurationReport(curation);
            announce(`Plantilla "${preset.name}" aplicada en ${wall.name}.`);
          } catch (err) {
            announce(`Error al aplicar plantilla: ${err.message}`, true);
          }
        });
        grid.appendChild(card);
      }
    } catch (err) {
      announce(`No se pudieron cargar las plantillas: ${err.message}`, true);
    }
  };

  presetsToggleBtn?.addEventListener("click", async () => {
    const isHidden = presetsPanel?.classList.contains("hidden");
    if (isHidden) {
      closeShortcutsPanel(false);
      await renderPresetsGrid();
      presetsPanel?.classList.remove("hidden");
      presetsToggleBtn.setAttribute("aria-expanded", "true");
      document.getElementById("btn-close-presets")?.focus();
    } else {
      closePresetsPanel(true);
    }
  });
  document.getElementById("btn-close-presets")?.addEventListener("click", () => closePresetsPanel(true));

  shortcutsToggleBtn?.addEventListener("click", () => {
    const isHidden = shortcutsPanel?.classList.contains("hidden");
    if (isHidden) {
      closePresetsPanel(false);
      shortcutsPanel?.classList.remove("hidden");
      shortcutsToggleBtn.setAttribute("aria-expanded", "true");
      document.getElementById("btn-close-shortcuts")?.focus();
    } else {
      closeShortcutsPanel(true);
    }
  });
  document.getElementById("btn-close-shortcuts")?.addEventListener("click", () => closeShortcutsPanel(true));

  document.getElementById("btn-close-curation")?.addEventListener("click", () => {
    closeCurationReport();
    document.getElementById("btn-reorganize")?.focus();
  });

  document.getElementById("btn-undo-curation")?.addEventListener("click", () => {
    closeCurationReport();
    document.getElementById("btn-undo")?.click();
  });

  document.getElementById("btn-clean-view")?.addEventListener("click", () => toggleCleanMode());
  document.getElementById("btn-exit-clean")?.addEventListener("click", () => toggleCleanMode(false));

  const openWebProjector = () => {
    window.open(`/projector?token=${encodeURIComponent(token)}`, "LayoutExpoProjector");
  };

  document.getElementById("btn-projector-toggle")?.addEventListener("click", async () => {
    try {
      const action = state.projectorOpen ? "close" : "open";
      const res = await api("/api/projector/window", { method: "POST", body: JSON.stringify({ action }) });
      state.projectorOpen = Boolean(res.projector_open);
      document.getElementById("btn-projector-toggle")?.setAttribute("aria-pressed", String(state.projectorOpen));
      if (state.projectorOpen) {
        const msg =
          state.displays.length <= 1
            ? "Vista previa del proyector abierta (1 pantalla detectada; conecta un proyector para pantalla completa)."
            : "Ventana de proyector abierta en pantalla secundaria.";
        announce(msg);
      } else {
        announce("Ventana de proyector cerrada.");
      }
    } catch {
      openWebProjector();
    }
  });

  document.getElementById("btn-proj-native")?.addEventListener("click", async () => {
    const selVal = document.getElementById("proj-display-select")?.value;
    const displayIdx = selVal !== "" ? Number(selVal) : null;
    try {
      const res = await api("/api/projector/window", {
        method: "POST",
        body: JSON.stringify({ action: "open", display_index: displayIdx }),
      });
      state.projectorOpen = Boolean(res.projector_open);
      document.getElementById("btn-projector-toggle")?.setAttribute("aria-pressed", String(state.projectorOpen));
      announce(
        state.displays.length <= 1
          ? "Vista previa de proyector abierta en ventana móvil (conecta un proyector para modo 1:1 en sala)."
          : "Salida 1:1 enviada al proyector seleccionado.",
      );
    } catch {
      openWebProjector();
    }
  });

  document.getElementById("btn-proj-web")?.addEventListener("click", openWebProjector);

  document.getElementById("btn-proj-reset-cal")?.addEventListener("click", async () => {
    const wall = getActiveWall();
    if (!wall) return;
    pushUndoSnapshot();
    const nextProj = structuredClone(state.snapshot.project);
    const w = nextProj.walls.find((item) => item.id === wall.id);
    w.calibration.wall_points_dmm = [
      [0, w.height_dmm],
      [w.width_dmm, w.height_dmm],
      [w.width_dmm, 0],
      [0, 0],
    ];
    w.calibration.projector_points_norm = [
      [0.1, 0.1],
      [0.9, 0.1],
      [0.9, 0.9],
      [0.1, 0.9],
    ];
    w.calibration.viewport_x_dmm = 0;
    w.calibration.viewport_width_dmm = 0;
    await commitProject(nextProj, wall.id);
    announce("Esquinas P1–P4 y tramo reiniciados al muro completo.");
  });

  document.getElementById("btn-remove-placement")?.addEventListener("click", () => {
    if (state.selectedPlacementId) removeSelectedPlacement(state.selectedPlacementId);
  });

  document.getElementById("btn-zoom-in")?.addEventListener("click", () => {
    state.zoom = Math.min(2.5, state.zoom + 0.15);
    renderCanvas();
  });
  document.getElementById("btn-zoom-out")?.addEventListener("click", () => {
    state.zoom = Math.max(0.4, state.zoom - 0.15);
    renderCanvas();
  });
  document.getElementById("btn-zoom-fit")?.addEventListener("click", () => {
    state.zoom = 1;
    renderCanvas();
  });

  document.getElementById("btn-toggle-unit")?.addEventListener("click", (ev) => {
    state.unit = state.unit === "cm" ? "mm" : "cm";
    ev.target.textContent = state.unit;
    renderAll();
  });
  document.getElementById("btn-toggle-dims")?.addEventListener("click", (ev) => {
    state.showDims = !state.showDims;
    ev.target.setAttribute("aria-pressed", String(state.showDims));
    renderCanvas();
  });
  document.getElementById("btn-toggle-anchors")?.addEventListener("click", (ev) => {
    state.showAnchors = !state.showAnchors;
    ev.target.setAttribute("aria-pressed", String(state.showAnchors));
    renderCanvas();
  });
  document.getElementById("btn-toggle-eye")?.addEventListener("click", (ev) => {
    state.showEyeLevel = !state.showEyeLevel;
    ev.target.setAttribute("aria-pressed", String(state.showEyeLevel));
    renderCanvas();
  });

  window.addEventListener("keydown", (ev) => {
    const isMod = ev.metaKey || ev.ctrlKey;
    if (ev.key === "Escape") {
      const curationWasOpen = !document.getElementById("curation-report")?.classList.contains("hidden");
      closeCurationReport();
      closePresetsPanel(true);
      closeShortcutsPanel(true);
      const fm = document.getElementById("file-menu");
      if (fm?.open) {
        fm.open = false;
        fm.querySelector("summary")?.focus();
      }
      if (curationWasOpen) document.getElementById("btn-reorganize")?.focus();
    } else if (isMod && ev.shiftKey && ev.key.toLowerCase() === "z") {
      ev.preventDefault();
      document.getElementById("btn-redo")?.click();
    } else if (ev.ctrlKey && !ev.metaKey && ev.key.toLowerCase() === "y") {
      ev.preventDefault();
      document.getElementById("btn-redo")?.click();
    } else if (isMod && ev.key.toLowerCase() === "z") {
      ev.preventDefault();
      document.getElementById("btn-undo")?.click();
    } else if (isMod && ev.key.toLowerCase() === "s") {
      ev.preventDefault();
      document.getElementById("btn-save-project")?.click();
    } else if (ev.key === "v" && !["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement?.tagName || "")) {
      toggleCleanMode();
    }
  });
}

function connectStudioEvents() {
  const es = new EventSource(`/api/projector/stream?token=${encodeURIComponent(token)}`);
  es.addEventListener("revision", async (ev) => {
    try {
      if (pendingMutations > 0) return;
      const payload = JSON.parse(ev.data);
      const currentRev = state.snapshot?.revision ?? 0;
      if (!payload || payload.revision <= currentRev) return;
      state.snapshot = await api("/api/project");
      renderAll();
    } catch {
      /* ignorar evento inválido */
    }
  });
}

async function init() {
  bindTabs();
  bindInspectorForms();
  bindTopbarAndCanvasEvents();
  try {
    state.capabilities = await api("/api/capabilities");
  } catch {
    state.capabilities = { native_dialogs: false, native_projector: false };
  }
  state.snapshot = await api("/api/project");
  renderAll();
  refreshDisplays();
  window.addEventListener("resize", () => renderCanvas());
  window.addEventListener("focus", () => {
    refreshDisplays().catch(() => {});
  });
  if (document.readyState === "complete") {
    setTimeout(connectStudioEvents, 50);
  } else {
    window.addEventListener("load", connectStudioEvents);
  }
}

init().catch((err) => announce(`Error al iniciar: ${err.message}`, true));
