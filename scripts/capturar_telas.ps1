# =============================================================================
#  Captura as telas do NutriPlan em resolução de celular (390 x 844, iPhone 12+).
#
#  Antes, gere os HTMLs autocontidos:
#      .venv\Scripts\python.exe scripts\exportar_telas.py
#
#  Depois rode, na raiz do projeto:
#      powershell -ExecutionPolicy Bypass -File scripts\capturar_telas.ps1
#
#  Sai em `.ui_snapshots\`, uma ou mais imagens por tela.
#
#  ---------------------------------------------------------------------------
#  TRÊS COISAS QUE PARECEM SIMPLES E NÃO SÃO
#
#  1. "chrome --window-size=390,844 --screenshot" NÃO dá 390 de largura.
#     O Chrome no Windows tem largura mínima de janela. Medido nesta máquina:
#         --window-size=390,844  ->  VIEWPORT=504x748
#     A imagem sai com 390, mas é um recorte de um layout montado para 504 —
#     parece certa e está errada. Por isso a página vai dentro de um <iframe>
#     de 390px exatos, e a imagem é recortada depois.
#
#  2. Captura de página inteira estraga `position: fixed`.
#     A barra de abas do NutriPlan é fixa no rodapé. Numa imagem única de
#     4.600px de altura ela apareceria só lá embaixo, que não é o que o usuário
#     vê. Por isso a captura sai em fatias de 844px com a página rolada: cada
#     imagem mostra a barra no lugar, como no celular.
#
#  3. Não dá para saber de antemão quantas fatias cada tela tem.
#     A medição por `--dump-dom` não devolveu nada nesta máquina. A saída foi
#     rolar até a imagem parar de mudar: quando o navegador chega ao fim da
#     página a rolagem trava, e a fatia seguinte sai idêntica à anterior.
#     Comparar os bytes das duas resolve sem precisar medir coisa alguma.
#
#  Playwright ou Puppeteer resolveriam isso em três linhas, mas não existem
#  nesta máquina — não há Node nem npm.
# =============================================================================

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing

$Raiz      = Split-Path -Parent $PSScriptRoot
$PastaWeb  = Join-Path $Raiz ".ui_snapshots\html"
$Saida     = Join-Path $Raiz ".ui_snapshots"
$Temp      = Join-Path $env:TEMP "nutriplan-capturas"
$Porta     = 8125
$Largura   = 390
$Altura    = 844   # tela do iPhone 12/13/14
$Emenda    = 60    # sobreposição entre fatias, para nada sumir na dobra
$MaxFatias = 12

$Chrome = (Get-Command chrome.exe -ErrorAction SilentlyContinue).Source
if (-not $Chrome) { $Chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe" }
if (-not (Test-Path $Chrome)) { throw "Chrome nao encontrado em $Chrome" }

if (-not (Test-Path $PastaWeb)) {
  throw "Nao achei $PastaWeb. Rode antes: .venv\Scripts\python.exe scripts\exportar_telas.py"
}
New-Item -ItemType Directory -Force -Path $Saida | Out-Null
New-Item -ItemType Directory -Force -Path $Temp  | Out-Null

# --- Servidor local ----------------------------------------------------------
# O iframe precisa ser da mesma origem para o script conseguir rolar a página de
# dentro. Servir por HTTP resolve sem afrouxar as travas de segurança do Chrome.
$Python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $Python) { $Python = Join-Path $Raiz ".venv\Scripts\python.exe" }
if (-not (Test-Path $Python)) { throw "Python nao encontrado." }

Write-Host "Subindo servidor local na porta $Porta..."
# As aspas em volta de $Raiz nao sao enfeite: esta pasta se chama "Nova pasta",
# com espaco no meio, e o Start-Process junta os argumentos sem citar nenhum.
# Sem elas o Python recebe o caminho partido ao meio e morre na largada.
$servidor = Start-Process -FilePath $Python `
  -ArgumentList @("-m", "http.server", "$Porta", "--directory", "`"$Raiz`"") `
  -WindowStyle Hidden -PassThru

# Conferir que o servidor RESPONDE, em vez de confiar num sleep: a primeira
# versao dormia dois segundos e seguia em frente, e as capturas saiam vazias
# sem dizer por que.
$noAr = $false
foreach ($tentativa in 1..15) {
  Start-Sleep -Milliseconds 400
  try {
    Invoke-WebRequest -Uri "http://127.0.0.1:$Porta/" -UseBasicParsing -TimeoutSec 2 | Out-Null
    $noAr = $true
    break
  } catch { }
}
if (-not $noAr) { throw "O servidor local nao subiu na porta $Porta." }

