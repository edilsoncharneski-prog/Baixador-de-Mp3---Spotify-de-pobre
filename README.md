# Biblioteca Offline

Aplicativo em Python para montar uma biblioteca local de musicas em MP3 a partir de uma playlist publica do Spotify. O app le a playlist, monta buscas no YouTube e chama `yt-dlp.exe` diretamente para baixar e converter o audio com FFmpeg.

Versao atual: `v1.0.5`

## Recursos

- Interface grafica em `customtkinter`.
- Pasta padrao em `C:\Users\SEU_USUARIO\Music\Biblioteca Offline`.
- Suporte opcional a `cookies.txt` em `C:\Users\SEU_USUARIO\Music\Biblioteca Offline` quando o YouTube exige sessao.
- Log claro na interface e em `BibliotecaOffline.log`.
- Registro de URL processada, comando externo, pasta de saida e erro real retornado por `yt-dlp`/FFmpeg.

## Requisitos

- Python 3.11 ou superior para desenvolvimento.
- Dependencias de `requirements.txt`.
- `ffmpeg.exe` e `ffprobe.exe` na raiz do projeto para embutir no build.
- `yt-dlp.exe` instalado pelo pacote `yt-dlp` ou disponivel na raiz/PATH.

Instalacao local:

```bash
python -m pip install -r requirements.txt
```

Execucao da interface:

```bash
python main_gui.py
```

Execucao em modo console:

```bash
python main.py
```

## Build

Gerar executavel:

```bash
python -m PyInstaller BibliotecaOffline.spec
```

Saida esperada:

```text
dist/BibliotecaOffline.exe
```

Gerar instalador com Inno Setup:

```text
installer/BibliotecaOffline.iss
release/BibliotecaOffline_Setup_v1.0.5.exe
```

## Cookies

Quando o YouTube bloquear por login/anti-bot, coloque um arquivo `cookies.txt` valido em `C:\Users\SEU_USUARIO\Music\Biblioteca Offline`. O app usa cookies primeiro e so tenta sem cookies se o YouTube nao entregar um formato baixavel.

Estrutura esperada na pasta de dados do usuario:

```text
C:\Users\SEU_USUARIO\Music\Biblioteca Offline\
cookies.txt
BibliotecaOffline.log
```

## Changelog

### v1.0.5

- Aceita formatos adicionais de links de playlist do Spotify antes de validar a URL.

### v1.0.4

- Preserva espacos, acentos e caracteres comuns nos nomes dos arquivos MP3 baixados.

### v1.0.3

- Renomeia o produto para Biblioteca Offline.
- Troca o download para chamada direta de `yt-dlp.exe` com argumentos estruturados.
- Adiciona logs detalhados de URL, comando, saida, pasta e erro real.
- Atualiza metadados do executavel, instalador e pasta padrao.
- Remove referencias visuais/textuais aos nomes antigos.
