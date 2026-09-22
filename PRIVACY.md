<!--
  Aegis — privacy policy.

  This file is written for the *operator* of an Aegis instance (the person who
  runs the bot and therefore holds the database). If you self-host, replace
  every [BRACKETED] placeholder, delete the names that are not yours, and have
  the result reviewed by a lawyer for your jurisdiction — this is a precise
  technical description of the software's behaviour, not legal advice.

  The factual claims below are traced to the code on purpose. If you change
  what the bot stores or where it sends data, change this file in the same
  commit: a policy that lies about the software is worse than none.
-->

# Privacy Policy

**Aegis — Telegram group management bot**

Last updated: **22 September 2026** · Applies to the bot operated as **@official_aegis_bot** and to the Aegis software in this repository.

Aegis is self-hosted software. There is no central Aegis service, no vendor account, and no data flowing to the people who wrote the code: whoever runs the bot — the "operator" — holds the database. This policy describes exactly what the software stores, what it sends, what it deliberately does not do, and how to get data removed.

## 1. Who is responsible

| Role | Who |
|---|---|
| **Data controller** — decides why and how personal data is processed | The operator of the instance you use: **Sehaj Varma**, contact **mr.sehaj.official@gmail.com** |
| **Software authors** — publish the code only | The Aegis contributors. They receive **no data** from any instance. |

If you run Aegis yourself, *you* are the controller and this document is your template.

## 2. What is deliberately not collected

- **No message archive.** Message text is examined as it arrives and then discarded; no database table stores member messages.
- **No media, files, contact lists, phone numbers or payment data.**
- **No analytics, trackers, advertising IDs or tracking pixels.**
- **No selling or sharing of personal data** with third parties for their own purposes.
- **No reading of private chats.** The bot processes messages in groups it has been added to, and in Telegram Business chats only after that account's owner explicitly connected it.

## 3. What is stored

Everything below lives in the operator's own database (SQLite or PostgreSQL) and exists to run protections a group's admins switched on.

| Data | Why it exists |
|---|---|
| Group ID, title, username, type | Identifying which group a setting belongs to |
| Member user ID, username, first/last name, role, join date | Warn/mute/ban the right account, and show admins who is who |
| Warnings — user ID, issuing admin, reason, time | Warning limits and `/warnings` |
| Audit log — action, actor ID, target ID, reason, metadata, time | `/logs`: accountability for every moderation action |
| Group settings — toggles, thresholds, rules, welcome/goodbye texts | Your configuration |
| Blacklisted words, notes, auto-reply filters, rules text | Written by **admins**, not by ordinary members |
| Telegram Business connection — connection ID, owner user ID, chat ID, toggles, greeting/away texts, keyword rules | Auto-replies on behalf of the account owner who enabled them |

Admin-authored text can incidentally mention people (a name inside a note, for example). Admins control that content and can delete it themselves.

## 4. Short-lived processing (memory only)

| Data | Lifetime | Notes |
|---|---|---|
| Anti-flood counters (user ID, timestamps) | sliding window, seconds | in memory, or the operator's Redis |
| Join-captcha state (user ID, message ID) | until solved, or the timeout (120 s default) | never written to the database |
| Business-reply debounce and cooldowns | 2 s / 15 min | prevents reply loops |
| Spam fingerprints (below) | 24 h | in memory, or the operator's Redis |
| Dashboard admin check (group ID, user ID, answer) | 5 min | avoids hammering the Telegram API |

### Spam fingerprints

When a group has anti-spam enabled and a message is judged spam, the bot records a **SHA-256 hash of the normalised message text** together with the group's chat ID, for 24 hours. The message text itself is never stored, and the hash is one-way. If the operator points several instances at one Redis, those hashes and chat IDs are shared between **those instances only** — that is what lets a campaign caught in one group be pre-flagged in another. Turning anti-spam off withdraws the group's contributions.

**Optional shared reputation feed.** When the operator sets `REPUTATION_FEED_URL`, the bot also reports each confirmed spam verdict to that endpoint. The feed receives **only** a salted fingerprint (`HMAC-SHA256(key=REPUTATION_SALT, msg=SHA-256-of-normalised-text)`) and a pseudonymised group token (`HMAC-SHA256(key=REPUTATION_SALT, msg=chat-ID)`). Neither the message text nor the raw chat ID is ever sent. `REPUTATION_SALT` must be set for the feed to be used — if it is empty the bot logs a warning and skips the feed. Reporting is fire-and-forget: any network or HTTP error is logged and never blocks local spam protection. The operator is responsible for choosing the feed operator and reviewing its own policy.

