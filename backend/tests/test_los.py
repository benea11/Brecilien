from app.geo import LocalFrame
from app.models import Building
from app.propagation.building_index import build_index
from app.propagation.los import check_los

FRAME = LocalFrame(0.0, 0.0)


def _square_building(building_id, x0, y0, x1, y1, height_m):
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    footprint = [list(reversed(FRAME.from_xy(x, y))) for x, y in corners]  # [lon, lat]
    return Building(id=building_id, height_m=height_m, footprint=footprint)


def test_node_inside_its_own_building_is_not_an_obstruction():
    # A leaf mounted near the far exterior wall of a 15 m building: its
    # position falls inside the footprint, but it must read as attached to
    # the building, not blocked by it.
    building = _square_building("host", 0, 0, 20, 20, 15.0)
    index = build_index(FRAME, [building])

    tx_lat, tx_lon = FRAME.from_xy(-200, 10)
    rx_lat, rx_lon = FRAME.from_xy(18, 10)

    result = check_los(FRAME, tx_lat, tx_lon, 20.0, rx_lat, rx_lon, 1.5, index)

    assert result.los is True
    assert result.obstructions == []


def test_other_buildings_still_obstruct_a_node_inside_its_own_building():
    host = _square_building("host", 0, 0, 20, 20, 15.0)
    intermediate = _square_building("blocker", -100, 5, -80, 15, 15.0)
    index = build_index(FRAME, [host, intermediate])

    tx_lat, tx_lon = FRAME.from_xy(-200, 10)
    rx_lat, rx_lon = FRAME.from_xy(18, 10)

    result = check_los(FRAME, tx_lat, tx_lon, 20.0, rx_lat, rx_lon, 1.5, index)

    assert result.los is False
    ids = {o.building_id for o in result.obstructions}
    assert ids == {"blocker"}


def test_node_on_far_side_of_unrelated_building_is_still_obstructed():
    # Sanity check: a node that is genuinely *outside* every footprint, but
    # behind one, must still be treated as NLOS.
    blocker = _square_building("blocker", 0, 0, 20, 20, 15.0)
    index = build_index(FRAME, [blocker])

    tx_lat, tx_lon = FRAME.from_xy(-200, 10)
    rx_lat, rx_lon = FRAME.from_xy(200, 10)

    result = check_los(FRAME, tx_lat, tx_lon, 20.0, rx_lat, rx_lon, 1.5, index)

    assert result.los is False
    assert {o.building_id for o in result.obstructions} == {"blocker"}
