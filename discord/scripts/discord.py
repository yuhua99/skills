#!/usr/bin/env python3
"""Read-only Discord CLI for agents: sync channels into SQLite, then search and read them.

Every command prints one JSON envelope on stdout:
  success: {"ok": true, "schema_version": "1", "data": ...}
  failure: {"ok": false, "schema_version": "1", "error": {"code": ..., "message": ...}}, exit 1
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, NoReturn
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SCHEMA_VERSION = "1"
API_BASE = "https://discord.com/api/v10"
DISCORD_EPOCH_MS = 1420070400000
TEXT_CHANNEL_TYPES = {0, 5}  # text, announcement; forums hold no messages of their own
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
    ),
    "sec-ch-ua": '"Chromium";v="133", "Not(A:Brand";v="99", "Google Chrome";v="133"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    platform      TEXT    NOT NULL DEFAULT 'discord',
    guild_id      TEXT,
    guild_name    TEXT,
    channel_id    TEXT    NOT NULL,
    channel_name  TEXT,
    msg_id        TEXT    NOT NULL,
    sender_id     TEXT,
    sender_name   TEXT,
    content       TEXT,
    timestamp     TEXT    NOT NULL,
    raw_json      TEXT,
    UNIQUE(platform, channel_id, msg_id)
);
CREATE INDEX IF NOT EXISTS idx_messages_channel_ts ON messages(channel_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_messages_content ON messages(content);
CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender_name);
CREATE INDEX IF NOT EXISTS idx_messages_guild ON messages(guild_id);
"""
_MESSAGE_COLUMNS = (
    "guild_id, guild_name, channel_id, channel_name, msg_id, "
    "sender_id, sender_name, content, timestamp"
)


class CliError(Exception):
    def __init__(self, code: str, message: str, details: Any | None = None):
        super().__init__(message)
        self.code = code
        self.details = details


# --- output -----------------------------------------------------------------


def _print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def emit(data: Any) -> None:
    _print({"ok": True, "schema_version": SCHEMA_VERSION, "data": data})


def fail(err: CliError) -> NoReturn:
    error: dict[str, Any] = {"code": err.code, "message": str(err)}
    if err.details is not None:
        error["details"] = err.details
    _print({"ok": False, "schema_version": SCHEMA_VERSION, "error": error})
    sys.exit(1)


# --- Discord API --------------------------------------------------------------


def _token() -> str:
    token = os.environ.get("DISCORD_TOKEN", "")
    if not token:
        raise CliError(
            "not_authenticated",
            "DISCORD_TOKEN not set. Get it from browser DevTools → Network tab → "
            "any Discord request → Authorization header.",
        )
    return token


def _wait_if_bucket_empty(headers: Any) -> None:
    if headers.get("X-RateLimit-Remaining") == "0":
        reset_after = float(headers.get("X-RateLimit-Reset-After", "1.0"))
        time.sleep(reset_after + random.uniform(0.2, 1.0))


def api_get(path: str, **params: Any) -> Any:
    """GET a Discord API path, retrying on 429 and mapping failures to CliError."""
    url = API_BASE + path + (f"?{urlencode(params)}" if params else "")
    request = Request(url, headers={**BROWSER_HEADERS, "Authorization": _token()})
    for _ in range(3):
        try:
            with urlopen(request, timeout=30) as response:
                data = json.load(response)
                _wait_if_bucket_empty(response.headers)
                return data
        except HTTPError as e:
            if e.code == 429:
                try:
                    retry_after = float(json.load(e).get("retry_after", 1.0))
                except ValueError:
                    retry_after = 1.0
                time.sleep(retry_after + random.uniform(0.5, 2.0))
                continue
            code = {401: "invalid_token", 403: "forbidden", 404: "not_found"}.get(e.code, "http_error")
            raise CliError(code, f"HTTP {e.code} for {path}", {"status_code": e.code}) from e
        except OSError as e:  # URLError, timeouts, resets, TLS errors
            raise CliError("connection_error", str(getattr(e, "reason", e))) from e
    raise CliError("rate_limited", f"Rate limited after 3 retries: {path}")


def list_guilds() -> list[dict]:
    return [
        {"id": g["id"], "name": g["name"], "icon": g.get("icon"), "owner": g.get("owner", False)}
        for g in api_get("/users/@me/guilds")
    ]


