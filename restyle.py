"""One-shot restyle: remove /start, professionalize all bot messages (run once)."""
import re
import pathlib


def rep(path, old, new, count=None):
    p = pathlib.Path(path)
    s = p.read_text()
    n = s.count(old)
    if n == 0:
        print(f"MISS: {path}: {old[:55]!r}")
        return
    if count is not None and n != count:
        print(f"COUNT? {path}: {n} != {count}: {old[:45]!r}")
    p.write_text(s.replace(old, new))


ROOT = "app/bot"

# 1. Remove /start registration
rep(f"{ROOT}/application.py",
    'from app.bot.handlers.commands import (\n    start_command,\n',
    'from app.bot.handlers.commands import (\n')
rep(f"{ROOT}/application.py",
    '    app.add_handler(CommandHandler("start", start_command))\n', '')
rep(f"{ROOT}/handlers/__init__.py",
    'from app.bot.handlers.commands import (\n    start_command,\n',
    'from app.bot.handlers.commands import (\n')
rep(f"{ROOT}/handlers/__init__.py", '    "start_command",\n', '')

# 2. Remove start_command function
p = pathlib.Path(f"{ROOT}/handlers/commands.py")
s = p.read_text()
m = re.search(r"\nasync def start_command.*?(?=\nasync def help_command)", s, re.S)
if m:
    p.write_text(s[: m.start()] + s[m.end():])
    print("start_command removed")
else:
    print("WARN: start_command not found")
print("PART1 DONE")

# 3. Rebuild /help text
C = f"{ROOT}/handlers/commands.py"
HELP_OLD_START = '        f"\U0001F6E1 <b>{settings.BOT_NAME}'
new_help = r'''        f"<b>{settings.BOT_NAME} — Commands</b>\n\n"

        "<b>Moderation</b> <i>(admins only)</i>\n"
        "/ban [reply|@user] [reason] — Ban a member\n"
        "/unban [reply|@user] — Remove a ban\n"
        "/kick [reply|@user] [reason] — Remove without ban\n"
        "/mute [reply|@user] [time] — Mute a member\n"
        "/unmute [reply|@user] — Remove a mute\n"
        "/warn [reply|@user] [reason] — Issue a warning\n"
        "/warnings [reply|@user] — View warnings\n"
        "/resetwarns [reply|@user] — Clear warnings\n"
        "/purge — Delete from the replied-to message onward\n"
        "/pin — Pin the replied-to message\n"
        "/unpin — Unpin the pinned message\n\n"

        "<b>Group</b> <i>(admins only)</i>\n"
        "/rules — Show the group rules\n"
        "/setrules [text] — Set the rules\n"
        "/welcome — Welcome message status\n"
        "/setwelcome on|off — Toggle welcome messages\n"
        "/goodbye — Goodbye message status\n"
        "/setgoodbye on|off — Toggle goodbye messages\n"
        "/settings — Group settings overview\n"
        "/setwarnlimit N — Warnings before action (1-20)\n\n"

        "<b>Filters</b> <i>(admins only)</i>\n"
        "/filter [keyword] [response] — Add an auto-reply filter\n"
        "/filters — List active filters\n"
        "/stop [keyword] — Remove a filter\n\n"

        "<b>Information</b>\n"
        "/id — Show chat, user and message IDs\n"
        "/info [reply|@user|id] — User profile and role\n"
        "/admins — List group administrators\n\n"

        "<b>Admin</b> <i>(admins only)</i>\n"
        "/logs — Recent moderation log\n\n"

        "<i>Commands marked (admins only) require admin or owner role.</i>"'''

p2 = pathlib.Path(C)
s2 = p2.read_text()
a = s2.index(HELP_OLD_START)
b = s2.index("\n    )", a)
p2.write_text(s2[:a] + new_help + s2[b:])
print("help rebuilt")

# 4. commands.py message cleanup
rep(C, 'f"\U0001F194 <b>ID Information</b>\\n"', '"<b>ID Information</b>\\n"')
rep(C, 'f"<b>Your ID:</b> <code>{user.id}</code>"', 'f"Your ID: <code>{user.id}</code>"')
rep(C, 'f"<b>Chat ID:</b> <code>{chat.id}</code>"', 'f"Chat ID: <code>{chat.id}</code>"')
rep(C, 'f"<b>Chat type:</b> {chat.type}"', 'f"Chat type: {chat.type}"')
rep(C, 'f"<b>Replied message ID:</b> <code>{replied.message_id}</code>"',
        'f"Replied message ID: <code>{replied.message_id}</code>"')
