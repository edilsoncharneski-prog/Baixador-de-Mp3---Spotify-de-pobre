from __future__ import annotations

import yt_dlp


BAD_RESULT_TERMS = [
    "karaoke",
    "cover",
    "instrumental",
    "nightcore",
    "sped up",
    "slowed",
    "remix",
    "live",
    "aula",
    "tutorial",
]


def split_track_search_query(search_query: str) -> tuple[str, str]:
    if " - " not in search_query:
        return search_query.strip(), ""

    track_name, artist_name = search_query.split(" - ", 1)
    return track_name.strip(), artist_name.strip()


def build_youtube_search_terms(search_query: str) -> list[str]:
    track_name, artist_name = split_track_search_query(search_query)
    combined = " ".join(part for part in [track_name, artist_name] if part).strip()

    terms = []
    if combined:
        terms.extend(
            [
                f"ytsearch1:{combined} official audio",
                f"ytsearch1:{combined} audio",
                f"ytsearch1:{combined} lyrics",
                f"ytsearch1:{combined}",
            ]
        )
    if track_name and track_name != combined:
        terms.append(f"ytsearch1:{track_name}")
    terms.append(f"ytsearch1:{search_query.replace(' - ', ' ')}")

    unique_terms = []
    for term in terms:
        if term not in unique_terms:
            unique_terms.append(term)

    return unique_terms


def contains_bad_result_term(title: str, original_query: str) -> bool:
    normalized_title = title.lower()
    normalized_query = original_query.lower()

    for term in BAD_RESULT_TERMS:
        if term in normalized_title and term not in normalized_query:
            return True
    return False


def resolve_download_target(
    ydl: yt_dlp.YoutubeDL,
    search_term: str,
    original_query: str,
) -> tuple[str | None, str | None, str | None]:
    info = ydl.extract_info(search_term, download=False)
    entries = info.get("entries") if isinstance(info, dict) else None
    candidate = None

    if entries:
        candidate = next((entry for entry in entries if entry), None)
    elif isinstance(info, dict):
        candidate = info

    if not candidate:
        return None, None, "nenhum resultado encontrado"

    title = str(candidate.get("title") or "").strip()
    if title and contains_bad_result_term(title, original_query):
        return None, title, "resultado rejeitado por titulo suspeito"

    target = (
        candidate.get("webpage_url")
        or candidate.get("original_url")
        or candidate.get("url")
    )
    if not target:
        return None, title, "resultado sem URL valida"

    return str(target), title or None, None
