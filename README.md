# StockBot

An independent AI trading experiment with $100,000 of **simulated** capital. The public dashboard shows positions, fractional shares, equity, realized/unrealized gains, transactions and the agent's journal. Humans can pause, resume a pause, or permanently stop the experiment. They cannot submit prompts, place trades, edit balances, or change its strategy through the app.

The frontend is static on Vercel. One continuously running Python process on Hack Club Nest owns the SQLite database, Alpaca IEX stream, research loop, and simulation. Website visits never trigger AI calls or trades. No Alpaca trading/account endpoints are implemented or called.

## Deployment status

The base experiment was verified running on Nest and serving the public dashboard on October 3, 2026 at https://stockbot.tekwiz17.me. Code changes must be pulled and restarted on Nest; Vercel must deploy the latest repository commit for frontend changes. The coding workspace cannot resolve the SSH host, so direct server deployment from it is unavailable.

## Behavior

- During the XNYS regular session, deliberates about every ten minutes; up to six independent actions per cycle. An active full session permits roughly 39 deliberations, potentially hundreds of fills including AI-planned stop losses and profit targets.
- The AI chooses and revises its own strategy, holding horizon, risk appetite and cash allocation from evidence. It is not required to remain aggressive or invest for the long term. The dashboard shows its chosen approach and explanation.
- Holds long stocks and ETFs, supports microshare precision, a $10 minimum fill, no leverage or shorting, and a 30% single-position maximum.
- Uses ask plus 5 bps to buy and bid minus 5 bps to sell. Quotes must be no more than 90 seconds old with a valid spread under 2%. A fill is atomic and cannot overdraft cash or sell unowned shares. These are simplified simulated fills, without actual liquidity/queue modeling.
- Studies realized outcomes by symbol, recent trade theses and prior notes before each decision. Closed sessions—including holidays and weekends—get one conditional next-session plan per New York calendar day after 10 AM, with rationale, watchlist, entry conditions and invalidation signals. Closed-market plans cannot execute trades and are reassessed with fresh data after opening. Market holidays and half-days use `exchange-calendars`.
- Starts with 30 US stocks/ETFs, then rotates the IEX stream toward holdings and AI-discovered tickers. New action tickers get batched REST quotes before execution; discovery is not limited to the starter list. Stores quote samples every 15 seconds per symbol, retains 14 days of samples, and permanently retains fills and decisions. Uses a batched REST quote fallback only when needed.
- A pause suspends execution (including planned exits), research and streams. A stop is permanent through the app and preserves holdings without forced liquidation. Restarting the server preserves state.

## Budget controls

StockBot uses the owner's stated **$0.60/day** allocation, regardless of the larger generic allowance in Hack Club's public docs.

| Provider | StockBot limit | Mechanism |
| --- | --- | --- |
| Hack Club AI | $0.55 reserved / rolling 24h; 57 completions maximum | Fetches live model pricing; reserves full input/output bound with 20% margin **before** calling. Timeouts and failures keep their reserve. Unknown/expensive pricing suspends AI. |
| Hack Club Search | 48 searches / rolling 24h | Caches news, selects the next query autonomously, retains local request counts across restarts. |
| Alpaca REST | 20 requests / rolling 60 seconds | Only batch latest IEX quotes; normally about one call per ten-minute cycle if streaming fails. |
| Alpaca stream | One worker connection; up to 30 dynamic symbols | Backoff on errors; no per-visitor upstream connection. |
| Vercel | Static assets and cached reverse proxy | No Vercel cron or AI functions; visitors poll at most once per minute while visible. |

Preferred models, subject to live affordable pricing: DeepSeek V4 Pro, DeepSeek V4.1 Flash, DeepSeek V4 Flash, DeepSeek V3.2, Qwen3 235B A22B, DeepSeek V3, Qwen3 32B, Gemini 2.5 Flash Lite, Gemini 2.5 Flash. A live V4 Pro completion succeeded. Its output billing exceeded the catalog estimate, so requests now explicitly cap upstream routing at $0.22/M input and $2.70/M output, with a fixed conservative $0.009528 reservation (including 20% margin), or $0.543096 for 57 calls. Higher-priced candidates are rejected. Unexpected reported cost above the reservation suspends further AI calls. The bot rejects any candidate whose conservative maximum request exceeds $0.01. Saved `Models.html` was used as a model-directory reference, not as current billing authority. AI calls use Hack Club, not OpenRouter directly; OpenRouter's public catalog is used only to look up explicit model prices if Hack Club's catalog omits them.

