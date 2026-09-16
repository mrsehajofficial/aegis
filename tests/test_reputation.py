"""
Tests for the cross-group spam fingerprint network.

The reputation store is module-global state, exactly like the flood store, so
every test gets a clean backend via an autouse fixture. Timestamps are
injected, so TTL behaviour is tested without sleeping.
"""
import time

import pytest

from app.anti_spam import AntiSpamChecker, GroupProtectionSettings
from app.anti_spam import reputation
from app.anti_spam.reputation import (
    InMemoryReputationStore,
    fingerprint,
    known_spam_groups,
    record_spam,
)


@pytest.fixture(autouse=True)
def _fresh_reputation_store():
    """Reputation state is module-global — isolate every test case."""
    store = InMemoryReputationStore()
    reputation.configure_store(store)
    reputation.configure_fallback(InMemoryReputationStore())
    yield store
    reputation.configure_store(InMemoryReputationStore())
    reputation.configure_fallback(InMemoryReputationStore())


class TestFingerprint:
    def test_is_stable_for_the_same_text(self):
        assert fingerprint("buy now") == fingerprint("buy now")

    def test_evasion_variants_collapse_to_one_fingerprint(self):
        # The whole point: spammers mutate text to dodge exact-match filters,
        # but the normalised fingerprint must not care.
        variants = [
            "free crypto now",
            "freeee crypto now",           # character repeats
            "FREE CRYPTO NOW",             # case
            "ｆｒｅｅ crypto now",         # fullwidth letters
            "fr33 crypto now",             # leetspeak
            "free cry\u200bpto now",       # zero-width space inside a word
            "fr\u0435\u0435 crypto now",   # Cyrillic е/е homoglyphs
        ]
        assert len({fingerprint(v) for v in variants}) == 1

    def test_different_texts_fingerprint_differently(self):
        assert fingerprint("buy now") != fingerprint("sell now")

    def test_is_one_way_hex(self):
        fp = fingerprint("some secret campaign text")
        assert len(fp) == 64
        int(fp, 16)  # valid hex
        assert "secret" not in fp


class TestInMemoryStore:
    async def test_flags_from_other_groups_are_counted(self):
        store = InMemoryReputationStore()
        fp = fingerprint("spam message")
        await store.flag(fp, -100111, now=1000.0, ttl_seconds=86400)
        await store.flag(fp, -100222, now=1001.0, ttl_seconds=86400)
        assert await store.groups_for(fp, -100333, 1002.0, 86400) == [
            -100111,
            -100222,
        ]

    async def test_own_group_never_counts_against_itself(self):
        store = InMemoryReputationStore()
        fp = fingerprint("spam message")
        await store.flag(fp, -100111, now=1000.0, ttl_seconds=86400)
        assert await store.groups_for(fp, -100111, 1001.0, 86400) == []

    async def test_repeated_flags_from_one_group_dedupe(self):
        store = InMemoryReputationStore()
        fp = fingerprint("spam message")
        for i in range(5):
            await store.flag(fp, -100111, now=1000.0 + i, ttl_seconds=86400)
        assert await store.groups_for(fp, -100999, 1010.0, 86400) == [-100111]

    async def test_entries_expire_after_the_ttl(self):
        store = InMemoryReputationStore()
        fp = fingerprint("spam message")
        await store.flag(fp, -100111, now=1000.0, ttl_seconds=86400)
        # One second before expiry it still counts…
        assert await store.groups_for(fp, -100999, 1000 + 86399, 86400) == [
            -100111
        ]
        # …and just after, it does not.
        assert await store.groups_for(fp, -100999, 1000 + 86401, 86400) == []

    async def test_forget_chat_withdraws_all_contributions(self):
        store = InMemoryReputationStore()
        fp_a, fp_b = fingerprint("alpha"), fingerprint("beta")
        await store.flag(fp_a, -100111, now=1000.0, ttl_seconds=86400)
        await store.flag(fp_b, -100111, now=1000.0, ttl_seconds=86400)
        await store.flag(fp_a, -100222, now=1000.0, ttl_seconds=86400)

        await store.forget_chat(-100111)

        assert await store.groups_for(fp_a, -100999, 1001.0, 86400) == [-100222]
        assert await store.groups_for(fp_b, -100999, 1001.0, 86400) == []


