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
    contribute_to_feed,
    fingerprint,
    known_spam_groups,
    pseudonymize_chat_id,
    record_spam,
    salted_fingerprint,
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


class TestSaltedFingerprint:
    def test_same_text_and_salt_produce_same_hmac(self):
        assert salted_fingerprint("buy now", "secret-salt") == salted_fingerprint("buy now", "secret-salt")

    def test_different_salts_produce_different_fingerprints(self):
        assert salted_fingerprint("buy now", "salt-a") != salted_fingerprint("buy now", "salt-b")

    def test_salted_fingerprint_is_not_the_plain_sha256(self):
        fp = fingerprint("buy now")
        sfp = salted_fingerprint("buy now", "some-key")
        assert fp != sfp

    def test_different_texts_produce_different_hmac(self):
        assert salted_fingerprint("buy now", "key") != salted_fingerprint("sell now", "key")

    def test_salted_variants_collapse_to_one_value(self):
        # The salted fingerprint builds on the normalised form, so evasion
        # variants that share a fingerprint must also share a salted fingerprint.
        salt = "shared-key"
        variants = [
            "free crypto now",
            "freeee crypto now",
            "FREE CRYPTO NOW",
        ]
        assert len({salted_fingerprint(v, salt) for v in variants}) == 1


class TestPseudonymizeChatId:
    def test_same_chat_id_and_salt_produces_stable_pseudonym(self):
        assert pseudonymize_chat_id(-100111, "salt") == pseudonymize_chat_id(-100111, "salt")

    def test_different_chat_ids_produce_different_pseudonyms(self):
        assert pseudonymize_chat_id(-100111, "salt") != pseudonymize_chat_id(-100222, "salt")

    def test_different_salts_produce_different_pseudonyms(self):
        assert pseudonymize_chat_id(-100111, "salt-a") != pseudonymize_chat_id(-100111, "salt-b")

    def test_pseudonym_is_hex_and_not_the_raw_id(self):
        pseudo = pseudonymize_chat_id(-100111, "salt")
        assert len(pseudo) == 64
        int(pseudo, 16)  # valid hex
        assert "100111" not in pseudo


