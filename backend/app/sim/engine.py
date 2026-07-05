"""Simulation orchestrator: builds the routing tree, then for every hop in
that tree solves per-link transmit power and runs a Monte Carlo of
frequency-selective-fading + BLER + IR-HARQ trials to get a converged hop
PDR and latency, and finally composes those hop results analytically across
each leaf's route to the sink (product of hop PDRs, sum of hop latencies).
See the plan's "Simulation scope" note: this is deliberately *not* a
discrete-event MAC/contention simulator.
"""
from __future__ import annotations

import hashlib
import zlib
from collections import OrderedDict
from dataclasses import dataclass
from math import floor
from typing import Callable, Optional

import numpy as np

from .. import osm
from ..geo import LocalFrame, horizontal_distance_m
from ..harq.incremental_redundancy import simulate_harq_batch
from ..linklevel.bler_curves import build_bler_curve
from ..models import (
    ETSI_MAX_TX_POWER_DBM,
    Building,
    CoveragePoint,
    LinkMetric,
    NetworkKpi,
    Node,
    NodeMetric,
    NodeType,
    Params,
    SimResult,
)
from ..phy.channels import carrier_frequency_hz
from ..phy.mcs_table import get_mcs
from ..phy.noise import noise_floor_dbm
from ..phy.numerology import get_numerology
from ..phy.power_control import solve_tx_power
from ..phy.tbs import HEADER_BYTES, data_subcarriers, packet_timing
from ..propagation.building_index import BuildingIndex, build_index
from ..propagation.shadow_field import ShadowField, build_shadow_field
from .autoconnect import ensure_connectivity
from .coverage import GRID_PADDING_M, compute_coverage_grid
from .roles import derive_roles, select_sink
from .topology import TreeEntry, build_tree

ProgressCb = Optional[Callable[[str], None]]

BUILDING_QUERY_PADDING_M = 400.0
HARQ_FEEDBACK_ROUNDTRIP_SLOTS = 8.0

# Cluster-tree formation is the one genuinely expensive step at large node
# counts (see sim/topology.py's module docstring) -- it's also the one step
# whose result depends on *none* of the PHY/MAC params (MCS, HARQ rounds,
# trials-per-link, tx power ceiling...), only on node siting and the large-
# scale RF model. So re-running a simulation after only changing one of
# those doesn't need to pay for it again. This is a small in-memory,
# per-process cache -- it resets on backend restart, which is fine for a
# planning tool.
_TOPOLOGY_CACHE_MAX = 8


@dataclass
class _TopologyBundle:
    buildings: list[Building]
    building_index: BuildingIndex
    extent_m: float
    shadow_field: ShadowField
    tree: dict[str, TreeEntry]
    roles: dict[str, NodeType]
    coverage: list[CoveragePoint]
    # The node list actually used to build the above -- identical to the
    # input `nodes` unless Params.auto_connect provisioned extra backhaul
    # sinks, in which case it's longer. Cached so a cache *hit* reports the
    # same auto-provisioned sinks as the run that first computed them.
    nodes: list[Node]


_topology_cache: "OrderedDict[str, _TopologyBundle]" = OrderedDict()


def _topology_cache_key(nodes: list[Node], params: Params) -> str:
    """Cluster-tree selection now depends on estimated per-hop PDR (see
    sim/topology.py's module docstring for why), which needs power control
    and the BLER curve -- so unlike a pure large-scale-loss tree, changing
    MCS, the numerology (mu, via bandwidth/noise floor), payload size, or
    the tx power ceiling can genuinely change which tree is optimal, and
    must invalidate the cache. HARQ rounds and trials-per-link don't affect
    the ranking proxy (it's a single-round, average-SINR estimate), so a
    simulation re-run that only changes those still hits the cache. Per-node
    forced_role/static_parent are included in node_sig for the same reason
    (they change sink selection / tree shape); tx_power_dbm is deliberately
    excluded -- it only affects the per-hop Monte Carlo section below,
    which is never cached."""
    node_sig = tuple(
        sorted(
            (n.id, round(n.lat, 7), round(n.lon, 7), round(n.h, 3), n.forced_role, n.static_parent)
            for n in nodes
        )
    )
    antenna = params.antenna
    key_data = (
        node_sig,
        params.band,
        params.channel,
        params.model,
        round(params.sigma, 6),
        params.o2i,
        params.seed,
        params.mu,
        params.mcs,
        params.payload,
        params.auto_connect,
        round(params.max_tx_power_dbm, 6),
        round(params.nf, 6),
        antenna.gain_dbi,
        antenna.elevation_beamwidth_deg,
        antenna.front_to_back_db,
        antenna.cable_loss_db,
        antenna.polarization_loss_db,
    )
    return hashlib.sha256(repr(key_data).encode()).hexdigest()


