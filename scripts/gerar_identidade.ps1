# Deriva os ícones do NutriPlan da arte aprovada.
#
#     powershell -ExecutionPolicy Bypass -File scripts/gerar_identidade.ps1
#
# POR QUE ESTE ARQUIVO EXISTE
#
# A arte aprovada (`assets/nutriplan-icon-source.png`) é um PNG de 1254x1254
# SEM canal alfa: os cantos arredondados estão desenhados sobre PRETO SÓLIDO, e
# há um wordmark "NUTRIPLAN" na parte de baixo. Redimensionar a imagem inteira
# produziria ícones com cantos pretos — visível no apple-touch-icon, onde o iOS
# aplica a própria máscara, e fatal no maskable, onde o Android recorta.
#
# Então os derivados não são "a imagem menor". Eles são recompostos a partir
# dos pixels originais:
#
#   1. um MODELO DE FUNDO é construído interpolando, linha a linha, entre dois
#      pontos de fundo puro à esquerda e à direita da placa. O gradiente da
#      arte é suave, então a interpolação reproduz o fundo onde o símbolo e o
#      wordmark estavam;
#   2. o SÍMBOLO (N + folha) é extraído com alfa por distância de cor até esse
#      modelo de fundo — chave sobre fundo conhecido, que é o que dá borda
#      limpa numa arte anti-serrilhada;
#   3. cada ícone é composto: fundo + símbolo na escala e posição que aquele
#      formato pede.
#
# Nada é redesenhado. O N e a folha são os pixels da arte aprovada.
#
# A ferramenta é System.Drawing (GDI+), que já vem no Windows. Não há Pillow
# nem dependência nova: os PNGs finais entram estáticos no repositório e
# produção nunca executa este arquivo.

Add-Type -AssemblyName System.Drawing

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
$fonte = Join-Path $raiz "assets\nutriplan-icon-source.png"
$saida = Join-Path $raiz "static\icons"

# --------------------------------------------------------------------------
# Medidas da arte, levantadas dela e não presumidas.
# --------------------------------------------------------------------------
# Símbolo (N + folha), wordmark e placa foram medidos varrendo a imagem por
# classe de pixel. A lacuna vertical de 78px em y 826..905 é o que separa o
# símbolo do wordmark, e é ela que permite descartar o texto sem cortar o N.
$SIM_X0 = 335; $SIM_X1 = 964; $SIM_Y0 = 299; $SIM_Y1 = 826
# Colunas de fundo puro, uma de cada lado da placa, na faixa vertical do
# símbolo. Alimentam o modelo de fundo.
$BG_ESQ = 150; $BG_DIR = 1120
# Quadrado de fundo limpo, centrado na placa, longe dos cantos arredondados.
$FUNDO_X = 177; $FUNDO_Y = 177; $FUNDO_LADO = 900

# --------------------------------------------------------------------------
# Leitura da fonte
# --------------------------------------------------------------------------
$bmpFonte = New-Object System.Drawing.Bitmap $fonte
$larg = $bmpFonte.Width; $alt = $bmpFonte.Height
$ret = New-Object System.Drawing.Rectangle 0, 0, $larg, $alt
$trava = $bmpFonte.LockBits($ret, [System.Drawing.Imaging.ImageLockMode]::ReadOnly, [System.Drawing.Imaging.PixelFormat]::Format24bppRgb)
$passo = $trava.Stride
$px = New-Object byte[] ($passo * $alt)
[System.Runtime.InteropServices.Marshal]::Copy($trava.Scan0, $px, 0, $px.Length)
$bmpFonte.UnlockBits($trava)
$bmpFonte.Dispose()

Write-Output ("fonte: " + $larg + "x" + $alt)

# --------------------------------------------------------------------------
# 1. Modelo de fundo
# --------------------------------------------------------------------------
# Para cada linha, o fundo é a reta entre o pixel de fundo puro da esquerda e
# o da direita. O gradiente da arte varia devagar nas duas direções, então
# essa reta reproduz o fundo debaixo do símbolo com erro de poucos níveis.
#
# É calculado por linha, dentro do laço que precisa dele, e não guardado numa
# matriz de 1254x1254: a matriz custaria centenas de MB em PowerShell para
# devolver o mesmo número que duas multiplicações resolvem.
$vao = [double]($BG_DIR - $BG_ESQ)

