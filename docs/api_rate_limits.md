# API Rate Limits (Redis-backed)

## Why

Gunicorn runs multiple workers. Without shared state, per-worker in-memory counters can exceed third-party API limits.

A shared limiter is required to enforce limits reliably across workers.

## Backend Design

Implementation uses Redis-backed counters with TTL windows.

Applied in runtime API execution paths:
- Scenario API calls (`_do_single_request`)
- Scenario paginated API calls (`_do_paginated_request`, each page request)
- Single method test execution (`execute_single_method`)

## Configuration Source

Rate limits are configured via:
- `integrations.SystemConfig`
- key: `api_rate_limits`

Flat format:

```json
{
  "scope": "auth",
  "default": { "requests": 60, "per_seconds": 60, "mode": "wait" },
  "rules": [
    { "match": { "host": "www.virustotal.com" }, "requests": 4, "per_seconds": 60, "mode": "wait" }
  ]
}
```

## Config Semantics

- `scope`
  - `auth` (recommended default in this project)
  - `host`
  - `host+auth`
- `default`
  - fallback limit for requests without a matching rule
- `rules[]`
  - first matching rule wins
  - currently host-based matching: `match.host`
- `mode`
  - `wait`: block until window allows request
  - otherwise limiter raises an error (fail-fast behavior)

## Scope and Auth Object

For `scope=auth`, limiter key is derived from resolved `ApiAuthID` (`auth_obj.pk`) used by Scenario step runtime.

If auth object is missing, limiter falls back to `auth:none` scope key.

## Redis Runtime

Expected runtime dependency:
- Python package: `redis`
- Redis service reachable via:
  - `REDIS_URL` env var, or
  - default `redis://127.0.0.1:6379/0`

## Fail-Open Behavior

If Redis is unavailable, limiter currently fails open (request proceeds).

Reason:
- avoid hard runtime outage due to infra dependency.

Operationally, monitor Redis health if strict enforcement is required.

## Troubleshooting

### Cloudflare timeout vs invalid upstream response

If run-tests console shows:
- `Invalid JSON response: <!DOCTYPE html ...>`

This is usually an upstream non-JSON response (often external edge/WAF behavior), not necessarily Cloudflare 524 on your app.

Use `external_requests` to inspect:
- target URL
- request headers
- response status/body

For VirusTotal specifically, validate:
- API endpoint path is correct (API URL, not web page URL),
- expected auth header is injected.

