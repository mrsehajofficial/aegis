"""
API layer for Aegis Telegram Mini App Dashboard.

Every route is guarded by :func:`authorize_miniapp_request` (declared as an
app-wide dependency below), which verifies the Telegram ``initData`` signature
and that the caller is an admin of the group in the path. Declaring a new
endpoint therefore protects it by default - there is no way to forget the gate.
For local UI work only, ``MINIAPP_AUTH_DISABLED=true`` turns the gate off.
"""
from typing import Optional
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.api.auth import authorize_miniapp_request
from app.database.connection import get_session
from app.database.repositories.groups import GroupRepository
from app.database.repositories.settings import SettingsRepository
from app.database.repositories.protection import BlacklistRepository, NoteRepository
from app.database.repositories.filters import FilterRepository

app = FastAPI(
    title="Aegis Dashboard API",
    version="1.0.0",
    dependencies=[Depends(authorize_miniapp_request)],
)


class SettingsUpdate(BaseModel):
    welcome_enabled: Optional[bool] = None
    goodbye_enabled: Optional[bool] = None
    anti_flood_enabled: Optional[bool] = None
    anti_spam_enabled: Optional[bool] = None
    warn_limit: Optional[int] = Field(None, ge=1, le=20)
    welcome_message: Optional[str] = None
    goodbye_message: Optional[str] = None
    rules: Optional[str] = None


class FilterCreate(BaseModel):
    trigger: str = Field(..., min_length=1, max_length=255)
    response: str = Field(..., max_length=3000)
    enabled: bool = True


class BlacklistCreate(BaseModel):
    word: str = Field(..., min_length=1, max_length=500)
    action: str = Field(default="delete", pattern="^(delete|warn|mute|ban)$")


class NoteCreate(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., max_length=10000)


async def _get_group(telegram_id: int):
    async with get_session() as session:
        repo = GroupRepository(session)
        return await repo.get_by_telegram_id(telegram_id)


@app.get("/api/v1/groups/{telegram_id}/settings")
async def get_settings(telegram_id: int):
    group = await _get_group(telegram_id)
    if not group:
        raise HTTPException(404, "Group not found")
    async with get_session() as session:
        s = await SettingsRepository(session).get_or_create(group.id)
        return {
            "welcome_enabled": s.welcome_enabled,
            "goodbye_enabled": s.goodbye_enabled,
            "anti_flood_enabled": s.anti_flood_enabled,
            "anti_spam_enabled": s.anti_spam_enabled,
            "log_enabled": s.log_enabled,
            "reports_enabled": s.reports_enabled,
            "warn_limit": s.warn_limit,
            "welcome_message": s.welcome_message,
            "goodbye_message": s.goodbye_message,
            "rules": s.rules,
        }


@app.patch("/api/v1/groups/{telegram_id}/settings")
async def update_settings(telegram_id: int, data: SettingsUpdate):
    group = await _get_group(telegram_id)
    if not group:
        raise HTTPException(404, "Group not found")
    async with get_session() as session:
        s = await SettingsRepository(session).get_or_create(group.id)
        for k, v in data.model_dump(exclude_unset=True).items():
            if hasattr(s, k):
                setattr(s, k, v)
        await session.commit()
        return {"success": True}


@app.get("/api/v1/groups/{telegram_id}/filters")
async def list_filters(telegram_id: int):
    group = await _get_group(telegram_id)
    if not group:
        raise HTTPException(404, "Group not found")
    async with get_session() as session:
        items = await FilterRepository(session).get_by_group(group.id)
        return [{"id": f.id, "trigger": f.trigger, "response": f.response, "enabled": f.enabled} for f in items]


@app.post("/api/v1/groups/{telegram_id}/filters", status_code=201)
async def create_filter(telegram_id: int, data: FilterCreate):
    group = await _get_group(telegram_id)
    if not group:
        raise HTTPException(404, "Group not found")
    async with get_session() as session:
        f = await FilterRepository(session).create(group.id, data.trigger.lower().strip(), data.response, data.enabled)
        await session.commit()
        return {"id": f.id, "trigger": f.trigger, "response": f.response, "enabled": f.enabled}


@app.delete("/api/v1/groups/{telegram_id}/filters/{filter_id}")
async def delete_filter(telegram_id: int, filter_id: int):
    group = await _get_group(telegram_id)
    if not group:
        raise HTTPException(404, "Group not found")
    async with get_session() as session:
        repo = FilterRepository(session)
        f = await repo.get_by_id(filter_id)
        if not f or f.group_id != group.id:
            raise HTTPException(404, "Filter not found")
        await repo.delete_by_id(filter_id)
        await session.commit()
        return {"success": True}


@app.get("/api/v1/groups/{telegram_id}/blacklist")
async def list_blacklist(telegram_id: int):
    group = await _get_group(telegram_id)
    if not group:
        raise HTTPException(404, "Group not found")
    async with get_session() as session:
        items = await BlacklistRepository(session).get_by_group(group.id)
        return [{"id": w.id, "word": w.word, "action": w.action} for w in items]


@app.post("/api/v1/groups/{telegram_id}/blacklist", status_code=201)
async def add_blacklist(telegram_id: int, data: BlacklistCreate):
    group = await _get_group(telegram_id)
    if not group:
        raise HTTPException(404, "Group not found")
    async with get_session() as session:
        w = await BlacklistRepository(session).add_word(group.id, data.word, data.action)
        await session.commit()
        return {"id": w.id, "word": w.word, "action": w.action}


@app.delete("/api/v1/groups/{telegram_id}/blacklist/{word_id}")
async def delete_blacklist(telegram_id: int, word_id: int):
    group = await _get_group(telegram_id)
    if not group:
        raise HTTPException(404, "Group not found")
    async with get_session() as session:
        from sqlalchemy import select
        from app.database.models.protection import Blacklist
        r = await session.execute(select(Blacklist).where(Blacklist.id == word_id, Blacklist.group_id == group.id))
        w = r.scalar_one_or_none()
        if not w:
            raise HTTPException(404, "Word not found")
        await session.delete(w)
        await session.commit()
        return {"success": True}


@app.get("/api/v1/groups/{telegram_id}/notes")
async def list_notes(telegram_id: int):
    group = await _get_group(telegram_id)
    if not group:
        raise HTTPException(404, "Group not found")
    async with get_session() as session:
        items = await NoteRepository(session).get_by_group(group.id)
        return [{"id": n.id, "keyword": n.keyword, "content": n.content} for n in items]


@app.post("/api/v1/groups/{telegram_id}/notes", status_code=201)
async def upsert_note(telegram_id: int, data: NoteCreate):
    group = await _get_group(telegram_id)
    if not group:
        raise HTTPException(404, "Group not found")
    async with get_session() as session:
        n = await NoteRepository(session).save_note(group.id, data.keyword, data.content)
        await session.commit()
        return {"id": n.id, "keyword": n.keyword, "content": n.content}


@app.delete("/api/v1/groups/{telegram_id}/notes/{note_id}")
async def delete_note(telegram_id: int, note_id: int):
    group = await _get_group(telegram_id)
    if not group:
        raise HTTPException(404, "Group not found")
    async with get_session() as session:
        deleted = await NoteRepository(session).remove_note_by_id(note_id)
        if not deleted or deleted.group_id != group.id:
            raise HTTPException(404, "Note not found")
        await session.commit()
        return {"success": True}


@app.get("/api/v1/health")
async def health():
    return {"status": "ok"}
