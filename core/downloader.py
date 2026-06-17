import os
from pathlib import Path

import yt_dlp


def get_cookie_file_path() -> Path | None:
    cookie_file = Path(__file__).resolve().parent.parent / "cookies.txt"
    if cookie_file.exists():
        return cookie_file
    return None


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


def summarize_download_error(error: Exception, used_chrome_cookies: bool = False) -> str:
    error_text = str(error)
    if "Sign in to confirm" in error_text or "not a bot" in error_text:
        if used_chrome_cookies:
            return (
                "YouTube exigiu autenticacao/anti-bot mesmo usando os cookies do Chrome. "
                "Abra o Chrome, entre no YouTube e tente novamente. "
                "Se persistir, coloque um cookies.txt valido na pasta do projeto."
            )
        return (
            "YouTube bloqueou por anti-bot/login. "
            "O script esta usando os cookies do Chrome como rota de escape. "
            "Se persistir, coloque um cookies.txt valido na pasta do projeto."
        )
    if "Could not copy Chrome cookie database" in error_text or "Failed to decrypt with DPAPI" in error_text:
        return (
            "Nao foi possivel ler os cookies do Chrome. "
            "Feche o Chrome e tente novamente, ou coloque um cookies.txt valido na pasta do projeto."
        )
    return "Video nao encontrado ou bloqueado no YouTube."


def download_music(search_query: str, output_dir: str) -> tuple[bool, str]:
    """
    Busca no YouTube e baixa/converte para MP3 usando yt-dlp e FFmpeg.
    """
    output_template = os.path.join(output_dir, "%(title)s.%(ext)s")

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
        "quiet": False,
        "no_warnings": True,
        "extract_flat": False,
        "cookiesfrombrowser": ("chrome", None, None, None),
    }

    using_chrome_cookies = True
    cookie_file = get_cookie_file_path()
    if cookie_file:
        ydl_opts.pop("cookiesfrombrowser", None)
        ydl_opts["cookiefile"] = str(cookie_file)
        using_chrome_cookies = False

    last_download_error = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            for attempt, search_term in enumerate(build_youtube_search_terms(search_query), start=1):
                display_name = search_term.replace("ytsearch1:", "", 1)
                display_name = (
                    display_name[:45] + "..." if len(display_name) > 45 else display_name
                )

                try:
                    print(f"  -> Busca {attempt}: {display_name}")
                    ydl.download([search_term])
                    return True, "OK"
                except yt_dlp.utils.DownloadError as error:
                    last_download_error = error
                    if "Sign in to confirm" in str(error) or "not a bot" in str(error):
                        return False, summarize_download_error(error, using_chrome_cookies)
                    print("  -> Resultado nao encontrado. Tentando busca alternativa...")

        if last_download_error:
            raise last_download_error

        return True, "OK"
    except yt_dlp.utils.DownloadError as error:
        return False, summarize_download_error(error, using_chrome_cookies)
    except yt_dlp.utils.PostProcessingError:
        return False, "Falha na conversao para MP3 (verifique o FFmpeg)."
    except Exception as error:
        return False, f"Erro inesperado: {type(error).__name__}"
