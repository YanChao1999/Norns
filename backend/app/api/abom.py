"""HTTP API for abom recipe catalog / install / link (Agent Bill of Materials)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..plugins.abom_plugin import (
    RECIPE_KINDS,
    abom_installed,
    discover_linked_mcps,
    discover_linked_skills,
    enable_recipe,
    list_recipe_cards,
    recipe_card_dict,
)
from .auth import get_current_user

router = APIRouter(prefix="/abom", tags=["abom"], dependencies=[Depends(get_current_user)])


class RecipeAction(BaseModel):
    name: str = Field(min_length=1)


class LinkAction(BaseModel):
    name: str = Field(min_length=1)
    target_repo: str = Field(min_length=1)
    link_name: str | None = None


class EnableAction(BaseModel):
    name: str = Field(min_length=1)
    target_repo: str | None = None


def _cli():
    try:
        from abom import cli as abom_cli
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "abom is not installed. pip install abom or pip install 'norns-ide[abom]' "
                "(https://yanchao1999.github.io/abom/)"
            ),
        ) from exc
    return abom_cli


def _run(call, *args, **kwargs) -> str:
    cli = _cli()
    try:
        result = call(*args, **kwargs)
    except Exception as exc:
        error_type = getattr(cli, "AbomError", RuntimeError)
        if isinstance(exc, error_type):
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if isinstance(result, list):
        return "\n".join(str(item) for item in result)
    return str(result)


@router.get("/status")
async def abom_status() -> dict[str, Any]:
    return {
        "installed": abom_installed(),
        "homepage": "https://yanchao1999.github.io/abom/",
        "install": "pip install abom  # or: pip install 'norns-ide[abom]'",
        "kinds": list(RECIPE_KINDS),
    }


@router.get("/catalog")
async def recipe_catalog(
    query: Annotated[str | None, Query()] = None,
    kind: Annotated[str | None, Query()] = None,
    workspace_path: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    """Skill-store catalog: structured recipes with install/link status."""
    if not abom_installed():
        raise HTTPException(
            status_code=503,
            detail=(
                "abom is not installed. pip install abom or pip install 'norns-ide[abom]' "
                "(https://yanchao1999.github.io/abom/)"
            ),
        )
    kind_value = (kind or "").strip().lower() or None
    if kind_value and kind_value not in RECIPE_KINDS:
        raise HTTPException(status_code=400, detail=f"kind must be one of: {', '.join(RECIPE_KINDS)}")
    try:
        cards = list_recipe_cards(query=query, kind=kind_value, workspace_path=workspace_path)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "recipes": [recipe_card_dict(card) for card in cards],
        "count": len(cards),
        "kinds": list(RECIPE_KINDS),
        "workspace_path": workspace_path,
    }


@router.get("/recipes")
async def list_recipes(query: Annotated[str | None, Query()] = None) -> dict[str, Any]:
    cli = _cli()
    lines = cli.cmd_recipes(query)
    return {"recipes": lines, "count": len(lines)}


@router.get("/recipes/{name}")
async def show_recipe(name: str) -> dict[str, Any]:
    return {"text": _run(_cli().cmd_show, name)}


@router.post("/check")
async def check_recipe(payload: RecipeAction) -> dict[str, Any]:
    return {"text": _run(_cli().cmd_check, payload.name.strip())}


@router.post("/install")
async def install_recipe(payload: RecipeAction) -> dict[str, Any]:
    return {"text": _run(_cli().cmd_install_recipe, payload.name.strip())}


@router.post("/enable")
async def enable_abom_recipe(payload: EnableAction) -> dict[str, Any]:
    """One-click install (+ link into board workspace when target_repo is set)."""
    if not abom_installed():
        raise HTTPException(
            status_code=503,
            detail=(
                "abom is not installed. pip install abom or pip install 'norns-ide[abom]' "
                "(https://yanchao1999.github.io/abom/)"
            ),
        )
    try:
        result = enable_recipe(payload.name, target_repo=payload.target_repo)
    except Exception as exc:
        cli = _cli()
        error_type = getattr(cli, "AbomError", RuntimeError)
        if isinstance(exc, error_type):
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return result


@router.get("/installed")
async def list_installed(query: Annotated[str | None, Query()] = None) -> dict[str, Any]:
    cli = _cli()
    names = cli.cmd_search(query)
    return {"installed": names, "count": len(names)}


@router.post("/link")
async def link_tool(payload: LinkAction) -> dict[str, Any]:
    return {
        "text": _run(
            _cli().cmd_link,
            payload.name.strip(),
            payload.target_repo.strip(),
            payload.link_name.strip() if payload.link_name else None,
        )
    }


@router.get("/skills")
async def list_linked_skills(workspace_path: Annotated[str, Query()]) -> dict[str, Any]:
    skills = discover_linked_skills(workspace_path)
    mcps = discover_linked_mcps(workspace_path)
    return {
        "workspace_path": workspace_path,
        "skills": [{"name": skill.name, "description": skill.description, "path": skill.path} for skill in skills],
        "mcps": [{"name": item.name, "command": item.command, "args": item.args, "path": item.path} for item in mcps],
        "count": len(skills),
        "mcp_count": len(mcps),
    }