class TestContributeToFeed:
    async def test_returns_false_when_no_feed_url(self, monkeypatch):
        monkeypatch.setattr(reputation.settings, "REPUTATION_FEED_URL", "", raising=False)
        monkeypatch.setattr(reputation.settings, "REPUTATION_SALT", "key", raising=False)
        result = await contribute_to_feed("spam text", -100111)
        assert result is False

    async def test_returns_false_when_salt_is_empty(self, monkeypatch):
        monkeypatch.setattr(reputation.settings, "REPUTATION_FEED_URL", "https://feed.example.com", raising=False)
        monkeypatch.setattr(reputation.settings, "REPUTATION_SALT", "", raising=False)
        result = await contribute_to_feed("spam text", -100111)
        assert result is False

    async def test_no_outbound_request_when_feed_url_empty(self, monkeypatch):
        monkeypatch.setattr(reputation.settings, "REPUTATION_FEED_URL", "", raising=False)
        monkeypatch.setattr(reputation.settings, "REPUTATION_SALT", "key", raising=False)

        requests_made = []

        class _FakeClient:
            def __init__(self, *a, **kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                pass

            async def post(self, *args, **kwargs):
                requests_made.append((args, kwargs))
                class _Resp:
                    status_code = 200
                return _Resp()

        import httpx
        monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)

        result = await contribute_to_feed("spam text", -100111)
        assert result is False
        assert requests_made == []

    async def test_posts_salted_fingerprint_and_pseudonym_when_configured(self, monkeypatch):
        monkeypatch.setattr(reputation.settings, "REPUTATION_FEED_URL", "https://feed.example.com", raising=False)
        monkeypatch.setattr(reputation.settings, "REPUTATION_SALT", "test-salt", raising=False)
        monkeypatch.setattr(reputation.settings, "REPUTATION_FEED_TOKEN", "abc123", raising=False)

        received = {}

        class _FakeResp:
            status_code = 202

        class _FakeClient:
            def __init__(self, *a, **kw):
                pass
            async def __aenter__(self):
                return self
            async def __aexit__(self, *a):
                pass
            async def post(self, url, json=None, headers=None):
                received["url"] = url
                received["json"] = json
                received["headers"] = headers
                return _FakeResp()

        import httpx
        monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)

        result = await contribute_to_feed("grab it at spam.ru", -100111)
        assert result is True
        assert received["url"] == "https://feed.example.com"

        # Payload must contain a salted fingerprint — not the raw hash.
        expected_fp = salted_fingerprint("grab it at spam.ru", "test-salt")
        assert received["json"]["fingerprint"] == expected_fp
        assert received["json"]["fingerprint"] != fingerprint("grab it at spam.ru")

        # Payload must contain a pseudonymised chat ID — not the raw one.
        expected_token = pseudonymize_chat_id(-100111, "test-salt")
        assert received["json"]["group_token"] == expected_token
        assert "100111" not in str(received["json"])

        # Bearer token in Authorization header.
        assert received["headers"]["Authorization"] == "Bearer abc123"

    async def test_network_error_does_not_raise(self, monkeypatch):
        monkeypatch.setattr(reputation.settings, "REPUTATION_FEED_URL", "https://feed.example.com", raising=False)
        monkeypatch.setattr(reputation.settings, "REPUTATION_SALT", "test-salt", raising=False)

        class _FakeClient:
            def __init__(self, *a, **kw):
                pass
            async def __aenter__(self):
                return self
            async def __aexit__(self, *a):
                pass
            async def post(self, *args, **kwargs):
                raise ConnectionError("feed unreachable")

        import httpx
        monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)

        result = await contribute_to_feed("spam text", -100111)
        assert result is False

    async def test_non_2xx_response_returns_false(self, monkeypatch):
        monkeypatch.setattr(reputation.settings, "REPUTATION_FEED_URL", "https://feed.example.com", raising=False)
        monkeypatch.setattr(reputation.settings, "REPUTATION_SALT", "test-salt", raising=False)

        class _FakeResp:
            status_code = 500

        class _FakeClient:
            def __init__(self, *a, **kw):
                pass
            async def __aenter__(self):
                return self
            async def __aexit__(self, *a):
                pass
            async def post(self, *args, **kwargs):
                return _FakeResp()

        import httpx
        monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)

        result = await contribute_to_feed("spam text", -100111)
        assert result is False


class TestRecordSpamFeedIntegration:
    async def test_record_spam_does_not_call_feed_when_unconfigured(self, monkeypatch):
        monkeypatch.setattr(reputation.settings, "REPUTATION_FEED_URL", "", raising=False)
        monkeypatch.setattr(reputation.settings, "REPUTATION_SALT", "key", raising=False)

        calls = []
        monkeypatch.setattr(reputation, "contribute_to_feed", lambda *a, **kw: calls.append(a))

        await record_spam(-100111, "spam text", now=1000.0)
        assert calls == []

    async def test_record_spam_calls_feed_when_configured(self, monkeypatch):
        monkeypatch.setattr(reputation.settings, "REPUTATION_FEED_URL", "https://feed.example.com", raising=False)
        monkeypatch.setattr(reputation.settings, "REPUTATION_SALT", "test-salt", raising=False)

        class _FakeResp:
            status_code = 202

        class _FakeClient:
            def __init__(self, *a, **kw):
                pass
            async def __aenter__(self):
                return self
            async def __aexit__(self, *a):
                pass
            async def post(self, *args, **kwargs):
                return _FakeResp()

        import httpx
        monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)

        await record_spam(-100111, "spam text", now=1000.0)
        fp = fingerprint("spam text")
        groups = await reputation._store.groups_for(fp, -100222, now=1001.0, ttl_seconds=86400)
        assert groups == [-100111]
