<?php
/**
 * MOFADO MU — camada de dados (MS SQL Server / base MuOnline 0.97k).
 *
 * Três regras que valem para tudo aqui dentro:
 *
 *  1. NADA de concatenar variável em SQL. Sempre prepare()/execute([...]).
 *     A única coisa interpolada é nome de coluna, e ele passa por lista branca.
 *
 *  2. Todo SELECT leva WITH (NOLOCK). Esta base está sendo escrita pelo
 *     GameServer AGORA. Um SELECT sem NOLOCK no ranking já derrubou servidor:
 *     o site trava a tabela Character e o GS engasga no save de personagem.
 *     Ranking desatualizado por 1 minuto não mata ninguém; lock mata.
 *
 *  3. Consulta de ranking passa por cache em arquivo (CACHE_SEGUNDOS).
 *     Cem visitantes por minuto não podem virar cem varreduras na Character.
 */
declare(strict_types=1);

require_once __DIR__ . '/config.php';

/* ================================================================== *
 * 1. CONEXÃO
 * ================================================================== */

/**
 * Conexão PDO única por requisição (lazy: só abre se alguém pedir).
 * Retorna null se o banco estiver fora — o site continua de pé, mostrando
 * "manutenção" nos módulos, em vez de dar tela branca.
 */
function db(): ?PDO
{
    static $pdo = null;
    static $tentou = false;

    if ($tentou) {
        return $pdo;
    }
    $tentou = true;

    try {
        if (DB_DRIVER === 'dblib') {
            $dsn = 'dblib:host=' . DB_HOST . ';dbname=' . DB_NOME . ';charset=UTF-8';
        } else {
            $dsn = 'sqlsrv:Server=' . DB_HOST . ';Database=' . DB_NOME
                 . ';TrustServerCertificate=1;LoginTimeout=5';
        }

        $pdo = new PDO($dsn, DB_USER, DB_SENHA, [
            PDO::ATTR_ERRMODE            => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
            PDO::ATTR_EMULATE_PREPARES   => false,
        ]);
    } catch (Throwable $erro) {
        $pdo = null;
        erro_log('conexao', $erro);
    }

    return $pdo;
}

/** Erro nunca vai para a tela do jogador — vai para o log do PHP. */
function erro_log(string $onde, Throwable $erro): void
{
    error_log('[MOFADO/' . $onde . '] ' . $erro->getMessage());
    if (MODO_DEBUG) {
        echo '<pre style="color:#e8434c">[' . e($onde) . '] '
           . e($erro->getMessage()) . '</pre>';
    }
}

/** SELECT preparado com tratamento de erro. Devolve [] se algo falhar. */
function consulta(string $sql, array $params = []): array
{
    $pdo = db();
    if (!$pdo) {
        return [];
    }
    try {
        $st = $pdo->prepare($sql);
        $st->execute($params);
        return $st->fetchAll();
    } catch (Throwable $erro) {
        erro_log('consulta', $erro);
        return [];
    }
}

/* ================================================================== *
 * 2. LISTA BRANCA DE COLUNAS
 * ================================================================== *
 * COL_RESET vem do config.php, que é um arquivo seu — mas se um dia esse
 * valor passar a vir de um painel admin, esta função é a barreira que
 * impede "Resets; DROP TABLE" de virar SQL.
 */
function coluna_segura(string $coluna, string $padrao): string
{
    $permitidas = [
        'Resets', 'Reset', 'ResetCount', 'RESETS',
        'MasterResets', 'MResets', 'GrandResets', 'MasterReset',
    ];
    return in_array($coluna, $permitidas, true) ? $coluna : $padrao;
}

/* ================================================================== *
 * 3. CACHE EM ARQUIVO
 * ================================================================== */
