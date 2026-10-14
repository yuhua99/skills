# Threads Search Agent Skill

Search Threads posts and fetch a post with its top direct comments through the bundled CLI `scripts/threads_cli.py` (Python 3.10+, stdlib only).

## Environment setup

The CLI authenticates with cookies from a logged-in Threads browser session.

| Variable | Required | Value |
|---|---|---|
| `THREADS_SID` | Yes | `sessionid` cookie value |
| `THREADS_CSRF` | For search pagination (`--max-pages` > 0) | `csrftoken` cookie value |

To get the values, log in to `https://www.threads.com`, open DevTools → Application → Cookies → `https://www.threads.com`, and copy the **Value** column of each cookie.

Set only the value itself, not `sessionid=...` or a full `Cookie` header. Values containing whitespace, `;`, or `,` are rejected.

```bash
export THREADS_SID="your_sessionid_value"
export THREADS_CSRF="your_csrftoken_value"
```

When the CLI reports `Session rejected or expired`, log in again and update `THREADS_SID`.
