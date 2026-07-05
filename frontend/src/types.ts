export type NodeType = "sink" | "relay" | "leaf";
export type Band = "b1" | "b2";
export type LossModel = "uma" | "umi" | "logd";

/** A placed radio. Role (sink/relay/leaf) is not set here -- it is only
 * known once a simulation has run (see NodeMetric.role): the engine derives
 * it from siting and topology, so nothing is asked of the user up front. */
export interface DectNode {
  id: string;
  lon: number;
  lat: number;
  h: number;
  /** Manual override of sink selection: "sink" pins this node into the sink
   * set, "relay" excludes it from ever being auto-selected as one. Leaf is
   * never manually assignable -- see backend models.Node.forced_role. */
  forced_role?: "sink" | "relay" | null;
  /** Manual override of this node's per-hop transmit power (dBm), clamped
   * to ETSI_MAX_TX_POWER_DBM. Unset means the engine's power control picks it. */
  tx_power_dbm?: number | null;
  /** Manual override pinning this node's next hop to a specific node id
   * instead of the Dijkstra cluster-tree's pick. */
  static_parent?: string | null;
}

export interface AntennaSpec {
  gain_dbi: number;
  elevation_beamwidth_deg: number;
  front_to_back_db: number;
  cable_loss_db: number;
  polarization_loss_db: number;
}

export interface Params {
  band: Band;
  channel: string;
  mu: "1" | "2" | "4" | "8";
  mcs: string;
  max_tx_power_dbm: number;
  antenna: AntennaSpec;
  model: LossModel;
  sigma: number;
  nf: number;
  o2i: boolean;
  payload: number;
  interval: number;
  duration: number;
  harq: "0" | "2" | "4";
  seed: number;
  auto_connect: boolean;
}

export interface Project {
  id: string;
  name: string;
  nodes: DectNode[];
  params: Params;
}

export interface LinkMetric {
  child: string;
  parent: string;
  distance_m: number;
  los: boolean;
  pathloss_db: number;
  diffraction_loss_db: number;
  o2i_loss_db: number;
  shadow_db: number;
  antenna_gain_db: number;
  tx_power_dbm: number;
  rssi_dbm: number;
  sinr_db: number;
  hop_pdr: number;
  mean_hop_latency_ms: number;
  mean_harq_rounds: number;
}

export interface NodeMetric {
  node_id: string;
  role: NodeType;
  offline: boolean;
  hop: number | null;
  parent: string | null;
  rssi_dbm: number | null;
  snr_db: number | null;
  e2e_pdr: number | null;
  e2e_latency_ms: number | null;
  route: string[];
}

export interface NetworkKpi {
  pdr: number;
  mean_latency_ms: number;
  max_hops: number;
  sent: number;
  delivered: number;
  events: number;
}

export interface CoveragePoint {
  lat: number;
  lon: number;
  rssi_dbm: number;
}

export interface SimResult {
  node_metrics: NodeMetric[];
  link_metrics: LinkMetric[];
  network: NetworkKpi;
  coverage: CoveragePoint[];
  added_nodes: DectNode[];
}

export interface Building {
  id: string;
  height_m: number;
  footprint: number[][];
}

export interface GeocodeResult {
  display_name: string;
  lat: number;
  lon: number;
  country_code: string;
}

export interface MvSubstation {
  lat: number;
  lon: number;
  nom_commune: string;
}

/** Street/pole-mount height used when seeding MV substations as nodes --
 * matches the existing street-level mount convention (see main.py's
 * default project: leaves sit at 3 m). */
export const MV_SUBSTATION_DEFAULT_HEIGHT_M = 3;

export interface ProjectSummary {
  id: string;
  name: string;
}

export const ETSI_MAX_TX_POWER_DBM = 23.0;

export function defaultAntenna(): AntennaSpec {
  return {
    gain_dbi: 5.0,
    elevation_beamwidth_deg: 20.0,
    front_to_back_db: 20.0,
    cable_loss_db: 1.0,
    polarization_loss_db: 0.0,
  };
}

export function defaultParams(): Params {
  return {
    band: "b1",
    channel: "1657",
    mu: "1",
    mcs: "1",
    max_tx_power_dbm: ETSI_MAX_TX_POWER_DBM,
    antenna: defaultAntenna(),
    model: "uma",
    sigma: 4.0,
    nf: 5.0,
    o2i: true,
    payload: 64,
    interval: 10,
    duration: 600,
    harq: "2",
    seed: 42,
    auto_connect: false,
  };
}
