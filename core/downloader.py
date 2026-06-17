import os

import yt_dlp


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
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            display_name = (
                search_query[:45] + "..." if len(search_query) > 45 else search_query
            )
            print(f"  -> Buscando: {display_name}")
            ydl.download([search_query])

        return True, "OK"
    except yt_dlp.utils.DownloadError:
        return False, "Video nao encontrado ou bloqueado no YouTube."
    except yt_dlp.utils.PostProcessingError:
        return False, "Falha na conversao para MP3 (verifique o FFmpeg)."
    except Exception as error:
        return False, f"Erro inesperado: {type(error).__name__}"
