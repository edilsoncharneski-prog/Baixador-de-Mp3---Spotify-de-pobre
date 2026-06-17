# Spotify Playlist para MP3

Script em Python para ler uma playlist publica do Spotify, montar buscas no YouTube e baixar as faixas em MP3 usando `yt-dlp` e FFmpeg.

O objetivo e simples: colar o link de uma playlist publica, deixar o script buscar as musicas automaticamente e gerar uma pasta com os arquivos `.mp3`, pronta para copiar para um pendrive ou outro dispositivo.

## Como funciona

1. O usuario informa a URL de uma playlist publica do Spotify.
2. O script converte a URL para a versao `embed` do Spotify.
3. O parser extrai as faixas do bloco `__NEXT_DATA__` da pagina.
4. Cada musica vira uma busca no YouTube no formato:

   ```text
   Nome da musica - Nome do artista
   ```

5. O `yt-dlp` baixa o melhor audio encontrado.
6. O FFmpeg converte o audio para MP3.
7. Os arquivos finais sao salvos na pasta `musicas_pendrive`.

## Requisitos

- Python 3.10 ou superior
- FFmpeg instalado no sistema operacional
- Conexao com a internet

Dependencias Python:

- `yt-dlp`
- `requests`
- `beautifulsoup4`

## Instalacao

Clone o repositorio:

```bash
git clone https://github.com/seu-usuario/seu-repositorio.git
cd seu-repositorio
```

Instale as dependencias:

```bash
pip install -r requirements.txt
```

Instale o FFmpeg e confirme que ele esta disponivel no terminal:

```bash
ffmpeg -version
```

Se o comando acima nao funcionar, o FFmpeg provavelmente nao esta instalado ou nao foi adicionado ao `PATH`.

## Uso

Execute:

```bash
python main.py
```

Cole a URL de uma playlist publica do Spotify quando o programa pedir:

```text
Cole a URL da playlist publica do Spotify aqui:
```

Exemplo de URL aceita:

```text
https://open.spotify.com/playlist/ID_DA_PLAYLIST
```

Tambem sao aceitas URLs no formato:

```text
https://open.spotify.com/embed/playlist/ID_DA_PLAYLIST
https://open.spotify.com/intl-pt/playlist/ID_DA_PLAYLIST
```

Ao final, os arquivos MP3 ficarao em:

```text
musicas_pendrive/
```

## Estrutura do projeto

```text
.
├── main.py
├── requirements.txt
└── core/
    ├── __init__.py
    ├── downloader.py
    ├── file_manager.py
    └── spotify_parser.py
```

### `main.py`

Orquestra o fluxo principal: recebe a URL, extrai as musicas, cria a pasta de destino, baixa os arquivos e exibe o relatorio final.

### `core/spotify_parser.py`

Faz a leitura da playlist publica do Spotify. O script usa a pagina `embed`, que costuma expor os dados publicos da playlist de forma mais direta do que a pagina normal.

### `core/downloader.py`

Usa `yt-dlp` para buscar a musica no YouTube e baixar o melhor audio disponivel, convertendo para MP3 com FFmpeg.

### `core/file_manager.py`

Cria a pasta de saida quando necessario.

## Observacoes importantes

- O Spotify pode alterar a estrutura interna da pagina a qualquer momento. Se isso acontecer, o parser pode precisar de ajustes.
- O resultado depende da busca do YouTube. Em alguns casos, o primeiro resultado pode nao ser exatamente a faixa desejada.
- O FFmpeg e obrigatorio para converter os arquivos para MP3.
- Playlists privadas ou que exigem login nao sao suportadas.
- Este projeto nao usa a API oficial do Spotify e nao exige token.

## Aviso legal

Este projeto foi criado para fins educacionais e de automacao pessoal. Respeite os direitos autorais, os termos de uso das plataformas envolvidas e as leis aplicaveis no seu pais.

## Licenca

Defina uma licenca antes de publicar o repositorio. Para projetos abertos simples, a licenca MIT costuma ser uma opcao comum.
