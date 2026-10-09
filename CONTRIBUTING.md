# Contribuição

## Regra principal

Nenhuma alteração deve ser aplicada diretamente à branch `main`. Todo trabalho deve acontecer em uma branch curta e ser mesclado por pull request.

## Fluxo

1. Atualize a `main` local.
2. Crie uma branch com prefixo `feat/`, `fix/`, `docs/`, `test/` ou `chore/`.
3. Faça alterações pequenas e verificáveis.
4. Execute `python -m unittest discover -s tests -v`.
5. Crie commits com mensagem objetiva.
6. Inclua Gustavo como coautor em cada commit:

```text
Co-authored-by: GustavoLoes <gustavoloes7@gmail.com>
```

7. Envie a branch e abra um pull request.
8. Mescle somente após os testes passarem e a revisão ser concluída.

## Pull requests

O PR deve explicar o problema, a solução, como foi testada e eventuais riscos. Prefira squash merge para manter o histórico da `main` conciso, preservando o trailer de coautoria na mensagem final.

