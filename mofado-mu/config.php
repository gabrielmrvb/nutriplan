<?php
/**
 * MOFADO MU — configuração central.
 *
 * Este é o ÚNICO arquivo que você precisa editar para colocar o site no ar.
 * Nada aqui é impresso na tela: db.php e as páginas leem daqui.
 */
declare(strict_types=1);

/* ------------------------------------------------------------------ *
 * 1. AMBIENTE
 * ------------------------------------------------------------------ */
const MODO_DEBUG = false;   // true SOMENTE na sua máquina. Em produção vaza SQL.

date_default_timezone_set('America/Sao_Paulo');
mb_internal_encoding('UTF-8');

if (MODO_DEBUG) {
    ini_set('display_errors', '1');
    error_reporting(E_ALL);
} else {
    ini_set('display_errors', '0');
    error_reporting(E_ALL & ~E_DEPRECATED & ~E_NOTICE);
}

/* Sessão endurecida: cookie inacessível ao JS, só no mesmo domínio. */
if (session_status() === PHP_SESSION_NONE) {
    session_set_cookie_params([
        'httponly' => true,
        'samesite' => 'Lax',
        'secure'   => (($_SERVER['HTTPS'] ?? '') === 'on'),
    ]);
    session_start();
}

/* ------------------------------------------------------------------ *
 * 2. BANCO — MS SQL Server (base MuOnline)
 * ------------------------------------------------------------------ */
const DB_HOST  = 'localhost';       // ou 'localhost\SQLEXPRESS' ou '127.0.0.1,1433'
const DB_NOME  = 'MuOnline';
const DB_USER  = 'sa';
const DB_SENHA = 'troque-esta-senha';

/**
 * Driver PDO. 'sqlsrv' é o oficial da Microsoft (Windows/IIS, ou Linux com
 * ODBC Driver 17+). 'dblib' é o FreeTDS — use só em Linux sem o driver da MS.
 */
const DB_DRIVER = 'sqlsrv';

/* ------------------------------------------------------------------ *
 * 3. COLUNAS QUE VARIAM ENTRE SERVER FILES
 * ------------------------------------------------------------------ *
 * Reset NÃO existe no 0.97k original — é coluna acrescentada pelo seu
 * repack, e cada um batiza de um jeito. Ajuste aqui uma vez.
 * db.php valida contra lista branca: não dá para injetar SQL por este campo.
 */
const COL_RESET  = 'Resets';        // Resets | Reset | ResetCount | RESETS
const COL_MRESET = 'MasterResets';  // MasterResets | MResets | GrandResets

/* ------------------------------------------------------------------ *
 * 4. SERVIDOR DO JOGO (para o "online/offline" do topo)
 * ------------------------------------------------------------------ */
const GS_HOST  = '127.0.0.1';
const GS_PORTA = 55901;   // GameServer
const CS_PORTA = 44405;   // ConnectServer

/* ------------------------------------------------------------------ *
 * 5. SENHA DA CONTA — leia antes de mudar
 * ------------------------------------------------------------------ *
 * O GameServer do 0.97k compara a senha DIRETO com MEMB_INFO.memb__pwd.
 * Ele não sabe o que é bcrypt. O site é obrigado a gravar no formato que
 * o GS espera, e no mundo 0.97k só existem dois:
 *
 *   'plain' → texto puro (padrão dos repacks antigos). Inseguro por
 *             natureza: quem lê a tabela lê todas as senhas.
 *   'md5'   → repacks com _ENCRYPT ligado.
 *
 * Não há opção segura aqui — a limitação é do emulador, não do site.
 * Mitigação real: base em rede privada (nunca porta 1433 exposta), senha
 * forte no 'sa', backup cifrado, e avisar o jogador para não reusar a
 * senha do e-mail. O aviso está impresso no formulário de cadastro.
 */
const SENHA_MODO = 'plain';   // 'plain' | 'md5'
const SENHA_MAX  = 10;        // memb__pwd é varchar(10). Pedir mais só frustra.

/* ------------------------------------------------------------------ *
 * 6. IDENTIDADE E RATES
 * ------------------------------------------------------------------ */
const SITE_NOME   = 'MOFADO MU';
const SITE_LEMA   = 'O 0.97k que você lembra — sem o que você odiava.';
const SITE_VERSAO = '0.97k';
const DISCORD_URL = 'https://discord.gg/mofadomu';
const CLIENTE_URL = 'https://mega.nz/troque-este-link';
const CLIENTE_TAM = '1,4 GB';

/** Cada item vira uma "runa" na seção de informações. */
const RATES = [
    ['rune' => 'exp',   'nome' => 'Experiência',   'valor' => '100x',       'nota' => 'Progressão média — dá para jogar depois do trabalho'],
    ['rune' => 'drop',  'nome' => 'Drop',          'valor' => '35%',        'nota' => 'Excellent controlado, no máximo 2 opções'],
    ['rune' => 'reset', 'nome' => 'Reset',         'valor' => 'Nível 400',  'nota' => 'Acumulativo · 500 pontos por reset'],
    ['rune' => 'zen',   'nome' => 'Zen por reset', 'valor' => '5.000.000',  'nota' => 'Descontado no /reset'],
    ['rune' => 'party', 'nome' => 'Party',         'valor' => 'Até 5',      'nota' => 'Bônus de EXP por membro em mapa'],
    ['rune' => 'guild', 'nome' => 'Guild',         'valor' => 'Nível 100',  'nota' => 'Aliança e Castle Siege liberados'],
];

