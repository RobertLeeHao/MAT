// MAT relay · Cloudflare Worker (protocol: MATDemo/docs/remote-protocol.md §9).
//
// Lets a phone reach a Mac that is not on the same network: the Mac keeps one outgoing
// WebSocket to its mailbox here, a phone opens another, and this copies bytes between
// them. Everything after the two v1 hello frames is end-to-end encrypted between phone
// and Mac, so the relay only ever handles ciphertext. No accounts, no storage.
//
//   wss://relay.askmat.app/v1/host/<host key>   the Mac (proves it holds the key)
//   wss://relay.askmat.app/v1/r/<host key>      a phone or another computer
//
// Same rules as the reference relay, MATDemo/tools/remote/relay.py; `npm test` runs the
// selftest against `npm run dev`.

import { DurableObject } from "cloudflare:workers";

const AUTH_LABEL = new TextEncoder().encode("MAT relay v1");
const MAX_STREAMS = 16; // remotes connected to one host at once
const AUTH_MS = 10_000; // a host has this long to answer the challenge
const MAX_PENDING = 4; // challenges open at once (someone who knows the key can't crowd the Mac out)
const T_TEXT = 1, T_BINARY = 2; // first byte of a host-side data frame
const PATH = /^\/v1\/(host|r)\/([A-Za-z0-9_-]{43})$/;

const b64u = (buf) => {
  let s = "";
  for (const b of new Uint8Array(buf)) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
};
const unb64u = (s) => {
  const t = s.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((s.length + 3) % 4);
  return Uint8Array.from(atob(t), (c) => c.charCodeAt(0));
};
const validKey = (k) => {
  try {
    const b = unb64u(k);
    return b.length === 32 && b64u(b) === k;
  } catch {
    return false;
  }
};

/** Accept a socket only to close it with a code the app understands. */
function refuse(code, reason) {
  const [client, server] = Object.values(new WebSocketPair());
  server.accept();
  server.addEventListener("error", () => {}); // the phone hanging up first is fine
  server.close(code, reason);
  return new Response(null, { status: 101, webSocket: client });
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (req.headers.get("Upgrade") !== "websocket") {
      if (url.pathname === "/") {
        return new Response("MAT relay — connects your phone to MAT on your Mac. It only sees encrypted bytes. https://askmat.app\n",
          { headers: { "content-type": "text/plain; charset=utf-8" } });
      }
      return new Response("not found\n", { status: 404 });
    }
    const m = url.pathname.match(PATH);
    if (!m || !validKey(m[2])) return refuse(4400, "bad path");
    return env.MAILBOX.get(env.MAILBOX.idFromName(m[2])).fetch(req);
  },
};

