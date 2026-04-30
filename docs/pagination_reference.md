# Auto-Pagination Reference

When a `ServiceEndpoint` has a `pagination` section in its `api_configuration`, any Scenario Step using that endpoint will automatically fetch all pages and return a single merged list.

## How It Works

1. The first request is made with the original URL (including any user-defined parameters).
2. The system reads the response, extracts the data array via `data_path`, and records its length as `effective_page_size`.
3. After each response the system checks stop conditions (in order):
   - **Empty page** (0 items) → stop
   - **`has_more_path`** present and falsy → stop
   - **Page size < `effective_page_size`** → stop (incomplete page = last page)
   - **Safety limit** reached → stop (configurable via SystemConfig `pagination_safety_limit`, default 200)
4. If none of the stop conditions are met, the pagination parameters are advanced and the next request is made.
5. All page results are merged into a single flat list and returned.

## Activation

Pagination is active when **both** conditions are met:
- The endpoint's `api_configuration` contains a `pagination` object
- The `pagination` object has a `strategy` field

No additional flags on the Scenario Step are needed. Endpoints without a `pagination` config behave exactly as before (single request).

## Pagination Config Format

Add this to `ServiceEndpoint.api_configuration`:

```json
{
  "pagination": {
    "strategy": "<offset|page|cursor|link_header>",
    "data_path": "path.to.data.array",
    ...strategy-specific fields...
  }
}
```

### Common Fields (all strategies)

| Field | Required | Description |
|-------|----------|-------------|
| `strategy` | Yes | One of: `offset`, `page`, `cursor`, `link_header` |
| `data_path` | Yes | Dot-notation path to the data array in the response (e.g. `data`, `results`, `response.items`) |
| `has_more_path` | No | Dot-notation path to a boolean/truthy field (e.g. `meta.has_more`, `paging.next`). When falsy → stop |

### Strategy: `offset`

Classic offset/limit pagination. The system increments `offset` by `effective_page_size` after each page.

```json
{
  "pagination": {
    "strategy": "offset",
    "offset_param": "offset",
    "limit_param": "limit",
    "default_limit": 100,
    "data_path": "data"
  }
}
```

| Field | Default | Description |
|-------|---------|-------------|
| `offset_param` | `"offset"` | Query parameter name for the offset value |
| `limit_param` | `"limit"` | Query parameter name for the page size |
| `default_limit` | `effective_page_size` | Value to send in `limit_param`. Falls back to the size of the first response |

**Example flow:** `?offset=0&limit=100` → 100 items → `?offset=100&limit=100` → 100 items → `?offset=200&limit=100` → 47 items → stop.

### Strategy: `page`

Page-number pagination. The system increments the page number after each page.

```json
{
  "pagination": {
    "strategy": "page",
    "page_param": "page",
    "page_size_param": "pageSize",
    "default_page_size": 50,
    "start_page": 1,
    "data_path": "results"
  }
}
```

| Field | Default | Description |
|-------|---------|-------------|
| `page_param` | `"page"` | Query parameter name for the page number |
| `start_page` | `1` | First page number (some APIs start at 0) |
| `page_size_param` | — | Query parameter name for page size (optional, only if the API accepts it) |
| `default_page_size` | — | Value for `page_size_param` |

### Strategy: `cursor`

Token/cursor-based pagination. The system reads the next cursor from the response and passes it in the next request.

```json
{
  "pagination": {
    "strategy": "cursor",
    "cursor_param": "after",
    "cursor_response_path": "paging.cursors.after",
    "has_more_path": "paging.next",
    "data_path": "data"
  }
}
```

| Field | Default | Description |
|-------|---------|-------------|
| `cursor_param` | `"cursor"` | Query parameter name to send the cursor value |
| `cursor_response_path` | — | Dot-notation path to the next cursor value in the response |

### Strategy: `link_header`

Pagination via HTTP `Link` header with `rel="next"`. The system follows the `next` URL directly.

```json
{
  "pagination": {
    "strategy": "link_header",
    "data_path": "items"
  }
}
```

No additional fields needed — the next URL comes from the response headers.

## Safety Limit

To prevent infinite loops (e.g. buggy API returning duplicates), a global safety limit is enforced. Configure it via **SystemConfig**:

- **Key:** `pagination_safety_limit`
- **Value:** `200` (or any integer)
- **Description:** Maximum number of pages per auto-paginated API call

If not set, defaults to 200.

## Important Notes

- **`effective_page_size`**: The stop condition compares each page's size against the *first page's actual size*, not `default_limit`. This handles APIs that enforce their own smaller limit regardless of what you request.
- **`offset` increment**: Uses `effective_page_size`, not `default_limit`, to avoid skipping records when the API caps page size below the requested limit.
- **Existing endpoints**: Adding a `pagination` config to an existing endpoint will change its behavior. Best practice: create a copy of the endpoint with pagination config and build new workflows on it.
- **Logs**: Each page is logged with item count and running total for debugging.
- **External requests**: Each page request is recorded as a separate entry in `external_requests` with `[page N]` suffix.
