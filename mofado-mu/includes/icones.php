<?php
/**
 * MOFADO MU — ícones desenhados à mão em SVG.
 *
 * Por que SVG inline e não uma fonte de ícones ou PNG:
 *   · zero requisição de rede (o site abre inteiro no primeiro pacote);
 *   · herda currentColor, então o emblema pega a cor da classe sozinho;
 *   · escala em tela retina e em ultrawide sem borrar.
 *
 * Todos usam viewBox 0 0 24 24 e stroke em currentColor.
 */
declare(strict_types=1);

/** Emblema por família de classe do 0.97k. */
function emblema_classe(string $familia): string
{
    $abre = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" '
          . 'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">';

    $corpo = match ($familia) {
        // Dark Wizard / Soul Master — cajado com orbe.
        'mago' => '<path d="M8 20 L17 6"/><circle cx="18" cy="4.4" r="2.4"/>'
                . '<path d="M13.6 9.6 L16 11"/><path d="M6.6 21.4 L9.4 18.6"/>'
                . '<path d="M4 8 l1 2 2 1 -2 1 -1 2 -1-2 -2-1 2-1z"/>',

        // Dark Knight / Blade Knight — espada com guarda larga.
        'guerreiro' => '<path d="M12 2 L12 15"/><path d="M6.5 15 L17.5 15"/>'
                     . '<path d="M12 15 L12 22"/><path d="M9.5 18.5 L14.5 18.5"/>'
                     . '<path d="M12 2 L14 5 L12 8 L10 5 Z"/>',

        // Fairy Elf / Muse Elf — arco com flecha.
        'elfa' => '<path d="M6 3 C15 6 15 18 6 21"/><path d="M6 3 L6 21"/>'
                . '<path d="M6 12 L20 12"/><path d="M16.5 8.5 L20 12 L16.5 15.5"/>',

        // Magic Gladiator — espada e cajado cruzados.
        'gladiador' => '<path d="M4 20 L15 5"/><path d="M20 20 L9 5"/>'
                     . '<circle cx="12" cy="13" r="2.2"/><path d="M2.6 21.4 L5.4 18.6"/>'
                     . '<path d="M21.4 21.4 L18.6 18.6"/>',

        // Guild — brasão.
        'guild' => '<path d="M12 2 L20 5.5 V12 C20 17 16.4 20.6 12 22 C7.6 20.6 4 17 4 12 V5.5 Z"/>'
                 . '<path d="M12 7.5 L13.6 10.7 L17 11.2 L14.5 13.7 L15.1 17.2 L12 15.5 '
                 . 'L8.9 17.2 L9.5 13.7 L7 11.2 L10.4 10.7 Z"/>',

        // Killer — caveira estilizada.
        'pk' => '<path d="M12 2 C7 2 4 5.4 4 10 C4 12.6 5.2 14 6.4 15 V18.6 '
              . 'C6.4 19.4 7 20 7.8 20 H16.2 C17 20 17.6 19.4 17.6 18.6 V15 '
              . 'C18.8 14 20 12.6 20 10 C20 5.4 17 2 12 2 Z"/>'
              . '<circle cx="9" cy="10.5" r="1.7"/><circle cx="15" cy="10.5" r="1.7"/>'
              . '<path d="M11 15 L13 15"/>',

        default => '<circle cx="12" cy="12" r="8"/>',
    };

    return $abre . $corpo . '</svg>';
}

