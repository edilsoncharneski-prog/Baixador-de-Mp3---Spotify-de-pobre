import json
import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


def _build_embed_playlist_url(playlist_url: str) -> str:
    parsed_url = urlparse(playlist_url)
    path_parts = [part for part in parsed_url.path.split("/") if part]

    if parsed_url.netloc != "open.spotify.com":
        raise ValueError(
            "URL invalida. Certifique-se de que e um link de playlist publico do Spotify."
        )

    if path_parts[:2] == ["embed", "playlist"] and len(path_parts) >= 3:
        playlist_id = path_parts[2]
    elif path_parts[0:1] == ["playlist"] and len(path_parts) >= 2:
        playlist_id = path_parts[1]
    elif len(path_parts) >= 3 and path_parts[1] == "playlist":
        playlist_id = path_parts[2]
    else:
        raise ValueError(
            "URL invalida. Certifique-se de que e um link de playlist publico do Spotify."
        )

    return f"https://open.spotify.com/embed/playlist/{playlist_id}"


def _extract_tracks_from_embed_data(data: dict) -> list[str]:
    track_items = data["props"]["pageProps"]["state"]["data"]["entity"]["trackList"]

    tracks = []
    for item in track_items:
        track_name = item["title"]
        artist_names = item["subtitle"]
        tracks.append(f"{track_name} - {artist_names}")

    return tracks


def _extract_tracks_from_page_data(data: dict) -> list[str]:
    track_items = data["props"]["pageProps"]["data"]["trackList"]["items"]

    tracks = []
    for item in track_items:
        track_name = item["track"]["name"]
        artists = item["track"]["artists"]

        if isinstance(artists, list):
            artist_names = ", ".join(artist["name"] for artist in artists)
        else:
            artist_names = str(artists)

        tracks.append(f"{track_name} - {artist_names}")

    return tracks


def extract_playlist_tracks(playlist_url: str) -> list[str]:
    """
    Extrai a lista de "Musica - Artista" de uma playlist publica do Spotify
    atraves do parsing do HTML da pagina embed (bloco __NEXT_DATA__).
    """
    if not re.match(r"https?://open\.spotify\.com/", playlist_url):
        raise ValueError(
            "URL invalida. Certifique-se de que e um link de playlist publico do Spotify."
        )
    embed_url = _build_embed_playlist_url(playlist_url)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }

    print("  -> Conectando ao Spotify...")
    response = requests.get(embed_url, headers=headers, timeout=15)
    response.raise_for_status()

    print("  -> Extraindo dados da pagina...")
    soup = BeautifulSoup(response.text, "html.parser")

    script_tag = soup.find("script", id="__NEXT_DATA__")
    if not script_tag:
        raise ValueError(
            "Nao foi possivel encontrar os dados da playlist. A playlist e realmente publica?"
        )

    try:
        data = json.loads(script_tag.string)
    except (KeyError, json.JSONDecodeError, TypeError) as error:
        raise ValueError(
            "Erro ao analisar a estrutura de dados do Spotify. "
            f"O layout do site pode ter mudado. Detalhes: {error}"
        ) from error

    try:
        return _extract_tracks_from_embed_data(data)
    except (KeyError, TypeError):
        pass

    try:
        return _extract_tracks_from_page_data(data)
    except (KeyError, TypeError) as error:
        raise ValueError(
            "Erro ao analisar a estrutura de dados do Spotify. "
            f"O layout do site pode ter mudado. Detalhes: {error}"
        ) from error
