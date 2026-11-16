/**
 * Utilidades compartidas de homografía 2D (DLT 4-puntos) y formateo métrico exacto.
 */

export const DMM_PER_MM = 10;
export const DMM_PER_CM = 100;

/**
 * Formatea una medida en dmm como texto métrico limpio (`cm` o `mm`).
 * @param {number} dmm
 * @param {"cm"|"mm"} unit
 * @returns {string}
 */
export function formatMetric(dmm, unit = "cm") {
  if (unit === "mm") {
    const val = Math.round(dmm) / DMM_PER_MM;
    return `${Number(val.toFixed(1))} mm`;
  }
  const val = Math.round(dmm) / DMM_PER_CM;
  return `${Number(val.toFixed(1))} cm`;
}

/**
 * Resuelve sistema lineal Ax = b por eliminación gaussiana con pivoteo parcial.
 * @param {number[][]} matrix
 * @param {number[]} rhs
 * @returns {number[]|null}
 */
function solveLinearSystem(matrix, rhs) {
  const n = rhs.length;
  const aug = matrix.map((row, idx) => [...row, rhs[idx]]);

  for (let col = 0; col < n; col += 1) {
    let pivotRow = col;
    for (let r = col + 1; r < n; r += 1) {
      if (Math.abs(aug[r][col]) > Math.abs(aug[pivotRow][col])) {
        pivotRow = r;
      }
    }
    if (Math.abs(aug[pivotRow][col]) < 1e-10) {
      return null;
    }
    [aug[col], aug[pivotRow]] = [aug[pivotRow], aug[col]];
    const pivotVal = aug[col][col];
    for (let j = col; j <= n; j += 1) {
      aug[col][j] /= pivotVal;
    }
    for (let r = 0; r < n; r += 1) {
      if (r === col) continue;
      const factor = aug[r][col];
      if (factor === 0) continue;
      for (let j = col; j <= n; j += 1) {
        aug[r][j] -= factor * aug[col][j];
      }
    }
  }
  return aug.map((row) => row[n]);
}

/**
 * Calcula matriz CSS `matrix3d(...)` para mapear 4 puntos locales (px) a 4 puntos destino (px).
 * @param {Array<[number, number]>} srcPoints
 * @param {Array<[number, number]>} dstPoints
 * @returns {string|null}
 */
export function computeCssMatrix3d(srcPoints, dstPoints) {
  if (srcPoints.length !== 4 || dstPoints.length !== 4) return null;
  const aRows = [];
  const bVals = [];
  for (let i = 0; i < 4; i += 1) {
    const [x, y] = srcPoints[i];
    const [u, v] = dstPoints[i];
    aRows.push([x, y, 1, 0, 0, 0, -u * x, -u * y]);
    bVals.push(u);
    aRows.push([0, 0, 0, x, y, 1, -v * x, -v * y]);
    bVals.push(v);
  }
  const h = solveLinearSystem(aRows, bVals);
  if (!h) return null;
  const [h00, h01, h02, h10, h11, h12, h20, h21] = h;
  const values = [
    h00, h10, 0, h20,
    h01, h11, 0, h21,
    0, 0, 1, 0,
    h02, h12, 0, 1,
  ];
  return `matrix3d(${values.map((v) => v.toFixed(8)).join(", ")})`;
}
