#!/usr/bin/env python3
"""
BetBurger Surebet Fetcher
Busca surebets (prematch/live) via API oficial do BetBurger.

Requisitos:
    pip install requests

Como obter o FILTER_ID:
    1. Acesse https://www.betburger.com -> My Account -> Multifilters
    2. Crie um filtro com as casas/esportes que voce usa
    3. O numero do filtro aparece na lista de filtros (ex: 12345)

Como obter o TOKEN:
    My Account -> API  (ATENCAO: o token muda a cada nova sessao/login!)
"""

import requests
import sys
from datetime import datetime

# ========== CONFIGURE AQUI ==========
ACCESS_TOKEN = "COLE_SEU_TOKEN_AQUI"  # seu token (My Account -> API)
FILTER_IDS   = [1]        # <-- SUBSTITUA pelo ID do seu filtro (Multifilters)
PER_PAGE     = 20         # surebets por requisicao (max ~30)
MODO         = "prematch" # "prematch" ou "live"
# ====================================

ENDPOINTS = {
    "prematch": "https://rest-api-pr.betburger.com/api/v1/arbs/bot_pro_search",
    "live":     "https://rest-api-lv.betburger.com/api/v1/arbs/bot_pro_search",
}

def buscar_surebets():
    url = ENDPOINTS[MODO]
    data = [("access_token", ACCESS_TOKEN), ("per_page", PER_PAGE), ("grouped", 1)]
    for fid in FILTER_IDS:
        data.append(("search_filter[]", fid))

    r = requests.post(url, data=data, timeout=30)
    if r.status_code == 401:
        sys.exit("ERRO 401: token invalido ou sessao expirada. Gere um novo em My Account -> API.")
    if r.status_code == 402:
        sys.exit("ERRO 402: assinatura da API inativa/expirada. Verifique em My Account -> API.")
    if r.status_code == 429:
        sys.exit("ERRO 429: limite de requisicoes excedido. Aguarde um pouco.")
    r.raise_for_status()
    return r.json()

def imprimir(resp):
    arbs = resp.get("arbs", [])
    bets = {b["id"]: b for b in resp.get("bets", [])}
    print(f"\nTotal no sistema: {resp.get('total')} | Com seu filtro: {resp.get('totalByFilter')} "
          f"| Maior %: {resp.get('maxPercentByFilter')}%\n")
    if not arbs:
        print("Nenhuma surebet encontrada com esse filtro agora.")
        return

    for arb in arbs:
        inicio = datetime.fromtimestamp(int(arb["started_at"])).strftime("%d/%m %H:%M")
        print("=" * 78)
        print(f"[{arb['id']}] {arb.get('name','')}  |  {inicio}  |  ROI: {arb['percent']:.2f}%")
        for key in ("bet1_id", "bet2_id", "bet3_id"):
            bid = arb.get(key)
            if not bid:
                continue
            b = bets.get(bid)
            if not b:
                continue
            casa = b.get("bookmaker_id")
            odds = b.get("koef")
            mercado = b.get("market_and_bet_type")
            print(f"    perna {key[-4]}: casa ID {casa:>3} | odd {odds} | mercado tipo {mercado} | {b.get('home','')} x {b.get('away','')}")
        print(f"    odds min {arb.get('min_koef')} / max {arb.get('max_koef')}")

if __name__ == "__main__":
    print(f"Consultando surebets {MODO.upper()} no BetBurger...")
    imprimir(buscar_surebets())
