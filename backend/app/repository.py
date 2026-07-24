import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func

from app.database import AsyncSessionLocal
from app.models import (
    UserModel,
    ProjectModel,
    RequirementStateModel,
    EpicModel,
    RequirementModel,
    UserStoryModel,
    AcceptanceCriteriaModel,
    ClarificationQuestionModel,
    AuditResultModel,
    PRDDocumentModel,
    VersionHistoryModel,
    ConversationMessageModel,
    PendingActionModel
)

logger = logging.getLogger("app.repository")

class ProjectRepository:
    """
    Handles project-level operations.
    """
    @staticmethod
    async def list_all(session: AsyncSession) -> List[Dict[str, Any]]:
        stmt = select(ProjectModel)
        result = await session.execute(stmt)
        projects = result.scalars().all()
        return [
            {
                "id": str(p.id),
                "name": p.name,
                "description": p.description,
                "industry_standard": p.industry_standard
            }
            for p in projects
        ]

    @staticmethod
    async def create_project(project_data: Dict[str, Any], session: AsyncSession) -> Dict[str, Any]:
        user_id = project_data.get("user_id")
        if not user_id:
            # Resolve to standard seeded default system user
            user_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
        else:
            user_id = uuid.UUID(str(user_id))
            
        project = ProjectModel(
            id=uuid.UUID(str(project_data["id"])) if "id" in project_data else uuid.uuid4(),
            user_id=user_id,
            name=project_data["name"],
            description=project_data.get("description"),
            industry_standard=project_data.get("industry_standard", "Generic")
        )
        session.add(project)
        await session.flush()
        
        # Initialize requirement state
        req_state = RequirementStateModel(
            project_id=project.id,
            project_name=project.name
        )
        session.add(req_state)
        
        await session.flush()
        await session.refresh(project)
        return {"id": str(project.id), "name": project.name}

    @staticmethod
    async def create(project_data: Dict[str, Any], session: AsyncSession) -> Dict[str, Any]:
        return await ProjectRepository.create_project(project_data, session)

    @staticmethod
    async def get_by_id(project_id: str, session: AsyncSession) -> Optional[Dict[str, Any]]:
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        stmt = select(ProjectModel).where(ProjectModel.id == pid)
        result = await session.execute(stmt)
        p = result.scalar_one_or_none()
        if p:
            return {
                "id": str(p.id),
                "name": p.name,
                "description": p.description,
                "industry_standard": p.industry_standard
            }
        return None

    @staticmethod
    async def get_by_project(project_id: str, session: AsyncSession) -> Optional[Dict[str, Any]]:
        return await ProjectRepository.get_by_id(project_id, session)

    @staticmethod
    async def update(project_id: str, updates: Dict[str, Any], session: AsyncSession) -> Optional[Dict[str, Any]]:
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        stmt = select(ProjectModel).where(ProjectModel.id == pid)
        result = await session.execute(stmt)
        p = result.scalar_one_or_none()
        if p:
            if "name" in updates:
                p.name = updates["name"]
            if "description" in updates:
                p.description = updates["description"]
            if "industry_standard" in updates:
                p.industry_standard = updates["industry_standard"]
            await session.flush()
            await session.refresh(p)
            return {
                "id": str(p.id),
                "name": p.name,
                "description": p.description,
                "industry_standard": p.industry_standard
            }
        return None

    @staticmethod
    async def delete(project_id: str, session: AsyncSession) -> bool:
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        stmt = select(ProjectModel).where(ProjectModel.id == pid)
        result = await session.execute(stmt)
        p = result.scalar_one_or_none()
        if p:
            await session.delete(p)
            await session.flush()
            return True
        return False

class EpicRepository:
    """
    Handles Epics of the project.
    """
    @staticmethod
    async def get_active_by_project(project_id: str, session: AsyncSession) -> Optional[Dict[str, Any]]:
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        stmt = select(EpicModel).where(EpicModel.project_id == pid, EpicModel.status == "active").order_by(EpicModel.updated_at.desc())
        result = await session.execute(stmt)
        epic = result.scalars().first()
        if epic:
            return {
                "id": str(epic.id),
                "project_id": str(epic.project_id),
                "epic_name": epic.epic_name,
                "version": epic.version,
                "status": epic.status
            }
        return None

    @staticmethod
    async def save_or_update_epic(project_id: str, epic_name: str, session: AsyncSession, version: int = 1) -> Dict[str, Any]:
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        stmt = select(EpicModel).where(EpicModel.project_id == pid, EpicModel.status == "active").order_by(EpicModel.updated_at.desc())
        result = await session.execute(stmt)
        epic = result.scalars().first()
        
        name_to_use = epic_name.strip() if (epic_name and epic_name.strip()) else "Untitled Epic"
        if epic:
            if epic_name and epic_name.strip():
                epic.epic_name = name_to_use
            epic.version = version
            await session.flush()
            await session.refresh(epic)
        else:
            epic = EpicModel(
                project_id=pid,
                epic_name=name_to_use,
                version=version,
                status="active"
            )
            session.add(epic)
            await session.flush()
            await session.refresh(epic)
            
        return {
            "id": str(epic.id),
            "project_id": str(epic.project_id),
            "epic_name": epic.epic_name,
            "version": epic.version,
            "status": epic.status
        }

    @staticmethod
    async def create(project_id: str, data: Dict[str, Any], session: AsyncSession) -> Dict[str, Any]:
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        epic = EpicModel(
            project_id=pid,
            epic_name=data.get("epic_name", "Untitled Epic"),
            version=data.get("version", 1)
        )
        session.add(epic)
        await session.flush()
        await session.refresh(epic)
        return {
            "id": str(epic.id),
            "project_id": str(epic.project_id),
            "epic_name": epic.epic_name,
            "version": epic.version
        }

    @staticmethod
    async def get_by_id(id_val: str, project_id: str, session: AsyncSession) -> Optional[Dict[str, Any]]:
        eid = uuid.UUID(id_val) if isinstance(id_val, str) else id_val
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        stmt = select(EpicModel).where(EpicModel.id == eid, EpicModel.project_id == pid)
        result = await session.execute(stmt)
        epic = result.scalar_one_or_none()
        if epic:
            return {
                "id": str(epic.id),
                "project_id": str(epic.project_id),
                "epic_name": epic.epic_name,
                "version": epic.version
            }
        return None

    @staticmethod
    async def get_by_project(project_id: str, session: AsyncSession) -> List[Dict[str, Any]]:
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        stmt = select(EpicModel).where(EpicModel.project_id == pid)
        result = await session.execute(stmt)
        epics = result.scalars().all()
        return [
            {
                "id": str(e.id),
                "project_id": str(e.project_id),
                "epic_name": e.epic_name,
                "version": e.version
            }
            for e in epics
        ]

    @staticmethod
    async def update(id_val: str, project_id: str, updates: Dict[str, Any], session: AsyncSession) -> Optional[Dict[str, Any]]:
        eid = uuid.UUID(id_val) if isinstance(id_val, str) else id_val
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        stmt = select(EpicModel).where(EpicModel.id == eid, EpicModel.project_id == pid)
        result = await session.execute(stmt)
        epic = result.scalar_one_or_none()
        if epic:
            if "epic_name" in updates:
                epic.epic_name = updates["epic_name"]
            if "version" in updates:
                epic.version = updates["version"]
            await session.flush()
            await session.refresh(epic)
            return {
                "id": str(epic.id),
                "project_id": str(epic.project_id),
                "epic_name": epic.epic_name,
                "version": epic.version
            }
        return None

    @staticmethod
    async def delete(id_val: str, project_id: str, session: AsyncSession) -> bool:
        eid = uuid.UUID(id_val) if isinstance(id_val, str) else id_val
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        stmt = select(EpicModel).where(EpicModel.id == eid, EpicModel.project_id == pid)
        result = await session.execute(stmt)
        epic = result.scalar_one_or_none()
        if epic:
            await session.delete(epic)
            await session.flush()
            return True
        return False

