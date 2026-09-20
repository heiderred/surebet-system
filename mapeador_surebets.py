#!/usr/bin/env python3
"""
Mapeador de Surebets 1X2 — Betano / Betfair / Bullbet / Esporte da Sorte / Superbet
====================================================================================
Busca surebets de resultado final (1X2) na API do BetBurger e gera um
relatorio HTML interativo com as melhores oportunidades entre suas casas.

REQUISITOS
----------
    pip install requests

COMO USAR
---------
    python mapeador_surebets.py --token SEU_TOKEN --filtro ID_DO_FILTRO

Onde ID_DO_FILTRO vem de: betburger.com -> My Account -> Multifilters
(o numero do filtro que voce criou com suas casas).

Opcionais:
    --filtro 123 --filtro 456   varios filtros
    --modo prematch|live        padrao: prematch
    --banca 1000                banca em R$ (padrao 1000)
    --saida relatorio.html      nome do relatorio gerado
    --listar-casas              so lista os IDs de casas encontrados e sai
                                (use na 1a vez para mapear os nomes abaixo)

IMPORTANTE
----------
- O token muda a cada login! Copie um novo em My Account -> API se der erro 401.
- Assinatura da API deve estar "Active" (My Account -> API), senao erro 402.
"""

import argparse
import json
import sys
from datetime import datetime

import requests

ENDPOINTS = {
    "prematch": "https://rest-api-pr.betburger.com/api/v1/arbs/bot_pro_search",
    "live": "https://rest-api-lv.betburger.com/api/v1/arbs/bot_pro_search",
}.copy()
ENDPOINTS["live"] = "https://rest-api-lv.betburger.com/api/v1/arbs/bot_pro_search"

# Mercados de resultado final (1X2) na API do BetBurger
MERCADOS_1X2 = {11: "1", 12: "X", 13: "2"}

# Mapeamento ID da casa -> nome. Preencha apos rodar com --listar-casas
# (a API retorna bookmaker_id numerico; a 1a execucao mostra quais aparecem).
BK_NAMES = {
    # exemplos de formato — descubra os IDs reais com --listar-casas:
    # 10: "Betano",
    # 4:  "Betfair",
    # 99: "Bullbet",
    # 77: "Esporte da Sorte",
    # 5:  "Superbet",
}


def buscar(token, filtros, modo, per_page=30):
    dados = [("access_token", token), ("per_page", per_page), ("grouped", 1)]
    for f in (filtros or []):
        dados.append(("search_filter[]", f))
    r = requests.post(ENDPOINTS[modo], data=dados, timeout=40)
    if r.status_code == 401:
        sys.exit("ERRO 401: token invalido ou sessao expirada. Copie um novo em My Account -> API.")
    if r.status_code == 402:
        sys.exit("ERRO 402: assinatura da API inativa. Ative em My Account -> API.")
    if r.status_code == 429:
        sys.exit("ERRO 429: limite de requisicoes excedido. Aguarde e tente de novo.")
    r.raise_for_status()
    return r.json()


def extrair_1x2(resp):
    """Retorna (oportunidades, ids_de_casas_vistos)."""
    bets = {b["id"]: b for b in resp.get("bets", [])}
    oportunidades, casas_vistas = [], set()

    for arb in resp.get("arbs", []):
        pernas = []
        ok = True
        for chave in ("bet1_id", "bet2_id", "bet3_id"):
            bid = arb.get(chave)
            if not bid:
                continue
            b = bets.get(bid)
            if not b:
                ok = False
                break
            casas_vistas.add(b.get("bookmaker_id"))
            mercado = b.get("market_and_bet_type")
            if mercado not in MERCADOS_1X2:   # fora de 1X2 -> ignora
                ok = False
                break
            pernas.append({
                "resultado": MERCADOS_1X2[mercado],
                "odd": b.get("koef"),
                "casa_id": b.get("bookmaker_id"),
                "casa": BK_NAMES.get(b.get("bookmaker_id"), f"Casa {b.get('bookmaker_id')}"),
                "link": b.get("bookmaker_event_direct_link", ""),
            })
        if not ok or len(pernas) < 3:
            continue

        odds = {p["resultado"]: p["odd"] for p in pernas}
        if not all(o in odds for o in ("1", "X", "2")) or any(v <= 1 for v in odds.values()):
            continue

        inv = 1/odds["1"] + 1/odds["X"] + 1/odds["2"]
        oportunidades.append({
            "jogo": arb.get("name") or f"{arb.get('home','')} x {arb.get('away','')}",
            "liga": arb.get("league", ""),
            "inicio": arb.get("started_at"),
            "lucro_pct": round((1 - inv) * 100, 2),
            "pernas": pernas,
        })

    oportunidades.sort(key=lambda o: o["lucro_pct"], reverse=True)
    return oportunidades, casas_vistas


def gerar_html(ops, modo, banca, caminho):
    payload = json.dumps(ops, ensure_ascii=False)
    html = TEMPLATE.replace("__DADOS__", payload)\
                   .replace("__MODO__", modo.upper())\
                   .replace("__BANCA__", str(banca))\
                   .replace("__GERADO__", datetime.now().strftime("%d/%m/%Y %H:%M"))
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(html)


