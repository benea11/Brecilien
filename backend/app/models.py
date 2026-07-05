"""Pydantic schemas shared across the API surface."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from .phy.antenna import AntennaSpec, default_omni_1900mhz

NodeType = Literal["sink", "relay", "leaf"]
Band = Literal["b1", "b2"]
LossModel = Literal["uma", "umi", "logd"]

ETSI_MAX_TX_POWER_DBM = 23.0


class Node(BaseModel):
    """A placed radio. Role (sink/relay/leaf) is derived by the simulation
    engine (see sim/roles.py) from siting and topology by default. The three
    fields below are optional manual overrides a caller can set to pin that
    behavior for a specific node -- see sim/roles.py and sim/topology.py for
    how each is honored."""

    id: str
    lon: float
    lat: float
    h: float = Field(description="Mounting height above ground level, meters")
    forced_role: Optional[Literal["sink", "relay"]] = Field(
        default=None,
        description=(
            "Manual override of sink selection: 'sink' forces this node into "
            "the (possibly multi-root) sink set; 'relay' excludes it from "
            "ever being auto-selected as a sink. Leaf is never manually "
            "assignable -- it stays a derived-only label for a node the "
            "resulting tree gives no children."
        ),
    )
    tx_power_dbm: Optional[float] = Field(
        default=None,
        description=(
            "Manual override of this node's per-hop transmit power, "
            "clamped to the ETSI 23 dBm limit. When unset, the engine's "
            "power-control step picks the value (see phy/power_control.py)."
        ),
    )
    static_parent: Optional[str] = Field(
        default=None,
        description=(
            "Manual override pinning this node's next hop to a specific "
            "node id, instead of letting the Dijkstra cluster-tree pick it. "
            "A pin that creates a cycle or targets a node with no path to "
            "any sink simply leaves the affected node(s) offline."
        ),
    )


class Params(BaseModel):
    band: Band = "b1"
    channel: str = "1657"
    mu: Literal["1", "2", "4", "8"] = "1"
    mcs: str = "1"
    max_tx_power_dbm: float = Field(
        default=ETSI_MAX_TX_POWER_DBM,
        ge=0,
        le=ETSI_MAX_TX_POWER_DBM,
        description=(
            "Power budget ceiling, not a fixed transmit power: the engine's "
            "power-control step (phy/power_control.py) picks the minimum "
            "per-link tx power that closes the link at the target BLER, "
            "capped at this value and at the ETSI hard limit of 23 dBm."
        ),
    )
    antenna: AntennaSpec = Field(default_factory=default_omni_1900mhz)
    model: LossModel = "uma"
    sigma: float = 4.0
    nf: float = 5.0
    o2i: bool = True
    payload: int = 64
    interval: float = 10.0
    duration: float = 600.0
    harq: Literal["0", "2", "4"] = "2"
    seed: int = 42
    auto_connect: bool = False


class Project(BaseModel):
    id: str
    name: str
    nodes: list[Node]
    params: Params


class LinkMetric(BaseModel):
    """Per-hop physical-layer result for one link in the routing tree."""

    child: str
    parent: str
    distance_m: float
    los: bool
    pathloss_db: float
    diffraction_loss_db: float
    o2i_loss_db: float
    shadow_db: float
    antenna_gain_db: float
    tx_power_dbm: float
    rssi_dbm: float
    sinr_db: float
    hop_pdr: float
    mean_hop_latency_ms: float
    mean_harq_rounds: float


class NodeMetric(BaseModel):
    node_id: str
    role: NodeType
    offline: bool = False
    hop: Optional[int] = None
    parent: Optional[str] = None
    rssi_dbm: Optional[float] = None
    snr_db: Optional[float] = None
    e2e_pdr: Optional[float] = None
    e2e_latency_ms: Optional[float] = None
    route: list[str] = Field(default_factory=list)


class NetworkKpi(BaseModel):
    pdr: float
    mean_latency_ms: float
    max_hops: int
    sent: int
    delivered: int
    events: int


class CoveragePoint(BaseModel):
    lat: float
    lon: float
    rssi_dbm: float


class SimResult(BaseModel):
    node_metrics: list[NodeMetric]
    link_metrics: list[LinkMetric]
    network: NetworkKpi
    coverage: list[CoveragePoint] = Field(default_factory=list)
    added_nodes: list[Node] = Field(
        default_factory=list,
        description="Reserved for future features that add physical nodes during "
        "simulation. Currently always empty -- Params.auto_connect promotes "
        "existing nodes to sink role rather than adding new ones.",
    )


class SimulateRequest(BaseModel):
    nodes: list[Node]
    params: Params
    trials_per_link: int = Field(default=4000, ge=200, le=50000)


class ReportRequest(BaseModel):
    project: Project
    result: SimResult


class Building(BaseModel):
    id: str
    height_m: float
    footprint: list[list[float]] = Field(description="[[lon, lat], ...] ring, closed")