class RequirementRepository:
    """
    Handles atomic requirements of the project.
    """
    @staticmethod
    async def create(project_id: str, data: Dict[str, Any], session: AsyncSession) -> Dict[str, Any]:
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        req = RequirementModel(
            project_id=pid,
            epic_id=uuid.UUID(data["epic_id"]) if data.get("epic_id") else None,
            requirement_code=data.get("requirement_code", "REQ-000"),
            title=data.get("title", "Untitled Requirement"),
            description=data.get("description"),
            priority=data.get("priority"),
            status=data.get("status", "active")
        )
        session.add(req)
        await session.flush()
        await session.refresh(req)
        return {
            "id": str(req.id),
            "project_id": str(req.project_id),
            "epic_id": str(req.epic_id) if req.epic_id else None,
            "requirement_code": req.requirement_code,
            "title": req.title,
            "description": req.description,
            "priority": req.priority,
            "status": req.status
        }

    @staticmethod
    async def get_by_id(id_val: str, project_id: str, session: AsyncSession) -> Optional[Dict[str, Any]]:
        rid = uuid.UUID(id_val) if isinstance(id_val, str) else id_val
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        stmt = select(RequirementModel).where(RequirementModel.id == rid, RequirementModel.project_id == pid)
        result = await session.execute(stmt)
        req = result.scalar_one_or_none()
        if req:
            return {
                "id": str(req.id),
                "project_id": str(req.project_id),
                "epic_id": str(req.epic_id) if req.epic_id else None,
                "requirement_code": req.requirement_code,
                "title": req.title,
                "description": req.description,
                "priority": req.priority,
                "status": req.status
            }
        return None

    @staticmethod
    async def get_by_project(project_id: str, session: AsyncSession) -> List[Dict[str, Any]]:
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        stmt = select(RequirementModel).where(RequirementModel.project_id == pid)
        result = await session.execute(stmt)
        reqs = result.scalars().all()
        return [
            {
                "id": str(r.id),
                "project_id": str(r.project_id),
                "epic_id": str(r.epic_id) if r.epic_id else None,
                "requirement_code": r.requirement_code,
                "title": r.title,
                "description": r.description,
                "priority": r.priority,
                "status": r.status
            }
            for r in reqs
        ]

    @staticmethod
    async def update(id_val: str, project_id: str, updates: Dict[str, Any], session: AsyncSession) -> Optional[Dict[str, Any]]:
        rid = uuid.UUID(id_val) if isinstance(id_val, str) else id_val
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        stmt = select(RequirementModel).where(RequirementModel.id == rid, RequirementModel.project_id == pid)
        result = await session.execute(stmt)
        req = result.scalar_one_or_none()
        if req:
            if "title" in updates: req.title = updates["title"]
            if "description" in updates: req.description = updates["description"]
            if "priority" in updates: req.priority = updates["priority"]
            if "status" in updates: req.status = updates["status"]
            await session.flush()
            await session.refresh(req)
            return {
                "id": str(req.id),
                "project_id": str(req.project_id),
                "epic_id": str(req.epic_id) if req.epic_id else None,
                "requirement_code": req.requirement_code,
                "title": req.title,
                "description": req.description,
                "priority": req.priority,
                "status": req.status
            }
        return None

    @staticmethod
    async def delete(id_val: str, project_id: str, session: AsyncSession) -> bool:
        rid = uuid.UUID(id_val) if isinstance(id_val, str) else id_val
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        stmt = select(RequirementModel).where(RequirementModel.id == rid, RequirementModel.project_id == pid)
        result = await session.execute(stmt)
        req = result.scalar_one_or_none()
        if req:
            req.status = "deleted"
            # Archive User Stories and Acceptance Criteria related to that Requirement
            stmt_stories = select(UserStoryModel).where(UserStoryModel.requirement_id == rid)
            res_stories = await session.execute(stmt_stories)
            stories = res_stories.scalars().all()
            for story in stories:
                story.status = "archived"
                story.change_type = "archived"
                story.version = story.version + 1
                
                stmt_ac = select(AcceptanceCriteriaModel).where(AcceptanceCriteriaModel.user_story_id == story.id)
                res_ac = await session.execute(stmt_ac)
                ac_list = res_ac.scalars().all()
                for ac in ac_list:
                    ac.status = "archived"
                    ac.change_type = "archived"
                    ac.version = ac.version + 1

            await session.flush()
            return True
        return False

class UserStoryRepository:
    """
    Handles Agile User Stories of the project.
    """
    @staticmethod
    async def generate_unique_ticket_code(project_id: uuid.UUID, session: AsyncSession) -> str:
        stmt = select(UserStoryModel.ticket_code).where(UserStoryModel.project_id == project_id)
        res = await session.execute(stmt)
        codes = res.scalars().all()
        
        max_num = 0
        for code in codes:
            if code and code.startswith("US-"):
                try:
                    num = int(code.split("-")[1])
                    if num > max_num:
                        max_num = num
                except (ValueError, IndexError):
                    pass
        
        new_num = max_num + 1
        return f"US-{new_num:03d}"

    @staticmethod
    async def save_or_update(project_id: str, data: Dict[str, Any], session: AsyncSession, requirement_id: Optional[uuid.UUID] = None) -> Dict[str, Any]:
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        
        if requirement_id is None:
            # 1. Resolve requirement_id for this project
            stmt = select(RequirementModel).where(RequirementModel.project_id == pid).order_by(RequirementModel.version.desc())
            res = await session.execute(stmt)
            req = res.scalars().first()
            if not req:
                req = RequirementModel(project_id=pid, epic_name="Untitled Epic")
                session.add(req)
                await session.flush()
            requirement_id = req.id

        ticket_code = data.get("ticket_code")
        story_title = data.get("story_title", "Untitled Story")
        
        # Check if story already exists by (requirement_id and ticket_code) OR (requirement_id and story_title)
        story = None
        if ticket_code and ticket_code != "US-000":
            stmt = select(UserStoryModel).where(
                UserStoryModel.requirement_id == requirement_id,
                UserStoryModel.ticket_code == ticket_code
            )
            res = await session.execute(stmt)
            story = res.scalars().first()
            
        if not story:
            stmt = select(UserStoryModel).where(
                UserStoryModel.requirement_id == requirement_id,
                UserStoryModel.story_title == story_title
            )
            res = await session.execute(stmt)
            story = res.scalars().first()
            
        # If no ticket_code is provided or it is a placeholder/invalid, generate a unique one!
        if not ticket_code or ticket_code == "US-000":
            if story and story.ticket_code and story.ticket_code != "US-000":
                ticket_code = story.ticket_code
            else:
                ticket_code = await UserStoryRepository.generate_unique_ticket_code(pid, session)
        
        if story:
            # Update existing story
            story.ticket_code = ticket_code
            story.story_title = story_title
            story.as_a = data.get("as_a", story.as_a)
            story.i_want_to = data.get("i_want_to", story.i_want_to)
            story.so_that = data.get("so_that", story.so_that)
            story.project_id = pid
            story.status = data.get("status", story.status)
            story.version = data.get("version", story.version)
            story.last_modified_by = data.get("last_modified_by", story.last_modified_by)
            story.change_type = data.get("change_type", story.change_type)
            await session.flush()
        else:
            # Create a brand new story
            story = UserStoryModel(
                project_id=pid,
                requirement_id=requirement_id,
                ticket_code=ticket_code,
                story_title=story_title,
                as_a=data.get("as_a", ""),
                i_want_to=data.get("i_want_to", ""),
                so_that=data.get("so_that", ""),
                status=data.get("status", "active"),
                version=data.get("version", 1),
                last_modified_by=data.get("last_modified_by", "automated_agent"),
                change_type=data.get("change_type", "created")
            )
            session.add(story)
            await session.flush()
            
        await session.refresh(story)
        return {
            "id": str(story.id),
            "project_id": str(pid),
            "ticket_code": story.ticket_code,
            "story_title": story.story_title,
            "as_a": story.as_a,
            "i_want_to": story.i_want_to,
            "so_that": story.so_that,
            "status": story.status,
            "version": story.version,
            "last_modified_by": story.last_modified_by,
            "change_type": story.change_type
        }

    @staticmethod
    async def create(project_id: str, data: Dict[str, Any], session: AsyncSession, requirement_id: Optional[uuid.UUID] = None) -> Dict[str, Any]:
        return await UserStoryRepository.save_or_update(project_id, data, session, requirement_id=requirement_id)

    @staticmethod
    async def get_by_id(id_val: str, project_id: str, session: AsyncSession) -> Optional[Dict[str, Any]]:
        sid = uuid.UUID(id_val) if isinstance(id_val, str) else id_val
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        stmt = select(UserStoryModel).join(RequirementModel).where(
            UserStoryModel.id == sid, 
            RequirementModel.project_id == pid
        )
        result = await session.execute(stmt)
        story = result.scalar_one_or_none()
        if story:
            return {
                "id": str(story.id),
                "project_id": str(pid),
                "ticket_code": story.ticket_code,
                "story_title": story.story_title,
                "as_a": story.as_a,
                "i_want_to": story.i_want_to,
                "so_that": story.so_that,
                "status": story.status,
                "version": story.version,
                "last_modified_by": story.last_modified_by,
                "change_type": story.change_type
            }
        return None

    @staticmethod
    async def get_by_project(project_id: str, session: AsyncSession, requirement_id: Optional[uuid.UUID] = None) -> List[Dict[str, Any]]:
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        if requirement_id is None:
            stmt_req = select(RequirementModel).where(RequirementModel.project_id == pid).order_by(RequirementModel.version.desc())
            res_req = await session.execute(stmt_req)
            req = res_req.scalars().first()
            if req:
                requirement_id = req.id
                
        if requirement_id:
            stmt = select(UserStoryModel).where(UserStoryModel.requirement_id == requirement_id)
        else:
            stmt = select(UserStoryModel).join(RequirementModel).where(RequirementModel.project_id == pid)
            
        result = await session.execute(stmt)
        stories = result.scalars().all()
        return [
            {
                "id": str(s.id),
                "project_id": str(pid),
                "ticket_code": s.ticket_code,
                "story_title": s.story_title,
                "as_a": s.as_a,
                "i_want_to": s.i_want_to,
                "so_that": s.so_that,
                "status": s.status,
                "version": s.version,
                "last_modified_by": s.last_modified_by,
                "change_type": s.change_type
            }
            for s in stories
        ]

    @staticmethod
    async def update(id_val: str, project_id: str, updates: Dict[str, Any], session: AsyncSession) -> Optional[Dict[str, Any]]:
        sid = uuid.UUID(id_val) if isinstance(id_val, str) else id_val
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        stmt = select(UserStoryModel).join(RequirementModel).where(
            UserStoryModel.id == sid, 
            RequirementModel.project_id == pid
        )
        result = await session.execute(stmt)
        story = result.scalar_one_or_none()
        if story:
            if "ticket_code" in updates:
                story.ticket_code = updates["ticket_code"]
            if "story_title" in updates:
                story.story_title = updates["story_title"]
            if "as_a" in updates:
                story.as_a = updates["as_a"]
            if "i_want_to" in updates:
                story.i_want_to = updates["i_want_to"]
            if "so_that" in updates:
                story.so_that = updates["so_that"]
            if "status" in updates:
                story.status = updates["status"]
            if "version" in updates:
                story.version = updates["version"]
            if "last_modified_by" in updates:
                story.last_modified_by = updates["last_modified_by"]
            if "change_type" in updates:
                story.change_type = updates["change_type"]
            await session.flush()
            await session.refresh(story)
            return {
                "id": str(story.id),
                "project_id": str(pid),
                "ticket_code": story.ticket_code,
                "story_title": story.story_title,
                "as_a": story.as_a,
                "i_want_to": story.i_want_to,
                "so_that": story.so_that,
                "status": story.status,
                "version": story.version,
                "last_modified_by": story.last_modified_by,
                "change_type": story.change_type
            }
        return None

    @staticmethod
    async def delete(id_val: str, project_id: str, session: AsyncSession) -> bool:
        sid = uuid.UUID(id_val) if isinstance(id_val, str) else id_val
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        stmt = select(UserStoryModel).join(RequirementModel).where(
            UserStoryModel.id == sid, 
            RequirementModel.project_id == pid
        )
        result = await session.execute(stmt)
        story = result.scalar_one_or_none()
        if story:
            await session.delete(story)
            await session.flush()
            return True
        return False

