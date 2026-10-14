#!/usr/bin/env python3

from __future__ import annotations

import gzip
import json
import os
import random
import re
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler

SID_ENV = "THREADS_SID"
CSRF_ENV = "THREADS_CSRF"
GRAPHQL_ENDPOINT = "https://www.threads.com/graphql/query"
SEARCH_DOC_ID = "27823181280640742"
SEARCH_QUERY = "BarcelonaSearchResultsRefetchableQuery"
# Comment pagination is disabled: the previous refetch doc_id now returns execution errors,
# and the current web client's follow-up query has not been captured.
PAGE_LIMITS = {"search": 2, "get": 0}
SCHEMA_VERSION = "1"
TIMEOUT_SECONDS = 30
COOKIE_VALUE_FORBIDDEN = re.compile(r"[\s;,\x00-\x1f\x7f]")
SCRIPT_JSON = re.compile(
    r"<script\b[^>]*type=[\"']application/json[\"'][^>]*>([\s\S]*?)</script>", re.IGNORECASE
)

# Retain the web query's variables; changing them requires live verification.
SEARCH_VARIABLES = {
    "before": None,
    "first": 10,
    "has_communities": True,
    "has_community_green_dot": False,
    "has_favicons": False,
    "has_live_chats": False,
    "has_serp_header": True,
    "last": None,
    "meta_place_id": None,
    "pinned_ids": None,
    "power_search_info": None,
    "recent": 0,
    "search_surface": "default",
    "tagID": None,
    "trend_fbid": None,
    "__relay_internal__pv__BarcelonaHasSERPHeaderrelayprovider": True,
    "__relay_internal__pv__BarcelonaHasCommunitiesrelayprovider": True,
    "__relay_internal__pv__BarcelonaHasWebFaviconsrelayprovider": False,
    "__relay_internal__pv__BarcelonaHasCommunityGreenDotrelayprovider": False,
    "__relay_internal__pv__BarcelonaMessagesHasLiveChatMessagingrelayprovider": False,
    "__relay_internal__pv__BarcelonaHasCommunityTopContributorsrelayprovider": False,
    "__relay_internal__pv__BarcelonaHasCommunityBobbleheadsrelayprovider": True,
    "__relay_internal__pv__BarcelonaIsLoggedInrelayprovider": True,
    "__relay_internal__pv__BarcelonaHasDearAlgoConsumptionrelayprovider": True,
    "__relay_internal__pv__BarcelonaHasEventBadgerelayprovider": False,
    "__relay_internal__pv__BarcelonaGenAIRepliesEnabledrelayprovider": True,
    "__relay_internal__pv__BarcelonaIsSearchDiscoveryEnabledrelayprovider": False,
    "__relay_internal__pv__BarcelonaHasGameScoreSharerelayprovider": True,
    "__relay_internal__pv__BarcelonaHasPublicViewCountCardrelayprovider": True,
    "__relay_internal__pv__BarcelonaHasCommunityEntityCardrelayprovider": True,
    "__relay_internal__pv__BarcelonaHasScorecardCommunityrelayprovider": True,
    "__relay_internal__pv__BarcelonaHasSportTeamAllegianceCardrelayprovider": True,
    "__relay_internal__pv__BarcelonaHasMusicrelayprovider": True,
    "__relay_internal__pv__BarcelonaHasNewspaperLinkStylerelayprovider": False,
    "__relay_internal__pv__BarcelonaHasMessagingrelayprovider": True,
    "__relay_internal__pv__BarcelonaHasPodcastTextFragmentsrelayprovider": False,
    "__relay_internal__pv__BarcelonaShouldFulfillLightboxQueryrelayprovider": True,
    "__relay_internal__pv__BarcelonaHasViewerRepliedrelayprovider": True,
    "__relay_internal__pv__BarcelonaHasPrivateRepliesDeprecationrelayprovider": False,
    "__relay_internal__pv__BarcelonaHasGhostPostEmojiActivationrelayprovider": False,
    "__relay_internal__pv__BarcelonaOptionalCookiesEnabledrelayprovider": True,
    "__relay_internal__pv__BarcelonaHasDearAlgoWebProductionrelayprovider": False,
    "__relay_internal__pv__BarcelonaIsCrawlerrelayprovider": False,
    "__relay_internal__pv__BarcelonaCanSeeSponsoredContentrelayprovider": False,
    "__relay_internal__pv__BarcelonaShouldShowFediverseM075Featuresrelayprovider": True,
    "__relay_internal__pv__BarcelonaIsInternalUserrelayprovider": False,
}


