"""Every word the user reads, in one place. Brazilian Portuguese.

There is no i18n framework and there is not meant to be one: one module is
enough to read the whole voice of the app at once and keep it consistent.

The wording rules that matter, because getting them wrong tells someone they did
not win when they did:

* **Pending and unavailable are different sentences**, and neither is "0
  acertos". A contest that has not been drawn has no result; one that could not
  be downloaded has an unknown result.
* **Prizes are Caixa's published gross values.** A tier nobody won says so
  instead of printing R$ 0,00.
* **Plain words.** No exclamation marks, no slang, no celebration. The app
  checks; it does not congratulate.
"""

from datetime import date, datetime
from decimal import Decimal

APP_NAME = "LotoConfere"

# --- lobby ----------------------------------------------------------------------

LOBBY_PROMPT = "Escolha o jogo que você quer conferir."
CHECK_ALL = "Conferir todas as apostas salvas"
SAVED_COUNT_NONE = "Nenhuma aposta salva"
SAVED_COUNT_ONE = "1 aposta salva"
SAVED_COUNT_MANY = "{count} apostas salvas"
ABOUT = "Sobre"
SETTINGS = "Configurações"

# --- the game screen --------------------------------------------------------------

BACK = "Voltar"
SAVED_BET = "Apostas salvas"
NEW_BET = "— novas apostas —"
CONTEST = "Concurso"
LATEST_CONTEST = "Último concurso"
TEIMOSINHA = "Teimosinha"
CONTESTS_WORD = "concursos"
CHECK = "Conferir"
CANCEL = "Cancelar"
CHECKING = "Consultando…"
CHECKING_CONTEST = "Consultando o concurso {contest}…"
CLEAR = "Limpar"
MIRROR_BET = "Gerar aposta-espelho"
BET_NUMBER = "Aposta {number}"
ADD_BET = "Adicionar outra aposta"
REMOVE_BET = "Remover esta aposta"
TYPED_HINT = "Ou digite os números separados por espaço"

CHOSEN_COUNT = "{chosen} de {needed} números escolhidos"
CHOSEN_RANGE = "{chosen} números escolhidos (de {low} a {high})"
COLUMN_TITLE = "Coluna {number}"
COLUMN_HINT = "Escolha ao menos um número em cada coluna."
CLOVERS = "Trevos"
TEAM = "Time do Coração"
MONTH = "Mês de Sorte"

# --- saved bets --------------------------------------------------------------------

SAVE_BET = "Salvar apostas"
BET_NAME = "Nome para estas apostas"
DELETE_BET = "Excluir"
EXPORT_BETS = "Exportar apostas"
IMPORT_BETS = "Importar apostas"
BET_SAVED = "Apostas salvas."
BET_DELETED = "Apostas excluídas."
BETS_EXPORTED = "{count} apostas exportadas."
BETS_IMPORTED = "{count} apostas importadas."
NAME_REQUIRED = "Dê um nome para as apostas antes de salvar."

# --- results -------------------------------------------------------------------------

HITS = "{count} acertos"
ONE_HIT = "1 acerto"
NO_HITS = "Nenhum acerto"
PRIZED = "PREMIADO"
NOT_DRAWN = "Ainda não sorteado"
UNAVAILABLE = "Não foi possível consultar"
NO_WINNER_IN_TIER = "Não houve ganhador nessa faixa"
PRIZE_NOT_PUBLISHED = "Prêmio ainda não divulgado"
FROM_CAIXA = "Caixa"
FROM_MIRROR = "Espelho da comunidade"
MIRROR_WARNING = "Resultado do espelho da comunidade, não confirmado pela Caixa."
FIRST_DRAW = "1º sorteio"
SECOND_DRAW = "2º sorteio"
TIMES = "×{count}"  # noqa: RUF001 (a real multiplication sign, not an x)

RUN_SUMMARY = "Conferidos {checked} de {total}"
RUN_PENDING = "{count} ainda não sorteados"
RUN_UNAVAILABLE = "{count} não consultados"
RUN_PRIZED = "{count} premiados"
RUN_CANCELLED = "Conferência interrompida."

OFFLINE_NOTICE = "Mostrando resultados salvos, atualizados em {when}."
NEVER_UPDATED = "Nenhum resultado baixado ainda."

# --- errors -------------------------------------------------------------------------

ERROR_TITLE = "Não deu certo"
NO_CONNECTION = "Não foi possível conectar ao site da Caixa."
NO_CERTIFICATE = "Não foi possível verificar a conexão segura com a Caixa."
TIMED_OUT = "A Caixa não respondeu a tempo."
INVALID_BET = "Esta aposta não pode ser conferida: {reason}"
IMPORT_FAILED = "Não foi possível importar o arquivo: {reason}"
EXPORT_FAILED = "Não foi possível salvar o arquivo: {reason}"

# --- settings -------------------------------------------------------------------------

USE_MIRROR_LABEL = "Usar o espelho da comunidade quando a Caixa não responder"
USE_MIRROR_HELP = (
    "O espelho é mantido por voluntários e pode estar desatualizado. "
    "Um resultado vindo dele aparece marcado."
)

# --- about ---------------------------------------------------------------------------

ABOUT_DISCLAIMER = (
    "O LotoConfere não tem nenhuma relação com a Caixa Econômica Federal. "
    "A conferência aqui é informativa: confirme sempre nos canais oficiais da Caixa."
)
ABOUT_VERSION = "Versão {version}"
ABOUT_RELEASES = "Novas versões: https://github.com/mtiengo/lotoconfere/releases"
ABOUT_LICENCE = "LotoConfere é software livre, sob a licença MIT."
ABOUT_COMPONENTS = "Componentes de terceiros"

# --- formatting ------------------------------------------------------------------------


def money(value: Decimal) -> str:
    """R$ 1.234,56 -- Brazilian grouping and decimal marks, always two places."""
    quantised = f"{value:,.2f}"
    swapped = quantised.replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return f"R$ {swapped}"


def day(value: date) -> str:
    """dd/mm/yyyy."""
    return value.strftime("%d/%m/%Y")


def moment(value: datetime) -> str:
    """dd/mm/yyyy hh:mm, in the reader's own time zone."""
    return value.astimezone().strftime("%d/%m/%Y %H:%M")


def hits(count: int) -> str:
    """Nenhum acerto / 1 acerto / 4 acertos. Singular is not a case to forget."""
    if count == 0:
        return NO_HITS
    if count == 1:
        return ONE_HIT
    return HITS.format(count=count)


def saved_count(count: int) -> str:
    if count == 0:
        return SAVED_COUNT_NONE
    if count == 1:
        return SAVED_COUNT_ONE
    return SAVED_COUNT_MANY.format(count=count)
