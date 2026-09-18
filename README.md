# Surebet System — 5 Casas (Brasil)

Sistema completo para identificar, calcular e monitorar surebets (arbitragem)
de resultado final 1X2 (Casa / Empate / Fora) entre casas licenciadas no Brasil.

## Casas suportadas

Betano · Betfair · Bullbet · Esporte da Sorte · Superbet

## Arquivos

| Arquivo | Descrição |
|---|---|
| `surebet_system.html` | Calculadora manual — cole as odds das 5 casas e verifique a surebet. Funciona offline, sem instalação. |
| `mapeador_surebets.py` | Busca pontual na API do BetBurger e gera relatório HTML interativo. |
| `monitor_surebets.py` | **Modo monitor**: loop contínuo, alerta sonoro e notificação no Telegram quando surgir surebet nova. |
| `betburger_surebets.py` | Script básico de consulta à API (ponto de partida para customizações). |

## Requisitos

- Python 3.8+
- `pip install requests`
- Conta ativa na API do BetBurger (My Account -> API)

## Uso rápido

### 1. Calculadora manual (sem API)
Abra `surebet_system.html` no navegador, cole as odds de cada casa e clique em "Analisar surebet".

### 2. Busca pontual
```bash
python mapeador_surebets.py --token SEU_TOKEN --filtro SEU_FILTRO --banca 1000
```

### 3. Monitor 24h com alerta no Telegram
```bash
python monitor_surebets.py --token SEU_TOKEN --filtro SEU_FILTRO \
  --loop --intervalo 2 --min-alerta 1.5 \
  --telegram-token TOKEN_BOT --telegram-chat-id SEU_CHAT_ID
```

Onde encontrar cada token:
- **BetBurger**: My Account -> API (muda a cada login)
- **Telegram**: crie um bot com @BotFather; chat_id via `https://api.telegram.org/bot<TOKEN>/getUpdates`

## Avisos

- Preencha o dicionário `BK_NAMES` no topo dos scripts com os IDs reais das casas
  (rode uma vez e veja os `bookmaker_id` retornados pela API).
- Surebet não é ilegal, mas viola os Termos das casas — contas podem ser limitadas.
- Nunca commite tokens reais no repositório. Use variáveis de ambiente ou apague antes do push.
- Apostas são para maiores de 18 anos. Use apenas casas licenciadas pela SPA/MF.

## Aviso legal

Este projeto é para fins educacionais. O autor não se responsabiliza por perdas
financeiras, bloqueio de contas ou violação de termos de uso das casas de apostas.
