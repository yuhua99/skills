---
name: discord
description: Read-only Discord access through a local message cache. Use when the user asks what happened in a Discord server or channel, wants a Discord discussion summarized, or wants to find a Discord message, topic, or person's messages.
---

Use the bundled script `scripts/discord.py`, resolved relative to this `SKILL.md` (not the caller's cwd). Run it with `python3`.

## Ground rules

- **Read-only.** The script syncs and reads; it cannot post, react, or edit.
- **Sync before read.** `search`, `recent`, and `stats` read only the local cache. A channel that was never synced does not exist for them; `dc *` commands hit the Discord API.
- **IDs over names.** Pass channel and guild IDs once you have them. Names must match exactly (case-insensitive); a name shared across guilds is rejected as ambiguous.
- **Light traffic.** It runs on the user's own Discord *user token*; heavy automation risks account restrictions. Scope every sync to the channels the task needs.

## Output

Every command prints one JSON object: `{"ok": true, "data": ...}` or `{"ok": false, "error": {"code", "message"}}`.

## Workflow

1. **Check auth**: `status`. Done when `ok` is true. On `not_authenticated` / `invalid_token`, ask the user to set `DISCORD_TOKEN` in the environment this agent runs in (usually: export it, then restart the agent); the token stays out of the chat.
2. **Locate the channel**: `dc guilds` → `dc channels <guild>`. Done when you hold the channel ID.
3. **Sync**: `dc sync <channel_id>`. For a first sync, add `--hours N` matching the period the user cares about. Done when `has_more` is false; otherwise run the same sync again.
4. **Read**:
   - Catch-up or summary → `recent -c <channel_id> --hours N -n 200` (oldest first).
   - Topic lookup → `search "<keyword>" -c <channel_id>`, narrowing with `--sender` / `--hours`.
   - Channel never synced and only a lookup is needed → `dc search <guild> "<keyword>"` (Discord's own search, no sync).
   Done when every claim in your answer traces to a returned message (sender + timestamp).

## Commands

```bash
python3 scripts/discord.py status
python3 scripts/discord.py dc guilds
python3 scripts/discord.py dc channels <guild>
python3 scripts/discord.py dc sync <channel_id> [--hours N]
python3 scripts/discord.py dc search <guild> "<keyword>" [-c <channel_id>] [-n N]
python3 scripts/discord.py search "<keyword>" [-c CHANNEL] [-g GUILD] [--sender NAME] [--hours N] [-n N]
python3 scripts/discord.py recent [-c CHANNEL] [-g GUILD] [--hours N] [-n N]
python3 scripts/discord.py stats
```

- `stats` shows which channels are cached and how fresh each one is.
- `dc sync` continues from the newest cached message. With `--hours`, it starts at the cutoff instead and the gap before it is never backfilled.

## Errors

| `error.code` | Action |
|---|---|
| `not_authenticated`, `invalid_token` | Ask the user to set `DISCORD_TOKEN` |
| `empty_database` | Run step 3 first |
| `channel_resolution_error` | Not synced yet, or ambiguous: use the channel ID or add `-g` |
| `guild_resolution_error` | Use the guild ID from `dc guilds` |
| `forbidden`, `not_found` | The account cannot see that guild/channel; tell the user |
| other codes | Retry once, then report the message to the user |
