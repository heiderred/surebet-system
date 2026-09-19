#!/usr/bin/env python3
"""
Mapeador de Surebets 1X2 — MODO MONITOR CONTINUO
==================================================
Consulta a API do BetBurger em loop, regenera o relatorio HTML a cada
ciclo e dispara ALERTA SONORO quando surgir surebet nova acima do limite.

COMO USAR
---------
    pip install requests

    python monitor_surebets.py --token SEU_TOKEN --filtro SEU_FILTRO

Opcionais:
    --intervalo 2          minutos entre consultas (padrao 2, minimo 0.5)
    --min-alerta 1.5       dispara alerta se lucro >= 1.5%% (padrao 1.0)
    --modo prematch|live   padrao: prematch
    --banca 1000           banca em R$ (padrao 1000)
    --saida relatorio.html nome do relatorio (atualizado a cada ciclo)
    --loop                 modo monitor (sem isso, roda uma vez so)

IMPORTANTE
----------
- Token muda a cada login! Se der 401, copie novo em My Account -> API.
- Limite da API: 1800 resultados/minuto. Nao use --intervalo muito baixo.

PARE O MONITOR A QUALQUER MOMENTO: Ctrl+C

NOTIFICACAO NO TELEGRAM (opcional, gratis)
-------------------------------------------
1. No Telegram, fale com @BotFather -> /newbot -> de um nome e username
2. Ele devolve um TOKEN (ex: 123456:ABC-DEF...)
3. Descubra seu chat_id: envie qualquer msg para o bot e abra
   https://api.telegram.org/botSEU_TOKEN/getUpdates
   (o "chat":{"id":123456789} e o seu chat_id)
4. Rode o monitor com:
   --telegram-token SEU_TOKEN --telegram-chat-id SEU_CHAT_ID
"""

import argparse
import json
import sys
import time
from datetime import datetime

import requests

ENDPOINTS = {
    "prematch": "https://rest-api-pr.betburger.com/api/v1/arbs/bot_pro_search",
    "live": "https://rest-api-lv.betburger.com/api/v1/arbs/bot_pro_search",
}

MERCADOS_1X2 = {11: "1", 12: "X", 13: "2"}

# Preencha apos rodar uma vez (veja os IDs no console ou no relatorio)
BK_NAMES = {
    # 10: "Betano",
    # 4:  "Betfair",
    # 99: "Bullbet",
    # 77: "Esporte da Sorte",
    # 5:  "Superbet",
}


def alerta_sonoro(vezes=3):
    """Toca alerta: winsound no Windows, senao bell do terminal."""
    try:
        import winsound
        for _ in range(vezes):
            winsound.Beep(1200, 350)
            time.sleep(0.12)
        return
    except ImportError:
        pass
    for _ in range(vezes):
        sys.stdout.write("\a")
        sys.stdout.flush()
        time.sleep(0.25)


def enviar_telegram(token_bot, chat_id, texto):
    """Envia mensagem via Telegram Bot API. Falha silenciosamente."""
    if not token_bot or not chat_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token_bot}/sendMessage",
            data={"chat_id": chat_id, "text": texto, "parse_mode": "HTML",
                  "disable_web_page_preview": True},
            timeout=15,
        )
    except Exception as e:
        log(f"[Telegram] falha ao enviar: {e}")


