import time
from typing import Any

from xiaomi_e10_map_v60 import XiaomiE10MapV60


class XiaomiE10MapV69(XiaomiE10MapV60):
    """V69: diagnostica clean-end real y no confunde placeholders con FDS."""

    PLACEHOLDER_REFS = {
        "",
        "0",
        "cloud",
        "hello",
        "retry",
        "none",
        "null",
    }

    def __init__(self, *args, **kwargs):
        self.last_v69_clean_end_diagnostics: dict[str, Any] = {}
        super().__init__(*args, **kwargs)

    @classmethod
    def _v69_ref_kind(cls, value: Any) -> str:
        if value is None:
            return "none"
        text = str(value).strip()
        if not text:
            return "none"
        if text.lower() in cls.PLACEHOLDER_REFS:
            return "placeholder"
        if cls._looks_http(text):
            return "http"
        if "/" in text or "\\" in text:
            return "path"
        return "object"

    @classmethod
    def _v69_ref_usable(cls, value: Any) -> bool:
        return cls._v69_ref_kind(value) in {"http", "path", "object"}

    def _clean_end_quick(self):
        """Consulta 7.1 sin contar 'cloud' u otros placeholders como referencias.

        Además de PIID 30, inspecciona nombres de objeto/URL presentes en el
        mismo registro, porque algunos backends envuelven la referencia real.
        """
        started = time.monotonic()
        method = "Cloud clean-end 7.1 V69"

        end = int(time.time()) + 30
        start = max(
            0,
            end - 24 * 3600,
            int(float(getattr(self, "_v57_session_started_at", 0.0) or 0.0)) - 120,
        )
        variants = (
            ("/v2/user/get_user_device_data", "event", False),
            ("/user/get_user_device_data", "event", False),
            ("/v2/user/get_device_data_raw", "store", False),
        )

        diagnostics = []
        usable_refs = []
        shape_counts = {
            "none": 0,
            "placeholder": 0,
            "http": 0,
            "path": 0,
            "object": 0,
        }
        records_seen = 0
        piid30_seen = 0
        nested_refs_seen = 0

        for endpoint, typ, include_uid in variants:
            try:
                records, detail = self._history_request_variant(
                    endpoint, self.CLEAN_END_KEY, typ, start, end, include_uid
                )
                diagnostics.append({"ok": True, **detail})
                records_seen += len(records)

                for record in records:
                    meta = self._event_meta(record)
                    record_time = self._record_time(record) or 0.0
                    direct = meta.get("record_map_url")

                    if direct is not None:
                        piid30_seen += 1
                        kind = self._v69_ref_kind(direct)
                        shape_counts[kind] = shape_counts.get(kind, 0) + 1
                        if self._v69_ref_usable(direct):
                            usable_refs.append((
                                record_time,
                                f"{endpoint.rsplit('/', 1)[-1]}:piid30",
                                str(direct).strip(),
                                0,
                            ))

                    # El registro Cloud puede envolver el objeto real fuera de
                    # out/piid30. Sólo miramos claves explícitas de archivo/URL.
                    for source, value in self._object_refs_from_response(record):
                        if direct is not None and str(value).strip() == str(direct).strip():
                            continue
                        kind = self._v69_ref_kind(value)
                        shape_counts[kind] = shape_counts.get(kind, 0) + 1
                        if not self._v69_ref_usable(value):
                            continue
                        nested_refs_seen += 1
                        usable_refs.append((
                            record_time,
                            f"{endpoint.rsplit('/', 1)[-1]}:{source}",
                            str(value).strip(),
                            1,
                        ))

                # Seguimos probando variantes si sólo vimos placeholders.
                if usable_refs:
                    break
            except Exception as exc:
                diagnostics.append({
                    "ok": False,
                    "endpoint": endpoint.rsplit("/", 1)[-1],
                    "type": typ,
                    "uid": bool(include_uid),
                    "error": self._sanitize_error(exc),
                })

        usable_refs.sort(key=lambda x: (-float(x[0]), int(x[3]), len(x[2])))
        refs = [
            (f"clean-end:{source}", ref, priority)
            for _when, source, ref, priority in usable_refs[:5]
        ]

        self.last_v69_clean_end_diagnostics = {
            "records_seen": int(records_seen),
            "piid30_seen": int(piid30_seen),
            "nested_refs_seen": int(nested_refs_seen),
            "usable_refs": len(refs),
            "ref_shapes": dict(shape_counts),
            "queries": diagnostics,
        }

        self._record_v60(
            method,
            started,
            ok=True,
            records=records_seen,
            piid30=piid30_seen,
            refs=len(refs),
            placeholder_refs=int(shape_counts.get("placeholder", 0) or 0),
            ref_shapes=dict(shape_counts),
            queries=diagnostics,
        )
        return refs