rep(C, 'f"<b>Replied user ID:</b> <code>{replied_user.id}</code>"',
        'f"Replied user ID: <code>{replied_user.id}</code>"')
rep(C, 'f"<b>Replied username:</b> @{replied_user.username}"',
        'f"Replied username: @{replied_user.username}"')
rep(C, 'Could not find that user. Reply to their message or use @username.',
        'User not found. Reply to one of their messages, or provide their @username or numeric ID.')
rep(C, 'f"\U0001F464 <b>User Info</b>\\n"', '"<b>User Information</b>\\n"')
rep(C, 'f"<b>Name:</b> {mention}"', 'f"Name: {mention}"')
rep(C, 'f"<b>ID:</b> <code>{target_user.id}</code>"', 'f"ID: <code>{target_user.id}</code>"')
rep(C, 'f"<b>Username:</b> @{target_user.username}"', 'f"Username: @{target_user.username}"')
rep(C, "f\"<b>Bot:</b> {'Yes' if target_user.is_bot else 'No'}\"",
        "f\"Bot: {'Yes' if target_user.is_bot else 'No'}\"")
rep(C, 'f"<b>Role:</b> {role.title()}"', 'f"Role: {role.title()}"')
rep(C, 'Could not fetch admin list. Make sure I have the required permissions.',
        'Could not fetch the admin list. Make sure I have the required permissions.')

# 5. moderation.py
M = f"{ROOT}/handlers/moderation.py"
DENIED = '<b>Permission denied.</b>\\nAdmins only.'
rep(M, DENIED, '<b>Permission denied.</b>\\nThis command is restricted to administrators.')
rep(M, "I can't ban myself! \U0001F605", "I cannot ban myself.")
rep(M, "You can't ban someone with equal or higher rank.",
        "You cannot ban a member with an equal or higher rank.")
rep(M, "You can't kick someone with equal or higher rank.",
        "You cannot kick a member with an equal or higher rank.")
rep(M, "Ban failed: {e}. Make sure I'm admin with ban rights.",
        "Ban failed. Make sure I am an administrator with ban rights.\\n({e})")
rep(M, "Kick failed: {e}. Make sure I'm admin with ban rights.",
        "Kick failed. Make sure I am an administrator with ban rights.\\n({e})")
rep(M, "Mute failed: {e}. Make sure I'm admin with restrict rights.",
        "Mute failed. Make sure I am an administrator with restrict rights.\\n({e})")
rep(M, "Unmute failed: {e}", "Unmute failed. ({e})")
rep(M, "Unban failed: {e}", "Unban failed. ({e})")
rep(M, 'f"\U0001F528 <b>{_mention(target)}</b> has been <b>banned</b>."',
        'f"<b>{_mention(target)}</b> has been banned."')
rep(M, 'f"\u2705 <b>{_mention(target)}</b> has been <b>unbanned</b>."',
        'f"<b>{_mention(target)}</b> has been unbanned."')
rep(M, 'f"\U0001F462 <b>{_mention(target)}</b> has been <b>kicked</b>."',
        'f"<b>{_mention(target)}</b> has been kicked."')
rep(M, 'f"\U0001F507 <b>{_mention(target)}</b> has been <b>{label}</b>."',
        'f"<b>{_mention(target)}</b> has been <b>{label}</b>."')
rep(M, 'f"\U0001F50A <b>{_mention(target)}</b> has been <b>unmuted</b>."',
        'f"<b>{_mention(target)}</b> has been unmuted."')
rep(M, "I can't warn bots.", "Bots cannot be warned.")
rep(M, 'reply_text(f"\u274c {e}")', 'reply_text(str(e))', 2)
rep(M, 'f"\u26a0\ufe0f <b>{_mention(target)}</b> warned (<b>{total}/{limit}</b>)."',
        'f"<b>{_mention(target)}</b> was warned (<b>{total}/{limit}</b>)."')
rep(M, '"\\n\U0001F6AB Warn limit reached \u2014 <b>banned</b>."',
        '"\\nWarn limit reached \u2014 <b>banned</b>."')
rep(M, '"\\n\U0001F462 Warn limit reached \u2014 <b>kicked</b>."',
        '"\\nWarn limit reached \u2014 <b>kicked</b>."')
