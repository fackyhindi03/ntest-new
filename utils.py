import os
import requests

def download_and_rename_subtitle(sub_url: str, ep_num: str, cache_dir: str) -> str:
    """
    Downloads a .vtt (or .srt) subtitle from sub_url into cache_dir,
    naming it episode_<ep_num>.<ext>.
    Returns the local file path.
    """
    if not sub_url:
        raise ValueError("No subtitle URL provided")

    resp = requests.get(sub_url, timeout=30)
    resp.raise_for_status()

    ext = os.path.splitext(sub_url)[1] or ".vtt"
    filename = f"episode_{ep_num}{ext}"
    path = os.path.join(cache_dir, filename)

    with open(path, "wb") as f:
        f.write(resp.content)

    return path
