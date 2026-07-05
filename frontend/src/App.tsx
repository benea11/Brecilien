import type React from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import TopBar from "./components/TopBar";
import Sidebar from "./components/Sidebar";
import MapView, { type MapViewHandle } from "./components/MapView";
import ResultsPanel from "./components/ResultsPanel";
import NodeInspector from "./components/NodeInspector";
import PropagationModelInfo from "./components/PropagationModelInfo";
import { getBuildings, getMvSubstations, getProject, runSimulation, saveProject } from "./api";
import type { Building, DectNode, GeocodeResult, LinkMetric, MvSubstation, Params, Project, SimResult } from "./types";
import { defaultParams, MV_SUBSTATION_DEFAULT_HEIGHT_M } from "./types";
import { colors, mono } from "./theme";
import type { MapLayers, MapMode } from "./map/SimMap";
import { findBuildingAt, ROOFTOP_MAST_OFFSET_M } from "./geo";
import { parseNodesCsv, CSV_IMPORT_DEFAULT_HEIGHT_M } from "./csvImport";

const DEFAULT_PROJECT_ID = "grenoble-centre";
const DEFAULT_CENTER: [number, number] = [5.7262, 45.1893];
const BUILDING_PADDING_DEG = 0.004;
const MV_SUBSTATION_PADDING_DEG = 0.01; // ~1.1 km around the picked point
const TRIALS_PER_LINK = 4000;

const rotateButtonStyle: React.CSSProperties = {
  ...mono,
  width: 22,
  height: 22,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  border: "none",
  background: "transparent",
  color: colors.textMuted,
  fontSize: 13,
  borderRadius: 3,
  cursor: "pointer",
};

function slugify(name: string): string {
  const base = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40);
  return `${base || "project"}-${Math.random().toString(36).slice(2, 7)}`;
}

/** New nodes carry no role -- the simulation engine decides sink/relay/leaf
 * from siting and topology every run (see backend sim/roles.py), so
 * placement never asks for a type. Mounting on a building defaults to a
 * rooftop mast (a plausible backbone site); off-building placements get a
 * generic pole height that the engine will read as a leaf by default. */
function placementHeight(lon: number, lat: number, buildings: Building[]): number {
  const building = findBuildingAt(lon, lat, buildings);
  if (building) return Math.round((building.height_m + ROOFTOP_MAST_OFFSET_M) * 10) / 10;
  return CSV_IMPORT_DEFAULT_HEIGHT_M;
}

function nextId(nodes: DectNode[]): string {
  let n = nodes.length + 1;
  const used = new Set(nodes.map((x) => x.id));
  let id = `N-${String(n).padStart(3, "0")}`;
  while (used.has(id)) {
    n++;
    id = `N-${String(n).padStart(3, "0")}`;
  }
  return id;
}