rep(M, '"\\n\U0001F507 Warn limit reached \u2014 <b>muted</b>."',
        '"\\nWarn limit reached \u2014 <b>muted</b>."')
rep(M, 'msg += f"\\n\u26a0\ufe0f Limit action failed: {html.escape(str(e))}"',
        'msg += f"\\nLimit action failed: {html.escape(str(e))}"')
rep(M, 'f"\u2728 <b>{_mention(target)}</b> has no warnings. Clean record!"',
        'f"{_mention(target)} has no warnings."')
rep(M, 'f"\u26a0\ufe0f <b>Warnings for {_mention(target)}</b> ({len(warns)}):\\n"',
        'f"<b>Warnings \u2014 {_mention(target)}</b> ({len(warns)})\\n"')
rep(M, 'f"\U0001F9F9 Cleared <b>{n}</b> warning(s) for {_mention(target)}."',
        'f"Cleared <b>{n}</b> warnings for {_mention(target)}."')
rep(M, 'f"\U0001F9F9 Purged {deleted} message(s)."', 'f"Purged {deleted} messages."')
rep(M, "Pin failed: {e}. I need pin rights.",
        "Pin failed. Make sure I am an administrator with pin rights.\\n({e})")
rep(M, 'reply_text("\U0001F4CC Pinned.")', 'reply_text("Message pinned.")')
rep(M, "Unpin failed: {e}", "Unpin failed. ({e})")
rep(M, 'reply_text("\U0001F4CC Unpinned.")', 'reply_text("Pinned message unpinned.")')
rep(M, 'reply_text("\U0001F4DC No audit entries yet.")', 'reply_text("No audit entries yet.")')
rep(M, 'lines = ["\U0001F4DC <b>Recent actions</b>\\n"]', 'lines = ["<b>Recent Actions</b>\\n"]')
rep(M, '\\n\U0001F4DD Reason: {html.escape(reason)}', '\\nReason: {html.escape(reason)}', 4)
print("PART4 DONE")

# 6. welcome.py
W = f"{ROOT}/handlers/welcome.py"
rep(W, 'Group not registered yet. Send /start first.',
        'Group is not registered yet. Please try again in a moment.', 7)
rep(W, DENIED, '<b>Permission denied.</b>\\nThis command is restricted to administrators.')
rep(W, '"ON \u2705" if s["welcome_enabled"] else "OFF \u274c"',
        '"<b>On</b>" if s["welcome_enabled"] else "<b>Off</b>"')
rep(W, 'f"\U0001F44B <b>Welcome messages:</b> {state}\\n"',
        'f"<b>Welcome messages:</b> {state}\\n"')
rep(W, "Welcome messages {'enabled \u2705' if enabled else 'disabled \u274c'}.",
        "Welcome messages {'enabled' if enabled else 'disabled'}.")
rep(W, '"ON \u2705" if s["goodbye_enabled"] else "OFF \u274c"',
        '"<b>On</b>" if s["goodbye_enabled"] else "<b>Off</b>"')
rep(W, 'f"\U0001F44B <b>Goodbye messages:</b> {state}\\n"',
        'f"<b>Goodbye messages:</b> {state}\\n"')
rep(W, "Goodbye messages {'enabled \u2705' if enabled else 'disabled \u274c'}.",
        "Goodbye messages {'enabled' if enabled else 'disabled'}.")
rep(W, '"\U0001F4CB No rules set yet. Admins: /setrules <text>"',
        '"No rules have been set. Administrators can add them with /setrules <text>."')
rep(W, '"\U0001F4CB Rules cleared."', '"Rules cleared."')
rep(W, '"\U0001F4CB Group rules updated \u2705."', '"Group rules updated."')
rep(W, 'tick = lambda b: "\u2705" if b else "\u274c"', 'tick = lambda b: "On" if b else "Off"')
rep(W, 'f"Rules: {\'set \u2705\' if s[\'rules\'] else \'not set \u274c\'}"',
        'f"Rules: {\'set\' if s[\'rules\'] else \'not set\'}"')
