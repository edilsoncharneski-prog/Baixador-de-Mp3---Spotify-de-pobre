from pathlib import Path
import sys

import requests

from core.downloader import (
    download_music,
    get_cookie_file_path,
    get_expected_cookie_file_path,
)
from core.file_manager import create_output_dir
from core.spotify_parser import extract_playlist_tracks


DEFAULT_OUTPUT_DIR = Path.home() / "Music" / "Biblioteca Offline"


def main() -> None:
    print("=" * 60)
    print("   BIBLIOTECA OFFLINE")
    print("=" * 60)

    playlist_url = input("\nCole a URL da playlist publica do Spotify aqui: ").strip()
    if not playlist_url:
        print("[ERRO] Nenhuma URL fornecida. Saindo.")
        sys.exit(1)

    print("\n[ETAPA 1/3] Extraindo informacoes da playlist...")
    try:
        musicas = extract_playlist_tracks(playlist_url)
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
    dir_path = create_output_dir(str(DEFAULT_OUTPUT_DIR))
    print(f"  Pasta: {dir_path}\n")

    cookie_file = get_cookie_file_path()
    if cookie_file:
        print(f"  cookies.txt encontrado: {cookie_file}")
    else:
        print(f"  cookies.txt nao encontrado ou vazio em: {get_expected_cookie_file_path()}")
        print("  O script nao vai tentar ler cookies do Chrome.\n")

    print("[ETAPA 3/3] Iniciando lote de downloads...")
    print("-" * 60)

    sucessos = 0
    falhas = []

    for index, musica in enumerate(musicas, start=1):
        print(f"[{index}/{len(musicas)}]", end=" ")
        sucesso, msg = download_music(musica, dir_path)

        if sucesso:
            print("  OK Concluido\n")
            sucessos += 1
        else:
            print(f"  FALHOU: {msg}\n")
            falhas.append((musica, msg))

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
