# Agent Workbench

Aplicativo desktop local com interface HTML/CSS/SVG para acompanhar sessões do Codex, processos ativos, repositórios Git e pull requests do GitHub. A interface roda em uma janela nativa com pywebview, sem abrir uma aba do navegador.

## Recursos

- Exibe agents e repositórios em um Mission Control vetorial e animado.
- Permite reorganizar os blocos por arraste, mantendo o núcleo central fixo e as conexões atualizadas em tempo real.
- Conecta cada sessão ao repositório correspondente usando o diretório real da sessão.
- Mostra arquivos recentes circulando pelas conexões e a ferramenta atualmente em uso.
- Abre um inspector funcional ao selecionar um agent ou repositório.
- Retoma sessões em uma nova janela com `codex resume`.
- Descobre automaticamente repositórios relacionados às sessões e monitora branch, alterações e PRs.
- Permite pausar a animação sem interromper a coleta de dados.
- Agrupa sessões antigas, seleciona automaticamente o trabalho ativo e reduz o ruído visual.
- Oferece atalhos: `F5` atualiza, `Espaço` pausa o fluxo e `Esc` volta ao foco principal.
- Mantém configuração local fora do Git em `~/.agent-workbench/config.json`.
- Usa uma WebView local; nenhum conteúdo da interface é hospedado publicamente.

## Requisitos

- Windows 10 ou 11.
- Python 3.11 ou superior com Tkinter.
- Git no `PATH` para monitorar repositórios.
- Codex CLI no `PATH` para retomar sessões.
- GitHub CLI (`gh`) autenticado para listar pull requests.

## Executar

No PowerShell:

```powershell
cd C:\Users\Usuario\agent-workbench
.\run.ps1
```

Alternativamente:

```powershell
python -m pip install -e .
agent-workbench
```

## Desenvolvimento

```powershell
python -m unittest discover -s tests -v
```

Todas as alterações devem seguir o fluxo descrito em [CONTRIBUTING.md](CONTRIBUTING.md): branch dedicada, pull request e merge pela interface do GitHub.

## Privacidade

O aplicativo lê metadados locais das sessões e dos repositórios. Ele não envia conteúdo para nenhum servidor. A única comunicação externa ocorre quando o comando `gh` consulta pull requests no GitHub.

