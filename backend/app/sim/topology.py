"""Cluster-tree formation: a Dijkstra shortest-cumulative-loss tree rooted
at the sink, over the *complete* graph of every node pair's real large-scale
link budget.

Any node can relay for any other node here -- there is no pre-assigned
infrastructure/leaf split gating who is allowed to be an intermediate hop
(see sim/roles.py: role is now derived from the resulting tree, not the
other way around). That matters physically: restricting relaying to a
height-gated subset means a flat-height import (e.g. a CSV with no mount
data) can *only* ever form a star, no matter how far apart nodes are or how
much a multi-hop route through a well-placed neighbor would help. Letting
every node participate lets the tree actually reflect the terrain and
geometry.

We minimize each node's *cumulative* routing cost to the sink (a shortest-
path tree), not the tree's total edge-weight sum (a minimum spanning tree)
-- those are different objectives, and cumulative cost-to-sink is the one
that actually tracks end-to-end PDR, which is what this planner reports.

That cost is deliberately *not* raw summed dB loss, even though large-
scale loss is what compute_link_budget gives you. TR 38.901 pathloss is
logarithmic in distance, so pathloss(d1) + pathloss(d2) for two hops
covering the same total distance as one direct hop is *much larger* in dB
than pathloss(d1+d2) -- splitting a link into hops multiplies the dB
budget rather than sharing it. Minimizing summed dB loss therefore almost
always picks one long direct hop over any multi-hop detour, even when
that direct hop is one no real radio could ever close (SINR far below
what any MCS/HARQ combination decodes), which produces exactly the
degenerate star this module exists to avoid. What end-to-end delivery
actually depends on is the *product* of achievable per-hop PDRs (see
sim/engine.py's e2e_pdr aggregation), so the cost needs to be additive in
-log(pdr_estimate), not in dB: `_edge_pdr_cost` runs the same power-
control + BLER-curve model the final Monte Carlo phase uses (at the
average SINR, without per-trial fading -- fine for ranking candidate
parents, since the Monte Carlo phase still computes the real per-hop
number afterward) to estimate each candidate edge's achievability before
it's allowed to accumulate.

The cost, and the reason this module exists: a full pairwise matrix is
O(V^2) real link-budget evaluations (~4 ms each even after the STRtree
query fix in propagation/los.py), so a 1500-node project means roughly
1500^2/2 ~= 1.1M evaluations. Nothing here approximates or prunes that
candidate set -- every pair is evaluated with the same physics as the final
per-hop simulation -- so the only lever left is parallelizing the
evaluation itself across CPU cores (see `_compute_cost_matrix`). At
1500 nodes this is still minutes, not seconds; sim/engine.py caches the
resulting tree (keyed on node positions/heights and the RF-relevant
params) so re-running a simulation with only e.g. a different MCS or
trials-per-link doesn't pay this cost again.
"""
from __future__ import annotations

import heapq
import os
from dataclasses import dataclass
from math import ceil
from typing import Optional

import numpy as np

# ProcessPoolExecutor (spawn -- required on macOS; numpy linked against
# Accelerate is known to hang after fork()) needs every worker to end up
# with its own BuildingIndex, since shapely's STRtree doesn't survive a
# pickle round-trip and so can't just be built once and shared. The naive
# way to get a Building list into each worker -- passing it through
# initargs -- means the main process pickles the whole (large: ~2 GB for
# ~300k buildings, measured) list once per worker and ships it through the
# pool's init pipe, which in practice was slower than just re-fetching:
# osm.fetch_buildings already disk-caches the raw Overpass JSON keyed by
# bbox, so each worker re-reading+re-parsing that cache file directly is a
# few independent, genuinely parallel disk reads instead of one serialized
# multi-GB pickle. Workers get the (tiny) bbox tuple, not the buildings.
#
# Even with that, one worker still means one more full BuildingIndex in
# memory, so spawning one worker per CPU core can multiply that past
# available RAM and make the machine thrash, which is *slower* than fewer
# workers, not just less parallel -- size the pool to what memory actually
# allows (see `_safe_worker_count`).
_BYTES_PER_BUILDING_ESTIMATE = 8_000  # calibrated with margin above the ~6.5 KB/building measured
_WORKER_MEMORY_BUDGET_FRACTION = 0.5  # leave headroom for the main process's own copy + everything else

