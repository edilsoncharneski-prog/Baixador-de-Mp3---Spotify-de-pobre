from __future__ import annotations

import re
import unicodedata
from typing import Any


LIVE_TERMS = ("ao vivo", "live", "dvd", "show", "concert", "acustico", "acoustic")
PLAYBACK_TERMS = (
    "playback",
    "play back",
    "play-back",
    "backing track",
    "karaoke",
)
PENALTIES = {
    "karaoke": -1000,
    "playback": -1000,
    "play back": -1000,
    "backing track": -1000,
    "cover": -80,
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
BAD_RESULT_TERMS = [
    "playback", "play back", "play-back", "backing track",
    "karaoke", "cover", "instrumental", "nightcore", "sped up", "slowed",
    "remix", "live", "aula", "tutorial",
]
BAD_CHANNEL_TERMS = [
    "playback", "play back", "play-back", "backing track", "karaoke",
]


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", normalized.casefold()).strip()


def is_playback_title(value: str) -> bool:
    """Verifica se um titulo/texto contem indicativo explicito de playback/karaoke."""
    norm = normalize_text(value)
    cleaned = re.sub(r"[\-_/\\()\[\]\{\}\.,;:|]", " ", norm)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    words = set(cleaned.split())
    if "playback" in words or "karaoke" in words:
        return True
    if re.search(r"\bplay\s*back\b", cleaned):
        return True
    if re.search(r"\bbacking\s+track\b", cleaned):
        return True
    return False


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


def contains_bad_result_term(
    title: str,
    original_query: str,
    channel: str = "",
    allowed_live: bool = False,
) -> bool:
    normalized_title = normalize_text(title)
    normalized_query = normalize_text(original_query)
    normalized_channel = normalize_text(channel)

    # 1. Proibicao estrita de playback: se a busca nao for intencionalmente playback,
    # descarta qualquer resultado com playback no titulo ou no canal.
    if not is_playback_title(normalized_query):
        if is_playback_title(normalized_title):
            return True
        for bad_channel in BAD_CHANNEL_TERMS:
            if bad_channel in normalized_channel:
                return True
        if re.search(r"\bpbk\b", normalized_channel) or re.search(r"\bpbk\b", normalized_title):
            return True

    # 2. Descarte dos demais termos suspeitos
    for term in BAD_RESULT_TERMS:
        if term in {"playback", "play back", "play-back", "backing track"}:
            continue
        if allowed_live and term in {"live", "ao vivo", "dvd", "show", "concert"}:
            continue
        if term in normalized_title and term not in normalized_query:
            return True

    return False


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
    log=None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """
    Ordena candidatos por score e pelos criterios de desempate definidos.
    Resultados com titulo ou canal suspeito (playback, karaoke, cover, live indevido,
    etc. ausentes da busca original) sao estritamente descartados antes da pontuacao.
    """
    scored = []
    track_name, _ = split_track_search_query(search_query)
    allowed_live = is_live_source(track_name, album_name)

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        target = entry.get("webpage_url") or entry.get("original_url") or entry.get("url")
        if not target:
            continue
        title = str(entry.get("title") or "").strip()
        channel = str(entry.get("channel") or entry.get("uploader") or "").strip()
        if title and contains_bad_result_term(title, search_query, channel, allowed_live=allowed_live):
            if log:
                log(f"  Descartado por titulo/canal proibido (playback/suspeito): {title} [{channel}]")
            continue
        score, flags = score_youtube_candidate(entry, search_query, album_name)
        if score < -100:
            if log:
                log(f"  Descartado por pontuacao proibida ({score}): {title}")
            continue
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


def build_youtube_search_terms(search_query: str) -> list[str]:
    """Termos de busca alternativos para retry quando o primeiro falha."""
    track_name, artist_name = split_track_search_query(search_query)
    combined = " ".join(part for part in [track_name, artist_name] if part).strip()
    terms = []
    if combined:
        terms.extend([
            f"ytsearch10:{combined} audio oficial",
            f"ytsearch10:{combined} official audio",
            f"ytsearch10:{combined} audio",
            f"ytsearch10:{combined}",
        ])
    if track_name and track_name != combined:
        terms.append(f"ytsearch10:{track_name}")
    terms.append(f"ytsearch10:{search_query.replace(' - ', ' ')}")
    return list(dict.fromkeys(terms))
