import json
import os
import re
import shutil
import subprocess
import sys
import sysconfig
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from core.youtube import choose_youtube_result
from core.models import TrackInfo, ensure_track_info
from core.tagger import apply_id3_tags


APP_NAME = "Biblioteca Offline"
MAX_PARALLEL_DOWNLOADS = 3


def _noop_log(message: str) -> None:
    pass


# ---------------------------------------------------------------------------
# Localizacao de executaveis e arquivos auxiliares (compativel com PyInstaller)
# ---------------------------------------------------------------------------

def get_app_base_path() -> Path:
    """Pasta real do app, tanto no Python normal quanto no PyInstaller."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def get_external_base_path() -> Path:
    """Pasta visivel do app, onde o usuario pode colocar arquivos auxiliares."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def get_user_data_path() -> Path:
    return Path.home() / "Music" / APP_NAME


def get_expected_cookie_file_path() -> Path:
    return get_user_data_path() / "cookies.txt"


def get_cookie_file_path() -> Path | None:
    cookie_file = get_expected_cookie_file_path()
    if cookie_file.is_file() and cookie_file.stat().st_size > 0:
        return cookie_file
    return None


def migrate_legacy_cookie_file(log=None) -> None:
    log = log or _noop_log
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
            log(f"cookies.txt migrado para: {expected_cookie_file}")
            return
        except OSError as error:
            log(f"Nao foi possivel migrar cookies.txt: {error}")


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


def get_deno_executable() -> Path | None:
    """Localiza o runtime JavaScript usado pelo yt-dlp para o desafio do YouTube."""
    return find_executable(["deno.exe", "deno"])


def get_youtube_runtime_args() -> list[str]:
    """Habilita o componente oficial de JS/PO Token quando o Deno estiver disponivel."""
    deno_path = get_deno_executable()
    if not deno_path:
        return []
    return [
        "--js-runtimes", f"deno:{deno_path}",
        "--remote-components", "ejs:github",
    ]


def get_ffmpeg_location() -> str | None:
    base_path = get_app_base_path()
    if (base_path / "ffmpeg.exe").exists() and (base_path / "ffprobe.exe").exists():
        return str(base_path)

    ffmpeg_path = shutil.which("ffmpeg")
    return str(Path(ffmpeg_path).parent) if ffmpeg_path else None


# ---------------------------------------------------------------------------
# Execucao de processos externos
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Diagnostico de erros e retries de cookies
# ---------------------------------------------------------------------------

def shorten_error(error_text: str) -> str:
    error_text = re.sub(r"\s+", " ", str(error_text)).strip()
    error_text = error_text.replace("ERROR: ", "")
    return error_text[:700]


def summarize_download_error(error_text: str, used_cookie_file: bool = False) -> str:
    if "Sign in to confirm" in error_text or "not a bot" in error_text:
        if used_cookie_file:
            return (
                "YouTube exigiu autenticacao/anti-bot mesmo usando cookies.txt. "
                "Exporte cookies novos do YouTube e substitua o arquivo na pasta de dados do app."
            )
        return (
            "YouTube bloqueou por anti-bot/login. "
            "Coloque um cookies.txt valido na pasta de dados do app e tente novamente."
        )
    if "Could not copy Chrome cookie database" in error_text or "Failed to decrypt with DPAPI" in error_text:
        return (
            "Nao foi possivel ler os cookies. "
            "Coloque um cookies.txt valido na pasta de dados do app e tente novamente."
        )
    if "Requested format is not available" in error_text or "Only images are available" in error_text:
        return (
            "O YouTube retornou o video sem formato de audio. "
            "Instale o Node.js/Deno ou atualize o yt-dlp para resolver o challenge do YouTube."
        )
    return "Video nao encontrado ou bloqueado no YouTube."


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


def _build_cookie_retry_modes(error_text: str, cookie_file: Path | None, cookie_path_used: Path | None) -> list[Path | None]:
    """
    Define a sequencia automatica de tentativas com/sem cookies:
    - sem cookies + bloqueio anti-bot -> repete com cookies;
    - com cookies + 403/formato invalido -> repete sem cookies.
    """
    if cookie_path_used and should_retry_without_cookies(error_text):
        return [None]
    if not cookie_path_used and cookie_file and should_retry_with_cookies(error_text):
        return [cookie_file]
    return []


# ---------------------------------------------------------------------------
# Busca e download no YouTube
# ---------------------------------------------------------------------------

