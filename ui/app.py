import base64
import ctypes
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import sysconfig
import threading
import tkinter as tk
import tkinter.filedialog as filedialog
import webbrowser
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import customtkinter
import requests
from bs4 import BeautifulSoup
from core.youtube import (
    build_youtube_search_terms as build_shared_youtube_search_terms,
)
from icon_data import ICON_DATA_BASE64


DEFAULT_MUSIC_FOLDER_NAME = "Biblioteca Offline"
APP_NAME = "Biblioteca Offline"
APP_EXECUTABLE_NAME = "BibliotecaOffline"
APP_VERSION = "1.0.3"
APP_AUTHOR = "Edilson Charneski"
APP_COPYRIGHT = "Copyright (c) 2026 Edilson Charneski."
APP_USAGE_NOTE = (
    "Ferramenta criada para uso pessoal e educacional, pensada para quem mora "
    "em locais com pouca internet movel e ainda usa pendrive no dia a dia."
)
COOKIE_EXTENSION_URL = (
    "https://chromewebstore.google.com/detail/get-cookiestxt-locally/"
    "cclelndahbckbenkjhflpdbgdldlbecc"
)
GOLD = "#d4af37"
GOLD_HOVER = "#b8941f"
DARK_PANEL = "#1f1f1f"
SPLASH_BG = "#1a1a1a"
COOKIE_OK = "#39d98a"
COOKIE_MISSING = "#ff4d4f"
MUTED_TEXT = "#9f9f9f"
INVALID_WINDOWS_CHARS = r'[\\/:*?"<>|]'
SPOTIFY_PLAYLIST_QUERY_URL = "https://api-partner.spotify.com/pathfinder/v1/query"
SPOTIFY_PLAYLIST_QUERY_HASH = (
    "908a5597b4d0af0489a9ad6a2d41bc3b416ff47c0884016d92bbd6822d0eb6d8"
)


customtkinter.set_appearance_mode("dark")
try:
    customtkinter.set_default_color_theme("gold")
except (FileNotFoundError, OSError):
    customtkinter.set_default_color_theme("dark-blue")


def get_app_base_path() -> Path:
    """Retorna a pasta real do app, tanto no Python normal quanto no PyInstaller."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def get_external_base_path() -> Path:
    """Retorna a pasta visivel do app, onde o usuario pode colocar arquivos auxiliares."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def get_user_data_path() -> Path:
    return Path.home() / "Music" / APP_NAME


def get_expected_cookie_file_path() -> Path:
    return get_user_data_path() / "cookies.txt"


def get_log_file_path() -> Path:
    return get_user_data_path() / f"{APP_EXECUTABLE_NAME}.log"


def get_default_destination_root() -> Path:
    destination_root = Path.home() / "Music" / DEFAULT_MUSIC_FOLDER_NAME
    destination_root.mkdir(parents=True, exist_ok=True)
    return destination_root


def normalize_destination_path(destination_text: str) -> Path:
    clean_text = destination_text.strip().strip('"')
    if re.match(r"^[A-Za-z]:[^\\/]", clean_text):
        clean_text = f"{clean_text[:2]}\\{clean_text[2:]}"
    return Path(clean_text).expanduser()


def get_cookie_file_path() -> Path | None:
    cookie_file = get_expected_cookie_file_path()
    if cookie_file.is_file() and cookie_file.stat().st_size > 0:
        return cookie_file
    return None


def migrate_legacy_cookie_file(log=None) -> None:
    expected_cookie_file = get_expected_cookie_file_path()
    legacy_cookie_files = [
        get_external_base_path() / "cookies.txt",
    ]
    appdata = os.environ.get("APPDATA")
    if appdata:
        legacy_cookie_files.append(Path(appdata) / APP_NAME / "cookies.txt")

    if expected_cookie_file.exists():
        return

    for legacy_cookie_file in legacy_cookie_files:
        if not legacy_cookie_file.is_file():
            continue
        try:
            expected_cookie_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(legacy_cookie_file, expected_cookie_file)
            if log:
                log(f"cookies.txt migrado para: {expected_cookie_file}")
            return
        except OSError as error:
            if log:
                log(f"Nao foi possivel migrar cookies.txt: {error}")


def ensure_icon_file() -> Path:
    icon_path = get_app_base_path() / "icon.ico"
    if icon_path.is_file() and icon_path.stat().st_size > 0:
        return icon_path

    icon_path.write_bytes(base64.b64decode(ICON_DATA_BASE64))
    return icon_path


def find_executable(candidates: list[str], extra_dirs: list[Path] | None = None) -> Path | None:
    search_dirs = [
        get_app_base_path(),
        get_external_base_path(),
        Path(__file__).resolve().parent.parent,
    ]
    if extra_dirs:
        search_dirs.extend(extra_dirs)

    for directory in search_dirs:
        for candidate in candidates:
            executable_path = directory / candidate
            if executable_path.is_file():
                return executable_path

    for candidate in candidates:
        found_path = shutil.which(candidate)
        if found_path:
            return Path(found_path)

    return None


def get_yt_dlp_executable() -> Path | None:
    scripts_path = sysconfig.get_path("scripts")
    extra_dirs = [Path(scripts_path)] if scripts_path else []
    return find_executable(["yt-dlp.exe", "yt-dlp"], extra_dirs)