def _bbox_with_padding(nodes: list[Node], padding_m: float) -> tuple[float, float, float, float]:
    lats = [n.lat for n in nodes]
    lons = [n.lon for n in nodes]
    lat0, lon0 = sum(lats) / len(lats), sum(lons) / len(lons)
    frame = LocalFrame(lat0, lon0)
    xs, ys = [], []
    for n in nodes:
        x, y = frame.to_xy(n.lat, n.lon)
        xs.append(x)
        ys.append(y)
    min_x, max_x = min(xs) - padding_m, max(xs) + padding_m
    min_y, max_y = min(ys) - padding_m, max(ys) + padding_m
    lat_a, lon_a = frame.from_xy(min_x, min_y)
    lat_b, lon_b = frame.from_xy(max_x, max_y)
    return min(lat_a, lat_b), min(lon_a, lon_b), max(lat_a, lat_b), max(lon_a, lon_b)


def _extent_m(nodes: list[Node], frame: LocalFrame) -> float:
    dists = [horizontal_distance_m(frame.lat0, frame.lon0, n.lat, n.lon) for n in nodes]
    return max(dists + [50.0]) + BUILDING_QUERY_PADDING_M


def _link_seed(base_seed: int, child_id: str) -> int:
    return (base_seed * 1_000_003 + zlib.crc32(child_id.encode())) % (2**32)


@dataclass
class _HopResult:
    link: LinkMetric
    hop_pdr: float
    hop_latency_ms: float


