<!--
  Aegis — terms of service.

  Written for the *operator* of an Aegis instance. Self-hosting? Replace every
  [BRACKETED] placeholder and have the result reviewed by a lawyer for your
  jurisdiction — this document describes the software's behaviour accurately,
  but it is a starting point, not legal advice.

  Keep the factual claims in step with the code (the licence, the commands, the
  retention rules). Contradicting your own privacy policy is the one mistake
  that actually creates liability.
-->

# Terms of Service

**Aegis — Telegram group management bot**

Last updated: **22 September 2026** · Instance operated by **Sehaj Varma**

These terms cover your use of the Aegis bot in a Telegram group or private chat ("the Service"). By adding the bot to a group, or by taking part in a group where it is active, you agree to them. If you do not agree, remove the bot or ask a group admin to remove it.

## 1. The software and the instance are different things

- **The software** is free and open source under the **GNU Affero General Public License v3.0** ([LICENSE](https://github.com/mrsehajofficial/aegis/blob/main/LICENSE)). You may run, study and modify it under that licence. If you run a modified version as a network service, the AGPL requires you to offer its source to the people using that service.
- **The instance** you are using is operated by **Sehaj Varma**, who decides whether it runs, which features are enabled, and who may use it. The authors of the software do not operate this instance and cannot access its data.

## 2. What the Service does

Aegis is a deterministic group-management bot. Depending on the settings an admin has chosen, it can delete messages, warn, mute, kick or ban members, lock content types, run a join captcha, publish rules and welcome/goodbye messages, keep an audit log of moderation actions, and — for Telegram Business accounts that connected it — send automatic replies on that account's behalf.

Every automatic action follows from the group's configuration and the bot's heuristics, not from a decision taken personally by the operator. Admins can reverse most actions (`/unban`, `/unmute`, `/resetwarns`, `/unpin`).

## 3. Acceptable use

You must not:

- use the Service for anything unlawful, or to harass, threaten, defraud or harm anyone;
- use it to spam, flood, scrape or send bulk unsolicited messages;
- attempt to bypass its rate limits, locks, captcha or authentication, or probe it for vulnerabilities without written permission;
- use it to collect, compile or publish other people's personal data;
- misrepresent a modified version as the official instance, or run one in a way that violates the AGPL.

You must also follow [Telegram's Terms of Service](https://telegram.org/tos) and the rules of the group you are in.

## 4. If you are a group admin

By adding the bot to a group you confirm that:

- you are authorised to add it, and you will make sure members know an automated moderation bot is active and where to read the privacy policy (for example in the group description or the rules);
- the settings you choose — blacklists, filters, notes, rules, welcome texts, captcha — are lawful and appropriate for your community;
- you are responsible for the content admins enter, including any personal data that appears in notes, filter replies, blacklist entries or moderation reasons.

## 5. Data

How data is handled is described in the [Privacy Policy](https://github.com/mrsehajofficial/aegis/blob/main/PRIVACY.md). In short: the operator holds the database, there is no central Aegis server, message content is not archived, and **removing the bot does not delete the group's stored data** — deletion is a request to the operator.

## 6. Availability

The Service is provided on a best-effort basis, with no uptime, latency or feature guarantee. The operator may restart it, change its behaviour, turn protections on or off, or stop running it entirely at any time, with or without notice. Telegram outages, API changes and rate limits are outside anyone's control.

## 7. No warranty — moderation decisions can be wrong

Aegis uses deterministic heuristics. They are predictable, but they are still heuristics: a legitimate message can be removed, and unwanted messages can slip through. The Service is provided "as is" and "as available", without warranties of any kind, express or implied — including fitness for a particular purpose or uninterrupted availability. Admins should review `/logs` and reverse mistakes; the operator gives no warranty that every unwanted message is caught or that no legitimate message is ever affected.

## 8. Limitation of liability

To the maximum extent permitted by law, the operator is not liable for indirect, incidental, special or consequential damages, loss of data, loss of goodwill or reputation, or for the consequences of moderation actions — including missed spam, wrongful bans, mutes, kicks or deletions. Where liability cannot lawfully be excluded, it is limited to **the amount you paid to use the Service — which is nothing**.

Nothing in these terms limits rights you have under mandatory consumer law in your country.

## 9. Suspension and termination

The operator may refuse or revoke access for a user, group or instance at any time — for example after abuse, a security incident, or a legal requirement — and may shut the Service down altogether. You can stop using the Service at any time by removing the bot from your group. Stored data is handled as described in the Privacy Policy.

## 10. Intellectual property

The software is licensed under the AGPL-3.0; the "Aegis" name and its artwork belong to their respective owner. Content you send stays yours — you grant the operator only the limited licence needed to operate the Service, such as checking a message for spam or showing it in the moderation log.

## 11. Changes to these terms

The operator may update these terms. The date at the top changes with each update, and the repository keeps the full history. Continuing to use the Service after a change means you accept the updated terms.

## 12. Governing law

These terms are governed by the laws of **India**, without depriving you of the protection of mandatory rules of the country where you live. Disputes are handled by the courts of **India**, unless the law gives you a different forum.

## 13. Contact

**Sehaj Varma** — **mr.sehaj.official@gmail.com** — or open an issue at [github.com/mrsehajofficial/aegis/issues](https://github.com/mrsehajofficial/aegis/issues).

