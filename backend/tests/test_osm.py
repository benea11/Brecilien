from app.osm import _elements_to_buildings


def _node(id_, lon, lat):
    return {"type": "node", "id": id_, "lon": lon, "lat": lat}


def test_simple_way_building():
    elements = [
        _node(1, 0.0, 0.0),
        _node(2, 1.0, 0.0),
        _node(3, 1.0, 1.0),
        _node(4, 0.0, 1.0),
        {"type": "way", "id": 100, "nodes": [1, 2, 3, 4, 1], "tags": {"building": "yes", "height": "12"}},
    ]
    buildings = _elements_to_buildings(elements)
    assert len(buildings) == 1
    b = buildings[0]
    assert b.id == "way/100"
    assert b.height_m == 12.0
    assert b.footprint[0] == b.footprint[-1]


def test_untagged_member_way_is_not_its_own_building():
    # A bare way with no `building` tag (e.g. a relation's ring segment
    # fetched standalone, or any other non-building way) must not turn into
    # a spurious footprint of its own.
    elements = [
        _node(1, 0.0, 0.0),
        _node(2, 1.0, 0.0),
        _node(3, 1.0, 1.0),
        {"type": "way", "id": 200, "nodes": [1, 2, 3, 1], "tags": {}},
    ]
    assert _elements_to_buildings(elements) == []


def test_multipolygon_relation_single_outer_way():
    elements = [
        _node(1, 0.0, 0.0),
        _node(2, 1.0, 0.0),
        _node(3, 1.0, 1.0),
        _node(4, 0.0, 1.0),
        {"type": "way", "id": 10, "nodes": [1, 2, 3, 4, 1], "tags": {}},
        {"type": "way", "id": 11, "nodes": [5, 6, 7, 5], "tags": {}},  # inner hole, ignored
        {
            "type": "relation",
            "id": 500,
            "tags": {"building": "yes", "type": "multipolygon", "height": "30"},
            "members": [
                {"type": "way", "ref": 10, "role": "outer"},
                {"type": "way", "ref": 11, "role": "inner"},
            ],
        },
    ]
    buildings = _elements_to_buildings(elements)
    assert len(buildings) == 1
    b = buildings[0]
    assert b.id == "relation/500"
    assert b.height_m == 30.0
    assert b.footprint[0] == b.footprint[-1]
    assert len(b.footprint) == 5  # 4 distinct corners + closing repeat


def test_multipolygon_relation_outer_ring_split_across_ways():
    # Real OSM data frequently splits one building outline across several
    # ways -- that's often exactly *why* it's modeled as a relation. The
    # assembler must chain them by shared endpoint node ids into one ring.
    elements = [
        _node(1, 0.0, 0.0),
        _node(2, 1.0, 0.0),
        _node(3, 1.0, 1.0),
        _node(4, 0.0, 1.0),
        {"type": "way", "id": 20, "nodes": [1, 2, 3], "tags": {}},
        {"type": "way", "id": 21, "nodes": [3, 4, 1], "tags": {}},
        {
            "type": "relation",
            "id": 600,
            "tags": {"building": "yes", "type": "multipolygon", "building:levels": "4"},
            "members": [
                {"type": "way", "ref": 21, "role": "outer"},
                {"type": "way", "ref": 20, "role": "outer"},
            ],
        },
    ]
    buildings = _elements_to_buildings(elements)
    assert len(buildings) == 1
    b = buildings[0]
    assert b.id == "relation/600"
    assert b.height_m == 12.0  # 4 levels * 3.0 m
    assert b.footprint[0] == b.footprint[-1]
    assert len(b.footprint) == 5