def get_ffmpeg_location() -> str | None:
    base_path = get_app_base_path()
    ffmpeg_path = base_path / "ffmpeg.exe"
    ffprobe_path = base_path / "ffprobe.exe"

    if ffmpeg_path.exists() and ffprobe_path.exists():
        return str(base_path)

    local_ffmpeg_path = Path(__file__).resolve().parent / "ffmpeg.exe"
    local_ffprobe_path = Path(__file__).resolve().parent / "ffprobe.exe"
    if local_ffmpeg_path.exists() and local_ffprobe_path.exists():
        return str(local_ffmpeg_path.parent)

    return None


def extract_playlist_id(playlist_url: str) -> str:
    parsed_url = urlparse(playlist_url)
    path_parts = [part for part in parsed_url.path.split("/") if part]

    if parsed_url.netloc != "open.spotify.com":
        raise ValueError(
            "URL invalida. Use um link publico de playlist do Spotify."
        )

    if path_parts[:2] == ["embed", "playlist"] and len(path_parts) >= 3:
        return path_parts[2]
    if path_parts[:1] == ["playlist"] and len(path_parts) >= 2:
        return path_parts[1]
    if len(path_parts) >= 3 and path_parts[1] == "playlist":
        return path_parts[2]

    raise ValueError(
        "URL invalida. Use um link publico de playlist do Spotify."
    )


def build_embed_playlist_url(playlist_url: str) -> str:
    return f"https://open.spotify.com/embed/playlist/{extract_playlist_id(playlist_url)}"


def sanitize_folder_name(folder_name: str) -> str:
    clean_name = re.sub(INVALID_WINDOWS_CHARS, "", folder_name)
    clean_name = re.sub(r"\s+", " ", clean_name).strip(" .")
    return clean_name[:100] or "Playlist Spotify"


def extract_playlist_name_from_embed_data(data: dict) -> str:
    playlist_name = data["props"]["pageProps"]["state"]["data"]["entity"]["name"]
    return sanitize_folder_name(str(playlist_name))


def extract_playlist_name_from_page_data(data: dict) -> str:
    playlist_name = data["props"]["pageProps"]["data"]["name"]
    return sanitize_folder_name(str(playlist_name))


def extract_tracks_from_embed_data(data: dict) -> list[str]:
    track_items = data["props"]["pageProps"]["state"]["data"]["entity"]["trackList"]
    return [f"{item['title']} - {item['subtitle']}" for item in track_items]


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


def extract_access_token_from_embed_data(data: dict) -> str | None:
    try:
        token = data["props"]["pageProps"]["state"]["settings"]["session"]["accessToken"]
    except (KeyError, TypeError):
        return None

    return str(token) if token else None


def extract_track_from_graphql_item(item: dict) -> str | None:
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


def fetch_all_tracks_from_graphql(playlist_id: str, access_token: str, log) -> list[str]:
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
        page_tracks = []
        for item in items:
            track = extract_track_from_graphql_item(item)
            if track:
                page_tracks.append(track)

        tracks.extend(page_tracks)
        total_count = int(content.get("totalCount") or 0)
        log(f"  Carregadas {len(tracks)}/{total_count or '?'} musicas do Spotify...")

        next_offset = content.get("pagingInfo", {}).get("nextOffset")
        if not next_offset or not items or (total_count and next_offset >= total_count):
            break

        offset = int(next_offset)

    return tracks


def extract_playlist_data(playlist_url: str, log) -> tuple[str, list[str]]:
    if not re.match(r"https?://open\.spotify\.com/", playlist_url):
        raise ValueError(
            "URL invalida. Use um link publico de playlist do Spotify."
        )

    playlist_id = extract_playlist_id(playlist_url)
    embed_url = build_embed_playlist_url(playlist_url)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }

    log("Conectando ao Spotify pela pagina embed...")
    response = requests.get(embed_url, headers=headers, timeout=20)
    response.raise_for_status()
    response.encoding = "utf-8"

    log("Extraindo dados da playlist...")
    soup = BeautifulSoup(response.text, "html.parser")
    script_tag = soup.find("script", id="__NEXT_DATA__")
    if not script_tag:
        raise ValueError(
            "Nao foi possivel encontrar os dados da playlist. Ela e publica?"
        )

    try:
        data = json.loads(script_tag.string)
    except (json.JSONDecodeError, TypeError) as error:
        raise ValueError(f"Erro ao ler JSON do Spotify: {error}") from error

    playlist_name = "Playlist Spotify"
    try:
        playlist_name = extract_playlist_name_from_embed_data(data)
    except (KeyError, TypeError):
        try:
            playlist_name = extract_playlist_name_from_page_data(data)
        except (KeyError, TypeError):
            pass

    access_token = extract_access_token_from_embed_data(data)
    if access_token:
        try:
            log("Buscando todas as paginas da playlist...")
            tracks = fetch_all_tracks_from_graphql(playlist_id, access_token, log)
            if tracks:
                return playlist_name, tracks
        except (KeyError, TypeError, ValueError, requests.exceptions.RequestException) as error:
            log(f"  Nao foi possivel paginar pelo Spotify: {shorten_error(error)}")
            log("  Usando lista inicial disponivel no embed.")

    try:
        return playlist_name, extract_tracks_from_embed_data(data)
    except (KeyError, TypeError):
        pass

    try:
        return playlist_name, extract_tracks_from_page_data(data)
    except (KeyError, TypeError) as error:
        raise ValueError(
            "Erro ao analisar a estrutura de dados do Spotify. "
            f"O layout do site pode ter mudado. Detalhes: {error}"
        ) from error


def split_track_search_query(search_query: str) -> tuple[str, str]:
    if " - " not in search_query:
        return search_query.strip(), ""

    track_name, artist_name = search_query.split(" - ", 1)
    return track_name.strip(), artist_name.strip()


