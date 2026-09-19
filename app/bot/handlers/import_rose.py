"""
import_rose.py — Migrate from MissRose with one CSV upload.

Switching bots is the real battleground: nobody leaves Rose over features
while re-entering hundreds of blacklisted words by hand. This command imports
a CSV file or Rose JSON export into Aegis's existing blacklist / filter / note
repositories, so an admin can be fully migrated in under a minute.

Usage — reply to a .csv or .json document with /importfromrose, or send the
document with /importfromrose as its caption.

CSV format (header row optional, columns in this order):

    type,keyword,content,action
    blacklist,free crypto,,delete
    filter,hello,Hi there! Welcome to the group,reply
    note,rules,Be kind to each other,

* ``type`` — ``blacklist`` (aliases: banned, blocklist), ``filter``
  (aliases: trigger, autoresponse) or ``note`` (aliases: saved, snippet).
* ``keyword`` — the blacklisted word / filter trigger / note keyword.
* ``content`` — filter response or note body (empty for blacklist rows).
* ``action`` — blacklist consequence: delete (default), warn, mute or ban.
  Ignored for filters and notes.

Rose JSON format (exported from MissRose bot):

    The JSON file exported from MissRose contains:
    - data.filters.filters: array of filter objects
    - data.notes.notes: array of note objects
    - data.blocklists.filters: array of blacklist words

Upsert semantics: re-importing updates existing rows instead of failing, so a
partially-successful first import can simply be fixed and re-run.
"""
import csv
import html
import io
import json
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes

from app.database.connection import get_session
from app.database.models.filter import Filter
from app.database.models.protection import Blacklist
from app.database.base import utc_now
from app.database.repositories.groups import GroupRepository
from app.database.repositories.protection import (
    BlacklistRepository,
    NoteRepository,
)
from app.bot.helpers.ensure_group import guard
from app.bot.middleware.auth import is_admin_or_above

logger = logging.getLogger(__name__)

# One CSV cell grid never needs to be enormous; 200 KB covers tens of
# thousands of rows and keeps memory predictable.
MAX_FILE_BYTES = 200_000

BLACKLIST_ACTIONS = ("delete", "warn", "mute", "ban")

_TYPE_ALIASES = {
    "blacklist": "blacklist",
    "banned": "blacklist",
    "banword": "blacklist",
    "blocklist": "blacklist",
    "filter": "filter",
    "trigger": "filter",
    "autoresponse": "filter",
    "autoresponder": "filter",
    "note": "note",
    "saved": "note",
    "snippet": "note",
}

_ACTION_ALIASES = {
    "": "delete",
    "del": "delete",
    "delete": "delete",
    "warn": "warn",
    "mute": "mute",
    "ban": "ban",
    "kick": "mute",  # closest available consequence
}


@dataclass
class ImportItem:
    kind: str          # blacklist | filter | note
    keyword: str
    content: str
    action: str        # delete | warn | mute | ban (blacklist only)
    line: int          # 1-based CSV line for error reporting


def _norm_cell(cell: Optional[str]) -> str:
    return (cell or "").strip()


@dataclass
class RoseFilter:
    """Structure for a filter from Rose JSON export."""
    trigger: str
    response: str
    action: str = "reply"
    enabled: bool = True


@dataclass
class RoseNote:
    """Structure for a note from Rose JSON export."""
    keyword: str
    content: str


@dataclass
class RoseBlacklist:
    """Structure for a blacklist item from Rose JSON export."""
    word: str
    action: str = "delete"