class AcceptanceCriteriaRepository:
    """
    Handles Agile Acceptance Criteria of the project.
    """
    @staticmethod
    async def create(project_id: str, data: Dict[str, Any], session: AsyncSession) -> Dict[str, Any]:
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        story_id = data.get("user_story_id")
        if story_id and isinstance(story_id, str):
            story_id = uuid.UUID(story_id)
        ac = AcceptanceCriteriaModel(
            user_story_id=story_id,
            criteria_text=data.get("criteria_text", ""),
            status=data.get("status", "active"),
            version=data.get("version", 1),
            last_modified_by=data.get("last_modified_by", "automated_agent"),
            change_type=data.get("change_type", "created")
        )
        session.add(ac)
        await session.flush()
        await session.refresh(ac)
        return {
            "id": str(ac.id),
            "project_id": str(pid),
            "ticket_code": data.get("ticket_code"),
            "user_story_id": str(ac.user_story_id) if ac.user_story_id else None,
            "criteria_text": ac.criteria_text,
            "status": ac.status,
            "version": ac.version,
            "last_modified_by": ac.last_modified_by,
            "change_type": ac.change_type
        }

    @staticmethod
    async def get_by_id(id_val: str, project_id: str, session: AsyncSession) -> Optional[Dict[str, Any]]:
        acid = uuid.UUID(id_val) if isinstance(id_val, str) else id_val
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        stmt = select(AcceptanceCriteriaModel, UserStoryModel.ticket_code).join(
            UserStoryModel, AcceptanceCriteriaModel.user_story_id == UserStoryModel.id
        ).join(
            RequirementModel, UserStoryModel.requirement_id == RequirementModel.id
        ).where(AcceptanceCriteriaModel.id == acid, RequirementModel.project_id == pid)
        result = await session.execute(stmt)
        record = result.first()
        if record:
            ac, ticket_code = record
            return {
                "id": str(ac.id),
                "project_id": str(pid),
                "ticket_code": ticket_code,
                "user_story_id": str(ac.user_story_id) if ac.user_story_id else None,
                "criteria_text": ac.criteria_text,
                "status": ac.status,
                "version": ac.version,
                "last_modified_by": ac.last_modified_by,
                "change_type": ac.change_type
            }
        return None

    @staticmethod
    async def get_by_project(project_id: str, session: AsyncSession, requirement_id: Optional[uuid.UUID] = None) -> List[Dict[str, Any]]:
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        if requirement_id is None:
            stmt_req = select(RequirementModel).where(RequirementModel.project_id == pid).order_by(RequirementModel.version.desc())
            res_req = await session.execute(stmt_req)
            req = res_req.scalars().first()
            if req:
                requirement_id = req.id
                
        if requirement_id:
            stmt = select(AcceptanceCriteriaModel, UserStoryModel.ticket_code).join(
                UserStoryModel, AcceptanceCriteriaModel.user_story_id == UserStoryModel.id
            ).where(UserStoryModel.requirement_id == requirement_id)
        else:
            stmt = select(AcceptanceCriteriaModel, UserStoryModel.ticket_code).join(
                UserStoryModel, AcceptanceCriteriaModel.user_story_id == UserStoryModel.id
            ).join(
                RequirementModel, UserStoryModel.requirement_id == RequirementModel.id
            ).where(RequirementModel.project_id == pid)
            
        result = await session.execute(stmt)
        records = result.all()
        return [
            {
                "id": str(ac.id),
                "project_id": str(pid),
                "ticket_code": ticket_code,
                "user_story_id": str(ac.user_story_id) if ac.user_story_id else None,
                "criteria_text": ac.criteria_text,
                "status": ac.status,
                "version": ac.version,
                "last_modified_by": ac.last_modified_by,
                "change_type": ac.change_type
            }
            for ac, ticket_code in records
        ]

    @staticmethod
    async def update(id_val: str, project_id: str, updates: Dict[str, Any], session: AsyncSession) -> Optional[Dict[str, Any]]:
        acid = uuid.UUID(id_val) if isinstance(id_val, str) else id_val
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        stmt = select(AcceptanceCriteriaModel).join(
            UserStoryModel, AcceptanceCriteriaModel.user_story_id == UserStoryModel.id
        ).join(
            RequirementModel, UserStoryModel.requirement_id == RequirementModel.id
        ).where(AcceptanceCriteriaModel.id == acid, RequirementModel.project_id == pid)
        result = await session.execute(stmt)
        ac = result.scalar_one_or_none()
        if ac:
            if "criteria_text" in updates:
                ac.criteria_text = updates["criteria_text"]
            if "user_story_id" in updates:
                story_id = updates["user_story_id"]
                ac.user_story_id = uuid.UUID(story_id) if story_id else None
            if "status" in updates:
                ac.status = updates["status"]
            if "version" in updates:
                ac.version = updates["version"]
            if "last_modified_by" in updates:
                ac.last_modified_by = updates["last_modified_by"]
            if "change_type" in updates:
                ac.change_type = updates["change_type"]
            await session.flush()
            await session.refresh(ac)
            
            stmt_code = select(UserStoryModel.ticket_code).where(UserStoryModel.id == ac.user_story_id)
            res_code = await session.execute(stmt_code)
            ticket_code = res_code.scalar_one_or_none()
            
            return {
                "id": str(ac.id),
                "project_id": str(pid),
                "ticket_code": ticket_code,
                "user_story_id": str(ac.user_story_id) if ac.user_story_id else None,
                "criteria_text": ac.criteria_text,
                "status": ac.status,
                "version": ac.version,
                "last_modified_by": ac.last_modified_by,
                "change_type": ac.change_type
            }
        return None

    @staticmethod
    async def delete(id_val: str, project_id: str, session: AsyncSession) -> bool:
        acid = uuid.UUID(id_val) if isinstance(id_val, str) else id_val
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        stmt = select(AcceptanceCriteriaModel).join(
            UserStoryModel, AcceptanceCriteriaModel.user_story_id == UserStoryModel.id
        ).join(
            RequirementModel, UserStoryModel.requirement_id == RequirementModel.id
        ).where(AcceptanceCriteriaModel.id == acid, RequirementModel.project_id == pid)
        result = await session.execute(stmt)
        ac = result.scalar_one_or_none()
        if ac:
            await session.delete(ac)
            await session.flush()
            return True
        return False

