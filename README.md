# LotoConfere

Confira suas apostas das loterias da Caixa contra os resultados oficiais. Em um concurso ou em
uma teimosinha, com o resultado de cada concurso separado.

> **Aviso:** este projeto não tem nenhuma relação com a Caixa Econômica Federal. Os resultados são
> lidos do portal de loterias da Caixa, mas a conferência aqui é apenas informativa. Confirme
> sempre nos canais oficiais da Caixa antes de considerar qualquer aposta premiada.

> **[falta captura de tela: janela principal do LotoConfere, com uma aposta conferida]**

## O que ele faz

- Confere uma aposta contra um concurso.
- Confere a mesma aposta em vários concursos seguidos (teimosinha), mostrando o resultado de cada
  um e um resumo no fim.
- Guarda apostas com nome, para você conferir de novo depois.
- Funciona sem internet com tudo o que já foi baixado antes.

Os nove jogos de números: Mega-Sena, Lotofácil, Quina, Lotomania, Timemania, Dupla Sena, Dia de
Sorte, Super Sete e +Milionária.

## O que ele não faz

- Não registra apostas e não faz pagamentos.
- Não dá palpites, não gera números e não mostra estatísticas.
- Não promete prêmio. Os valores exibidos são os valores brutos que a Caixa publicou para aquele
  concurso, sem nenhum cálculo de imposto.
- Não envia nada sobre você para lugar nenhum.

Quando o LotoConfere não tem certeza de alguma coisa, ele diz isso em vez de chutar. Um concurso
que ainda não foi sorteado aparece como não sorteado, e um resultado que não pôde ser baixado
aparece como indisponível. Nenhum dos dois é contado como zero acertos.

## Instalação

Os instaladores ficam na [página de
Releases](https://github.com/mtiengo/lotoconfere/releases). Baixe o arquivo do seu sistema.

O LotoConfere não é assinado digitalmente. Isso é uma decisão do projeto, que é sem fins
lucrativos: a assinatura custa caro e não deixaria o programa mais seguro para você. O efeito é
que cada sistema mostra um aviso na primeira vez que você abre o programa. Abaixo está o que
esperar em cada um.

### Windows

1. Baixe `LotoConfere-<versão>-windows-x64-Setup.exe`.
2. Dê dois cliques. O Windows mostra uma tela azul do SmartScreen dizendo que não reconhece o
   programa.
3. Clique em **Mais informações** e depois em **Executar assim mesmo**.
4. Siga o instalador.

> **[falta captura de tela: aviso do SmartScreen, com o link "Mais informações" destacado]**

Sobre esse aviso, na documentação da Microsoft: [Proteger-se contra aplicativos potencialmente
indesejados](https://support.microsoft.com/pt-br/windows/proteger-se-contra-aplicativos-potencialmente-indesejados-c7668a25-174e-3b78-0191-faf0607f7a6e).

### macOS

1. Baixe o `.dmg` da sua arquitetura: **Apple Silicon** (Macs com chip M1 ou mais novo) ou
   **Intel**.
2. Abra o `.dmg` e arraste o LotoConfere para a pasta Aplicativos.
3. Na primeira vez, o macOS bloqueia o programa e diz que não conseguiu verificar o
   desenvolvedor.
4. Abra **Ajustes do Sistema → Privacidade e Segurança**, role até o aviso sobre o LotoConfere e
   clique em **Abrir mesmo assim**.
5. Confirme no aviso seguinte.

Clicar com o botão direito e escolher Abrir **não funciona mais** a partir do macOS 15. O caminho
é o dos Ajustes do Sistema.

> **[falta captura de tela: Ajustes do Sistema, Privacidade e Segurança, botão "Abrir mesmo
> assim"]**
>
> **[falta link: página de ajuda da Apple sobre abrir apps de desenvolvedores não identificados]**

### Linux

1. Baixe `LotoConfere-<versão>-linux-x86_64.AppImage`.
2. Marque o arquivo como executável:

   ```
   chmod +x LotoConfere-*-linux-x86_64.AppImage
   ```

3. Abra o arquivo.

O que é um AppImage e como usá-lo: [documentação do
AppImage](https://docs.appimage.org/introduction/quickstart.html) (em inglês).

## Como conferir o que você baixou

Como os arquivos não são assinados, cada release publica junto um arquivo `.sha256`. Ele serve
para você verificar que o download não foi corrompido nem trocado no caminho.

Compare o resultado do comando com o conteúdo do arquivo `.sha256`. Os dois têm que ser iguais.

**Windows (PowerShell):**

```
Get-FileHash .\LotoConfere-0.1.0-windows-x64-Setup.exe -Algorithm SHA256
```

**macOS:**

```
shasum -a 256 LotoConfere-0.1.0-macos-arm64.dmg
```

**Linux:**

```
sha256sum LotoConfere-0.1.0-linux-x86_64.AppImage
```

## Problemas e sugestões

Abra uma issue em [github.com/mtiengo/lotoconfere/issues](https://github.com/mtiengo/lotoconfere/issues).
Conte o que você esperava, o que aconteceu, e qual jogo e concurso você estava conferindo.

Encontrou uma falha de segurança? Não abra uma issue pública. O caminho está em
[SECURITY.md](SECURITY.md).

## Para desenvolvedores

```
python -m pip install -e ".[dev]" -c constraints.txt
```

Python 3.12 ou mais novo. O resto está em [CONTRIBUTING.md](CONTRIBUTING.md).

## Licença

[MIT](LICENSE).

O LotoConfere usa Qt (via PySide6, sob LGPL) e as fontes Inter e JetBrains Mono (sob SIL Open Font
License). As licenças desses componentes são distribuídas junto com o programa.
