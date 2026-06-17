import json
import os
import queue
import re
import sys
import threading
from pathlib import Path
from urllib.parse import urlparse

import customtkinter
import requests
import yt_dlp
from bs4 import BeautifulSoup


OUTPUT_DIR = "musicas_pendrive"
GOLD = "#d4af37"
GOLD_HOVER = "#b8941f"
DARK_PANEL = "#1f1f1f"
INVALID_WINDOWS_CHARS = r'[\\/:*?"<>|]'


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


def build_embed_playlist_url(playlist_url: str) -> str:
    parsed_url = urlparse(playlist_url)
    path_parts = [part for part in parsed_url.path.split("/") if part]

    if parsed_url.netloc != "open.spotify.com":
        raise ValueError(
            "URL invalida. Use um link publico de playlist do Spotify."
        )

    if path_parts[:2] == ["embed", "playlist"] and len(path_parts) >= 3:
        playlist_id = path_parts[2]
    elif path_parts[:1] == ["playlist"] and len(path_parts) >= 2:
        playlist_id = path_parts[1]
    elif len(path_parts) >= 3 and path_parts[1] == "playlist":
        playlist_id = path_parts[2]
    else:
        raise ValueError(
            "URL invalida. Use um link publico de playlist do Spotify."
        )

    return f"https://open.spotify.com/embed/playlist/{playlist_id}"


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


def extract_playlist_data(playlist_url: str, log) -> tuple[str, list[str]]:
    if not re.match(r"https?://open\.spotify\.com/", playlist_url):
        raise ValueError(
            "URL invalida. Use um link publico de playlist do Spotify."
        )

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

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            log(f"  Buscando: {search_query}")
            ydl.download([search_query])
        return True, "OK"
    except yt_dlp.utils.DownloadError:
        return False, "Video nao encontrado ou bloqueado no YouTube."
    except yt_dlp.utils.PostProcessingError:
        return False, "Falha na conversao para MP3. Verifique o FFmpeg."
    except Exception as error:
        return False, f"Erro inesperado: {type(error).__name__}: {error}"


class SpotifyDownloaderApp(customtkinter.CTk):
    def __init__(self) -> None:
        super().__init__()

        self.title("Spotify Playlist -> MP3")
        self.geometry("880x620")
        self.minsize(720, 520)

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.worker_thread: threading.Thread | None = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

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

        self.download_button = customtkinter.CTkButton(
            self,
            text="Iniciar Download",
            height=44,
            font=customtkinter.CTkFont(size=15, weight="bold"),
            command=self.start_download,
            fg_color=GOLD,
            hover_color=GOLD_HOVER,
            text_color="#111111",
        )
        self.download_button.grid(row=2, column=0, padx=36, pady=(0, 18))

        self.log_textbox = customtkinter.CTkTextbox(
            self,
            wrap="word",
            font=customtkinter.CTkFont(family="Consolas", size=13),
            fg_color=DARK_PANEL,
            border_color=GOLD,
            border_width=1,
        )
        self.log_textbox.grid(row=3, column=0, padx=24, pady=(0, 24), sticky="nsew")
        self.log_textbox.insert(
            "end",
            "Pronto. Cole a URL da playlist e clique em Iniciar Download.\n",
        )
        self.log_textbox.configure(state="disabled")

        self.after(100, self.process_log_queue)

    def append_log(self, message: str) -> None:
        self.log_queue.put(message)

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

        self.download_button.configure(state="disabled", text="Baixando...")
        self.worker_thread = threading.Thread(
            target=self.run_download_flow,
            args=(playlist_url,),
            daemon=True,
        )
        self.worker_thread.start()

    def run_download_flow(self, playlist_url: str) -> None:
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

            playlist_name, tracks = extract_playlist_data(playlist_url, self.append_log)
            if not tracks:
                self.append_log("A playlist esta vazia.")
                return

            self.append_log(f"Playlist identificada: {playlist_name}")
            self.append_log(f"{len(tracks)} musicas encontradas.")

            output_dir = Path.cwd() / OUTPUT_DIR / playlist_name
            output_dir.mkdir(parents=True, exist_ok=True)
            self.append_log(f"Preparando pasta da playlist: {output_dir}")
            self.append_log("-" * 70)

            successes = 0
            failures = []

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
        except requests.exceptions.RequestException as error:
            self.append_log(f"ERRO DE CONEXAO: {error}")
        except ValueError as error:
            self.append_log(f"ERRO: {error}")
        except Exception as error:
            self.append_log(f"ERRO INESPERADO: {type(error).__name__}: {error}")
        finally:
            self.after(
                0,
                lambda: self.download_button.configure(
                    state="normal",
                    text="Iniciar Download",
                ),
            )


if __name__ == "__main__":
    app = SpotifyDownloaderApp()
    app.mainloop()