There is no central Aegis fingerprint server operated by the project authors.

## 5. The only outbound connections the software makes

1. **Telegram Bot API** (`api.telegram.org`) — required for the bot to function at all.
2. **GitHub releases API** (`api.github.com`) — an optional, anonymous version check while `UPDATE_CHECK_ENABLED` is true (the default). It sends no instance data; set `UPDATE_CHECK_ENABLED=false` to switch it off.
3. **The operator's own Redis** — only when the operator configured `REDIS_URL`, for shared flood and spam-fingerprint state.
4. **The operator's chosen reputation feed** — only when the operator configured `REPUTATION_FEED_URL`. The bot posts a salted fingerprint and a pseudonymised group token (see §4); no message content or raw chat IDs are sent. Set `REPUTATION_FEED_URL` to empty (the default) to disable it.

Nothing else: no analytics, no crash reporting, no third-party APIs, no Aegis-operated server.

## 6. Logs

The bot logs to standard output; verbosity is set by `LOG_LEVEL`. Log records can contain Telegram IDs, moderation reasons and — for the Telegram Business auto-reply path — the first 50 characters of the message being evaluated. Logs remain on the operator's host, and how long they are kept is decided by the operator's own log configuration (journald, Docker, hosting panel, database backups). Setting `LOG_LEVEL=WARNING` keeps markedly less.

## 7. The website and the dashboard

The project's landing page and the dashboard Mini App are static pages: they set **no cookies** and run **no analytics**. The pages load their fonts from Google Fonts, which means your IP address is visible to Google when a page loads. The dashboard talks to its API only to read or change group settings, and requests are authenticated with Telegram's signed `initData` — the payload is validated on the server and not stored.

## 8. Legal bases (if the GDPR or a similar law applies)

- **Legitimate interests** — protecting a community from spam, floods and abuse, and keeping an audit trail of moderation actions.
- **Contract** — providing the features an admin enabled for their group.
- **Legal obligation** — where a lawful request requires an action to be recorded or disclosed.

Telegram processes account data under [Telegram's own privacy policy](https://telegram.org/privacy); Aegis only sees what Telegram sends to a bot.

## 9. Retention and deletion

- Live data stays while the group uses the bot. **Removing the bot from a group does not delete that group's stored data** — the software keeps it on purpose so a re-added bot retains its settings. Deletion is a request to the operator.
- Self-service deletions: `/resetwarns` clears a user's warnings, `/clear` removes a note, `/stop` removes an auto-reply filter, `/rmblacklist` removes a banned word, `/unban` removes a ban.
- The short-lived state in section 4 expires by itself.
- The operator deletes remaining records on request, and can destroy the entire database or instance at any time.

## 10. Your rights

Depending on where you live, you may have the right to access, correct, delete, restrict or port your data, and to object to processing. Contact the operator at **mr.sehaj.official@gmail.com**. Group admins can already clear much of the data themselves with the commands in section 9.

## 11. Security

- The bot token lives in `.env`, created with `600` permissions by `python -m app.setup`, and is never written to logs in full.
- Webhook mode signs every request with a secret token; Mini App requests are verified with Telegram's HMAC scheme plus an `auth_date` freshness window and a live admin check through the Bot API.
- The database and Redis belong to the operator; controlling access to them is the operator's responsibility.
- No system is perfectly secure. Report a suspected issue to **mr.sehaj.official@gmail.com** or through the repository's issue tracker.

## 12. Children

Aegis is not directed at children and collects no age data. Telegram requires users to be at least 13 years old (older where local law demands), which sets the floor for any group the bot serves.

## 13. International transfers

Data stays with the operator's hosting provider and Telegram's global infrastructure; the optional version check contacts GitHub. Where data crosses borders, choosing appropriate safeguards is the operator's responsibility.

## 14. Changes to this policy

Material changes update the date at the top of this document and appear in the repository history, so every version stays reviewable.

## 15. Contact

**Sehaj Varma** — **mr.sehaj.official@gmail.com**