class ClarificationQuestionRepository:
    """
    Handles Clarification Questions of the project.
    """
    @staticmethod
    async def create(project_id: str, data: Dict[str, Any], session: AsyncSession, requirement_id: Optional[uuid.UUID] = None) -> Dict[str, Any]:
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        
        # 1. Resolve requirement_id
        if requirement_id is None:
            stmt_req = select(RequirementModel).where(RequirementModel.project_id == pid).order_by(RequirementModel.version.desc())
            res_req = await session.execute(stmt_req)
            req = res_req.scalars().first()
            if not req:
                req = RequirementModel(project_id=pid, epic_name="Untitled Epic")
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
        story_id_val = None
        target_us = data.get("target_user_story_id")
        if target_us:
            try:
                story_uuid = uuid.UUID(str(target_us))
                stmt_us = select(UserStoryModel).where(UserStoryModel.id == story_uuid)
                res_us = await session.execute(stmt_us)
                us = res_us.scalar_one_or_none()
                if us:
                    story_id_val = us.id
            except ValueError:
                stmt_us = select(UserStoryModel).join(RequirementModel).where(
                    UserStoryModel.ticket_code == str(target_us),
                    RequirementModel.project_id == pid
                ).order_by(RequirementModel.version.desc())
                res_us = await session.execute(stmt_us)
                us = res_us.scalars().first()
                if us:
                    story_id_val = us.id
                    
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
        
        ret_story_id = None
        if cq.target_user_story_id:
            stmt_code = select(UserStoryModel.ticket_code).where(UserStoryModel.id == cq.target_user_story_id)
            res_code = await session.execute(stmt_code)
            ret_story_id = res_code.scalar_one_or_none()
        if not ret_story_id:
            ret_story_id = target_us
            
        return {
            "id": str(cq.id),
            "project_id": str(pid),
            "checklist_category": cq.checklist_category,
            "target_user_story_id": ret_story_id,
            "question_text": cq.question_text,
            "user_answer": cq.user_answer,
            "is_resolved": cq.is_resolved
        }

    @staticmethod
    async def get_by_id(id_val: str, project_id: str, session: AsyncSession) -> Optional[Dict[str, Any]]:
        cqid = uuid.UUID(id_val) if isinstance(id_val, str) else id_val
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        stmt = select(ClarificationQuestionModel).join(
            AuditResultModel, ClarificationQuestionModel.audit_result_id == AuditResultModel.id
        ).join(
            RequirementModel, AuditResultModel.requirement_id == RequirementModel.id
        ).where(ClarificationQuestionModel.id == cqid, RequirementModel.project_id == pid)
        result = await session.execute(stmt)
        cq = result.scalar_one_or_none()
        if cq:
            ret_story_id = None
            if cq.target_user_story_id:
                stmt_code = select(UserStoryModel.ticket_code).where(UserStoryModel.id == cq.target_user_story_id)
                res_code = await session.execute(stmt_code)
                ret_story_id = res_code.scalar_one_or_none()
            return {
                "id": str(cq.id),
                "project_id": str(pid),
                "checklist_category": cq.checklist_category,
                "target_user_story_id": ret_story_id,
                "question_text": cq.question_text,
                "user_answer": cq.user_answer,
                "is_resolved": cq.is_resolved
            }
        return None

    @staticmethod
    async def get_by_project(project_id: str, session: AsyncSession, requirement_id: Optional[uuid.UUID] = None) -> List[Dict[str, Any]]:
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
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
            ret_story_id = None
            if cq.target_user_story_id:
                stmt_code = select(UserStoryModel.ticket_code).where(UserStoryModel.id == cq.target_user_story_id)
                res_code = await session.execute(stmt_code)
                ret_story_id = res_code.scalar_one_or_none()
            out.append({
                "id": str(cq.id),
                "project_id": str(pid),
                "checklist_category": cq.checklist_category,
                "target_user_story_id": ret_story_id,
                "question_text": cq.question_text,
                "user_answer": cq.user_answer,
                "is_resolved": cq.is_resolved
            })
        return out

    @staticmethod
    async def update(id_val: str, project_id: str, updates: Dict[str, Any], session: AsyncSession) -> Optional[Dict[str, Any]]:
        cqid = uuid.UUID(id_val) if isinstance(id_val, str) else id_val
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        stmt = select(ClarificationQuestionModel).join(
            AuditResultModel, ClarificationQuestionModel.audit_result_id == AuditResultModel.id
        ).join(
            RequirementModel, AuditResultModel.requirement_id == RequirementModel.id
        ).where(ClarificationQuestionModel.id == cqid, RequirementModel.project_id == pid)
        result = await session.execute(stmt)
        cq = result.scalar_one_or_none()
        if cq:
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
            
            ret_story_id = None
            if cq.target_user_story_id:
                stmt_code = select(UserStoryModel.ticket_code).where(UserStoryModel.id == cq.target_user_story_id)
                res_code = await session.execute(stmt_code)
                ret_story_id = res_code.scalar_one_or_none()
                
            return {
                "id": str(cq.id),
                "project_id": str(pid),
                "checklist_category": cq.checklist_category,
                "target_user_story_id": ret_story_id,
                "question_text": cq.question_text,
                "user_answer": cq.user_answer,
                "is_resolved": cq.is_resolved
            }
        return None

    @staticmethod
    async def delete(id_val: str, project_id: str, session: AsyncSession) -> bool:
        cqid = uuid.UUID(id_val) if isinstance(id_val, str) else id_val
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        stmt = select(ClarificationQuestionModel).join(
            AuditResultModel, ClarificationQuestionModel.audit_result_id == AuditResultModel.id
        ).join(
            RequirementModel, AuditResultModel.requirement_id == RequirementModel.id
        ).where(ClarificationQuestionModel.id == cqid, RequirementModel.project_id == pid)
        result = await session.execute(stmt)
        cq = result.scalar_one_or_none()
        if cq:
            await session.delete(cq)
            await session.flush()
            return True
        return False

class AuditResultRepository:
    """
    Handles Audit Results of the project.
    """
    @staticmethod
    async def create(project_id: str, data: Dict[str, Any], session: AsyncSession, requirement_id: Optional[uuid.UUID] = None) -> Dict[str, Any]:
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        
        if requirement_id is None:
            stmt = select(RequirementModel).where(RequirementModel.project_id == pid).order_by(RequirementModel.version.desc())
            res = await session.execute(stmt)
            req = res.scalars().first()
            if not req:
                req = RequirementModel(project_id=pid, epic_name="Untitled Epic")
                session.add(req)
                await session.flush()
            requirement_id = req.id
            
        ar = AuditResultModel(
            requirement_id=requirement_id,
            is_valid=data.get("is_valid", False),
            audit_version_reviewed=data.get("audit_version_reviewed", 1),
            passed_checks=data.get("passed_checks", []),
            failed_checks=data.get("failed_checks", [])
        )
        session.add(ar)
        await session.flush()
        await session.refresh(ar)
        return {
            "id": str(ar.id),
            "project_id": str(pid),
            "is_valid": ar.is_valid,
            "audit_version_reviewed": ar.audit_version_reviewed,
            "passed_checks": ar.passed_checks,
            "failed_checks": ar.failed_checks
        }

    @staticmethod
    async def get_by_id(id_val: str, project_id: str, session: AsyncSession) -> Optional[Dict[str, Any]]:
        arid = uuid.UUID(id_val) if isinstance(id_val, str) else id_val
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        stmt = select(AuditResultModel).join(RequirementModel).where(
            AuditResultModel.id == arid, 
            RequirementModel.project_id == pid
        )
        result = await session.execute(stmt)
        ar = result.scalar_one_or_none()
        if ar:
            return {
                "id": str(ar.id),
                "project_id": str(pid),
                "is_valid": ar.is_valid,
                "audit_version_reviewed": ar.audit_version_reviewed,
                "passed_checks": ar.passed_checks,
                "failed_checks": ar.failed_checks
            }
        return None

    @staticmethod
    async def get_by_project(project_id: str, session: AsyncSession, requirement_id: Optional[uuid.UUID] = None) -> List[Dict[str, Any]]:
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        if requirement_id is None:
            stmt_req = select(RequirementModel).where(RequirementModel.project_id == pid).order_by(RequirementModel.version.desc())
            res_req = await session.execute(stmt_req)
            req = res_req.scalars().first()
            if req:
                requirement_id = req.id
                
        if requirement_id:
            stmt = select(AuditResultModel).where(AuditResultModel.requirement_id == requirement_id)
        else:
            stmt = select(AuditResultModel).join(RequirementModel).where(RequirementModel.project_id == pid)
            
        result = await session.execute(stmt)
        records = result.scalars().all()
        return [
            {
                "id": str(ar.id),
                "project_id": str(pid),
                "is_valid": ar.is_valid,
                "audit_version_reviewed": ar.audit_version_reviewed,
                "passed_checks": ar.passed_checks,
                "failed_checks": ar.failed_checks
            }
            for ar in records
        ]

    @staticmethod
    async def update(id_val: str, project_id: str, updates: Dict[str, Any], session: AsyncSession) -> Optional[Dict[str, Any]]:
        arid = uuid.UUID(id_val) if isinstance(id_val, str) else id_val
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        stmt = select(AuditResultModel).join(RequirementModel).where(
            AuditResultModel.id == arid, 
            RequirementModel.project_id == pid
        )
        result = await session.execute(stmt)
        ar = result.scalar_one_or_none()
        if ar:
            if "is_valid" in updates:
                ar.is_valid = updates["is_valid"]
            if "audit_version_reviewed" in updates:
                ar.audit_version_reviewed = updates["audit_version_reviewed"]
            if "passed_checks" in updates:
                ar.passed_checks = updates["passed_checks"]
            if "failed_checks" in updates:
                ar.failed_checks = updates["failed_checks"]
            await session.flush()
            await session.refresh(ar)
            return {
                "id": str(ar.id),
                "project_id": str(pid),
                "is_valid": ar.is_valid,
                "audit_version_reviewed": ar.audit_version_reviewed,
                "passed_checks": ar.passed_checks,
                "failed_checks": ar.failed_checks
            }
        return None

    @staticmethod
    async def delete(id_val: str, project_id: str, session: AsyncSession) -> bool:
        arid = uuid.UUID(id_val) if isinstance(id_val, str) else id_val
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        stmt = select(AuditResultModel).join(RequirementModel).where(
            AuditResultModel.id == arid, 
            RequirementModel.project_id == pid
        )
        result = await session.execute(stmt)
        ar = result.scalar_one_or_none()
        if ar:
            await session.delete(ar)
            await session.flush()
            return True
        return False

