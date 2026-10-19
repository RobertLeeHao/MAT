# MCP catalog

`https://robertleehao.github.io/MAT/mcp/v1/catalog.json` — the servers MAT offers on **Settings › Tools › Browse**.
Same delivery as the rankings: the app keeps a local copy, refreshes it in the background when it is older than 12 hours, and falls back to the copy bundled in the app.

## Rules
- **Hand-picked, not open.** Entries are added by us, never merged from outside PRs without a review.
- **Only reviewed entries ship.** The app shows an entry only when `reviewed` is set: `{"by": "...", "date": "YYYY-MM-DD"}`.
- **Pinned.** Every local package has an exact `version`. Never `latest`. A new version means a new review.
- **Official first.** Prefer the vendor's own remote server (`transport: remote`). `registry` is the name in the official MCP Registry (registry.modelcontextprotocol.io) when there is one; MAT reads remotes/packages from there only as a cross-check, never to replace what is pinned here.
- **Defaults.** Reads → `allow`, changes → `ask`. Anything that moves money or deletes goes in `overrides` as `off`.

## Fields
| field | meaning |
|---|---|
| `id` | stable key; the app remembers what you added by it |
| `summary.en / .zh` | one line under the name |
| `category` | heading in the Browse sheet |
| `logo` | name of the bundled logo (`Logo / <name>` in Figma); `Server` when there is none |
| `transport` | `remote` (URL) or `local` (runs on this Mac) |
| `remote.auth` | `oauth` (browser sign-in), `key`, `token`, `none` |
| `local.runtime` | `npx` or `uvx`; `needs` lists what must be installed |
| `local.args` | `{folders}`, `{folder}`, `{app_id}`… are filled in from what the user enters |
| `local.env` | keys the user types once; `secret: true` goes to the keychain |
| `regions` | `cn` entries are listed first for Chinese UI languages |
| `suggested` | shown on the empty Tools page (keep to four) |
| `availability.status` | `ready`, `needs-setup` or `unavailable` — see below |
| `availability.reason` | one sentence, en + zh, shown under the name **before** anyone ticks it |
| `availability.blocker` | `kind` (paid-key, admin-app, real-name, client-approval, app-approval, oauth-verification, publisher-verification, oauth-app) and `who` (user, company, mat) |
| `note` | for the reviewer; not shown in the app |

## First draft (2026-10-15)
40 entries, all `reviewed: null`: 25 ready, 10 needs-setup, 5 unavailable. Remote URLs and registry names were read from the official registry on 2026-10-15; npm/PyPI versions were the latest that day. Entries whose `note` says *verify* need their endpoint, args or env checked before review.

## Availability — say it before anyone starts
Every common server is listed, even when it cannot be used yet, and the problem is shown up front instead of after a sign-in fails.

- **ready** — tick and go. At most a browser sign-in or a free account on that service.
- **needs-setup** — works, but the user (or their company) must get something first. The row shows the requirement in place of the summary and the tag says what kind: PAID KEY, ADMIN, REAL NAME. Still tickable.
- **unavailable** — listed but not tickable; tag NOT YET. The reason says what MAT itself still has to do.

### Blockers today (2026-10-15)
| server | status | blocker | who |
|---|---|---|---|
| Figma | unavailable | Only approved clients may connect; full use needs a paid Dev/Full seat (to verify) | MAT applies · user pays seat |
| Slack | unavailable | Official MCP accepts approved apps only (to verify) | MAT |
| Gmail, Drive & Calendar | unavailable | Google app verification + paid yearly security assessment (restricted scopes) | MAT |
| Outlook, Teams & OneDrive | unavailable | Microsoft publisher verification; many tenants need admin consent | MAT · company |
| GitHub · browser sign-in | unavailable | GitHub OAuth app for MAT. GitHub itself works with a personal access token | MAT |
| Brave Search | needs-setup | API key; free plan still needs a card | user |
| Exa | needs-setup | API key; free credits then paid | user |
| Perplexity | needs-setup | API key, paid per request | user |
| Tavily | needs-setup | API key; monthly free allowance then paid | user |
| Firecrawl | needs-setup | API key; free credits then paid | user |
| Apify | needs-setup | Usage credits; small free amount then paid | user |
| 飞书 / Lark | needs-setup | App on 飞书开放平台, admin approval | company |
| 钉钉 | needs-setup | App on 钉钉开放平台, admin approval | company |
| 高德地图 | needs-setup | Real-name developer account + key | user |
| 百度地图 | needs-setup | Real-name developer account + AK | user |

Also worth knowing (ready, but): Notion, Linear, Atlassian, Asana, monday, Todoist, Airtable, Miro, Canva, Zapier, GitLab, Sentry, Hugging Face, Supabase, Neon, Stripe, PayPal need the user's own account on that service (all have free tiers; Zapier's free plan has a task cap). Stripe and PayPal touch real money, so their write tools default to Off.

## domains（2026-10-15）
本机服务器可以带 `domains`：除了 npm / PyPI / GitHub 这些下载包的地址，它只能连这里列出的域名（`*.example.com` 匹配子域名）。MAT 用本机代理 + 沙箱执行，IP 地址和本机服务一律不通。`["*"]` = 任何公网域名，但解析到内网（127/8、10/8、192.168/16、169.254/16 等）的一律拒绝；Fetch 用这个，同时沙箱关掉 DNS，所以 Fetch 自带的内网检查不会被 Clash/Surge 的 fake-ip（198.18.0.0/15）误伤。没有这个字段 = 不限网络（browser、mongodb 以及用户自己加的服务器）。写错了的话，行上会写出被拦的域名。
