"""Sink selection and role labeling.

Nodes carry no *required* role (see models.Node) -- but a caller may set
Node.forced_role to pin sink selection by hand. Two separate decisions
happen at different points in the pipeline:

1. `select_sink` picks the mesh's root(s) *before* the cluster tree is built
   -- Dijkstra's shortest-cumulative-loss tree (see sim/topology.py) needs a
   root to run from. If any node has forced_role == "sink", those nodes are
   the sink set, full stop (a multi-root forest, same mechanism
   sim/autoconnect.py uses for auto-provisioned backhaul sinks) -- a manual
   pin always wins over the heuristic below. Otherwise: a radio mounted
   above INFRA_HEIGHT_THRESHOLD_M is assumed to be a deliberately-elevated
   backhaul mount (rooftop, mast), so we prefer the most-central such mount
   as the sink, the same way a real deployment would designate its backhaul
   point. If nothing clears the height bar (e.g. a flat CSV import with no
   height data), the single most central node overall is promoted to sink
   anyway -- a mesh needs exactly one root. Nodes with forced_role ==
   "relay" are excluded from this heuristic entirely -- an explicit "make
   this a router" instruction must never be silently overridden by
   auto-sink-selection.

2. `derive_roles` labels every other node *after* the tree is built: a node
   is a "relay" if the resulting tree actually routes other nodes through
   it, and a "leaf" otherwise. Role is therefore an observed property of
   the real topology (which any node can participate in as a relay -- see
   sim/topology.py's module docstring for why height no longer gates that),
   not a pre-assigned category. forced_role == "relay" only ever affects
   sink *candidacy* in step 1 above -- it is not a guarantee about the
   final label, so a forced-router node the tree gives no children still
   legitimately displays as "leaf" here.
"""
from __future__ import annotations

from typing import Optional

from ..geo import horizontal_distance_m
from ..models import Node, NodeType

INFRA_HEIGHT_THRESHOLD_M = 8.0


def _most_central(candidates: list[Node], all_nodes: list[Node]) -> Node:
    def total_distance(n: Node) -> float:
        return sum(horizontal_distance_m(n.lat, n.lon, o.lat, o.lon) for o in all_nodes if o.id != n.id)

    return min(candidates, key=total_distance)


def select_sink(nodes: list[Node]) -> list[Node]:
    forced = [n for n in nodes if n.forced_role == "sink"]
    if forced:
        return forced
    if len(nodes) == 1:
        return [nodes[0]]
    candidates = [n for n in nodes if n.forced_role != "relay"] or nodes
    infra_candidates = [n for n in candidates if n.h > INFRA_HEIGHT_THRESHOLD_M]
    if infra_candidates:
        return [_most_central(infra_candidates, nodes)]
    return [_most_central(candidates, nodes)]


def derive_roles(nodes: list[Node], parent_of: dict[str, Optional[str]], sink_ids: set[str]) -> dict[str, NodeType]:
    """`parent_of` maps every connected node id to its tree parent id (None
    for a sink). Nodes absent from `parent_of` weren't reached by the tree
    (shouldn't happen once the tree spans a fully-connected graph, but is
    handled defensively) and are labeled "leaf". `sink_ids` normally has one
    entry -- more than one only when sim/autoconnect.py provisioned extra
    backhaul sinks for otherwise-unreachable clusters."""
    has_children = {pid for pid in parent_of.values() if pid is not None}
    roles: dict[str, NodeType] = {}
    for n in nodes:
        if n.id in sink_ids:
            roles[n.id] = "sink"
        elif n.id in has_children:
            roles[n.id] = "relay"
        else:
            roles[n.id] = "leaf"
    return roles