def _parse_rose_json(text: str) -> Tuple[List[ImportItem], List[str]]:
    """
    Parse Rose JSON export text into import items plus error lines.

    Rose JSON structure:
    - data.filters.filters: array of {trigger, response, action, enabled}
    - data.notes.notes: array of {keyword, content}
    - data.blocklists.filters: array of {word, action}
    """
    items: List[ImportItem] = []
    errors: List[str] = []

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        errors.append(f"Invalid JSON: {e}")
        return items, errors

    if not isinstance(data, dict):
        errors.append("JSON root must be an object")
        return items, errors

    if "data" not in data:
        errors.append("Missing 'data' object in Rose export")
        return items, errors

    rose_data = data.get("data", {})
    if not isinstance(rose_data, dict):
        errors.append("Invalid 'data' object in Rose export")
        return items, errors

    line_num = 0

    # Parse filters
    filters_data = rose_data.get("filters", {})
    if isinstance(filters_data, dict):
        filters_list = filters_data.get("filters")
        if isinstance(filters_list, list):
            for idx, filter_data in enumerate(filters_list, start=1):
                line_num += 1
                if not isinstance(filter_data, dict):
                    errors.append(f"line {line_num}: filter entry must be an object")
                    continue

                trigger = _norm_cell(filter_data.get("trigger"))
                response = _norm_cell(filter_data.get("response"))
                action = _norm_cell(filter_data.get("action", "reply"))
                enabled = filter_data.get("enabled", True)

                if not trigger:
                    errors.append(f"line {line_num}: filter missing trigger")
                    continue
                if not response:
                    errors.append(f"line {line_num}: filter rows need content in 'response'")
                    continue

                # Map Rose actions to Aegis actions
                if action not in ("reply", "delete", "warn", "mute", "ban"):
                    action = "reply"

                items.append(ImportItem(
                    kind="filter",
                    keyword=trigger,
                    content=response,
                    action=action,
                    line=line_num
                ))

    # Parse notes
    notes_data = rose_data.get("notes", {})
    if isinstance(notes_data, dict):
        notes_list = notes_data.get("notes")
        if isinstance(notes_list, list):
            for idx, note_data in enumerate(notes_list, start=1):
                line_num += 1
                if not isinstance(note_data, dict):
                    errors.append(f"line {line_num}: note entry must be an object")
                    continue

                keyword = _norm_cell(note_data.get("keyword"))
                content = _norm_cell(note_data.get("content"))

                if not keyword:
                    errors.append(f"line {line_num}: note missing keyword")
                    continue
                if not content:
                    errors.append(f"line {line_num}: note rows need content")
                    continue

                items.append(ImportItem(
                    kind="note",
                    keyword=keyword,
                    content=content,
                    action="",
                    line=line_num
                ))

    # Parse blocklists (blacklist)
    blocklists_data = rose_data.get("blocklists", {})
    if isinstance(blocklists_data, dict):
        blocklists_list = blocklists_data.get("filters")
        if isinstance(blocklists_list, list):
            for idx, bl_data in enumerate(blocklists_list, start=1):
                line_num += 1
                if not isinstance(bl_data, dict):
                    errors.append(f"line {line_num}: blacklist entry must be an object")
                    continue

                word = _norm_cell(bl_data.get("word"))
                action = _norm_cell(bl_data.get("action", "delete"))

                if not word:
                    errors.append(f"line {line_num}: blacklist missing word")
                    continue

                # Map Rose blacklist actions to Aegis actions
                action = _ACTION_ALIASES.get(action.lower(), action.lower())
                if action not in BLACKLIST_ACTIONS:
                    errors.append(f"line {line_num}: unknown action '{bl_data.get('action')}'")
                    continue

                items.append(ImportItem(
                    kind="blacklist",
                    keyword=word,
                    content="",
                    action=action,
                    line=line_num
                ))

    return items, errors


def parse_import_csv(text: str) -> Tuple[List[ImportItem], List[str]]:
    """
    Parse CSV text into import items plus human-readable error lines.

    Errors never abort the import: a 500-row file with three bad rows imports
    497 items and lists the three problems, rather than importing nothing.
    """
    items: List[ImportItem] = []
    errors: List[str] = []

    reader = csv.reader(io.StringIO(text))
    for row_num, raw in enumerate(reader, start=1):
        cells = [_norm_cell(c) for c in raw]
        if not any(cells):
            continue  # blank line, not an error
        # Header row: the first cell naming a column. Recognised explicitly so
        # "type" as a blacklisted word doesn't silently look like a header.
        if row_num == 1 and cells[0].lower() in ("type", "kind"):
            continue

        kind = _TYPE_ALIASES.get(cells[0].lower())
        if kind is None:
            errors.append(f"line {row_num}: unknown type {cells[0]!r}")
            continue
        keyword = cells[1].lower() if len(cells) > 1 else ""
        content = cells[2] if len(cells) > 2 else ""
        raw_action = cells[3].lower() if len(cells) > 3 else ""

        if not keyword:
            errors.append(f"line {row_num}: missing keyword")
            continue
        if kind == "blacklist":
            action = _ACTION_ALIASES.get(raw_action or "", "")
            if action == "":
                errors.append(
                    f"line {row_num}: unknown action {raw_action!r} "
                    "(use delete, warn, mute or ban)"
                )
                continue
            if len(keyword) > 500:
                errors.append(f"line {row_num}: blacklisted word too long (max 500)")
                continue
            items.append(ImportItem(kind, keyword, "", action, row_num))
        else:
            if not content:
                errors.append(
                    f"line {row_num}: {kind} rows need content in column 3"
                )
                continue
            limit = 200 if kind == "filter" else 255
            if len(keyword) > limit:
                errors.append(
                    f"line {row_num}: keyword too long (max {limit})"
                )
                continue
            if kind == "filter" and len(content) > 3000:
                errors.append(f"line {row_num}: filter response too long (max 3000)")
                continue
            items.append(ImportItem(kind, keyword, content, "delete", row_num))

    return items, errors


