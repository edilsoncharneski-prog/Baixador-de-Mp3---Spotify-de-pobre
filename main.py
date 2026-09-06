from pathlib import Path
import sys

import requests

from core.downloader import (
    MAX_PARALLEL_DOWNLOADS,
    download_tracks,
    get_cookie_file_path,
    get_expected_cookie_file_path,
    get_ffmpeg_location,
    get_yt_dlp_executable,
    migrate_legacy_cookie_file,
)
from core.spotify_parser import extract_playlist_data


DEFAULT_OUTPUT_DIR = Path.home() / "Music" / "Biblioteca Offline"


def main() -> None:
    print("=" * 60)
    print("   BIBLIOTECA OFFLINE (modo console)")
    print("=" * 60)

    playlist_url = input("\nCole a URL da playlist/album/faixa publica do Spotify aqui: ").strip()
    if not playlist_url:
        print("[ERRO] Nenhuma URL fornecida. Saindo.")
        sys.exit(1)

    print("\n[ETAPA 1/3] Extraindo informacoes do Spotify...")
    try:
        collection_type, playlist_name, musicas = extract_playlist_data(playlist_url, print)
        if not musicas:
            print("A playlist esta vazia.")
            sys.exit(0)
        print(f"  [SUCESSO] {len(musicas)} musicas encontradas.\n")
    except ValueError as error:
        print(f"\n[ERRO FATAL] {error}")
        sys.exit(1)
    except requests.exceptions.RequestException as error:
        print(f"\n[ERRO FATAL] Falha de conexao com o Spotify: {error}")
        sys.exit(1)

    print("[ETAPA 2/3] Preparando pasta de destino...")
    dir_path = DEFAULT_OUTPUT_DIR / playlist_name
    dir_path.mkdir(parents=True, exist_ok=True)
    print(f"  Pasta: {dir_path}\n")

    migrate_legacy_cookie_file(print)
    cookie_file = get_cookie_file_path()
    if cookie_file:
        print(f"  cookies.txt encontrado: {cookie_file}")
    else:
        print(f"  cookies.txt nao encontrado ou vazio em: {get_expected_cookie_file_path()}")

    if not get_yt_dlp_executable():
        print("[ERRO FATAL] yt-dlp.exe nao foi encontrado.")
        sys.exit(1)
    ffmpeg_location = get_ffmpeg_location()
    if ffmpeg_location:
        print(f"  FFmpeg localizado em: {ffmpeg_location}")
    else:
        print("  FFmpeg nao encontrado junto ao app. Tentando usar o PATH do sistema.")
    print()

    print(f"[ETAPA 3/3] Iniciando lote de downloads (ate {MAX_PARALLEL_DOWNLOADS} em paralelo)...")
    print("-" * 60)

    source_album = playlist_name if collection_type == "album" else ""

    def on_result(index: int, total: int, track: str, success: bool, message: str) -> None:
        status = "OK Concluido" if success else f"FALHOU: {message}"
        print(f"[{index}/{total}] {track}\n  {status}\n")

    try:
        sucessos, falhas = download_tracks(
            musicas,
            str(dir_path),
            ffmpeg_location,
            print,
            source_album,
            on_result,
        )
    except Exception as error:  # diagnostico final do modo console
        print(f"\n[ERRO FATAL] {type(error).__name__}: {error}")
        sys.exit(1)

    print("-" * 60)
    print("=" * 60)
    print("                 RELATORIO FINAL")
    print("=" * 60)
    print(f"Total na playlist     : {len(musicas)}")
    print(f"Baixadas com sucesso  : {sucessos}")
    print(f"Falhas                : {len(falhas)}")

    if falhas:
        print("\n--- Musicas que falharam ---")
        for musica, erro in falhas:
            nome_curto = musica[:50] + "..." if len(musica) > 50 else musica
            print(f"- {nome_curto} ({erro})")

    print("=" * 60)


if __name__ == "__main__":
    main()
