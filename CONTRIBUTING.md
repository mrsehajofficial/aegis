# Contributing to Aegis

Thanks for helping. Aegis is a self-hosted Telegram group-management bot, maintained
by one person, so contributions are genuinely load-bearing — a good bug report or a
focused patch saves real time.

This guide is short on purpose. Read it once and you can ship a change.

---

## Running it locally

```bash
git clone https://github.com/mrsehajofficial/aegis.git
cd aegis
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

python -m app.setup     # writes .env and asks for your bot token
python -m app.main      # starts the bot (SQLite, no servers needed)
```

No Docker, Redis or PostgreSQL is required to develop. Defaults are: **long polling**
(no public URL), **SQLite** (`./aegis.db`), **in-memory** flood + reputation stores.

To try it against a real group, create a throwaway bot with
[@BotFather](https://t.me/BotFather) and promote it to admin in a test group with
*Delete messages* and *Ban users*. **Never test against a group you care about** —
the captcha and anti-flood paths really do kick and mute people.

---

## Tests

Every change needs a test. The suite is fast (a couple of seconds) and needs no
network, no Telegram token and no database server.

```bash
pytest -q                          # everything
pytest tests/test_detector.py -q   # one module
pytest -q -k "captcha"             # one behaviour
```

Conventions worth matching:

- Tests are **synchronous where possible**; the suite uses `asyncio_mode = "auto"`,
  so an `async def test_...` just works.
- The bot's collaborators are replaced with small hand-written fakes rather than
  `unittest.mock` where the interaction matters — see `tests/test_captcha.py` for
  the established style (`FakeBot`, `FakeContext`, ...).
- Time-dependent code takes an injectable clock or an explicit `now` argument.
  Never call `time.time()`/`time.monotonic()` directly in new logic — see the
  `clock` fixture in `tests/conftest.py`.
- Anything touching spam detection must stay **deterministic**. No random
  thresholds, no model downloads.

Please don't add tests that call the network or the real Telegram API.

---

## What to work on

Good first issues are labelled
[`good first issue`](https://github.com/mrsehajofficial/aegis/labels/good%20first%20issue).
Before starting anything larger than a bug fix, open an issue first — it's much
cheaper to disagree about a design in an issue than in a 500-line pull request.

Areas where help is especially welcome:

- **Spam evasion bypasses** — a message that gets through the detector. A failing
  test case in `tests/` is the perfect bug report.
- **Docs** — the README's install paths, troubleshooting, translations.
- **Deployment guides** — Caddy/Nginx webhook setups, systemd units, ARM/Raspberry Pi.

---

## Code style

Match the surrounding code; it is consistent and intentional.

- Python ≥ 3.11, full type hints on public functions, `async def` throughout.
- **Comments explain *why*, not *what*.** The existing code documents the reasoning
  behind a decision (and the bug it prevents) instead of restating the line below
  it. A comment that says `# increment counter` adds nothing.
- Never `.strip()` a value into silence where a user needs to know it failed —
  log the reason and degrade gracefully. See the flood/reputation store factories:
  a Redis outage falls back to memory instead of disabling protection.
- User-facing text is HTML (`reply_html`), and all interpolated values are escaped
  with `html.escape()` or wrapped in `html.escape()`-safe formatting. Telegram
  rejects malformed HTML, so an unescaped `<` breaks the whole message.
- Emoji in source are written as `"\U0001F6E1\uFE0F"` escapes so no editor or
  encoding round-trip can corrupt them.
- Keep everything behind the per-group toggle it belongs to. A feature that acts
  the moment the bot is added is a liability; opt-in is the house rule.

---

## Pull requests

1. Branch from `main`: `git checkout -b fix/flood-window-off-by-one`.
2. Keep the diff focused — one behaviour per PR. Unrelated formatting churn makes
   review harder and is the usual reason a PR sits unreviewed.
3. Run `pytest -q` and confirm it's green before pushing.
4. Describe **what breaks without this change**. "Fixes #123" plus a sentence on the
   user-visible symptom is enough. If you changed behaviour, say what an admin will
   notice.
5. New commands must be registered in `app/bot/application.py` (`_COMMANDS`, plus a
   handler) **and** documented in `build_help_text()` in `app/bot/handlers/commands.py`.
   Tests assert the two stay in sync — `tests/test_command_menu.py`.

Never commit a real `BOT_TOKEN`. `.env` is gitignored; `.env.example` is the place
to document new settings, with safe defaults and a comment.

---

## Licence

Aegis is **AGPL-3.0** (see [LICENSE](LICENSE)). By contributing you agree your work
is licensed under the same terms. If you run a modified Aegis as a network service,
the AGPL requires you to publish your changes — please honour that, it's what keeps
this project from being out-competed by a closed fork of itself.