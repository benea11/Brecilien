"""Headless rendering of the project map for the PDF report, via a
standalone MapLibre GL harness (templates/map_render.html) driven by
Playwright -- there is no way to rasterize a WebGL map server-side in pure
Python, so this reuses the same rendering engine the live app uses, just
pointed at a static data blob instead of the React app's live state.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, Optional

from playwright.sync_api import sync_playwright

from ..models import Building, LinkMetric, Node, NodeType

TEMPLATE_PATH = Path(__file__).parent / "templates" / "map_render.html"
PLACEHOLDER = "REPORT_DATA_PLACEHOLDER"

RenderMode = Literal["vector", "satellite", "3d"]

VIEWPORT_WIDTH = 1400
VIEWPORT_HEIGHT = 900
PADDING_PX = 50
READY_TIMEOUT_MS = 20_000


def _safe_json_for_script(data: dict) -> str:
    """json.dumps, with '</' escaped so a node id/label can never prematurely
    close the enclosing <script> tag."""
    return json.dumps(data).replace("</", "<\\/")


class MapRenderer:
    """Keeps one headless browser alive across every screenshot a report
    needs (overview x3 + N cluster detail shots) -- relaunching Chromium
    per-image would dominate report generation time. Each render() still
    gets its own fresh page: reusing one page across set_content() calls
    left `window.__reportReady` from the *previous* render already true
    when the ready-check ran on the next one, so the screenshot could be
    taken before that page's map (esp. slower raster tile fetches) had
    actually painted -- a fresh page has no stale globals to race against."""

    def __init__(self) -> None:
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"]
        )
        self._template = TEMPLATE_PATH.read_text()

    def render(
        self,
        nodes: list[Node],
        links: list[LinkMetric],
        roles: dict[str, NodeType],
        pdr_by_node: dict[str, Optional[float]],
        offline_ids: set[str],
        bbox: tuple[float, float, float, float],
        mode: RenderMode,
        show_labels: bool = True,
        buildings: Optional[list[Building]] = None,
    ) -> bytes:
        min_lon, min_lat, max_lon, max_lat = bbox
        data = {
            "nodes": [{"id": n.id, "lon": n.lon, "lat": n.lat} for n in nodes],
            "links": [{"child": l.child, "parent": l.parent, "sinr_db": l.sinr_db} for l in links],
            "roles": roles,
            "pdr": pdr_by_node,
            "offline": sorted(offline_ids),
            "bbox": [min_lon, min_lat, max_lon, max_lat],
            "padding_px": PADDING_PX,
            "mode": mode,
            "showLabels": show_labels,
            "buildings": (
                [{"height_m": b.height_m, "footprint": b.footprint} for b in buildings]
                if buildings and mode == "3d"
                else []
            ),
        }
        html = self._template.replace(PLACEHOLDER, _safe_json_for_script(data))
        page = self._browser.new_page(viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT})
        try:
            page.set_content(html, wait_until="load")
            page.wait_for_function("window.__reportReady === true", timeout=READY_TIMEOUT_MS)
            return page.screenshot(type="png")
        finally:
            page.close()

    def render_pdf(self, html: str, header_html: str, footer_html: str) -> bytes:
        """Prints a full report HTML document to a paginated PDF, reusing the
        same Chromium instance as the map screenshots. Header/footer templates
        are rendered by Playwright in their own isolated context (not the
        page's own stylesheet), so they're passed as separate, self-contained
        snippets rather than <head>/<style> slots inside `html`."""
        page = self._browser.new_page()
        try:
            page.set_content(html, wait_until="load")
            page.evaluate("document.fonts.ready")
            return page.pdf(
                format="A4",
                margin={"top": "0.7in", "bottom": "0.7in", "left": "0.7in", "right": "0.7in"},
                print_background=True,
                display_header_footer=True,
                header_template=header_html,
                footer_template=footer_html,
            )
        finally:
            page.close()

    def close(self) -> None:
        self._browser.close()
        self._pw.stop()

    def __enter__(self) -> "MapRenderer":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