from .. import osm
from ..geo import LocalFrame, horizontal_distance_m
from ..linklevel.bler_curves import BlerCurve
from ..linklevel.effective_sinr import effective_mi
from ..models import Building, Node, Params
from ..phy.antenna import AntennaSpec
from ..propagation.building_index import BuildingIndex, build_index
from ..propagation.link_budget import LinkBudget, compute_link_budget
from ..propagation.shadow_field import ShadowField, build_shadow_field
from .roles import INFRA_HEIGHT_THRESHOLD_M

Bbox = tuple[float, float, float, float]

ProgressCb = Optional["callable"]

# Below this node count, process-pool startup + per-worker index rebuild
# costs more than the serial computation it would save.
PARALLEL_MIN_NODES = 60


@dataclass
class TreeEntry:
    parent: Optional[str]
    hop: int
    budget: Optional[LinkBudget]  # large-scale budget for the (parent -> this) link


def _rx_is_leaf(rx: Node) -> bool:
    """O2I (indoor penetration) applies to any receiver mounted at or below
    the infra height threshold, independent of its eventual tree role -- a
    low, wall-mounted node can still end up relaying for one neighbor, but
    it's still physically a low, possibly-embedded-in-a-building mount when
    it's on the *receiving* end of a link."""
    return rx.h <= INFRA_HEIGHT_THRESHOLD_M


# MI saturates at bits_per_symbol (effective_sinr.effective_mi's cap) once
# raw SINR clears a fairly modest margin -- ~4.8 dB for QPSK, less for
# higher-order MCS. Past that point, *every* comfortably-closeable edge,
# whether a 60 m hop or a 600 m one, produces the exact same MI and
# therefore the exact same neg_log_pdr_from_mi cost (down to 20+ decimal
# places -- verified: two edges differing 9x in distance both landed on
# 1.0526606081e-23). That left Dijkstra with no signal at all to prefer
# the shorter/cleaner of two otherwise-viable edges, which is what
# produced reports of nodes routing through a far node while skipping an
# obvious close neighbor. This tie-break term is strictly dominated by any
# real PDR difference (see the weight's docstring below) but breaks that
# degeneracy in favor of lower total path loss once every candidate is
# otherwise "perfect".
_TIE_BREAK_WEIGHT_PER_DB = 1e-6


def _edge_pdr_cost(
    budget: LinkBudget,
    bits_per_symbol: int,
    noise_dbm: float,
    bler_curve: BlerCurve,
    max_tx_power_dbm: float,
) -> float:
    """Deliberately evaluates SINR at a *fixed* reference power
    (max_tx_power_dbm) rather than running this through solve_tx_power's
    adaptive minimum-power control. Adaptive power control's entire job is
    to spend just enough power to land every closeable link at the same
    target-SINR-plus-margin operating point -- which is exactly right for
    the final per-hop simulation, but means two closeable candidate edges
    of very different quality (a 150 m hop and a 3 km hop that both happen
    to fit under the power budget) come back with an *identical* SINR and
    therefore an identical cost, leaving Dijkstra with no signal to prefer
    the shorter/cleaner one. Fixing the reference power instead makes SINR
    (and thus cost) actually track link quality/margin continuously, which
    is what a routing decision needs.

    Uses `bler_curve.neg_log_pdr_from_mi`, not `bler_from_mi` -- the latter
    clips BLER to a ceiling (right for a Monte Carlo trial, wrong for a
    routing cost; see that method's docstring), which made every
    sufficiently-bad edge cost exactly the same and left Dijkstra with no
    reason to prefer a relay chain over repeating the same bad hop.

    The `_TIE_BREAK_WEIGHT_PER_DB * total_loss_db` term added at the end
    exists for the *other* saturation case -- see that constant's
    docstring: MI capping means neg_log_pdr_from_mi also floors to the
    same near-zero value for every sufficiently-good edge, which needs its
    own tie-break in the opposite direction (prefer lower loss) once the
    primary term stops discriminating. The weight is small enough (1e-6
    per dB) that even an implausibly bad 500 dB total loss only
    contributes 5e-4 -- far below any primary-cost delta that reflects a
    genuine PDR difference (typically >= 0.01), so it can never override
    a real quality preference, only break ties among edges that are
    otherwise indistinguishable."""
    total_loss_db = budget.pathloss_db + budget.diffraction_loss_db + budget.o2i_loss_db + budget.shadow_db
    rssi_dbm = max_tx_power_dbm + budget.antenna_gain_db - total_loss_db
    avg_sinr_linear = 10.0 ** ((rssi_dbm - noise_dbm) / 10.0)
    mi = effective_mi(np.array([avg_sinr_linear]), bits_per_symbol)
    primary = bler_curve.neg_log_pdr_from_mi(mi)
    return primary + _TIE_BREAK_WEIGHT_PER_DB * total_loss_db


