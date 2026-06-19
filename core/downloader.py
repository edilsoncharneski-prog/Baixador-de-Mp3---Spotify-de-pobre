import os
import re
import shutil
import subprocess
import sysconfig
from pathlib import Path

from core.youtube import build_youtube_search_terms


def _find_executable(candidates: list[str], extra_dirs: list[Path] | None = None) -> Path | None:
    project_root = Path(__file__).resolve().parent.parent
    search_dirs = [project_root]
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
    return _find_executable(["yt-dlp.exe", "yt-dlp"], extra_dirs)


def get_ffmpeg_location() -> str | None:
    project_root = Path(__file__).resolve().parent.parent
    if (project_root / "ffmpeg.exe").is_file() and (project_root / "ffprobe.exe").is_file():
        return str(project_root)
    ffmpeg_path = shutil.which("ffmpeg")
    return str(Path(ffmpeg_path).parent) if ffmpeg_path else None


def get_expected_cookie_file_path() -> Path:
    return Path.home() / "Music" / "Biblioteca Offline" / "cookies.txt"


def get_cookie_file_path() -> Path | None:
    cookie_file = get_expected_cookie_file_path()
    if cookie_file.is_file() and cookie_file.stat().st_size > 0:
        return cookie_file
    return None


def summarize_download_error(error_text: str, used_cookie_file: bool = False) -> str:
    if "Sign in to confirm" in error_text or "not a bot" in error_text:
        if used_cookie_file:
            return (
                "YouTube exigiu autenticacao/anti-bot mesmo usando cookies.txt. "
                "Exporte cookies novos do YouTube e substitua o arquivo na pasta do projeto."
            )
        return (
            "YouTube bloqueou por anti-bot/login. "
            "Coloque um cookies.txt valido na pasta do projeto e tente novamente."
        )
    if "Could not copy Chrome cookie database" in error_text or "Failed to decrypt with DPAPI" in error_text:
        return (
            "Nao foi possivel ler os cookies. "
            "Coloque um cookies.txt valido na pasta do projeto e tente novamente."
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


def download_music(search_query: str, output_dir: str) -> tuple[bool, str]:
    """
    Busca no YouTube e baixa/converte para MP3 usando yt-dlp e FFmpeg.
    """
    yt_dlp_path = get_yt_dlp_executable()
    if not yt_dlp_path:
        return False, "yt-dlp.exe nao foi encontrado."

    ffmpeg_location = get_ffmpeg_location()
    output_template = os.path.join(output_dir, "%(title)s.%(ext)s")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    cookie_file = get_cookie_file_path()
    using_cookie_file = bool(cookie_file)

    last_error_text = ""
    for attempt, search_term in enumerate(build_youtube_search_terms(search_query), start=1):
        display_name = search_term.replace("ytsearch1:", "", 1)
        display_name = display_name[:45] + "..." if len(display_name) > 45 else display_name

        cookie_modes = [cookie_file] if cookie_file else [None]
        if cookie_file:
            cookie_modes.append(None)

        for cookie_mode_index, cookie_path in enumerate(cookie_modes, start=1):
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
                "--restrict-filenames",
                "--output",
                output_template,
            ]
            if ffmpeg_location:
                command.extend(["--ffmpeg-location", ffmpeg_location])
            if cookie_path:
                command.extend(["--cookies", str(cookie_path)])
            command.append(search_term)

            print(f"  -> Busca {attempt}: {display_name}")
            if cookie_file and cookie_mode_index == 2:
                print("  -> Repetindo sem cookies porque o YouTube nao entregou formato valido com cookies.")
            print(f"  -> Comando externo: {' '.join(command)}")

            try:
                result = subprocess.run(
                    command,
                    cwd=output_dir,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    shell=False,
                    env=get_external_process_env(),
                    timeout=1800,
                    **get_external_process_options(),
                )
            except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired) as error:
                return False, f"Erro ao executar yt-dlp: {error}"

            combined_output = "\n".join(
                part.strip() for part in [result.stdout, result.stderr] if part and part.strip()
            )
            if combined_output:
                print(combined_output)

            if result.returncode == 0:
                return True, "OK"

            last_error_text = combined_output or f"yt-dlp retornou codigo {result.returncode} sem mensagem."
            print(f"  -> Erro do yt-dlp/FFmpeg: {shorten_error(last_error_text)}")

            if (
                cookie_path
                and cookie_file
                and should_retry_without_cookies(last_error_text)
                and cookie_mode_index < len(cookie_modes)
            ):
                continue

    return False, summarize_download_error(last_error_text, using_cookie_file)
