import base64
import concurrent.futures
import ctypes
import os
import queue
import re
import sys
import threading
import tkinter as tk
import tkinter.filedialog as filedialog
import webbrowser
from datetime import datetime
from pathlib import Path

import customtkinter
import requests
from core.downloader import (
    APP_NAME,
    MAX_PARALLEL_DOWNLOADS,
    download_music,
    get_cookie_file_path,
    get_deno_executable,
    get_expected_cookie_file_path,
    get_ffmpeg_location,
    get_yt_dlp_executable,
    migrate_legacy_cookie_file,
)
from core.spotify_parser import extract_playlist_data
from icon_data import ICON_DATA_BASE64


APP_EXECUTABLE_NAME = "BibliotecaOffline"
APP_VERSION = "1.0.11"
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


def get_user_data_path() -> Path:
    return Path.home() / "Music" / APP_NAME


def get_log_file_path() -> Path:
    return get_user_data_path() / f"{APP_EXECUTABLE_NAME}.log"


def get_default_destination_root() -> Path:
    destination_root = Path.home() / "Music" / APP_NAME
    destination_root.mkdir(parents=True, exist_ok=True)
    return destination_root


def normalize_destination_path(destination_text: str) -> Path:
    clean_text = destination_text.strip().strip('"')
    if re.match(r"^[A-Za-z]:[^\\/]", clean_text):
        clean_text = f"{clean_text[:2]}\\{clean_text[2:]}"
    return Path(clean_text).expanduser()