# --------------------------------------------------------------------------
# 2. Extração do símbolo com alfa
# --------------------------------------------------------------------------
# Alfa por DISTÂNCIA DE COR até o fundo estimado, e não por luminância: a
# folha tem verdes escuros que a luminância confundiria com o fundo, enquanto
# a distância os separa bem.
#
# A rampa é estreita e começa acima do erro do modelo (~8 níveis somados), o
# que descarta a sombra projetada do N sem comer a borda anti-serrilhada.
$simLarg = $SIM_X1 - $SIM_X0 + 1
$simAlt = $SIM_Y1 - $SIM_Y0 + 1
$simbolo = New-Object System.Drawing.Bitmap $simLarg, $simAlt, ([System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$travaS = $simbolo.LockBits((New-Object System.Drawing.Rectangle 0, 0, $simLarg, $simAlt), [System.Drawing.Imaging.ImageLockMode]::WriteOnly, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$passoS = $travaS.Stride
$bytesS = New-Object byte[] ($passoS * $simAlt)

$RAMPA_BAIXA = 14.0    # abaixo disto é fundo (ou sombra): alfa 0
$RAMPA_ALTA = 46.0     # acima disto é símbolo cheio: alfa 255

for ($y = 0; $y -lt $simAlt; $y++) {
  $yf = $SIM_Y0 + $y
  $baseF = $yf * $passo
  $baseS = $y * $passoS

  # As duas pontas de fundo puro desta linha, lidas uma vez só.
  $iE = $baseF + $BG_ESQ * 3
  $iD = $baseF + $BG_DIR * 3
  $eB = [double]$px[$iE]; $eG = [double]$px[$iE + 1]; $eR = [double]$px[$iE + 2]
  $dB = [double]$px[$iD]; $dG = [double]$px[$iD + 1]; $dR = [double]$px[$iD + 2]

  for ($x = 0; $x -lt $simLarg; $x++) {
    $xf = $SIM_X0 + $x
    $i = $baseF + $xf * 3
    $b = [double]$px[$i]; $g = [double]$px[$i + 1]; $r = [double]$px[$i + 2]

    $t = ($xf - $BG_ESQ) / $vao
    $fR = $eR + ($dR - $eR) * $t
    $fG = $eG + ($dG - $eG) * $t
    $fB = $eB + ($dB - $eB) * $t

    $dR2 = $r - $fR; if ($dR2 -lt 0) { $dR2 = -$dR2 }
    $dG2 = $g - $fG; if ($dG2 -lt 0) { $dG2 = -$dG2 }
    $dB2 = $b - $fB; if ($dB2 -lt 0) { $dB2 = -$dB2 }
    $dist = $dR2 + $dG2 + $dB2

    $a = ($dist - $RAMPA_BAIXA) / ($RAMPA_ALTA - $RAMPA_BAIXA)
    if ($a -lt 0) { $a = 0 }; if ($a -gt 1) { $a = 1 }

    $j = $baseS + $x * 4
    $bytesS[$j] = [byte]$b; $bytesS[$j + 1] = [byte]$g; $bytesS[$j + 2] = [byte]$r
    $bytesS[$j + 3] = [byte][math]::Round($a * 255)
  }
}
[System.Runtime.InteropServices.Marshal]::Copy($bytesS, 0, $travaS.Scan0, $bytesS.Length)
$simbolo.UnlockBits($travaS)
Write-Output ("simbolo extraido: " + $simLarg + "x" + $simAlt)

# --------------------------------------------------------------------------
# 3. Fundos
# --------------------------------------------------------------------------
# O fundo é um GRADIENTE LIMPO com as cores da arte, e não um recorte dela.
#
# Recortar os pixels do fundo original foi a primeira tentativa e produziu um
# `icon-512.png` de 352 KB, contra 12 KB do ícone anterior. A arte tem
# granulação no fundo, e ruído é justamente o que o PNG não consegue comprimir
# — 29x o tamanho para carregar grão que ninguém vê a 192px.
#
# As duas pontas são medidas na arte, com média de um bloco 11x11 para não
# herdar o grão de um pixel só. A cor é a da identidade aprovada; o que se
# perde é o ruído.
function CorMedia {
  param([int]$cx, [int]$cy)
  $sR = 0.0; $sG = 0.0; $sB = 0.0; $n = 0
  for ($y = $cy - 5; $y -le $cy + 5; $y++) {
    $b = $y * $passo
    for ($x = $cx - 5; $x -le $cx + 5; $x++) {
      $i = $b + $x * 3
      $sB += $px[$i]; $sG += $px[$i + 1]; $sR += $px[$i + 2]; $n++
    }
  }
  return [System.Drawing.Color]::FromArgb(255, [int][math]::Round($sR / $n), [int][math]::Round($sG / $n), [int][math]::Round($sB / $n))
}
$corTopo = CorMedia -cx $FUNDO_X -cy $FUNDO_Y
$corBase = CorMedia -cx ($FUNDO_X + $FUNDO_LADO) -cy ($FUNDO_Y + $FUNDO_LADO)
Write-Output ("gradiente do fundo: #" + $corTopo.R.ToString("X2") + $corTopo.G.ToString("X2") + $corTopo.B.ToString("X2") + " -> #" + $corBase.R.ToString("X2") + $corBase.G.ToString("X2") + $corBase.B.ToString("X2"))

# Sólido para o maskable: a média do fundo da placa. O Android recorta o
# maskable em formatos diferentes por fabricante, e gradiente sob máscara
# entrega bordas que mudam de tom conforme o corte.
$somaR = 0.0; $somaG = 0.0; $somaB = 0.0; $conta = 0
for ($y = $FUNDO_Y; $y -lt ($FUNDO_Y + $FUNDO_LADO); $y += 7) {
  $baseF = $y * $passo
  $iE = $baseF + $BG_ESQ * 3
  $iD = $baseF + $BG_DIR * 3
  $eB = [double]$px[$iE]; $eG = [double]$px[$iE + 1]; $eR = [double]$px[$iE + 2]
  $dB = [double]$px[$iD]; $dG = [double]$px[$iD + 1]; $dR = [double]$px[$iD + 2]
  for ($x = $FUNDO_X; $x -lt ($FUNDO_X + $FUNDO_LADO); $x += 7) {
    $t = ($x - $BG_ESQ) / $vao
    $somaR += $eR + ($dR - $eR) * $t
    $somaG += $eG + ($dG - $eG) * $t
    $somaB += $eB + ($dB - $eB) * $t
    $conta++
  }
}
$flR = [int][math]::Round($somaR / $conta); $flG = [int][math]::Round($somaG / $conta); $flB = [int][math]::Round($somaB / $conta)
$verdeFloresta = [System.Drawing.Color]::FromArgb(255, $flR, $flG, $flB)
Write-Output ("verde-floresta solido: #" + $flR.ToString("X2") + $flG.ToString("X2") + $flB.ToString("X2") + "  rgb(" + $flR + "," + $flG + "," + $flB + ")")

# --------------------------------------------------------------------------
# 4. Composição
# --------------------------------------------------------------------------
function Compor {
  param([int]$lado, [double]$fracao, [bool]$solido, [string]$arquivo)

  $tela = New-Object System.Drawing.Bitmap $lado, $lado, ([System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
  $g = [System.Drawing.Graphics]::FromImage($tela)
  $g.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
  $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
  $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
  $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality

  if ($solido) {
    $pincel = New-Object System.Drawing.SolidBrush $verdeFloresta
    $g.FillRectangle($pincel, 0, 0, $lado, $lado)
    $pincel.Dispose()
  }
  else {
    # Diagonal, como na arte: mais claro em cima à esquerda, fechando embaixo
    # à direita. O retângulo do pincel é 1px maior para o GDI+ não deixar a
    # última coluna sem pintar por arredondamento.
    $area = New-Object System.Drawing.Rectangle 0, 0, ($lado + 1), ($lado + 1)
    $pincel = New-Object System.Drawing.Drawing2D.LinearGradientBrush($area, $corTopo, $corBase, 45.0)
    $g.FillRectangle($pincel, 0, 0, $lado, $lado)
    $pincel.Dispose()
  }

  # O símbolo entra pela LARGURA: ele é mais largo que alto, então é a largura
  # que decide se ele cabe.
  $alvoLarg = [double]$lado * $fracao
  $escala = $alvoLarg / $simLarg
  $alvoAlt = $simAlt * $escala
  $dx = ($lado - $alvoLarg) / 2.0
  $dy = ($lado - $alvoAlt) / 2.0
  $destino = New-Object System.Drawing.RectangleF ([single]$dx), ([single]$dy), ([single]$alvoLarg), ([single]$alvoAlt)
  $g.DrawImage($simbolo, $destino)

  $g.Dispose()
  $caminho = Join-Path $saida $arquivo
  $tela.Save($caminho, [System.Drawing.Imaging.ImageFormat]::Png)
  $tela.Dispose()
  $tam = (Get-Item $caminho).Length
  Write-Output ("  " + $arquivo.PadRight(28) + $lado + "x" + $lado + "   " + $tam + " bytes")
}

Write-Output "--- icones cheios (purpose any) ---"
# 0.70 da largura: sobra respiro nas laterais sem o símbolo encolher.
Compor -lado 512 -fracao 0.70 -solido $false -arquivo "icon-512.png"
Compor -lado 192 -fracao 0.70 -solido $false -arquivo "icon-192.png"
Compor -lado 180 -fracao 0.70 -solido $false -arquivo "apple-touch-icon.png"

Write-Output "--- icones maskable (zona segura de 80%) ---"
# A zona segura do Android é o círculo central de 80% do lado. A diagonal do
# símbolo (630x528 -> 822) precisa caber nela:
#     822 * (fracao * lado / 630) <= 0.80 * lado   =>   fracao <= 0.613
# 0.55 deixa folga real, e é o que sobrevive a círculo, squircle e quadrado
# arredondado sem encostar em nenhum deles.
Compor -lado 512 -fracao 0.55 -solido $true -arquivo "icon-512-maskable.png"
Compor -lado 192 -fracao 0.55 -solido $true -arquivo "icon-192-maskable.png"

Write-Output "--- favicon ---"
# Maior que o ícone instalado: no favicon não há nome do app embaixo, e o
# símbolo é a única coisa que identifica a aba.
Compor -lado 48 -fracao 0.80 -solido $false -arquivo "favicon-48.png"
Compor -lado 32 -fracao 0.80 -solido $false -arquivo "favicon-32.png"
# O 16 leva o símbolo a 0,95 — compensação óptica, e não um desenho diferente.
#
# Medido lado a lado a 10x: com 0,80 o N perde a diagonal e a folha vira uma
# mancha verde. Com 0,95 os dois voltam a ler. Acima disso o recorte começa a
# comer o canto do N (1,10) e a quebrá-lo (1,25).
#
# A folha FICA. Ela é o que separa esta identidade da anterior, e some-la a
# 16px devolveria um "N" genérico — que é exatamente o que a marca antiga era.
Compor -lado 16 -fracao 0.95 -solido $false -arquivo "favicon-16.png"

# Não há arquivo separado para a marca da interface.
#
# Ela aparece a 29,6px no cabeçalho e a 64px nas telas de entrada, e o
# `icon-192.png` cobre as duas com folga até em tela 3x. Um `marca.png`
# próprio seria a mesma arte num segundo arquivo — mais 35 KB para baixar e
# mais um lugar onde a identidade pode divergir de si mesma. O convite de
# instalação já usava o `icon-192.png`; agora o cabeçalho e o login também.

$simbolo.Dispose()

# --------------------------------------------------------------------------
# 5. favicon.ico com os três tamanhos
# --------------------------------------------------------------------------
# ICO é um contêiner: cabeçalho de 6 bytes, uma entrada de 16 por imagem, e os
# PNGs inteiros no fim. Windows e todo navegador atual aceitam PNG dentro de
# ICO desde o Vista, e é o que permite guardar 48x48 sem inflar o arquivo.
$tamanhos = @(16, 32, 48)
$blocos = @()
foreach ($t in $tamanhos) { $blocos += , ([System.IO.File]::ReadAllBytes((Join-Path $saida ("favicon-" + $t + ".png")))) }

$fluxo = New-Object System.IO.MemoryStream
$escritor = New-Object System.IO.BinaryWriter $fluxo
$escritor.Write([uint16]0)               # reservado
$escritor.Write([uint16]1)               # tipo 1 = ícone
$escritor.Write([uint16]$tamanhos.Count)
$deslocamento = 6 + 16 * $tamanhos.Count
for ($i = 0; $i -lt $tamanhos.Count; $i++) {
  $t = $tamanhos[$i]
  $escritor.Write([byte]$(if ($t -ge 256) { 0 } else { $t }))   # largura
  $escritor.Write([byte]$(if ($t -ge 256) { 0 } else { $t }))   # altura
  $escritor.Write([byte]0)               # cores da paleta (0 = sem paleta)
  $escritor.Write([byte]0)               # reservado
  $escritor.Write([uint16]1)             # planos
  $escritor.Write([uint16]32)            # bits por pixel
  $escritor.Write([uint32]$blocos[$i].Length)
  $escritor.Write([uint32]$deslocamento)
  $deslocamento += $blocos[$i].Length
}
foreach ($bloco in $blocos) { $escritor.Write($bloco) }
$escritor.Flush()
[System.IO.File]::WriteAllBytes((Join-Path $saida "favicon.ico"), $fluxo.ToArray())
$escritor.Dispose(); $fluxo.Dispose()
Write-Output ("  favicon.ico".PadRight(30) + "16+32+48    " + (Get-Item (Join-Path $saida "favicon.ico")).Length + " bytes")

Write-Output "pronto."
