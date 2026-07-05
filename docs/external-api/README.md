# DrinkX CRM — External Read-Only API (for OS DrinkX)

This is the consumer-facing guide for OS DrinkX to pull read-only CRM data:
leads, companies, contacts, pipelines. Two surfaces expose the same
underlying data:

- **REST** — `GET`-only JSON endpoints under `/external/v1`.
- **MCP** — a remote MCP server (streamable HTTP) at `/mcp`, exposing 4
  read-only tools, for LLM-agent consumers.

Both surfaces use the same machine API key and the same underlying
services, so results are consistent between them.

## Base URLs

| Surface | Base URL |
|---|---|
| REST | `https://crm.drinkx.tech/api/external/v1` |
| MCP  | `https://crm.drinkx.tech/api/mcp` |

Nginx strips the `/api` prefix before proxying to the backend, where the
routes are actually mounted at `/external/v1` and `/mcp` respectively — the
paths below are relative to the base URLs above, so don't double up the
prefix.

## Authentication

Every request (REST and MCP) requires a Bearer machine key:

```
Authorization: Bearer drinkx_os_...
```

There is no Supabase JWT involved on this surface — the key is a standalone
machine credential scoped to one workspace (`read:core` scope). See
[Obtaining a key](#obtaining-a-key) below.

Failure modes:

| Status | Meaning |
|---|---|
| `401 Unauthorized` | missing or invalid key |
| `403 Forbidden` | key revoked, or key lacks the `read:core` scope |
| `429 Too Many Requests` | rate limit exceeded (see below) |

## Rate limit

**10 requests/second per key**, enforced as an in-memory token bucket on
each API replica. Design the nightly pull to run **sequentially** (one
request in flight at a time, or a small serial batch) rather than fanning
out concurrent requests — bursts above 10 rps will get `429`s.

## Dates

All timestamps in responses are **ISO 8601, UTC** (e.g.
`2026-07-01T00:00:00Z`).

`stage_entered_at` on a lead **may be `null`**. This happens for leads that
have no stage-history row recorded (stage history tracking started with
migration `0029`, 2026-05-16 — leads whose current stage predates that, or
that haven't changed stage since, have no row). Treat `null` as **"unknown"**,
not as a sentinel date — do not default it to lead creation time or to now.

## Pagination

List endpoints (`/leads`, `/companies`) return a page shape:

```json
{
  "items": [ ... ],
  "next_cursor": "opaque-string-or-null"
}
```

When `next_cursor` is non-null, pass it back as `?cursor=` on the next
request to get the following page. `null` means you've reached the last
page. Cursors are opaque (base64-encoded `updated_at` + row id) — don't
parse or construct them.

`limit` defaults to 50 and is capped at **100** (`limit=1..100`; values
above 100 are rejected by validation, not silently clamped — send at most
100).

## Incremental pull

Both `/leads` and `/companies` accept `?updated_since=<ISO8601 UTC>` to
fetch only rows updated at or after that timestamp — use this for the
nightly incremental sync instead of re-pulling the full dataset:

```
GET /leads?updated_since=2026-07-01T00:00:00Z&limit=100
```

Combine with cursor pagination to page through everything changed since the
last successful sync.

## REST endpoint reference

All endpoints are `GET`-only and require the `Authorization` header above.
Workspace scoping is automatic — every result is implicitly filtered to the
workspace bound to your key; there is no `workspace_id` parameter.

| Method | Path | Query params | Returns |
|---|---|---|---|
| GET | `/leads` | `pipeline_id`, `stage_id`, `assigned_to`, `updated_since`, `q`, `cursor`, `limit` (1-100, default 50) | `LeadPage` (`items[]` + `next_cursor`) |
| GET | `/leads/{lead_id}` | — | `LeadOut`, or `404` if not found |
| GET | `/leads/{lead_id}/summary` | — | `LeadSummaryOut` (lead + company + contacts + stage info), or `404` |
| GET | `/companies` | `q`, `updated_since`, `cursor`, `limit` (1-100, default 50) | `CompanyPage` (`items[]` + `next_cursor`) |
| GET | `/companies/{company_id}` | — | `CompanyOut`, or `404` |
| GET | `/contacts` | exactly one of `lead_id` **or** `company_id` (required; `400` if both or neither given) | `ContactOut[]` |
| GET | `/pipelines` | — | `PipelineOut[]` (each with nested `stages[]`) |
| GET | `/pipelines/{pipeline_id}/summary` | — | `PipelineSummaryOut` (per-stage lead counts / amounts), or `404` |
| GET | `/meta` | — | `MetaOut` (contract version, all stages, all managers) |

### curl example

```bash
curl -s "https://crm.drinkx.tech/api/external/v1/leads?limit=5" \
  -H "Authorization: Bearer $DRINKX_OS_KEY" | jq
```

Incremental pull example:

```bash
curl -s "https://crm.drinkx.tech/api/external/v1/leads?updated_since=2026-07-01T00:00:00Z&limit=100" \
  -H "Authorization: Bearer $DRINKX_OS_KEY" | jq
```

Fetch a single lead's full picture:

```bash
curl -s "https://crm.drinkx.tech/api/external/v1/leads/$LEAD_ID/summary" \
  -H "Authorization: Bearer $DRINKX_OS_KEY" | jq
```

### Response field notes

- `LeadOut.tags` is always an array (possibly empty), never null.
- `LeadOut.score` defaults to `0`, never null.
- `LeadOut.won_at` / `lost_at` are only set once the lead reaches a won/lost
  stage; otherwise `null`.
- `CompanyOut.segment` mirrors the company's primary segment.
- `ContactOut.position` mirrors the contact's job title field.
- `MetaOut.contract_version` is the current contract version string (`"1.0"`
  at the time of writing) — check this if you want to detect breaking
  changes to the shape of the API over time.

## MCP tools

The MCP server at `/mcp` uses streamable HTTP transport and the same
Bearer machine key (read per-call from the `Authorization` header — there
is no separate MCP-specific credential). It exposes 4 read-only tools that
wrap the same service layer as the REST endpoints:

| Tool | Params | Returns |
|---|---|---|
| `search_leads` | `q: str \| None`, `pipeline_id: str \| None`, `stage_id: str \| None`, `limit: int = 25` | list of lead dicts (one page, no cursoring) |
| `get_lead_summary` | `lead_id: str` (UUID) | lead summary dict, or `null` if not found |
| `pipeline_overview` | `pipeline_id: str` (UUID) | pipeline summary dict (per-stage counts/amounts), or `null` if not found |
| `list_pipelines` | — | list of pipeline dicts, each with nested stages |

All tool outputs are JSON-serializable dicts (via `model_dump(mode="json")`),
with `None`/absent fields omitted.

## Obtaining a key

An operator with server access issues a machine key via the CLI:

```bash
cd apps/api
python -m scripts.issue_service_key issue --workspace <workspace-id> --name "OS DrinkX"
```

This prints the `key_id` and the **full token — shown exactly once**. Store
it immediately in the OS side's `.env` (e.g. `DRINKX_OS_KEY=drinkx_os_...`);
the CRM only ever stores its sha256 hash and cannot show it again. If it's
lost, revoke and reissue:

```bash
python -m scripts.issue_service_key revoke --key-id <key-id>
python -m scripts.issue_service_key issue --workspace <workspace-id> --name "OS DrinkX"
```

To list existing keys for a workspace (id, active/revoked, name, last used):

```bash
python -m scripts.issue_service_key list --workspace <workspace-id>
```
