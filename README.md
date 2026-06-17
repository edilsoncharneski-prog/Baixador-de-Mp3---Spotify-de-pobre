# Spotify Playlist para MP3

Aplicativo em Python para ler uma playlist publica do Spotify, montar buscas no YouTube e baixar as faixas em MP3 usando `yt-dlp` e FFmpeg.

O fluxo principal e simples: cole o link da playlist, escolha a pasta de destino, deixe o programa identificar o nome real da playlist e acompanhe o progresso geral pela interface.

## Recursos

- Interface grafica com `customtkinter`
- Leitura de playlists publicas pelo embed do Spotify
- Criacao automatica de pasta com o nome real da playlist
- Limpeza de caracteres proibidos pelo Windows em nomes de pasta
- Escolha da pasta base de destino pela interface
- Barra de progresso geral
- Console de logs em tempo real
- Botao para abrir a pasta final apos o download
- Suporte opcional a `cookies.txt` local para contornar bloqueios anti-bot do YouTube
- Download/conversao para MP3 com `yt-dlp` e FFmpeg

## Como funciona

1. O usuario informa a URL de uma playlist publica do Spotify.
2. O app converte a URL para a versao `embed` do Spotify.
3. O parser extrai o nome da playlist e as faixas do bloco `__NEXT_DATA__`.
4. Cada musica vira uma busca no YouTube no formato:

   ```text
   Nome da musica - Nome do artista
   ```

5. O `yt-dlp` baixa o melhor audio encontrado.
6. O FFmpeg converte o audio para MP3.
7. Os arquivos finais sao salvos em:

   ```text
   [Pasta escolhida]/[Nome da Playlist]/
   ```

Por padrao, a pasta base sugerida e:

```text
musicas_pendrive/
```

## Requisitos

- Python 3.10 ou superior
- FFmpeg instalado no sistema operacional ou embutido no executavel
- Node.js instalado no Windows para ajudar o `yt-dlp` a resolver challenges recentes do YouTube
- Conexao com a internet

Dependencias Python:

- `yt-dlp`
- `requests`
- `beautifulsoup4`
- `customtkinter`
- `pyinstaller`

## Instalacao

Clone o repositorio:

```bash
git clone https://github.com/edilsoncharneski-prog/Baixador-de-Mp3---Spotify-de-pobre.git
cd Baixador-de-Mp3---Spotify-de-pobre
```

Instale as dependencias:

```bash
pip install -r requirements.txt
```

## Uso pela GUI

Execute:

```bash
python main_gui.py
```

Depois:

1. Cole a URL publica da playlist do Spotify.
2. Escolha a pasta base de destino, se quiser mudar a padrao.
3. Clique em `Iniciar Download`.
4. Acompanhe o console e a barra de progresso.
5. Ao final, clique em `Abrir Pasta Final`.

URLs aceitas:

```text
https://open.spotify.com/playlist/ID_DA_PLAYLIST
https://open.spotify.com/embed/playlist/ID_DA_PLAYLIST
https://open.spotify.com/intl-pt/playlist/ID_DA_PLAYLIST
```

## Uso pelo terminal

Tambem existe a versao simples em terminal:

```bash
python main.py
```

## Gerar executavel

Com `ffmpeg.exe` e `ffprobe.exe` na raiz do projeto, rode:

```powershell
python -m PyInstaller --onefile --noconsole --name "BaixadorSpotifyMP3" --collect-all customtkinter --hidden-import darkdetect --add-binary "ffmpeg.exe;." --add-binary "ffprobe.exe;." main_gui.py
```

O executavel final sera gerado em:

```text
dist/BaixadorSpotifyMP3.exe
```

## Bloqueio anti-bot do YouTube

Se o log mostrar que o YouTube pediu login ou confirmou comportamento de bot, o video pode existir normalmente no YouTube, mas o `yt-dlp` foi bloqueado na hora de extrair o audio.

Nesse caso, coloque um arquivo `cookies.txt` valido ao lado do executavel:

```text
dist/
|-- BaixadorSpotifyMP3.exe
`-- cookies.txt
```

### Como gerar o `cookies.txt` pelo navegador

1. Abra o Chrome.
2. Entre no site do YouTube e confirme que voce esta logado na sua conta.
3. Instale uma extensao que exporte cookies no formato Netscape, por exemplo uma extensao chamada `cookies.txt` ou `Get cookies.txt LOCALLY`.
4. Com o YouTube aberto, clique no icone da extensao.
5. Exporte ou baixe os cookies do site atual em formato `.txt`.
6. Renomeie o arquivo baixado para exatamente:

   ```text
   cookies.txt
   ```

7. Copie esse arquivo para a mesma pasta do executavel:

   ```text
   dist/cookies.txt
   ```

No Windows, confira se as extensoes de arquivo estao visiveis. Se o arquivo ficar como `cookies.txt.txt`, o app nao vai reconhecer.

Na execucao pelo terminal, coloque o `cookies.txt` na raiz do projeto. Esse arquivo e privado e esta protegido pelo `.gitignore`.

Se o log mostrar `Requested format is not available`, o YouTube pode ter entregue apenas formatos de imagem/storyboard. O app tenta usar Node.js automaticamente para resolver o challenge JavaScript do YouTube.

## Estrutura do projeto

```text
.
|-- main.py
|-- main_gui.py
|-- requirements.txt
|-- atualizar_github.bat
`-- core/
    |-- __init__.py
    |-- downloader.py
    |-- file_manager.py
    `-- spotify_parser.py
```

## Observacoes importantes

- O Spotify pode alterar a estrutura interna da pagina a qualquer momento. Se isso acontecer, o parser pode precisar de ajustes.
- O resultado depende da busca do YouTube. Em alguns casos, o primeiro resultado pode nao ser exatamente a faixa desejada.
- O FFmpeg e obrigatorio para converter os arquivos para MP3.
- Playlists privadas ou que exigem login nao sao suportadas.
- Este projeto nao usa a API oficial do Spotify e nao exige token.
- O `.gitignore` impede que musicas, builds, executaveis, cookies e binarios locais do FFmpeg sejam enviados ao GitHub.

## Autoria e uso

Desenvolvido por Edilson Charneski.

Copyright (c) 2026 Edilson Charneski.

Este projeto foi criado para uso pessoal e educacional, especialmente pensando em quem mora em locais com pouca internet movel e ainda usa pendrive para ouvir musica no dia a dia.

## Aviso legal

Este projeto foi criado para fins educacionais e de automacao pessoal. Respeite os direitos autorais, os termos de uso das plataformas envolvidas e as leis aplicaveis no seu pais.

## Licenca

Defina uma licenca antes de publicar o repositorio. Para projetos abertos simples, a licenca MIT costuma ser uma opcao comum.