/** One host key: the Mac's socket (tag "h") and its remotes (tags "r", "s:<sid>"). */
export class Mailbox extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    // keepalive from the Mac without waking this object
    ctx.setWebSocketAutoResponse(new WebSocketRequestResponsePair('{"t":"ping"}', '{"t":"pong"}'));
  }

  host() {
    return this.ctx.getWebSockets("h").find((w) => w.deserializeAttachment()?.role === "host");
  }

  async fetch(req) {
    const url = new URL(req.url);
    const [, role, key] = url.pathname.match(PATH);
    const [client, server] = Object.values(new WebSocketPair());

    if (role === "host") {
      const kp = await crypto.subtle.generateKey({ name: "X25519" }, true, ["deriveBits"]);
      const r = b64u(await crypto.subtle.exportKey("raw", kp.publicKey));
      const n = b64u(crypto.getRandomValues(new Uint8Array(16)));
      const priv = b64u(await crypto.subtle.exportKey("pkcs8", kp.privateKey));
      // each socket answers its own challenge; only the oldest extra one goes
      const pending = this.ctx.getWebSockets("h").filter((w) => w.deserializeAttachment()?.role === "pending")
        .sort((a, b) => a.deserializeAttachment().at - b.deserializeAttachment().at);
      while (pending.length >= MAX_PENDING) pending.shift().close(4408, "too many");
      this.ctx.acceptWebSocket(server, ["h"]);
      // the relay's own name goes into the MAC: a relay can't pass on another relay's challenge
      server.serializeAttachment({ role: "pending", key, priv, r, n, name: url.host, at: Date.now() });
      server.send(JSON.stringify({ t: "challenge", r, n }));
      await this.ctx.storage.setAlarm(Date.now() + AUTH_MS);
      return new Response(null, { status: 101, webSocket: client });
    }

    const host = this.host();
    if (!host) return refuse(4404, "host offline");
    if (this.ctx.getWebSockets("r").length >= MAX_STREAMS) return refuse(4429, "too many devices");
    let sid;
    do {
      sid = crypto.getRandomValues(new Uint32Array(1))[0];
    } while (this.ctx.getWebSockets("s:" + sid).length);
    this.ctx.acceptWebSocket(server, ["r", "s:" + sid]);
    server.serializeAttachment({ role: "remote", sid });
    try {
      host.send(JSON.stringify({ t: "open", s: sid }));
    } catch {
      server.close(4404, "host offline"); // the Mac's socket was closing
    }
    return new Response(null, { status: 101, webSocket: client });
  }

  async webSocketMessage(ws, data) {
    const a = ws.deserializeAttachment() || {};

    if (a.role === "verifying" || a.role === "replaced") return;
    if (a.role === "pending") {
      // no second answer while the first is being checked
      ws.serializeAttachment({ ...a, role: "verifying" });
      if (!(await this.verify(a, data))) {
        ws.close(4401, "not this host");
        return;
      }
      // the Mac reconnected: the new socket wins, the old one and its streams go
      const old = this.host();
      if (old && old !== ws) {
        old.serializeAttachment({ role: "replaced" });
        old.close(4409, "replaced");
        for (const r of this.ctx.getWebSockets("r")) r.close(4404, "host offline");
      }
      ws.serializeAttachment({ role: "host" });
      ws.send(JSON.stringify({ t: "ready" }));
      return;
    }

    if (a.role === "host") {
      if (typeof data === "string") {
        let c;
        try {
          c = JSON.parse(data);
        } catch {
          return;
        }
        if (c.t === "close") {
          for (const r of this.ctx.getWebSockets("s:" + c.s)) r.close(1000, "closed by host");
        }
        return;
      }
      const b = new Uint8Array(data);
      if (b.length < 5 || (b[0] !== T_TEXT && b[0] !== T_BINARY)) return;
      const sid = new DataView(b.buffer, b.byteOffset, 5).getUint32(1);
      const payload = b.subarray(5);
      for (const r of this.ctx.getWebSockets("s:" + sid)) {
        r.send(b[0] === T_TEXT ? new TextDecoder().decode(payload) : payload);
      }
      return;
    }

    if (a.role === "remote") {
      const host = this.host();
      if (!host) {
        ws.close(4404, "host offline");
        return;
      }
      const isText = typeof data === "string";
      const payload = isText ? new TextEncoder().encode(data) : new Uint8Array(data);
      const f = new Uint8Array(5 + payload.length);
      f[0] = isText ? T_TEXT : T_BINARY;
      new DataView(f.buffer).setUint32(1, a.sid);
      f.set(payload, 5);
      try {
        host.send(f);
      } catch {
        ws.close(4404, "host offline");
      }
    }
  }

  async verify(a, data) {
    try {
      const msg = JSON.parse(data);
      if (msg.t !== "auth" || typeof msg.m !== "string") return false;
      const priv = await crypto.subtle.importKey("pkcs8", unb64u(a.priv), { name: "X25519" }, false, ["deriveBits"]);
      const pub = await crypto.subtle.importKey("raw", unb64u(a.key), { name: "X25519" }, false, []);
      const shared = await crypto.subtle.deriveBits({ name: "X25519", public: pub }, priv, 256);
      const mac = await crypto.subtle.importKey("raw", shared, { name: "HMAC", hash: "SHA-256" }, false, ["verify"]);
      const n = unb64u(a.n), r = unb64u(a.r), name = new TextEncoder().encode(a.name || "");
      const signed = new Uint8Array(AUTH_LABEL.length + name.length + n.length + r.length);
      signed.set(AUTH_LABEL, 0);
      signed.set(name, AUTH_LABEL.length);
      signed.set(n, AUTH_LABEL.length + name.length);
      signed.set(r, AUTH_LABEL.length + name.length + n.length);
      return await crypto.subtle.verify("HMAC", mac, unb64u(msg.m), signed);
    } catch {
      return false;
    }
  }

  async webSocketClose(ws) {
    this.gone(ws);
  }

  async webSocketError(ws) {
    this.gone(ws);
  }

  gone(ws) {
    const a = ws.deserializeAttachment() || {};
    if (a.role === "host") {
      for (const r of this.ctx.getWebSockets("r")) r.close(4404, "host offline");
    } else if (a.role === "remote") {
      const host = this.host();
      try {
        if (host) host.send(JSON.stringify({ t: "close", s: a.sid }));
      } catch {
        /* the Mac's socket is going too */
      }
    }
    try {
      ws.close(1000, "bye");
    } catch {
      /* already closed */
    }
  }

  async alarm() {
    // a host socket that never answered the challenge
    for (const w of this.ctx.getWebSockets("h")) {
      const a = w.deserializeAttachment();
      if ((a?.role === "pending" || a?.role === "verifying") && Date.now() - a.at >= AUTH_MS - 50) w.close(4401, "no answer");
    }
  }
}
