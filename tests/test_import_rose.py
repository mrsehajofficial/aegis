"""
Tests for the /importfromrose migration command.

Parsing is a pure function so every format edge case is cheap to test. The
apply step runs against a real in-memory SQLite database so the upsert
behaviour is proven, not assumed.
"""
import pytest

from app.bot.handlers.import_rose import ImportItem, apply_import_items, parse_import_csv


CSV_WITH_HEADER = (
    "type,keyword,content,action\n"
    "blacklist,free crypto,,delete\n"
    "filter,hello,Hi there! Welcome to the group,reply\n"
    "note,rules,Be kind to each other,\n"
)


class TestParseCsv:
    def test_the_documented_example_parses_fully(self):
        items, errors = parse_import_csv(CSV_WITH_HEADER)
        assert errors == []
        assert [(i.kind, i.keyword) for i in items] == [
            ("blacklist", "free crypto"),
            ("filter", "hello"),
            ("note", "rules"),
        ]
        assert items[0].action == "delete"
        assert items[1].content == "Hi there! Welcome to the group"
        assert items[2].content == "Be kind to each other"

    def test_header_row_is_optional(self):
        items, errors = parse_import_csv("blacklist,spam,,\n")
        assert errors == []
        assert len(items) == 1

    def test_type_aliases_are_accepted(self):
        csv_text = (
            "banned,word one,,\n"
            "blocklist,word two,,mute\n"
            "trigger,hi,Hello!,\n"
            "saved,tips,Use /help,\n"
        )
        items, errors = parse_import_csv(csv_text)
        assert errors == []
        assert [i.kind for i in items] == [
            "blacklist",
            "blacklist",
            "filter",
            "note",
        ]

    def test_action_aliases_and_defaults(self):
        csv_text = "blacklist,w,,del\nblacklist,x,,BAN\nblacklist,y,,\n"
        items, _ = parse_import_csv(csv_text)
        assert [i.action for i in items] == ["delete", "ban", "delete"]

    def test_kick_maps_to_the_closest_available_action(self):
        items, _ = parse_import_csv("blacklist,w,,kick\n")
        assert items[0].action == "mute"

    def test_unknown_type_is_reported_not_fatal(self):
        items, errors = parse_import_csv(
            "blacklist,good,,\nwidget,bad,,\nblacklist,also good,,\n"
        )
        assert len(items) == 2
        assert errors == ["line 2: unknown type 'widget'"]

    def test_missing_keyword_is_reported(self):
        _, errors = parse_import_csv("blacklist,,,\n")
        assert errors == ["line 1: missing keyword"]

    def test_filter_and_note_rows_need_content(self):
        _, errors = parse_import_csv("filter,hi,,\nnote,rules,,\n")
        assert errors == [
            "line 1: filter rows need content in column 3",
            "line 2: note rows need content in column 3",
        ]

    def test_unknown_blacklist_action_is_reported(self):
        _, errors = parse_import_csv("blacklist,w,,nuke\n")
        assert "unknown action 'nuke'" in errors[0]

    def test_blank_lines_are_skipped_silently(self):
        items, errors = parse_import_csv("\n\nblacklist,word,,\n\n")
        assert errors == []
        assert len(items) == 1

    def test_quoted_csv_cells_with_commas_parse_correctly(self):
        csv_text = 'note,rules,"Be kind, no spam, have fun",\n'
        items, errors = parse_import_csv(csv_text)
        assert errors == []
        assert items[0].content == "Be kind, no spam, have fun"

    def test_keywords_are_normalised_to_lowercase(self):
        items, _ = parse_import_csv("BLACKLIST,FREE CRYPTO,,\n")
        assert items[0].keyword == "free crypto"

    def test_overlong_fields_are_rejected(self):
        _, errors = parse_import_csv(
            f"blacklist,{'w' * 501},,\n"
            f"filter,{'k' * 201},response,\n"
            f"filter,ok,{'r' * 3001},\n"
        )
        assert any("blacklisted word too long" in e for e in errors)
        assert any("keyword too long" in e for e in errors)
        assert any("response too long" in e for e in errors)

    def test_empty_input_yields_nothing(self):
        items, errors = parse_import_csv("")
        assert items == [] and errors == []

    def test_line_numbers_are_one_based_csv_lines(self):
        _, errors = parse_import_csv("blacklist,ok,,\nbogus,x,,\n")
        assert errors == ["line 2: unknown type 'bogus'"]


@pytest.fixture
async def db_session(tmp_path):
    """A real in-memory SQLite session with the full schema created."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    import app.database.models  # noqa: F401 — register all model metadata
    from app.database.base import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


class TestApplyItems:
    async def test_all_three_kinds_are_written(self, db_session):
        items, errors = parse_import_csv(CSV_WITH_HEADER)
        assert errors == []
        counts = await apply_import_items(db_session, group_id=1, items=items)
        assert counts == {"blacklist": 1, "filter": 1, "note": 1}

        from app.database.repositories.protection import (
            BlacklistRepository,
            NoteRepository,
        )
        from sqlalchemy import select
        from app.database.models.filter import Filter

        bl = (await BlacklistRepository(db_session).get_by_group(1))[0]
        assert (bl.word, bl.action) == ("free crypto", "delete")

        f = (await db_session.execute(
            select(Filter).where(Filter.group_id == 1)
        )).scalar_one()
        assert (f.trigger, f.response, f.enabled) == (
            "hello",
            "Hi there! Welcome to the group",
            True,
        )

        note = (await NoteRepository(db_session).get_by_group(1))[0]
        assert (note.keyword, note.content) == ("rules", "Be kind to each other")

    async def test_reimport_updates_existing_rows_instead_of_duplicating(
        self, db_session
    ):
        items, _ = parse_import_csv("blacklist,spam,,mute\n")
        await apply_import_items(db_session, 1, items)
        items2, _ = parse_import_csv("blacklist,spam,,ban\n")
        counts = await apply_import_items(db_session, 1, items2)
        assert counts == {"blacklist": 1, "filter": 0, "note": 0}

        from app.database.repositories.protection import BlacklistRepository

        rows = await BlacklistRepository(db_session).get_by_group(1)
        assert len(rows) == 1  # upserted, not duplicated
        assert rows[0].action == "ban"

    async def test_filter_response_is_updated_on_reimport(self, db_session):
        items, _ = parse_import_csv("filter,hello,Old response,\n")
        await apply_import_items(db_session, 1, items)
        items2, _ = parse_import_csv("filter,hello,New response,\n")
        await apply_import_items(db_session, 1, items2)

        from sqlalchemy import select
        from app.database.models.filter import Filter

        rows = (await db_session.execute(
            select(Filter).where(Filter.group_id == 1)
        )).scalars().all()
        assert len(rows) == 1
        assert rows[0].response == "New response"

    async def test_all_kinds_share_one_session(self, db_session):
        """Everything is written through the caller's single session, so the
        command's commit covers the whole migration atomically."""
        items, _ = parse_import_csv(CSV_WITH_HEADER)
        assert db_session.in_transaction() is False
        counts = await apply_import_items(db_session, 1, items)
        assert counts == {"blacklist": 1, "filter": 1, "note": 1}
        # Rows are flushed (queryable) but not committed — the command owns
        # the commit, which is what makes a partial import impossible.
        assert db_session.in_transaction() is True
