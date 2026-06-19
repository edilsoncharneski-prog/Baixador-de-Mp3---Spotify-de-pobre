import json
import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


SPOTIFY_PLAYLIST_QUERY_URL = "https://api-partner.spotify.com/pathfinder/v1/query"
SPOTIFY_PLAYLIST_QUERY_HASH = (
    "908a5597b4d0af0489a9ad6a2d41bc3b416ff47c0884016d92bbd6822d0eb6d8"
)
SPOTIFY_PLAYLIST_ID_PATTERN = re.compile(r"^[A-Za-z0-9]{16,64}$")
SPOTIFY_URL_PATTERN = re.compile(
    r"(https?://[^\s<>\"']+|spotify:(?:playlist|album):[A-Za-z0-9]+)"
)
SPOTIFY_COLLECTION_TYPES = {"playlist", "album"}


def _normalize_spotify_playlist_url(playlist_url: str) -> str:
    clean_url = playlist_url.strip().strip('"').strip("'")
    match = SPOTIFY_URL_PATTERN.search(clean_url)
    if match:
        clean_url = match.group(1).rstrip(").,;")

    if clean_url.startswith(("spotify:playlist:", "spotify:album:")):
        _, collection_type, collection_id = clean_url.split(":", 2)
        if collection_type in SPOTIFY_COLLECTION_TYPES and SPOTIFY_PLAYLIST_ID_PATTERN.match(collection_id):
            return f"https://open.spotify.com/{collection_type}/{collection_id}"

    parsed_url = urlparse(clean_url)
    hostname = (parsed_url.hostname or "").lower()
    if hostname == "open.spotify.com":
        return clean_url

    if hostname.endswith("spotify.com") or hostname.endswith("spotify.link"):
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }
        try:
            response = requests.get(clean_url, headers=headers, timeout=10, allow_redirects=True)
            response.close()
            return response.url.strip() or clean_url
        except requests.exceptions.RequestException:
            return clean_url

    return clean_url


def _extract_spotify_collection(playlist_url: str) -> tuple[str, str]:
    normalized_url = _normalize_spotify_playlist_url(playlist_url)
    parsed_url = urlparse(normalized_url)
    path_parts = [part for part in parsed_url.path.split("/") if part]

    if (parsed_url.hostname or "").lower() != "open.spotify.com":
        raise ValueError(
            "URL invalida. Certifique-se de que e um link de playlist ou album publico do Spotify."
        )

    if (
        len(path_parts) >= 3
        and path_parts[0] == "embed"
        and path_parts[1] in SPOTIFY_COLLECTION_TYPES
    ):
        return path_parts[1], path_parts[2]
    if len(path_parts) >= 2 and path_parts[0] in SPOTIFY_COLLECTION_TYPES:
        return path_parts[0], path_parts[1]
    if len(path_parts) >= 3 and path_parts[1] in SPOTIFY_COLLECTION_TYPES:
        return path_parts[1], path_parts[2]

    raise ValueError(
        "URL invalida. Certifique-se de que e um link de playlist ou album publico do Spotify."
    )


def _extract_playlist_id(playlist_url: str) -> str:
    return _extract_spotify_collection(playlist_url)[1]


def _build_embed_playlist_url(playlist_url: str) -> str:
    collection_type, collection_id = _extract_spotify_collection(playlist_url)
    return f"https://open.spotify.com/embed/{collection_type}/{collection_id}"


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


def _extract_access_token_from_embed_data(data: dict) -> str | None:
    try:
        token = data["props"]["pageProps"]["state"]["settings"]["session"]["accessToken"]
    except (KeyError, TypeError):
        return None

    return str(token) if token else None


def _extract_track_from_graphql_item(item: dict) -> str | None:
    track = item.get("itemV2", {}).get("data", {})
    if track.get("__typename") != "Track":
        return None

    track_name = track.get("name")
    artist_items = track.get("artists", {}).get("items", [])
    artist_names = [
        artist.get("profile", {}).get("name")
        for artist in artist_items
        if artist.get("profile", {}).get("name")
    ]

    if not track_name or not artist_names:
        return None

    return f"{track_name} - {', '.join(artist_names)}"


def _fetch_all_tracks_from_graphql(playlist_id: str, access_token: str) -> list[str]:
    tracks = []
    offset = 0
    limit = 100

    headers = {
        "Accept": "application/json",
        "App-Platform": "WebPlayer",
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
    }

    while True:
        payload = {
            "operationName": "queryPlaylist",
            "variables": {
                "uri": f"spotify:playlist:{playlist_id}",
                "limit": limit,
                "offset": offset,
            },
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": SPOTIFY_PLAYLIST_QUERY_HASH,
                }
            },
        }

        response = requests.post(
            SPOTIFY_PLAYLIST_QUERY_URL,
            headers=headers,
            json=payload,
            timeout=20,
        )
        response.raise_for_status()
        playlist = response.json()["data"]["playlistV2"]
        if playlist.get("__typename") != "Playlist":
            raise ValueError("O Spotify nao retornou uma playlist valida.")

        content = playlist["content"]
        items = content.get("items", [])
        for item in items:
            track = _extract_track_from_graphql_item(item)
            if track:
                tracks.append(track)

        total_count = int(content.get("totalCount") or 0)
        next_offset = content.get("pagingInfo", {}).get("nextOffset")
        if not next_offset or not items or (total_count and next_offset >= total_count):
            break

        offset = int(next_offset)

    return tracks


def extract_playlist_tracks(playlist_url: str) -> list[str]:
    """
    Extrai a lista de "Musica - Artista" de uma playlist ou album publico do Spotify
    atraves do parsing do HTML da pagina embed (bloco __NEXT_DATA__).
    """
    playlist_url = _normalize_spotify_playlist_url(playlist_url)
    collection_type, playlist_id = _extract_spotify_collection(playlist_url)
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
    response.encoding = "utf-8"

    print("  -> Extraindo dados da pagina...")
    soup = BeautifulSoup(response.text, "html.parser")

    script_tag = soup.find("script", id="__NEXT_DATA__")
    if not script_tag:
        raise ValueError(
            "Nao foi possivel encontrar os dados do Spotify. O link e realmente publico?"
        )

    try:
        data = json.loads(script_tag.string)
    except (KeyError, json.JSONDecodeError, TypeError) as error:
        raise ValueError(
            "Erro ao analisar a estrutura de dados do Spotify. "
            f"O layout do site pode ter mudado. Detalhes: {error}"
        ) from error

    try:
        access_token = _extract_access_token_from_embed_data(data)
        if collection_type == "playlist" and access_token:
            print("  -> Buscando todas as paginas da playlist...")
            tracks = _fetch_all_tracks_from_graphql(playlist_id, access_token)
            if tracks:
                return tracks
    except (KeyError, TypeError, ValueError, requests.exceptions.RequestException):
        print("  -> Nao foi possivel paginar. Usando lista inicial do embed.")

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
