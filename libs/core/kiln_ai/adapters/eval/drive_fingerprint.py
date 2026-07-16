"""Content identity for eval-time multi-turn drives.

A drive fingerprint hashes everything that shapes a driven conversation —
the synthetic-user drive config, the resolved run-config properties of the
agent under test, and the scenario content. Two records with equal
fingerprints (and the same run config) were driven under identical
conditions, so one stored trace can stand in for the other's drive.
"""

import hashlib
import json

from kiln_ai.datamodel.eval import (
    MultiTurnDriveConfig,
    MultiTurnSyntheticEvalInputData,
)
from kiln_ai.datamodel.run_config import RunConfigProperties

# Version prefix on every fingerprint: bumping it makes all old fingerprints
# implicitly non-matching if the hash recipe ever changes (v1 never equals v2).
_FINGERPRINT_VERSION = "v1"


def compute_drive_fingerprint(
    drive_config: MultiTurnDriveConfig,
    run_config_properties: RunConfigProperties,
    data: MultiTurnSyntheticEvalInputData,
) -> str:
    """sha256 over canonical JSON of the drive-shaping inputs, as "v1:<hex>".

    Includes only what shapes the conversation. Deliberately excluded:
    EvalInput reference data and judge/eval-config properties (they shape the
    judgment, not the drive) and the EvalInput id (identical scenarios must
    fingerprint identically regardless of which eval's input carries them).
    """
    payload = {
        "drive": {
            "model_name": drive_config.model_name,
            "model_provider": drive_config.model_provider,
            "turns": drive_config.turns,
        },
        # Resolved properties rather than the TaskRunConfig id: ids stay
        # stable while the properties behind them are edited, which would
        # silently reuse traces from a different agent configuration.
        "run_config": run_config_properties.model_dump(mode="json"),
        "scenario": {
            "first_message": data.first_message.text if data.first_message else None,
            "synthetic_user_info": data.synthetic_user_info.model_dump(mode="json"),
        },
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{_FINGERPRINT_VERSION}:{digest}"
