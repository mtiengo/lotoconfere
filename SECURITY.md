# Segurança

## Como relatar uma falha

**Não abra uma issue pública.** Uma issue é visível para qualquer pessoa, inclusive para quem
quiser usar a falha antes da correção.

Use o canal privado do GitHub: vá em
[Security → Report a vulnerability](https://github.com/mtiengo/lotoconfere/security/advisories/new).
Só você e o mantenedor enxergam o relato.

Conte o que você encontrou, como reproduzir, e qual versão do LotoConfere e qual sistema
operacional você usou. Se precisar de um arquivo para demonstrar o problema, anexe no próprio
relato.

Você recebe uma resposta assim que o mantenedor ler. Este é um projeto sem fins lucrativos,
mantido por uma pessoa nas horas vagas: não há prazo garantido e não há recompensa em dinheiro.

## O que interessa

O LotoConfere não tem contas, não tem senhas e não envia nada sobre você para lugar nenhum. O que
sobra, e que interessa em um relato:

- Qualquer coisa que faça o programa executar código a partir de uma resposta da internet.
- Qualquer coisa que faça um arquivo de apostas importado escrever fora do lugar dele, abrir
  conexões ou executar algo.
- Qualquer caminho em que o programa aceite um endereço diferente dos dois que ele conhece (o
  portal da Caixa e o espelho da comunidade).
- Qualquer falha na verificação do certificado das conexões.

## O que já é conhecido, e não é falha

- **Os instaladores não são assinados.** É uma decisão do projeto. Por isso cada release publica
  um arquivo `.sha256`, e o [README](README.md) explica como conferir.
- **O programa não se atualiza sozinho.** Também é uma decisão. Novas versões saem na página de
  Releases.
- **A API da Caixa não é documentada e pode mudar sem aviso.** Quando uma resposta não faz
  sentido, o LotoConfere recusa em vez de adivinhar. Isso é o comportamento esperado.

## Versões

Só a última versão publicada recebe correção.
