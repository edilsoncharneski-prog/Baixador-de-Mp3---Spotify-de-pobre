from __future__ import annotations

import re
import unicodedata
from typing import Any


LIVE_TERMS = ("ao vivo", "live", "dvd", "show", "concert", "acustico", "acoustic")
PENALTIES = {
    "karaoke": -80,
    "cover": -80,
    "playback": -60,
    "instrumental": -60,
    "remix": -50,
    "mashup": -50,
    "live": -40,
    "ao vivo": -40,
    "acustico": -40,
    "acoustic": -40,
    "dvd": -40,
    "show": -40,
    "concert": -40,
}


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", normalized.casefold()).strip()


def split_track_search_query(search_query: str) -> tuple[str, str]:
    if " - " not in search_query:
        return search_query.strip(), ""

    track_name, artist_name = search_query.split(" - ", 1)
    return track_name.strip(), artist_name.strip()


def is_live_source(track_name: str, album_name: str = "") -> bool:
    source_text = normalize_text(f"{track_name} {album_name}")
    return any(term in source_text for term in LIVE_TERMS)


def _has_phrase(text: str, phrase: str) -> bool:
    return bool(phrase and phrase in text)


def score_youtube_candidate(
    candidate: dict[str, Any],
    search_query: str,
    album_name: str = "",
) -> tuple[int, dict[str, bool]]:
    """Pontua um resultado do yt-dlp usando titulo e canal publicos."""
    track_name, artist_name = split_track_search_query(search_query)
    title = normalize_text(str(candidate.get("title") or ""))
    channel = normalize_text(
        str(candidate.get("channel") or candidate.get("uploader") or "")
    )
    combined = f"{title} {channel}"
    normalized_track = normalize_text(track_name)
    main_artist = normalize_text(artist_name.split(",", 1)[0])

    flags = {
        "official_audio": _has_phrase(combined, "official audio"),
        "topic": "topic" in channel,
        "artist_channel": bool(main_artist and main_artist in channel),
        "album": "album" in combined,
    }
    score = 0
    if _has_phrase(title, normalized_track):
        score += 30
    if main_artist and _has_phrase(combined, main_artist):
        score += 25
    if flags["official_audio"]:
        score += 20
    if flags["topic"]:
        score += 20
    if flags["album"]:
        score += 15
    if "audio" in combined:
        score += 10
    if "remastered" in combined:
        score += 5
    if "versao oficial" in combined or "official version" in combined:
        score += 5

    allowed_live = is_live_source(track_name, album_name)
    for term, penalty in PENALTIES.items():
        if allowed_live and term in {"live", "ao vivo", "dvd", "show", "concert"}:
            continue
        if term in combined:
            score += penalty

    return score, flags


def choose_youtube_result(
    entries: list[dict[str, Any]],
    search_query: str,
    album_name: str = "",
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Ordena candidatos por score e pelos criterios de desempate definidos."""
    scored = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        target = entry.get("webpage_url") or entry.get("original_url") or entry.get("url")
        if not target:
            continue
        score, flags = score_youtube_candidate(entry, search_query, album_name)
        scored.append({"entry": entry, "target": str(target), "score": score, "flags": flags})

    scored.sort(
        key=lambda item: (
            item["score"],
            item["flags"]["official_audio"],
            item["flags"]["topic"],
            item["flags"]["artist_channel"],
            item["flags"]["album"],
        ),
        reverse=True,
    )
    return (scored[0] if scored else None), scored

BAD_RESULT_TERMS = [
    "karaoke", "cover", "instrumental", "nightcore", "sped up", "slowed",
    "remix", "live", "aula", "tutorial",
]


def build_youtube_search_terms(search_query: str) -> list[str]:
    """Compatibilidade com o downloader auxiliar legado."""
    track_name, artist_name = split_track_search_query(search_query)
    combined = " ".join(part for part in [track_name, artist_name] if part).strip()
    terms = []
    if combined:
        terms.extend([
            f"ytsearch1:{combined} official audio",
            f"ytsearch1:{combined} audio",
            f"ytsearch1:{combined} lyrics",
            f"ytsearch1:{combined}",
        ])
    if track_name and track_name != combined:
        terms.append(f"ytsearch1:{track_name}")
    terms.append(f"ytsearch1:{search_query.replace(' - ', ' ')}")
    return list(dict.fromkeys(terms))


def contains_bad_result_term(title: str, original_query: str) -> bool:
    normalized_title = normalize_text(title)
    normalized_query = normalize_text(original_query)
    return any(term in normalized_title and term not in normalized_query for term in BAD_RESULT_TERMS)


def resolve_download_target(ydl: Any, search_term: str, original_query: str) -> tuple[str | None, str | None, str | None]:
    info = ydl.extract_info(search_term, download=False)
    entries = info.get("entries") if isinstance(info, dict) else None
    candidate = next((entry for entry in entries if entry), None) if entries else info
    if not isinstance(candidate, dict):
        return None, None, "nenhum resultado encontrado"
    title = str(candidate.get("title") or "").strip()
    if title and contains_bad_result_term(title, original_query):
        return None, title, "resultado rejeitado por titulo suspeito"
    target = candidate.get("webpage_url") or candidate.get("original_url") or candidate.get("url")
    return (str(target), title or None, None) if target else (None, title or None, "resultado sem URL valida")