function Invoke-Chrome {
  # NAO renomeie o parametro para $Args: e variavel automatica do PowerShell, e
  # a colisao faz o Chrome ser chamado sem argumento nenhum, em silencio.
  param([string]$Perfil, [string[]]$Argumentos)

  # Cada chamada leva o seu proprio --user-data-dir: com um so compartilhado, as
  # execucoes disputam a trava do perfil e as primeiras saem sem imagem.
  $todos = @(
    "--headless=new", "--disable-gpu", "--hide-scrollbars",
    "--no-first-run", "--no-default-browser-check",
    "--user-data-dir=$Temp\$Perfil"
  ) + $Argumentos

  # Sem `2>&1`: no PowerShell 5.1 redirecionar a saida de erro de um executavel
  # nativo embrulha cada linha num ErrorRecord e derruba o script. E o Chrome
  # escreve "N bytes written to file" na saida de erro justamente quando DA
  # certo — ou seja, a versao com 2>&1 morria no primeiro acerto.
  & $Chrome @todos | Out-Null
}

function Save-Recorte {
  param([string]$Origem, [string]$Destino, [int]$W, [int]$H)
  $img = [System.Drawing.Image]::FromFile($Origem)
  try {
    $w = [Math]::Min($W, $img.Width)
    $h = [Math]::Min($H, $img.Height)
    $area = New-Object System.Drawing.Rectangle 0, 0, $w, $h
    $recorte = New-Object System.Drawing.Bitmap $w, $h
    $g = [System.Drawing.Graphics]::FromImage($recorte)
    $g.DrawImage($img, $area, $area, [System.Drawing.GraphicsUnit]::Pixel)
    $g.Dispose()
    $recorte.Save($Destino, [System.Drawing.Imaging.ImageFormat]::Png)
    $recorte.Dispose()
  } finally { $img.Dispose() }
}

function Test-ImagensIguais {
  param([string]$A, [string]$B)
  if (-not (Test-Path $A) -or -not (Test-Path $B)) { return $false }
  $bytesA = [System.IO.File]::ReadAllBytes($A)
  $bytesB = [System.IO.File]::ReadAllBytes($B)
  if ($bytesA.Length -ne $bytesB.Length) { return $false }
  for ($i = 0; $i -lt $bytesA.Length; $i++) {
    if ($bytesA[$i] -ne $bytesB[$i]) { return $false }
  }
  return $true
}

try {
  $telas = Get-ChildItem -Path $PastaWeb -Filter "*.html" | Sort-Object Name
  Write-Host "$($telas.Count) telas encontradas.`n"
  $total = 0

  foreach ($tela in $telas) {
    $nome = [System.IO.Path]::GetFileNameWithoutExtension($tela.Name)
    $urlAlvo = "http://127.0.0.1:$Porta/.ui_snapshots/html/$($tela.Name)"
    $fatiasSalvas = 0
    $anterior = $null

    for ($k = 0; $k -lt $MaxFatias; $k++) {
      $rolagem = $k * ($Altura - $Emenda)

      $anfitria = @"
<!doctype html><html><body style="margin:0;background:#fff">
<iframe id="f" src="$urlAlvo" style="width:${Largura}px;height:${Altura}px;border:0;display:block"></iframe>
<script>
  var f = document.getElementById('f');
  function rolar() { try { f.contentWindow.scrollTo(0, $rolagem); } catch (e) {} }
  f.addEventListener('load', rolar);
  setTimeout(rolar, 300);
  setTimeout(rolar, 900);
</script>
</body></html>
"@
      Set-Content -Path (Join-Path $Saida "temp-captura.html") -Value $anfitria -Encoding utf8

      $bruta = Join-Path $Temp "$nome-bruta.png"
      Invoke-Chrome -Perfil "p-$nome-$k" -Argumentos @(
        "--window-size=700,1100",
        "--virtual-time-budget=6000",
        "--screenshot=$bruta",
        "http://127.0.0.1:$Porta/.ui_snapshots/temp-captura.html"
      )
      if (-not (Test-Path $bruta)) { break }

      $candidato = Join-Path $Temp "$nome-fatia.png"
      Save-Recorte -Origem $bruta -Destino $candidato -W $Largura -H $Altura

      # Rolagem travou no fim da pagina: esta fatia saiu igual a anterior, entao
      # a tela acabou e nao ha o que salvar.
      if ($anterior -and (Test-ImagensIguais -A $candidato -B $anterior)) { break }

      if ($k -eq 0) { $sufixo = "" } else { $sufixo = "-parte{0}" -f ($k + 1) }
      Copy-Item -LiteralPath $candidato -Destination (Join-Path $Saida "$nome$sufixo.png") -Force

      $anterior = Join-Path $Temp "$nome-anterior.png"
      Copy-Item -LiteralPath $candidato -Destination $anterior -Force
      $fatiasSalvas++
      $total++
    }

    if ($fatiasSalvas -eq 1) { $plural = "imagem" } else { $plural = "imagens" }
    Write-Host ("  {0,-30} {1} {2} de {3}x{4}" -f $nome, $fatiasSalvas, $plural, $Largura, $Altura)
  }

  Write-Host "`n$total imagens em: $Saida"
}
finally {
  if ($servidor -and -not $servidor.HasExited) { Stop-Process -Id $servidor.Id -Force }
  $lixo = Join-Path $Saida "temp-captura.html"
  if (Test-Path $lixo) { Remove-Item -LiteralPath $lixo -Force }
}
