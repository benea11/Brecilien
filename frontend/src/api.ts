import type { Building, DectNode, GeocodeResult, MvSubstation, Params, Project, ProjectSummary, SimResult } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export async function getProject(id: string): Promise<Project> {
  const r = await fetch(`${API_BASE}/api/project/${id}`);
  if (!r.ok) throw new Error(`getProject failed: ${r.status}`);
  return r.json();
}

export async function saveProject(project: Project): Promise<Project> {
  const r = await fetch(`${API_BASE}/api/project`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(project),
  });
  if (!r.ok) throw new Error(`saveProject failed: ${r.status}`);
  return r.json();
}

export async function listProjects(): Promise<ProjectSummary[]> {
  const r = await fetch(`${API_BASE}/api/projects`);
  if (!r.ok) throw new Error(`listProjects failed: ${r.status}`);
  return r.json();
}

export async function deleteProject(id: string): Promise<void> {
  const r = await fetch(`${API_BASE}/api/project/${id}`, { method: "DELETE" });
  if (!r.ok) throw new Error(`deleteProject failed: ${r.status}`);
}

export async function geocode(query: string): Promise<GeocodeResult[]> {
  if (!query.trim()) return [];
  const r = await fetch(`${API_BASE}/api/geocode?${new URLSearchParams({ q: query })}`);
  if (!r.ok) throw new Error(`geocode failed: ${r.status}`);
  return r.json();
}

export async function getBuildings(
  minLat: number,
  minLon: number,
  maxLat: number,
  maxLon: number,
): Promise<Building[]> {
  const params = new URLSearchParams({
    min_lat: String(minLat),
    min_lon: String(minLon),
    max_lat: String(maxLat),
    max_lon: String(maxLon),
  });
  const r = await fetch(`${API_BASE}/api/buildings?${params}`);
  if (!r.ok) throw new Error(`getBuildings failed: ${r.status}`);
  return r.json();
}

export async function getMvSubstations(
  minLat: number,
  minLon: number,
  maxLat: number,
  maxLon: number,
): Promise<MvSubstation[]> {
  const params = new URLSearchParams({
    min_lat: String(minLat),
    min_lon: String(minLon),
    max_lat: String(maxLat),
    max_lon: String(maxLon),
  });
  const r = await fetch(`${API_BASE}/api/mv-substations?${params}`);
  if (!r.ok) throw new Error(`getMvSubstations failed: ${r.status}`);
  return r.json();
}

export async function generateReport(project: Project, result: SimResult): Promise<Blob> {
  const r = await fetch(`${API_BASE}/api/report`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project, result }),
  });
  if (!r.ok) throw new Error(`generateReport failed: ${r.status}`);
  return r.blob();
}

export interface SimulateHandlers {
  onProgress: (message: string) => void;
  onResult: (result: SimResult) => void;
  onError: (message: string) => void;
}

/** Streams the SSE response from POST /api/simulate by reading the fetch
 * body manually (the EventSource API can't send a POST body). Returns an
 * abort function the caller can use to cancel an in-flight run. */
export function runSimulation(
  nodes: DectNode[],
  params: Params,
  trialsPerLink: number,
  handlers: SimulateHandlers,
): () => void {
  const controller = new AbortController();

  (async () => {
    try {
      const resp = await fetch(`${API_BASE}/api/simulate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nodes, params, trials_per_link: trialsPerLink }),
        signal: controller.signal,
      });
      if (!resp.ok || !resp.body) {
        handlers.onError(`simulate failed: ${resp.status}`);
        return;
      }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      const dispatch = (raw: string) => {
        if (!raw.trim()) return;
        const lines = raw.split("\n");
        let event = "message";
        let data = "";
        for (const line of lines) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          else if (line.startsWith("data:")) data += line.slice(5).trim();
        }
        if (!data) return;
        if (event === "progress") handlers.onProgress(data);
        else if (event === "result") handlers.onResult(JSON.parse(data));
        else if (event === "error") handlers.onError(JSON.parse(data).message ?? data);
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        // sse-starlette terminates lines with \r\n; normalize to \n so the
        // \n\n event-boundary split below and the per-line "event:"/"data:"
        // parsing both work regardless of the server's line-ending choice.
        buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");

        const events = buffer.split("\n\n");
        buffer = events.pop() ?? "";
        events.forEach(dispatch);
      }
      // the stream can close right after the final event without a
      // trailing blank line -- flush whatever's left in the buffer too.
      buffer += decoder.decode().replace(/\r\n/g, "\n");
      dispatch(buffer);
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        handlers.onError(String(err));
      }
    }
  })();

  return () => controller.abort();
}