def build_youtube_search_terms(search_query: str) -> list[str]:
    return build_shared_youtube_search_terms(search_query)


def summarize_download_error(error_text: str, used_cookie_file: bool = False) -> str:
    if "Sign in to confirm" in error_text or "not a bot" in error_text:
        if used_cookie_file:
            return (
                "YouTube exigiu autenticacao/anti-bot mesmo usando cookies.txt. "
                "Exporte cookies novos do YouTube e substitua o arquivo ao lado do .exe."
            )
        return (
            "YouTube bloqueou por anti-bot/login. "
            "Coloque um cookies.txt valido ao lado do .exe e tente novamente."
        )
    if "Could not copy Chrome cookie database" in error_text or "Failed to decrypt with DPAPI" in error_text:
        return (
            "Nao foi possivel ler os cookies. "
            "Coloque um cookies.txt valido ao lado do .exe e tente novamente."
        )
    if "Requested format is not available" in error_text or "Only images are available" in error_text:
        return (
            "O YouTube retornou o video sem formato de audio. "
            "Instale o Node.js ou atualize o yt-dlp para resolver o challenge do YouTube."
        )
    return "Video nao encontrado ou bloqueado no YouTube."


def shorten_error(error_text: str) -> str:
    error_text = re.sub(r"\s+", " ", error_text).strip()
    error_text = error_text.replace("ERROR: ", "")
    return error_text[:700]


def should_retry_with_cookies(error_text: str) -> bool:
    retry_markers = [
        "Sign in to confirm",
        "not a bot",
        "confirm your age",
        "This video may be inappropriate",
        "HTTP Error 429",
        "Too Many Requests",
    ]
    return any(marker in error_text for marker in retry_markers)


def should_retry_without_cookies(error_text: str) -> bool:
    retry_markers = [
        "Requested format is not available",
        "HTTP Error 403",
        "Forbidden",
    ]
    return any(marker in error_text for marker in retry_markers)


