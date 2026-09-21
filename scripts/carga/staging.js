/* TESTE DE CARGA DO STAGING (21/09/2026) — k6, em job manual, NUNCA em produção.
 *
 *   k6 run scripts/carga/staging.js
 *   CARGA_DEGRAUS=10,25,50 CARGA_DURACAO=45s k6 run scripts/carga/staging.js
 *
 * Degraus de usuários simultâneos, um depois do outro (10 → 25 → 50 → 75 → 100
 * por padrão, 60 s cada), cada usuário percorrendo as ROTAS abaixo com uma
 * pausa curta entre elas. Só GET: nenhuma conta é criada, nada é escrito. As
 * rotas do `/demo/` são o app INTEIRO renderizado com a pessoa fictícia — a
 * Home do demo custa as mesmas 41 consultas da Home de verdade —, então é a
 * carga real do Django + Neon, sem precisar de login.
 *
 * O relatório (`relatorio.md`, também no resumo do run) traz o p95 por rota
 * em cada degrau e o TETO: o maior degrau em que toda rota ficou abaixo de
 * `CARGA_P95_MS` (2000 ms) com menos de 1 % de erro. O free do Render tem
 * dois workers síncronos do gunicorn — o teto é a medida disso, não do código.
 *
 * Guardas: o `setup()` lê `/saude/` e exige `"ambiente": "staging"`; um
 * endereço que não se anuncie como staging derruba o teste antes do primeiro
 * usuário. O endereço de produção não aparece neste arquivo de propósito.
 */
import http from "k6/http";
import { check, sleep } from "k6";
import { textSummary } from "https://jslib.k6.io/k6-summary/0.1.0/index.js";

const BASE = (__ENV.CARGA_BASE || "https://nutriplan-staging.onrender.com").replace(/\/$/, "");
const DEGRAUS = (__ENV.CARGA_DEGRAUS || "10,25,50,75,100").split(",").map((n) => parseInt(n, 10)).filter((n) => n > 0);
const DURACAO = __ENV.CARGA_DURACAO || "60s";
const P95_MS = parseInt(__ENV.CARGA_P95_MS || "2000", 10);
const ERRO_MAX = 0.01;

export const ROTAS = [
  ["landing", "/"],
  ["vivo", "/saude/vivo/"],
  ["entrar", "/conta/entrar/"],
  ["demo-capa", "/demo/"],
  ["demo-hoje", "/demo/hoje/"],
  ["demo-treino", "/demo/treino/"],
  ["demo-progresso", "/demo/historico/"],
];

function segundos(duracao) {
  const m = /^(\d+)(s|m)$/.exec(duracao);
  return m ? parseInt(m[1], 10) * (m[2] === "m" ? 60 : 1) : 60;
}

function cenarios() {
  const saida = {
    aquecer: { executor: "constant-vus", vus: 2, duration: "20s", startTime: "0s", tags: { degrau: "aquecer" }, exec: "percurso" },
  };
  let inicio = 25;
  for (const n of DEGRAUS) {
    saida["vu" + n] = {
      executor: "constant-vus", vus: n, duration: DURACAO, startTime: inicio + "s",
      gracefulStop: "10s", tags: { degrau: String(n) }, exec: "percurso",
    };
    inicio += segundos(DURACAO) + 15;
  }
  return saida;
}

function limiares() {
  // Um limiar por (degrau, rota) faz o k6 guardar o sub-métrico com essas
  // tags — é assim que o p95 por rota e por degrau aparece no resumo.
  const saida = {};
  for (const n of DEGRAUS) {
    saida[`http_req_failed{degrau:${n}}`] = [`rate<${ERRO_MAX}`];
    for (const [rota] of ROTAS) {
      saida[`http_req_duration{degrau:${n},rota:${rota}}`] = [{ threshold: `p(95)<${P95_MS}`, abortOnFail: false }];
    }
  }
  return saida;
}

