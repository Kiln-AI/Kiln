# Verify Kiln Copilot API Key

**GET /api/provider/verify_kiln_copilot_api_key**

**Tags:** Providers & Models

Verify the stored Kiln Copilot API key against the Kiln server.

Returns `{is_valid: bool}`. A stale key the server rejects with
401/403 is cleared from local config so subsequent flows fall back to
the connect screen instead of silently using a dead key. Network
failures leave the key in place and report `false` for this check
only — they shouldn't punish the user for a transient blip.

## Responses

### 200 OK

Successful Response
