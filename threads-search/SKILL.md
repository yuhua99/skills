---
name: threads-search
description: Search Threads posts and comments. Use for Threads recommendations, reviews, warnings, or travel experiences.
compatibility: Python 3.10+. Env THREADS_SID (sessionid cookie value).
---

# Threads Search

CLI: `<dir of this SKILL.md>/scripts/threads_cli.py`

```sh
python3 "<CLI_PATH>" search --query "<keywords>" --max-pages 0   # 0-2; start at 0, prefer a new query over more pages
python3 "<CLI_PATH>" get --url "<results[].url>"                 # post + top ~10 direct comments; no pagination
```

stdout: `{"schemaVersion":"1","command":"search|get","data":{...}}`
stderr on failure (exit 1): `{"schemaVersion":"1","error":{"code":"INVALID_ARGUMENT|COMMAND_FAILED","message":"..."}}`

`data`:

- search: `results[]{id,url,text,timestamp,likeCount,replyCount,images,videos,links}`, `hasMoreResults`
- get: `post{same fields}`, `comments[]{same fields without replyCount}`, `hasMoreComments` (not fetchable)

## Use

- Cite only `url` values from the output; never fabricate URLs.
- Deduplicate by `id`. Reposts or several mentions in one thread are one source.
- `get` only posts whose comments add evidence.

## Failures

Stop and report on: `Session rejected or expired` (user must refresh `THREADS_SID`), `Rate limited` (stop all calls), `Search query expired`, `Request forbidden (HTTP 403)` (do not assume expiry). Fix `INVALID_ARGUMENT` once. `did not contain the requested post` / `redirected away`: skip that URL. Never retry auth or rate-limit failures; never touch cookies or GraphQL config.
