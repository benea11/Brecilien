import maplibregl from "maplibre-gl";
import type { FeatureCollection } from "geojson";
import type { Building, CoveragePoint, DectNode, LinkMetric, NodeType } from "../types";

const TYPE_COLOR: Record<NodeType, string> = {
  sink: "#16756c",
  relay: "#211f1a",
  leaf: "#5b574d",
};
// Role is only known once a simulation has run -- nodes placed or imported
// beforehand render in this neutral color until then.
const UNASSIGNED_COLOR = "#9a9587";

// PDR health bands -- match ResultsPanel's thresholds so the map marker
// fill and the results-table PDR figure always agree.
const PDR_GREEN = "#3d8a47";
const PDR_ORANGE = "#b3861c";
const PDR_RED = "#bb4326";

function pdrColor(pdr: number): string {
  if (pdr >= 0.9) return PDR_GREEN;
  if (pdr >= 0.7) return PDR_ORANGE;
  return PDR_RED;
}

const COVERAGE_CELL_M = 45; // must match backend sim/coverage.py GRID_CELL_M

// Free, no-API-key raster imagery -- the 2D "bird's eye" basemap. Vector
// style (below) supplies the 3D mode's streets/building outlines instead.
const SATELLITE_TILE_URL =
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";
const SATELLITE_ATTRIBUTION = "Esri, Maxar, Earthstar Geographics, and the GIS community";

const PITCH_3D = 57;
const BEARING_3D = -16;

export type MapMode = "2d" | "3d";
export type Bbox = [number, number, number, number]; // [minLon, minLat, maxLon, maxLat]

export interface MapLayers {
  buildings: boolean;
  heat: boolean;
  links: boolean;
  labels: boolean;
  satellite: boolean;
}

export interface SimMapHandlers {
  onNodeClick: (id: string) => void;
  onMapClick: (lon: number, lat: number) => void;
  onBackgroundClick: () => void;
  onNodeMove: (id: string, lon: number, lat: number) => void;
  onModeChange: (mode: MapMode) => void;
  onBearingChange: (bearing: number) => void;
  /** Fetches building footprints for on-demand 3D rendering of the current
   * viewport -- independent of the app's simulation-accuracy building
   * fetch, which stays scoped to the node bounding box. */
  fetchBuildings: (bbox: Bbox) => Promise<Building[]>;
}

function squarePolygon(lat: number, lon: number, cellM: number): number[][] {
  const dLat = cellM / 2 / 110540;
  const dLon = cellM / 2 / (111320 * Math.cos((lat * Math.PI) / 180));
  return [
    [lon - dLon, lat - dLat],
    [lon + dLon, lat - dLat],
    [lon + dLon, lat + dLat],
    [lon - dLon, lat + dLat],
    [lon - dLon, lat - dLat],
  ];
}

function bboxContains(outer: Bbox, inner: Bbox): boolean {
  return inner[0] >= outer[0] && inner[1] >= outer[1] && inner[2] <= outer[2] && inner[3] <= outer[3];
}

// Fetch a bbox well beyond what's currently visible so that panning/rotating
// a bit further doesn't immediately require another fetch.
function padBbox([minLon, minLat, maxLon, maxLat]: Bbox, factor: number): Bbox {
  const dLon = (maxLon - minLon) * factor;
  const dLat = (maxLat - minLat) * factor;
  return [minLon - dLon, minLat - dLat, maxLon + dLon, maxLat + dLat];
}

export class SimMap {
  private map: maplibregl.Map;
  private markers: maplibregl.Marker[] = [];
  private handlers: SimMapHandlers;
  private placeMode = false;
  private ready = false;
  private pendingWork: (() => void)[] = [];
  private mode: MapMode = "2d";
  private renderedBuildingsBbox: Bbox | null = null;
  private buildingsChipOn = true;
  private satelliteOn = true;
  private loading3d = false;
  // Tilting the camera itself (pitch 0 -> 57) drastically enlarges what
  // getBounds() reports -- at a steep pitch you can see much farther toward
  // the horizon -- which would otherwise immediately trip the "panned
  // outside the rendered area" check in the moveend handler below, right
  // after our *own* toggle3D() animation, with no actual panning involved.
  // Suppress exactly one moveend check after we programmatically move the
  // camera ourselves.
  private suppressNextMoveEnd = false;

  constructor(container: HTMLElement, center: [number, number], handlers: SimMapHandlers) {
    this.handlers = handlers;
    this.map = new maplibregl.Map({
      container,
      style: "https://tiles.openfreemap.org/styles/positron",
      center,
      zoom: 15.35,
      pitch: 0,
      bearing: 0,
      canvasContextAttributes: { antialias: true },
      attributionControl: { compact: true },
    });
    this.map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "bottom-right");