def get_external_process_options() -> dict:
    options = {"creationflags": 0}
    if os.name == "nt":
        options["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        options["startupinfo"] = startupinfo
    return options


def get_external_process_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def download_music(search_query: str, output_dir: str, ffmpeg_location: str | None, log) -> tuple[bool, str]:
    output_template = os.path.join(output_dir, "%(title)s.%(ext)s")
    yt_dlp_path = get_yt_dlp_executable()
    if not yt_dlp_path:
        return (
            False,
            "yt-dlp.exe nao foi encontrado. Reinstale o app ou instale o yt-dlp no ambiente.",
        )

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    cookie_file = get_cookie_file_path()
    using_cookie_file = bool(cookie_file)

    last_error_text = ""
    log(f"  URL/processamento: {search_query}")
    log(f"  Pasta de saida: {output_path}")

    for attempt, search_term in enumerate(build_youtube_search_terms(search_query), start=1):
        display_term = search_term.replace("ytsearch1:", "", 1)
        cookie_modes = [cookie_file] if cookie_file else [None]
        if cookie_file:
            cookie_modes.append(None)

        for cookie_mode_index, cookie_path in enumerate(cookie_modes, start=1):
            extractor_args = None
            command = [
                str(yt_dlp_path),
                "--default-search",
                "ytsearch1",
                "--format",
                "bestaudio/best",
                "--check-formats",
                "--extract-audio",
                "--audio-format",
                "mp3",
                "--audio-quality",
                "192K",
                "--no-playlist",
                "--no-warnings",
                "--windows-filenames",
                "--output",
                output_template,
            ]
            if extractor_args:
                command.extend(["--extractor-args", extractor_args])
            if ffmpeg_location:
                command.extend(["--ffmpeg-location", ffmpeg_location])
            if cookie_path:
                command.extend(["--cookies", str(cookie_path)])
            command.append(search_term)

            safe_command = " ".join(f'"{part}"' if " " in part else part for part in command)
            log(f"  Busca {attempt}: {display_term}")
            if cookie_file and cookie_mode_index == 2:
                log("  Repetindo sem cookies porque o YouTube nao entregou formato valido com cookies.")
            log(f"  Comando externo: {safe_command}")

            try:
                result = subprocess.run(
                    command,
                    cwd=str(output_path),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    shell=False,
                    env=get_external_process_env(),
                    timeout=1800,
                    **get_external_process_options(),
                )
            except FileNotFoundError:
                return False, f"Executavel nao encontrado: {yt_dlp_path}"
            except PermissionError as error:
                return False, f"Sem permissao para executar ou gravar em {output_path}: {error}"
            except subprocess.TimeoutExpired as error:
                return False, f"Timeout no yt-dlp apos {error.timeout} segundos."

            combined_output = "\n".join(
                part.strip() for part in [result.stdout, result.stderr] if part and part.strip()
            )
            if combined_output:
                for line in combined_output.splitlines()[-18:]:
                    log(f"    {line}")

            if result.returncode == 0:
                log("    Download concluido e convertido para MP3.")
                return True, "OK"

            last_error_text = combined_output or f"yt-dlp retornou codigo {result.returncode} sem mensagem."
            log(f"    Falha na etapa yt-dlp/FFmpeg. Codigo: {result.returncode}")
            log(f"    Erro real: {shorten_error(last_error_text)}")

            if (
                cookie_path
                and cookie_file
                and should_retry_without_cookies(last_error_text)
                and cookie_mode_index < len(cookie_modes)
            ):
                continue

            if (
                not cookie_path
                and cookie_file
                and should_retry_with_cookies(last_error_text)
            ):
                log("    O YouTube pediu cookies, mas a tentativa com cookies ja foi feita.")

            if "Sign in to confirm" in last_error_text or "not a bot" in last_error_text:
                return False, summarize_download_error(last_error_text, using_cookie_file)
            if (
                "Could not copy Chrome cookie database" in last_error_text
                or "Failed to decrypt with DPAPI" in last_error_text
            ):
                return False, summarize_download_error(last_error_text, using_cookie_file)

            log("    Tentando busca alternativa...")

    return False, summarize_download_error(last_error_text, using_cookie_file)


class SplashScreen(customtkinter.CTk):
    def __init__(self) -> None:
        super().__init__()

        self.geometry("400x250")
        self.overrideredirect(True)
        self.configure(fg_color=SPLASH_BG)
        self.attributes("-alpha", 0.0)
        self.center_window(400, 250)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        self.title_label = customtkinter.CTkLabel(
            self,
            text=APP_NAME,
            font=customtkinter.CTkFont(size=28, weight="bold"),
            text_color=GOLD,
        )
        self.title_label.grid(row=1, column=0, padx=36, pady=(20, 6), sticky="ew")

        self.subtitle_label = customtkinter.CTkLabel(
            self,
            text="Preparando sua biblioteca offline",
            font=customtkinter.CTkFont(size=13),
            text_color=MUTED_TEXT,
        )
        self.subtitle_label.grid(row=2, column=0, padx=36, pady=(0, 24), sticky="ew")

        self.progress_bar = customtkinter.CTkProgressBar(
            self,
            width=260,
            height=10,
            mode="indeterminate",
            progress_color=GOLD,
        )
        self.progress_bar.grid(row=3, column=0, padx=70, pady=(0, 24), sticky="ew")
        self.progress_bar.start()

        self.fade_in()

    def center_window(self, width: int, height: int) -> None:
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = int((screen_width - width) / 2)
        y = int((screen_height - height) / 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def fade_in(self, alpha: float = 0.0) -> None:
        next_alpha = min(alpha + 0.05, 1.0)
        self.attributes("-alpha", next_alpha)
        if next_alpha < 1.0:
            self.after(25, lambda: self.fade_in(next_alpha))


class BibliotecaOfflineApp(customtkinter.CTk):
    def __init__(self) -> None:
        self.configure_windows_app_id()
        super().__init__()

        self.configure_window_icon()
        self.title(APP_NAME)
        self.geometry("920x720")
        self.minsize(760, 640)

        self.log_queue: queue.Queue[tuple[str, bool]] = queue.Queue()
        self.worker_thread: threading.Thread | None = None
        self.destination_root = get_default_destination_root()
        self.last_output_dir: Path | None = None
        self.cancel_requested = False
        self.log_file_path = get_log_file_path()
        self.show_technical_log_var = tk.BooleanVar(value=False)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(10, weight=1)

        self.title_label = customtkinter.CTkLabel(
            self,
            text=APP_NAME,
            font=customtkinter.CTkFont(size=26, weight="bold"),
        )
        self.title_label.grid(row=0, column=0, padx=28, pady=(28, 8), sticky="ew")

        self.url_entry = customtkinter.CTkEntry(
            self,
            height=44,
            placeholder_text="Cole aqui a URL publica da playlist do Spotify",
            font=customtkinter.CTkFont(size=14),
            border_color=GOLD,
        )
        self.url_entry.grid(row=1, column=0, padx=36, pady=(10, 14), sticky="ew")

        self.playlist_label = customtkinter.CTkLabel(
            self,
            text="Playlist:\n-",
            font=customtkinter.CTkFont(size=14, weight="bold"),
            text_color="#d7d7d7",
            justify="left",
            anchor="w",
        )
        self.playlist_label.grid(row=2, column=0, padx=36, pady=(0, 12), sticky="ew")

        self.destination_frame = customtkinter.CTkFrame(self, fg_color="transparent")
        self.destination_frame.grid(row=3, column=0, padx=36, pady=(0, 12), sticky="ew")
        self.destination_frame.grid_columnconfigure(0, weight=1)

        self.destination_entry = customtkinter.CTkEntry(
            self.destination_frame,
            height=38,
            font=customtkinter.CTkFont(size=13),
            border_color=GOLD,
        )
        self.destination_entry.grid(row=0, column=0, padx=(0, 10), sticky="ew")
        self.destination_entry.insert(0, str(self.destination_root))

        self.choose_folder_button = customtkinter.CTkButton(
            self.destination_frame,
            text="Escolher Pasta",
            width=140,
            height=38,
            command=self.choose_destination_folder,
            fg_color=GOLD,
            hover_color=GOLD_HOVER,
            text_color="#111111",
        )
        self.choose_folder_button.grid(row=0, column=1)

        self.cookie_status_frame = customtkinter.CTkFrame(self, fg_color="transparent")
        self.cookie_status_frame.grid(row=4, column=0, padx=36, pady=(0, 12), sticky="ew")
        self.cookie_status_frame.grid_columnconfigure(1, weight=1)

        self.cookie_status_light = customtkinter.CTkFrame(
            self.cookie_status_frame,
            width=12,
            height=12,
            corner_radius=6,
            fg_color=COOKIE_MISSING,
        )
        self.cookie_status_light.grid(row=0, column=0, padx=(0, 8), pady=4)
        self.cookie_status_light.grid_propagate(False)

        self.cookie_status_label = customtkinter.CTkLabel(
            self.cookie_status_frame,
            text="cookies nao detectados",
            font=customtkinter.CTkFont(size=12, weight="bold"),
            text_color=COOKIE_MISSING,
        )
        self.cookie_status_label.grid(row=0, column=1, sticky="w")

        self.open_cookie_folder_button = customtkinter.CTkButton(
            self.cookie_status_frame,
            text="Abrir pasta",
            width=96,
            height=30,
            command=self.open_cookie_folder,
        )
        self.open_cookie_folder_button.grid(row=0, column=2, padx=(10, 8))

        self.cookie_help_button = customtkinter.CTkButton(
            self.cookie_status_frame,
            text="Ajuda cookies",
            width=112,
            height=30,
            command=self.show_cookie_help_window,
        )
        self.cookie_help_button.grid(row=0, column=3)

        self.action_frame = customtkinter.CTkFrame(self, fg_color="transparent")
        self.action_frame.grid(row=5, column=0, padx=36, pady=(0, 12))

        self.download_button = customtkinter.CTkButton(
            self.action_frame,
            text="Iniciar Download",
            height=44,
            width=170,
            font=customtkinter.CTkFont(size=15, weight="bold"),
            command=self.start_download,
            fg_color=GOLD,
            hover_color=GOLD_HOVER,
            text_color="#111111",
        )
        self.download_button.grid(row=0, column=0, padx=(0, 10))

        self.cancel_button = customtkinter.CTkButton(
            self.action_frame,
            text="Cancelar",
            height=44,
            width=130,
            font=customtkinter.CTkFont(size=15, weight="bold"),
            command=self.request_cancel,
            state="disabled",
            fg_color="#7f1d1d",
            hover_color="#991b1b",
        )
        self.cancel_button.grid(row=0, column=1, padx=(0, 10))

        self.open_folder_button = customtkinter.CTkButton(
            self.action_frame,
            text="Abrir Pasta Final",
            height=44,
            width=170,
            font=customtkinter.CTkFont(size=15, weight="bold"),
            command=self.open_last_output_folder,
            state="disabled",
        )
        self.open_folder_button.grid(row=0, column=2)

        self.progress_frame = customtkinter.CTkFrame(self, fg_color="transparent")
        self.progress_frame.grid(row=6, column=0, padx=36, pady=(0, 14), sticky="ew")
        self.progress_frame.grid_columnconfigure(0, weight=1)

        self.progress_bar = customtkinter.CTkProgressBar(
            self.progress_frame,
            height=12,
            progress_color=GOLD,
        )
        self.progress_bar.grid(row=0, column=0, sticky="ew")
        self.progress_bar.set(0)

        self.progress_label = customtkinter.CTkLabel(
            self.progress_frame,
            text="Progresso geral: 0%",
            width=140,
        )
        self.progress_label.grid(row=0, column=1, padx=(12, 0))

        self.current_track_frame = customtkinter.CTkFrame(self, fg_color="transparent")
        self.current_track_frame.grid(row=7, column=0, padx=36, pady=(0, 10), sticky="ew")
        self.current_track_frame.grid_columnconfigure(0, weight=1)

        self.current_track_title = customtkinter.CTkLabel(
            self.current_track_frame,
            text="Baixando agora:",
            font=customtkinter.CTkFont(size=13, weight="bold"),
            text_color=GOLD,
            anchor="w",
        )
        self.current_track_title.grid(row=0, column=0, sticky="ew")

        self.current_track_label = customtkinter.CTkLabel(
            self.current_track_frame,
            text="Nenhum download em andamento.",
            font=customtkinter.CTkFont(size=13),
            text_color="#d7d7d7",
            anchor="w",
        )
        self.current_track_label.grid(row=1, column=0, sticky="ew")

        self.summary_label = customtkinter.CTkLabel(
            self,
            text="Resumo: aguardando inicio.",
            font=customtkinter.CTkFont(size=13),
            text_color=MUTED_TEXT,
            anchor="w",
            justify="left",
        )
        self.summary_label.grid(row=8, column=0, padx=36, pady=(0, 12), sticky="ew")

        self.log_options_frame = customtkinter.CTkFrame(self, fg_color="transparent")
        self.log_options_frame.grid(row=9, column=0, padx=36, pady=(0, 8), sticky="ew")

        self.technical_log_checkbox = customtkinter.CTkCheckBox(
            self.log_options_frame,
            text="Mostrar log técnico",
            variable=self.show_technical_log_var,
            onvalue=True,
            offvalue=False,
        )
        self.technical_log_checkbox.grid(row=0, column=0, sticky="w")

        self.log_textbox = customtkinter.CTkTextbox(
            self,
            wrap="word",
            font=customtkinter.CTkFont(family="Consolas", size=13),
            fg_color=DARK_PANEL,
            border_color=GOLD,
            border_width=1,
        )
        self.log_textbox.grid(row=10, column=0, padx=24, pady=(0, 24), sticky="nsew")
        self.log_textbox.insert(
            "end",
            "Pronto. Cole a URL da playlist e clique em Iniciar Download.\n",
        )
        self.log_textbox.configure(state="disabled")

        self.footer_frame = customtkinter.CTkFrame(self, fg_color="transparent")
        self.footer_frame.grid(row=11, column=0, padx=24, pady=(0, 12), sticky="ew")
        self.footer_frame.grid_columnconfigure(0, weight=1)

        self.footer_label = customtkinter.CTkLabel(
            self.footer_frame,
            text=f"{APP_NAME} v{APP_VERSION} | (c) 2026 {APP_AUTHOR} | uso pessoal",
            font=customtkinter.CTkFont(size=11),
            text_color="#9f9f9f",
        )
        self.footer_label.grid(row=0, column=0, sticky="w")

        self.about_button = customtkinter.CTkButton(
            self.footer_frame,
            text="Sobre",
            width=72,
            height=28,
            command=self.show_about_window,
        )
        self.about_button.grid(row=0, column=1, sticky="e")

        self.update_cookie_status()
        self.after(100, self.process_log_queue)
        self.after(2000, self.refresh_cookie_status)

    def configure_windows_app_id(self) -> None:
        try:
            app_id = f"EdilsonCharneski.BibliotecaOffline.{APP_VERSION}"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        except Exception:
            pass

    def configure_window_icon(self) -> None:
        try:
            icon_path = ensure_icon_file()
            if icon_path.is_file() and icon_path.stat().st_size > 0:
                self.iconbitmap(str(icon_path))
        except Exception:
            pass

    def append_log(self, message: str, technical: bool = False) -> None:
        try:
            self.log_file_path.parent.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with self.log_file_path.open("a", encoding="utf-8") as log_file:
                log_file.write(f"[{timestamp}] {message}\n")
        except OSError:
            pass
        self.log_queue.put((message, technical))

    def append_technical_log(self, message: str) -> None:
        self.append_log(message, technical=True)

    def update_cookie_status(self) -> None:
        migrate_legacy_cookie_file()
        cookie_file = get_cookie_file_path()
        if cookie_file:
            self.cookie_status_light.configure(fg_color=COOKIE_OK)
            self.cookie_status_label.configure(
                text="cookies detectados",
                text_color=COOKIE_OK,
            )
        else:
            self.cookie_status_light.configure(fg_color=COOKIE_MISSING)
            self.cookie_status_label.configure(
                text="cookies nao detectados",
                text_color=COOKIE_MISSING,
            )

    def refresh_cookie_status(self) -> None:
        self.update_cookie_status()
        self.after(2000, self.refresh_cookie_status)

    def open_cookie_folder(self) -> None:
        cookie_folder = get_user_data_path()
        cookie_folder.mkdir(parents=True, exist_ok=True)
        os.startfile(cookie_folder)

    def show_cookie_help_window(self) -> None:
        help_window = customtkinter.CTkToplevel(self)
        help_window.title("Ajuda cookies")
        help_window.geometry("620x420")
        help_window.resizable(False, False)
        help_window.transient(self)
        help_window.grab_set()

        help_window.grid_columnconfigure(0, weight=1)

        title_label = customtkinter.CTkLabel(
            help_window,
            text="Como deixar os cookies prontos",
            font=customtkinter.CTkFont(size=21, weight="bold"),
        )
        title_label.grid(row=0, column=0, padx=24, pady=(24, 10), sticky="ew")

        steps_text = (
            "1. Clique em Instalar extensao e adicione a extensao ao Chrome.\n"
            "2. Abra o YouTube no Chrome e entre na sua conta.\n"
            "3. Clique no icone da extensao Get cookies.txt LOCALLY.\n"
            "4. Escolha exportar/baixar em formato Netscape.\n"
            "5. Renomeie o arquivo baixado para exatamente cookies.txt.\n"
            "6. Coloque esse arquivo na pasta aberta pelo botao Abrir pasta de cookies.\n\n"
            "Quando estiver certo, a luz desta tela fica verde e aparece cookies detectados."
        )
        steps_label = customtkinter.CTkLabel(
            help_window,
            text=steps_text,
            justify="left",
            wraplength=540,
            font=customtkinter.CTkFont(size=14),
        )
        steps_label.grid(row=1, column=0, padx=32, pady=(0, 18), sticky="w")

        expected_label = customtkinter.CTkLabel(
            help_window,
            text=f"Local esperado: {get_expected_cookie_file_path()}",
            justify="left",
            wraplength=540,
            font=customtkinter.CTkFont(size=12),
            text_color=MUTED_TEXT,
        )
        expected_label.grid(row=2, column=0, padx=32, pady=(0, 18), sticky="w")

        button_frame = customtkinter.CTkFrame(help_window, fg_color="transparent")
        button_frame.grid(row=3, column=0, padx=24, pady=(0, 24))

        youtube_button = customtkinter.CTkButton(
            button_frame,
            text="Instalar extensao",
            width=140,
            command=lambda: webbrowser.open(COOKIE_EXTENSION_URL),
        )
        youtube_button.grid(row=0, column=0, padx=(0, 10))

        youtube_button = customtkinter.CTkButton(
            button_frame,
            text="Abrir YouTube",
            width=120,
            command=lambda: webbrowser.open("https://www.youtube.com/"),
        )
        youtube_button.grid(row=0, column=1, padx=(0, 10))

        folder_button = customtkinter.CTkButton(
            button_frame,
            text="Abrir pasta",
            width=120,
            command=self.open_cookie_folder,
        )
        folder_button.grid(row=0, column=2, padx=(0, 10))

        close_button = customtkinter.CTkButton(
            button_frame,
            text="Fechar",
            width=100,
            command=help_window.destroy,
            fg_color=GOLD,
            hover_color=GOLD_HOVER,
            text_color="#111111",
        )
        close_button.grid(row=0, column=3)

    def show_about_window(self) -> None:
        about_window = customtkinter.CTkToplevel(self)
        about_window.title(f"Sobre o {APP_NAME}")
        about_window.geometry("520x300")
        about_window.resizable(False, False)
        about_window.transient(self)
        about_window.grab_set()

        about_window.grid_columnconfigure(0, weight=1)

        title_label = customtkinter.CTkLabel(
            about_window,
            text=f"{APP_NAME} v{APP_VERSION}",
            font=customtkinter.CTkFont(size=22, weight="bold"),
        )
        title_label.grid(row=0, column=0, padx=24, pady=(24, 8), sticky="ew")

        author_label = customtkinter.CTkLabel(
            about_window,
            text=f"Desenvolvido por {APP_AUTHOR}",
            font=customtkinter.CTkFont(size=14, weight="bold"),
        )
        author_label.grid(row=1, column=0, padx=24, pady=(0, 8), sticky="ew")

        copyright_label = customtkinter.CTkLabel(
            about_window,
            text=APP_COPYRIGHT,
            font=customtkinter.CTkFont(size=13),
        )
        copyright_label.grid(row=2, column=0, padx=24, pady=(0, 12), sticky="ew")

        usage_label = customtkinter.CTkLabel(
            about_window,
            text=APP_USAGE_NOTE,
            wraplength=440,
            justify="center",
            font=customtkinter.CTkFont(size=13),
        )
        usage_label.grid(row=3, column=0, padx=24, pady=(0, 18), sticky="ew")

        close_button = customtkinter.CTkButton(
            about_window,
            text="Fechar",
            width=110,
            command=about_window.destroy,
            fg_color=GOLD,
            hover_color=GOLD_HOVER,
            text_color="#111111",
        )
        close_button.grid(row=4, column=0, padx=24, pady=(0, 24))

    def choose_destination_folder(self) -> None:
        initial_dir = self.destination_root if self.destination_root.exists() else get_default_destination_root()
        selected_dir = filedialog.askdirectory(
            title="Escolha a pasta de destino",
            initialdir=str(initial_dir),
        )
        if not selected_dir:
            return

        self.destination_root = Path(selected_dir)
        self.destination_entry.delete(0, "end")
        self.destination_entry.insert(0, str(self.destination_root))
        self.append_log(f"Pasta base selecionada: {self.destination_root}")

    def open_last_output_folder(self) -> None:
        if not self.last_output_dir or not self.last_output_dir.exists():
            self.append_log("Nenhuma pasta final disponivel para abrir ainda.")
            return

        os.startfile(self.last_output_dir)

    def set_progress(self, completed: int, total: int) -> None:
        if total <= 0:
            ratio = 0
        else:
            ratio = completed / total

        percent = int(ratio * 100)
        self.after(0, lambda: self.progress_bar.set(ratio))
        self.after(
            0,
            lambda: self.progress_label.configure(
                text=f"Progresso geral: {percent}% ({completed}/{total})"
            ),
        )

    def set_current_track(self, track: str | None) -> None:
        text = track if track else "Nenhum download em andamento."
        self.after(0, lambda: self.current_track_label.configure(text=text))

    def set_playlist_name(self, playlist_name: str | None) -> None:
        text = playlist_name if playlist_name else "-"
        self.after(0, lambda: self.playlist_label.configure(text=f"Playlist:\n{text}"))

    def set_summary(
        self,
        status: str,
        total: int = 0,
        successes: int = 0,
        failures: int = 0,
        remaining: int = 0,
    ) -> None:
        if status in {"concluido", "cancelado"}:
            title = "Concluído" if status == "concluido" else "Cancelado"
            summary = (
                f"{title}\n"
                f"Total: {total}\n"
                f"Baixadas: {successes}\n"
                f"Falhas: {failures}"
            )
        elif status == "erro":
            summary = "Falhou\nVerifique as mensagens acima."
        else:
            summary = (
                f"Resumo: {status} | Total: {total} | "
                f"Baixadas: {successes} | Falhas: {failures} | Restantes: {remaining}"
            )
        self.after(0, lambda: self.summary_label.configure(text=summary))

    def set_controls_running(self, is_running: bool) -> None:
        state = "disabled" if is_running else "normal"
        self.download_button.configure(
            state=state,
            text="Baixando..." if is_running else "Iniciar Download",
        )
        self.cancel_button.configure(state="normal" if is_running else "disabled")
        self.choose_folder_button.configure(state=state)
        self.destination_entry.configure(state=state)

    def request_cancel(self) -> None:
        if not self.worker_thread or not self.worker_thread.is_alive():
            return

        self.cancel_requested = True
        self.cancel_button.configure(state="disabled", text="Cancelando...")
        self.append_log("Cancelamento solicitado. O app vai parar antes da proxima musica.")

    def process_log_queue(self) -> None:
        while not self.log_queue.empty():
            message, technical = self.log_queue.get_nowait()
            if technical and not self.show_technical_log_var.get():
                continue
            self.log_textbox.configure(state="normal")
            self.log_textbox.insert("end", message + "\n")
            self.log_textbox.see("end")
            self.log_textbox.configure(state="disabled")

        self.after(100, self.process_log_queue)

    def start_download(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            self.append_log("Ja existe um download em andamento.")
            return

        playlist_url = self.url_entry.get().strip()
        if not playlist_url:
            self.append_log("Informe a URL da playlist antes de iniciar.")
            return

        destination_text = self.destination_entry.get().strip()
        if not destination_text:
            self.append_log("Informe uma pasta de destino antes de iniciar.")
            return

        self.destination_root = normalize_destination_path(destination_text)
        self.destination_entry.delete(0, "end")
        self.destination_entry.insert(0, str(self.destination_root))
        self.last_output_dir = None
        self.cancel_requested = False
        self.open_folder_button.configure(state="disabled")
        self.set_progress(0, 0)
        self.set_current_track(None)
        self.set_playlist_name(None)
        self.set_summary("em andamento")
        self.set_controls_running(True)
        self.worker_thread = threading.Thread(
            target=self.run_download_flow,
            args=(playlist_url, self.destination_root),
            daemon=True,
        )
        self.worker_thread.start()

    def run_download_flow(self, playlist_url: str, destination_root: Path) -> None:
        try:
            self.append_technical_log("=" * 70)
            self.append_log("Buscando playlist...")
            self.append_technical_log(f"Iniciando processo no {APP_NAME} v{APP_VERSION}...")
            self.append_technical_log(f"Log completo: {self.log_file_path}")
            self.append_technical_log(f"URL processada: {playlist_url}")
            migrate_legacy_cookie_file(self.append_technical_log)

            yt_dlp_path = get_yt_dlp_executable()
            if yt_dlp_path:
                self.append_technical_log(f"yt-dlp localizado em: {yt_dlp_path}")
            else:
                self.append_log("yt-dlp.exe nao foi encontrado.")

            ffmpeg_location = get_ffmpeg_location()
            if ffmpeg_location:
                self.append_technical_log(f"FFmpeg localizado em: {ffmpeg_location}")
            else:
                self.append_log(
                    "FFmpeg nao foi encontrado junto ao app. Tentando usar o PATH do sistema."
                )

            expected_cookie_file = get_expected_cookie_file_path()
            cookie_file = get_cookie_file_path()
            if cookie_file:
                self.append_technical_log(f"cookies.txt encontrado: {cookie_file}")
            else:
                self.append_technical_log(
                    f"cookies.txt nao encontrado ou vazio em: {expected_cookie_file}"
                )
                self.append_technical_log(
                    "O app tentara baixar sem cookies. Se o YouTube bloquear por login/anti-bot, coloque cookies.txt nesse local."
                )

            playlist_name, tracks = extract_playlist_data(playlist_url, self.append_technical_log)
            if not tracks:
                self.append_log("A playlist esta vazia.")
                return

            self.set_playlist_name(playlist_name)
            self.append_log(f"Playlist:\n{playlist_name}")
            self.append_log(f"{len(tracks)} musicas encontradas.")

            output_dir = destination_root / playlist_name
            output_dir.mkdir(parents=True, exist_ok=True)
            self.last_output_dir = output_dir
            self.append_technical_log(f"Preparando pasta da playlist: {output_dir}")
            self.append_technical_log("-" * 70)

            successes = 0
            failures = []
            self.set_progress(0, len(tracks))
            self.set_summary("em andamento", len(tracks), successes, len(failures), len(tracks))

            for index, track in enumerate(tracks, start=1):
                if self.cancel_requested:
                    remaining = len(tracks) - index + 1
                    self.append_log("Download cancelado pelo usuario.")
                    self.append_log(f"Musicas restantes nao processadas: {remaining}")
                    break

                self.set_current_track(track)
                self.append_log(f"[{index}/{len(tracks)}] Buscando música...")
                self.append_log("Resultado encontrado.")
                self.append_log("Baixando...")
                self.append_log("Convertendo para MP3...")
                success, message = download_music(
                    track,
                    str(output_dir),
                    ffmpeg_location,
                    self.append_technical_log,
                )

                if success:
                    successes += 1
                    self.append_log("Concluído.")
                else:
                    failures.append((track, message))
                    self.append_log(f"Falhou: {message}")

                self.append_technical_log("")
                self.set_progress(index, len(tracks))
                remaining = len(tracks) - index
                self.set_summary(
                    "em andamento",
                    len(tracks),
                    successes,
                    len(failures),
                    remaining,
                )

            canceled = self.cancel_requested
            completed = successes + len(failures)
            remaining = max(len(tracks) - completed, 0)
            self.append_technical_log("-" * 70)
            self.append_technical_log("RELATORIO FINAL")
            self.append_log(f"Total na playlist    : {len(tracks)}")
            self.append_log(f"Baixadas com sucesso : {successes}")
            self.append_log(f"Falhas               : {len(failures)}")
            if canceled:
                self.append_log(f"Canceladas/restantes : {remaining}")

            if failures:
                self.append_log("")
                self.append_log("Musicas que falharam:")
                for track, error in failures:
                    self.append_log(f"- {track} ({error})")

            self.append_technical_log("=" * 70)
            final_status = "cancelado" if canceled else "concluido"
            self.set_current_track(None)
            self.set_summary(final_status, len(tracks), successes, len(failures), remaining)
            self.after(0, lambda: self.open_folder_button.configure(state="normal"))
        except requests.exceptions.RequestException as error:
            self.append_log(f"ERRO DE CONEXAO: {error}")
            self.set_summary("erro")
        except ValueError as error:
            self.append_log(f"ERRO: {error}")
            self.set_summary("erro")
        except Exception as error:
            self.append_log(f"ERRO INESPERADO: {type(error).__name__}: {error}")
            self.set_summary("erro")
        finally:
            self.set_current_track(None)
            self.after(0, lambda: self.set_controls_running(False))
            self.after(0, lambda: self.cancel_button.configure(text="Cancelar"))


def main() -> None:
    def close_splash() -> None:
        splash.destroy()

    splash = SplashScreen()
    splash.after(3000, close_splash)
    splash.mainloop()

    app = BibliotecaOfflineApp()
    app.mainloop()


if __name__ == "__main__":
    main()
