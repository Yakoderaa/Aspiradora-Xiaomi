from typing import Any

from xiaomi_e10_map_v62 import XiaomiE10MapV62


class XiaomiE10MapV64(XiaomiE10MapV62):
    """V64: build-map oficial del xiaomi.vacuum.b112."""

    def _probe_state(self, force: bool = False) -> dict[str, Any]:
        state = dict(super()._probe_state(force=force) or {})
        vacuum = getattr(self, "vacuum", None)
        build_diag = dict(getattr(vacuum, "last_map_build_diag", {}) or {}) if vacuum else {}

        armed = bool(build_diag.get("success"))
        state["build_armed"] = armed
        if armed:
            if not state.get("saved_map") and not state.get("pending_map") and not state.get("building"):
                state["status"] = "new_map_armed"
            if state.get("privacy_enabled") is not False:
                state["allow_realtime_upload"] = True

        # Mantener coherente el cache heredado para que load/request_fresh_upload
        # vean el estado aumentado y no vuelvan a bloquear realtime por cur-map-id=0.
        self._v61_state = dict(state)

        diag = dict(
            getattr(self, "last_v62_diagnostics", {})
            or getattr(self, "last_v61_diagnostics", {})
            or {}
        )
        diag["state"] = dict(state)
        diag["build_request"] = build_diag
        diag["v64_exact_model"] = "xiaomi.vacuum.b112"
        diag["v64_remember_state_gate_removed"] = True
        diag["v64_map_privacy_semantics"] = "0=Enable,1=DisEnable"
        diag["skip_realtime_upload"] = not bool(state.get("allow_realtime_upload"))
        if diag["skip_realtime_upload"]:
            diag["skip_reason"] = (
                "sin mapa guardado/pendiente/build armado o map-privacy=1"
            )
        else:
            diag["skip_reason"] = ""

        self.last_v61_diagnostics = dict(diag)
        self.last_v62_diagnostics = dict(diag)
        self.last_v64_diagnostics = dict(diag)
        return state
