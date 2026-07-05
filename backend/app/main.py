from __future__ import annotations

import asyncio
import json

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from . import enedis, geocode, osm, project_store
from .enedis import MvSubstation
from .geocode import GeocodeResult
from .models import Building, Project, ReportRequest, SimulateRequest
from .report import generate_report_pdf
from .sim.engine import run_simulation

app = FastAPI(title="Brécilien — DECT NR+ Link Simulator API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DEFAULT_PROJECT_ID = "grenoble-centre"


def _default_project() -> Project:
    from .models import Node, Params

    # Infrastructure mount heights are set above the typical local rooftop
    # line (Grenoble's historic centre runs ~15-21 m / 4-6 storeys): real
    # DECT NR+ outdoor mesh planning mounts sinks/relays above surrounding
    # roofs specifically to get LOS mesh backhaul, exactly like a real
    # deployment would. Leaves stay at realistic street/window-mount height
    # (3 m) -- some leaves being hard to reach is expected and is the actual
    # planning problem this tool is for.
    nodes = [
        Node(id="SINK-01", lon=5.7265, lat=45.1897, h=28),
        Node(id="RN-01", lon=5.7247, lat=45.1917, h=24),
        Node(id="RN-02", lon=5.7299, lat=45.1908, h=24),
        Node(id="RN-03", lon=5.7288, lat=45.1872, h=22),
        Node(id="RN-04", lon=5.7221, lat=45.1884, h=24),
        Node(id="EP-01", lon=5.7238, lat=45.1932, h=3),
        Node(id="EP-02", lon=5.7319, lat=45.1918, h=3),
        Node(id="EP-03", lon=5.7307, lat=45.1886, h=3),
        Node(id="EP-04", lon=5.7267, lat=45.1861, h=3),
        Node(id="EP-05", lon=5.7198, lat=45.1872, h=3),
        Node(id="EP-06", lon=5.7210, lat=45.1905, h=3),
    ]
    return Project(id=DEFAULT_PROJECT_ID, name="grenoble-centre", nodes=nodes, params=Params())


@app.on_event("startup")
def ensure_default_project() -> None:
    try:
        project_store.load(DEFAULT_PROJECT_ID)
    except FileNotFoundError:
        project_store.save(_default_project())


@app.get("/api/projects")
def list_projects() -> list[dict]:
    return project_store.list_projects()


@app.get("/api/project/{project_id}", response_model=Project)
def get_project(project_id: str) -> Project:
    try:
        return project_store.load(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")


@app.post("/api/project", response_model=Project)
def save_project(project: Project) -> Project:
    project_store.save(project)
    return project


@app.get("/api/buildings", response_model=list[Building])
def get_buildings(min_lat: float, min_lon: float, max_lat: float, max_lon: float) -> list[Building]:
    return osm.fetch_buildings(min_lat, min_lon, max_lat, max_lon)


@app.get("/api/geocode", response_model=list[GeocodeResult])
def get_geocode(q: str) -> list[GeocodeResult]:
    if not q.strip():
        return []
    try:
        return geocode.search(q)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"geocoding failed: {exc}")


@app.get("/api/mv-substations", response_model=list[MvSubstation])
def get_mv_substations(min_lat: float, min_lon: float, max_lat: float, max_lon: float) -> list[MvSubstation]:
    try:
        return enedis.fetch_substations(min_lat, min_lon, max_lat, max_lon)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"MV substation lookup failed: {exc}")


@app.post("/api/report")
async def generate_report(req: ReportRequest) -> Response:
    """Renders the map (headless Playwright + MapLibre) and assembles the
    PDF in a worker thread -- both are blocking/CPU-bound, same reasoning
    as /api/simulate's asyncio.to_thread use."""
    try:
        pdf_bytes = await asyncio.to_thread(generate_report_pdf, req.project, req.result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"report generation failed: {exc}")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{req.project.id}-report.pdf"'},
    )


@app.delete("/api/project/{project_id}")
def delete_project(project_id: str) -> dict:
    project_store.delete(project_id)
    return {"ok": True}


@app.post("/api/simulate")
async def simulate(req: SimulateRequest) -> EventSourceResponse:
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def progress_cb(msg: str) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, ("progress", msg))

    async def runner() -> None:
        try:
            result = await asyncio.to_thread(
                run_simulation, req.nodes, req.params, req.trials_per_link, progress_cb
            )
            loop.call_soon_threadsafe(queue.put_nowait, ("result", result))
        except Exception as exc:  # surfaced to the client as an SSE error event
            loop.call_soon_threadsafe(queue.put_nowait, ("error", str(exc)))

    task = asyncio.create_task(runner())

    async def event_gen():
        try:
            while True:
                kind, payload = await queue.get()
                if kind == "progress":
                    yield {"event": "progress", "data": payload}
                elif kind == "result":
                    yield {"event": "result", "data": payload.model_dump_json()}
                    break
                elif kind == "error":
                    yield {"event": "error", "data": json.dumps({"message": payload})}
                    break
        finally:
            await task

    return EventSourceResponse(event_gen())
