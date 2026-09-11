"""Read-only smoke test: run TraceabilityService + response validation against
the REAL configured database (Supabase). Issues ONLY SELECT queries.

Usage:  ../venv/bin/python scripts/smoke_traceability.py
"""
import asyncio
import sys

from sqlalchemy import select

from app.database import AsyncSessionLocal


async def main() -> int:
    from app.models import ProjectModel
    from app.schemas import TraceabilityResponse
    from app.traceability_service import TraceabilityService

    async with AsyncSessionLocal() as session:
        res = await session.execute(select(ProjectModel.id).order_by(ProjectModel.created_at))
        project_ids = [row[0] for row in res.all()]
        print(f"projects in DB: {len(project_ids)}")

        all_ok = True
        for pid in project_ids[:6]:
            try:
                # Fresh nested transaction per project so one failure cannot
                # poison the rest of the run.
                async with session.begin_nested():
                    matrix = await TraceabilityService.build_traceability(str(pid), session)
                validated = TraceabilityResponse(**matrix)  # same path FastAPI takes
                rows = matrix["rows"]
                traced = matrix["coverage"]["traced_requirements"]
                print(
                    f"[OK]   {str(pid)[:8]}… rows={len(rows)} traced={traced} "
                    f"stories={matrix['coverage']['total_user_stories']} "
                    f"sections_ref={len([k for r in rows for k in r['prd_sections']])} "
                    f"diagram_labels={[d['label'] for d in matrix['diagrams']][:3]}"
                )
                if validated.project_id != str(pid):
                    all_ok = False
            except Exception as exc:
                all_ok = False
                print(f"[FAIL] {str(pid)[:8]}… -> {type(exc).__name__}: {exc}")
        return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))