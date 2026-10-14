# Changelog

## [2.0.1] - 2026-10-14

### Added

- Proibição estrita de download de playbacks no programa:
  - Filtro automático no Spotify para detectar e ignorar faixas de playback em playlists e álbuns (ex.: `- Playback`, `(Playback)`, `Karaokê`, `Backing Track`).
  - Bloqueio imediato na seleção do YouTube para descartar qualquer vídeo ou canal de playback/karaokê (`BAD_RESULT_TERMS` e `BAD_CHANNEL_TERMS`).
  - Bloqueio preventivo na função `download_music` para impedir requisições diretas de playbacks.
  - Expansão da consulta do YouTube para 10 candidatos (`ytsearch10`) com retries automáticos usando termos de áudio oficial caso a busca inicial contenha apenas playbacks descartados.

### Fixed

- Correção do descarte falso-positivo de faixas ao vivo quando a faixa original do Spotify é uma versão ao vivo (`allowed_live`).
- Correção do fallback de busca sem cookies quando a consulta inicial com cookies falha.

### Packaging

- Versão do produto atualizada para `2.0.1`.
- Executável: `release/BibliotecaOffline_v2.0.1.exe`.
- Instalador Inno Setup: `release/BibliotecaOffline_Setup_v2.0.1.exe`.
- SHA-256 do instalador: `F38044D80402D195599BF554A4F3293025D7FDA47E04BECF28F6E57846422886`.

## [2.0.0] - 2026-10-03

### Added

- Metadados Spotify estruturados com `TrackInfo`.
- Tags ID3 nos arquivos MP3 usando `mutagen`.
- Título, artista, álbum, número da faixa e número do disco quando disponíveis.
- Download e cache local da capa do álbum.
- Validação de formato JPEG/PNG para capas incorporadas.
- Descoberta do caminho final gerado pelo `yt-dlp` após a conversão.

### Maintained

- Interface gráfica em `customtkinter`.
- Modo console.
- Busca pontuada no YouTube.
- Cookies, retries automáticos e runtime Deno.
- Até três downloads simultâneos.
- Logs técnicos e resumo de progresso.
- Empacotamento standalone com PyInstaller.

### Fixed

- Correção da atualização do indicador de downloads paralelos quando a fila usa metadados `TrackInfo`.
- Correção da extração das capas Spotify em `albumOfTrack.coverArt.sources`.
- Atualização do `yt-dlp` para `2026.08.19` para corrigir falhas `HTTP 403` do YouTube.

### Packaging

- Versão do produto atualizada para `2.0.0`.
- Executável: `release/BibliotecaOffline_v2.0.0.exe`.
- Instalador Inno Setup: `release/BibliotecaOffline_Setup_v2.0.0.exe`.
- SHA-256 do instalador: `8CBC8E6C3567A590E4100BC887AF6548F254DE601269DFC0655DE4FE663DBC0B`.
- O instalador inclui o executável PyInstaller, FFmpeg, FFprobe, yt-dlp e Deno.

### Backup

- Snapshot anterior à implementação salvo na tag Git `backup-pre-v2.0`.

## [1.0.11]

- Versão anterior com pipeline unificado de download, retries com/sem cookies, seleção pontuada de resultados e paralelismo.