class CommandError(Exception):
    pass


class Response:
    def __init__(self, status: int, url: str, headers: dict[str, str], body: bytes):
        self.status = status
        self.url = url
        self.headers = headers
        self.body = body

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.text())


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: N802
        return None


def cookie_value(name: str, required: bool) -> str | None:
    value = (os.environ.get(name) or "").strip()
    if not value:
        if required:
            raise CommandError(f"{name} is not set. Set it to the sessionid cookie value.")
        return None
    if COOKIE_VALUE_FORBIDDEN.search(value):
        cookie = "sessionid" if name == SID_ENV else "csrftoken"
        raise CommandError(f"{name} must contain only the {cookie} cookie value.")
    return value


def request_headers(accept: str) -> dict[str, str]:
    sid = cookie_value(SID_ENV, required=True)
    csrf = cookie_value(CSRF_ENV, required=False)
    cookie = f"sessionid={sid}" + (f"; csrftoken={csrf}" if csrf else "")
    headers = {"Cookie": cookie, "Accept": accept, "Accept-Encoding": "gzip"}
    if csrf:
        headers["X-CSRFToken"] = csrf
    return headers


def send(url: str, headers: dict[str, str], data: bytes | None = None, follow_redirects: bool = True) -> Response:
    opener = build_opener() if follow_redirects else build_opener(_NoRedirect)
    request = Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as raw:
            body = raw.read()
            response_headers = {key.lower(): value for key, value in raw.headers.items()}
            status, final_url = raw.status, raw.geturl()
    except HTTPError as error:
        body = error.read()
        response_headers = {key.lower(): value for key, value in error.headers.items()}
        status, final_url = error.code, error.geturl()
    if response_headers.get("content-encoding") == "gzip":
        body = gzip.decompress(body)
    return Response(status, final_url, response_headers, body)


def fetch_with_retry(url: str, headers: dict[str, str], data: bytes | None = None, follow_redirects: bool = True) -> Response:
    def attempt() -> Response:
        return send(url, headers, data, follow_redirects)

    try:
        response = attempt()
    except (URLError, TimeoutError, OSError):
        time.sleep(0.25 + random.random() * 0.5)
        return attempt()
    if 500 <= response.status <= 599:
        time.sleep(0.25 + random.random() * 0.5)
        return attempt()
    return response


def check_response(response: Response, content_type: str) -> None:
    if response.status == 401:
        raise CommandError(f"Session rejected or expired (HTTP 401). Refresh {SID_ENV} from a logged-in browser.")
    if response.status == 403:
        raise CommandError(f"Request forbidden (HTTP 403). This alone does not establish that {SID_ENV} expired.")
    if response.status in (301, 302, 303, 307, 308):
        raise CommandError("Unexpected redirect")
    if re.search(r"/(?:login|accounts/login)(?:/|$)", urlparse(response.url).path):
        raise CommandError("Session rejected or expired. Threads redirected to login.")
    if response.status == 429:
        raise CommandError("Rate limited")
    if not 200 <= response.status < 300:
        raise CommandError(f"HTTP request failed ({response.status})")
    if content_type not in response.headers.get("content-type", ""):
        raise CommandError(f"Response content type was not {content_type}")


