#!/usr/bin/env python
"""Download Kaggle competition discussion topics and comments.

This uses the official Kaggle Python client rather than browser scraping.  It
is intended for research/offline mining: every topic is saved as raw JSON, a
topic/comment JSONL corpus, and a readable Markdown transcript.

Authentication follows the normal Kaggle client rules. In this workbench that
means ~/.kaggle/access_token is enough; do not put credentials in this repo.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import time
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable

from kaggle.api.kaggle_api_extended import KaggleApi


DEFAULT_COMPETITION = "ai-agent-security-multi-step-tool-attacks"


class _HTMLToText(HTMLParser):
    """Small dependency-free HTML-to-text converter for Kaggle message bodies."""

    BLOCK_TAGS = {
        "blockquote",
        "br",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "ol",
        "p",
        "pre",
        "table",
        "tr",
        "ul",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []
        self._link_href: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n")
        if tag == "a":
            attrs_map = dict(attrs)
            self._link_href = attrs_map.get("href")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "a":
            self._link_href = None
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_entityref(self, name: str) -> None:
        self.parts.append(html.unescape(f"&{name};"))

    def handle_charref(self, name: str) -> None:
        self.parts.append(html.unescape(f"&#{name};"))

    def text(self) -> str:
        text = "".join(self.parts)
        text = html.unescape(text)
        text = re.sub(r"[ \t\r\f\v]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def html_to_text(value: Any) -> str:
    if not value:
        return ""
    parser = _HTMLToText()
    parser.feed(str(value))
    parser.close()
    return parser.text()


def jsonable(value: Any) -> Any:
    """Convert Kaggle SDK objects and datetimes into JSON-safe data."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(v) for v in value]
    if hasattr(value, "to_dict"):
        return jsonable(value.to_dict())
    return str(value)


def iter_nested_comments(
    comments: Iterable[dict[str, Any]],
    *,
    topic_id: int,
    parent_id: Any = None,
    depth: int = 0,
) -> Iterable[dict[str, Any]]:
    for index, comment in enumerate(comments):
        row = dict(comment)
        replies = row.pop("replies", None) or []
        row["topicId"] = topic_id
        row["parentCommentId"] = parent_id
        row["depth"] = depth
        row["siblingIndex"] = index
        row["contentText"] = html_to_text(row.get("content"))
        yield row
        comment_id = row.get("id")
        yield from iter_nested_comments(
            replies,
            topic_id=topic_id,
            parent_id=comment_id,
            depth=depth + 1,
        )


