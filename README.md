# Agent Workbench

Aplicativo desktop local para acompanhar sessões do Codex, processos ativos, repositórios Git e pull requests do GitHub.

## Recursos do MVP

- Lista as sessões locais encontradas em `~/.codex/sessions`.
- Destaca sessões recentemente atualizadas como ativas.
- Retoma uma sessão selecionada em uma nova janela com `codex resume`.
- Monitora branch, alterações locais, remote e PRs dos repositórios adicionados.
- Abre o repositório no Explorador de Arquivos.
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