/** Ligado/desligado — vira um interruptor físico no layout. */
const FLAGS = [
    ['nome' => 'Bug Bless',      'ligado' => false, 'nota' => 'Corrigido no GameServer'],
    ['nome' => 'Bug Post/Trade', 'ligado' => false, 'nota' => 'Corrigido'],
    ['nome' => 'PK livre',       'ligado' => true,  'nota' => 'Sem trava de PK fora das cidades'],
    ['nome' => 'Full Excellent', 'ligado' => false, 'nota' => 'Teto de 2 opções por item'],
];

const COMANDOS = [
    ['cmd' => '/reset',          'desc' => 'Reseta no nível 400 · 500 pontos acumulativos'],
    ['cmd' => '/addstr /addagi', 'desc' => 'Distribui pontos em lote'],
    ['cmd' => '/addvit /adden',  'desc' => 'Distribui pontos em lote'],
    ['cmd' => '/post <msg>',     'desc' => 'Anúncio global — custa 10.000 zen'],
    ['cmd' => '/pkclear',        'desc' => 'Limpa o status de assassino'],
    ['cmd' => '/guildcreate',    'desc' => 'Cria guild a partir do nível 100'],
];

/** Grade fixa de eventos. Horário de Brasília. */
const EVENTOS = [
    ['nome' => 'Blood Castle', 'horarios' => '00:30 · 04:30 · 08:30 · 12:30 · 16:30 · 20:30', 'nota' => 'Entrada pelo Archangel'],
    ['nome' => 'Devil Square', 'horarios' => '01:30 · 05:30 · 09:30 · 13:30 · 17:30 · 21:30', 'nota' => 'Charon, em Devias'],
    ['nome' => 'Chaos Castle', 'horarios' => '02:30 · 06:30 · 10:30 · 14:30 · 18:30 · 22:30', 'nota' => 'Só entra sem asas'],
    ['nome' => 'Invasão',      'horarios' => 'A cada 2 horas, na hora cheia',                 'nota' => 'Golden Dragon e White Wizard'],
];

/** Notícias do banner do Hero. */
const NOTICIAS = [
    ['tag' => 'Evento', 'titulo' => 'Semana do Ancião: drop de joias +50% até domingo', 'data' => '26/08/2026'],
    ['tag' => 'Patch',  'titulo' => 'Corrigido o duplicate de itens no Chaos Machine',  'data' => '22/08/2026'],
    ['tag' => 'Guild',  'titulo' => 'Castle Siege abre inscrições no sábado, 20h',      'data' => '19/08/2026'],
];

/* ------------------------------------------------------------------ *
 * 7. AJUSTES FINOS
 * ------------------------------------------------------------------ */
const CACHE_DIR       = __DIR__ . '/cache';
const CACHE_SEGUNDOS  = 60;   // ranking: 1 min. Poupa a base que o GS está usando.
const STATUS_SEGUNDOS = 30;   // online/offline: 30 s.
const RANKING_TOPO    = 5;    // "Top 5" — o pódio grande usa o primeiro colocado.
const CADASTRO_ESPERA = 60;   // segundos entre dois cadastros do mesmo IP.

/* ------------------------------------------------------------------ *
 * 8. AJUDANTES DE SAÍDA
 * ------------------------------------------------------------------ *
 * e() → tudo que vem do banco ou do usuário passa por aqui antes do HTML.
 * n() → número em pt-BR: 1.234.567 e 62,50. Nunca 1,234,567.
 */
function e(?string $texto): string
{
    return htmlspecialchars($texto ?? '', ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

function n(int|float|string|null $numero, int $casas = 0): string
{
    return number_format((float) $numero, $casas, ',', '.');
}

/** Token anti-CSRF: um por sessão, comparado com hash_equals (tempo constante). */
function csrf_token(): string
{
    if (empty($_SESSION['csrf'])) {
        $_SESSION['csrf'] = bin2hex(random_bytes(32));
    }
    return $_SESSION['csrf'];
}

function csrf_valido(?string $enviado): bool
{
    return is_string($enviado)
        && !empty($_SESSION['csrf'])
        && hash_equals($_SESSION['csrf'], $enviado);
}

/** Mensagem de uma requisição só (padrão POST → Redirect → GET). */
function flash_grava(string $tipo, string $msg): void
{
    $_SESSION['flash'] = ['tipo' => $tipo, 'msg' => $msg];
}

function flash_le(): ?array
{
    $f = $_SESSION['flash'] ?? null;
    unset($_SESSION['flash']);
    return $f;
}

/** IP real do visitante, respeitando proxy só se você confiar nele. */
function ip_visitante(): string
{
    return (string) ($_SERVER['REMOTE_ADDR'] ?? '0.0.0.0');
}