# --- Parallel pairwise cost matrix ------------------------------------------
#
# Each worker rebuilds its own BuildingIndex/ShadowField once (shapely's
# STRtree does not survive a pickle round-trip, so we can't just hand a
# worker the main process's index) from picklable raw inputs, then answers
# many (i, j) cost queries against that local state.

_worker_state: dict = {}


def _init_worker(
    nodes: list[Node],
    bbox: Bbox,
    frame: LocalFrame,
    model: str,
    sigma_db: float,
    o2i_enabled: bool,
    extent_m: float,
    seed: int,
    antenna: AntennaSpec,
    fc_hz: float,
    bits_per_symbol: int,
    noise_dbm: float,
    bler_curve: BlerCurve,
    max_tx_power_dbm: float,
) -> None:
    buildings = osm.fetch_buildings(*bbox)
    _worker_state.update(
        nodes=nodes,
        frame=frame,
        index=build_index(frame, buildings),
        shadow=build_shadow_field(frame, extent_m, model, seed),
        model=model,
        sigma_db=sigma_db,
        o2i_enabled=o2i_enabled,
        antenna=antenna,
        fc_hz=fc_hz,
        bits_per_symbol=bits_per_symbol,
        noise_dbm=noise_dbm,
        bler_curve=bler_curve,
        max_tx_power_dbm=max_tx_power_dbm,
    )