def find_youtube_result(
    yt_dlp_path: Path,
    search_query: str,
    cookie_file: Path | None,
    log=None,
    album_name: str = "",
) -> tuple[str | None, str | None, str]:
    """Consulta os 5 primeiros resultados do YouTube e escolhe o melhor pelo score."""
    log = log or _noop_log
    command = [
        str(yt_dlp_path), "--flat-playlist", "--default-search", "ytsearch5", "--skip-download",
        "--dump-single-json", "--no-warnings", f"ytsearch5:{search_query}",
    ]
    if cookie_file:
        command[1:1] = ["--cookies", str(cookie_file)]
    log(f"  Consultando 5 resultados: {search_query}")
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8", errors="replace",
            shell=False, env=get_external_process_env(), timeout=120, **get_external_process_options(),
        )
    except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired) as error:
        return None, None, f"Erro ao buscar no YouTube: {error}"

    if result.returncode != 0:
        error_text = "\n".join(part.strip() for part in [result.stdout, result.stderr] if part and part.strip())
        return None, None, error_text or f"yt-dlp retornou codigo {result.returncode} ao buscar."
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        return None, None, f"Resposta de busca invalida do yt-dlp: {error}"

    entries = payload.get("entries", []) if isinstance(payload, dict) else []
    selected, scored = choose_youtube_result(entries, search_query, album_name, log)
    for index, item in enumerate(scored, start=1):
        entry = item["entry"]
        channel = entry.get("channel") or entry.get("uploader") or "-"
        log(f"  Resultado {index}: titulo={entry.get('title') or '-'} | canal={channel} | score={item['score']}")
    if not selected:
        return None, None, "Nenhum resultado com URL valida foi encontrado."

    entry = selected["entry"]
    channel = entry.get("channel") or entry.get("uploader") or "-"
    log(f"  Resultado escolhido: titulo={entry.get('title') or '-'} | canal={channel} | score={selected['score']}")
    return selected["target"], str(entry.get("title") or ""), ""


def _run_yt_dlp_download(
    yt_dlp_path: Path,
    target_url: str,
    output_dir: str,
    output_template: str,
    ffmpeg_location: str | None,
    cookie_path: Path | None,
    log,
) -> tuple[bool, str, Path | None]:
    command = [
        str(yt_dlp_path), *get_youtube_runtime_args(), "--format", "bestaudio/best", "--check-formats",
        "--extract-audio", "--audio-format", "mp3", "--audio-quality", "192K",
        "--no-playlist", "--no-warnings", "--windows-filenames",
        "--print", "after_move:filepath", "--output", output_template,
    ]
    if ffmpeg_location:
        command.extend(["--ffmpeg-location", ffmpeg_location])
    if cookie_path:
        command.extend(["--cookies", str(cookie_path)])
    command.append(target_url)
    safe_command = " ".join(f'"{part}"' if " " in part else part for part in command)
    log(f"  Comando externo: {safe_command}")
    try:
        result = subprocess.run(
            command, cwd=output_dir, capture_output=True, text=True,
            encoding="utf-8", errors="replace", shell=False, env=get_external_process_env(),
            timeout=1800, **get_external_process_options(),
        )
    except FileNotFoundError:
        return False, f"Executavel nao encontrado: {yt_dlp_path}", None
    except PermissionError as error:
        return False, f"Sem permissao para executar ou gravar em {output_dir}: {error}", None
    except subprocess.TimeoutExpired as error:
        return False, f"Timeout no yt-dlp apos {error.timeout} segundos.", None

    combined_output = "\n".join(part.strip() for part in [result.stdout, result.stderr] if part and part.strip())
    if combined_output:
        for line in combined_output.splitlines()[-18:]:
            log(f"    {line}")
    if result.returncode == 0:
        log("    Download concluido e convertido para MP3.")
        mp3_path = None
        for line in reversed(combined_output.splitlines()):
            candidate = Path(line.strip().strip('"'))
            if candidate.suffix.lower() == ".mp3":
                mp3_path = candidate if candidate.is_absolute() else Path(output_dir) / candidate
                if mp3_path.is_file():
                    break
        return True, "OK", mp3_path

    error_text = combined_output or f"yt-dlp retornou codigo {result.returncode} sem mensagem."
    log(f"    Falha na etapa yt-dlp/FFmpeg. Codigo: {result.returncode}")
    log(f"    Erro real: {shorten_error(error_text)}")
    return False, error_text, None


