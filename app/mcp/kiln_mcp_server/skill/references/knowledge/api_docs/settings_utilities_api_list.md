# Settings & Utilities API

Server settings, connectivity checks, and utility endpoints.

|Endpoint|Method|Name|Description|Details File|
|-|-|-|-|-|
|`/ping`|GET|Ping Server|Ping the server to check connectivity.|get_ping.md|
|`/api/settings`|GET|Get Settings|Get the user's Kiln settings. Secrets such as API keys are hidden.|get_api_settings.md|
|`/api/settings/{item_id}`|GET|Get Setting Item|Get one Kiln setting by name. Null when it is not set; secrets are hidden.|get_api_settings_item_id.md|
|`/api/check_entitlements`|GET|Check Entitlements|Check whether the authenticated user has the given entitlements.  The feature_codes parameter should...|get_api_check_entitlements.md|