def _safe_worker_count(n_buildings: int) -> int:
    cpu = os.cpu_count() or 4
    if n_buildings == 0:
        return cpu
    try:
        total_ram_bytes = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (ValueError, OSError, AttributeError):
        return 1
    per_worker_bytes = n_buildings * _BYTES_PER_BUILDING_ESTIMATE
    budget_bytes = int(total_ram_bytes * _WORKER_MEMORY_BUDGET_FRACTION)
    by_memory = max(1, budget_bytes // max(per_worker_bytes, 1))
    return max(1, min(cpu, int(by_memory)))


def _edge_cost(pair: tuple[int, int]) -> float:
    i, j = pair
    st = _worker_state
    tx, rx = st["nodes"][i], st["nodes"][j]
    budget = compute_link_budget(
        tx,
        rx,
        model=st["model"],
        fc_hz=st["fc_hz"],
        sigma_db=st["sigma_db"],
        o2i_enabled=st["o2i_enabled"],
        rx_is_leaf=_rx_is_leaf(rx),
        frame=st["frame"],
        building_index=st["index"],
        shadow_field=st["shadow"],
        antenna=st["antenna"],
    )
    return _edge_pdr_cost(budget, st["bits_per_symbol"], st["noise_dbm"], st["bler_curve"], st["max_tx_power_dbm"])


# Below this separation, two nodes are treated as the same physical site
# (adjacent poles on the same substation, the same building, etc.) rather
# than independent siting decisions -- see sim/autoconnect.py-adjacent
# discussion: _edge_pdr_cost's tie-break makes the router prefer shorter/
# cleaner hops among otherwise-comparable candidates, but it can still
# correctly route two nodes a few meters apart onto completely different
# branches if each independently has a *measurably* better path to the
# sink through someone else -- real deployments don't do that with two
# adjacent radios. Forcing these edges to ~0 cost means whichever
# co-located node has the best route to the sink effectively becomes the
# other's route too, at negligible extra cost, without touching how any
# other pair in the graph is ranked.
COLOCATED_RADIUS_M = 15.0
_FORCED_EDGE_COST = 0.0


def _force_colocated_edges(cost: np.ndarray, nodes: list[Node]) -> np.ndarray:
    n = len(nodes)
    for i in range(n):
        for j in range(i + 1, n):
            if horizontal_distance_m(nodes[i].lat, nodes[i].lon, nodes[j].lat, nodes[j].lon) < COLOCATED_RADIUS_M:
                cost[i, j] = cost[j, i] = _FORCED_EDGE_COST
    return cost


def _compute_cost_matrix(
    nodes: list[Node],
    params: Params,
    fc_hz: float,
    frame: LocalFrame,
    building_index: BuildingIndex,
    shadow_field: ShadowField,
    antenna: AntennaSpec,
    buildings: list[Building],
    bbox: Bbox,
    extent_m: float,
    bits_per_symbol: int,
    noise_dbm: float,
    bler_curve: BlerCurve,
    report,
) -> np.ndarray:
    n = len(nodes)
    cost = np.full((n, n), np.inf, dtype=np.float64)
    pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]
    total = len(pairs)

    max_workers = _safe_worker_count(len(buildings))

    if n < PARALLEL_MIN_NODES or max_workers <= 1:
        next_report_pct = 10
        for k, (i, j) in enumerate(pairs):
            tx, rx = nodes[i], nodes[j]
            budget = compute_link_budget(
                tx,
                rx,
                model=params.model,
                fc_hz=fc_hz,
                sigma_db=params.sigma,
                o2i_enabled=params.o2i,
                rx_is_leaf=_rx_is_leaf(rx),
                frame=frame,
                building_index=building_index,
                shadow_field=shadow_field,
                antenna=antenna,
            )
            cost[i, j] = cost[j, i] = _edge_pdr_cost(
                budget, bits_per_symbol, noise_dbm, bler_curve, params.max_tx_power_dbm
            )
            pct = int((k + 1) / max(total, 1) * 100)
            if pct >= next_report_pct:
                report(f"Building full {n}x{n} link-budget matrix for cluster-tree formation… {pct}%")
                next_report_pct = pct + 10
        return _force_colocated_edges(cost, nodes)

    from concurrent.futures import ProcessPoolExecutor

    report(
        f"Building full {n}x{n} link-budget matrix using {max_workers} parallel worker(s) "
        f"(sized to available memory for {len(buildings)} buildings)…"
    )
    chunksize = max(1, min(500, ceil(total / (max_workers * 20))))
    next_report_pct = 10
    with ProcessPoolExecutor(
        max_workers=max_workers,
        initializer=_init_worker,
        initargs=(
            nodes, bbox, frame, params.model, params.sigma, params.o2i, extent_m, params.seed, antenna, fc_hz,
            bits_per_symbol, noise_dbm, bler_curve, params.max_tx_power_dbm,
        ),
    ) as executor:
        for k, (pair, loss_db) in enumerate(zip(pairs, executor.map(_edge_cost, pairs, chunksize=chunksize))):
            i, j = pair
            cost[i, j] = cost[j, i] = loss_db
            pct = int((k + 1) / total * 100)
            if pct >= next_report_pct:
                report(f"Building full {n}x{n} link-budget matrix for cluster-tree formation… {pct}%")
                next_report_pct = pct + 10

    return _force_colocated_edges(cost, nodes)


def _dijkstra_tree(
    cost: np.ndarray,
    sink_indices: list[int],
    static_parent_idx: Optional[dict[int, int]] = None,
) -> tuple[list[Optional[int]], list[int], list[float]]:
    """Shortest cumulative-loss *forest* rooted at every index in
    sink_indices, over the complete graph `cost` -- each node ends up
    attached to whichever sink gives the lowest cumulative cost, exactly
    like single-source Dijkstra except the heap starts seeded with every
    sink at distance 0 instead of just one. A node unreachable from *any*
    sink keeps parent=None, same as the single-sink case. Returns
    (parent_idx per node, hop count per node, cumulative cost per node --
    the latter is -log(estimated e2e PDR) per _edge_pdr_cost's definition,
    which sim/autoconnect.py uses to find nodes whose *estimated* PDR is
    unacceptable even though Dijkstra did technically connect them -- see
    that module for why "connected" can't just mean "reachable" here).

    `static_parent_idx` pins specific nodes' parent to a caller-chosen index
    instead of letting Dijkstra pick it (see models.Node.static_parent): a
    node with an entry here only ever accepts a relaxation from that one
    parent, so its distance/parent become fixed to that single edge the
    moment the forced parent is finalized. A pin that forms a cycle (or
    chains onto a parent that never resolves) simply never gets relaxed and
    falls out unreached, same as any other unreachable node -- no special
    casing needed beyond this one guard."""
    n = cost.shape[0]
    static_parent_idx = static_parent_idx or {}
    dist = [float("inf")] * n
    parent: list[Optional[int]] = [None] * n
    hop = [0] * n
    visited = [False] * n
    heap: list[tuple[float, int]] = []
    for sink_idx in sink_indices:
        dist[sink_idx] = 0.0
        heap.append((0.0, sink_idx))
    heapq.heapify(heap)

    while heap:
        d, u = heapq.heappop(heap)
        if visited[u]:
            continue
        visited[u] = True
        for v in range(n):
            if visited[v] or v == u:
                continue
            forced_parent = static_parent_idx.get(v)
            if forced_parent is not None and forced_parent != u:
                continue
            w = cost[u, v]
            if not np.isfinite(w):
                continue
            nd = d + w
            if nd < dist[v]:
                dist[v] = nd
                parent[v] = u
                hop[v] = hop[u] + 1
                heapq.heappush(heap, (nd, v))

    return parent, hop, dist


