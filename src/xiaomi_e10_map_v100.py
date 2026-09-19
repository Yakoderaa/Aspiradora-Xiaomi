import time

from xiaomi_e10_map_v93 import XiaomiE10MapV93


class XiaomiE10MapV100(XiaomiE10MapV93):
    """V100: fast-path del slot 0 para dibujar el grid Xiaomi mientras nace.

    La cadena V57 conserva el gate fuerte para considerar/persistir un mapa
    completo. Este cliente agrega una lectura live que evita ese gate sólo para
    entregar al renderer un snapshot B112 parcial ya descifrado.
    """

    LIVE_REFRESH_ACTIONS = (
        (18, [], "upmapdata"),
        (15, [0], "upload-by-maptype-ii"),
        (6, [0], "upload-by-maptype"),
    )
    LIVE_SETTLE_SECONDS = 0.55

    def __init__(self, *args, **kwargs):
        self._v100_live_hash = None
        self._v100_live_reads = 0
        self._v100_live_changes = 0
        self._v100_live_decode_ok = 0
        self._v100_live_errors = []
        self._v100_refresh_index = 0
        self._v100_refresh_attempts = 0
        self._v100_refresh_ok = 0
        self.last_v100_diagnostics = {}
        super().__init__(*args, **kwargs)

    def reset_v100_live(self, reason="nueva sesión"):
        self._v100_live_hash = None
        self._v100_live_reads = 0
        self._v100_live_changes = 0
        self._v100_live_decode_ok = 0
        self._v100_live_errors = []
        self._v100_refresh_index = 0
        self._v100_refresh_attempts = 0
        self._v100_refresh_ok = 0
        self.last_v100_diagnostics = {"reset_reason": str(reason)}

    def request_live_upload(self):
        """Pide una actualización oficial, una acción por ciclo.

        No ejecuta el ciclo estructurado largo V60. Si el blob no cambia, el
        siguiente intento rota 18 -> 15 -> 6; cuando cambia vuelve a 18.
        """
        index = int(self._v100_refresh_index) % len(self.LIVE_REFRESH_ACTIONS)
        aiid, params, label = self.LIVE_REFRESH_ACTIONS[index]
        self._v100_refresh_attempts += 1
        try:
            item, _refs, _response = self._call_lan_action_exact(
                aiid,
                list(params),
                f"{label} V100-live",
            )
            ok = bool(item.get("ok")) and not item.get("error")
            if ok:
                self._v100_refresh_ok += 1
            self._v100_refresh_index = (index + 1) % len(self.LIVE_REFRESH_ACTIONS)
            time.sleep(self.LIVE_SETTLE_SECONDS)
            return {
                "ok": ok,
                "action": f"10/{aiid}",
                "label": label,
                "error": item.get("error"),
            }
        except Exception as exc:
            self._v100_live_errors.append(
                f"refresh 10/{aiid}: {self._sanitize_error(exc)}"
            )
            self._v100_live_errors = self._v100_live_errors[-8:]
            self._v100_refresh_index = (index + 1) % len(self.LIVE_REFRESH_ACTIONS)
            return {
                "ok": False,
                "action": f"10/{aiid}",
                "label": label,
                "error": self._sanitize_error(exc),
            }

    def load_live_partial(self):
        """Descarga slot 0 y devuelve snapshot B112 aunque V57 aún sea False."""
        started = time.monotonic()
        self._v100_live_reads += 1
        raw = b""
        endpoint = None
        status = None
        sha = None
        changed = False
        try:
            raw, endpoint, status = self._download_slot("0")
            sha = self._sha12(raw)
            changed = bool(
                self._v100_live_hash
                and sha
                and sha != self._v100_live_hash
            )
            if changed:
                self._v100_live_changes += 1
                self._v100_refresh_index = 0

            decoded = self._decode_b112_payload(raw)
            if decoded is None or not decoded.get("exact_b112_grid"):
                raise RuntimeError("slot 0 no contiene grid B112 exacto")

            snapshot = self._snapshot_from_grid(
                "v100-slot0-live",
                endpoint,
                raw,
                decoded,
            )
            self._v100_live_decode_ok += 1
            self._v100_live_hash = sha or self._v100_live_hash

            metrics = dict(
                getattr(snapshot, "v93_grid_metrics", {})
                or getattr(snapshot, "v92_grid_metrics", {})
                or self._grid_metrics(getattr(snapshot, "grid_cells", []) or [])
            )
            self.last_v100_diagnostics = {
                "ok": True,
                "duration_ms": int((time.monotonic() - started) * 1000),
                "http": status,
                "bytes": len(raw),
                "sha12": sha,
                "changed": changed,
                "reads": self._v100_live_reads,
                "changes": self._v100_live_changes,
                "decode_ok": self._v100_live_decode_ok,
                "refresh_attempts": self._v100_refresh_attempts,
                "refresh_ok": self._v100_refresh_ok,
                "refresh_next": self.LIVE_REFRESH_ACTIONS[
                    int(self._v100_refresh_index) % len(self.LIVE_REFRESH_ACTIONS)
                ][0],
                "metrics": metrics,
                "grid_order": getattr(snapshot, "grid_order", None),
                "error": None,
            }
            return snapshot
        except Exception as exc:
            error = self._sanitize_error(exc)
            self._v100_live_errors.append(error)
            self._v100_live_errors = self._v100_live_errors[-8:]
            self.last_v100_diagnostics = {
                "ok": False,
                "duration_ms": int((time.monotonic() - started) * 1000),
                "http": status,
                "bytes": len(raw),
                "sha12": sha,
                "changed": changed,
                "reads": self._v100_live_reads,
                "changes": self._v100_live_changes,
                "decode_ok": self._v100_live_decode_ok,
                "refresh_attempts": self._v100_refresh_attempts,
                "refresh_ok": self._v100_refresh_ok,
                "error": error,
                "errors": list(self._v100_live_errors),
            }
            raise