class PRDDocumentRepository:
    """
    Handles generated PRD Documents of the project.
    """
    @staticmethod
    async def create(project_id: str, data: Dict[str, Any], session: AsyncSession) -> Dict[str, Any]:
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        prd = PRDDocumentModel(
            project_id=pid,
            version=data.get("version", 1),
            prd_markdown=data.get("prd_markdown", ""),
            mermaid_diagram=data.get("mermaid_diagram", "")
        )
        session.add(prd)
        await session.flush()
        await session.refresh(prd)
        return {
            "id": str(prd.id),
            "project_id": str(prd.project_id),
            "version": prd.version,
            "prd_markdown": prd.prd_markdown,
            "mermaid_diagram": prd.mermaid_diagram
        }

    @staticmethod
    async def get_by_id(id_val: str, project_id: str, session: AsyncSession) -> Optional[Dict[str, Any]]:
        prdid = uuid.UUID(id_val) if isinstance(id_val, str) else id_val
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        stmt = select(PRDDocumentModel).where(PRDDocumentModel.id == prdid, PRDDocumentModel.project_id == pid)
        result = await session.execute(stmt)
        prd = result.scalar_one_or_none()
        if prd:
            return {
                "id": str(prd.id),
                "project_id": str(prd.project_id),
                "version": prd.version,
                "prd_markdown": prd.prd_markdown,
                "mermaid_diagram": prd.mermaid_diagram
            }
        return None

    @staticmethod
    async def get_by_project(project_id: str, session: AsyncSession, version: Optional[int] = None) -> List[Dict[str, Any]]:
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        if version is not None:
            stmt = select(PRDDocumentModel).where(PRDDocumentModel.project_id == pid, PRDDocumentModel.version == version)
        else:
            stmt = select(PRDDocumentModel).where(PRDDocumentModel.project_id == pid).order_by(PRDDocumentModel.version.desc())
        result = await session.execute(stmt)
        records = result.scalars().all()
        return [
            {
                "id": str(prd.id),
                "project_id": str(prd.project_id),
                "version": prd.version,
                "prd_markdown": prd.prd_markdown,
                "mermaid_diagram": prd.mermaid_diagram
            }
            for prd in records
        ]

    @staticmethod
    async def update(id_val: str, project_id: str, updates: Dict[str, Any], session: AsyncSession) -> Optional[Dict[str, Any]]:
        prdid = uuid.UUID(id_val) if isinstance(id_val, str) else id_val
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        stmt = select(PRDDocumentModel).where(PRDDocumentModel.id == prdid, PRDDocumentModel.project_id == pid)
        result = await session.execute(stmt)
        prd = result.scalar_one_or_none()
        if prd:
            if "version" in updates:
                prd.version = updates["version"]
            if "prd_markdown" in updates:
                prd.prd_markdown = updates["prd_markdown"]
            if "mermaid_diagram" in updates:
                prd.mermaid_diagram = updates["mermaid_diagram"]
            await session.flush()
            await session.refresh(prd)
            return {
                "id": str(prd.id),
                "project_id": str(prd.project_id),
                "version": prd.version,
                "prd_markdown": prd.prd_markdown,
                "mermaid_diagram": prd.mermaid_diagram
            }
        return None

    @staticmethod
    async def delete(id_val: str, project_id: str, session: AsyncSession) -> bool:
        prdid = uuid.UUID(id_val) if isinstance(id_val, str) else id_val
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        stmt = select(PRDDocumentModel).where(PRDDocumentModel.id == prdid, PRDDocumentModel.project_id == pid)
        result = await session.execute(stmt)
        prd = result.scalar_one_or_none()
        if prd:
            await session.delete(prd)
            await session.flush()
            return True
        return False

class VersionHistoryRepository:
    """
    Handles Version History snapshot tracking of the project.
    """
    @staticmethod
    async def create(project_id: str, data: Dict[str, Any], session: AsyncSession) -> Dict[str, Any]:
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        
        stmt_req = select(RequirementModel).where(RequirementModel.project_id == pid)
        res_req = await session.execute(stmt_req)
        req = res_req.scalar_one_or_none()
        if not req:
            req = RequirementModel(project_id=pid, epic_name="Untitled Epic")
            session.add(req)
            await session.flush()
            
        system_user_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
        
        vh = VersionHistoryModel(
            project_id=pid,
            requirement_id=req.id,
            version=data.get("version", 1),
            changed_by_user_id=system_user_id,
            description=data.get("description", "Requirements updated."),
            requirements_snapshot=data.get("requirements_snapshot", {})
        )
        session.add(vh)
        await session.flush()
        return {
            "id": str(vh.id),
            "project_id": str(vh.project_id),
            "version": vh.version,
            "timestamp": vh.timestamp,
            "author": vh.author,
            "description": vh.description,
            "requirements_snapshot": vh.requirements_snapshot
        }

    @staticmethod
    async def get_by_id(id_val: str, project_id: str, session: AsyncSession) -> Optional[Dict[str, Any]]:
        vhid = uuid.UUID(id_val) if isinstance(id_val, str) else id_val
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        stmt = select(VersionHistoryModel).where(VersionHistoryModel.id == vhid, VersionHistoryModel.project_id == pid)
        result = await session.execute(stmt)
        vh = result.scalar_one_or_none()
        if vh:
            return {
                "id": str(vh.id),
                "project_id": str(vh.project_id),
                "version": vh.version,
                "timestamp": vh.timestamp,
                "author": vh.author,
                "description": vh.description,
                "requirements_snapshot": vh.requirements_snapshot
            }
        return None

    @staticmethod
    async def get_by_project(project_id: str, session: AsyncSession) -> List[Dict[str, Any]]:
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        stmt = select(VersionHistoryModel).where(VersionHistoryModel.project_id == pid).order_by(VersionHistoryModel.version.desc())
        result = await session.execute(stmt)
        records = result.scalars().all()
        return [
            {
                "id": str(vh.id),
                "project_id": str(vh.project_id),
                "version": vh.version,
                "timestamp": vh.timestamp,
                "author": vh.author,
                "description": vh.description,
                "requirements_snapshot": vh.requirements_snapshot
            }
            for vh in records
        ]

    @staticmethod
    async def update(id_val: str, project_id: str, updates: Dict[str, Any], session: AsyncSession) -> Optional[Dict[str, Any]]:
        vhid = uuid.UUID(id_val) if isinstance(id_val, str) else id_val
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        stmt = select(VersionHistoryModel).where(VersionHistoryModel.id == vhid, VersionHistoryModel.project_id == pid)
        result = await session.execute(stmt)
        vh = result.scalar_one_or_none()
        if vh:
            if "version" in updates:
                vh.version = updates["version"]
            if "description" in updates:
                vh.description = updates["description"]
            if "requirements_snapshot" in updates:
                vh.requirements_snapshot = updates["requirements_snapshot"]
            await session.flush()
            return {
                "id": str(vh.id),
                "project_id": str(vh.project_id),
                "version": vh.version,
                "timestamp": vh.timestamp,
                "author": vh.author,
                "description": vh.description,
                "requirements_snapshot": vh.requirements_snapshot
            }
        return None

    @staticmethod
    async def delete(id_val: str, project_id: str, session: AsyncSession) -> bool:
        vhid = uuid.UUID(id_val) if isinstance(id_val, str) else id_val
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        stmt = select(VersionHistoryModel).where(VersionHistoryModel.id == vhid, VersionHistoryModel.project_id == pid)
        result = await session.execute(stmt)
        vh = result.scalar_one_or_none()
        if vh:
            await session.delete(vh)
            await session.flush()
            return True
        return False