async def apply_import_items(session, group_id: int, items: List[ImportItem]) -> dict:
    """
    Upsert parsed items into this group's blacklist / filters / notes.

    Runs inside the caller's session so the whole import is one transaction:
    a failure partway rolls back everything instead of leaving a half-migrated
    group. Returns per-kind counts of written rows.

    Uses bulk operations for blacklists to avoid N+1 query patterns on large
    imports (Rose exports can contain thousands of words).
    """
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    counts = {"blacklist": 0, "filter": 0, "note": 0}

    bl_repo = BlacklistRepository(session)
    note_repo = NoteRepository(session)

    # Batch blacklist items for bulk upsert
    blacklist_items = [i for i in items if i.kind == "blacklist"]
    filter_items = [i for i in items if i.kind == "filter"]
    note_items = [i for i in items if i.kind == "note"]

    if blacklist_items:
        # Use bulk upsert for blacklists — much faster than one query per word
        await _bulk_upsert_blacklist(session, group_id, blacklist_items)
        counts["blacklist"] = len(blacklist_items)

    for item in filter_items:
        # Manual upsert mirrors filter_command's semantics.
        q = await session.execute(
            select(Filter).where(
                Filter.group_id == group_id,
                Filter.trigger == item.keyword,
            )
        )
        f = q.scalar_one_or_none()
        if f is None:
            session.add(
                Filter(
                    group_id=group_id,
                    trigger=item.keyword,
                    response=item.content,
                    enabled=True,
                    created_at=utc_now(),
                )
            )
        else:
            f.response = item.content
            f.enabled = True
        counts["filter"] += 1

    for item in note_items:
        await note_repo.save_note(group_id, item.keyword, item.content)
        counts["note"] += 1

    await session.flush()
    return counts


async def _bulk_upsert_blacklist(session, group_id: int, items: List[ImportItem]) -> None:
    """
    Bulk upsert blacklist words using INSERT ... ON CONFLICT.

    Each word is normalised at write time so the hot path (message checking)
    does not need to re-normalise every entry.
    """
    from app.anti_spam.normalize import normalize
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    # Build payload with pre-computed normalized forms
    payload = [
        {
            "group_id": group_id,
            "word": item.keyword.lower().strip(),
            "normalized_word": normalize(item.keyword),
            "action": item.action,
        }
        for item in items
    ]

    # Detect dialect and use appropriate bulk insert
    dialect_name = session.bind.dialect.name if session.bind else "sqlite"

    if dialect_name == "postgresql":
        stmt = pg_insert(Blacklist).values(payload)
        upsert_stmt = stmt.on_conflict_do_update(
            index_elements=["group_id", "word"],
            set_={
                "action": stmt.excluded.action,
                "normalized_word": stmt.excluded.normalized_word,
            },
        )
        await session.execute(upsert_stmt)
    else:
        # SQLite: use INSERT OR REPLACE style via on_conflict_do_update
        # Note: SQLite's insert() doesn't support constraint= parameter,
        # so we use index_elements instead
        stmt = sqlite_insert(Blacklist).values(payload)
        upsert_stmt = stmt.on_conflict_do_update(
            index_elements=["group_id", "word"],
            set_={
                "action": stmt.excluded.action,
                "normalized_word": stmt.excluded.normalized_word,
            },
        )
        await session.execute(upsert_stmt)


