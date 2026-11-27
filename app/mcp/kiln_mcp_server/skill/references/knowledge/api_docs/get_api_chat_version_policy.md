# Client version policy

**GET /api/chat/version_policy**

**Tags:** Copilot

Check whether this app version must or should upgrade for the Kiln Assistant.

Proxies Kiln Copilot's ``GET /v1/chat/version_policy``. Lets the assistant page
show the upgrade banners on load. Forwards the desktop version header so the
server can compute the verdict; on any upstream/transport failure we degrade to
"no banner" rather than error.

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|required|boolean||
|upgrade_nudge_version|one of: string or null||
