# MAT relay

Lets a phone reach MAT on a Mac that isn't on the same Wi-Fi — no accounts, no port opened
at home. The Mac keeps one outgoing WebSocket here; a phone opens another; this Worker copies
bytes between them. The phone and the Mac encrypt end to end (X25519 + ChaCha20-Poly1305,
`MATDemo/docs/remote-protocol.md` §4–§5), so the relay only ever handles ciphertext and keeps
nothing. Protocol: §9 of the same file.

```
wss://relay.askmat.app/v1/host/<host key>   the Mac (proves it holds the key)
wss://relay.askmat.app/v1/r/<host key>      a phone or another computer
```

One Durable Object per host key (WebSocket hibernation: idle Macs cost nothing).

## Try it locally

```sh
npm install
npm run dev                 # ws://127.0.0.1:8787
npm test                    # MATDemo/tools/remote/selftest.py --relay ws://127.0.0.1:8787
```

## Deploy (once)

1. `npx wrangler login` (the Cloudflare account that has askmat.app).
2. In `wrangler.jsonc`, uncomment the `routes` line (`relay.askmat.app`, custom domain).
3. `npm run deploy`.
4. Check: `curl https://relay.askmat.app/` answers "MAT relay — …".

SQLite-backed Durable Objects are on the Workers Free plan (check current limits); the relay stores nothing,
it only uses them to hold sockets.

## Self-host

`MATDemo/tools/remote/relay.py` follows the same rules. Run it behind any TLS proxy and put its
`wss://` address in MAT › Settings › Devices › Relay › Change.

## Limits

16 devices per Mac at once (4429), one message ≤ 1 MiB, the Mac must answer the challenge
within 10 s. In mainland China Cloudflare can be slow or blocked on some networks; Tailscale or
a self-hosted relay are the fallback.
