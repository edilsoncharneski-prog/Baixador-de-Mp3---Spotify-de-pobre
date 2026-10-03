import json
import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from core.models import TrackInfo


APP_NAME = "Biblioteca Offline"
SPOTIFY_PLAYLIST_QUERY_URL = "https://api-partner.spotify.com/pathfinder/v1/query"
SPOTIFY_PLAYLIST_QUERY_HASH = (
    "908a5597b4d0af0489a9ad6a2d41bc3b416ff47c0884016d92bbd6822d0eb6d8"
)
SPOTIFY_PLAYLIST_ID_PATTERN = re.compile(r"^[A-Za-z0-9]{16,64}$")
SPOTIFY_URL_PATTERN = re.compile(
    r"(https?://[^\s<>\"']+|spotify:(?:playlist|album|track):[A-Za-z0-9]+)"
)
SPOTIFY_COLLECTION_TYPES = {"playlist", "album", "track"}
INVALID_WINDOWS_CHARS = r'[\\/:*?"<>|]'
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _noop_log(message: str) -> None:
    pass


def _extract_image_url(value) -> str | None:
    """Extrai a primeira URL de capa conhecida nas estruturas do Spotify."""
    if isinstance(value, dict):
        for key in ("cover_url", "url"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.startswith(("http://", "https://")):
                return candidate
        for key in ("coverArt", "sources", "images", "image", "imageUrl", "album", "albumOfTrack", "cover"):
            result = _extract_image_url(value.get(key))
            if result:
                return result
    elif isinstance(value, list):
        for item in value:
            result = _extract_image_url(item)
            if result:
                return result
    return None


def _artist_names(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        names = []
        for item in value:
            if isinstance(item, dict):
                name = item.get("name") or item.get("profile", {}).get("name")
                if name:
                    names.append(str(name))
        return ", ".join(names)
    if isinstance(value, dict):
        return _artist_names(value.get("items") or value.get("artists"))
    return ""


def _to_int(value) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _track_info_from_item(item: dict, album_name: str = "", index: int | None = None, total: int | None = None) -> TrackInfo | None:
    title = item.get("title") or item.get("name")
    artist = item.get("subtitle") or _artist_names(item.get("artists"))
    nested_track = item.get("track") if isinstance(item.get("track"), dict) else {}
    title = title or nested_track.get("name")
    artist = artist or _artist_names(nested_track.get("artists"))
    album_value = item.get("album")
    album = album_value if isinstance(album_value, str) else ""
    if isinstance(album_value, dict):
        album = album_value.get("name", "")
    album = album or nested_track.get("album", {}).get("name", "")
    album = album or item.get("albumOfTrack", {}).get("name", "")
    album = album or album_name
    if not title or not artist:
        return None

    return TrackInfo(
        title=str(title),
        artist=str(artist),
        album=str(album or ""),
        track_number=_to_int(item.get("trackNumber") or nested_track.get("trackNumber") or index),
        track_total=_to_int(item.get("trackTotal") or total),
        disc_number=_to_int(item.get("discNumber") or nested_track.get("discNumber")),
        disc_total=_to_int(item.get("discTotal")),
        cover_url=_extract_image_url(item) or _extract_image_url(nested_track),
    )


def sanitize_folder_name(folder_name: str) -> str:
    clean_name = re.sub(INVALID_WINDOWS_CHARS, "", folder_name)
    clean_name = re.sub(r"\s+", " ", clean_name).strip(" .")
    return clean_name[:100] or "Playlist Spotify"


def normalize_spotify_playlist_url(playlist_url: str, log=None) -> str:
    log = log or _noop_log
    clean_url = playlist_url.strip().strip('"').strip("'")
    match = SPOTIFY_URL_PATTERN.search(clean_url)
    if match:
        clean_url = match.group(1).rstrip(").,;")

    if clean_url.startswith(("spotify:playlist:", "spotify:album:", "spotify:track:")):
        _, collection_type, collection_id = clean_url.split(":", 2)
        if collection_type in SPOTIFY_COLLECTION_TYPES and SPOTIFY_PLAYLIST_ID_PATTERN.match(collection_id):
            return f"https://open.spotify.com/{collection_type}/{collection_id}"

    parsed_url = urlparse(clean_url)
    hostname = (parsed_url.hostname or "").lower()
    if hostname == "open.spotify.com":
        return clean_url

    if hostname.endswith("spotify.com") or hostname.endswith("spotify.link"):
        try:
            response = requests.get(clean_url, headers={"User-Agent": USER_AGENT}, timeout=10, allow_redirects=True)
            response.close()
            final_url = response.url.strip()
            if final_url and final_url != clean_url:
                log(f"URL Spotify normalizada: {final_url}")
                return final_url
        except requests.exceptions.RequestException as error:
            log(f"Nao foi possivel resolver redirecionamento do Spotify: {error}")

    return clean_url


def extract_spotify_collection(playlist_url: str, log=None) -> tuple[str, str]:
    normalized_url = normalize_spotify_playlist_url(playlist_url, log)
    parsed_url = urlparse(normalized_url)
    path_parts = [part for part in parsed_url.path.split("/") if part]

    if (parsed_url.hostname or "").lower() != "open.spotify.com":
        raise ValueError(
            "URL invalida. Certifique-se de que e um link de playlist, album ou faixa publica do Spotify."
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
        "URL invalida. Certifique-se de que e um link de playlist, album ou faixa publica do Spotify."
    )


def build_embed_playlist_url(playlist_url: str, log=None) -> str:
    collection_type, collection_id = extract_spotify_collection(playlist_url, log)
    return f"https://open.spotify.com/embed/{collection_type}/{collection_id}"


def extract_tracks_from_embed_data(data: dict) -> list[str]:
    track_items = data["props"]["pageProps"]["state"]["data"]["entity"]["trackList"]
    return [f"{item['title']} - {item['subtitle']}" for item in track_items]


def extract_track_info_from_embed_data(data: dict, album_name: str = "") -> list[TrackInfo]:
    track_items = data["props"]["pageProps"]["state"]["data"]["entity"]["trackList"]
    total = len(track_items)
    tracks = []
    for index, item in enumerate(track_items, start=1):
        track = _track_info_from_item(item, album_name, index, total)
        if track:
            tracks.append(track)
    return tracks


def extract_tracks_from_page_data(data: dict) -> list[str]:
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


def extract_track_info_from_page_data(data: dict) -> list[TrackInfo]:
    track_items = data["props"]["pageProps"]["data"]["trackList"]["items"]
    total = len(track_items)
    tracks = []
    for index, item in enumerate(track_items, start=1):
        track = _track_info_from_item(item, index=index, total=total)
        if track:
            tracks.append(track)
    return tracks


def extract_playlist_name_from_embed_data(data: dict) -> str:
    playlist_name = data["props"]["pageProps"]["state"]["data"]["entity"]["name"]
    return sanitize_folder_name(str(playlist_name))


def extract_playlist_name_from_page_data(data: dict) -> str:
    playlist_name = data["props"]["pageProps"]["data"]["name"]
    return sanitize_folder_name(str(playlist_name))


def extract_access_token_from_embed_data(data: dict) -> str | None:
    try:
        token = data["props"]["pageProps"]["state"]["settings"]["session"]["accessToken"]
    except (KeyError, TypeError):
        return None

    return str(token) if token else None


def extract_track_from_graphql_item(item: dict) -> str | None:
    track = extract_track_info_from_graphql_item(item)
    return track.search_query if track else None


def extract_track_info_from_graphql_item(item: dict) -> TrackInfo | None:
    track = item.get("itemV2", {}).get("data", {})
    if track.get("__typename") != "Track":
        return None

    return _track_info_from_item(track)


def fetch_all_tracks_from_graphql(playlist_id: str, access_token: str, log=None) -> list[str]:
    return [track.search_query for track in fetch_all_track_info_from_graphql(playlist_id, access_token, log)]


def fetch_all_track_info_from_graphql(playlist_id: str, access_token: str, log=None) -> list[TrackInfo]:
    log = log or _noop_log
    tracks: list[TrackInfo] = []
    offset = 0
    limit = 100

    headers = {
        "Accept": "application/json",
        "App-Platform": "WebPlayer",
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
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
            track = extract_track_info_from_graphql_item(item)
            if track:
                tracks.append(track)

        total_count = int(content.get("totalCount") or 0)
        log(f"  Carregadas {len(tracks)}/{total_count or '?'} musicas do Spotify...")

        next_offset = content.get("pagingInfo", {}).get("nextOffset")
        if not next_offset or not items or (total_count and next_offset >= total_count):
            break

        offset = int(next_offset)

    return tracks


def extract_playlist_data(playlist_url: str, log=None) -> tuple[str, str, list[str]]:
    """
    Extrai (tipo, nome, faixas) de uma playlist, album ou faixa publica do Spotify
    atraves do parsing do HTML da pagina embed (bloco __NEXT_DATA__), com paginacao
    via GraphQL quando um access token esta disponivel.
    """
    log = log or _noop_log
    playlist_url = normalize_spotify_playlist_url(playlist_url, log)
    collection_type, playlist_id = extract_spotify_collection(playlist_url)
    embed_url = build_embed_playlist_url(playlist_url)

    log("Conectando ao Spotify pela pagina embed...")
    response = requests.get(embed_url, headers={"User-Agent": USER_AGENT}, timeout=20)
    response.raise_for_status()
    response.encoding = "utf-8"
    log("Extraindo dados do Spotify...")
    soup = BeautifulSoup(response.text, "html.parser")
    script_tag = soup.find("script", id="__NEXT_DATA__")
    if not script_tag:
        raise ValueError("Nao foi possivel encontrar os dados do Spotify. O link e publico?")
    try:
        data = json.loads(script_tag.string)
    except (json.JSONDecodeError, TypeError) as error:
        raise ValueError(f"Erro ao ler JSON do Spotify: {error}") from error

    if collection_type == "track":
        entity = data["props"]["pageProps"]["state"]["data"]["entity"]
        track_name = str(entity.get("title") or entity.get("name") or "Spotify")
        artists = entity.get("artists") or []
        artist_names = ", ".join(
            str(artist.get("name"))
            for artist in artists
            if isinstance(artist, dict) and artist.get("name")
        )
        if not artist_names:
            artist_names = "Artista desconhecido"
        duration = entity.get("duration")
        if duration:
            log(f"Faixa individual: {track_name} | duracao: {int(duration) // 1000}s")
        return collection_type, sanitize_folder_name(track_name), [f"{track_name} - {artist_names}"]

    playlist_name = "Spotify"
    try:
        playlist_name = extract_playlist_name_from_embed_data(data)
    except (KeyError, TypeError):
        try:
            playlist_name = extract_playlist_name_from_page_data(data)
        except (KeyError, TypeError):
            pass

    access_token = extract_access_token_from_embed_data(data)
    if collection_type == "playlist" and access_token:
        try:
            log("Buscando todas as paginas da playlist...")
            tracks = fetch_all_tracks_from_graphql(playlist_id, access_token, log)
            if tracks:
                return collection_type, playlist_name, tracks
        except (KeyError, TypeError, ValueError, requests.exceptions.RequestException) as error:
            log(f"  Nao foi possivel paginar pelo Spotify: {error}")
            log("  Usando lista inicial disponivel no embed.")

    try:
        return collection_type, playlist_name, extract_tracks_from_embed_data(data)
    except (KeyError, TypeError):
        pass
    try:
        return collection_type, playlist_name, extract_tracks_from_page_data(data)
    except (KeyError, TypeError) as error:
        raise ValueError(
            "Erro ao analisar a estrutura de dados do Spotify. "
            f"O layout do site pode ter mudado. Detalhes: {error}"
        ) from error


def extract_playlist_data_with_metadata(playlist_url: str, log=None) -> tuple[str, str, list[TrackInfo]]:
    """Versao enriquecida; a funcao legada acima permanece compativel."""
    log = log or _noop_log
    playlist_url = normalize_spotify_playlist_url(playlist_url, log)
    collection_type, playlist_id = extract_spotify_collection(playlist_url)
    embed_url = build_embed_playlist_url(playlist_url)

    log("Conectando ao Spotify pela pagina embed...")
    response = requests.get(embed_url, headers={"User-Agent": USER_AGENT}, timeout=20)
    response.raise_for_status()
    response.encoding = "utf-8"
    soup = BeautifulSoup(response.text, "html.parser")
    script_tag = soup.find("script", id="__NEXT_DATA__")
    if not script_tag:
        raise ValueError("Nao foi possivel encontrar os dados do Spotify. O link e publico?")
    try:
        data = json.loads(script_tag.string)
    except (json.JSONDecodeError, TypeError) as error:
        raise ValueError(f"Erro ao ler JSON do Spotify: {error}") from error

    if collection_type == "track":
        entity = data["props"]["pageProps"]["state"]["data"]["entity"]
        track = _track_info_from_item(entity)
        if not track:
            raise ValueError("Nao foi possivel extrair os metadados da faixa do Spotify.")
        return collection_type, sanitize_folder_name(track.title), [track]

    playlist_name = "Spotify"
    try:
        playlist_name = extract_playlist_name_from_embed_data(data)
    except (KeyError, TypeError):
        try:
            playlist_name = extract_playlist_name_from_page_data(data)
        except (KeyError, TypeError):
            pass

    access_token = extract_access_token_from_embed_data(data)
    if collection_type == "playlist" and access_token:
        try:
            log("Buscando todas as paginas da playlist...")
            tracks = fetch_all_track_info_from_graphql(playlist_id, access_token, log)
            if tracks:
                return collection_type, playlist_name, tracks
        except (KeyError, TypeError, ValueError, requests.exceptions.RequestException) as error:
            log(f"  Nao foi possivel paginar pelo Spotify: {error}")
            log("  Usando lista inicial disponivel no embed.")

    try:
        album_name = playlist_name if collection_type == "album" else ""
        tracks = extract_track_info_from_embed_data(data, album_name)
        if tracks:
            return collection_type, playlist_name, tracks
    except (KeyError, TypeError):
        pass
    try:
        tracks = extract_track_info_from_page_data(data)
        if tracks:
            return collection_type, playlist_name, tracks
    except (KeyError, TypeError) as error:
        raise ValueError(
            "Erro ao analisar os metadados do Spotify. "
            f"O layout do site pode ter mudado. Detalhes: {error}"
        ) from error

    raise ValueError("Nenhuma faixa com metadados validos foi encontrada no Spotify.")


def extract_playlist_tracks(playlist_url: str) -> list[str]:
    """Compatibilidade: retorna apenas a lista de faixas."""
    _, _, tracks = extract_playlist_data(playlist_url)
    return tracks