def marcar_tendencias(ops, hist):
    """Compara odds com o ciclo anterior:
    - tend por perna: 1 subiu / -1 desceu / 0 sem historico (seta no relatorio)
    - atrasada: perna cuja odd NAO moveu enquanto as outras duas moveram >=2%
      (sinal classico de casa atrasada = janela de arbitragem)."""
    for o in ops:
        chave = o.get("id") or o.get("jogo")
        odds = {p["resultado"]: p["odd"] for p in o["pernas"]}
        prev = hist.get(chave) or {}
        for p in o["pernas"]:
            ant = prev.get(p["resultado"])
            if not ant or ant <= 1:
                p["tend"] = 0
            elif p["odd"] > ant:
                p["tend"] = 1
            elif p["odd"] < ant:
                p["tend"] = -1
            else:
                p["tend"] = 0
        variacoes = {r: abs(odds[r] - prev[r]) / prev[r] for r in odds if prev.get(r, 0) > 1}
        o["atrasada"] = ""
        if len(variacoes) == 3:
            maior = max(variacoes.values())
            parada = min(variacoes, key=lambda r: variacoes[r])
            if maior >= 0.02 and variacoes[parada] <= 0.005:
                o["atrasada"] = parada
        hist[chave] = dict(odds)
    return ops


def buscar(token, filtros, modo, per_page=30):
    dados = [("access_token", token), ("per_page", per_page), ("grouped", 1)]
    for f in filtros:
        dados.append(("search_filter[]", f))
    r = requests.post(ENDPOINTS[modo], data=dados, timeout=40)
    if r.status_code == 401:
        print("\n[ERRO 401] Token invalido/expirado. Copie novo em My Account -> API.")
        return None
    if r.status_code == 402:
        print("\n[ERRO 402] Assinatura da API inativa. Ative em My Account -> API.")
        return None
    if r.status_code == 429:
        print("\n[AVISO 429] Rate limit. Aguardando ciclo extra...")
        return None
    r.raise_for_status()
    return r.json()


def extrair_1x2(resp):
    bets = {b["id"]: b for b in resp.get("bets", [])}
    oportunidades = []
    for arb in resp.get("arbs", []):
        pernas, ok = [], True
        for chave in ("bet1_id", "bet2_id", "bet3_id"):
            bid = arb.get(chave)
            if not bid:
                continue
            b = bets.get(bid)
            if not b or b.get("market_and_bet_type") not in MERCADOS_1X2:
                ok = False
                break
            pernas.append({
                "resultado": MERCADOS_1X2[b["market_and_bet_type"]],
                "odd": b.get("koef"),
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
            "id": arb.get("id"),
            "jogo": arb.get("name") or f"{arb.get('home','')} x {arb.get('away','')}",
            "liga": arb.get("league", ""),
            "inicio": arb.get("started_at"),
            "lucro_pct": round((1 - inv) * 100, 2),
            "pernas": pernas,
        })
    oportunidades.sort(key=lambda o: o["lucro_pct"], reverse=True)
    return oportunidades


