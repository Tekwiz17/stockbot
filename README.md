# StockBot

An independent AI trading experiment with $100,000 of **simulated** capital. The public dashboard shows positions, fractional shares, equity, realized/unrealized gains, transactions and the agent's journal. Humans can pause, resume a pause, or permanently stop the experiment. They cannot submit prompts, place trades, edit balances, or change its strategy through the app.

The frontend is static on Vercel. One continuously running Python process on Hack Club Nest owns the SQLite database, Alpaca IEX stream, research loop, and simulation. Website visits never trigger AI calls or trades. No Alpaca trading/account endpoints are implemented or called.

## Deployment status

Source and tests are ready. The backend has **not** been installed or started on Nest: the build workspace could not reach SSH (DNS failure / no IPv6 route). A temporary Vercel design preview was deployed on October 3, 2026; it requires claiming to become permanent. There are no live trades or fabricated preview balances. The Nest domain in `vercel.json` is the planned address, not a verified active service.

## Behavior

- During the XNYS regular session, deliberates about every ten minutes; up to six independent actions per cycle. An active full session permits roughly 39 deliberations, potentially hundreds of fills including AI-planned stop losses and profit targets.
- Aggressive catalyst and momentum mandate, targeting 70–95% exposure across multiple names. This is a policy given to the model, not a guarantee it always trades or makes money. A model may hold when evidence is insufficient.
- Holds long stocks and ETFs, supports microshare precision, a $10 minimum fill, no leverage or shorting, and a 30% single-position maximum.
- Uses ask plus 5 bps to buy and bid minus 5 bps to sell. Quotes must be no more than 90 seconds old with a valid spread under 2%. A fill is atomic and cannot overdraft cash or sell unowned shares. These are simplified simulated fills, without actual liquidity/queue modeling.
- Studies realized outcomes by symbol, recent trade theses and prior notes before each decision. Closed sessions—including holidays and weekends—get one reflection per New York calendar day after 10 AM. Market holidays and half-days use `exchange-calendars`.
- Streams a curated universe of 30 US stocks/ETFs through IEX, compatible with Alpaca Basic. Stores quote samples every 15 seconds per symbol, retains 14 days of samples, and permanently retains fills and decisions. Uses a batched REST quote fallback only when needed.
- A pause suspends execution (including planned exits), research and streams. A stop is permanent through the app and preserves holdings without forced liquidation. Restarting the server preserves state.

## Budget controls

StockBot uses the owner's stated **$0.60/day** allocation, regardless of the larger generic allowance in Hack Club's public docs.

| Provider | StockBot limit | Mechanism |
| --- | --- | --- |
| Hack Club AI | $0.45 reserved / rolling 24h; 42 completions maximum | Fetches live model pricing; reserves full input/output bound with 20% margin **before** calling. Timeouts and failures keep their reserve. Unknown/expensive pricing suspends AI. |
| Hack Club Search | 48 searches / rolling 24h | Caches news, selects the next query autonomously, retains local request counts across restarts. |
| Alpaca REST | 20 requests / rolling 60 seconds | Only batch latest IEX quotes; normally about one call per ten-minute cycle if streaming fails. |
| Alpaca stream | One worker connection; 30 symbols | Backoff on errors; no per-visitor upstream connection. |
| Vercel | Static assets and cached reverse proxy | No Vercel cron or AI functions; visitors poll at most once per minute while visible. |

Preferred models, subject to live affordable pricing: DeepSeek V4 Pro, DeepSeek V4.1 Flash, DeepSeek V4 Flash, DeepSeek V3.2, Qwen3 235B A22B, DeepSeek V3, Qwen3 32B, Gemini 2.5 Flash Lite, Gemini 2.5 Flash. A live V4 Pro completion succeeded. Its output billing exceeded the catalog estimate, so requests now explicitly cap upstream routing at $0.22/M input and $2.70/M output, with a fixed conservative $0.009528 reservation (including 20% margin), or $0.400176 for 42 calls. Higher-priced candidates are rejected. Unexpected reported cost above the reservation suspends further AI calls. The bot rejects any candidate whose conservative maximum request exceeds $0.01. Saved `Models.html` was used as a model-directory reference, not as current billing authority. AI calls use Hack Club, not OpenRouter directly; OpenRouter's public catalog is used only to look up explicit model prices if Hack Club's catalog omits them.

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

This is an experiment, not a brokerage or investment recommendation. It does not model commissions, taxes, dividends, splits, corporate actions, liquidity, market impact or trading halts. A split can distort raw price-based returns until corporate-action accounting is added. IEX is not a consolidated all-exchange quote. The fixed stream universe limits discovery to 30 names. Model notes provide feedback memory, not trained model-weight updates. There is no proof of profitability and no promise of a minimum trade count.

Provider references: [Alpaca market data plans](https://docs.alpaca.markets/us/docs/about-market-data-api), [Hack Club AI docs](https://docs.ai.hackclub.com/), [Hack Club Search docs](https://search.hackclub.com/docs), [Nest quickstart](https://guides.hackclub.app/index.php/Quickstart).

## Update an existing Nest installation

```sh
cd /root/stockbot
git pull --ff-only
bash deploy/install-nest.sh
```

The installer preserves provider credentials and the database, adds `https://stockbot.tekwiz17.me` to allowed origins, rewrites the service to use `backend.serve`, and restarts it. This fixes the IPv6-only listener that may prevent an IPv4 reverse-proxy connection. Verify locally using both `http://127.0.0.1:8765/api/health` and `http://[::1]:8765/api/health`.