def run_simulation(
    nodes: list[Node],
    params: Params,
    trials_per_link: int,
    progress_cb: ProgressCb = None,
) -> SimResult:
    """Synchronous and CPU-bound end to end -- callers running inside an
    event loop (see main.py) should invoke this via asyncio.to_thread so
    SSE progress events can be streamed while it runs."""

    def report(msg: str) -> None:
        if progress_cb:
            progress_cb(msg)

    lats = [n.lat for n in nodes]
    lons = [n.lon for n in nodes]
    frame = LocalFrame(sum(lats) / len(lats), sum(lons) / len(lons))
    fc_hz = carrier_frequency_hz(params.band, params.channel)
    antenna = params.antenna

    numerology = get_numerology(int(params.mu))
    mcs = get_mcs(params.mcs)
    num_sc = data_subcarriers(numerology)
    timing = packet_timing(params.payload, mcs, numerology)
    info_bits = (params.payload + HEADER_BYTES) * 8
    coded_bits = info_bits / mcs.code_rate
    bler_curve = build_bler_curve(mcs, int(coded_bits))
    max_extra_rounds = int(params.harq)
    noise_dbm = noise_floor_dbm(numerology.bandwidth_hz, params.nf)
    feedback_delay_s = HARQ_FEEDBACK_ROUNDTRIP_SLOTS * numerology.slot_duration_s

    original_node_ids = {n.id for n in nodes}

    cache_key = _topology_cache_key(nodes, params)
    cached = _topology_cache.get(cache_key)
    if cached is not None:
        _topology_cache.move_to_end(cache_key)
        report("Reusing cached cluster-tree topology and coverage heatmap (no siting/RF-model changes)…")
        buildings = cached.buildings
        building_index = cached.building_index
        extent_m = cached.extent_m
        shadow_field = cached.shadow_field
        tree = cached.tree
        roles = cached.roles
        coverage = cached.coverage
        nodes = cached.nodes  # may include auto-provisioned sinks from the run that first built this
    else:
        report("Building propagation loss matrix (TR 38.901)…")
        bbox = _bbox_with_padding(nodes, BUILDING_QUERY_PADDING_M)
        min_lat, min_lon, max_lat, max_lon = bbox
        buildings = osm.fetch_buildings(min_lat, min_lon, max_lat, max_lon)
        building_index = build_index(frame, buildings)

        extent_m = _extent_m(nodes, frame)
        shadow_field = build_shadow_field(frame, extent_m, params.model, params.seed)

        if params.auto_connect:
            nodes, sink_ids, tree = ensure_connectivity(
                nodes, params, fc_hz, frame, building_index, shadow_field, antenna,
                buildings, bbox, extent_m, mcs.bits_per_symbol, noise_dbm, bler_curve, report,
            )
        else:
            report("Selecting sink from siting…")
            sink_ids = [n.id for n in select_sink(nodes)]

            report(f"Building cluster tree over {len(nodes)} nodes (exact -- every pair evaluated)…")
            tree = build_tree(
                nodes, sink_ids, params, fc_hz, frame, building_index, shadow_field, antenna,
                buildings, bbox, extent_m, mcs.bits_per_symbol, noise_dbm, bler_curve, report,
            )
        roles = derive_roles(nodes, {nid: e.parent for nid, e in tree.items()}, set(sink_ids))

        report("Rendering coverage heatmap…")
        infra_nodes = [n for n in nodes if roles[n.id] != "leaf"] or nodes
        coverage_bbox = _bbox_with_padding(infra_nodes, GRID_PADDING_M)
        coverage = compute_coverage_grid(
            nodes, roles, params, fc_hz, frame, coverage_bbox, building_index, shadow_field, antenna
        )

        _topology_cache[cache_key] = _TopologyBundle(
            buildings=buildings,
            building_index=building_index,
            extent_m=extent_m,
            shadow_field=shadow_field,
            tree=tree,
            nodes=nodes,
            roles=roles,
            coverage=coverage,
        )
        if len(_topology_cache) > _TOPOLOGY_CACHE_MAX:
            _topology_cache.popitem(last=False)

    report(f"Scheduling {len(nodes)} DECT NR+ radios — Monte Carlo per-hop trials…")
    hop_results: dict[str, _HopResult] = {}
    nodes_by_id = {n.id: n for n in nodes}

    for child_id, entry in tree.items():
        if entry.parent is None or entry.budget is None:
            continue
        budget = entry.budget
        total_loss_db = budget.pathloss_db + budget.diffraction_loss_db + budget.o2i_loss_db + budget.shadow_db

        tx_power_override = nodes_by_id[child_id].tx_power_dbm
        if tx_power_override is not None:
            tx_power_dbm = max(0.0, min(tx_power_override, ETSI_MAX_TX_POWER_DBM))
        else:
            tx_power_dbm = solve_tx_power(
                path_loss_db=total_loss_db,
                antenna_gain_db=budget.antenna_gain_db,
                noise_floor_dbm=noise_dbm,
                required_sinr_db=bler_curve.center_sinr_db,
                max_tx_power_dbm=params.max_tx_power_dbm,
            ).tx_power_dbm
        rssi_dbm = tx_power_dbm + budget.antenna_gain_db - total_loss_db
        avg_sinr_db = rssi_dbm - noise_dbm
        avg_sinr_linear = 10.0 ** (avg_sinr_db / 10.0)

        rng = np.random.default_rng(_link_seed(params.seed, child_id))
        outcome = simulate_harq_batch(
            rng,
            model=params.model,
            los=budget.los,
            avg_sinr_linear=avg_sinr_linear,
            bits_per_symbol=mcs.bits_per_symbol,
            num_subcarriers=num_sc,
            subcarrier_spacing_hz=numerology.subcarrier_spacing_hz,
            bler_curve=bler_curve,
            max_extra_rounds=max_extra_rounds,
            n_trials=trials_per_link,
        )

        hop_pdr = outcome.successes.sum() / trials_per_link
        mean_rounds = float(outcome.rounds_used.mean())
        hop_latency_ms = (
            mean_rounds * timing.packet_duration_s
            + max(mean_rounds - 1.0, 0.0) * feedback_delay_s
        ) * 1000.0

        link_metric = LinkMetric(
            child=child_id,
            parent=entry.parent,
            distance_m=budget.distance_m,
            los=budget.los,
            pathloss_db=budget.pathloss_db,
            diffraction_loss_db=budget.diffraction_loss_db,
            o2i_loss_db=budget.o2i_loss_db,
            shadow_db=budget.shadow_db,
            antenna_gain_db=budget.antenna_gain_db,
            tx_power_dbm=tx_power_dbm,
            rssi_dbm=rssi_dbm,
            sinr_db=avg_sinr_db,
            hop_pdr=hop_pdr,
            mean_hop_latency_ms=hop_latency_ms,
            mean_harq_rounds=mean_rounds,
        )
        hop_results[child_id] = _HopResult(
            link=link_metric, hop_pdr=hop_pdr, hop_latency_ms=hop_latency_ms
        )

    report("Aggregating packet traces…")

    node_metrics: list[NodeMetric] = []
    pdr_sum = lat_sum = 0.0
    counted = 0
    max_hop = 0

    for n in nodes:
        entry = tree.get(n.id)
        if entry is None:
            node_metrics.append(NodeMetric(node_id=n.id, role=roles[n.id], offline=True))
            continue
        if roles[n.id] == "sink":
            node_metrics.append(
                NodeMetric(node_id=n.id, role="sink", hop=0, parent=None, e2e_pdr=1.0, e2e_latency_ms=0.0, route=[n.id])
            )
            continue

        route = [n.id]
        e2e_pdr = 1.0
        e2e_latency = 0.0
        cur = n.id
        while True:
            hop = hop_results.get(cur)
            if hop is None:
                e2e_pdr = 0.0
                break
            e2e_pdr *= hop.hop_pdr
            e2e_latency += hop.hop_latency_ms
            cur = tree[cur].parent
            route.append(cur)
            if cur is None or tree[cur].parent is None:
                break

        own_hop = hop_results.get(n.id)
        node_metrics.append(
            NodeMetric(
                node_id=n.id,
                role=roles[n.id],
                hop=entry.hop,
                parent=entry.parent,
                rssi_dbm=own_hop.link.rssi_dbm if own_hop else None,
                snr_db=own_hop.link.sinr_db if own_hop else None,
                e2e_pdr=e2e_pdr,
                e2e_latency_ms=e2e_latency,
                route=route,
            )
        )
        pdr_sum += e2e_pdr
        lat_sum += e2e_latency
        counted += 1
        max_hop = max(max_hop, entry.hop)

    net_pdr = pdr_sum / counted if counted else 0.0
    mean_latency = lat_sum / counted if counted else 0.0
    per_node_packets = floor(params.duration / max(params.interval, 1.0))
    sent = per_node_packets * counted
    delivered = round(sent * net_pdr)
    harq_factor = int(params.harq) / 2.0 + 1.0
    events = int(round(sent * (2 + max_hop) * harq_factor))

    network = NetworkKpi(
        pdr=net_pdr,
        mean_latency_ms=mean_latency,
        max_hops=max_hop,
        sent=sent,
        delivered=delivered,
        events=events,
    )

    added_nodes = [n for n in nodes if n.id not in original_node_ids]

    return SimResult(
        node_metrics=node_metrics,
        link_metrics=[h.link for h in hop_results.values()],
        network=network,
        coverage=coverage,
        added_nodes=added_nodes,
    )