rep(W, 'f"\u26a0\ufe0f Warn limit set to {n}."', 'f"Warn limit set to <b>{n}</b>."')
rep(W, 'f"\u2699\ufe0f <b>Group Settings</b>\\n\\n"', 'f"<b>Group Settings</b>\\n\\n"')
rep(W, 'f"\u26a0\ufe0f Warn limit: <b>{s[\'warn_limit\']}</b> <i>(/setwarnlimit N)</i>\\n"',
        'f"Warn limit: <b>{s[\'warn_limit\']}</b> <i>(/setwarnlimit N)</i>\\n"')
rep(W, 'f"\U0001F44B Welcome: {tick(s[\'welcome_enabled\'])}\\n"',
        'f"Welcome: {tick(s[\'welcome_enabled\'])}\\n"')
rep(W, 'f"\U0001F44B Goodbye: {tick(s[\'goodbye_enabled\'])}\\n"',
        'f"Goodbye: {tick(s[\'goodbye_enabled\'])}\\n"')
rep(W, 'f"\U0001F30A Anti-flood: {tick(s[\'anti_flood_enabled\'])}\\n"',
        'f"Anti-flood: {tick(s[\'anti_flood_enabled\'])}\\n"')
rep(W, 'f"\U0001F6E1 Anti-spam: {tick(s[\'anti_spam_enabled\'])}\\n"',
        'f"Anti-spam: {tick(s[\'anti_spam_enabled\'])}\\n"')
rep(W, 'f"\U0001F4DC Logging: {tick(s[\'log_enabled\'])}\\n"',
        'f"Logging: {tick(s[\'log_enabled\'])}\\n"')

# 7. filters.py
F = f"{ROOT}/handlers/filters.py"
rep(F, DENIED, '<b>Permission denied.</b>\\nThis command is restricted to administrators.')
rep(F, 'Group not registered yet. Send /start first.',
        'Group is not registered yet. Please try again in a moment.')
rep(F, 'Keyword too long or response too long.',
        'Keyword or response exceeds the allowed length (keyword 200, response 3000 characters).')
rep(F, 'f"\u2705 Filter <code>{html.escape(keyword)}</code> saved."',
        'f"Filter <code>{html.escape(keyword)}</code> saved."')
rep(F, 'lines = ["\U0001F50D <b>Active filters</b>\\n"]', 'lines = ["<b>Active Filters</b>\\n"]')
rep(F, "f\"No filter named '{keyword}'.\"",
        'f"No filter named <code>{html.escape(keyword)}</code>.",')

# 8. lifecycle.py + errors.py
L = f"{ROOT}/handlers/lifecycle.py"
rep(L, '''f"\U0001F44B <b>{settings.BOT_NAME} is online.</b>\\n\\n"
                    "I'm your group's guardian. "
                    "Every action I take is rule-based, auditable, and logged.\\n\\n"
                    "\U0001F4CB Send /help to see all available commands.\\n"
                    "\U0001F511 Only group admins can use moderation commands."''',
    '''f"<b>{settings.BOT_NAME} is now active in this group.</b>\\n\\n"
                    "I will handle moderation, filtering and member management.\\n"
                    "All actions are logged and can be reviewed with /logs.\\n\\n"
                    "Send /help to see the full command list."''')
rep(L, '''f"\u2705 <b>{settings.BOT_NAME} has been granted admin privileges.</b>\\n\\n"
                    "I can now perform all moderation actions (ban, mute, kick, etc.).\\n"
                    "Send /help for the full command list."''',
    '''f"<b>{settings.BOT_NAME} has been granted admin privileges.</b>\\n\\n"
                    "All moderation actions are now available.\\n"
                    "Send /help for the full command list."''')
E = f"{ROOT}/handlers/errors.py"
rep(E, '''f"\u274c <b>An error occurred</b>\\n\\n"
                f"<code>{error_type}: {safe_error}</code>\\n\\n"
                f"<i>This has been logged. If the issue persists, contact the bot administrator.</i>"''',
    '''f"<b>An error occurred while processing that command.</b>\\n\\n"
                f"<code>{error_type}: {safe_error}</code>\\n\\n"
                f"<i>The incident has been logged. If it persists, contact the bot administrator.</i>"''')

# 9. ensure_group.py
G = f"{ROOT}/helpers/ensure_group.py"
rep(G, '"\u23f3 Slow down \u2014 you\'re sending commands too fast."',
        '"You are sending commands too quickly. Please wait a moment."')
rep(G, '"\u26a0\ufe0f Group registration failed. Try removing and re-adding me."',
        '"Group registration failed. Please try again shortly."')
print("ALL DONE")