function cache_pega(string $chave, int $ttl, callable $produz): mixed
{
    if (!is_dir(CACHE_DIR)) {
        @mkdir(CACHE_DIR, 0775, true);
    }
    $arquivo = CACHE_DIR . '/' . preg_replace('/[^a-z0-9_]/i', '', $chave) . '.json';

    if (is_readable($arquivo) && (time() - filemtime($arquivo)) < $ttl) {
        $bruto = json_decode((string) file_get_contents($arquivo), true);
        if ($bruto !== null) {
            return $bruto;
        }
    }

    $valor = $produz();
    // LOCK_EX evita dois visitantes simultâneos gravarem JSON pela metade.
    @file_put_contents($arquivo, json_encode($valor), LOCK_EX);
    return $valor;
}

/* ================================================================== *
 * 4. CLASSES DO 0.97k
 * ================================================================== *
 * Character.Class é tinyint. No 0.97k só existem estes sete valores —
 * Dark Lord, Summoner e as classes de Season vieram muito depois.
 */
function classe_info(int $classe): array
{
    return match (true) {
        $classe === 0  => ['DW',  'Dark Wizard',     'mago'],
        $classe === 1  => ['SM',  'Soul Master',     'mago'],
        $classe === 16 => ['DK',  'Dark Knight',     'guerreiro'],
        $classe === 17 => ['BK',  'Blade Knight',    'guerreiro'],
        $classe === 32 => ['FE',  'Fairy Elf',       'elfa'],
        $classe === 33 => ['ME',  'Muse Elf',        'elfa'],
        $classe === 48 => ['MG',  'Magic Gladiator', 'gladiador'],
        default        => ['???', 'Desconhecida',    'mago'],
    };
}

/* ================================================================== *
 * 5. STATUS DO SERVIDOR
 * ================================================================== */

/**
 * Bate na porta do GameServer e do ConnectServer.
 * fsockopen com timeout curto: se o GS caiu, o site não pode congelar
 * 30 segundos esperando. 1,5 s já responde a pergunta.
 */
function servidor_status(): array
{
    return cache_pega('status', STATUS_SEGUNDOS, function (): array {
        $porta = function (string $host, int $porta): bool {
            $con = @fsockopen($host, $porta, $n, $s, 1.5);
            if ($con) {
                fclose($con);
                return true;
            }
            return false;
        };
        return [
            'game'    => $porta(GS_HOST, GS_PORTA),
            'connect' => $porta(GS_HOST, CS_PORTA),
        ];
    });
}

/**
 * Jogadores conectados. MEMB_STAT.ConnectStat = 1 é a fonte canônica:
 * o GameServer escreve 1 no login e 0 no logout.
 *
 * Atenção: em queda feia do GS as linhas ficam presas em 1 e o número
 * infla. O filtro por ConnectTM descarta sessões abertas há mais de 24 h,
 * que são sempre lixo de crash.
 */
function jogadores_online(): int
{
    return (int) cache_pega('online', STATUS_SEGUNDOS, function (): int {
        $r = consulta(
            "SELECT COUNT(*) AS total
               FROM MEMB_STAT WITH (NOLOCK)
              WHERE ConnectStat = 1
                AND (ConnectTM IS NULL OR ConnectTM > DATEADD(hour, -24, GETDATE()))"
        );
        return (int) ($r[0]['total'] ?? 0);
    });
}

/**
 * Recorde de online. Guardado em arquivo de propósito: não exige coluna
 * nova na base do jogo, e a base do Render/host pode ser recriada sem
 * levar o recorde junto.
 */
function recorde_online(int $agora): array
{
    $arquivo = CACHE_DIR . '/recorde.json';
    $rec = ['total' => 0, 'quando' => null];

    if (is_readable($arquivo)) {
        $lido = json_decode((string) file_get_contents($arquivo), true);
        if (is_array($lido)) {
            $rec = $lido + $rec;
        }
    }

    if ($agora > (int) $rec['total']) {
        $rec = ['total' => $agora, 'quando' => date('d/m/Y H:i')];
        if (!is_dir(CACHE_DIR)) {
            @mkdir(CACHE_DIR, 0775, true);
        }
        @file_put_contents($arquivo, json_encode($rec), LOCK_EX);
    }

    return $rec;
}