def _usage_text() -> str:
    return (
        "<b>Migrate from Rose</b>\n\n"
        "Reply to a CSV or JSON document with this command (or send the document with "
        "/importfromrose as its caption).\n\n"
        "CSV format:\n"
        "<code>type,keyword,content,action</code>\n"
        "<code>blacklist,free crypto,,delete</code>\n"
        "<code>filter,hello,Hi there! Welcome,reply</code>\n"
        "<code>note,rules,Be kind to each other,</code>\n\n"
        "Rose JSON format (exported from MissRose bot):\n"
        "• Filters: data.filters.filters array\n"
        "• Notes: data.notes.notes array\n"
        "• Blacklist: data.blocklists.filters array\n\n"
        "• type: blacklist (aliases: banned, blocklist), filter (trigger), "
        "note (saved)\n"
        "• action: delete (default), warn, mute, ban — blacklist rows only\n\n"
        "Existing entries are updated, so you can fix rows and re-import."
    )


async def _read_document(document, context) -> Tuple[Optional[str], str]:
    """Download a Telegram document and decode it. Returns (text, error)."""
    if document.file_size and document.file_size > MAX_FILE_BYTES:
        return None, (
            f"File is too large ({document.file_size} bytes, "
            f"max {MAX_FILE_BYTES})."
        )
    try:
        tg_file = await context.bot.get_file(document.file_id)
        data = await tg_file.download_as_bytearray()
    except Exception as e:
        return None, f"Could not download the file ({type(e).__name__}: {e})."
    return data.decode("utf-8", errors="replace"), ""


async def importfromrose_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /importfromrose against an uploaded CSV or JSON document."""
    if await guard(update, context, "importfromrose") is None:
        return
    chat = update.effective_chat
    msg = update.effective_message
    if not await is_admin_or_above(update):
        await msg.reply_html("<b>Access denied.</b>\nThis command is restricted to administrators.")
        return

    # The document can arrive three ways: attached to this message (caption
    # command), or the command replying to a document sent separately.
    document = msg.document
    if document is None and msg.reply_to_message is not None:
        document = msg.reply_to_message.document
    if document is None:
        await msg.reply_html(_usage_text())
        return

    text, error = await _read_document(document, context)
    if error:
        await msg.reply_html(f"<b>Import failed.</b>\n{html.escape(error)}")
        return

    # Detect format: JSON if it starts with '{' or '[', otherwise CSV
    content = text or ""
    if content.strip().startswith(("{", "[")):
        items, errors = _parse_rose_json(content)
        source_type = "Rose JSON"
    else:
        items, errors = parse_import_csv(content)
        source_type = "CSV"

    if not items:
        lines = [f"<b>Nothing to import from {source_type}.</b>"]
        lines += [f"• {html.escape(e)}" for e in errors[:5]]
        if len(errors) > 5:
            lines.append(f"… and {len(errors) - 5} more problems")
        lines.append("")
        lines.append("Send /importfromrose to see the expected format.")
        await msg.reply_html("\n".join(lines))
        return

    async with get_session() as session:
        g = await GroupRepository(session).get_by_telegram_id(chat.id)
        if not g:
            await msg.reply_text("Group is not registered yet. Please try again in a moment.")
            return
        counts = await apply_import_items(session, g.id, items)
        await session.commit()

    logger.info(
        f"Rose import in chat {chat.id} ({source_type}): {counts} written, "
        f"{len(errors)} rows skipped"
    )
    lines = [
        f"<b>Migration from Rose ({source_type}) complete.</b>",
        f"• Blacklist words: <b>{counts['blacklist']}</b>",
        f"• Filters: <b>{counts['filter']}</b>",
        f"• Notes: <b>{counts['note']}</b>",
    ]
    if errors:
        lines.append(f"• Skipped rows: <b>{len(errors)}</b>")
        lines += [f"  • {html.escape(e)}" for e in errors[:5]]
        if len(errors) > 5:
            lines.append(f"  … and {len(errors) - 5} more")
    await msg.reply_html("\n".join(lines))