class TestPublicApi:
    async def test_record_then_lookup_across_groups(self):
        await record_spam(-100111, "free crypto now", now=1000.0)
        await record_spam(-100222, "freeee CRYPTO now", now=1005.0)
        # The second group's variant text fingerprints identically, so the
        # campaign is already known there.
        assert await known_spam_groups("FREE CRYPTO NOW", -100333, now=1010.0) == 2

    async def test_empty_text_never_counts(self):
        assert await known_spam_groups("", -100111) == 0

    async def test_single_group_is_below_the_threshold(self):
        await record_spam(-100111, "only one group", now=1000.0)
        assert await known_spam_groups("only one group", -100222, now=1001.0) == 1


class _FakeUser:
    def __init__(self, user_id: int = 42):
        self.id = user_id


class _FakeMessage:
    def __init__(self, text: str, user_id: int = 42):
        self.text = text
        self.caption = None
        self.from_user = _FakeUser(user_id)
        self.forward_date = None
        self.message_id = 5
        self.deleted = False

    async def delete(self):
        self.deleted = True


class _FakeBot:
    async def send_message(self, *a, **k):
        pass

    async def restrict_chat_member(self, *a, **k):
        return True


class _FakeContext:
    def __init__(self):
        self.bot = _FakeBot()


def _checker(chat_id: int = -100999) -> AntiSpamChecker:
    return AntiSpamChecker(
        _FakeContext(),
        chat_id=chat_id,
        settings=GroupProtectionSettings(anti_spam_enabled=True),
    )


class TestAntiSpamCheckerIntegration:
    """Fakes mirroring test_antispam_edits.py conventions."""

    async def test_message_flagged_by_two_other_groups_is_deleted(self):
        # The core wedge: the text itself passes every local heuristic, but the
        # network already knows it.
        text = "hey come join us, it is a really nice day today"
        # Wall-clock stamps: the checker looks records up with time.time().
        await record_spam(-100111, text)
        await record_spam(-100222, text)

        message = _FakeMessage(text)
        assert await _checker().check_message(message) == "spam_deleted"
        assert message.deleted is True

    async def test_message_flagged_by_one_group_alone_passes(self):
        text = "hey come join us, it is a really nice day today"
        await record_spam(-100111, text)

        message = _FakeMessage(text)
        assert await _checker().check_message(message) is None
        assert message.deleted is False

    async def test_own_group_verdict_does_not_retrigger_itself(self):
        text = "hey come join us, it is a really nice day today"
        await record_spam(-100999, text)  # this very group

        message = _FakeMessage(text)
        assert await _checker(chat_id=-100999).check_message(message) is None

    async def test_a_confirmed_verdict_is_contributed_to_the_network(self):
        # An edit introducing a link is locally-detected spam; the fingerprint
        # must land in the store so other groups get pre-warned.
        text = "grab it at spam.ru"
        message = _FakeMessage(text)
        checker = _checker(chat_id=-100111)
        assert await checker.check_message(message, is_edit=True) == "spam_deleted"

        fp = fingerprint(text)
        store = reputation.get_reputation_store()
        # Wall clock again: the checker recorded the verdict at time.time().
        # Query from a DIFFERENT group's perspective: the own-chat exclusion
        # means -100111 can never see its own flag (by design), but everyone
        # else can.
        now = time.time()
        own_view = await store.groups_for(fp, -100111, now=now, ttl_seconds=86400)
        assert own_view == []  # a group is never warned by its own verdict
        other_view = await store.groups_for(fp, -100999, now=now, ttl_seconds=86400)
        assert other_view == [-100111]

    async def test_evasion_of_the_local_heuristic_still_spreads(self):
        # Group A deletes "grab it at spam.ru"; group B receives the mutated
        # form. Local heuristics pass it (one link, no edit), but the shared
        # fingerprint does not.
        await record_spam(-100111, "grab it at spam.ru")
        await record_spam(-100222, "GRAB IT AT SPAM.RU")

        message = _FakeMessage("gr\u0430b it at spam.ru")  # Cyrillic a
        assert await _checker().check_message(message) == "spam_deleted"


class TestInitSelection:
    async def test_without_redis_url_the_memory_store_is_selected(self, monkeypatch):
        from app.config.settings import settings

        monkeypatch.setattr(settings, "REDIS_URL", "", raising=False)
        store = await reputation.init_reputation_store()
        assert isinstance(store, InMemoryReputationStore)
        assert store.name == "memory"