# Normalize Threads objects without changing the public JSON output fields.
def base_post_fields(post: dict[str, Any]) -> dict[str, Any]:
    images: dict[str, None] = {}
    videos: dict[str, None] = {}
    links: dict[str, None] = {}
    for item in [post, *(post.get("carousel_media") or [])]:
        candidates = (item.get("image_versions2") or {}).get("candidates") or []
        if candidates and candidates[0].get("url"):
            images[candidates[0]["url"]] = None
        for video in item.get("video_versions") or []:
            if video.get("url"):
                videos[video["url"]] = None
    info = post.get("text_post_app_info") or {}
    for fragment in ((info.get("text_fragments") or {}).get("fragments") or []):
        if fragment.get("linkified_web_url"):
            links[fragment["linkified_web_url"]] = None
    preview = info.get("link_preview_attachment") or {}
    for key in ("url", "display_url"):
        if preview.get(key):
            links[preview[key]] = None
    username = (post.get("user") or {}).get("username")
    code = post.get("code")
    return {
        "id": str(post.get("pk") or post.get("id") or ""),
        "url": f"https://www.threads.com/@{username}/post/{code}" if code and username else None,
        "text": (post.get("caption") or {}).get("text") or "",
        "timestamp": post.get("taken_at"),
        "likeCount": post.get("like_count"),
        "images": list(images),
        "videos": list(videos),
        "links": list(links),
    }


def normalize_post(post: dict[str, Any]) -> dict[str, Any]:
    return {**base_post_fields(post), "replyCount": (post.get("text_post_app_info") or {}).get("direct_reply_count")}


def post_key(post: dict[str, Any]) -> str:
    return str(post.get("pk") or post.get("id") or post.get("code"))


