import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import "maplibre-gl/dist/maplibre-gl.css";
import { SimMap, type Bbox, type MapLayers, type MapMode } from "../map/SimMap";
import { getBuildings } from "../api";
import type { Building, CoveragePoint, DectNode, LinkMetric, NodeType } from "../types";

interface Props {
  center: [number, number];
  nodes: DectNode[];
  rolesById: Record<string, NodeType>;
  pdrById: Record<string, number | null>;
  coverage: CoveragePoint[];
  linkMetrics: LinkMetric[];
  layers: MapLayers;
  selectedId: string | null;
  selectedRoute: string[];
  offlineIds: Set<string>;
  placeMode: boolean;
  onNodeClick: (id: string) => void;
  onMapClick: (lon: number, lat: number) => void;
  onBackgroundClick: () => void;
  onNodeMove: (id: string, lon: number, lat: number) => void;
  onModeChange: (mode: MapMode) => void;
  onBearingChange: (bearing: number) => void;
}

export interface MapViewHandle {
  toggle3D: () => Promise<void>;
  flyToNode: (lon: number, lat: number) => void;
  rotateBy: (deltaDeg: number) => void;
  resetBearing: () => void;
}

async function fetchBuildingsForBbox(bbox: Bbox): Promise<Building[]> {
  const [minLon, minLat, maxLon, maxLat] = bbox;
  return getBuildings(minLat, minLon, maxLat, maxLon);
}

const MapView = forwardRef<MapViewHandle, Props>(function MapView(props, ref) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<SimMap | null>(null);
  const propsRef = useRef(props);
  propsRef.current = props;

  useImperativeHandle(ref, () => ({
    toggle3D: async () => {
      await mapRef.current?.toggle3D();
    },
    flyToNode: (lon, lat) => {
      mapRef.current?.flyToNode(lon, lat);
    },
    rotateBy: (deltaDeg) => {
      mapRef.current?.rotateBy(deltaDeg);
    },
    resetBearing: () => {
      mapRef.current?.resetBearing();
    },
  }));

  useEffect(() => {
    if (!containerRef.current) return;
    const map = new SimMap(containerRef.current, props.center, {
      onNodeClick: (id) => propsRef.current.onNodeClick(id),
      onMapClick: (lon, lat) => propsRef.current.onMapClick(lon, lat),
      onBackgroundClick: () => propsRef.current.onBackgroundClick(),
      onNodeMove: (id, lon, lat) => propsRef.current.onNodeMove(id, lon, lat),
      onModeChange: (mode) => propsRef.current.onModeChange(mode),
      onBearingChange: (bearing) => propsRef.current.onBearingChange(bearing),
      fetchBuildings: fetchBuildingsForBbox,
    });
    mapRef.current = map;
    return () => map.destroy();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const isFirstCenter = useRef(true);
  useEffect(() => {
    if (isFirstCenter.current) {
      isFirstCenter.current = false;
      return;
    }
    mapRef.current?.setView(props.center);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.center]);

  useEffect(() => {
    mapRef.current?.setCoverage(props.coverage);
  }, [props.coverage]);

  useEffect(() => {
    const byId = Object.fromEntries(props.nodes.map((n) => [n.id, n]));
    mapRef.current?.setLinks(props.linkMetrics, byId);
  }, [props.linkMetrics, props.nodes]);

  useEffect(() => {
    const byId = Object.fromEntries(props.nodes.map((n) => [n.id, n]));
    mapRef.current?.setSelectedRoute(props.selectedRoute, byId);
  }, [props.selectedRoute, props.nodes]);

  useEffect(() => {
    mapRef.current?.setLayerVisibility(props.layers);
  }, [props.layers]);

  useEffect(() => {
    mapRef.current?.setMarkers(
      props.nodes,
      props.rolesById,
      props.pdrById,
      props.selectedId,
      props.offlineIds,
      props.layers.labels,
    );
  }, [props.nodes, props.rolesById, props.pdrById, props.selectedId, props.offlineIds, props.layers.labels]);

  useEffect(() => {
    mapRef.current?.setPlaceMode(props.placeMode);
  }, [props.placeMode]);

  return <div ref={containerRef} style={{ position: "absolute", inset: 0 }} />;
});

export default MapView;
