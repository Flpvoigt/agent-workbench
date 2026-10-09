# Agent Workbench

Aplicativo desktop local para acompanhar sessões do Codex, processos ativos, repositórios Git e pull requests do GitHub.

## Recursos

- Exibe agents e repositórios em um mapa operacional animado.
- Conecta cada sessão ao repositório correspondente usando o diretório real da sessão.
- Mostra arquivos recentes circulando pelas conexões e a ferramenta atualmente em uso.
- Abre um inspector funcional ao selecionar um agent ou repositório.
- Retoma sessões em uma nova janela com `codex resume`.
- Descobre automaticamente repositórios relacionados às sessões e monitora branch, alterações e PRs.
- Permite pausar a animação sem interromper a coleta de dados.
- Mantém configuração local fora do Git em `~/.agent-workbench/config.json`.
- Funciona sem servidor web e sem dependências Python externas.

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