/** Glifo de cada card de rate. */
function glifo_runa(string $nome): string
{
    $abre = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" '
          . 'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">';

    $corpo = match ($nome) {
        'exp'   => '<path d="M3 17 L9 11 L13 15 L21 6"/><path d="M15 6 L21 6 L21 12"/>',
        'drop'  => '<path d="M12 2.5 C12 2.5 5 10 5 14.5 A7 7 0 0 0 19 14.5 C19 10 12 2.5 12 2.5 Z"/>'
                 . '<path d="M9.5 14.5 A2.5 2.5 0 0 0 12 17"/>',
        'reset' => '<path d="M3.5 12 A8.5 8.5 0 1 1 6.6 18.6"/><path d="M3 14.5 L3.5 12 L6.4 12.8"/>'
                 . '<path d="M12 8 L12 12 L14.8 13.6"/>',
        'zen'   => '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5 L12 16.5"/>'
                 . '<path d="M9.4 10 H14.6"/><path d="M9.4 13.4 H14.6"/>',
        'party' => '<circle cx="8.5" cy="8.5" r="3"/><circle cx="16.5" cy="10" r="2.4"/>'
                 . '<path d="M2.8 19.5 C3.6 15.8 6 14 8.5 14 C11 14 13.4 15.8 14.2 19.5"/>'
                 . '<path d="M15.2 15 C17.6 14.6 20 15.9 21.2 19.5"/>',
        'guild' => '<path d="M12 2 L20 5.5 V12 C20 17 16.4 20.6 12 22 C7.6 20.6 4 17 4 12 V5.5 Z"/>'
                 . '<path d="M9 12 L11 14 L15.5 9.5"/>',
        default => '<circle cx="12" cy="12" r="8"/>',
    };

    return $abre . $corpo . '</svg>';
}

/** Ícone genérico da interface. */
function icone(string $nome): string
{
    $abre = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" '
          . 'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">';

    $corpo = match ($nome) {
        'download' => '<path d="M12 3 L12 15"/><path d="M7 10.5 L12 15.5 L17 10.5"/>'
                    . '<path d="M4 19.5 L20 19.5"/>',
        'usuario'  => '<circle cx="12" cy="8" r="4"/><path d="M4.5 20.5 C5.5 16 8.5 14 12 14 '
                    . 'C15.5 14 18.5 16 19.5 20.5"/>',
        'escudo'   => '<path d="M12 2.5 L19.5 5.6 V12 C19.5 16.6 16.2 20.2 12 21.5 '
                    . 'C7.8 20.2 4.5 16.6 4.5 12 V5.6 Z"/><path d="M9 12 L11 14 L15.5 9.5"/>',
        'alerta'   => '<path d="M12 3 L22 20 H2 Z"/><path d="M12 9.5 V14"/><circle cx="12" cy="17" r=".9" fill="currentColor" stroke="none"/>',
        'ok'       => '<circle cx="12" cy="12" r="9.2"/><path d="M8 12.4 L11 15.4 L16.2 9"/>',
        'copiar'   => '<rect x="9" y="9" width="11.5" height="11.5" rx="2.4"/>'
                    . '<path d="M15 5.5 A2.5 2.5 0 0 0 12.5 3 H6 A2.5 2.5 0 0 0 3.5 5.5 V13"/>',
        default    => '<circle cx="12" cy="12" r="8"/>',
    };

    return $abre . $corpo . '</svg>';
}

/**
 * Uma asa do logo — quatro penas em opacidades diferentes.
 * A pena de fora mais apagada dá profundidade sem custar um blur.
 *
 * A asa "direita" é a mesma geometria espelhada por scale(-1,1): metade
 * do desenho, simetria perfeita, e um arquivo menor.
 *
 * @param string $lado 'esquerda' ou 'direita'
 */
function asa_logo(string $lado = 'esquerda'): string
{
    $penas = '<path class="pena-fraca" d="M2 10 C11 9 21 6 31 1 C26 10 16 15 4 16 Z"/>'
           . '<path class="pena"       d="M4 17 C13 16 22 12.5 30 6 C27 15.5 18 21 6 22.5 Z"/>'
           . '<path class="pena"       d="M8 24 C16 23 24 19.5 30 13 C28.5 22 20 27.5 10 29 Z"/>'
           . '<path class="pena-fraca" d="M13 30 C20 29.5 26 27 30 22 C29 29 23 33.5 15 34.5 Z"/>';

    /* A asa nasce apontando para a direita; para o lado esquerdo do logo
       ela precisa apontar para fora, ou seja, para a esquerda. */
    $t = $lado === 'esquerda'
        ? 'translate(33,4) scale(-1,1)'
        : 'translate(0,4)';

    return '<svg class="marca-asas" viewBox="0 0 33 42" aria-hidden="true">'
         . '<g transform="' . $t . '">' . $penas . '</g></svg>';
}