def dedupe_posts(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return list({post_key(post): post for post in posts}.values())


def parse_ssr_json(html: str, page_label: str) -> list[Any]:
    values = []
    for source in SCRIPT_JSON.findall(html):
        try:
            values.append(json.loads(source))
        except ValueError:
            # Pages may contain unrelated, non-JSON script payloads.
            continue
    if not values:
        raise CommandError(f"{page_label} did not contain readable Relay JSON")
    return values


def walk(value: Any):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def page_request_context(html: str) -> dict[str, str]:
    context: dict[str, str] = {}
    for value in parse_ssr_json(html, "Threads page"):
        for node in walk(value):
            if not (isinstance(node, list) and len(node) >= 3 and isinstance(node[2], dict)):
                continue
            name, data = node[0], node[2]
            if name == "LSD" and isinstance(data.get("token"), str):
                context["lsd"] = data["token"]
            elif name == "DTSGInitialData" and isinstance(data.get("token"), str):
                context["fb_dtsg"] = data["token"]
            elif name == "CurrentUserInitialData" and data.get("APP_ID"):
                context["app_id"] = str(data["APP_ID"])
    return context


def search_connection(connection: Any) -> dict[str, Any] | None:
    if not isinstance(connection, dict) or not isinstance(connection.get("edges"), list) or not connection.get("page_info"):
        return None
    posts = []
    for edge in connection["edges"]:
        items = (((edge or {}).get("node") or {}).get("thread") or {}).get("thread_items") or []
        if items and items[0].get("post"):
            posts.append(items[0]["post"])
    return {"posts": posts, "page_info": connection["page_info"]}


def parse_search_html(html: str) -> dict[str, Any]:
    found: dict[str, dict[str, Any]] = {}
    for value in parse_ssr_json(html, "Threads search page"):
        for node in walk(value):
            if isinstance(node, dict) and "searchResults" in node:
                result = search_connection(node["searchResults"])
                if result:
                    key = json.dumps({"ids": [post_key(p) for p in result["posts"]], "page_info": result["page_info"]}, sort_keys=True)
                    found[key] = result
    if len(found) != 1:
        raise CommandError("Threads search page did not contain one search result set")
    return next(iter(found.values()))


# Post pages embed several `data.media` fragments sharing one `id`: one carries the post
# (pk/code/user), another carries `text_post_app_info.direct_replies`, where
# edges[].node.posts.edges[].node are the reply posts.
def parse_post_html(html: str, code: str) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    found = [
        node["media"]
        for value in parse_ssr_json(html, "Threads page")
        for node in walk(value)
        if isinstance(node, dict) and isinstance(node.get("media"), dict)
        and node["media"].get("id") and node["media"].get("text_post_app_info")
    ]
    main_post = next(
        (m for m in found if m.get("code") == code and m.get("pk") and (m.get("user") or {}).get("username")
         and not m["text_post_app_info"].get("is_reply")),
        None,
    )
    if main_post is None:
        if not found:
            raise CommandError("Threads page did not contain the requested post: no SSR post data was found.")
        raise CommandError("Threads page did not contain the requested post")
    replies = next(
        (m["text_post_app_info"]["direct_replies"] for m in found
         if m.get("id") == main_post["id"] and m["text_post_app_info"].get("direct_replies")),
        None,
    ) or {}
    posts = [
        inner["node"]
        for edge in replies.get("edges") or []
        for inner in (((edge or {}).get("node") or {}).get("posts") or {}).get("edges") or []
        if inner and inner.get("node")
    ]
    return main_post, posts, replies.get("page_info") or {"has_next_page": False, "end_cursor": None}


def fetch_graphql(doc_id: str, friendly_name: str, variables: dict[str, Any], operation: str, context: dict[str, str]) -> Any:
    form = {"doc_id": doc_id, "fb_api_req_friendly_name": friendly_name, "variables": json.dumps(variables)}
    for key in ("lsd", "fb_dtsg"):
        if context.get(key):
            form[key] = context[key]
    headers = request_headers("application/json")
    headers["Content-Type"] = "application/x-www-form-urlencoded"
    headers["X-FB-Friendly-Name"] = friendly_name
    if context.get("lsd"):
        headers["X-FB-LSD"] = context["lsd"]
    if context.get("app_id"):
        headers["X-IG-App-ID"] = context["app_id"]
    response = fetch_with_retry(GRAPHQL_ENDPOINT, headers, urlencode(form).encode(), follow_redirects=False)
    check_response(response, "application/json")
    result = response.json()
    errors = result.get("errors") or []
    if errors:
        expired = any(
            re.search(r"query (?:not found|does not exist|is invalid)|doc.?id", str(e.get("message") or ""), re.IGNORECASE)
            or e.get("code") in ("1675030", 1675030)
            for e in errors
        )
        raise CommandError(f"{operation} query expired" if expired else f"{operation} GraphQL request failed")
    return result


def search(query: str, max_pages: int) -> dict[str, Any]:
    if max_pages > 0 and not cookie_value(CSRF_ENV, required=False):
        raise CommandError(f"{CSRF_ENV} is not set; it is required for --max-pages > 0. Set it to the csrftoken cookie value or use --max-pages 0.")
    url = "https://www.threads.com/search?" + urlencode({"q": query, "serp_type": "default"})
    response = fetch_with_retry(url, request_headers("text/html"))
    check_response(response, "text/html")
    html = response.text()
    initial = parse_search_html(html)
    context = page_request_context(html) if max_pages > 0 else {}
    posts = list(initial["posts"])
    page_info = initial["page_info"]
    for _ in range(max_pages):
        if not page_info.get("has_next_page"):
            break
        if not page_info.get("end_cursor"):
            raise CommandError("Search pagination cursor was missing")
        result = fetch_graphql(
            SEARCH_DOC_ID, SEARCH_QUERY, {**SEARCH_VARIABLES, "query": query, "after": page_info["end_cursor"]},
            "Search", context,
        )
        nxt = search_connection((result.get("data") or {}).get("searchResults"))
        if nxt is None:
            raise CommandError("Search query expired")
        posts.extend(nxt["posts"])
        page_info = nxt["page_info"]
    return {
        "query": query,
        "results": [normalize_post(p) for p in dedupe_posts(posts)],
        "hasMoreResults": bool(page_info.get("has_next_page")),
    }


def parse_post_url(value: str) -> tuple[str, str]:
    url = urlparse(value)
    if url.scheme != "https" or url.hostname not in ("threads.com", "www.threads.com") \
            or not re.fullmatch(r"/@[^/]+/post/[^/]+/?", url.path):
        raise CommandError("Expected a full Threads post URL")
    return value, url.path.rstrip("/").rsplit("/", 1)[-1]


def is_direct_reply(post: dict[str, Any], main_post: dict[str, Any]) -> bool:
    root_author = (main_post.get("user") or {}).get("pk") or (main_post.get("user") or {}).get("id")
    info = post.get("text_post_app_info") or {}
    reply_to = info.get("reply_to_author") or {}
    replied_to = reply_to.get("pk") or reply_to.get("id")
    return info.get("is_reply") is True and root_author is not None and str(replied_to) == str(root_author)


def get_post(value: str, max_pages: int) -> dict[str, Any]:
    url, code = parse_post_url(value)
    if max_pages > 0:
        raise CommandError("Comment pagination is not supported; use --max-pages 0")
    headers = request_headers("text/html")
    # Verified live: without this Referer the page redirects to the feed or omits post data.
    headers["Referer"] = "https://www.threads.com/"
    response = fetch_with_retry(url, headers)
    check_response(response, "text/html")
    if not urlparse(response.url).path.rstrip("/").endswith(f"/post/{code}"):
        raise CommandError("Threads post page redirected away from the requested post; not parsing the destination feed.")
    main_post, posts, page_info = parse_post_html(response.text(), code)
    comments = [p for p in posts if is_direct_reply(p, main_post)]
    return {
        "post": normalize_post(main_post),
        "comments": [base_post_fields(p) for p in dedupe_posts(comments)],
        "hasMoreComments": bool(page_info.get("has_next_page")),
    }


def parse_args(args: list[str]) -> tuple[str, str, int]:
    command = args[0] if args else None
    value_flag = {"search": "--query", "get": "--url"}.get(command or "")
    if not value_flag:
        raise ValueError("Usage: threads_cli.py <search|get> <--query|--url> <value> [--max-pages N]")
    options: dict[str, str] = {}
    rest = args[1:]
    for index in range(0, len(rest), 2):
        flag = rest[index]
        if flag not in ("--query", "--url", "--max-pages") or index + 1 >= len(rest) or flag in options:
            raise ValueError(f"Invalid arguments for {command}")
        options[flag] = rest[index + 1]
    unwanted = "--url" if command == "search" else "--query"
    if unwanted in options:
        raise ValueError(f"{unwanted} is not valid for {command}")
    if not options.get(value_flag, "").strip():
        raise ValueError(f"{value_flag} is required")
    raw_max_pages = options.get("--max-pages", "0")
    if not re.fullmatch(r"\d+", raw_max_pages):
        raise ValueError("--max-pages must be a non-negative integer")
    max_pages = int(raw_max_pages)
    if max_pages > PAGE_LIMITS[command]:
        raise ValueError(f"--max-pages must not exceed {PAGE_LIMITS[command]} for {command}")
    return command, options[value_flag], max_pages


def emit_error(code: str, message: str) -> int:
    sys.stderr.write(json.dumps({"schemaVersion": SCHEMA_VERSION, "error": {"code": code, "message": message}}) + "\n")
    return 1


def main(argv: list[str]) -> int:
    try:
        command, value, max_pages = parse_args(argv)
    except ValueError as error:
        return emit_error("INVALID_ARGUMENT", str(error))
    try:
        data = search(value, max_pages) if command == "search" else get_post(value, max_pages)
    except CommandError as error:
        return emit_error("COMMAND_FAILED", str(error))
    except (URLError, TimeoutError, OSError, ValueError):
        return emit_error("COMMAND_FAILED", "Threads command failed")
    sys.stdout.write(json.dumps({"schemaVersion": SCHEMA_VERSION, "command": command, "data": data}, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
