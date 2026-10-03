from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TrackInfo:
    """Metadados do Spotify usados tanto para busca quanto para tagging."""

    title: str
    artist: str
    album: str = ""
    track_number: int | None = None
    track_total: int | None = None
    disc_number: int | None = None
    disc_total: int | None = None
    cover_url: str | None = None

    @property
    def search_query(self) -> str:
        return f"{self.title} - {self.artist}"

    def __str__(self) -> str:
        return self.search_query


def ensure_track_info(track: TrackInfo | str) -> TrackInfo:
    if isinstance(track, TrackInfo):
        return track

    title, separator, artist = str(track).partition(" - ")
    return TrackInfo(
        title=title.strip(),
        artist=artist.strip() if separator else "",
    )