No software can guarantee unlimited free service: provider policies, shared account usage, traffic, outages and price changes can affect availability. The bot limits **its own** usage and suspends calls on quota/authentication failures. It does not evade limits, purchase credits or silently switch to paid services. Other apps on the same account can still consume the allowance. Public traffic can exhaust Vercel bandwidth/request limits; a large public launch needs platform-level traffic controls. The 20% reservation margin is an estimate, not a contractual provider billing cap.

## Install the backend on Nest

SSH into the existing container, clone this repository, then run the installer:

```sh
ssh tekwiz17@hackclub.app
git clone https://github.com/Tekwiz17/stockbot.git
cd stockbot
bash deploy/install-nest.sh
```

The installer asks privately for the supplied provider credentials and admin passcode; it generates a session secret. Choose the requested passcode in that private prompt. It writes `.env` with permissions 0600 and runs a **single** Uvicorn worker under systemd. Secrets belong on Nest because Nest makes provider calls; putting them only in Vercel would not configure the worker. No credential is bundled in this public repository.

In the [Nest dashboard](https://dashboard.hackclub.app), add a reverse-proxy domain **stockbot.tekwiz17.hackclub.app**, pointing to the container's port **8765**. The worker explicitly enables a dual-stack IPv4/IPv6 socket for Nest's proxy. Verify `https://stockbot.tekwiz17.hackclub.app/api/health` reports `configured: true`. Nonroot containers using user systemd need lingering enabled so the worker survives logout; root containers use system-wide systemd.

Import `Tekwiz17/stockbot` into Vercel as an **Other** project. Output directory: **public**. No build command or dependency install is needed. `vercel.json` reverse-proxies `/api/*` to Nest and routes `/admin` to the controls page. Set the exact Vercel production origin in Nest's `PUBLIC_ORIGINS`; login/control POSTs reject other origins. Redeploy the frontend if the backend domain changes. Vercel needs no provider API keys because it only serves assets and forwards requests.

```sh
# On the Nest server (use systemctl --user for a nonroot install):
systemctl status stockbot
journalctl -u stockbot --since '10 minutes ago'
.venv/bin/python deploy/backup.py
```

The admin passcode is server-only, with a signed HTTP-only secure cookie, an hour-long session, same-origin mutation checks, and an eight-attempt-per-15-minute login throttle. A short passcode is inherently weak; throttle limits attempts but cannot make a three-character secret strong. Never put `.env`, databases, or SSH keys in GitHub.

## Local development and verification

```sh
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt pytest
.venv/bin/python -m pytest -q
STOCKBOT_DISABLE_WORKER=1 .venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8765
```

Open http://127.0.0.1:8765. Local login testing additionally needs `ADMIN_PASSCODE`, `SESSION_SECRET` and `ALLOW_HTTP=1`; never use `ALLOW_HTTP` in production. CI validates ledger atomicity, partial cost basis, stale data and market closure guards, budget persistence, holiday/half-day schedules, mock AI pricing and responses, authentication and lifecycle-only controls. Live checks confirmed Alpaca latest IEX quotes and a DeepSeek V4 Pro completion with the supplied credentials. Hack Club Search rejected the supplied key with HTTP 422 / SUBSCRIPTION_TOKEN_INVALID; a working Search key is still needed. Nest deployment and public-domain validation remain blocked. DOM integration checks verified dashboard response rendering, charts, tabs and escaped notes; a real-browser visual check remains outstanding.

## Current limits

This is an experiment, not a brokerage or investment recommendation. It does not model commissions, taxes, dividends, splits, corporate actions, liquidity, market impact or trading halts. A split can distort raw price-based returns until corporate-action accounting is added. IEX is not a consolidated all-exchange quote. The stream watches up to 30 names at once; additional action tickers and holdings use budgeted REST market data. Tickers without a valid fresh IEX quote cannot fill. Model notes provide feedback memory, not trained model-weight updates. There is no proof of profitability and no promise of a minimum trade count.

Provider references: [Alpaca market data plans](https://docs.alpaca.markets/us/docs/about-market-data-api), [Hack Club AI docs](https://docs.ai.hackclub.com/), [Hack Club Search docs](https://search.hackclub.com/docs), [Nest quickstart](https://guides.hackclub.app/index.php/Quickstart).

## Update an existing Nest installation

```sh
cd /root/stockbot
git pull --ff-only
bash deploy/install-nest.sh
```

The installer preserves provider credentials and the database, adds `https://stockbot.tekwiz17.me` to allowed origins, rewrites the service to use `backend.serve`, and restarts it. This fixes the IPv6-only listener that may prevent an IPv4 reverse-proxy connection. Verify locally using both `http://127.0.0.1:8765/api/health` and `http://[::1]:8765/api/health`.

## Reset headers, planning and risk (October 4 update)

Every budgeted provider response records `x-ratelimit-reset-requests` and `x-ratelimit-reset-tokens` when supplied, including successful responses and rate-limit errors. Durations (`2m59.56s`, milliseconds), epoch seconds/milliseconds, ISO timestamps and HTTP dates are accepted. Exhausted limits and `Retry-After` control persistent cooldowns. The dashboard displays reported reset times, or “not reported.” These headers describe request/token limits; they are not evidence of a dollar-credit replenishment time. On HTTP 402 without explicit credit-reset metadata, the next UTC day is a labeled retry fallback. Reset headers never clear StockBot's independent rolling $0.55 reservations.

The Stock risk tab covers current holdings only, and holdings have a risk column. At least 20 valid observed one-minute returns are needed. The 0–100 heuristic weights volatility (45 points), observed drawdown (25), bid/ask spread (15), and portfolio concentration (15). Components saturate at an 8% daily volatility proxy, 10% drawdown, 0.5% spread and 30% portfolio weight. It is a transparent local indicator, not a probability of losing money, a trained risk model or a stock recommendation. Overnight gaps are excluded from volatility samples, and stale measurements are labeled. Until market quote history accumulates, risk reads “Insufficient data.” No additional AI or market-data requests are made to calculate scores.

The performance chart supports pointer inspection and left/right keyboard navigation, 1D/1W/1M/ALL ranges, and portfolio value, gain/loss or cash metrics. Its horizontal axis uses actual snapshot timestamps. Older history is sampled for display while recent one-day points and first/latest snapshots are retained; the database keeps all snapshots.

## Data-grounded decisions and diagnosis

The existing IEX WebSocket now subscribes to one-minute OHLCV bars alongside quotes; no extra REST polling is needed for bars. Observed bars are saved locally and supplied to the AI. It must adapt to available measurements, treat old journal claims as unverified, and anchor past-trade lessons in the actual ledger. Output length is bounded in the prompt and truncated completions are rejected. Failures now persist a credential-safe stage and reason in `cycle_errors` and the dashboard notice. Run `.venv/bin/python deploy/diagnose.py` in the Nest repository to inspect recent failures and budget usage without exposing credentials.

## Risk-taking experiment and six-month memory

StockBot uses simulated money and pursues substantial net returns, accepting meaningful risk. The AI chooses its strategy and does not have to trade every day. Position horizons persist across later strategy changes. New intraday entries have a 60-minute review window; swing entries 2 calendar days, medium-term 5 days, and long-term 20 days. Earlier discretionary sales require an explicit thesis-break explanation; this is a churn guard, not independent verification of the model's narrative. Planned price stops remain active even during review windows. Targets default to selling half the position once, keeping the remainder until the AI or the stored stop exits. Adding shares preserves the original holding plan and stop. Existing holdings keep their stored stops. A 30% position cap and cash-only ledger remain in force. No rule promises profitable trades.

A separate collector batches all 30 watchlist tickers, plus holdings and discoveries, into one market-data request every five minutes during regular market hours. It does not call AI or Search. It continues observation while trading is paused and stops after the experiment is stopped. A cooldown/quota/outage can defer collection; missing or stale quotes are never fabricated. Each five-minute bucket stores actual quote time, bid and ask; records remain for 183 days. Existing genuine quote observations are migrated into this archive. Six months of past history cannot appear immediately; coverage grows from real stored observations. Raw quotes and minute bars retain their shorter 14-day window. At most roughly 78 regular-session collection requests per day are needed for the base watchlist, well below the local 20/minute REST cap.

The AI receives locally calculated multi-window returns, drawdown, observed volatility, position weight, bid-based net liquidation profit/loss, holding plans, and actual realized outcomes. History summaries require no AI or external API requests. The compact prompt can omit lower-priority non-held rows when its 12KB budget is reached; all observations remain in SQLite. The dashboard shows archive coverage and holding horizons. `GET /api/history/NVDA?days=183` reads saved five-minute bid/ask history, paginated 2,000 points at a time via `before=next_before`. It never triggers price collection or a trading decision.