class RequirementStateRepository:
    """
    Dedicated persistence repository isolating all Supabase/PostgreSQL database operations
    from the multi-agent system.
    """
    
    @staticmethod
    async def get_by_project_id(project_id: str, session: AsyncSession) -> Optional[Dict[str, Any]]:
        """
        Loads the latest RequirementState from Supabase for a given project_id.
        Requires an active session to maintain transactional consistency.
        """
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        return await RequirementStateRepository._get_by_project_id_impl(pid, session)

    @staticmethod
    async def _get_by_project_id_impl(project_id: uuid.UUID, session: AsyncSession) -> Optional[Dict[str, Any]]:
        stmt = select(RequirementStateModel).where(RequirementStateModel.project_id == project_id)
        result = await session.execute(stmt)
        model = result.scalar_one_or_none()
        if not model:
            return None
        
        # Load active epic directly from epics table
        active_epic = await EpicRepository.get_active_by_project(str(project_id), session)
        epic_name = active_epic["epic_name"] if active_epic else ""

        # Load ALL active requirements for this project (multi-requirement support)
        stmt_req = select(RequirementModel).where(
            RequirementModel.project_id == project_id,
            func.lower(RequirementModel.status) == "active"
        ).order_by(RequirementModel.created_at.asc())
        res_req = await session.execute(stmt_req)
        reqs = res_req.scalars().all()
        
        version_num = model.version_number
        
        # Build the requirements list with their user stories
        all_user_stories = []
        all_acceptance_criteria = []
        requirements_list = []
        
        for req in reqs:
            req_id = req.id
            if not epic_name and req.epic_id:
                stmt_epic = select(EpicModel).where(EpicModel.id == req.epic_id)
                res_epic = await session.execute(stmt_epic)
                epic = res_epic.scalar_one_or_none()
                if epic:
                    epic_name = epic.epic_name
            
            # Load user stories for this specific requirement
            stories = await UserStoryRepository.get_by_project(str(project_id), session, requirement_id=req_id)
            ac_list = await AcceptanceCriteriaRepository.get_by_project(str(project_id), session, requirement_id=req_id)
            
            active_stories = [s for s in stories if s.get("status", "active") == "active"]
            active_ac_list = [ac for ac in ac_list if ac.get("status", "active") == "active"]
            
            flat_ac = [ac["criteria_text"] for ac in active_ac_list]
            
            # Map acceptance criteria to stories
            for story in active_stories:
                story_ac = [ac["criteria_text"] for ac in active_ac_list if ac["ticket_code"] == story["ticket_code"]]
                story["acceptance_criteria"] = story_ac
            
            # Build requirement entry
            req_entry = {
                "requirement_code": req.requirement_code,
                "title": req.title,
                "description": req.description or "",
                "user_stories": active_stories
            }
            requirements_list.append(req_entry)
            all_user_stories.extend(active_stories)
            all_acceptance_criteria.extend(flat_ac)

        # Fallback if no epic found in epics table but present in model.requirements
        if not epic_name and model.requirements:
            if isinstance(model.requirements, dict):
                epic_name = model.requirements.get("epic_name", "")
            elif isinstance(model.requirements, list) and len(model.requirements) > 0:
                epic_name = model.requirements[0].get("epic_name", "")
            if epic_name:
                saved_epic = await EpicRepository.save_or_update_epic(str(project_id), epic_name, session, version=version_num)
                epic_name = saved_epic["epic_name"]
        
        if not requirements_list:
            # Fallback: use the old flat model.user_stories if no requirements found
            all_user_stories = model.user_stories or []
            all_acceptance_criteria = model.acceptance_criteria or []
            if model.requirements and isinstance(model.requirements, dict) and "epic_name" in model.requirements:
                epic_name = model.requirements["epic_name"]

        cqs = await ClarificationQuestionRepository.get_by_project(str(project_id), session)
        prds = await PRDDocumentRepository.get_by_project(str(project_id), session, version=version_num)

        generated_prd = ""
        generated_diagrams = ""
        if prds:
            generated_prd = prds[0]["prd_markdown"]
            generated_diagrams = prds[0]["mermaid_diagram"]

        return {
            "project_id": str(model.project_id),
            "project_name": model.project_name,
            "requirements": requirements_list if requirements_list else [],
            "business_goals": model.business_goals,
            "actors": model.actors,
            "user_stories": all_user_stories if all_user_stories else [],
            "acceptance_criteria": all_acceptance_criteria if all_acceptance_criteria else [],
            "clarification_questions": cqs if cqs else [],
            "validation_status": model.validation_status,
            "generated_prd": generated_prd if generated_prd else "",
            "generated_diagrams": generated_diagrams if generated_diagrams else "",
            "current_workflow_state": model.current_workflow_state,
            "version_number": version_num,
            "updated_at": model.__dict__.get("updated_at").isoformat() if model.__dict__.get("updated_at") else None
        }

    @staticmethod
    async def save_or_update(project_id: str, updates: Dict[str, Any], session: AsyncSession) -> Dict[str, Any]:
        """
        Saves or partially updates the RequirementState for a given project_id.
        Does not overwrite unchanged fields. Uses partial updates whenever possible.
        Requires an active session to maintain transactional consistency.
        """
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        res = await RequirementStateRepository._save_or_update_impl(pid, updates, session)
        return res

    @staticmethod
    async def _save_or_update_impl(project_id: uuid.UUID, updates: Dict[str, Any], session: AsyncSession) -> Dict[str, Any]:
        stmt = select(RequirementStateModel).where(RequirementStateModel.project_id == project_id)
        result = await session.execute(stmt)
        model = result.scalar_one_or_none()
        
        # Initialize fallback variables
        original_requirements = {}
        original_user_stories = []
        original_acceptance_criteria = []
        original_clarification_questions = []
        original_generated_prd = ""
        original_generated_diagrams = ""
        
        if not model:
            model = RequirementStateModel(
                project_id=project_id,
                project_name=updates.get("project_name", "Default Project"),
                requirements={},
                business_goals=updates.get("business_goals", []),
                actors=updates.get("actors", []),
                user_stories=[],
                acceptance_criteria=[],
                clarification_questions=[],
                validation_status=updates.get("validation_status", "pending"),
                generated_prd="",
                generated_diagrams="",
                current_workflow_state=updates.get("current_workflow_state", "gatherer_node"),
                version_number=updates.get("version_number", 1)
            )
            session.add(model)
            await session.flush()
        else:
            # Preserve original values for fallback
            original_requirements = model.requirements or {}
            original_user_stories = model.user_stories or []
            original_acceptance_criteria = model.acceptance_criteria or []
            original_clarification_questions = model.clarification_questions or []
            original_generated_prd = model.generated_prd or ""
            original_generated_diagrams = model.generated_diagrams or ""
            
            if "project_name" in updates and updates["project_name"] is not None:
                model.project_name = updates["project_name"]
            if "validation_status" in updates and updates["validation_status"] is not None:
                model.validation_status = updates["validation_status"]
            if "current_workflow_state" in updates and updates["current_workflow_state"] is not None:
                model.current_workflow_state = updates["current_workflow_state"]
            if "version_number" in updates and updates["version_number"] is not None:
                model.version_number = updates["version_number"]
            if "business_goals" in updates and updates["business_goals"] is not None:
                model.business_goals = updates["business_goals"]
            if "actors" in updates and updates["actors"] is not None:
                model.actors = updates["actors"]
                
            # Only clear JSON blob fields that are being re-derived from relation tables.
            # This avoids wasteful clearing and prevents data loss if re-derivation fails mid-way.
            if "requirements" in updates and updates["requirements"] is not None:
                model.requirements = {}
            if "user_stories" in updates and updates["user_stories"] is not None:
                model.user_stories = []
            if "acceptance_criteria" in updates and updates["acceptance_criteria"] is not None:
                model.acceptance_criteria = []
            if "clarification_questions" in updates and updates["clarification_questions"] is not None:
                model.clarification_questions = []
            if "generated_prd" in updates and updates["generated_prd"] is not None:
                model.generated_prd = ""
            if "generated_diagrams" in updates and updates["generated_diagrams"] is not None:
                model.generated_diagrams = ""
        
        version_num = model.version_number

        # ===============================================
        # MULTI-REQUIREMENT SAVE LOGIC
        # Parse updates.requirements or updates.user_stories to handle multiple requirements
        # ===============================================
        
        # Extract the list of requirements to persist
        req_items = []
        if "requirements" in updates and updates["requirements"] is not None:
            reqs_data = updates["requirements"]
            if isinstance(reqs_data, list):
                # New multi-requirement format: [{"requirement_code": "REQ-001", "title": "...", "user_stories": [...]}, ...]
                req_items = reqs_data
            elif isinstance(reqs_data, dict):
                # Legacy flat format: {"epic_name": "...", "user_stories": [...]}
                # Convert to single requirement
                legacy_epic = reqs_data.get("epic_name", "")
                legacy_stories = reqs_data.get("user_stories", []) if "user_stories" in reqs_data else updates.get("user_stories", [])
                req_items = [{
                    "requirement_code": "REQ-001",
                    "title": legacy_epic or updates.get("project_name", "Default Requirement"),
                    "description": "",
                    "user_stories": legacy_stories if isinstance(legacy_stories, list) else []
                }]
        elif "user_stories" in updates and updates["user_stories"] is not None:
            # Legacy flat user_stories fallback
            req_items = [{
                "requirement_code": "REQ-001",
                "title": "Structured Requirements",
                "description": "",
                "user_stories": updates["user_stories"] if isinstance(updates["user_stories"], list) else []
            }]

        if not req_items:
            req_items = [{
                "requirement_code": "REQ-001",
                "title": "Default Requirement",
                "description": "",
                "user_stories": []
            }]

        # Determine epic name from first requirement or updates
        epic_name_val = ""
        if "requirements" in updates and isinstance(updates["requirements"], dict):
            epic_name_val = updates["requirements"].get("epic_name", "")
        if not epic_name_val and req_items:
            epic_name_val = req_items[0].get("title", "")
        if not epic_name_val:
            epic_name_val = updates.get("project_name", "Default Epic")

        # Save or update active Epic in epics table
        if epic_name_val:
            epic_rec = await EpicRepository.save_or_update_epic(str(project_id), epic_name_val, session, version=version_num)
        else:
            active_epic = await EpicRepository.get_active_by_project(str(project_id), session)
            epic_rec = active_epic or await EpicRepository.save_or_update_epic(str(project_id), "Untitled Epic", session, version=version_num)

        epic_id_uuid = uuid.UUID(epic_rec["id"])
        
        # Load ALL existing active requirements for this project (by requirement_code map)
        stmt_all_reqs = select(RequirementModel).where(
            RequirementModel.project_id == project_id,
            func.lower(RequirementModel.status) == "active"
        )
        res_all_reqs = await session.execute(stmt_all_reqs)
        all_db_reqs = res_all_reqs.scalars().all()
        
        db_reqs_by_code = {}
        db_reqs_by_id = {}
        for r in all_db_reqs:
            if r.requirement_code:
                db_reqs_by_code[r.requirement_code] = r
            db_reqs_by_id[str(r.id)] = r
        
        # Also load archived requirements (we might need to reactivate)
        stmt_archived_reqs = select(RequirementModel).where(
            RequirementModel.project_id == project_id,
            func.lower(RequirementModel.status) == "archived"
        )
        res_archived_reqs = await session.execute(stmt_archived_reqs)
        for r in res_archived_reqs.scalars().all():
            if r.requirement_code and r.requirement_code not in db_reqs_by_code:
                db_reqs_by_code[r.requirement_code] = r

        # Track which requirement IDs are touched to archive others
        touched_req_ids = set()
        
        for req_item in req_items:
            req_code = req_item.get("requirement_code", "REQ-000")
            req_title = req_item.get("title", "Untitled Requirement")
            req_desc = req_item.get("description", "")
            stories = req_item.get("user_stories", [])
            
            # Find or create the RequirementModel for this requirement_code
            db_req = db_reqs_by_code.get(req_code)
            if db_req:
                # Update existing requirement
                if db_req.status != "active":
                    db_req.status = "active"
                db_req.title = req_title
                db_req.description = req_desc
                db_req.epic_id = epic_id_uuid
                db_req.version = version_num
                await session.flush()
                created_req_id = db_req.id
            else:
                # Create new requirement
                new_req = RequirementModel(
                    project_id=project_id,
                    epic_id=epic_id_uuid,
                    requirement_code=req_code,
                    title=req_title,
                    description=req_desc,
                    version=version_num,
                    status="active"
                )
                session.add(new_req)
                await session.flush()
                created_req_id = new_req.id

            touched_req_ids.add(str(created_req_id))

            # ---- Process User Stories for this requirement ----
            if not stories:
                continue

            # Load all existing stories for this specific requirement
            stmt_stories = select(UserStoryModel).where(UserStoryModel.requirement_id == created_req_id)
            res_stories = await session.execute(stmt_stories)
            db_stories = res_stories.scalars().all()

            stories_by_id = {s.id: s for s in db_stories}
            stories_by_code = {s.ticket_code: s for s in db_stories if s.ticket_code}
            stories_by_title = {s.story_title: s for s in db_stories if s.story_title}

            touched_story_ids = []
            semantic_recs = updates.get("semantic_recommendations") or []

            for story in stories:
                ticket_code = story.get("ticket_code")
                story_title = story.get("story_title", "Untitled Story")

                # Check match
                db_story = None
                if ticket_code and ticket_code != "US-000":
                    db_story = stories_by_code.get(ticket_code)
                if not db_story:
                    db_story = stories_by_title.get(story_title)

                rec_action = None
                if semantic_recs:
                    matched_rec = next((r for r in semantic_recs if r.get("target_requirement_id") == ticket_code), None)
                    if not matched_rec and db_story:
                        matched_rec = next((r for r in semantic_recs if r.get("target_requirement_id") == db_story.ticket_code), None)
                    if matched_rec:
                        rec_action = matched_rec.get("recommended_action")

                if db_story:
                    title_changed = db_story.story_title != story_title
                    as_a_changed = db_story.as_a != story.get("as_a", "")
                    i_want_to_changed = db_story.i_want_to != story.get("i_want_to", "")
                    so_that_changed = db_story.so_that != story.get("so_that", "")
                    was_archived = db_story.status != "active"

                    if rec_action == "UPDATE":
                        story_modified = True
                    elif rec_action == "NO_CHANGE":
                        story_modified = False
                    elif rec_action == "ARCHIVE":
                        db_story.status = "archived"
                        db_story.change_type = "archived"
                        db_story.version = db_story.version + 1
                        db_story.last_modified_by = "automated_agent"
                        db_story.project_id = project_id
                        await session.flush()
                        continue
                    else:
                        story_modified = title_changed or as_a_changed or i_want_to_changed or so_that_changed

                    if story_modified or was_archived:
                        db_story.story_title = story_title
                        db_story.as_a = story.get("as_a", "")
                        db_story.i_want_to = story.get("i_want_to", "")
                        db_story.so_that = story.get("so_that", "")
                        db_story.status = "active"
                        db_story.version = db_story.version + 1
                        db_story.change_type = "updated"
                    else:
                        db_story.change_type = "unchanged"
                        db_story.status = "active"

                    db_story.last_modified_by = "automated_agent"
                    db_story.project_id = project_id
                    await session.flush()
                else:
                    if not ticket_code or ticket_code == "US-000" or ticket_code in stories_by_code:
                        ticket_code = await UserStoryRepository.generate_unique_ticket_code(project_id, session)

                    db_story = UserStoryModel(
                        project_id=project_id,
                        requirement_id=created_req_id,
                        ticket_code=ticket_code,
                        story_title=story_title,
                        as_a=story.get("as_a", ""),
                        i_want_to=story.get("i_want_to", ""),
                        so_that=story.get("so_that", ""),
                        status="active",
                        version=1,
                        last_modified_by="automated_agent",
                        change_type="created"
                    )
                    session.add(db_story)
                    await session.flush()

                touched_story_ids.append(db_story.id)

                # Sync acceptance criteria for this story
                stmt_ac = select(AcceptanceCriteriaModel).where(AcceptanceCriteriaModel.user_story_id == db_story.id)
                res_ac = await session.execute(stmt_ac)
                db_ac_list = res_ac.scalars().all()

                incoming_ac_texts = story.get("acceptance_criteria", [])
                matched_db_ac = set()
                matched_incoming_indices = set()

                for i, text_val in enumerate(incoming_ac_texts):
                    for db_ac in db_ac_list:
                        if db_ac.id not in matched_db_ac and db_ac.status == "active" and db_ac.criteria_text == text_val:
                            db_ac.change_type = "unchanged"
                            matched_db_ac.add(db_ac.id)
                            matched_incoming_indices.add(i)
                            break

                for i, text_val in enumerate(incoming_ac_texts):
                    if i in matched_incoming_indices:
                        continue
                    for db_ac in db_ac_list:
                        if db_ac.id not in matched_db_ac and db_ac.status == "archived" and db_ac.criteria_text == text_val:
                            db_ac.status = "active"
                            db_ac.change_type = "updated"
                            db_ac.version = db_ac.version + 1
                            matched_db_ac.add(db_ac.id)
                            matched_incoming_indices.add(i)
                            break

                unmatched_active_db_ac = [ac for ac in db_ac_list if ac.id not in matched_db_ac and ac.status == "active"]
                unmatched_incoming_indices_list = [i for i in range(len(incoming_ac_texts)) if i not in matched_incoming_indices]

                for idx, i in enumerate(unmatched_incoming_indices_list):
                    text_val = incoming_ac_texts[i]
                    if idx < len(unmatched_active_db_ac):
                        db_ac = unmatched_active_db_ac[idx]
                        db_ac.criteria_text = text_val
                        db_ac.status = "active"
                        db_ac.version = db_ac.version + 1
                        db_ac.change_type = "updated"
                        db_ac.last_modified_by = "automated_agent"
                        matched_db_ac.add(db_ac.id)
                    else:
                        new_ac = AcceptanceCriteriaModel(
                            user_story_id=db_story.id,
                            criteria_text=text_val,
                            status="active",
                            version=1,
                            last_modified_by="automated_agent",
                            change_type="created"
                        )
                        session.add(new_ac)

                for db_ac in db_ac_list:
                    if db_ac.id not in matched_db_ac and db_ac.status == "active":
                        db_ac.status = "archived"
                        db_ac.change_type = "archived"
                        db_ac.version = db_ac.version + 1

                await session.flush()

            # Archive any user stories in this requirement that are NOT in the current payload
            for s_id, s_model in stories_by_id.items():
                if s_id not in touched_story_ids and s_model.status == "active":
                    s_model.status = "archived"
                    s_model.change_type = "archived"
                    s_model.version = s_model.version + 1

                    stmt_story_ac = select(AcceptanceCriteriaModel).where(
                        AcceptanceCriteriaModel.user_story_id == s_id,
                        AcceptanceCriteriaModel.status == "active"
                    )
                    res_story_ac = await session.execute(stmt_story_ac)
                    story_ac_list = res_story_ac.scalars().all()
                    for db_ac in story_ac_list:
                        db_ac.status = "archived"
                        db_ac.change_type = "archived"
                        db_ac.version = db_ac.version + 1

            await session.flush()

        # Archive any active requirements NOT in the incoming payload (requirement removal)
        for r_code, r_model in db_reqs_by_code.items():
            r_id_str = str(r_model.id)
            if r_id_str not in touched_req_ids and r_model.status == "active":
                r_model.status = "archived"
                # Also archive all its user stories
                stmt_orphan_stories = select(UserStoryModel).where(UserStoryModel.requirement_id == r_model.id)
                res_orphan_stories = await session.execute(stmt_orphan_stories)
                for orphan_story in res_orphan_stories.scalars().all():
                    if orphan_story.status == "active":
                        orphan_story.status = "archived"
                        orphan_story.change_type = "archived"
                        orphan_story.version = orphan_story.version + 1
                await session.flush()

        # 3. Propagation for Clarification Questions (associate with first active requirement)
        first_active_req_id = None
        for r_id_str in touched_req_ids:
            first_active_req_id = uuid.UUID(r_id_str)
            break
        
        if "clarification_questions" in updates and updates["clarification_questions"] is not None:
            if first_active_req_id:
                stmt_ar_ids = select(AuditResultModel.id).where(AuditResultModel.requirement_id == first_active_req_id)
                res_ar_ids = await session.execute(stmt_ar_ids)
                ar_ids = res_ar_ids.scalars().all()
                if ar_ids:
                    stmt_del_cq = delete(ClarificationQuestionModel).where(ClarificationQuestionModel.audit_result_id.in_(ar_ids))
                    await session.execute(stmt_del_cq)

            for cq in updates["clarification_questions"]:
                await ClarificationQuestionRepository.create(str(project_id), {
                    "checklist_category": cq.get("checklist_category", "General"),
                    "target_user_story_id": cq.get("target_user_story_id"),
                    "question_text": cq.get("question_text", ""),
                    "user_answer": cq.get("user_answer"),
                    "is_resolved": cq.get("is_resolved", False)
                }, session, requirement_id=first_active_req_id)

        # 4. Propagation for PRD & Diagrams
        if ("generated_prd" in updates and updates["generated_prd"] is not None) or ("generated_diagrams" in updates and updates["generated_diagrams"] is not None):
            prd_list = await PRDDocumentRepository.get_by_project(str(project_id), session, version=version_num)
            prd_markdown = updates.get("generated_prd") or (prd_list[0]["prd_markdown"] if prd_list else "")
            mermaid_diagram = updates.get("generated_diagrams") or (prd_list[0]["mermaid_diagram"] if prd_list else "")
            
            if not prd_list:
                await PRDDocumentRepository.create(str(project_id), {
                    "version": version_num,
                    "prd_markdown": prd_markdown,
                    "mermaid_diagram": mermaid_diagram
                }, session)
            else:
                await PRDDocumentRepository.update(prd_list[0]["id"], str(project_id), {
                    "version": version_num,
                    "prd_markdown": prd_markdown,
                    "mermaid_diagram": mermaid_diagram
                }, session)

        # 5. Propagation for Audit Results
        if "validation_status" in updates and updates["validation_status"] is not None and first_active_req_id:
            passed = updates.get("passed_checks", [])
            failed = updates.get("failed_checks", [])
            is_valid = updates["validation_status"] == "valid"
            
            ar_list = await AuditResultRepository.get_by_project(str(project_id), session, requirement_id=first_active_req_id)
            if not ar_list:
                await AuditResultRepository.create(str(project_id), {
                    "is_valid": is_valid,
                    "audit_version_reviewed": version_num,
                    "passed_checks": passed,
                    "failed_checks": failed
                }, session, requirement_id=first_active_req_id)
            else:
                await AuditResultRepository.update(ar_list[0]["id"], str(project_id), {
                    "is_valid": is_valid,
                    "audit_version_reviewed": version_num,
                    "passed_checks": passed if passed else ar_list[0]["passed_checks"],
                    "failed_checks": failed if failed else ar_list[0]["failed_checks"]
                }, session)

        await session.flush()
        await session.refresh(model)
        
        return await RequirementStateRepository._get_by_project_id_impl(project_id, session)


