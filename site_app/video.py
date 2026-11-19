"""Встраивание видео поездки. В iframe попадает только собранный нами
адрес YouTube, Rutube или VK — произвольный URL роликом не становится,
для него на странице остаётся обычная ссылка."""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import parse_qs, urlparse

_YT_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_RUTUBE_ID = re.compile(r"^[0-9a-fA-F-]{16,40}$")


def video_embed_src(url: Optional[str]) -> Optional[str]:
    raw = (url or "").strip()
    if not raw:
        return None
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return None
    host = parsed.hostname.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path or ""

    if host in ("youtube.com", "m.youtube.com", "youtube-nocookie.com"):
        parts = [p for p in path.split("/") if p]
        vid = ""
        if parts[:1] == ["embed"] and len(parts) >= 2:
            vid = parts[1]
        elif parts[:1] == ["shorts"] and len(parts) >= 2:
            vid = parts[1]
        elif path == "/watch" or (parts[:1] == ["watch"]):
            vid = (parse_qs(parsed.query).get("v") or [""])[0]
        if _YT_ID.match(vid):
            return f"https://www.youtube-nocookie.com/embed/{vid}"
        return None

    if host == "youtu.be":
        vid = path.strip("/").split("/")[0] if path.strip("/") else ""
        if _YT_ID.match(vid):
            return f"https://www.youtube-nocookie.com/embed/{vid}"
        return None

    if host == "rutube.ru":
        parts = [p for p in path.split("/") if p]
        vid = ""
        if len(parts) >= 2 and parts[0] == "video":
            vid = parts[1]
        elif len(parts) >= 3 and parts[0] == "play" and parts[1] == "embed":
            vid = parts[2]
        if _RUTUBE_ID.match(vid):
            return f"https://rutube.ru/play/embed/{vid}"
        return None

    if host in ("vk.com", "vk.ru", "vkvideo.ru"):
        found = re.search(r"video(-?\d+)_(\d+)", path)
        if found:
            return f"https://vk.com/video_ext.php?oid={found.group(1)}&id={found.group(2)}&hd=2"
        if path.rstrip("/").endswith("video_ext.php"):
            q = parse_qs(parsed.query)
            oid = (q.get("oid") or [""])[0]
            vid = (q.get("id") or [""])[0]
            if re.fullmatch(r"-?\d+", oid) and re.fullmatch(r"\d+", vid):
                return f"https://vk.com/video_ext.php?oid={oid}&id={vid}&hd=2"
        return None
    return None
