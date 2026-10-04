from app.geo import LocalFrame
from app.propagation.shadow_field import MAX_GRID_N, build_shadow_field


def test_grid_size_bounded_for_large_extent():
    """A project spanning tens of km (the exact scenario Params.auto_connect's
    multi-sink rescue targets -- see sim/autoconnect.py's module docstring)
    must not blow the spectral-synthesis grid up unbounded: that previously
    allocated multi-GB FFT buffers and could OOM-kill the simulation."""
    frame = LocalFrame(45.0, 5.0)
    field = build_shadow_field(frame, extent_m=150_000.0, model="uma", seed=1)
    assert field.n <= MAX_GRID_N
    # the field must still cover the full requested extent, just coarser
    assert field.n * field.cell_m >= 2.0 * 150_000.0


def test_small_extent_keeps_default_resolution():
    frame = LocalFrame(45.0, 5.0)
    field = build_shadow_field(frame, extent_m=1000.0, model="uma", seed=1)
    assert field.cell_m == 15.0


def test_sample_in_bounds_for_capped_grid():
    frame = LocalFrame(45.0, 5.0)
    field = build_shadow_field(frame, extent_m=150_000.0, model="uma", seed=1)
    # sampling near the edge of the requested extent must not raise
    lat, lon = frame.from_xy(140_000.0, 140_000.0)
    field.sample(lat, lon, los=True)
    field.sample(lat, lon, los=False)