def resolve_guild_id(guild: str) -> str:
    """Resolve a guild ID or exact name (case-insensitive) to a guild ID."""
    if guild.isdigit():
        return guild
    matches = [g for g in list_guilds() if g["name"].lower() == guild.lower()]
    if not matches:
        raise CliError("guild_resolution_error", f"Guild '{guild}' not found.")
    if len(matches) > 1:
        ids = ", ".join(g["id"] for g in matches)
        raise CliError(
            "guild_resolution_error", f"Guild '{guild}' is ambiguous. Matches: {ids}. Use a guild ID."
        )
    return matches[0]["id"]


def list_channels(guild_id: str) -> list[dict]:
    channels = [
        {
            "id": ch["id"],
            "name": ch["name"],
            "type": ch.get("type", 0),
            "position": ch.get("position", 0),
            "parent_id": ch.get("parent_id"),
            "topic": ch.get("topic"),
        }
        for ch in api_get(f"/guilds/{guild_id}/channels")
        if ch.get("type") in TEXT_CHANNEL_TYPES
    ]
    return sorted(channels, key=lambda ch: ch["position"])


def parse_message(msg: dict, channel_id: str) -> dict:
    """Flatten a Discord message; attachments keep their CDN URL, embeds their title."""
    author = msg.get("author", {})
    ts = msg.get("timestamp", "")
    timestamp = datetime.fromisoformat(ts) if ts else datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)

    parts = [msg["content"]] if msg.get("content") else []
    for att in msg.get("attachments", []):
        filename = att.get("filename", "file")
        url = att.get("url") or att.get("proxy_url")
        parts.append(f"[attachment: {filename}]({url})" if url else f"[attachment: {filename}]")
    for embed in msg.get("embeds", []):
        if title := embed.get("title"):
            parts.append(f"[embed: {title}]")

    return {
        "msg_id": msg["id"],
        "channel_id": channel_id,
        "sender_id": author.get("id"),
        "sender_name": author.get("global_name") or author.get("username") or "Unknown",
        "content": "\n".join(parts),
        "timestamp": timestamp.isoformat(),
    }


def fetch_messages(channel_id: str, *, limit: int, after: str | None = None) -> list[dict]:
    """Fetch up to `limit` messages, oldest first.

    With `after`, page forward from that message ID; otherwise page backward from the newest.
    """
    messages: list[dict] = []
    before: str | None = None
    while len(messages) < limit:
        batch = min(limit - len(messages), 100)
        params: dict[str, Any] = {"limit": batch}
        if after is not None:
            params["after"] = after
        elif before is not None:
            params["before"] = before
        data = api_get(f"/channels/{channel_id}/messages", **params)
        messages.extend(parse_message(m, channel_id) for m in data)
        if len(data) < batch:
            break
        # Discord returns each page newest-first.
        if after is not None:
            after = data[0]["id"]
        else:
            before = data[-1]["id"]
        time.sleep(random.uniform(0.3, 1.0))
    return sorted(messages, key=lambda m: int(m["msg_id"]))


def channel_context(channel_id: str) -> dict[str, str | None]:
    """Best-effort guild/channel names to store alongside synced messages."""
    context: dict[str, str | None] = {"guild_id": None, "guild_name": None, "channel_name": None}
    try:
        channel = api_get(f"/channels/{channel_id}")
        context["channel_name"] = channel.get("name")
        context["guild_id"] = channel.get("guild_id")
        if context["guild_id"]:
            context["guild_name"] = api_get(f"/guilds/{context['guild_id']}").get("name")
    except CliError:
        pass
    return context


# --- local store ----------------------------------------------------------------


def db_path() -> Path:
    if raw := os.environ.get("DB_PATH"):
        return Path(raw).expanduser()
    if raw := os.environ.get("XDG_DATA_HOME"):
        base = Path(raw).expanduser()
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path.home() / ".local" / "share"
    return base / "discord-cli" / "messages.db"


def open_db() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA)
    return conn


def insert_messages(conn: sqlite3.Connection, messages: list[dict]) -> int:
    """Insert messages, skipping ones already stored. Returns rows inserted."""
    before = conn.total_changes
    conn.executemany(
        """INSERT OR IGNORE INTO messages
           (guild_id, guild_name, channel_id, channel_name, msg_id,
            sender_id, sender_name, content, timestamp)
           VALUES (:guild_id, :guild_name, :channel_id, :channel_name, :msg_id,
                   :sender_id, :sender_name, :content, :timestamp)""",
        messages,
    )
    conn.commit()
    return conn.total_changes - before


def last_msg_id(conn: sqlite3.Connection, channel_id: str) -> str | None:
    row = conn.execute(
        "SELECT msg_id FROM messages WHERE channel_id = ? ORDER BY CAST(msg_id AS INTEGER) DESC LIMIT 1",
        (channel_id,),
    ).fetchone()
    return row[0] if row else None