    this.map.on("click", (e) => {
      if (this.placeMode) {
        this.handlers.onMapClick(e.lngLat.lng, e.lngLat.lat);
      } else {
        this.handlers.onBackgroundClick();
      }
    });

    this.map.on("moveend", () => {
      if (this.suppressNextMoveEnd) {
        this.suppressNextMoveEnd = false;
        return;
      }
      if (this.mode !== "3d" || this.loading3d) return;
      const b = this.map.getBounds();
      const current: Bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()];
      if (!this.renderedBuildingsBbox || !bboxContains(this.renderedBuildingsBbox, current)) {
        // Panned/rotated past what's rendered -- fetch buildings for the new
        // view and keep going, rather than dropping the user back to 2D
        // (rotating alone can grow the reported bounds enough to trip this,
        // so free look/pan/rotate in 3D depends on this staying in 3D).
        this.refreshBuildingsFor3D(current);
      }
    });

    this.map.on("load", () => {
      // Bottom of the stack: the 2D satellite basemap. Opaque, so hiding it
      // reveals the vector style's own base layers (already loaded beneath
      // our added layers) for 3D mode.
      this.map.addSource("satellite", {
        type: "raster",
        tiles: [SATELLITE_TILE_URL],
        tileSize: 256,
        maxzoom: 19,
        attribution: SATELLITE_ATTRIBUTION,
      });
      // No `beforeId`: appends on top of the vector style's own base layers
      // (which are all that exist in the stack at this point), so the
      // opaque satellite raster fully covers them in 2D mode. Layers added
      // after this one (own-buildings, sim-heat, sim-links, sim-path) still
      // end up above the satellite layer, since each addLayer call appends
      // to the top of whatever's currently in the stack.
      this.map.addLayer({ id: "satellite", type: "raster", source: "satellite", paint: { "raster-opacity": 1 } });

      this.map.addSource("own-buildings", { type: "geojson", data: emptyFC() });
      this.map.addLayer({
        id: "own-buildings",
        type: "fill-extrusion",
        source: "own-buildings",
        minzoom: 12,
        layout: { visibility: "none" },
        paint: {
          "fill-extrusion-color": "#dedacf",
          "fill-extrusion-height": ["get", "height"],
          "fill-extrusion-base": 0,
          "fill-extrusion-opacity": 0.85,
        },
      });

      this.map.addSource("sim-heat", { type: "geojson", data: emptyFC() });
      this.map.addLayer({
        id: "sim-heat",
        type: "fill",
        source: "sim-heat",
        paint: {
          "fill-color": [
            "interpolate",
            ["linear"],
            ["get", "rssi"],
            -105,
            "#bb4326",
            -88,
            "#b3861c",
            -76,
            "#7ba33c",
            -64,
            "#3d8a47",
          ],
          "fill-opacity": 0.32,
        },
      });

      this.map.addSource("sim-links", { type: "geojson", data: emptyFC() });
      this.map.addLayer({
        id: "sim-links",
        type: "line",
        source: "sim-links",
        paint: {
          "line-color": ["step", ["get", "snr"], "#bb4326", 8, "#b3861c", 16, "#3d8a47"],
          "line-width": 2,
          "line-dasharray": [1.4, 1.1],
        },
      });

      this.map.addSource("sim-path", { type: "geojson", data: emptyFC() });
      this.map.addLayer({
        id: "sim-path",
        type: "line",
        source: "sim-path",
        paint: { "line-color": "#16756c", "line-width": 3.5 },
      });

      this.ready = true;
      this.pendingWork.forEach((fn) => fn());
      this.pendingWork = [];
    });

    // Fires for every rotation, whether from a manual rotateBy()/resetBearing()
    // call, the built-in NavigationControl compass drag, or two-finger touch
    // twist -- keeps the app's bearing readout in sync regardless of source.
    this.map.on("rotate", () => this.handlers.onBearingChange(this.map.getBearing()));
  }

  private whenReady(fn: () => void) {
    if (this.ready) fn();
    else this.pendingWork.push(fn);
  }

  /** Jumps the camera to a new project's location (instant, not animated --
   * a flyTo across a switch from e.g. Grenoble to Tokyo would just be a
   * long wait). Not used for routine node edits, only explicit project
   * load/switch/create. Always lands in 2D bird's eye, matching a fresh
   * project's default view. */
  setView(center: [number, number], zoom = 15.35) {
    this.enter2D();
    this.map.jumpTo({ center, zoom, pitch: 0, bearing: 0 });
  }

  getMode(): MapMode {
    return this.mode;
  }

  getBearing(): number {
    return this.map.getBearing();
  }

  /** Rotates by a relative amount -- works identically in 2D and 3D since
   * bearing is independent of pitch. */
  rotateBy(deltaDeg: number) {
    this.whenReady(() => {
      this.map.easeTo({ bearing: this.map.getBearing() + deltaDeg, duration: 250 });
    });
  }

  resetBearing() {
    this.whenReady(() => {
      this.map.easeTo({ bearing: 0, duration: 250 });
    });
  }

  /** Centers the camera on a node (e.g. picked from the results table)
   * without resetting pitch/bearing/zoom-out -- just close enough to read
   * off, but not so tight it feels like a hard cut if already nearby. */
  flyToNode(lon: number, lat: number) {
    this.whenReady(() => {
      this.map.flyTo({ center: [lon, lat], zoom: Math.max(this.map.getZoom(), 17), duration: 700 });
    });
  }

  private enter2D() {
    this.mode = "2d";
    this.whenReady(() => {
      this.suppressNextMoveEnd = true;
      this.map.easeTo({ pitch: 0, bearing: 0, duration: 500 });
      this.map.setLayoutProperty("satellite", "visibility", this.satelliteOn ? "visible" : "none");
      this.map.setLayoutProperty("own-buildings", "visibility", "none");
    });
    this.handlers.onModeChange("2d");
  }

  /** Fetches building footprints for the current viewport and switches to
   * the tilted 3D view. Async because of the fetch -- the caller (the "3D"
   * button) should treat this as a brief loading action. */
  async toggle3D(): Promise<void> {
    if (this.mode === "3d") {
      this.enter2D();
      return;
    }
    const b = this.map.getBounds();
    const bbox: Bbox = padBbox([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()], 0.5);
    this.loading3d = true;
    try {
      const buildings = await this.handlers.fetchBuildings(bbox);
      this.setBuildings(buildings);
      this.renderedBuildingsBbox = bbox;
      this.mode = "3d";
      this.whenReady(() => {
        this.suppressNextMoveEnd = true;
        this.map.easeTo({ pitch: PITCH_3D, bearing: BEARING_3D, duration: 500 });
        this.map.setLayoutProperty("satellite", "visibility", "none");
        this.map.setLayoutProperty("own-buildings", "visibility", this.buildingsChipOn ? "visible" : "none");
      });
      this.handlers.onModeChange("3d");
    } finally {
      this.loading3d = false;
    }
  }

  /** Re-fetches buildings for a bbox well past the current view and stays in
   * 3D. A fetch failure just leaves the previously rendered buildings in
   * place rather than kicking the user out of 3D mode. */
  private async refreshBuildingsFor3D(viewBbox: Bbox): Promise<void> {
    this.loading3d = true;
    try {
      const padded = padBbox(viewBbox, 0.5);
      const buildings = await this.handlers.fetchBuildings(padded);
      this.setBuildings(buildings);
      this.renderedBuildingsBbox = padded;
    } catch {
      // keep whatever's already rendered
    } finally {
      this.loading3d = false;
    }
  }

  setPlaceMode(mode: boolean) {
    this.placeMode = mode;
    this.map.getCanvas().style.cursor = mode ? "crosshair" : "";
  }

  setBuildings(buildings: Building[]) {
    this.whenReady(() => {
      const src = this.map.getSource("own-buildings") as maplibregl.GeoJSONSource;
      src?.setData({
        type: "FeatureCollection",
        features: buildings.map((b) => ({
          type: "Feature",
          properties: { height: b.height_m },
          geometry: { type: "Polygon", coordinates: [b.footprint] },
        })),
      });
    });
  }

  setCoverage(points: CoveragePoint[]) {
    this.whenReady(() => {
      const src = this.map.getSource("sim-heat") as maplibregl.GeoJSONSource;
      src?.setData({
        type: "FeatureCollection",
        features: points.map((p) => ({
          type: "Feature",
          properties: { rssi: p.rssi_dbm },
          geometry: { type: "Polygon", coordinates: [squarePolygon(p.lat, p.lon, COVERAGE_CELL_M)] },
        })),
      });
    });
  }

  setLinks(linkMetrics: LinkMetric[], nodesById: Record<string, DectNode>) {
    this.whenReady(() => {
      const src = this.map.getSource("sim-links") as maplibregl.GeoJSONSource;
      const features = linkMetrics
        .filter((l) => nodesById[l.child] && nodesById[l.parent])
        .map((l) => ({
          type: "Feature" as const,
          properties: { snr: l.sinr_db },
          geometry: {
            type: "LineString" as const,
            coordinates: [
              [nodesById[l.child].lon, nodesById[l.child].lat],
              [nodesById[l.parent].lon, nodesById[l.parent].lat],
            ],
          },
        }));
      src?.setData({ type: "FeatureCollection", features });
    });
  }

  setSelectedRoute(routeIds: string[], nodesById: Record<string, DectNode>) {
    this.whenReady(() => {
      const src = this.map.getSource("sim-path") as maplibregl.GeoJSONSource;
      const features = [];
      for (let i = 0; i < routeIds.length - 1; i++) {
        const a = nodesById[routeIds[i]];
        const b = nodesById[routeIds[i + 1]];
        if (!a || !b) continue;
        features.push({
          type: "Feature" as const,
          properties: {},
          geometry: { type: "LineString" as const, coordinates: [[a.lon, a.lat], [b.lon, b.lat]] },
        });
      }
      src?.setData({ type: "FeatureCollection", features });
    });
  }

  setLayerVisibility(layers: MapLayers) {
    this.buildingsChipOn = layers.buildings;
    this.satelliteOn = layers.satellite;
    this.whenReady(() => {
      this.map.setLayoutProperty(
        "own-buildings",
        "visibility",
        layers.buildings && this.mode === "3d" ? "visible" : "none",
      );
      this.map.setLayoutProperty("sim-heat", "visibility", layers.heat ? "visible" : "none");
      this.map.setLayoutProperty("sim-links", "visibility", layers.links ? "visible" : "none");
      // Satellite only applies in 2D -- 3D always shows the vector basemap
      // + extruded buildings instead, regardless of this toggle.
      if (this.mode === "2d") {
        this.map.setLayoutProperty("satellite", "visibility", layers.satellite ? "visible" : "none");
      }
    });
  }

  setMarkers(
    nodes: DectNode[],
    rolesById: Record<string, NodeType>,
    pdrById: Record<string, number | null>,
    selectedId: string | null,
    offlineIds: Set<string>,
    showLabels: boolean,
  ) {
    this.markers.forEach((m) => m.remove());
    this.markers = [];
    for (const n of nodes) {
      const role = rolesById[n.id];
      const pdr = pdrById[n.id];
      const color = pdr != null ? pdrColor(pdr) : role ? TYPE_COLOR[role] : UNASSIGNED_COLOR;
      const offline = offlineIds.has(n.id);
      const border = offline ? "#bb4326" : color;
      const isSelected = selectedId === n.id;
      const el = document.createElement("div");
      el.style.cssText = `display:flex;flex-direction:column;align-items:center;gap:2px;cursor:${isSelected ? "grab" : "pointer"};`;
      const shape = document.createElement("div");
      const ring = isSelected ? "box-shadow:0 0 0 3px rgba(22,117,108,0.35);" : "";
      if (role === "sink") {
        // The brand mast/tower glyph from TopBar's logo -- makes the sink
        // (the one node type every route ultimately depends on) instantly
        // recognizable at a glance instead of just a bigger colored square.
        shape.style.cssText = `width:24px;height:24px;border-radius:5px;background:${color};border:2px solid #fbfaf7;outline:1px solid ${border};display:flex;align-items:center;justify-content:center;${ring}`;
        shape.innerHTML =
          '<svg width="15" height="15" viewBox="0 0 16 16" fill="none">' +
          '<polygon points="8,1.5 12,7 4,7" fill="#fbfaf7" />' +
          '<polygon points="8,5 13,11.5 3,11.5" fill="#fbfaf7" />' +
          '<rect x="7" y="11.5" width="2" height="3" fill="#fbfaf7" />' +
          "</svg>";
      } else if (role === "relay") {
        shape.style.cssText = `width:13px;height:13px;background:#fbfaf7;border:2.5px solid ${border};transform:rotate(45deg);${ring}`;
      } else {
        shape.style.cssText = `width:11px;height:11px;border-radius:50%;background:#fbfaf7;border:2.5px solid ${border};${ring}`;
      }
      el.appendChild(shape);
      if (showLabels) {
        const lbl = document.createElement("div");
        lbl.textContent = n.id;
        lbl.style.cssText =
          "font:600 9.5px 'JetBrains Mono',monospace;color:#211f1a;letter-spacing:0.04em;text-shadow:0 0 3px #fbfaf7,0 0 3px #fbfaf7,0 0 3px #fbfaf7;";
        el.appendChild(lbl);
      }
      el.addEventListener("click", (ev) => {
        ev.stopPropagation();
        if (!isSelected) this.handlers.onNodeClick(n.id);
      });
      const marker = new maplibregl.Marker({ element: el, anchor: "center", draggable: isSelected })
        .setLngLat([n.lon, n.lat])
        .addTo(this.map);
      if (isSelected) {
        marker.on("dragend", () => {
          const { lng, lat } = marker.getLngLat();
          this.handlers.onNodeMove(n.id, lng, lat);
        });
      }
      this.markers.push(marker);
    }
  }

  destroy() {
    this.markers.forEach((m) => m.remove());
    this.map.remove();
  }
}

function emptyFC(): FeatureCollection {
  return { type: "FeatureCollection", features: [] };
}
