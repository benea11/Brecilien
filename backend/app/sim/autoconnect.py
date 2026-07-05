"""Auto-promotion of additional existing nodes to backhaul sinks so every
placed node ends up with an *acceptable* route to some sink, for projects
spanning multiple disconnected clusters (e.g. two suburbs too far apart for
any relay chain to bridge well). Opt-in via Params.auto_connect --
single-sink behavior is completely unchanged when it's off.

A node is "stranded" if its estimated end-to-end PDR under the current
sink set is below PDR_RESCUE_THRESHOLD. That's deliberately *not* "literal
graph unreachability": _edge_pdr_cost (see topology.py) is a smooth
-log(pdr) relaxation with no hard cutoff, so Dijkstra always finds *some*
finite-cost path between any two nodes, even ones many km apart with an
estimated PDR of 1e-30 -- there is no real distance at which a node
becomes formally "unreachable" in this graph. What actually needs fixing
similar to what the map's red/orange/green node coloring flags: a route
whose predicted PDR is bad enough to be useless. PDR_RESCUE_THRESHOLD
(80%) is deliberately stricter than the map's red cutoff (see
ResultsPanel.tsx / SimMap.ts, currently 70%) -- a node doesn't need to be
visually "red" yet to warrant its own backhaul sink; anything short of a
good link earns one.

No amount of allowing extra relay hops fixes a route whose every candidate
edge is that bad -- a genuinely isolated cluster needs its own backhaul
point, the same way a real deployment covering a large area would use more
than one gateway. Rather than inventing a synthetic sink at a location
nobody actually sited (a centroid can land on a rooftop nobody owns, a
lake, a motorway), this promotes the *existing* stranded node that is most
central to its own stranded cluster -- the way a human planner would look
at a disconnected pocket of nodes and pick one of them to wire up for
backhaul. So this module repeatedly: finds the stranded nodes, promotes
the most central one to sink, and re-solves the multi-sink forest, until
either everyone clears the threshold or MAX_PROMOTED_SINKS is hit.

Because promotion never changes the node set, the O(n^2) pairwise
link-budget matrix (topology.py's real bottleneck) only needs to be built
once up front, not re-evaluated per candidate sink the way a node-adding
approach would require -- each iteration after that is just a cheap
re-run of Dijkstra over the already-computed matrix with one more sink
index.
"""
from __future__ import annotations

import math

from ..models import Node, Params
from ..geo import LocalFrame
from ..linklevel.bler_curves import BlerCurve
from ..phy.antenna import AntennaSpec
from ..propagation.building_index import BuildingIndex
from ..propagation.shadow_field import ShadowField
from .roles import _most_central, select_sink
from .topology import Bbox, TreeEntry, _compute_cost_matrix, _dijkstra_tree, build_static_parent_idx, build_tree

MAX_PROMOTED_SINKS = 4
# Bar for "needs its own backhaul sink" -- stricter than the map's red
# cutoff (see SimMap.ts's PDR_RED band / ResultsPanel.tsx's pdrColor,
# 70%) so the deployment ends up with uniformly good PDR rather than
# merely avoiding outright-broken links.
PDR_RESCUE_THRESHOLD = 0.80


def ensure_connectivity(
    nodes: list[Node],
    params: Params,
    fc_hz: float,
    frame: LocalFrame,
    building_index: BuildingIndex,
    shadow_field: ShadowField,
    antenna: AntennaSpec,
    buildings: list,
    bbox: Bbox,
    extent_m: float,
    bits_per_symbol: int,
    noise_dbm: float,
    bler_curve: BlerCurve,
    report,
) -> tuple[list[Node], list[str], dict[str, TreeEntry]]:
    """Returns (the unchanged node list, sink ids [primary + any promoted],
    the resulting multi-sink tree). The node list is never extended -- extra
    sinks are always existing nodes whose role is promoted, never new
    physical nodes -- so callers can keep using their own node list as-is.
    """
    sink_ids = [n.id for n in select_sink(nodes)]

    cost = _compute_cost_matrix(
        nodes, params, fc_hz, frame, building_index, shadow_field, antenna, buildings, bbox, extent_m,
        bits_per_symbol, noise_dbm, bler_curve, report,
    )

    for _ in range(MAX_PROMOTED_SINKS + 1):
        sink_id_set = set(sink_ids)
        sink_indices = [i for i, n in enumerate(nodes) if n.id in sink_id_set]
        static_parent_idx = build_static_parent_idx(nodes, sink_id_set)
        parent_idx, _hop, dist = _dijkstra_tree(cost, sink_indices, static_parent_idx)
        stranded = [
            n
            for i, n in enumerate(nodes)
            if n.id not in sink_id_set
            and not n.static_parent  # an explicit user-pinned route is intentional, not a rescue case
            and (parent_idx[i] is None or math.exp(-dist[i]) < PDR_RESCUE_THRESHOLD)
        ]
        if not stranded:
            break
        # Nodes explicitly marked "relay" must never be silently promoted to
        # sink -- same reasoning as select_sink's own candidacy filter.
        promotable = [n for n in stranded if n.forced_role != "relay"]
        if not promotable or len(sink_ids) - 1 >= MAX_PROMOTED_SINKS:
            report(
                f"Stopped after promoting {len(sink_ids) - 1} node(s) to sink -- "
                f"{len(stranded)} node(s) still below the {PDR_RESCUE_THRESHOLD:.0%} PDR rescue threshold."
            )
            break
        promoted = _most_central(promotable, promotable)
        report(
            f"{len(stranded)} node(s) below {PDR_RESCUE_THRESHOLD:.0%} estimated PDR from any sink -- "
            f"promoting {promoted.id} to a backhaul sink…"
        )
        sink_ids.append(promoted.id)

    tree = build_tree(
        nodes, sink_ids, params, fc_hz, frame, building_index, shadow_field, antenna,
        buildings, bbox, extent_m, bits_per_symbol, noise_dbm, bler_curve, report,
        precomputed_cost=cost,
    )
    return nodes, sink_ids, tree
