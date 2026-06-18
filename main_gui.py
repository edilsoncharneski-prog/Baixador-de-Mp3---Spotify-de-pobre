import base64
import ctypes
import json
import os
import queue
import re
import shutil
import sys
import threading
import tkinter.filedialog as filedialog
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

import customtkinter
import requests
import yt_dlp
from bs4 import BeautifulSoup
from icon_data import ICON_DATA_BASE64


OUTPUT_DIR = "musicas_pendrive"
APP_NAME = "BaixadorSpotifyMP3"
APP_VERSION = "1.0"
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
    return Path(__file__).resolve().parent


def get_external_base_path() -> Path:
    """Retorna a pasta visivel do app, onde o usuario pode colocar arquivos auxiliares."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_expected_cookie_file_path() -> Path:
    return get_external_base_path() / "cookies.txt"


def get_cookie_file_path() -> Path | None:
    cookie_file = get_expected_cookie_file_path()
    if cookie_file.is_file() and cookie_file.stat().st_size > 0:
        return cookie_file
    return None


def ensure_icon_file() -> Path:
    icon_path = get_app_base_path() / "icon.ico"
    if icon_path.is_file() and icon_path.stat().st_size > 0:
        return icon_path

    icon_path.write_bytes(base64.b64decode(ICON_DATA_BASE64))
    return icon_path


def get_js_runtime_options(log=None) -> dict:
    if not shutil.which("node"):
        if log:
            log("  Node.js nao encontrado. Alguns videos podem falhar no challenge do YouTube.")
        return {}

    if log:
        log("  Node.js detectado. Ativando solver JS do YouTube.")
    return {
        "js_runtimes": {"node": {}},
        "remote_components": ["ejs:github"],
    }


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
    track_name, artist_name = split_track_search_query(search_query)
    terms = []

    if track_name and artist_name:
        terms.append(f"ytsearch1:{track_name} {artist_name}")
    if track_name:
        terms.append(f"ytsearch1:{track_name}")
    terms.append(f"ytsearch1:{search_query.replace(' - ', ' ')}")

    unique_terms = []
    for term in terms:
        if term not in unique_terms:
            unique_terms.append(term)

    return unique_terms


def summarize_download_error(error: Exception, used_cookie_file: bool = False) -> str:
    error_text = str(error)
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


def shorten_error(error: Exception) -> str:
    error_text = re.sub(r"\s+", " ", str(error)).strip()
    error_text = error_text.replace("ERROR: ", "")
    return error_text[:260]


def download_music(search_query: str, output_dir: str, ffmpeg_location: str | None, log) -> tuple[bool, str]:
    output_template = os.path.join(output_dir, "%(title)s.%(ext)s")

    def progress_hook(status: dict) -> None:
        if status.get("status") == "downloading":
            percent = status.get("_percent_str", "").strip()
            speed = status.get("_speed_str", "").strip()
            if percent:
                log(f"    Baixando: {percent} {speed}".rstrip())
        elif status.get("status") == "finished":
            log("    Download concluido. Convertendo para MP3...")

    ydl_opts = {
        "default_search": "ytsearch1",
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "progress_hooks": [progress_hook],
    }

    if ffmpeg_location:
        ydl_opts["ffmpeg_location"] = ffmpeg_location
    ydl_opts.update(get_js_runtime_options(log))

    cookie_file = get_cookie_file_path()
    using_cookie_file = bool(cookie_file)
    if cookie_file:
        ydl_opts["cookiefile"] = str(cookie_file)

    last_download_error = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            for attempt, search_term in enumerate(build_youtube_search_terms(search_query), start=1):
                try:
                    display_term = search_term.replace("ytsearch1:", "", 1)
                    log(f"  Busca {attempt}: {display_term}")
                    ydl.download([search_term])
                    return True, "OK"
                except yt_dlp.utils.DownloadError as error:
                    last_download_error = error
                    if "Sign in to confirm" in str(error) or "not a bot" in str(error):
                        return False, summarize_download_error(error, using_cookie_file)
                    if (
                        "Could not copy Chrome cookie database" in str(error)
                        or "Failed to decrypt with DPAPI" in str(error)
                    ):
                        return False, summarize_download_error(error, using_cookie_file)
                    log(f"    Erro do yt-dlp: {shorten_error(error)}")
                    log("    Resultado nao encontrado. Tentando busca alternativa...")

        if last_download_error:
            raise last_download_error
        return True, "OK"
    except yt_dlp.utils.DownloadError as error:
        return False, summarize_download_error(error, using_cookie_file)
    except yt_dlp.utils.PostProcessingError:
        return False, "Falha na conversao para MP3. Verifique o FFmpeg."
    except Exception as error:
        return False, f"Erro inesperado: {type(error).__name__}: {error}"


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
            text="SPOTIFY -> MP3",
            font=customtkinter.CTkFont(size=28, weight="bold"),
            text_color=GOLD,
        )
        self.title_label.grid(row=1, column=0, padx=36, pady=(20, 6), sticky="ew")

        self.subtitle_label = customtkinter.CTkLabel(
            self,
            text="Preparando seu baixador de musicas",
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


class SpotifyDownloaderApp(customtkinter.CTk):
    def __init__(self) -> None:
        self.configure_windows_app_id()
        super().__init__()

        self.configure_window_icon()
        self.title("Spotify Playlist -> MP3")
        self.geometry("920x720")
        self.minsize(760, 640)

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.worker_thread: threading.Thread | None = None
        self.destination_root = Path.cwd() / OUTPUT_DIR
        self.last_output_dir: Path | None = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(6, weight=1)

        self.title_label = customtkinter.CTkLabel(
            self,
            text="Spotify Playlist -> MP3",
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

        self.destination_frame = customtkinter.CTkFrame(self, fg_color="transparent")
        self.destination_frame.grid(row=2, column=0, padx=36, pady=(0, 12), sticky="ew")
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
        self.cookie_status_frame.grid(row=3, column=0, padx=36, pady=(0, 12), sticky="ew")
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
        self.action_frame.grid(row=4, column=0, padx=36, pady=(0, 12))

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

        self.open_folder_button = customtkinter.CTkButton(
            self.action_frame,
            text="Abrir Pasta Final",
            height=44,
            width=170,
            font=customtkinter.CTkFont(size=15, weight="bold"),
            command=self.open_last_output_folder,
            state="disabled",
        )
        self.open_folder_button.grid(row=0, column=1)

        self.progress_frame = customtkinter.CTkFrame(self, fg_color="transparent")
        self.progress_frame.grid(row=5, column=0, padx=36, pady=(0, 14), sticky="ew")
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

        self.log_textbox = customtkinter.CTkTextbox(
            self,
            wrap="word",
            font=customtkinter.CTkFont(family="Consolas", size=13),
            fg_color=DARK_PANEL,
            border_color=GOLD,
            border_width=1,
        )
        self.log_textbox.grid(row=6, column=0, padx=24, pady=(0, 24), sticky="nsew")
        self.log_textbox.insert(
            "end",
            "Pronto. Cole a URL da playlist e clique em Iniciar Download.\n",
        )
        self.log_textbox.configure(state="disabled")

        self.footer_frame = customtkinter.CTkFrame(self, fg_color="transparent")
        self.footer_frame.grid(row=7, column=0, padx=24, pady=(0, 12), sticky="ew")
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
            app_id = "EdilsonCharneski.BaixadorSpotifyMP3.1.0"
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

    def append_log(self, message: str) -> None:
        self.log_queue.put(message)

    def update_cookie_status(self) -> None:
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
        cookie_folder = get_external_base_path()
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
            "6. Coloque esse arquivo na pasta aberta pelo botao Abrir pasta.\n\n"
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
        initial_dir = self.destination_root if self.destination_root.exists() else Path.cwd()
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

    def set_controls_running(self, is_running: bool) -> None:
        state = "disabled" if is_running else "normal"
        self.download_button.configure(
            state=state,
            text="Baixando..." if is_running else "Iniciar Download",
        )
        self.choose_folder_button.configure(state=state)
        self.destination_entry.configure(state=state)

    def process_log_queue(self) -> None:
        while not self.log_queue.empty():
            message = self.log_queue.get_nowait()
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

        self.destination_root = Path(destination_text)
        self.last_output_dir = None
        self.open_folder_button.configure(state="disabled")
        self.set_progress(0, 0)
        self.set_controls_running(True)
        self.worker_thread = threading.Thread(
            target=self.run_download_flow,
            args=(playlist_url, self.destination_root),
            daemon=True,
        )
        self.worker_thread.start()

    def run_download_flow(self, playlist_url: str, destination_root: Path) -> None:
        try:
            self.append_log("=" * 70)
            self.append_log("Iniciando processo...")

            ffmpeg_location = get_ffmpeg_location()
            if ffmpeg_location:
                self.append_log(f"FFmpeg localizado em: {ffmpeg_location}")
            else:
                self.append_log(
                    "FFmpeg nao foi encontrado junto ao app. Tentando usar o PATH do sistema."
                )

            expected_cookie_file = get_expected_cookie_file_path()
            cookie_file = get_cookie_file_path()
            if cookie_file:
                self.append_log(f"cookies.txt encontrado: {cookie_file}")
            else:
                self.append_log(
                    f"cookies.txt nao encontrado ou vazio em: {expected_cookie_file}"
                )
                self.append_log(
                    "O app nao vai tentar ler cookies do Chrome. Downloads bloqueados pelo YouTube podem falhar."
                )

            playlist_name, tracks = extract_playlist_data(playlist_url, self.append_log)
            if not tracks:
                self.append_log("A playlist esta vazia.")
                return

            self.append_log(f"Playlist identificada: {playlist_name}")
            self.append_log(f"{len(tracks)} musicas encontradas.")

            output_dir = destination_root / playlist_name
            output_dir.mkdir(parents=True, exist_ok=True)
            self.last_output_dir = output_dir
            self.append_log(f"Preparando pasta da playlist: {output_dir}")
            self.append_log("-" * 70)

            successes = 0
            failures = []
            self.set_progress(0, len(tracks))

            for index, track in enumerate(tracks, start=1):
                self.append_log(f"[{index}/{len(tracks)}]")
                success, message = download_music(
                    track,
                    str(output_dir),
                    ffmpeg_location,
                    self.append_log,
                )

                if success:
                    successes += 1
                    self.append_log("  OK: concluido")
                else:
                    failures.append((track, message))
                    self.append_log(f"  FALHOU: {message}")

                self.append_log("")
                self.set_progress(index, len(tracks))

            self.append_log("-" * 70)
            self.append_log("RELATORIO FINAL")
            self.append_log(f"Total na playlist    : {len(tracks)}")
            self.append_log(f"Baixadas com sucesso : {successes}")
            self.append_log(f"Falhas               : {len(failures)}")

            if failures:
                self.append_log("")
                self.append_log("Musicas que falharam:")
                for track, error in failures:
                    self.append_log(f"- {track} ({error})")

            self.append_log("=" * 70)
            self.after(0, lambda: self.open_folder_button.configure(state="normal"))
        except requests.exceptions.RequestException as error:
            self.append_log(f"ERRO DE CONEXAO: {error}")
        except ValueError as error:
            self.append_log(f"ERRO: {error}")
        except Exception as error:
            self.append_log(f"ERRO INESPERADO: {type(error).__name__}: {error}")
        finally:
            self.after(0, lambda: self.set_controls_running(False))


if __name__ == "__main__":
    def launch_main() -> None:
        splash.destroy()
        app = SpotifyDownloaderApp()
        app.mainloop()


    splash = SplashScreen()
    splash.after(3000, launch_main)
    splash.mainloop()