def stored_channels(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT channel_id, channel_name, guild_id, guild_name,
                  COUNT(*) AS msg_count, MIN(timestamp) AS first_msg, MAX(timestamp) AS last_msg
           FROM messages GROUP BY channel_id ORDER BY msg_count DESC"""
    ).fetchall()
    return [dict(r) for r in rows]


def require_messages(conn: sqlite3.Connection) -> None:
    """Fail on an empty database so "no results" is not mistaken for "no matches"."""
    if not conn.execute("SELECT 1 FROM messages LIMIT 1").fetchone():
        raise CliError(
            "empty_database", "Local database is empty. Run `dc sync CHANNEL_ID` first."
        )


def resolve_guild(conn: sqlite3.Connection, guild: str) -> str:
    """Resolve a stored guild ID or exact name (case-insensitive) to a guild ID."""
    rows = conn.execute(
        """SELECT guild_id FROM messages
           WHERE guild_id IS NOT NULL AND (guild_id = ? OR lower(guild_name) = lower(?))
           GROUP BY guild_id""",
        (guild, guild),
    ).fetchall()
    if not rows:
        raise CliError("guild_resolution_error", f"Guild '{guild}' not found in database.")
    if len(rows) > 1:
        ids = ", ".join(r["guild_id"] for r in rows)
        raise CliError(
            "guild_resolution_error", f"Guild '{guild}' is ambiguous. Matches: {ids}. Use a guild ID."
        )
    return rows[0]["guild_id"]


def resolve_channel(conn: sqlite3.Connection, channel: str, guild_id: str | None) -> str:
    """Resolve a stored channel ID or exact name (case-insensitive), optionally within a guild."""
    channels = [c for c in stored_channels(conn) if not guild_id or c["guild_id"] == guild_id]
    matches = [c for c in channels if c["channel_id"] == channel] or [
        c for c in channels if (c["channel_name"] or "").lower() == channel.lower()
    ]
    if not matches:
        raise CliError("channel_resolution_error", f"Channel '{channel}' not found in database.")
    if len(matches) > 1:
        preview = ", ".join(
            f"{c['guild_name'] + ' > ' if c['guild_name'] else ''}"
            f"#{c['channel_name'] or c['channel_id']} ({c['channel_id']})"
            for c in matches[:5]
        ) + (", ..." if len(matches) > 5 else "")
        raise CliError(
            "channel_resolution_error",
            f"Channel '{channel}' is ambiguous. Matches: {preview}. Use a channel ID.",
        )
    return matches[0]["channel_id"]


def select_messages(
    conn: sqlite3.Connection,
    *,
    limit: int,
    keyword: str | None = None,
    channel_id: str | None = None,
    guild_id: str | None = None,
    sender: str | None = None,
    hours: int | None = None,
) -> list[dict]:
    """Return matching messages, newest first."""
    query = f"SELECT {_MESSAGE_COLUMNS} FROM messages WHERE 1=1"
    params: list[Any] = []
    if keyword is not None:
        query += " AND content LIKE ?"
        params.append(f"%{keyword}%")
    if channel_id:
        query += " AND channel_id = ?"
        params.append(channel_id)
    if guild_id:
        query += " AND guild_id = ?"
        params.append(guild_id)
    if sender:
        query += " AND (sender_id = ? OR lower(sender_name) = lower(?))"
        params += [sender, sender]
    if hours is not None:
        query += " AND timestamp >= ?"
        params.append((datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat())
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)
    return [dict(r) for r in conn.execute(query, params).fetchall()]


def local_scope(conn: sqlite3.Connection, args: argparse.Namespace) -> dict[str, str | None]:
    require_messages(conn)
    guild_id = resolve_guild(conn, args.guild) if args.guild else None
    channel_id = resolve_channel(conn, args.channel, guild_id) if args.channel else None
    return {"guild_id": guild_id, "channel_id": channel_id}


# --- commands -------------------------------------------------------------------


def cmd_status(args: argparse.Namespace) -> None:
    user = api_get("/users/@me")
    emit(
        {
            "authenticated": True,
            "user": {
                "id": user.get("id", ""),
                "name": user.get("global_name") or user.get("username", ""),
                "username": user.get("username", ""),
                "global_name": user.get("global_name") or "",
                "mfa_enabled": bool(user.get("mfa_enabled", False)),
                "premium_type": user.get("premium_type", 0),
            },
        }
    )


def cmd_guilds(args: argparse.Namespace) -> None:
    emit(list_guilds())


def cmd_channels(args: argparse.Namespace) -> None:
    emit(list_channels(resolve_guild_id(args.guild)))


def cmd_sync(args: argparse.Namespace) -> None:
    conn = open_db()
    after = last_msg_id(conn, args.channel)
    if args.hours is not None:
        since = datetime.now(timezone.utc) - timedelta(hours=args.hours)
        cutoff = (int(since.timestamp() * 1000) - DISCORD_EPOCH_MS) << 22
        if after is None or cutoff > int(after):
            after = str(cutoff)
    context = channel_context(args.channel)
    messages = [{**m, **context} for m in fetch_messages(args.channel, limit=args.limit, after=after)]
    emit(
        {
            "fetched": len(messages),
            "stored": insert_messages(conn, messages),
            # Paging forward stopped at the limit, so newer messages may remain.
            "has_more": after is not None and len(messages) >= args.limit,
        }
    )


def cmd_remote_search(args: argparse.Namespace) -> None:
    params: dict[str, Any] = {"content": args.keyword}
    if args.channel:
        params["channel_id"] = args.channel
    data = api_get(f"/guilds/{resolve_guild_id(args.guild)}/messages/search", **params)
    hits = [
        parse_message(m, m.get("channel_id", ""))
        for group in data.get("messages", [])
        for m in group
        if m.get("hit")
    ]
    emit(hits[: args.limit])


def cmd_search(args: argparse.Namespace) -> None:
    conn = open_db()
    scope = local_scope(conn, args)
    emit(
        select_messages(
            conn, limit=args.limit, keyword=args.keyword, sender=args.sender, hours=args.hours, **scope
        )
    )


def cmd_recent(args: argparse.Namespace) -> None:
    conn = open_db()
    scope = local_scope(conn, args)
    emit(select_messages(conn, limit=args.limit, hours=args.hours, **scope)[::-1])


def cmd_stats(args: argparse.Namespace) -> None:
    channels = stored_channels(open_db())
    emit({"total": sum(c["msg_count"] for c in channels), "channels": channels})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="discord.py", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Check that DISCORD_TOKEN is valid").set_defaults(func=cmd_status)

    dc = sub.add_parser("dc", help="Discord API commands").add_subparsers(dest="dc_command", required=True)
    dc.add_parser("guilds", help="List joined guilds").set_defaults(func=cmd_guilds)
    p = dc.add_parser("channels", help="List text channels in a guild")
    p.add_argument("guild", help="Guild ID or exact name")
    p.set_defaults(func=cmd_channels)
    p = dc.add_parser("sync", help="Fetch new messages of a channel into the local database")
    p.add_argument("channel", help="Channel ID")
    p.add_argument("-n", "--limit", type=int, default=5000, help="Max messages to fetch")
    p.add_argument(
        "--hours",
        type=int,
        help="Only fetch messages from the last N hours (older unsynced messages are skipped)",
    )
    p.set_defaults(func=cmd_sync)
    p = dc.add_parser("search", help="Discord native search in a guild (no sync needed)")
    p.add_argument("guild", help="Guild ID or exact name")
    p.add_argument("keyword")
    p.add_argument("-c", "--channel", help="Channel ID")
    p.add_argument("-n", "--limit", type=int, default=25, help="Max results")
    p.set_defaults(func=cmd_remote_search)

    def add_scope(p: argparse.ArgumentParser) -> None:
        p.add_argument("-c", "--channel", help="Channel ID or exact name")
        p.add_argument("-g", "--guild", help="Guild ID or exact name")
        p.add_argument("--hours", type=int, help="Only messages from the last N hours")

    p = sub.add_parser("search", help="Search locally stored messages, newest first")
    p.add_argument("keyword")
    add_scope(p)
    p.add_argument("--sender", help="Sender ID or exact name")
    p.add_argument("-n", "--limit", type=int, default=50, help="Max results")
    p.set_defaults(func=cmd_search)
    p = sub.add_parser("recent", help="Latest locally stored messages, oldest first")
    add_scope(p)
    p.add_argument("-n", "--limit", type=int, default=50, help="Max messages")
    p.set_defaults(func=cmd_recent)
    sub.add_parser("stats", help="Message counts per stored channel").set_defaults(func=cmd_stats)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except CliError as e:
        fail(e)
    except sqlite3.Error as e:
        fail(CliError("database_error", str(e)))


if __name__ == "__main__":
    main()