TEMPLATE = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Surebets 1X2 — relatorio</title>
<style>
  :root { --bg:#0f1115; --panel:#1a1d24; --border:#2a2e38; --text:#e8eaf0; --text2:#9aa0ae;
          --text3:#6b7280; --green:#22c55e; --red:#ef4444; --accent:#3b82f6; }
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:'Segoe UI',system-ui,sans-serif; background:var(--bg); color:var(--text); padding:24px 16px; }
  .container { max-width:900px; margin:0 auto; }
  header { display:flex; justify-content:space-between; align-items:flex-end; flex-wrap:wrap; gap:12px; margin-bottom:20px; }
  h1 { font-size:22px; } header p { color:var(--text2); font-size:13px; }
  .controls { display:flex; gap:16px; align-items:flex-end; flex-wrap:wrap; background:var(--panel);
              border:1px solid var(--border); border-radius:14px; padding:16px; margin-bottom:20px; }
  .field { display:flex; flex-direction:column; }
  .field label { font-size:12px; color:var(--text3); margin-bottom:4px; }
  .field input { padding:9px 12px; border:1px solid var(--border); border-radius:10px; background:var(--bg);
                 color:var(--text); font-size:15px; width:140px; font-variant-numeric:tabular-nums; }
  .chips { display:flex; gap:6px; flex-wrap:wrap; }
  .chip { padding:6px 12px; border-radius:999px; border:1px solid var(--border); font-size:13px; cursor:pointer;
          color:var(--text2); user-select:none; }
  .chip.on { border-color:var(--accent); color:var(--accent); background:rgba(59,130,246,.1); }
  .stats { display:flex; gap:16px; margin-bottom:16px; flex-wrap:wrap; }
  .stat { background:var(--panel); border:1px solid var(--border); border-radius:12px; padding:12px 18px; flex:1; min-width:120px; }
  .stat .v { font-size:26px; font-weight:700; font-variant-numeric:tabular-nums; }
  .stat .l { font-size:12px; color:var(--text3); }
  .op { background:var(--panel); border:1px solid var(--border); border-radius:14px; padding:16px; margin-bottom:12px; }
  .op-top { display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap; margin-bottom:10px; }
  .op-jogo { font-size:15px; font-weight:600; }
  .op-meta { color:var(--text3); font-size:12px; margin-top:2px; }
  .op-pct { font-size:22px; font-weight:700; color:var(--green); font-variant-numeric:tabular-nums; white-space:nowrap; }
  .legs { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; }
  .leg { background:var(--bg); border:1px solid var(--border); border-radius:10px; padding:10px; text-align:center; }
  .leg .r { font-size:12px; color:var(--text3); }
  .leg .o { font-size:20px; font-weight:700; font-variant-numeric:tabular-nums; }
  .leg .c { font-size:13px; color:var(--accent); font-weight:600; }
  .leg .s { font-size:14px; color:var(--text2); font-variant-numeric:tabular-nums; }
  .leg a { color:inherit; text-decoration:none; }
  .leg a:hover { text-decoration:underline; }
  .empty { text-align:center; color:var(--text3); padding:40px 0; }
  @media (max-width:620px) { .legs { grid-template-columns:1fr; } }
</style>
</head>
<body>
<div class="container">
  <header>
    <div><h1>Surebets 1X2 — __MODO__</h1><p>Gerado em __GERADO__ · Betano · Betfair · Bullbet · Esporte da Sorte · Superbet</p></div>
  </header>

  <div class="controls">
    <div class="field"><label>Banca (R$)</label><input id="bank" type="number" value="__BANCA__" min="1" oninput="render()"></div>
    <div class="field"><label>% minimo</label><input id="minpct" type="number" value="0" step="0.1" min="0" oninput="render()"></div>
    <div class="field"><label>Filtrar por casa envolvida</label><div class="chips" id="chips"></div></div>
  </div>

  <div class="stats">
    <div class="stat"><div class="v" id="st-total">0</div><div class="l">oportunidades</div></div>
    <div class="stat"><div class="v" id="st-max" style="color:var(--green)">—</div><div class="l">maior lucro %</div></div>
    <div class="stat"><div class="v" id="st-lucro">R$ 0,00</div><div class="l">lucro na maior (banca atual)</div></div>
  </div>

  <div id="lista"></div>
</div>

<script>
const OPS = __DADOS__;
const casas = [...new Set(OPS.flatMap(o => o.pernas.map(p => p.casa)))].sort();
let casaFiltro = null;

const chipsEl = document.getElementById('chips');
chipsEl.innerHTML = '<span class="chip on" data-c="">Todas</span>' + casas.map(c =>
  `<span class="chip" data-c="${c}">${c}</span>`).join('');
chipsEl.addEventListener('click', e => {
  const c = e.target.dataset && e.target.dataset.c;
  if (c === undefined) return;
  casaFiltro = c === '' ? null : c;
  document.querySelectorAll('.chip').forEach(x => x.classList.toggle('on', x.dataset.c === c));
  render();
});