def gerar_html(ops, modo, banca, caminho):
    html = TEMPLATE.replace("__DADOS__", json.dumps(ops, ensure_ascii=False)) \
                   .replace("__MODO__", modo.upper()) \
                   .replace("__BANCA__", str(banca)) \
                   .replace("__GERADO__", datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(html)


TEMPLATE = None


def carregar_template():
    global TEMPLATE
    TEMPLATE = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta http-equiv="refresh" content="60">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Surebets 1X2 — monitor</title>
<style>
  :root { --bg:#0f1115; --panel:#1a1d24; --border:#2a2e38; --text:#e8eaf0; --text2:#9aa0ae;
          --text3:#6b7280; --green:#22c55e; --accent:#3b82f6; }
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:'Segoe UI',system-ui,sans-serif; background:var(--bg); color:var(--text); padding:24px 16px; }
  .container { max-width:900px; margin:0 auto; }
  header { margin-bottom:20px; }
  h1 { font-size:22px; } header p { color:var(--text2); font-size:13px; }
  .controls { display:flex; gap:16px; align-items:flex-end; flex-wrap:wrap; background:var(--panel);
              border:1px solid var(--border); border-radius:14px; padding:16px; margin-bottom:20px; }
  .field { display:flex; flex-direction:column; }
  .field label { font-size:12px; color:var(--text3); margin-bottom:4px; }
  .field input { padding:9px 12px; border:1px solid var(--border); border-radius:10px; background:var(--bg);
                 color:var(--text); font-size:15px; width:140px; font-variant-numeric:tabular-nums; }
  .chips { display:flex; gap:6px; flex-wrap:wrap; }
  .chip { padding:6px 12px; border-radius:999px; border:1px solid var(--border); font-size:13px; cursor:pointer; color:var(--text2); user-select:none; }
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
  .leg a { color:inherit; }
  .empty { text-align:center; color:var(--text3); padding:40px 0; }
  @media (max-width:620px) { .legs { grid-template-columns:1fr; } }
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>Surebets 1X2 — __MODO__</h1>
    <p>Atualizado __GERADO__ · recarrega sozinho a cada 60s · Betano · Betfair · Bullbet · Esporte da Sorte · Superbet</p>
  </header>
  <div class="controls">
    <div class="field"><label>Banca (R$)</label><input id="bank" type="number" value="__BANCA__" min="1" oninput="render()"></div>
    <div class="field"><label>% minimo</label><input id="minpct" type="number" value="0" step="0.1" min="0" oninput="render()"></div>
    <div class="field"><label>Casa</label><div class="chips" id="chips"></div></div>
  </div>
  <div class="stats">
    <div class="stat"><div class="v" id="st-total">0</div><div class="l">oportunidades</div></div>
    <div class="stat"><div class="v" id="st-max" style="color:var(--green)">—</div><div class="l">maior lucro %</div></div>
    <div class="stat"><div class="v" id="st-lucro">R$ 0,00</div><div class="l">lucro na maior</div></div>
  </div>
  <div id="lista"></div>
</div>
<script>
const OPS = __DADOS__;
const casas = [...new Set(OPS.flatMap(o => o.pernas.map(p => p.casa)))].sort();
let casaFiltro = null;
const chipsEl = document.getElementById('chips');
chipsEl.innerHTML = '<span class="chip on" data-c="">Todas</span>' + casas.map(c => `<span class="chip" data-c="${c}">${c}</span>`).join('');
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
  if (!lista.length){ el.innerHTML = '<div class="empty">Nenhuma surebet 1X2 no momento.</div>'; return; }
  let html = '';
  lista.forEach(o => {
    const odds = {}; o.pernas.forEach(p => odds[p.resultado] = p.odd);
    const inv = 1/odds['1'] + 1/odds['X'] + 1/odds['2'];
    const lucro = bank * (1/inv - 1);
    document.getElementById('st-lucro').textContent = fmtBRL(Math.max(0, lucro));
    const legs = o.pernas.map(p => {
      const stake = bank / (p.odd * inv);
      const link = p.link ? `<a href="${p.link}" target="_blank" rel="noopener">apostar</a>` : '';
      const nome = p.resultado === '1' ? 'Casa (1)' : p.resultado === 'X' ? 'Empate (X)' : 'Fora (2)';
      const seta = p.tend > 0 ? '<span style="color:var(--green)">\u25b2</span>' : p.tend < 0 ? '<span style="color:#ef4444">\u25bc</span>' : '<span style="color:var(--text3)">\u2022</span>';
      const atras = o.atrasada === p.resultado;
      return `<div class="leg" ${atras ? 'style="border-color:#f59e0b"' : ''}><div class="r">${nome}</div><div class="o">${p.odd.toFixed(2)} ${seta}</div><div class="c">${p.casa}</div>${atras ? '<div style="font-size:11px;color:#f59e0b;font-weight:700">\u26a0 CASA ATRASADA</div>' : ''}<div class="s">${fmtBRL(stake)} ${link}</div></div>`;
    }).join('');
    html += `<div class="op"><div class="op-top"><div><div class="op-jogo">${o.jogo}</div><div class="op-meta">${o.liga} · ${fmtData(o.inicio)} · lucro ${fmtBRL(lucro)}</div></div><div class="op-pct">+${o.lucro_pct.toFixed(2)}%${o.atrasada ? '<div style="font-size:11px;color:#f59e0b;font-weight:600">\u26a0 casa atrasada</div>' : ''}</div></div><div class="legs">${legs}</div></div>`;
  });
  el.innerHTML = html;
}
render();
</script>
</body>
</html>"""


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def main():
    ap = argparse.ArgumentParser(description="Monitor continuo de surebets 1X2")
    ap.add_argument("--token", required=True)
    ap.add_argument("--filtro", type=int, action="append", required=True)
    ap.add_argument("--modo", choices=["prematch", "live"], default="prematch")
    ap.add_argument("--banca", type=float, default=1000)
    ap.add_argument("--saida", default="relatorio_surebets.html")
    ap.add_argument("--intervalo", type=float, default=2.0, help="minutos entre ciclos (min 0.5)")
    ap.add_argument("--min-alerta", type=float, default=1.0, help="alerta se lucro >= este %%")
    ap.add_argument("--loop", action="store_true", help="modo monitor continuo")
    ap.add_argument("--telegram-token", default=None, help="Token do bot Telegram (BotFather)")
    ap.add_argument("--telegram-chat-id", default=None, help="Seu chat_id no Telegram")
    args = ap.parse_args()

    if args.intervalo < 0.5:
        sys.exit("--intervalo minimo: 0.5 minuto (limite da API)")

    carregar_template()
    vistos = {}
    hist_odds = {}
    primeiro_ciclo = True

    log(f"Monitor iniciado | modo={args.modo} | alerta>={args.min_alerta}% | a cada {args.intervalo}min")
    log("Deixe o relatorio aberto no navegador — ele atualiza sozinho.")
    log("Ctrl+C para parar.")

    try:
        while True:
            resp = buscar(args.token, args.filtro, args.modo)
            if resp is not None:
                ops = extrair_1x2(resp)
                ops = marcar_tendencias(ops, hist_odds)
                gerar_html(ops, args.modo, args.banca, args.saida)
                acima = [o for o in ops if o.lucro_pct >= args.min_alerta]

                novas, subiram = [], []
                for o in acima:
                    anterior = vistos.get(o["id"])
                    if anterior is None:
                        novas.append(o)
                    elif o["lucro_pct"] > anterior + 0.3:
                        subiram.append(o)
                    vistos[o["id"]] = o["lucro_pct"]

                log(f"{len(ops)} surebets 1X2 | {len(acima)} acima de {args.min_alerta}% | max +{ops[0]['lucro_pct'] if ops else 0}%")

                if novas and not primeiro_ciclo:
                    for o in novas:
                        log(f"*** NOVA SUREBET: {o['jogo']} — +{o['lucro_pct']}% ({o['pernas'][0]['casa']} x {o['pernas'][1]['casa']} x {o['pernas'][2]['casa']})")
                        pernas_txt = "\n".join(
                            f"  {p['resultado']}: {p['odd']} @ {p['casa']}" for p in o["pernas"]
                        )
                        enviar_telegram(
                            args.telegram_token, args.telegram_chat_id,
                            "\u26a1 <b>NOVA SUREBET " + f"+{o['lucro_pct']}%</b>\n"
                            f"<b>{o['jogo']}</b>\n{o.get('liga','')}\n"
                            f"{pernas_txt}\n"
                            + (f"\u26a0 Casa ATRASADA na perna {o['atrasada']} — aposte ela primeiro!\n" if o.get("atrasada") else "")
                            + "Lucro s/ banca: ajuste no relatorio"
                        )
                    log(">>> ALERTA SONORO + TELEGRAM! <<<")
                    alerta_sonoro(3)
                elif subiram and not primeiro_ciclo:
                    log(f"*** {len(subiram)} surebet(s) subiram acima de {args.min_alerta}%")
                    alerta_sonoro(1)

                primeiro_ciclo = False

            if not args.loop:
                break
            time.sleep(args.intervalo * 60)

    except KeyboardInterrupt:
        log("Monitor encerrado pelo usuario.")


if __name__ == "__main__":
    main()
