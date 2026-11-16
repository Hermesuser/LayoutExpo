import { computeCssMatrix3d, formatMetric } from "/ui/shared/homography.js";

const SVG_NS = "http://www.w3.org/2000/svg";
const GUIDE_PALETTE = {
  white: "#FFFFFF",
  cyan: "#00E5FF",
  green: "#39FF14",
  amber: "#FFB300",
};

const params = new URLSearchParams(window.location.search);
const token = params.get("token") || "";

const stageEl = document.getElementById("projector-stage");
const svgEl = document.getElementById("projector-svg");
const hudEl = document.getElementById("projector-hud");
const wallNameEl = document.getElementById("hud-wall-name");
const statusEl = document.getElementById("hud-status");

let latestSnapshot = null;
let showCalibrationGrid = false;
let lastRemoteCalibrationGrid = null;
let showAnchors = true;
let showEyeLevel = true;

function el(tag, attrs = {}) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    node.setAttribute(k, String(v));
  }
  return node;
}

function renderProjector() {
  if (!latestSnapshot || !svgEl || !stageEl) return;

  const { project, reports, projections, active_wall_id: activeId } = latestSnapshot;
  const walls = project.walls || [];
  const wall = walls.find((w) => w.id === activeId) || walls[0];
  if (!wall) return;

  const report = reports[wall.id];
  const projInfo = projections[wall.id];
  const cal = wall.calibration;
  const remoteGrid = Boolean(cal.show_calibration_grid);
  if (lastRemoteCalibrationGrid !== remoteGrid) {
    showCalibrationGrid = remoteGrid;
    lastRemoteCalibrationGrid = remoteGrid;
  }
  const tile = projInfo ? projInfo.tile : { x_start_dmm: 0, x_end_dmm: wall.width_dmm, width_dmm: wall.width_dmm };

  const screenW = window.innerWidth || 1920;
  const screenH = window.innerHeight || 1080;

  // Escala base SVG en píxeles CSS proporcional al tramo activo
  const stageW = 1000;
  const stageH = stageW * (wall.height_dmm / Math.max(1, tile.width_dmm));
  stageEl.style.width = `${stageW}px`;
  stageEl.style.height = `${stageH}px`;

  // Convertir los 4 puntos del muro (dmm, origen inf-izq) a coords locales de stageEl (px, origen sup-izq)
  const dmmToStageX = (xDmm) => ((xDmm - tile.x_start_dmm) / Math.max(1, tile.width_dmm)) * stageW;
  const dmmToStageY = (yDmm) => ((wall.height_dmm - yDmm) / Math.max(1, wall.height_dmm)) * stageH;

  const srcPts = cal.wall_points_dmm.map(([wx, wy]) => [dmmToStageX(wx), dmmToStageY(wy)]);
  const dstPts = cal.projector_points_norm.map(([u, v]) => [u * screenW, v * screenH]);
  const matrix = computeCssMatrix3d(srcPts, dstPts);

  stageEl.style.transform = matrix || "none";
  svgEl.setAttribute("viewBox", `${tile.x_start_dmm} 0 ${tile.width_dmm} ${wall.height_dmm}`);
  svgEl.replaceChildren();

  const color = GUIDE_PALETTE[cal.guide_color] || GUIDE_PALETTE.cyan;
  const pxScale = Math.max(1, tile.width_dmm / stageW);
  const strokeW = (cal.stroke_width_px || 2) * pxScale;
  const toSvgY = (yDmm) => wall.height_dmm - yDmm;

  // Clip para proyectar estrictamente el tramo activo en muros largos
  const defs = el("defs");
  const clip = el("clipPath", { id: "tile-clip" });
  clip.appendChild(
    el("rect", {
      x: tile.x_start_dmm,
      y: 0,
      width: tile.width_dmm,
      height: wall.height_dmm,
    }),
  );
  defs.appendChild(clip);
  svgEl.appendChild(defs);

  const rootGroup = el("g", { "clip-path": "url(#tile-clip)" });
  svgEl.appendChild(rootGroup);

  // Contorno del tramo o muro + marca de origen (0, 0) / empalme
  rootGroup.appendChild(
    el("rect", {
      x: tile.x_start_dmm,
      y: 0,
      width: tile.width_dmm,
      height: wall.height_dmm,
      fill: "none",
      stroke: color,
      "stroke-width": strokeW * 0.7,
      "stroke-opacity": 0.45,
      "stroke-dasharray": `${strokeW * 4} ${strokeW * 4}`,
    }),
  );

  // Patrón de calibración física (4 puntos y retícula de verificación)
  if (showCalibrationGrid) {
    const [p0, p1, p2, p3] = cal.wall_points_dmm;
    const polyPts = [p0, p1, p2, p3].map(([x, y]) => `${x},${toSvgY(y)}`).join(" ");
    rootGroup.appendChild(
      el("polygon", {
        points: polyPts,
        fill: "none",
        stroke: GUIDE_PALETTE.amber,
        "stroke-width": strokeW * 1.4,
      }),
    );
    [p0, p1, p2, p3].forEach(([x, y], idx) => {
      const sy = toSvgY(y);
      const r = strokeW * 8;
      rootGroup.appendChild(
        el("circle", { cx: x, cy: sy, r, fill: "none", stroke: GUIDE_PALETTE.amber, "stroke-width": strokeW }),
      );
      const label = el("text", {
        x: x + r * 1.3,
        y: sy + strokeW * 3,
        fill: GUIDE_PALETTE.amber,
        "font-size": strokeW * 9,
        "font-family": "monospace",
      });
      label.textContent = `P${idx + 1} (${formatMetric(x)}, ${formatMetric(y)})`;
      rootGroup.appendChild(label);
    });
  }

  // Línea de eje visual / nivel de horizonte (patrón punto-raya)
  if (showEyeLevel) {
    const eyeY = toSvgY(wall.eye_level_dmm);
    rootGroup.appendChild(
      el("line", {
        x1: tile.x_start_dmm,
        y1: eyeY,
        x2: tile.x_end_dmm,
        y2: eyeY,
        stroke: color,
        "stroke-width": strokeW * 0.9,
        "stroke-dasharray": `${strokeW * 10} ${strokeW * 3} ${strokeW * 2} ${strokeW * 3}`,
        "stroke-opacity": 0.85,
      }),
    );
    const eyeLbl = el("text", {
      x: tile.x_start_dmm + strokeW * 6,
      y: eyeY - strokeW * 4,
      fill: color,
      "font-size": strokeW * 8,
      "font-family": "monospace",
    });
    eyeLbl.textContent = `EJE ${formatMetric(wall.eye_level_dmm)}`;
    rootGroup.appendChild(eyeLbl);
  }

  // Obras, ventanas de imagen y cruces de perforación
  const items = report ? report.items : [];
  items.forEach((item, index) => {
    const outer = item.outer_rect;
    const inner = item.image_rect;
    const outerTopY = toSvgY(outer.y + outer.height);
    const innerTopY = toSvgY(inner.y + inner.height);

    // Vista fantasma opcional de la fotografía para juzgar ritmo antes de perforar
    if (cal.show_ghost_image) {
      const imgNode = el("image", {
        href: `/api/media/proxy/${encodeURIComponent(item.artwork_id)}?token=${encodeURIComponent(token)}`,
        x: inner.x,
        y: innerTopY,
        width: inner.width,
        height: inner.height,
        opacity: cal.ghost_opacity ?? 0.25,
        preserveAspectRatio: "none",
      });
      rootGroup.appendChild(imgNode);
    }

    // Contorno exterior (línea continua)
    rootGroup.appendChild(
      el("rect", {
        x: outer.x,
        y: outerTopY,
        width: outer.width,
        height: outer.height,
        fill: "none",
        stroke: color,
        "stroke-width": strokeW * 1.2,
      }),
    );

    // Ventana de imagen interior si difiere del exterior (línea discontinua)
    if (inner.width !== outer.width || inner.height !== outer.height) {
      rootGroup.appendChild(
        el("rect", {
          x: inner.x,
          y: innerTopY,
          width: inner.width,
          height: inner.height,
          fill: "none",
          stroke: color,
          "stroke-width": strokeW * 0.8,
          "stroke-dasharray": `${strokeW * 5} ${strokeW * 3}`,
          "stroke-opacity": 0.8,
        }),
      );
    }

    // Etiqueta de obra en esquina superior interior
    const tag = el("text", {
      x: outer.x + strokeW * 4,
      y: outerTopY + strokeW * 11,
      fill: color,
      "font-size": strokeW * 8.5,
      "font-family": "monospace",
    });
    tag.textContent = `#${index + 1} ${item.title}`;
    rootGroup.appendChild(tag);

    // Cruces de perforación / anclaje (+ con círculo)
    if (showAnchors) {
      for (const anchor of item.anchors) {
        const ax = anchor.x_dmm;
        const ay = toSvgY(anchor.y_dmm);
        const arm = strokeW * 9;
        rootGroup.appendChild(
          el("circle", {
            cx: ax,
            cy: ay,
            r: arm * 0.55,
            fill: "none",
            stroke: GUIDE_PALETTE.amber,
            "stroke-width": strokeW * 1.1,
          }),
        );
        rootGroup.appendChild(
          el("line", {
            x1: ax - arm,
            y1: ay,
            x2: ax + arm,
            y2: ay,
            stroke: GUIDE_PALETTE.amber,
            "stroke-width": strokeW * 1.1,
          }),
        );
        rootGroup.appendChild(
          el("line", {
            x1: ax,
            y1: ay - arm,
            x2: ax,
            y2: ay + arm,
            stroke: GUIDE_PALETTE.amber,
            "stroke-width": strokeW * 1.1,
          }),
        );
        const coordText = el("text", {
          x: ax + arm * 1.1,
          y: ay - strokeW * 2,
          fill: GUIDE_PALETTE.amber,
          "font-size": strokeW * 7,
          "font-family": "monospace",
        });
        coordText.textContent = `(${formatMetric(anchor.x_dmm)}, ${formatMetric(anchor.y_dmm)})`;
        rootGroup.appendChild(coordText);
      }
    }
  });

  if (wallNameEl) {
    wallNameEl.textContent = `${wall.name} · Tramo ${formatMetric(tile.x_start_dmm)} – ${formatMetric(tile.x_end_dmm)}`;
  }
  if (statusEl) {
    statusEl.textContent = `Rev ${latestSnapshot.revision} · ${items.length} obra(s) · ${screenW}×${screenH}px`;
  }
  const hasTiling = (cal.viewport_width_dmm || 0) > 0 && cal.viewport_width_dmm < wall.width_dmm;
  document.getElementById("btn-prev-tile")?.classList.toggle("hidden", !hasTiling);
  document.getElementById("btn-next-tile")?.classList.toggle("hidden", !hasTiling);
}