class ConversationMessageRepository:
    """
    Handles conversation message persistence in Supabase.
    """
    @staticmethod
    async def save_message(project_id: str, role: str, message: str, session: Optional[AsyncSession] = None) -> Dict[str, Any]:
        if not message or not message.strip():
            return {}
            
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        
        async def _save(s: AsyncSession):
            msg_obj = ConversationMessageModel(
                id=uuid.uuid4(),
                project_id=pid,
                role=role,
                message=message
            )
            s.add(msg_obj)
            await s.flush()
            return {
                "id": str(msg_obj.id),
                "project_id": str(msg_obj.project_id),
                "role": msg_obj.role,
                "message": msg_obj.message,
                "content": msg_obj.message,
                "timestamp": msg_obj.timestamp.isoformat() if msg_obj.timestamp else ""
            }

        if session:
            # Session is managed by the caller (e.g. get_db dependency) - just flush
            return await _save(session)
        async with AsyncSessionLocal() as db_session:
            try:
                result = await _save(db_session)
                await db_session.commit()
                return result
            except Exception:
                await db_session.rollback()
                raise

    @staticmethod
    async def get_conversation_history(project_id: str, session: Optional[AsyncSession] = None) -> List[Dict[str, Any]]:
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        
        async def _fetch(s: AsyncSession):
            stmt = select(ConversationMessageModel).where(ConversationMessageModel.project_id == pid).order_by(ConversationMessageModel.timestamp.asc(), ConversationMessageModel.created_at.asc())
            res = await s.execute(stmt)
            messages = res.scalars().all()
            return [
                {
                    "id": str(m.id),
                    "project_id": str(m.project_id),
                    "role": m.role,
                    "message": m.message,
                    "content": m.message,
                    "timestamp": m.timestamp.isoformat() if m.timestamp else ""
                }
                for m in messages
            ]
        
        if session:
            return await _fetch(session)
        async with AsyncSessionLocal() as db_session:
            return await _fetch(db_session)

