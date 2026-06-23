# ChatGPT

> **Heads up — this path is beta and plan-gated, and it changes often.** The details below reflect
> OpenAI's connector documentation as of June 2026. Custom MCP connectors in ChatGPT are evolving;
> **always check
> [OpenAI's current connector / Developer mode docs](https://platform.openai.com/docs/guides/developer-mode)
> before relying on these steps.** We don't over-promise here — if something doesn't match what you
> see in your account, OpenAI's docs are authoritative.

## What ChatGPT requires

Per OpenAI's current docs, connecting a custom MCP server to ChatGPT has two hard requirements that
differ from Claude Desktop / Claude Code:

1. **Developer mode.** Custom MCP connectors require **Developer mode**, currently in beta and
   available on **Business / Enterprise / Edu** workspaces. It is **not** documented for
   Free / Plus / Pro plans. If you don't have it, this path isn't available to you yet.
2. **A remote HTTPS MCP endpoint.** ChatGPT connects to a **remote HTTPS** endpoint — it does
   **not** launch local `stdio` servers the way Claude clients do. So you must run this server in
   HTTP mode and expose it over HTTPS.

## Step 1 — run the server in HTTP mode

```bash
datacommons-mcp serve http --host localhost --port 8080
```

This serves a Streamable HTTP MCP endpoint at `http://localhost:8080/mcp`. Set your API key in the
environment first:

```bash
export DC_API_KEY=your-api-key-here
```

(See the [Claude Code guide](claude-code.md#critical-run-this-fork-not-the-pypi-package) for how to
invoke this fork from git or a local clone if it isn't already installed.)

Flags: `--host` (default `localhost`), `--port` (default `8080`), `--verbose`, `--storage-dir`.

## Step 2 — expose it over HTTPS

ChatGPT needs to reach the endpoint over **HTTPS**. Either:

- Put it behind a tunnel, e.g. [`cloudflared`](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
  or [`ngrok`](https://ngrok.com/), which gives you a public `https://…` URL that forwards to your
  local `:8080`, **or**
- Host the server on a machine you control with a real HTTPS certificate.

Your MCP endpoint URL will be that HTTPS origin plus the `/mcp` path, e.g.
`https://your-tunnel.example.com/mcp`.

> Anything reachable over the internet is exposed. Use access controls on your tunnel/host, treat
> the endpoint as sensitive, and shut it down when you're not using it.

## Step 3 — add the connector in ChatGPT

In a workspace that has Developer mode:

1. Enable **Developer mode**.
2. Go to **Settings → Apps → Create**.
3. Enter your HTTPS MCP endpoint URL (the `…/mcp` URL from Step 2).
4. **Scan Tools** — ChatGPT discovers `search_indicators` and `get_observations`.
5. **Create** to finish adding the connector.

Exact menu labels and flow may differ in your account as OpenAI iterates — follow the on-screen
steps and OpenAI's docs if they diverge from the above.

## Limitations to be honest about

- This requires a qualifying plan **and** a publicly reachable HTTPS endpoint you operate — it's
  more involved than the Claude clients.
- It is **beta**: availability, UI, and requirements can change without notice.
- Large-result CSV exports are written to the **server's** `DC_STORAGE_DIR`, i.e. wherever you run
  `serve http` — not to the ChatGPT user's machine.

If any of this doesn't match your current ChatGPT experience, defer to
[OpenAI's connector documentation](https://platform.openai.com/docs/guides/developer-mode).
