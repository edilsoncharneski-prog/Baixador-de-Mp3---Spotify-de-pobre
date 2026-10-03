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

### Packaging

- Versão do produto atualizada para `2.0.0`.
- Executável: `release/BibliotecaOffline_v2.0.0.exe`.
- Instalador Inno Setup: `release/BibliotecaOffline_Setup_v2.0.0.exe`.
- SHA-256 do instalador: `E1CC46756BA745BAF2F921E83C3BB83553B83E42FFA48A0D7A16CE9991A3390D`.
- O instalador inclui o executável PyInstaller, FFmpeg, FFprobe, yt-dlp e Deno.

### Backup

- Snapshot anterior à implementação salvo na tag Git `backup-pre-v2.0`.

## [1.0.11]

- Versão anterior com pipeline unificado de download, retries com/sem cookies, seleção pontuada de resultados e paralelismo.
