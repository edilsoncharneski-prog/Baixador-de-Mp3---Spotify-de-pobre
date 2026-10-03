# Changelog

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
