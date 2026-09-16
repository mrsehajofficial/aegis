"""
import_rose.py — Migrate from MissRose with one CSV upload.

Switching bots is the real battleground: nobody leaves Rose over features
while re-entering hundreds of blacklisted words by hand. This command imports
a CSV file into Aegis's existing blacklist / filter / note repositories, so an
admin can be fully migrated in under a minute.

Usage — reply to a .csv document with /importfromrose, or send the document
with /importfromrose as its caption.

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

Upsert semantics: re-importing updates existing rows instead of failing, so a
partially-successful first import can simply be fixed and re-run.
"""
import csv
import html
import io
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes

from app.database.connection import get_session
from app.database.models.filter import Filter
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
    """
    counts = {"blacklist": 0, "filter": 0, "note": 0}

    bl_repo = BlacklistRepository(session)
    note_repo = NoteRepository(session)

    for item in items:
        if item.kind == "blacklist":
            await bl_repo.add_word(group_id, item.keyword, item.action)
        elif item.kind == "filter":
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
        else:
            await note_repo.save_note(group_id, item.keyword, item.content)
        counts[item.kind] += 1

    await session.flush()
    return counts


def _usage_text() -> str:
    return (
        "<b>Migrate from Rose</b>\n\n"
        "Reply to a CSV document with this command (or send the document with "
        "/importfromrose as its caption). Format:\n\n"
        "<code>type,keyword,content,action</code>\n"
        "<code>blacklist,free crypto,,delete</code>\n"
        "<code>filter,hello,Hi there! Welcome,reply</code>\n"
        "<code>note,rules,Be kind to each other,</code>\n\n"
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
    """Handle /importfromrose against an uploaded CSV document."""
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

    csv_text, error = await _read_document(document, context)
    if error:
        await msg.reply_html(f"<b>Import failed.</b>\n{html.escape(error)}")
        return

    items, errors = parse_import_csv(csv_text or "")
    if not items:
        lines = ["<b>Nothing to import.</b>"]
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
        f"Rose import in chat {chat.id}: {counts} written, "
        f"{len(errors)} rows skipped"
    )
    lines = [
        "<b>Migration from Rose complete.</b>",
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