/** Total de contas cadastradas — número de vitrine do topo. */
function total_contas(): int
{
    return (int) cache_pega('contas', 300, function (): int {
        $r = consulta("SELECT COUNT(*) AS total FROM MEMB_INFO WITH (NOLOCK)");
        return (int) ($r[0]['total'] ?? 0);
    });
}

/* ================================================================== *
 * 6. RANKINGS
 * ================================================================== */

/**
 * Top resets.
 *
 * Desempate em três níveis, e a ordem importa:
 *   Resets → cLevel → Experience.
 * Sem o terceiro critério, dois personagens com mesmo reset e mesmo nível
 * trocam de posição a cada F5 (o SQL Server não garante ordem estável),
 * e o jogador jura que o site está bugado.
 *
 * Filtros: CtlCode = 0 tira GM e admin do pódio; bloc_code = '0' tira
 * conta banida — nada mais constrangedor que um banido em primeiro lugar.
 */
function top_resets(int $limite = RANKING_TOPO, bool $master = false): array
{
    $col = $master
        ? coluna_segura(COL_MRESET, 'MasterResets')
        : coluna_segura(COL_RESET, 'Resets');
    $limite = max(1, min(100, $limite));
    $chave  = 'rank_' . ($master ? 'mreset' : 'reset') . '_' . $limite;

    return cache_pega($chave, CACHE_SEGUNDOS, function () use ($col, $limite): array {
        return consulta(
            "SELECT TOP {$limite}
                    c.Name          AS nome,
                    c.cLevel        AS nivel,
                    c.Class         AS classe,
                    c.[{$col}]      AS pontos,
                    c.PkCount       AS pk,
                    g.G_Name        AS guild
               FROM [Character] c WITH (NOLOCK)
               JOIN MEMB_INFO m   WITH (NOLOCK) ON m.memb___id = c.AccountID
          LEFT JOIN GuildMember gm WITH (NOLOCK) ON gm.Name    = c.Name
          LEFT JOIN Guild g        WITH (NOLOCK) ON g.G_Name   = gm.G_Name
              WHERE c.CtlCode = 0
                AND m.bloc_code = '0'
           ORDER BY c.[{$col}] DESC, c.cLevel DESC, c.Experience DESC"
        );
    });
}

/**
 * Top guilds por pontuação de Castle Siege (G_Score).
 * A contagem de membros vem por subconsulta correlacionada em vez de
 * GROUP BY: a Guild tem dezenas de linhas, a GuildMember tem milhares, e
 * o plano fica mais barato varrendo a menor.
 */
function top_guilds(int $limite = RANKING_TOPO): array
{
    $limite = max(1, min(100, $limite));

    return cache_pega('rank_guild_' . $limite, CACHE_SEGUNDOS, function () use ($limite): array {
        return consulta(
            "SELECT TOP {$limite}
                    g.G_Name   AS nome,
                    g.G_Master AS mestre,
                    g.G_Score  AS pontos,
                    (SELECT COUNT(*) FROM GuildMember gm WITH (NOLOCK)
                      WHERE gm.G_Name = g.G_Name) AS membros,
                    (SELECT TOP 1 c.Class FROM [Character] c WITH (NOLOCK)
                      WHERE c.Name = g.G_Master)  AS classe
               FROM Guild g WITH (NOLOCK)
           ORDER BY g.G_Score DESC, g.G_Name ASC"
        );
    });
}

/**
 * Top killers. PkCount > 0 evita listar meio servidor empatado em zero
 * quando ninguém matou ninguém ainda (servidor recém-aberto).
 */
