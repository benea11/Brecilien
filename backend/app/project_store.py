"""Minimal JSON-file project persistence -- one project per file, no
multi-user/auth concerns in scope for this planning tool."""
from __future__ import annotations

import json
from pathlib import Path

from .models import Project

PROJECTS_DIR = Path(__file__).resolve().parent.parent / ".projects"


def _path(project_id: str) -> Path:
    safe_id = "".join(c for c in project_id if c.isalnum() or c in "-_")
    return PROJECTS_DIR / f"{safe_id}.json"


def save(project: Project) -> None:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    _path(project.id).write_text(project.model_dump_json(indent=2))


def load(project_id: str) -> Project:
    path = _path(project_id)
    if not path.exists():
        raise FileNotFoundError(project_id)
    return Project.model_validate_json(path.read_text())


def delete(project_id: str) -> None:
    path = _path(project_id)
    if path.exists():
        path.unlink()


def list_projects() -> list[dict]:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for f in PROJECTS_DIR.glob("*.json"):
        try:
            p = Project.model_validate_json(f.read_text())
            out.append({"id": p.id, "name": p.name})
        except Exception:
            continue
    return out
