# Changelog

Todas as mudanças importantes deste projeto são anotadas aqui.

O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/), e as versões seguem
o [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [0.1.0-rc.3] - 2026-10-03

### Adicionado

- Várias apostas na mesma tela, cada uma no seu volante, conferidas e salvas de uma vez.

### Corrigido

- Apostas salvas de Dia de Sorte, Timemania, +Milionária e Super Sete agora guardam o mês, o
  time, os trevos e as colunas. Apostas desses jogos salvas na versão anterior abrem sem esses
  dados e não são conferidas: salve-as de novo.
- O ícone da lixeira, que remove uma aposta da tela, ficou mais fácil de reconhecer.

## [0.1.0-rc.2] - 2026-09-27

Primeira versão de teste.

### Adicionado

- Conferência de uma aposta contra um concurso, nos nove jogos de números.
- Conferência da mesma aposta em vários concursos seguidos (teimosinha), com o resultado de cada
  concurso e um resumo.
- Apostas salvas com nome, com exportação e importação em JSON.
- Resultados guardados no computador, para conferir de novo sem internet.
