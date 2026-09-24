"""
GHOST — skill catalog endpoint (M4 step 5).

Metadata only. SkillRegistry holds SkillMetadata and never
imports an implementation — loading is SkillLoader's job on
demand — so this endpoint stays cheap no matter how many
skills exist, and cannot trigger a skill import. Nothing here
executes a skill: running goes through the task pipeline,
where PermissionPolicy stays in charge.
"""

from fastapi import APIRouter

from backend.core.agent_services import skill_registry, skill_stage


router = APIRouter(
    prefix="/api",
    tags=["Skills"],
)


@router.get("/skills")
async def list_skills():
    """List registered skills with their declared risk level."""

    skills = []

    for metadata in skill_registry.list_metadata():
        missing = skill_stage.missing_tools(metadata.name)

        skills.append(
            {
                "name": metadata.name,
                "description": metadata.description,
                "category": metadata.category,
                "version": metadata.version,
                "risk_level": metadata.risk_level.value,
                "required_tools": list(metadata.required_tools),
                "available": not missing,
                "missing_tools": missing,
            }
        )

    skills.sort(key=lambda item: item["name"])

    return {
        "skills": skills,
        "total": len(skills),
    }
