from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import requests
from mutagen import MutagenError
from mutagen.id3 import APIC, TALB, TIT2, TPE1, TPE2, TPOS, TRCK, ID3
from mutagen.mp3 import MP3

from core.models import TrackInfo


LOGGER = logging.getLogger(__name__)


def _download_cover(cover_url: str, cache_dir: Path, log) -> tuple[Path, str] | None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cover_hash = hashlib.sha256(cover_url.encode("utf-8")).hexdigest()

    try:
        for cache_path, cached_mime in (
            (cache_dir / f"{cover_hash}.jpg", "image/jpeg"),
            (cache_dir / f"{cover_hash}.png", "image/png"),
        ):
            if cache_path.is_file() and cache_path.stat().st_size > 0:
                return cache_path, cached_mime

        response = requests.get(
            cover_url,
            headers={"User-Agent": "BibliotecaOffline/2.0"},
            timeout=15,
        )
        response.raise_for_status()
        content_type = (response.headers.get("Content-Type") or "").split(";", 1)[0].lower()
        if content_type not in {"image/jpeg", "image/png"}:
            log(f"  Capa ignorada: formato nao suportado ({content_type or 'desconhecido'}).")
            return None

        suffix = ".png" if content_type == "image/png" else ".jpg"
        cache_path = cache_dir / f"{cover_hash}{suffix}"
        cache_path.write_bytes(response.content)
        return cache_path, content_type
    except (OSError, requests.RequestException) as error:
        log(f"  Nao foi possivel baixar a capa: {error}")
        return None


def apply_id3_tags(
    mp3_path: Path,
    track_info: TrackInfo,
    cache_dir: Path,
    log=None,
) -> bool:
    """Aplica metadados do Spotify sem tornar o tagging requisito do download."""
    log = log or LOGGER.info
    cover_result = None

    try:
        audio = MP3(mp3_path, ID3=ID3)
        if audio.tags is None:
            audio.add_tags()

        audio.tags.delall("TIT2")
        audio.tags.delall("TPE1")
        audio.tags.delall("TALB")
        audio.tags.delall("TPE2")
        audio.tags.delall("TRCK")
        audio.tags.delall("TPOS")
        audio.tags.delall("APIC")

        audio.tags.add(TIT2(encoding=3, text=[track_info.title]))
        if track_info.artist:
            audio.tags.add(TPE1(encoding=3, text=[track_info.artist]))
        if track_info.album:
            audio.tags.add(TALB(encoding=3, text=[track_info.album]))
            audio.tags.add(TPE2(encoding=3, text=[track_info.artist]))
        if track_info.track_number:
            track_text = str(track_info.track_number)
            if track_info.track_total:
                track_text += f"/{track_info.track_total}"
            audio.tags.add(TRCK(encoding=3, text=[track_text]))
        if track_info.disc_number:
            disc_text = str(track_info.disc_number)
            if track_info.disc_total:
                disc_text += f"/{track_info.disc_total}"
            audio.tags.add(TPOS(encoding=3, text=[disc_text]))

        if track_info.cover_url:
            cover_result = _download_cover(track_info.cover_url, cache_dir, log)
            if cover_result:
                cover_path, mime = cover_result
                audio.tags.add(
                    APIC(
                        encoding=3,
                        mime=mime,
                        type=3,
                        desc="Cover",
                        data=cover_path.read_bytes(),
                    )
                )
        else:
            log("    Spotify nao forneceu URL de capa para esta faixa.")

        audio.save(v2_version=3)
        return True
    except (OSError, ValueError, TypeError, MutagenError) as error:
        log(f"  Nao foi possivel aplicar metadados em {mp3_path.name}: {error}")
        return False
