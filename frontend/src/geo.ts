import type { Building } from "./types";

/** Ray-casting point-in-polygon test. `ring` is [[lon,lat], ...], closed. */
function pointInRing(lon: number, lat: number, ring: number[][]): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    const intersects = yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi;
    if (intersects) inside = !inside;
  }
  return inside;
}

/** Returns the first building whose footprint contains (lon, lat), if any.
 * Used to give a newly-placed node a sensible rooftop-mount default height. */
export function findBuildingAt(lon: number, lat: number, buildings: Building[]): Building | null {
  for (const b of buildings) {
    if (pointInRing(lon, lat, b.footprint)) return b;
  }
  return null;
}

export const ROOFTOP_MAST_OFFSET_M = 2.5;
