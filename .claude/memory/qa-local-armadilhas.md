---
name: qa-local-armadilhas
description: armadilhas medidas do QA de navegador nesta máquina (porta, cache de template, agent-browser, sondas)
metadata:
  type: reference
---
- Use `http://127.0.0.1:8000`, não `localhost`: o Chrome do agent-browser
  resolve `::1` e o `runserver` escuta só IPv4 (ERR_CONNECTION_REFUSED com o
  `curl` dando 200; medido em 27/09/2026).
- `runserver` em porta OCUPADA não sobe e o log fica vazio — você mede o
  servidor de outra sessão. Prova: `curl` com o seu cookie; 302 para
  `/conta/entrar/` = não é o seu.
- O template fica em cache mesmo com `--noreload`: reinicie depois de editar
  `.html`. O `preview_start` roda com o cwd da sessão, não do worktree.
- Nunca `agent-browser close --all` (fecha a sessão dos outros); `eval`
  devolve JSON (decodifique); `set media` SUBSTITUI o estado emulado;
  `screenshot ... --full`; no Git Bash, `MSYS_NO_PATHCONV=1`; o CDP não
  emula `display-mode`; `set offline` não corta o fetch do service worker
  (derrube o servidor); clique sob o `header.app-bar` pegajoso é recusado.
- Sonda: campo `required` vazio barra o envio EM SILÊNCIO; `<details>`
  fechado tem `innerText` vazio e ainda ocupa `elementFromPoint`; `innerText`
  chega em CAIXA ALTA; sem `main` no seletor, `form button` pega o SAIR.
- Logado local: cookie de `scripts/qa/sessao.py` e os três consentimentos,
  senão tudo cai em `/conta/consentimento/`. Excluir sem senha:
  `set_unusable_password()` e digitar EXCLUIR.
- ~5 sessões esgotam os 7,7 GB: feche os daemons de navegador ao terminar.

Fonte: memórias antigas `nutriplan-pente-fino-1`, `nutriplan-redesenho-do-treino`, `nutriplan-redesenho-hoje`, `nutriplan-execucao-nada-cobre`, `nutriplan-dado-errado`, `nutriplan-ux-pwa-seguranca`, `nutriplan-auditoria-b`, `nutriplan-experiencia-personas`; medição de 27/09/2026