def ensure_icon_file() -> Path:
    icon_path = get_app_base_path() / "icon.ico"
    if icon_path.is_file() and icon_path.stat().st_size > 0:
        return icon_path

    icon_path.write_bytes(base64.b64decode(ICON_DATA_BASE64))
    return icon_path


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
        self.log_write_lock = threading.Lock()
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
            placeholder_text="Cole aqui a URL publica da playlist, album ou faixa do Spotify",
            font=customtkinter.CTkFont(size=14),
            border_color=GOLD,
        )
        self.url_entry.grid(row=1, column=0, padx=36, pady=(10, 14), sticky="ew")

        self.playlist_label = customtkinter.CTkLabel(
            self,
            text="Origem:\n-",
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
            "Pronto. Cole a URL da playlist, album ou faixa e clique em Iniciar Download.\n",
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
            with self.log_write_lock:
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

        extension_button = customtkinter.CTkButton(
            button_frame,
            text="Instalar extensao",
            width=140,
            command=lambda: webbrowser.open(COOKIE_EXTENSION_URL),
        )
        extension_button.grid(row=0, column=0, padx=(0, 10))

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

    def set_playlist_name(self, playlist_name: str | None, collection_type: str = "playlist") -> None:
        text = playlist_name if playlist_name else "-"
        labels = {"playlist": "Playlist", "album": "Album", "track": "Faixa"}
        label = labels.get(collection_type, "Playlist")
        self.after(0, lambda: self.playlist_label.configure(text=f"Origem:\n{label}: {text}"))

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
            self.append_log("Informe a URL da playlist, album ou faixa antes de iniciar.")
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
            self.append_log("Buscando no Spotify...")
            self.append_technical_log(f"Iniciando processo no {APP_NAME} v{APP_VERSION}...")
            self.append_technical_log(f"Log completo: {self.log_file_path}")
            self.append_technical_log(f"URL processada: {playlist_url}")
            migrate_legacy_cookie_file(self.append_technical_log)

            yt_dlp_path = get_yt_dlp_executable()
            if yt_dlp_path:
                self.append_technical_log(f"yt-dlp localizado em: {yt_dlp_path}")
            else:
                self.append_log("yt-dlp.exe nao foi encontrado.")

            deno_path = get_deno_executable()
            if deno_path:
                self.append_technical_log(f"Runtime JavaScript localizado em: {deno_path}")
            else:
                self.append_technical_log(
                    "Runtime JavaScript nao encontrado; o yt-dlp usara o modo de compatibilidade."
                )

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

            collection_type, playlist_name, tracks = extract_playlist_data(
                playlist_url,
                self.append_technical_log,
            )
            if not tracks:
                self.append_log("Nenhuma musica encontrada.")
                return

            collection_label = {"playlist": "Playlist", "album": "Album", "track": "Faixa"}.get(collection_type, "Playlist")
            self.set_playlist_name(playlist_name, collection_type)
            self.append_log(f"Origem:\n{collection_label}: {playlist_name}")
            self.append_log(f"{len(tracks)} musicas encontradas.")

            output_dir = destination_root / playlist_name
            output_dir.mkdir(parents=True, exist_ok=True)
            self.last_output_dir = output_dir
            self.append_technical_log(f"Preparando pasta de saida: {output_dir}")
            self.append_technical_log("-" * 70)

            successes = 0
            failures: list[tuple[str, str]] = []
            self.set_progress(0, len(tracks))
            self.set_summary("em andamento", len(tracks), successes, len(failures), len(tracks))

            total_tracks = len(tracks)
            completed = 0
            active_downloads = min(MAX_PARALLEL_DOWNLOADS, total_tracks)
            self.append_log(f"Modo rapido ativado: ate {active_downloads} downloads ao mesmo tempo.")
            self.append_technical_log(f"Downloads paralelos configurados: {active_downloads}")

            source_album = playlist_name if collection_type == "album" else ""

            def run_track_download(index: int, track: str) -> tuple[int, str, bool, str]:
                def prefixed_log(message: str) -> None:
                    self.append_technical_log(f"[{index}/{total_tracks}] {message}")

                prefixed_log("")
                prefixed_log("Iniciando processamento.")
                success, message = download_music(
                    track,
                    str(output_dir),
                    ffmpeg_location,
                    prefixed_log,
                    source_album,
                )
                return index, track, success, message

            next_index = 1
            pending: dict[concurrent.futures.Future, tuple[int, str]] = {}
            with concurrent.futures.ThreadPoolExecutor(max_workers=active_downloads) as executor:
                while next_index <= total_tracks and len(pending) < active_downloads and not self.cancel_requested:
                    track = tracks[next_index - 1]
                    self.append_log(f"[{next_index}/{total_tracks}] Entrou na fila: {track}")
                    pending[executor.submit(run_track_download, next_index, track)] = (next_index, track)
                    next_index += 1

                while pending:
                    if self.cancel_requested:
                        for future in pending:
                            future.cancel()
                        self.append_log("Download cancelado pelo usuario.")
                        break

                    done, _ = concurrent.futures.wait(
                        pending,
                        timeout=0.5,
                        return_when=concurrent.futures.FIRST_COMPLETED,
                    )
                    if not done:
                        running = ", ".join(track for _, track in pending.values())
                        self.set_current_track(f"Processando em paralelo: {running}")
                        continue

                    for future in done:
                        original_index, original_track = pending.pop(future)
                        if future.cancelled():
                            failures.append((original_track, "Cancelado antes de iniciar."))
                            continue
                        try:
                            index, track, success, message = future.result()
                        except Exception as error:
                            index, track = original_index, original_track
                            success, message = False, f"Erro inesperado: {error}"

                        completed += 1
                        if success:
                            successes += 1
                            self.append_log(f"[{index}/{total_tracks}] Concluído: {track}")
                        else:
                            failures.append((track, message))
                            self.append_log(f"[{index}/{total_tracks}] Falhou: {track} ({message})")

                        self.append_technical_log("")
                        self.set_progress(completed, total_tracks)
                        remaining = total_tracks - completed
                        self.set_summary(
                            "em andamento",
                            total_tracks,
                            successes,
                            len(failures),
                            remaining,
                        )

                        while next_index <= total_tracks and len(pending) < active_downloads and not self.cancel_requested:
                            next_track = tracks[next_index - 1]
                            self.append_log(f"[{next_index}/{total_tracks}] Entrou na fila: {next_track}")
                            pending[executor.submit(run_track_download, next_index, next_track)] = (next_index, next_track)
                            next_index += 1

            canceled = self.cancel_requested
            completed = successes + len(failures)
            remaining = max(len(tracks) - completed, 0)
            self.append_technical_log("-" * 70)
            self.append_technical_log("RELATORIO FINAL")
            self.append_log(f"Total encontrado     : {len(tracks)}")
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
