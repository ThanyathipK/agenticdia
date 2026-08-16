"""
Clarification Question repository operations.
"""
import logging
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.lock_service import LockService
from app.models import (
    AuditResultModel,
    ClarificationQuestionModel,
    RequirementModel,
    UserStoryModel,
)
from app.repositories.base import as_uuid, serialize_clarification_question

logger = logging.getLogger(__name__)


class ClarificationQuestionRepository:
    """Handles Clarification Questions of the project."""

    @staticmethod
    async def _resolve_story_code(session: AsyncSession, story_id) -> Optional[str]:
        """Resolve a target user story UUID to its ticket code (US-xxx)."""
        if not story_id:
            return None
        stmt_code = select(UserStoryModel.ticket_code).where(UserStoryModel.id == story_id)
        res_code = await session.execute(stmt_code)
        return res_code.scalar_one_or_none()

    @staticmethod
    async def _resolve_story_id(pid, session: AsyncSession, target_us: str) -> Optional[uuid.UUID]:
        """Resolve ``target_user_story_id`` exactly like the legacy logic.

        A string that parses as a UUID is used as-is (with an existence check);
        anything that is NOT a valid UUID is resolved as a ticket code (US-xxx).
        """
        if not target_us:
            return None
        try:
            story_uuid = uuid.UUID(str(target_us))
            stmt_us = select(UserStoryModel).where(UserStoryModel.id == story_uuid)
            res_us = await session.execute(stmt_us)
            us = res_us.scalar_one_or_none()
            if us:
                return us.id
            return None
        except ValueError:
            stmt_us = select(UserStoryModel).join(RequirementModel).where(
                UserStoryModel.ticket_code == str(target_us),
                RequirementModel.project_id == pid
            ).order_by(RequirementModel.version.desc())
            res_us = await session.execute(stmt_us)
            us = res_us.scalars().first()
            if us:
                return us.id
            return None

    @staticmethod
    async def create(project_id: str, data: Dict[str, Any], session: AsyncSession, requirement_id: Optional[uuid.UUID] = None) -> Dict[str, Any]:
        pid = as_uuid(project_id)

        # 1. Resolve requirement_id
        if requirement_id is None:
            stmt_req = select(RequirementModel).where(RequirementModel.project_id == pid).order_by(RequirementModel.version.desc())
            res_req = await session.execute(stmt_req)
            req = res_req.scalars().first()
            if not req:
                req = RequirementModel(
                    project_id=pid,
                    requirement_code="REQ-000",
                    title="Untitled Requirement",
                    status="active",
                    is_locked=False,
                    locked_by=None,
                    locked_at=None
                )
                session.add(req)
                await session.flush()
            requirement_id = req.id

        # 2. Find or create an AuditResultModel for this requirement
        stmt_ar = select(AuditResultModel).where(AuditResultModel.requirement_id == requirement_id)
        res_ar = await session.execute(stmt_ar)
        ar = res_ar.scalars().first()
        if not ar:
            ar = AuditResultModel(
                requirement_id=requirement_id,
                is_valid=False,
                audit_version_reviewed=1,
                passed_checks=[],
                failed_checks=[]
            )
            session.add(ar)
            await session.flush()

        # 3. Resolve target_user_story_id UUID
        target_us = data.get("target_user_story_id")
        story_id_val = await ClarificationQuestionRepository._resolve_story_id(pid, session, target_us)

        # LOCK ENFORCEMENT: Cannot add clarification questions to a locked user story
        if story_id_val:
            stmt_story = select(UserStoryModel).where(UserStoryModel.id == story_id_val)
            res_story = await session.execute(stmt_story)
            story = res_story.scalar_one_or_none()
            if story:
                LockService.raise_if_locked_model(
                    "user_story",
                    story,
                    message=f"User Story {story.ticket_code} is locked by {story.locked_by or 'unknown'}. Unlock it before adding clarification questions."
                )

        cq = ClarificationQuestionModel(
            audit_result_id=ar.id,
            checklist_category=data.get("checklist_category", "General"),
            target_user_story_id=story_id_val,
            question_text=data.get("question_text", ""),
            user_answer=data.get("user_answer"),
            is_resolved=data.get("is_resolved", False)
        )
        session.add(cq)
        await session.flush()
        await session.refresh(cq)

        ret_story_id = await ClarificationQuestionRepository._resolve_story_code(session, cq.target_user_story_id)
        if not ret_story_id:
            ret_story_id = target_us

        return serialize_clarification_question(cq, pid, ret_story_id)

    @staticmethod
    async def get_by_id(id_val: str, project_id: str, session: AsyncSession) -> Optional[Dict[str, Any]]:
        cqid = as_uuid(id_val)
        pid = as_uuid(project_id)
        stmt = select(ClarificationQuestionModel).join(
            AuditResultModel, ClarificationQuestionModel.audit_result_id == AuditResultModel.id
        ).join(
            RequirementModel, AuditResultModel.requirement_id == RequirementModel.id
        ).where(ClarificationQuestionModel.id == cqid, RequirementModel.project_id == pid)
        result = await session.execute(stmt)
        cq = result.scalar_one_or_none()
        if cq:
            ret_story_id = await ClarificationQuestionRepository._resolve_story_code(session, cq.target_user_story_id)
            return serialize_clarification_question(cq, pid, ret_story_id)
        return None

    @staticmethod
    async def get_by_project(project_id: str, session: AsyncSession, requirement_id: Optional[uuid.UUID] = None) -> List[Dict[str, Any]]:
        pid = as_uuid(project_id)
        if requirement_id is None:
            stmt_req = select(RequirementModel).where(RequirementModel.project_id == pid).order_by(RequirementModel.version.desc())
            res_req = await session.execute(stmt_req)
            req = res_req.scalars().first()
            if req:
                requirement_id = req.id

        if requirement_id:
            stmt = select(ClarificationQuestionModel).join(
                AuditResultModel, ClarificationQuestionModel.audit_result_id == AuditResultModel.id
            ).where(AuditResultModel.requirement_id == requirement_id)
        else:
            stmt = select(ClarificationQuestionModel).join(
                AuditResultModel, ClarificationQuestionModel.audit_result_id == AuditResultModel.id
            ).join(
                RequirementModel, AuditResultModel.requirement_id == RequirementModel.id
            ).where(RequirementModel.project_id == pid)

        result = await session.execute(stmt)
        records = result.scalars().all()

        out = []
        for cq in records:
            ret_story_id = await ClarificationQuestionRepository._resolve_story_code(session, cq.target_user_story_id)
            out.append(serialize_clarification_question(cq, pid, ret_story_id))
        return out

    @staticmethod
    async def update(id_val: str, project_id: str, updates: Dict[str, Any], session: AsyncSession) -> Optional[Dict[str, Any]]:
        cqid = as_uuid(id_val)
        pid = as_uuid(project_id)
        stmt = select(ClarificationQuestionModel).join(
            AuditResultModel, ClarificationQuestionModel.audit_result_id == AuditResultModel.id
        ).join(
            RequirementModel, AuditResultModel.requirement_id == RequirementModel.id
        ).where(ClarificationQuestionModel.id == cqid, RequirementModel.project_id == pid)
        result = await session.execute(stmt)
        cq = result.scalar_one_or_none()
        if cq:
            # LOCK ENFORCEMENT: Cannot update a locked clarification question
            LockService.raise_if_locked_model(
                "clarification_question",
                cq,
                message=f"Clarification Question is locked by {cq.locked_by or 'unknown'}. Unlock it before modifying."
            )
            if "checklist_category" in updates:
                cq.checklist_category = updates["checklist_category"]
            if "question_text" in updates:
                cq.question_text = updates["question_text"]
            if "user_answer" in updates:
                cq.user_answer = updates["user_answer"]
            if "is_resolved" in updates:
                cq.is_resolved = updates["is_resolved"]
            if "target_user_story_id" in updates:
                target_us = updates["target_user_story_id"]
                story_id_val = None
                if target_us:
                    try:
                        story_uuid = uuid.UUID(str(target_us))
                        story_id_val = story_uuid
                    except ValueError:
                        stmt_us = select(UserStoryModel).join(RequirementModel).where(
                            UserStoryModel.ticket_code == str(target_us),
                            RequirementModel.project_id == pid
                        ).order_by(RequirementModel.version.desc())
                        res_us = await session.execute(stmt_us)
                        us = res_us.scalars().first()
                        if us:
                            story_id_val = us.id
                cq.target_user_story_id = story_id_val

            await session.flush()
            await session.refresh(cq)

            ret_story_id = await ClarificationQuestionRepository._resolve_story_code(session, cq.target_user_story_id)

            return serialize_clarification_question(cq, pid, ret_story_id)
        return None

    @staticmethod
    async def delete(id_val: str, project_id: str, session: AsyncSession) -> bool:
        cqid = as_uuid(id_val)
        pid = as_uuid(project_id)
        stmt = select(ClarificationQuestionModel).join(
            AuditResultModel, ClarificationQuestionModel.audit_result_id == AuditResultModel.id
        ).join(
            RequirementModel, AuditResultModel.requirement_id == RequirementModel.id
        ).where(ClarificationQuestionModel.id == cqid, RequirementModel.project_id == pid)
        result = await session.execute(stmt)
        cq = result.scalar_one_or_none()
        if cq:
            # LOCK ENFORCEMENT: Cannot delete a locked clarification question
            LockService.raise_if_locked_model(
                "clarification_question",
                cq,
                message=f"Clarification Question is locked by {cq.locked_by or 'unknown'}. Unlock it before deleting."
            )
            await session.delete(cq)
            await session.flush()
            return True
        return False