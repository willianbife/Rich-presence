# Discord Rich Presence Studio

Aplicativo desktop em Python para configurar e ativar Discord Rich Presence de forma visual, segura e profissional.

O projeto usa a integracao oficial via Discord RPC local com `pypresence`. Ele nao usa token de usuario, selfbot, automacao de DM, farm de call ou qualquer automacao proibida pela plataforma.

## Recursos

- Interface dark mode com sidebar, cards, animacoes suaves e preview ao vivo.
- Conexao com Discord RPC usando apenas o Discord Application Client ID.
- Editor visual de `details`, `state`, imagens, textos, botoes e timestamp.
- Preview inspirado no card de atividade do Discord.
- Presets locais em JSON com salvar, aplicar, editar, renomear, excluir, duplicar, importar e exportar.
- Temas: Dark, Cyberpunk, Discord Roxo e Minimalista.
- Estrutura preparada para integracoes futuras: Spotify, Steam, League of Legends, Valorant e APIs externas.
- Automacao segura para alternar presets, aplicar por horario e preparar ativacao ao iniciar.
- Sistema de logs em tempo real.
- Configuracao pronta para empacotar em `.exe` com PyInstaller.

## Estrutura

```text
main.py
app/
  ui/
  core/
  services/
  database/
  assets/
  utils/
  integrations/
README.md
requirements.txt
discord_rich_presence_studio.spec
```

## Instalacao

Requisitos:

- Python 3.10 ou superior
- Discord desktop aberto
- Uma aplicacao criada no Discord Developer Portal

Crie um ambiente virtual:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Instale as dependencias:

```powershell
pip install -r requirements.txt
```

Rode o app:

```powershell
python main.py
```

## Como criar a aplicacao no Discord

1. Acesse `https://discord.com/developers/applications`.
2. Clique em `New Application`.
3. Dê um nome para a aplicacao.
4. Copie o `Application ID`.
5. Cole esse ID na aba `Conexao Discord` do app.
6. Mantenha o Discord desktop aberto e clique em `Conectar`.

## Como configurar imagens/assets

1. No Discord Developer Portal, abra sua aplicacao.
2. Entre em `Rich Presence`.
3. Envie imagens em `Art Assets`.
4. Use o nome exato do asset nos campos `Imagem grande` e `Imagem pequena`.
5. Aguarde alguns minutos se o Discord ainda nao exibir o asset novo.

Exemplo:

- Asset enviado com nome `studio`
- Campo `Imagem grande`: `studio`

## Botoes

O Discord permite ate dois botoes por Rich Presence. Cada botao precisa de:

- Texto
- URL completa, como `https://github.com/seu-usuario`

## Presets

Os presets ficam salvos em:

```text
data/presets.json
```

Esse arquivo e criado automaticamente na primeira execucao.

## Automacao segura

A aba `Automacao Segura` inclui somente recursos locais permitidos:

- Alternar entre presets salvos.
- Trocar presenca a cada X minutos.
- Aplicar presenca atual em um horario configurado.
- Preparar ativacao ao iniciar o aplicativo.

O app nao controla conta de usuario, nao usa token, nao envia mensagens e nao automatiza acoes dentro do Discord.

## Empacotar como EXE

Com as dependencias instaladas, execute:

```powershell
pyinstaller discord_rich_presence_studio.spec
```

O executavel sera gerado em:

```text
dist/Discord Rich Presence Studio/Discord Rich Presence Studio.exe
```

Abra somente o executavel dentro de `dist`. A pasta `build` e intermediaria do PyInstaller e o executavel de la pode falhar ao encontrar DLLs.

Tambem e possivel gerar direto:

```powershell
pyinstaller --noconfirm --windowed --name "Discord Rich Presence Studio" main.py
```

Para gerar um unico `.exe`, use:

```powershell
pyinstaller --noconfirm --clean --windowed --onefile --name "Discord Rich Presence Studio" --hidden-import pypresence --distpath dist-onefile main.py
```

## Arquitetura

- `app/core`: modelos e temas.
- `app/services`: Discord RPC e automacao local segura.
- `app/database`: persistencia de presets.
- `app/ui`: telas, componentes e estilos PySide6.
- `app/integrations`: adapters futuros para servicos externos.
- `app/utils`: logger central da aplicacao.

## Observacoes importantes

- Rich Presence funciona pelo Discord desktop, nao pelo navegador.
- O Client ID e publico e nao e um token secreto.
- Se a conexao falhar, confirme que o Discord esta aberto.
- Assets podem levar alguns minutos para aparecer depois do upload.