export const options = {
  scenarios: cenarios(),
  thresholds: limiares(),
  summaryTrendStats: ["avg", "p(50)", "p(95)", "p(99)", "max"],
  userAgent: "nutriplan-carga (k6)",
};

export function setup() {
  const saude = http.get(BASE + "/saude/", { timeout: "120s", tags: { rota: "saude", degrau: "setup" } });
  let ambiente = "";
  try { ambiente = saude.json("ambiente"); } catch (e) { ambiente = ""; }
  if (saude.status !== 200 || ambiente !== "staging") {
    throw new Error(`${BASE}/saude/ respondeu ${saude.status} com ambiente=${JSON.stringify(ambiente)} — a carga só roda contra o staging.`);
  }
  return { commit: saude.json("commit") };
}

export function percurso() {
  for (const [rota, caminho] of ROTAS) {
    const r = http.get(BASE + caminho, { tags: { rota }, timeout: "60s" });
    check(r, { [`${rota} 200`]: (x) => x.status === 200 });
    sleep(0.5 + Math.random());
  }
}

export function teto(metrics) {
  // O maior degrau em que TODA rota ficou abaixo do p95 e o erro abaixo de 1 %.
  let ok = 0;
  for (const n of DEGRAUS) {
    const erro = (metrics[`http_req_failed{degrau:${n}}`] || {}).values || {};
    if ((erro.rate || 0) >= ERRO_MAX) break;
    let passou = true;
    for (const [rota] of ROTAS) {
      const m = (metrics[`http_req_duration{degrau:${n},rota:${rota}}`] || {}).values || {};
      if (m["p(95)"] === undefined || m["p(95)"] >= P95_MS) { passou = false; break; }
    }
    if (!passou) break;
    ok = n;
  }
  return ok;
}

export function relatorio(data) {
  const m = data.metrics;
  const linhas = [];
  linhas.push(`# Carga no staging — commit ${(data.setup_data || {}).commit || "?"}`, "");
  linhas.push(`Degraus: ${DEGRAUS.join(" → ")} usuários simultâneos, ${DURACAO} cada, só GET, ${ROTAS.length} rotas por volta.`, "");
  linhas.push("| rota | " + DEGRAUS.map((n) => `p95 @${n}`).join(" | ") + " |");
  linhas.push("|---|" + DEGRAUS.map(() => "---:").join("|") + "|");
  for (const [rota] of ROTAS) {
    const celulas = DEGRAUS.map((n) => {
      const v = ((m[`http_req_duration{degrau:${n},rota:${rota}}`] || {}).values || {})["p(95)"];
      return v === undefined ? "—" : `${Math.round(v)} ms`;
    });
    linhas.push(`| ${rota} | ${celulas.join(" | ")} |`);
  }
  linhas.push("| **erro** | " + DEGRAUS.map((n) => {
    const v = ((m[`http_req_failed{degrau:${n}}`] || {}).values || {}).rate;
    return v === undefined ? "—" : `${(v * 100).toFixed(2)} %`;
  }).join(" | ") + " |", "");
  const t = teto(m);
  linhas.push(`**TETO ENCONTRADO: ${t ? t + " usuários simultâneos" : "abaixo do primeiro degrau (" + DEGRAUS[0] + ")"}** — critério: toda rota com p95 < ${P95_MS} ms e erro < ${ERRO_MAX * 100} %.`, "");
  linhas.push(`Pedidos: ${((m.http_reqs || {}).values || {}).count || 0}; p95 geral ${Math.round(((m.http_req_duration || {}).values || {})["p(95)"] || 0)} ms.`);
  return linhas.join("\n") + "\n";
}

export function handleSummary(data) {
  return {
    "relatorio.md": relatorio(data),
    "resumo.json": JSON.stringify(data, null, 1),
    stdout: textSummary(data, { indent: " ", enableColors: false }),
  };
}
