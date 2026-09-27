# Como contribuir

Obrigado pelo interesse. Este é um projeto pequeno e sem fins lucrativos.

Antes de escrever código para uma mudança grande, abra uma issue para conversar. É chato escrever
algo que não vai entrar.

## Ambiente

```
python -m pip install -e ".[dev]" -c constraints.txt
```

Python 3.12 ou mais novo.

## Antes de abrir um pull request

Os cinco comandos precisam passar:

```
ruff check . && ruff format --check . && mypy && pytest --cov && pip-audit
```

A cobertura de testes é de 100% e não desce. Se uma linha não tem como ser executada, marque com
`# pragma: no cover` e escreva o motivo ao lado.

Os testes não acessam a internet. Os testes marcados com `live` acessam, e ficam de fora da
execução normal: eles existem para detectar mudanças na API da Caixa e são rodados à mão com
`pytest -m live`.

## Idioma

- O que o usuário lê é em português: textos da interface, mensagens de erro, documentação.
- O resto é em inglês: nomes de variáveis, comentários, docstrings e mensagens de commit.

## Commits

Um commit por mudança. Prefixo de tipo e assunto em minúsculas, até 72 caracteres:

```
feat: salvar e abrir uma aposta
```

Tipos: `feat`, `fix`, `test`, `docs`, `build`, `ci`, `chore`.

## Valores dos jogos

Faixa de números, tamanhos de aposta e faixas de premiação saem **da página oficial daquele jogo
no site da Caixa**, e de nenhuma outra fonte. Cada jogo registra no código o endereço da página e
a data em que ela foi lida.

Se a página oficial não for clara sobre um valor, pergunte na issue em vez de deduzir. Uma faixa
de premiação errada faz o programa dar uma resposta errada com toda a confiança, que é pior do que
não responder.
