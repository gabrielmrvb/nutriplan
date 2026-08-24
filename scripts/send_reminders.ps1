# Dispara os lembretes das refeicoes que estao chegando.
# Feito para o Agendador de Tarefas do Windows (tarefa de usuario, sem admin):
#
#   Acao:      powershell.exe
#   Argumentos: -ExecutionPolicy Bypass -File "<caminho>\scripts\send_reminders.ps1"
#   Gatilho:   diariamente, repetir a cada 5 minutos por 1 dia
#
# Rodar duas vezes no mesmo minuto e seguro: a unicidade
# (usuario, refeicao, dia) no banco decide quem ja foi avisado.

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

& "$raiz\.venv\Scripts\python.exe" manage.py send_meal_reminders
