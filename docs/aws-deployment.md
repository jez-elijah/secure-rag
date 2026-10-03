# Deployed on AWS (EC2 + Docker Compose)

The FastAPI service from this repo runs on a single AWS EC2 instance using the project's
`Dockerfile` and `docker-compose.yml`. This page records how, and what the limits are.

## Setup

| Piece | Choice |
|---|---|
| Compute | One EC2 instance, Ubuntu 24.04 LTS (x86_64), 4 GB or more of RAM, 30 GiB gp3 disk |
| Runtime | Docker Engine and Docker Compose, built from this repo (`docker compose up -d --build`) |
| Network | Security group allows SSH (22) and the API (8000) from one IP address only |
| Secrets | `.env` on the server (mode 600): `ANTHROPIC_API_KEY`, `AUTH_SECRET`. Never committed |
| LLM access | A workspace-scoped Anthropic API key with a spend limit |
| State | Named Docker volume: vector index, users database, audit and auth logs |

## What was done

1. Launched the instance and restricted the security group to a single IP.
2. Installed Docker, cloned the repo, created `.env`, and ran `docker compose up -d --build`.
3. Seeded users with `docker compose run --rm api python scripts/seed_users.py`.
4. Verified `/health`, then `/login` and `/ask` through the interactive docs at `/docs`.

## Problems found while deploying, and fixes

- **Startup failed on a mistyped `AUTH_SECRET` name.** The app refuses to start without a secret of
  32+ characters (fail fast), which turned a silent misconfiguration into a clear error.
- **Model calls returned 502 with no cause.** The API correctly hides upstream errors from clients,
  but did not log them. It now logs the status, error type, request id, and message server-side
  (never the question text). The root cause here was an API key that was not scoped to a workspace.
- **First request was slow** because models loaded on demand. The API now loads the embedding model
  and the PII analyzer at startup (`SECURE_RAG_WARMUP=0` disables this).

## Updating the server

```bash
cd ~/secure-rag
git pull
docker compose up -d --build
docker compose logs --tail 30
```

## Limitations

- Single instance, no load balancer, no autoscaling, no TLS. The API is not exposed publicly:
  the demo accounts have predictable passwords and each request spends LLM credits.
- No login rate limiting (see the main README). Put the service behind HTTPS and a reverse proxy,
  add rate limiting, and replace demo accounts before any public exposure.
- Infrastructure was created by hand in the console, not with infrastructure-as-code.

## Latency on EC2

```bash
docker compose exec api python eval/benchmark_latency.py --label aws_ec2
```

Run on the instance, this measures the same stages as on a laptop. The `llm` stage includes the
network round trip from the instance's region to the Anthropic API.