def build_static_parent_idx(nodes: list[Node], sink_id_set: set[str]) -> dict[int, int]:
    """Resolves Node.static_parent id references to index pairs for
    _dijkstra_tree. Silently drops any entry that self-references, targets
    an unknown id, or targets a node already in the sink set (a sink has no
    parent, forced or otherwise) -- callers shouldn't have to pre-validate
    stale/edited-around static_parent values."""
    id_to_idx = {node.id: i for i, node in enumerate(nodes)}
    static_parent_idx: dict[int, int] = {}
    for i, node in enumerate(nodes):
        if node.id in sink_id_set or not node.static_parent:
            continue
        parent_idx = id_to_idx.get(node.static_parent)
        if parent_idx is None or parent_idx == i:
            continue
        static_parent_idx[i] = parent_idx
    return static_parent_idx


def build_tree(
    nodes: list[Node],
    sink_ids: list[str],
    params: Params,
    fc_hz: float,
    frame: LocalFrame,
    building_index: BuildingIndex,
    shadow_field: ShadowField,
    antenna: AntennaSpec,
    buildings: list[Building],
    bbox: Bbox,
    extent_m: float,
    bits_per_symbol: int,
    noise_dbm: float,
    bler_curve: BlerCurve,
    report,
    precomputed_cost: Optional[np.ndarray] = None,
) -> dict[str, TreeEntry]:
    """Builds a shortest-cumulative-loss forest rooted at every id in
    sink_ids (see _dijkstra_tree) -- the normal single-sink case is just the
    len(sink_ids) == 1 case, nothing about it changes.

    `precomputed_cost` lets a caller that already paid for the O(n^2)
    pairwise matrix (sim/autoconnect.py's connectivity-repair loop evaluates
    it once per candidate sink count anyway) reuse it here instead of this
    function computing it again from scratch."""
    n = len(nodes)
    tree: dict[str, TreeEntry] = {}
    if n == 0:
        return tree
    if n == 1:
        return {nodes[0].id: TreeEntry(parent=None, hop=0, budget=None)}

    sink_id_set = set(sink_ids)
    sink_indices = [i for i, node in enumerate(nodes) if node.id in sink_id_set]
    cost = (
        precomputed_cost
        if precomputed_cost is not None
        else _compute_cost_matrix(
            nodes, params, fc_hz, frame, building_index, shadow_field, antenna, buildings, bbox, extent_m,
            bits_per_symbol, noise_dbm, bler_curve, report,
        )
    )
    static_parent_idx = build_static_parent_idx(nodes, sink_id_set)
    parent_idx, hop, _dist = _dijkstra_tree(cost, sink_indices, static_parent_idx)

    for sid in sink_ids:
        tree[sid] = TreeEntry(parent=None, hop=0, budget=None)
    for i, node in enumerate(nodes):
        if node.id in sink_id_set or parent_idx[i] is None:
            continue
        parent_node = nodes[parent_idx[i]]
        # The pairwise matrix used a single canonical direction per pair
        # purely to rank candidate edges; recompute the budget in the real
        # parent(tx) -> child(rx) direction now that it's known, so the
        # reported link metrics are never an approximation.
        budget = compute_link_budget(
            parent_node,
            node,
            model=params.model,
            fc_hz=fc_hz,
            sigma_db=params.sigma,
            o2i_enabled=params.o2i,
            rx_is_leaf=_rx_is_leaf(node),
            frame=frame,
            building_index=building_index,
            shadow_field=shadow_field,
            antenna=antenna,
        )
        tree[node.id] = TreeEntry(parent=parent_node.id, hop=hop[i], budget=budget)

    return tree
