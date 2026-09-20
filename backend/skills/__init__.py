"""
GHOST — Skill System (M3-F).

A skill is a reusable, named capability that plans and
executes work through the existing M3 pipeline:

  Task -> SkillRunner -> Skill plan -> Agent
       -> PermissionPolicy -> ToolRegistry -> result

Infrastructure split (progressive disclosure):
- metadata.py / registry.py / router.py: lightweight,
  always-resident metadata only — no skill code is
  imported for registration or routing.
- loader.py: imports a skill implementation lazily,
  only after selection, and caches the instance.
- runner.py: thin integration layer; every tool step
  still flows through Agent -> PermissionPolicy.
"""
