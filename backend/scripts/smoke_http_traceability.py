"""Read-only end-to-end HTTP smoke: GET /api/project/{id}/traceability against
the REAL configured database via the FastAPI ASGI app (dependency override to a
live session — no server process needed). Issues only SELECTs.

Usage:  PYTHONPATH=. ../venv/bin/python scripts/smoke_http_traceability.py
"""
import asyncio
import sys

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.database import AsyncSessionLocal, get_db
from app.main import app
from app.models import ProjectModel


async def main() -> int:
    async with AsyncSessionLocal() as s:
        pid = (
            await s.execute(
                select(ProjectModel.id).order_by(ProjectModel.created_at).limit(1)
            )
        ).scalar_one()

    async def override():
        async with AsyncSessionLocal() as sess:
            yield sess

    app.dependency_overrides[get_db] = override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(f"/api/project/{pid}/traceability")
            body = resp.json()
            print(f"HTTP status: {resp.status_code}")
            print(f"project_id  : {body.get('project_id')}")
            print(f"rows        : {len(body.get('rows') or [])}")
            print(f"traced      : {(body.get('coverage') or {}).get('traced_requirements')}")
            print(f"diagrams    : {[d['label'] for d in body.get('diagrams') or []]}")
            return 0 if resp.status_code == 200 else 1
    finally:
        app.dependency_overrides.pop(get_db, None)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))