async function stepProjectorTile(direction) {
  if (!latestSnapshot) return;
  const walls = latestSnapshot.project.walls || [];
  const wall = walls.find((w) => w.id === latestSnapshot.active_wall_id) || walls[0];
  if (!wall) return;
  const nextProj = structuredClone(latestSnapshot.project);
  const targetW = nextProj.walls.find((w) => w.id === wall.id);
  const stepW = targetW.calibration.viewport_width_dmm || targetW.width_dmm;
  const maxStart = Math.max(0, targetW.width_dmm - stepW);
  const nextX = Math.max(0, Math.min(maxStart, targetW.calibration.viewport_x_dmm + direction * stepW));
  targetW.calibration.viewport_x_dmm = nextX;
  const res = await fetch("/api/project", {
    method: "PUT",
    headers: { "Content-Type": "application/json", "X-LayoutExpo-Token": token },
    body: JSON.stringify({ project: nextProj, active_wall_id: wall.id }),
  });
  if (res.ok) {
    latestSnapshot = await res.json();
    renderProjector();
  }
}

async function fetchSnapshot() {
  const res = await fetch("/api/project", {
    headers: { "X-LayoutExpo-Token": token },
  });
  if (!res.ok) return;
  latestSnapshot = await res.json();
  renderProjector();
}