function fmtBRL(v){ return v.toLocaleString('pt-BR',{style:'currency',currency:'BRL'}); }
function fmtData(ts){ try { return new Date(ts*1000).toLocaleString('pt-BR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}); } catch(e){ return ''; } }

function render(){
  const bank = parseFloat(document.getElementById('bank').value) || 0;
  const minpct = parseFloat(document.getElementById('minpct').value) || 0;
  let lista = OPS.filter(o => o.lucro_pct >= minpct);
  if (casaFiltro) lista = lista.filter(o => o.pernas.some(p => p.casa === casaFiltro));

  document.getElementById('st-total').textContent = lista.length;
  document.getElementById('st-max').textContent = lista.length ? '+' + lista[0].lucro_pct.toFixed(2) + '%' : '—';

  const el = document.getElementById('lista');
  if (!lista.length){ el.innerHTML = '<div class="empty">Nenhuma surebet 1X2 encontrada com esses filtros.</div>'; return; }

  let html = '';
  lista.forEach(o => {
    const odds = {}; o.pernas.forEach(p => odds[p.resultado] = p.odd);
    const inv = 1/odds['1'] + 1/odds['X'] + 1/odds['2'];
    const lucro = bank * (1/inv - 1);
    document.getElementById('st-lucro').textContent = fmtBRL(Math.max(0, lucro));
    const legs = o.pernas.map(p => {
      const stake = bank / (p.odd * inv);
      const link = p.link ? `<a href="${p.link}" target="_blank" rel="noopener">apostar</a>` : '';
      return `<div class="leg"><div class="r">${p.resultado === '1' ? 'Casa (1)' : p.resultado === 'X' ? 'Empate (X)' : 'Fora (2)'}</div>
              <div class="o">${p.odd.toFixed(2)}</div><div class="c">${p.casa}</div>
              <div class="s">${fmtBRL(stake)} ${link}</div></div>`;
    }).join('');
    html += `<div class="op"><div class="op-top"><div><div class="op-jogo">${o.jogo}</div>
             <div class="op-meta">${o.liga} · ${fmtData(o.inicio)} · lucro ${fmtBRL(lucro)}</div></div>
             <div class="op-pct">+${o.lucro_pct.toFixed(2)}%</div></div><div class="legs">${legs}</div></div>`;
  });
  el.innerHTML = html;
}
render();
</script>
</body>
</html>"""


def main():
    ap = argparse.ArgumentParser(description="Mapeador de surebets 1X2 (BetBurger API)")
    ap.add_argument("--token", required=True, help="Seu token da API (My Account -> API)")
    ap.add_argument("--filtro", type=int, action="append", default=None,
                    help="ID do filtro (Multifilters). Repita para varios.")
    ap.add_argument("--modo", choices=["prematch", "live"], default="prematch")
    ap.add_argument("--banca", type=float, default=1000)
    ap.add_argument("--saida", default="relatorio_surebets.html")
    ap.add_argument("--listar-casas", action="store_true",
                    help="Apenas lista IDs de casas encontrados e sai")
    args = ap.parse_args()

    print(f"Consultando surebets {args.modo.upper()} (filtros {args.filtro})...")
    resp = buscar(args.token, args.filtro, args.modo)
    ops, casas = extrair_1x2(resp)

    if args.listar_casas:
        print("\nIDs de casas encontrados nesta busca:")
        for cid in sorted(casas, key=lambda x: (x is None, x)):
            print(f"  {cid}: {BK_NAMES.get(cid, '(sem nome mapeado)')}")
        print("\nAdicione os nomes no dicionario BK_NAMES no topo do script.")
        return

    print(f"Surebets 1X2 encontradas: {len(ops)} | total no sistema: {resp.get('total')}")
    gerar_html(ops, args.modo, args.banca, args.saida)
    print(f"Relatorio gerado: {args.saida}")
    print("Abra o arquivo no navegador. Ajuste a banca e os filtros direto na pagina.")

    # Diagnostico: consulta SEM filtro para comparar
    try:
        resp2 = buscar(args.token, None, args.modo)
        total_livre = resp2.get("total")
        livres, _ = extrair_1x2(resp2)
        print(f"DIAGNOSTICO sem filtro: total no sistema = {total_livre} | surebets 1X2 = {len(livres)}")
        if total_livre and int(total_livre) > 0 and len(ops) == 0:
            print(">>> O filtro esta bloqueando tudo! Edite o filtro no BetBurger (casas, %% minimo) ou use outro ID.")
        elif not total_livre or int(total_livre) == 0:
            print(">>> A API devolveu ZERO mesmo sem filtro. Provavel limitacao do plano gratuito.")
    except Exception as e:
        print(f"Diagnostico falhou: {e}")

    if not BK_NAMES:
        print("\nDICA: rode com --listar-casas para descobrir os IDs das casas e mapear os nomes.")


if __name__ == "__main__":
    main()