class PendingActionRepository:
    """
    Handles Pending Actions for Human-in-the-Loop confirmation.
    """
    @staticmethod
    async def create(project_id: str, data: Dict[str, Any], expires_at: datetime, session: AsyncSession) -> Dict[str, Any]:
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        action = PendingActionModel(
            project_id=pid,
            action_type=data.get("action_type", "UPDATE"),
            target_requirement_id=data.get("target_requirement_id"),
            original_user_message=data.get("original_user_message", ""),
            proposed_changes=data.get("proposed_changes", {}),
            affected_user_story_ids=data.get("affected_user_story_ids", []),
            affected_acceptance_criteria_ids=data.get("affected_acceptance_criteria_ids", []),
            workflow_stage=data.get("workflow_stage", "gatherer_node"),
            expires_at=expires_at
        )
        session.add(action)
        await session.flush()
        await session.refresh(action)
        return {
            "id": str(action.id),
            "project_id": str(action.project_id),
            "action_type": action.action_type,
            "target_requirement_id": action.target_requirement_id,
            "status": action.status
        }

    @staticmethod
    async def get_by_project(project_id: str, session: AsyncSession) -> List[Dict[str, Any]]:
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        stmt = select(PendingActionModel).where(PendingActionModel.project_id == pid, PendingActionModel.status == "WAITING_CONFIRMATION")
        result = await session.execute(stmt)
        actions = result.scalars().all()
        return [
            {
                "id": str(a.id),
                "project_id": str(a.project_id),
                "action_type": a.action_type,
                "target_requirement_id": a.target_requirement_id,
                "original_user_message": a.original_user_message,
                "proposed_changes": a.proposed_changes,
                "affected_user_story_ids": a.affected_user_story_ids,
                "affected_acceptance_criteria_ids": a.affected_acceptance_criteria_ids,
                "workflow_stage": a.workflow_stage,
                "status": a.status,
                "expires_at": a.expires_at.isoformat()
            }
            for a in actions
        ]

    @staticmethod
    async def delete(id_val: str, project_id: str, session: AsyncSession) -> bool:
        aid = uuid.UUID(id_val) if isinstance(id_val, str) else id_val
        pid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        stmt = select(PendingActionModel).where(PendingActionModel.id == aid, PendingActionModel.project_id == pid)
        result = await session.execute(stmt)
        action = result.scalar_one_or_none()
        if action:
            await session.delete(action)
            await session.flush()
            return True
        return False