function connectStream() {
  const es = new EventSource(`/api/projector/stream?token=${encodeURIComponent(token)}`);
  es.addEventListener("revision", () => {
    fetchSnapshot().catch(() => {});
  });
  es.onerror = () => {
    if (statusEl) statusEl.textContent = "Reconectando...";
  };
}

document.getElementById("btn-prev-tile")?.addEventListener("click", () => {
  stepProjectorTile(-1).catch(() => {});
});

document.getElementById("btn-next-tile")?.addEventListener("click", () => {
  stepProjectorTile(1).catch(() => {});
});

document.getElementById("btn-toggle-grid")?.addEventListener("click", () => {
  showCalibrationGrid = !showCalibrationGrid;
  renderProjector();
});

document.getElementById("btn-fullscreen")?.addEventListener("click", () => {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen?.().catch(() => {});
  } else {
    document.exitFullscreen?.().catch(() => {});
  }
});

let hintTimer = null;
function toggleHudVisibility(forceShow) {
  if (!hudEl) return;
  const shouldHide = typeof forceShow === "boolean" ? !forceShow : !hudEl.classList.contains("hidden");
  hudEl.classList.toggle("hidden", shouldHide);
  const hintEl = document.getElementById("projector-hint");
  if (hintEl) {
    if (shouldHide) {
      hintEl.classList.remove("hidden");
      if (hintTimer) clearTimeout(hintTimer);
      hintTimer = setTimeout(() => hintEl.classList.add("hidden"), 2500);
    } else {
      hintEl.classList.add("hidden");
    }
  }
}

document.getElementById("btn-hide-hud")?.addEventListener("click", () => {
  toggleHudVisibility();
});

document.getElementById("btn-close-projector")?.addEventListener("click", async () => {
  try {
    await fetch("/api/projector/window", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-LayoutExpo-Token": token },
      body: JSON.stringify({ action: "close" }),
    });
  } catch {
    // Modo navegador web
  }
  window.close();
});

window.addEventListener("keydown", (ev) => {
  if (ev.key === "g" || ev.key === "G") {
    showCalibrationGrid = !showCalibrationGrid;
    renderProjector();
  } else if (ev.key === "h" || ev.key === "H") {
    toggleHudVisibility();
  } else if (ev.key === "Escape") {
    toggleHudVisibility(true);
  } else if (ev.key === "f" || ev.key === "F") {
    document.getElementById("btn-fullscreen")?.click();
  } else if (ev.key === "a" || ev.key === "A") {
    showAnchors = !showAnchors;
    renderProjector();
  } else if (ev.key === "e" || ev.key === "E") {
    showEyeLevel = !showEyeLevel;
    renderProjector();
  }
});

window.addEventListener("resize", renderProjector);

fetchSnapshot().then(connectStream).catch(() => {});