function top_killers(int $limite = RANKING_TOPO): array
{
    $col    = coluna_segura(COL_RESET, 'Resets');
    $limite = max(1, min(100, $limite));

    return cache_pega('rank_pk_' . $limite, CACHE_SEGUNDOS, function () use ($col, $limite): array {
        return consulta(
            "SELECT TOP {$limite}
                    c.Name     AS nome,
                    c.cLevel   AS nivel,
                    c.Class    AS classe,
                    c.PkCount  AS pontos,
                    c.PkLevel  AS pklevel,
                    g.G_Name   AS guild
               FROM [Character] c WITH (NOLOCK)
               JOIN MEMB_INFO m   WITH (NOLOCK) ON m.memb___id = c.AccountID
          LEFT JOIN GuildMember gm WITH (NOLOCK) ON gm.Name    = c.Name
          LEFT JOIN Guild g        WITH (NOLOCK) ON g.G_Name   = gm.G_Name
              WHERE c.CtlCode = 0
                AND m.bloc_code = '0'
                AND c.PkCount > 0
           ORDER BY c.PkCount DESC, c.cLevel DESC"
        );
    });
}

/* ================================================================== *
 * 7. CADASTRO DE CONTA
 * ================================================================== */

/**
 * A senha é gravada no formato que o GameServer sabe ler.
 * Veja o comentário longo em config.php sobre por que não há bcrypt aqui.
 */
function senha_para_banco(string $senha): string
{
    return SENHA_MODO === 'md5' ? md5($senha) : $senha;
}

/** Já existe alguém com este login? */
function conta_existe(string $login): bool
{
    $r = consulta(
        "SELECT TOP 1 1 AS x FROM MEMB_INFO WITH (NOLOCK) WHERE memb___id = ?",
        [$login]
    );
    return !empty($r);
}

/** Já existe alguém com este e-mail? */
function email_existe(string $email): bool
{
    $r = consulta(
        "SELECT TOP 1 1 AS x FROM MEMB_INFO WITH (NOLOCK) WHERE mail_addr = ?",
        [$email]
    );
    return !empty($r);
}

/**
 * Cria a conta em MEMB_INFO.
 *
 * O esquema original do MuOnline declara quase tudo NOT NULL sem DEFAULT
 * (post_code, addr_info, tel__numb, fax__numb...). Se você omitir essas
 * colunas o INSERT falha com "cannot insert NULL". Por isso a lista abaixo
 * é longa e cheia de string vazia: não é entulho, é o que a tabela exige.
 *
 * A chave de segurança de 7 dígitos vai em sno__numb (char(13)),
 * preenchida com zeros à esquerda — é onde os painéis de MuOnline
 * historicamente guardam esse PIN.
 *
 * memb_guid é IDENTITY na maioria dos repacks e por isso não aparece aqui.
 * Se o seu INSERT reclamar de memb_guid, a coluna não é identity na sua
 * base — rode: DBCC CHECKIDENT ou recrie a tabela com IDENTITY(1,1).
 */
function criar_conta(string $login, string $senha, string $email, string $chave): bool
{
    $pdo = db();
    if (!$pdo) {
        return false;
    }

    try {
        $st = $pdo->prepare(
            "INSERT INTO MEMB_INFO
                (memb___id, memb__pwd, memb_name, sno__numb, mail_addr,
                 post_code, addr_info, addr_detail, tel__numb, phon_numb,
                 fax__numb, mail_chek, bloc_code, ctl1_code, appl_days)
             VALUES
                (?, ?, ?, ?, ?,
                 '', '', '', '', '',
                 '', '0', '0', '0', GETDATE())"
        );

        return $st->execute([
            $login,
            senha_para_banco($senha),
            $login,                                   // memb_name: varchar(10), mesmo do login
            str_pad($chave, 13, '0', STR_PAD_LEFT),   // sno__numb: char(13)
            $email,
        ]);
    } catch (Throwable $erro) {
        erro_log('criar_conta', $erro);
        return false;
    }
}