def render_topic_markdown(topic: dict[str, Any], comments: list[dict[str, Any]]) -> str:
    title = topic.get("title") or f"Topic {topic.get('id')}"
    lines = [
        f"# {title}",
        "",
        f"- Topic ID: {topic.get('id')}",
        f"- URL: {topic.get('url') or topic.get('topicUrl') or ''}",
        f"- Author: {topic.get('authorName') or topic.get('author_name') or ''}",
        f"- Posted: {topic.get('postDate') or topic.get('post_date') or ''}",
        f"- Votes: {topic.get('votes') or 0}",
        f"- Comment count: {topic.get('commentCount') or topic.get('comment_count') or 0}",
        "",
        "## Topic body",
        "",
        html_to_text(topic.get("content") or topic.get("body") or "") or "_No topic body returned by API._",
        "",
        "## Comments",
        "",
    ]
    if not comments:
        lines.append("_No comments returned by API._")
        return "\n".join(lines).rstrip() + "\n"

    for comment in comments:
        depth = int(comment.get("depth") or 0)
        prefix = "#" * min(depth + 3, 6)
        author = comment.get("authorName") or comment.get("author_name") or "Unknown"
        post_date = comment.get("postDate") or comment.get("post_date") or ""
        comment_id = comment.get("id")
        lines.extend(
            [
                f"{prefix} Comment {comment_id} by {author}",
                "",
                f"- Posted: {post_date}",
                f"- Parent: {comment.get('parentCommentId') or ''}",
                f"- Votes: {comment.get('votes') or 0}",
                "",
                comment.get("contentText") or "_No comment body returned by API._",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def append_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count


def safe_filename(topic_id: Any, title: Any) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", str(title or "topic")).strip("-")
    slug = slug[:90].strip("-") or "topic"
    return f"{topic_id}-{slug}.md"


def call_with_retries(label: str, fn: Any, *, retries: int, base_sleep: float) -> Any:
    """Call a Kaggle API function with simple retry/backoff for rate limits."""

    attempt = 0
    while True:
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - SDK raises several HTTP wrappers.
            message = str(exc)
            retryable = (
                "429" in message
                or "Too Many Requests" in message
                or "500" in message
                or "502" in message
                or "503" in message
                or "504" in message
            )
            if not retryable or attempt >= retries:
                raise
            sleep_s = base_sleep * (2 ** attempt)
            print(f"retry {attempt + 1}/{retries} after {label}: {type(exc).__name__}: {message}; sleeping {sleep_s:.1f}s", flush=True)
            time.sleep(sleep_s)
            attempt += 1


def list_all_topics(
    api: KaggleApi,
    competition: str,
    limit: int | None = None,
    *,
    retries: int,
    base_sleep: float,
) -> list[dict[str, Any]]:
    topics: list[dict[str, Any]] = []
    seen: set[int] = set()
    page = 1
    total_count: int | None = None
    while True:
        response = call_with_retries(
            f"competition_list_topics page={page}",
            lambda: api.competition_list_topics(competition, page=page),
            retries=retries,
            base_sleep=base_sleep,
        )
        page_topics = response.topics or []
        if total_count is None:
            total_count = getattr(response, "total_count", None)
        if not page_topics:
            break
        for topic_obj in page_topics:
            topic = jsonable(topic_obj)
            topic_id = int(topic["id"])
            if topic_id in seen:
                continue
            seen.add(topic_id)
            topics.append(topic)
            if limit is not None and len(topics) >= limit:
                return topics
        if total_count is not None and len(topics) >= total_count:
            break
        page += 1
    return topics


def fetch_topic(
    api: KaggleApi,
    competition: str,
    topic_id: int,
    page_size: int,
    *,
    retries: int,
    base_sleep: float,
) -> dict[str, Any]:
    topic_obj, comments_obj, next_page_token = call_with_retries(
        f"forums_topic_show topic={topic_id}",
        lambda: api.forums_topic_show(topic_id, page_size=page_size),
        retries=retries,
        base_sleep=base_sleep,
    )
    all_comment_objs = list(comments_obj or [])
    current_token = next_page_token
    while current_token:
        _, page_comments, current_token = call_with_retries(
            f"forums_topic_show topic={topic_id} page_token",
            lambda: api.forums_topic_show(
                topic_id,
                page_size=page_size,
                page_token=current_token,
            ),
            retries=retries,
            base_sleep=base_sleep,
        )
        all_comment_objs.extend(page_comments or [])

    topic = jsonable(topic_obj)
    comments_tree = [jsonable(comment) for comment in all_comment_objs]

    # The competition endpoint returns a slightly different message tree. Save it
    # too because it can expose reply structure differently across SDK versions.
    messages: Any
    try:
        messages_resp = call_with_retries(
            f"competition_list_topic_messages topic={topic_id}",
            lambda: api.competition_list_topic_messages(
                competition,
                topic_id,
                page_size=-1,
            ),
            retries=retries,
            base_sleep=base_sleep,
        )
        messages = jsonable(messages_resp.messages or [])
    except Exception as exc:  # noqa: BLE001 - preserve partial scrape.
        messages = {"error": type(exc).__name__, "message": str(exc)}

    flat_comments = list(iter_nested_comments(comments_tree, topic_id=topic_id))
    return {
        "topic": topic,
        "commentsTree": comments_tree,
        "commentsFlat": flat_comments,
        "competitionMessages": messages,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--competition", default=DEFAULT_COMPETITION)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--limit-topics", type=int, default=None)
    parser.add_argument("--sleep", type=float, default=0.0, help="Optional delay between topic requests.")
    parser.add_argument("--retries", type=int, default=8)
    parser.add_argument("--retry-base-sleep", type=float, default=5.0)
    parser.add_argument("--skip-comments", action="store_true")
    args = parser.parse_args()

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    out_dir = args.out or Path("runs") / f"kaggle-discussions-{stamp}"
    raw_dir = out_dir / "raw"
    md_dir = out_dir / "topics"
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    md_dir.mkdir(parents=True, exist_ok=True)

    api = KaggleApi()
    api.authenticate()

    topics = list_all_topics(
        api,
        args.competition,
        limit=args.limit_topics,
        retries=args.retries,
        base_sleep=args.retry_base_sleep,
    )
    topic_rows = [
        {
            **topic,
            "contentText": html_to_text(topic.get("content") or ""),
        }
        for topic in topics
    ]
    append_jsonl(out_dir / "topics.jsonl", topic_rows)

    total_comments = 0
    topic_errors: list[dict[str, Any]] = []
    if not args.skip_comments:
        for index, topic in enumerate(topics, start=1):
            topic_id = int(topic["id"])
            title = topic.get("title") or ""
            print(f"[{index}/{len(topics)}] {topic_id} {title}", flush=True)
            try:
                payload = fetch_topic(
                    api,
                    args.competition,
                    topic_id,
                    args.page_size,
                    retries=args.retries,
                    base_sleep=args.retry_base_sleep,
                )
                write_json(raw_dir / f"topic_{topic_id}.json", payload)
                flat_comments = payload["commentsFlat"]
                total_comments += append_jsonl(out_dir / "comments.jsonl", flat_comments)
                md = render_topic_markdown(payload["topic"], flat_comments)
                (md_dir / safe_filename(topic_id, title)).write_text(md, encoding="utf-8")
            except Exception as exc:  # noqa: BLE001 - keep collecting.
                error = {"topicId": topic_id, "title": title, "error": type(exc).__name__, "message": str(exc)}
                topic_errors.append(error)
                print(f"ERROR {topic_id}: {type(exc).__name__}: {exc}", flush=True)
            if args.sleep:
                time.sleep(args.sleep)

    manifest = {
        "competition": args.competition,
        "createdUtc": stamp,
        "topicCount": len(topics),
        "commentCount": total_comments,
        "errors": topic_errors,
        "files": {
            "topicsJsonl": "topics.jsonl",
            "commentsJsonl": "comments.jsonl",
            "rawTopicsDir": "raw/",
            "markdownTopicsDir": "topics/",
        },
        "method": "KaggleApi.competition_list_topics + KaggleApi.forums_topic_show + KaggleApi.competition_list_topic_messages",
    }
    write_json(out_dir / "manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2), flush=True)
    return 0 if not topic_errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