export default function App() {
  const [projectId, setProjectId] = useState(DEFAULT_PROJECT_ID);
  const [projectName, setProjectName] = useState(DEFAULT_PROJECT_ID);
  const [nodes, setNodes] = useState<DectNode[]>([]);
  const [params, setParams] = useState<Params>(defaultParams());
  const [buildings, setBuildings] = useState<Building[]>([]);
  const [placeMode, setPlaceMode] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [layers, setLayers] = useState<MapLayers>({ buildings: true, heat: true, links: true, labels: true, satellite: true });
  const [running, setRunning] = useState(false);
  const [simPhase, setSimPhase] = useState("");
  const [stale, setStale] = useState(false);
  const [resultsOpen, setResultsOpen] = useState(true);
  const [result, setResult] = useState<SimResult | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const [mapMode, setMapMode] = useState<MapMode>("2d");
  const [mapBearing, setMapBearing] = useState(0);
  const [toggling3d, setToggling3d] = useState(false);
  const [showModelInfo, setShowModelInfo] = useState(false);
  const mapViewRef = useRef<MapViewHandle>(null);
  // The map's camera view center: set explicitly on project load/switch/
  // create, NOT recomputed reactively from `nodes` -- otherwise dragging a
  // single node would shift the centroid and yank the camera on every edit.
  const [viewCenter, setViewCenter] = useState<[number, number]>(DEFAULT_CENTER);

  function centroidOf(ns: DectNode[]): [number, number] | null {
    if (ns.length === 0) return null;
    return [ns.reduce((s, n) => s + n.lon, 0) / ns.length, ns.reduce((s, n) => s + n.lat, 0) / ns.length];
  }

  function resetTransientState() {
    setSelectedId(null);
    setResult(null);
    setStale(false);
    setRunError(null);
    setPlaceMode(false);
    setClusterFilter(null);
  }

  function loadProject(id: string) {
    getProject(id)
      .then((p: Project) => {
        setProjectId(p.id);
        setProjectName(p.name);
        setNodes(p.nodes);
        setParams(p.params);
        setViewCenter(centroidOf(p.nodes) ?? DEFAULT_CENTER);
        resetTransientState();
        setLoadError(null);
      })
      .catch((e) => setLoadError(String(e)));
  }

  /** Fetches MV substations for every French location in `locations` (non-
   * French ones are silently skipped -- Enedis is France-only), dedupes
   * against both each other and `excludeCoords` (rounded to ~1m, since
   * Enedis records carry no stable id of their own), and assigns fresh
   * "MV-NN" ids that don't collide with `existingIds`. */
  function fetchMvSubstationNodes(
    locations: GeocodeResult[],
    existingIds: Set<string>,
    excludeCoords: Set<string>,
  ): Promise<DectNode[]> {
    const frLocations = locations.filter((l) => l.country_code === "fr");
    if (frLocations.length === 0) return Promise.resolve([]);

    return Promise.all(
      frLocations.map((l) =>
        getMvSubstations(
          l.lat - MV_SUBSTATION_PADDING_DEG,
          l.lon - MV_SUBSTATION_PADDING_DEG,
          l.lat + MV_SUBSTATION_PADDING_DEG,
          l.lon + MV_SUBSTATION_PADDING_DEG,
        ).catch(() => []),
      ),
    ).then((perLocation) => {
      const seen = new Set<string>(excludeCoords);
      const merged: MvSubstation[] = [];
      for (const subs of perLocation) {
        for (const s of subs) {
          const key = `${s.lat.toFixed(5)},${s.lon.toFixed(5)}`;
          if (seen.has(key)) continue;
          seen.add(key);
          merged.push(s);
        }
      }
      const ids = new Set(existingIds);
      const mvNodes: DectNode[] = [];
      let i = 1;
      for (const s of merged) {
        let id = `MV-${String(i).padStart(2, "0")}`;
        while (ids.has(id)) {
          i++;
          id = `MV-${String(i).padStart(2, "0")}`;
        }
        ids.add(id);
        mvNodes.push({ id, lon: s.lon, lat: s.lat, h: MV_SUBSTATION_DEFAULT_HEIGHT_M });
        i++;
      }
      return mvNodes;
    });
  }

  function createProject(name: string, locations: GeocodeResult[], addMvSubstations: boolean) {
    const id = slugify(name);
    const centerLat = locations.reduce((s, l) => s + l.lat, 0) / locations.length;
    const centerLon = locations.reduce((s, l) => s + l.lon, 0) / locations.length;

    function finish(nodes: DectNode[]) {
      const newProject: Project = { id, name, nodes, params: defaultParams() };
      saveProject(newProject)
        .then(() => {
          setProjectId(id);
          setProjectName(name);
          setNodes(nodes);
          setParams(defaultParams());
          setBuildings([]);
          setViewCenter([centerLon, centerLat]);
          resetTransientState();
          setLoadError(null);
        })
        .catch((e) => setLoadError(String(e)));
    }

    if (!addMvSubstations) {
      finish([]);
      return;
    }
    fetchMvSubstationNodes(locations, new Set(), new Set()).then(finish);
  }

  function handleAddSuburbs(locations: GeocodeResult[]) {
    const existingIds = new Set(nodes.map((n) => n.id));
    const existingCoords = new Set(nodes.map((n) => `${n.lat.toFixed(5)},${n.lon.toFixed(5)}`));
    fetchMvSubstationNodes(locations, existingIds, existingCoords).then((mvNodes) => {
      if (mvNodes.length === 0) return;
      setNodes((ns) => [...ns, ...mvNodes]);
      setStale(true);
    });
  }

  useEffect(() => {
    loadProject(DEFAULT_PROJECT_ID);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (nodes.length === 0) return;
    const lats = nodes.map((n) => n.lat);
    const lons = nodes.map((n) => n.lon);
    getBuildings(
      Math.min(...lats) - BUILDING_PADDING_DEG,
      Math.min(...lons) - BUILDING_PADDING_DEG,
      Math.max(...lats) + BUILDING_PADDING_DEG,
      Math.max(...lons) + BUILDING_PADDING_DEG,
    )
      .then(setBuildings)
      .catch(() => setBuildings([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes.length === 0, projectId]);

  const nodesById = useMemo(() => Object.fromEntries(nodes.map((n) => [n.id, n])), [nodes]);
  const rolesById = useMemo(
    () => Object.fromEntries((result?.node_metrics ?? []).map((m) => [m.node_id, m.role])),
    [result],
  );
  const pdrById = useMemo(
    () => Object.fromEntries((result?.node_metrics ?? []).map((m) => [m.node_id, m.e2e_pdr])),
    [result],
  );
  const offlineIds = useMemo(
    () => new Set((result?.node_metrics ?? []).filter((m) => m.offline).map((m) => m.node_id)),
    [result],
  );

  // Auto-connect (see backend sim/autoconnect.py) can promote more than one
  // existing node to sink, producing a forest of independent cluster trees
  // rather than one mesh -- this lets the user isolate a single cluster's
  // nodes/links on the map instead of the whole (potentially confusing)
  // multi-tree overlay. `null` means "show everything".
  const [clusterFilter, setClusterFilter] = useState<string | null>(null);
  const sinkIds = useMemo(
    () => (result?.node_metrics ?? []).filter((m) => m.role === "sink").map((m) => m.node_id),
    [result],
  );
  // Every non-sink node's route ends at the sink id it's ultimately routed
  // through (see engine.py's route-building loop) -- that terminal id is
  // exactly its cluster membership.
  const clusterOfNode = useMemo(() => {
    const map: Record<string, string> = {};
    for (const m of result?.node_metrics ?? []) {
      const root = m.role === "sink" ? m.node_id : m.route[m.route.length - 1];
      if (root) map[m.node_id] = root;
    }
    return map;
  }, [result]);
  const filteredNodes = useMemo(() => {
    if (!clusterFilter) return nodes;
    return nodes.filter((n) => clusterOfNode[n.id] === clusterFilter);
  }, [nodes, clusterFilter, clusterOfNode]);
  const filteredLinkMetrics = useMemo(() => {
    const links = result?.link_metrics ?? [];
    if (!clusterFilter) return links;
    return links.filter((l) => clusterOfNode[l.child] === clusterFilter && clusterOfNode[l.parent] === clusterFilter);
  }, [result, clusterFilter, clusterOfNode]);
  const selectedMetric = result?.node_metrics.find((m) => m.node_id === selectedId);
  const selectedLinkMetric = result?.link_metrics.find((l) => l.child === selectedId);
  const selectedRoute = selectedMetric?.route ?? [];
  const selectedRouteLinks = useMemo(() => {
    const route = selectedMetric?.route ?? [];
    const links = result?.link_metrics ?? [];
    const hops: LinkMetric[] = [];
    for (let i = 0; i < route.length - 1; i++) {
      const hop = links.find((l) => l.child === route[i] && l.parent === route[i + 1]);
      if (hop) hops.push(hop);
    }
    return hops;
  }, [selectedMetric, result]);

  function handleMapClick(lon: number, lat: number) {
    if (!placeMode) return;
    const id = nextId(nodes);
    const h = placementHeight(lon, lat, buildings);
    const newNode: DectNode = { id, lon, lat, h };
    setNodes((ns) => [...ns, newNode]);
    setPlaceMode(false);
    setStale(true);
    setSelectedId(id);
  }

  function handleImportClick() {
    fileInputRef.current?.click();
  }

  function handleImportFile(file: File) {
    file
      .text()
      .then((text) => {
        const existingIds = new Set(nodes.map((n) => n.id));
        const { nodes: imported, skipped } = parseNodesCsv(text, existingIds, nodes.length + 1);
        if (imported.length === 0) {
          setImportError("No valid rows found (expected a 'Geo Point' or lat/lon column).");
          return;
        }
        setNodes((ns) => [...ns, ...imported]);
        setStale(true);
        setImportError(skipped > 0 ? `Imported ${imported.length} nodes, skipped ${skipped} row(s) without coordinates.` : null);
      })
      .catch((e) => setImportError(String(e)));
  }

  function handleNodeMove(id: string, lon: number, lat: number) {
    setNodes((ns) => ns.map((n) => (n.id === id ? { ...n, lon, lat } : n)));
    setStale(true);
  }

  function handleHeightChange(id: string, h: number) {
    setNodes((ns) => ns.map((n) => (n.id === id ? { ...n, h } : n)));
    setStale(true);
  }

  function handleForcedRoleChange(id: string, forced_role: "sink" | "relay" | null) {
    setNodes((ns) => ns.map((n) => (n.id === id ? { ...n, forced_role } : n)));
    setStale(true);
  }

  function handleTxPowerChange(id: string, tx_power_dbm: number | null) {
    setNodes((ns) => ns.map((n) => (n.id === id ? { ...n, tx_power_dbm } : n)));
    setStale(true);
  }

  function handleStaticParentChange(id: string, static_parent: string | null) {
    setNodes((ns) => ns.map((n) => (n.id === id ? { ...n, static_parent } : n)));
    setStale(true);
  }

  function handleParamsChange(p: Params) {
    setParams(p);
    setStale(true);
  }

  function handleSelectResultRow(id: string) {
    setSelectedId(id);
    const node = nodesById[id];
    if (node) mapViewRef.current?.flyToNode(node.lon, node.lat);
  }

  function handleDelete(id: string) {
    setNodes((ns) => ns.filter((n) => n.id !== id));
    setSelectedId(null);
    setStale(true);
  }

  function handleRun() {
    if (running) return;
    setRunning(true);
    setRunError(null);
    setSimPhase("Starting…");
    runSimulation(nodes, params, TRIALS_PER_LINK, {
      onProgress: (msg) => setSimPhase(msg),
      onResult: (r) => {
        // Auto-connect mode may have provisioned new backhaul sinks --
        // fold them into the project's own node list so they show up on
        // the map/sidebar and persist, not just in this run's result.
        const mergedNodes = r.added_nodes.length > 0 ? [...nodes, ...r.added_nodes] : nodes;
        if (r.added_nodes.length > 0) setNodes(mergedNodes);
        setResult(r);
        setRunning(false);
        setStale(false);
        setResultsOpen(true);
        setClusterFilter(null);
        saveProject({ id: projectId, name: projectName, nodes: mergedNodes, params }).catch(() => {});
      },
      onError: (msg) => {
        setRunError(msg);
        setRunning(false);
      },
    });
  }

  const estRun = `~${(0.8 + nodes.length * params.duration * 0.0007).toFixed(1)} s · ${nodes.length} radios · ${params.duration} s sim time`;

  const chipDefs: { key: keyof MapLayers; label: string }[] = [
    { key: "buildings", label: "3D BUILDINGS" },
    { key: "heat", label: "COVERAGE" },
    { key: "links", label: "MESH LINKS" },
    { key: "labels", label: "LABELS" },
    { key: "satellite", label: "SATELLITE" },
  ];

  return (
    <div style={{ position: "fixed", inset: 0, display: "flex", flexDirection: "column", ...mono, color: colors.text, background: colors.bg }}>
      <TopBar
        projectId={projectId}
        projectName={projectName}
        running={running}
        onRun={handleRun}
        onSwitchProject={loadProject}
        onCreateProject={createProject}
        onShowModelInfo={() => setShowModelInfo(true)}
      />
      {showModelInfo && <PropagationModelInfo onClose={() => setShowModelInfo(false)} />}
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        <Sidebar
          nodes={nodes}
          rolesById={rolesById}
          params={params}
          onParamsChange={handleParamsChange}
          placeMode={placeMode}
          onPlaceMode={setPlaceMode}
          onImportClick={handleImportClick}
          onAddSuburbs={handleAddSuburbs}
          selectedId={selectedId}
          onSelect={setSelectedId}
          estRun={estRun}
        />
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv,text/csv"
          style={{ display: "none" }}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleImportFile(file);
            e.target.value = "";
          }}
        />
        <div data-screen-label="Map" style={{ flex: 1, position: "relative", minWidth: 0, background: "#e9e7e0" }}>
          <MapView
            ref={mapViewRef}
            center={viewCenter}
            nodes={filteredNodes}
            rolesById={rolesById}
            pdrById={pdrById}
            coverage={result?.coverage ?? []}
            linkMetrics={filteredLinkMetrics}
            layers={layers}
            selectedId={selectedId}
            selectedRoute={selectedRoute}
            offlineIds={offlineIds}
            placeMode={placeMode}
            onNodeClick={setSelectedId}
            onMapClick={handleMapClick}
            onBackgroundClick={() => setSelectedId(null)}
            onNodeMove={handleNodeMove}
            onModeChange={setMapMode}
            onBearingChange={setMapBearing}
          />

          <div
            style={{
              position: "absolute",
              top: 12,
              left: 12,
              display: "flex",
              flexWrap: "wrap",
              gap: 6,
              zIndex: 5,
              maxWidth: "calc(100% - 356px)", // leave room for the results panel (330px + margins) so chips wrap instead of sliding under it
            }}
          >
            <button
              onClick={async () => {
                setToggling3d(true);
                try {
                  await mapViewRef.current?.toggle3D();
                } catch (e) {
                  console.error("Could not render 3D view:", e);
                } finally {
                  setToggling3d(false);
                }
              }}
              disabled={toggling3d}
              style={{
                height: 27,
                padding: "0 10px",
                display: "flex",
                alignItems: "center",
                gap: 6,
                border: `1px solid ${mapMode === "3d" ? colors.teal : colors.border}`,
                background: mapMode === "3d" ? colors.teal : colors.panelBg,
                color: mapMode === "3d" ? colors.panelBg : colors.textMuted,
                borderRadius: 4,
                ...mono,
                fontSize: 10.5,
                fontWeight: 600,
                letterSpacing: "0.05em",
                cursor: toggling3d ? "wait" : "pointer",
              }}
            >
              {toggling3d ? "RENDERING…" : mapMode === "3d" ? "3D · CLICK FOR 2D" : "BIRD'S EYE · CLICK FOR 3D"}
            </button>
            {chipDefs.map((c) => {
              const on = layers[c.key];
              return (
                <button
                  key={c.key}
                  onClick={() => setLayers((l) => ({ ...l, [c.key]: !l[c.key] }))}
                  style={{
                    height: 27,
                    padding: "0 10px",
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                    border: `1px solid ${on ? colors.text : colors.border}`,
                    background: on ? colors.text : colors.panelBg,
                    color: on ? colors.panelBg : colors.textMuted,
                    borderRadius: 4,
                    ...mono,
                    fontSize: 10.5,
                    fontWeight: 600,
                    letterSpacing: "0.05em",
                    cursor: "pointer",
                  }}
                >
                  <span
                    style={{
                      width: 7,
                      height: 7,
                      borderRadius: 2,
                      background: on ? colors.tealGlow : "transparent",
                      border: "1px solid currentColor",
                      display: "inline-block",
                    }}
                  />
                  {c.label}
                </button>
              );
            })}
          </div>

          <div
            style={{
              position: "absolute",
              bottom: 92,
              right: 12,
              zIndex: 5,
              display: "flex",
              alignItems: "center",
              gap: 4,
              padding: "4px 6px",
              background: colors.panelBg,
              border: `1px solid ${colors.border}`,
              borderRadius: 4,
            }}
            title="Rotate map"
          >
            <button
              onClick={() => mapViewRef.current?.rotateBy(-30)}
              style={rotateButtonStyle}
              title="Rotate left"
              aria-label="Rotate map left"
            >
              ⟲
            </button>
            <button
              onClick={() => mapViewRef.current?.resetBearing()}
              disabled={mapBearing === 0}
              style={{
                ...rotateButtonStyle,
                width: "auto",
                padding: "0 6px",
                cursor: mapBearing === 0 ? "default" : "pointer",
                color: mapBearing === 0 ? colors.textFaint : colors.textMuted,
              }}
              title="Reset to north"
              aria-label="Reset map to north"
            >
              {Math.round(((mapBearing % 360) + 360) % 360)}°
            </button>
            <button
              onClick={() => mapViewRef.current?.rotateBy(30)}
              style={rotateButtonStyle}
              title="Rotate right"
              aria-label="Rotate map right"
            >
              ⟳
            </button>
          </div>

          {placeMode && (
            <div
              style={{
                position: "absolute",
                top: 12,
                left: "50%",
                transform: "translateX(-50%)",
                zIndex: 6,
                display: "flex",
                alignItems: "center",
                gap: 10,
                padding: "6px 14px",
                background: colors.text,
                color: colors.panelBg,
                borderRadius: 4,
                ...mono,
                fontSize: 11,
                letterSpacing: "0.04em",
              }}
            >
              <span style={{ width: 7, height: 7, borderRadius: "50%", background: colors.tealGlow, display: "inline-block" }} />
              CLICK MAP TO PLACE NODE
              <button
                onClick={() => setPlaceMode(false)}
                style={{
                  marginLeft: 6,
                  background: "none",
                  border: `1px solid ${colors.textMuted}`,
                  color: "#d9d5c9",
                  borderRadius: 3,
                  ...mono,
                  fontSize: 10,
                  padding: "2px 8px",
                  cursor: "pointer",
                }}
              >
                ESC
              </button>
            </div>
          )}

          {stale && !running && (
            <div
              style={{
                position: "absolute",
                top: 48,
                left: 12,
                zIndex: 5,
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "5px 10px",
                background: colors.panelBg,
                border: `1px solid ${colors.amber}`,
                borderRadius: 4,
                ...mono,
                fontSize: 10.5,
                color: colors.amber,
                fontWeight: 600,
              }}
            >
              ⚠ CONFIG CHANGED — RESULTS STALE · RE-RUN
            </div>
          )}

          {loadError && (
            <div
              style={{
                position: "absolute",
                top: 48,
                left: 12,
                zIndex: 5,
                padding: "5px 10px",
                background: colors.panelBg,
                border: `1px solid ${colors.red}`,
                borderRadius: 4,
                ...mono,
                fontSize: 10.5,
                color: colors.red,
                fontWeight: 600,
                maxWidth: 400,
              }}
            >
              Could not reach backend API: {loadError}
            </div>
          )}

          {runError && (
            <div
              style={{
                position: "absolute",
                top: 48,
                left: 12,
                zIndex: 5,
                display: "flex",
                alignItems: "center",
                gap: 10,
                padding: "5px 10px",
                background: colors.panelBg,
                border: `1px solid ${colors.red}`,
                borderRadius: 4,
                ...mono,
                fontSize: 10.5,
                color: colors.red,
                fontWeight: 600,
                maxWidth: 460,
              }}
            >
              <span>⚠ SIMULATION FAILED: {runError}</span>
              <button
                onClick={() => setRunError(null)}
                style={{ background: "none", border: "none", color: colors.red, cursor: "pointer", fontWeight: 700 }}
              >
                ✕
              </button>
            </div>
          )}

          {importError && (
            <div
              style={{
                position: "absolute",
                top: 48,
                left: 12,
                zIndex: 5,
                display: "flex",
                alignItems: "center",
                gap: 10,
                padding: "5px 10px",
                background: colors.panelBg,
                border: `1px solid ${colors.amber}`,
                borderRadius: 4,
                ...mono,
                fontSize: 10.5,
                color: colors.amber,
                fontWeight: 600,
                maxWidth: 460,
              }}
            >
              <span>⚠ CSV IMPORT: {importError}</span>
              <button
                onClick={() => setImportError(null)}
                style={{ background: "none", border: "none", color: colors.amber, cursor: "pointer", fontWeight: 700 }}
              >
                ✕
              </button>
            </div>
          )}

          <ResultsPanel
            project={{ id: projectId, name: projectName, nodes, params }}
            result={result}
            open={resultsOpen}
            onToggle={() => setResultsOpen((o) => !o)}
            selectedId={selectedId}
            onSelectRow={handleSelectResultRow}
            seed={params.seed}
            sinkIds={sinkIds}
            clusterFilter={clusterFilter}
            onClusterFilterChange={setClusterFilter}
          />

          {selectedId && nodesById[selectedId] && (
            <NodeInspector
              node={nodesById[selectedId]}
              nodes={nodes}
              role={rolesById[selectedId]}
              metric={selectedMetric}
              linkMetric={selectedLinkMetric}
              routeLinks={selectedRouteLinks}
              onClear={() => setSelectedId(null)}
              onDelete={() => handleDelete(selectedId)}
              onHeightChange={(h) => handleHeightChange(selectedId, h)}
              onForcedRoleChange={(role) => handleForcedRoleChange(selectedId, role)}
              onTxPowerChange={(dbm) => handleTxPowerChange(selectedId, dbm)}
              onStaticParentChange={(parentId) => handleStaticParentChange(selectedId, parentId)}
            />
          )}

          {layers.heat && (
            <div
              style={{
                position: "absolute",
                bottom: 34,
                left: "50%",
                transform: "translateX(-50%)",
                zIndex: 5,
                display: "flex",
                alignItems: "center",
                gap: 10,
                padding: "6px 12px",
                background: colors.panelBg,
                border: `1px solid ${colors.border}`,
                borderRadius: 4,
              }}
            >
              <span style={{ ...mono, fontSize: 9.5, letterSpacing: "0.08em", color: colors.textFaint }}>RSSI dBm</span>
              <div
                style={{
                  width: 140,
                  height: 8,
                  borderRadius: 2,
                  background: `linear-gradient(90deg, ${colors.red}, ${colors.amber}, #7ba33c, ${colors.green})`,
                  border: `1px solid ${colors.divider}`,
                }}
              />
              <div style={{ display: "flex", gap: 26, ...mono, fontSize: 9.5, color: colors.textMuted }}>
                <span>-105</span>
                <span>-88</span>
                <span>-64</span>
              </div>
            </div>
          )}

          {running && (
            <div style={{ position: "absolute", inset: 0, zIndex: 10, background: "rgba(242,241,237,0.55)", display: "grid", placeItems: "center" }}>
              <div style={{ width: 360, background: colors.panelBg, border: `1px solid ${colors.border}`, borderRadius: 6, padding: 16, boxShadow: "0 4px 14px rgba(33,31,26,0.13)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
                  <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", color: colors.text }}>RUNNING DECT NR+ SIMULATION</span>
                  <span style={{ ...mono, fontSize: 10.5, color: colors.textFaint }}>Monte Carlo</span>
                </div>
                <div style={{ position: "relative", height: 6, background: "#e9e7e0", overflow: "hidden", borderRadius: 3, marginBottom: 8 }}>
                  <div
                    style={{
                      position: "absolute",
                      top: 0,
                      bottom: 0,
                      width: "35%",
                      background: colors.teal,
                      animation: "simbar 1.1s linear infinite",
                      left: "-35%",
                    }}
                  />
                </div>
                <div style={{ ...mono, fontSize: 10.5, color: colors.textMuted }}>{simPhase}</div>
              </div>
            </div>
          )}
        </div>
      </div>
      <style>{`@keyframes simbar { 0% { left:-35%; } 100% { left:100%; } }`}</style>
    </div>
  );
}
