import os
import requests
import logging
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)

# Base URL for hianime-API v1 service
ANIWATCH_API_BASE = os.getenv(
    "ANIWATCH_API_BASE",
    "http://localhost:3030/api/v1"
)


def search_anime(query: str, page: int = 1):
    url = f"{ANIWATCH_API_BASE}/search"
    params = {"keyword": query, "page": page}
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()

    js = resp.json()
    hits = js.get("data", {}).get("response", [])
    results = []
    for item in hits:
        slug = item.get("id", "").split("?", 1)[0]
        title = (
            item.get("title")
            or item.get("alternativeTitle")
            or slug.replace("-", " ").title()
        )
        anime_url = f"https://hianime.bz/watch/{slug}"
        results.append((title, anime_url, slug))
    return results


def get_episodes_list(slug: str):
    """
    Fetches all episodes for given slug.
    Calls GET /api/v1/episodes/{slug}
    """
    url = f"{ANIWATCH_API_BASE}/episodes/{slug}"
    resp = requests.get(url, timeout=30)
    if resp.status_code == 404:
        return [("1", f"/watch/{slug}?ep=1")]

    resp.raise_for_status()
    eps = resp.json().get("data", [])

    episodes = []
    for ep in eps:
        raw_id = ep.get("id", "").strip()              # "/watch/slug?ep=N"
        if not raw_id:
            continue

        # parse out ep number
        qs      = urlparse(raw_id).query               # "ep=N"
        nums    = parse_qs(qs).get("ep", [])
        if not nums:
            continue
        episodes.append((nums[0], raw_id))

    episodes.sort(key=lambda x: int(x[0]))
    return episodes


def extract_episode_stream_and_subtitle(episode_id: str):
    """
    Given episode_id="/watch/slug?ep=N":
    Calls GET /api/v1/stream?id=...&server=HD-2&type=sub
    """
    url = f"{ANIWATCH_API_BASE}/stream"
    params = {
        "id":     episode_id,
        "server": "HD-2",
        "type":   "sub"
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()

    data   = resp.json().get("data", {})
    stream = data.get("streamingLink", {})

    # HLS link
    hls_link = stream.get("link", {}).get("file")

    # English subtitle
    subtitle_url = None
    for t in stream.get("tracks", []):
        if t.get("kind") == "captions" or t.get("label", "").lower().startswith("eng"):
            subtitle_url = t.get("file")
            break

    return hls_link, subtitle_url
