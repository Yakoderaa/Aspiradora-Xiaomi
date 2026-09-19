from collections import Counter

from xiaomi_e10_map_v60 import XiaomiE10MapV60


class XiaomiE10MapV91(XiaomiE10MapV60):
    """V91: cabecera B112 real observada + capas 2bpp validadas espacialmente.

    El payload post-hex observado en xiaomi.vacuum.b112 mide 3628 bytes:
      1 byte tipo variable (09/0b/0d observado)
      1 byte versión (=1)
      2 bytes BE de longitud de cabecera (=24)
      24 bytes de metadatos
      3600 bytes de grid 120x120 a 2bpp

    V56 asumía [tipo=06][longitud en 3 bytes], por eso descartaba el payload
    antes de que V57 pudiera validar su geometría.
    """

    GRID_RESOLUTION_M = 0.20
    V91_HEADER_VERSION = 1
    V91_HEADER_LEN = 24

    def __init__(self, *args, **kwargs):
        self.last_v91_diagnostics = {
            "header_candidates": 0,
            "header_accepted": 0,
            "last_header": None,
            "grid_candidates": [],
            "selected_grid": None,
        }
        super().__init__(*args, **kwargs)

    @classmethod
    def _parse_header(cls, payload: bytes):
        # Conserva compatibilidad por si aparece el formato histórico supuesto.
        legacy = super()._parse_header(payload)
        if legacy is not None:
            return legacy

        raw = bytes(payload or b"")
        if len(raw) < 4:
            return None

        # Formato observado: type8 + version8 + header_len16be.
        version = int(raw[1])
        length = int.from_bytes(raw[2:4], "big")
        offset = 4 + length
        if (
            version != cls.V91_HEADER_VERSION
            or length != cls.V91_HEADER_LEN
            or offset + cls.GRID_BYTES > len(raw)
        ):
            return None

        body = raw[4:offset]
        fields = cls._parse_len_strings(body)
        timestamp = None
        for value in fields:
            if isinstance(value, str) and value.isdigit() and len(value) == 10:
                number = int(value)
                if 1_500_000_000 <= number <= 2_200_000_000:
                    timestamp = number
                    break

        return {
            "type": int(raw[0]),
            "version": version,
            "length": length,
            "fields": fields,
            "timestamp": timestamp,
            "grid_offset": offset,
            "format": "type8-version8-len16be",
        }

    def _decode_b112_payload(self, raw: bytes):
        decoded = super()._decode_b112_payload(raw)
        if decoded is None:
            return None

        payload = bytes(decoded.get("payload") or b"")
        self.last_v91_diagnostics["header_candidates"] += 1
        header = self._parse_header(payload)
        if header is None:
            self.last_v91_diagnostics["last_header"] = {
                "payload_bytes": len(payload),
                "accepted": False,
                "prefix": payload[:4].hex(),
            }
            return decoded

        exact_size = (
            int(header["grid_offset"]) + int(self.GRID_BYTES)
            == len(payload)
        )
        decoded["exact_b112_grid"] = bool(exact_size)
        decoded["v91_header"] = dict(header)
        self.last_v91_diagnostics["last_header"] = {
            "payload_bytes": len(payload),
            "accepted": bool(exact_size),
            "type": header.get("type"),
            "version": header.get("version"),
            "length": header.get("length"),
            "grid_offset": header.get("grid_offset"),
            "timestamp": header.get("timestamp"),
            "format": header.get("format", "legacy"),
        }
        if exact_size:
            self.last_v91_diagnostics["header_accepted"] += 1
        return decoded

    @classmethod
    def _decode_grid(cls, grid_raw: bytes):
        """Prueba bit-order y capas de valor; V57 sigue siendo el gate final."""
        options = []
        masks = (
            ("nonzero", {1, 2, 3}),
            ("v1", {1}),
            ("v2", {2}),
            ("v3", {3}),
            ("v12", {1, 2}),
            ("v13", {1, 3}),
            ("v23", {2, 3}),
        )
        for order, msb in (("msb-first", True), ("lsb-first", False)):
            raw_cells = cls._unpack_2bpp(grid_raw, msb)
            raw_counts = dict(Counter(raw_cells))
            for mask_name, allowed in masks:
                cells = [1 if int(value) in allowed else 0 for value in raw_cells]
                metrics = cls._grid_metrics(cells)
                # El validador V57 decide validez. Este score sólo elige qué
                # interpretación entregar primero.
                score = (
                    (10_000_000 if metrics.get("valid") else 0)
                    + int(metrics.get("largest", 0) or 0) * 100
                    + int(metrics.get("nonzero", 0) or 0) * 3
                    + int(float(metrics.get("adjacency_ratio", 0.0) or 0.0) * 100)
                )
                options.append({
                    "label": f"{order}|{mask_name}",
                    "cells": cells,
                    "score": score,
                    "counts": dict(Counter(cells)),
                    "raw_counts": raw_counts,
                    "metrics": dict(metrics),
                    "mask": mask_name,
                })

        options.sort(
            key=lambda item: (
                bool((item.get("metrics") or {}).get("valid")),
                int(item.get("score", 0) or 0),
            ),
            reverse=True,
        )
        return options[0], options

    def _snapshot_from_grid(self, slot, endpoint, raw, decoded):
        snapshot = super()._snapshot_from_grid(slot, endpoint, raw, decoded)
        selected_metrics = self._grid_metrics(
            getattr(snapshot, "grid_cells", []) or []
        )
        snapshot.grid_resolution = self.GRID_RESOLUTION_M
        snapshot.resolution = self.GRID_RESOLUTION_M
        snapshot.v91_header = dict(decoded.get("v91_header") or {})
        snapshot.v91_grid_metrics = dict(selected_metrics)

        alternatives = list(getattr(snapshot, "grid_alternatives", []) or [])
        self.last_v91_diagnostics["grid_candidates"] = alternatives[:14]
        self.last_v91_diagnostics["selected_grid"] = {
            "order": getattr(snapshot, "grid_order", None),
            "counts": dict(getattr(snapshot, "grid_counts", {}) or {}),
            "metrics": dict(selected_metrics),
            "resolution": self.GRID_RESOLUTION_M,
        }
        return snapshot