def download_music(
    search_query: str | TrackInfo,
    output_dir: str,
    ffmpeg_location: str | None = None,
    log=None,
    source_album: str = "",
) -> tuple[bool, str]:
    """
    Busca no YouTube (5 resultados pontuados), baixa e converte para MP3 usando
    yt-dlp + FFmpeg, com retry automatico com/sem cookies conforme o erro.
    """
    log = log or _noop_log
    track_info = ensure_track_info(search_query)
    search_query = track_info.search_query
    yt_dlp_path = get_yt_dlp_executable()
    if not yt_dlp_path:
        return False, "yt-dlp.exe nao foi encontrado. Reinstale o app ou instale o yt-dlp no ambiente."
    if ffmpeg_location is None:
        ffmpeg_location = get_ffmpeg_location()

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    output_template = str(output_path / "%(title)s.%(ext)s")
    cookie_file = get_cookie_file_path()
    using_cookie_file = bool(cookie_file)
    log(f"  URL/processamento: {search_query}")
    log(f"  Pasta de saida: {output_path}")

    search_cookie_modes: list[Path | None] = [cookie_file] if cookie_file else [None]
    target_url = None
    search_error = ""
    for cookie_mode in search_cookie_modes:
        target_url, _, search_error = find_youtube_result(
            yt_dlp_path, search_query, cookie_mode, log, source_album
        )
        if target_url:
            break
        if cookie_mode and search_cookie_modes[-1] is None:
            log("  Busca com cookies falhou; repetindo a consulta sem cookies.")
    if not target_url:
        log(f"  Falha ao escolher resultado: {shorten_error(search_error)}")
        return False, summarize_download_error(search_error, using_cookie_file)

    cookie_modes: list[Path | None] = [cookie_file] if cookie_file else [None]
    attempt = 0
    while attempt < len(cookie_modes):
        cookie_path = cookie_modes[attempt]
        attempt += 1
        success, error_text, mp3_path = _run_yt_dlp_download(
            yt_dlp_path, target_url, output_dir, output_template,
            ffmpeg_location, cookie_path, log,
        )
        if success:
            if mp3_path and isinstance(track_info, TrackInfo):
                tagger_cache = Path(output_dir) / ".metadata" / "covers"
                if apply_id3_tags(mp3_path, track_info, tagger_cache, log):
                    log("    Metadados Spotify aplicados ao MP3.")
                else:
                    log("    Download mantido; tagging Spotify nao foi concluido.")
            return True, "OK"

        retry_modes = _build_cookie_retry_modes(error_text, cookie_file, cookie_path)
        for retry_mode in retry_modes:
            if retry_mode not in cookie_modes:
                if retry_mode is None:
                    log("  Repetindo sem cookies porque o YouTube nao entregou formato valido com cookies.")
                else:
                    log("  Repetindo com cookies porque o YouTube exigiu autenticacao/anti-bot.")
                cookie_modes.append(retry_mode)

    return False, summarize_download_error(error_text, using_cookie_file)


def download_tracks(
    tracks: list[str | TrackInfo],
    output_dir: str,
    ffmpeg_location: str | None = None,
    log=None,
    source_album: str = "",
    on_result=None,
    max_parallel: int = MAX_PARALLEL_DOWNLOADS,
) -> tuple[int, list[tuple[str, str]]]:
    """
    Baixa a lista de faixas com ate `max_parallel` downloads simultaneos.
    `on_result(index, total, track, success, message)` e chamado ao final de cada faixa.
    Retorna (sucessos, falhas).
    """
    log = log or _noop_log
    total = len(tracks)
    active = min(max_parallel, total)
    log(f"Modo rapido ativado: ate {active} downloads ao mesmo tempo.")
    successes = 0
    failures: list[tuple[str, str]] = []

    def run_one(index: int, track: str) -> tuple[int, str, bool, str]:
        success, message = download_music(
            track, output_dir, ffmpeg_location, log, source_album
        )
        return index, track, success, message

    with ThreadPoolExecutor(max_workers=active) as executor:
        futures = {executor.submit(run_one, i, t): (i, t) for i, t in enumerate(tracks, start=1)}
        for future in as_completed(futures):
            index, track = futures[future]
            try:
                _, _, success, message = future.result()
            except Exception as error:
                success, message = False, f"Erro inesperado: {error}"
            if success:
                successes += 1
            else:
                failures.append((track, message))
            if on_result:
                on_result(index, total, track, success, message)

    return successes, failures
