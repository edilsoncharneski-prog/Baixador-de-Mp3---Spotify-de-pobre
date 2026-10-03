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

### Packaging

- Versão do produto atualizada para `2.0.0`.
- Executável: `release/BibliotecaOffline_v2.0.0.exe`.
- SHA-256: `BA06C48A75402790037049F31541532725A9FEBC517644A34859BFF43D8D4EDB`.

### Backup

- Snapshot anterior à implementação salvo na tag Git `backup-pre-v2.0`.

## [1.0.11]

- Versão anterior com pipeline unificado de download, retries com/sem cookies, seleção pontuada de resultados e paralelismo.
