import hashlib
import math
import time
from collections import Counter, defaultdict
from typing import Any

import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

from xiaomi_e10_ijai_map import IjaiMapSnapshot
from xiaomi_e10_map_v54 import XiaomiE10MapV54


class XiaomiE10MapV56(XiaomiE10MapV54):
    """V56: refresco oficial B112 + decoder de rejilla realtime 120x120/2bpp.

    El payload V54 validado tiene 3628 bytes:
      - 4 bytes record header (tipo 0x06 + longitud 24)
      - 24 bytes de metadatos
      - 3600 bytes restantes

    3600 bytes = 14400 celdas * 2 bits = una rejilla 120x120. Eso además
    coincide con las coordenadas del firmware alrededor de 60_60.

    V56:
      1) solicita mapa realtime con las acciones oficiales 10/18, 10/15(0),
         10/6(0), parando cuando el hash Cloud cambia;
      2) descifra con la derivación MD5 completa que V53/V54 ya validaron;
      3) convierte la rejilla a contornos persistibles en LocalMap;
      4) si 10/24 sigue congelado, usa únicamente CAMBIOS TEMPORALES entre dos
         rejillas consecutivas para obtener un fallback de trayectoria.
    """

    GRID_SIDE = 120
    GRID_BYTES = 3600
    GRID_RESOLUTION_M = 0.10
    HEADER_TYPE = 0x06
    HEADER_LEN = 24
    REFRESH_SETTLE_SECONDS = 0.75
    MAX_GRID_TRACK_POINTS = 4000

    def __init__(self, *args, **kwargs):
        self.last_v56_diagnostics: dict[str, Any] = {}
        self.last_v56_upload_diagnostics: dict[str, Any] = {}
        self._v56_prev_cells: list[int] | None = None
        self._v56_prev_hash: str | None = None
        self._v56_grid_track: list[tuple[float, float]] = []
        self._v56_last_grid_pose: tuple[float, float] | None = None
        super().__init__(*args, **kwargs)

    # ------------------------------------------------------------ Cloud blob
    def _download_slot(self, slot: str = "0"):
        url, endpoint = self._map_download_url(str(slot))
        response = requests.get(url, timeout=25)
        raw = bytes(response.content or b"")
        status = int(response.status_code)
        response.raise_for_status()
        return raw, endpoint, status

    @staticmethod
    def _sha12(raw: bytes):
        return hashlib.sha256(bytes(raw or b"")).hexdigest()[:12] if raw else ""

    # --------------------------------------------------------- action helpers
    @staticmethod
    def _action_metadata(response: Any) -> dict[str, Any]:
        result = {
            "response_type": type(response).__name__,
            "code": None,
            "map_id": None,
            "map_type": None,
            "timestamp": None,
            "renew_map": None,
        }
        if not isinstance(response, dict):
            return result
        result["code"] = response.get("code")
        for item in response.get("out") or []:
            if not isinstance(item, dict):
                continue
            try:
                piid = int(item.get("piid"))
            except Exception:
                continue
            value = item.get("value")
            if piid == 6:
                result["map_id"] = value
            elif piid == 7:
                result["map_type"] = value
            elif piid == 18:
                result["timestamp"] = value
            elif piid == 21:
                result["renew_map"] = value
        return result

    def _call_realtime_upload(self, aiid: int, params: list[int], label: str):
        item = {
            "action": f"10/{aiid}",
            "label": label,
            "ok": False,
            "hash_before": None,
            "hash_after": None,
            "changed": False,
        }
        try:
            response = self.vacuum.device.call_action_by(10, aiid, list(params))
            item.update(self._action_metadata(response))
            code = item.get("code")
            if isinstance(code, int) and code != 0:
                raise RuntimeError(f"code={code}")
            item["ok"] = True
        except Exception as exc:
            item["error"] = self._safe_http_error(exc)
        return item

    def request_fresh_upload(self):
        """Pide realtime usando exclusivamente acciones documentadas del B112."""
        privacy_before = None
        privacy_enabled_temporarily = False
        try:
            privacy_before = self.map_privacy_state()
            if privacy_before == 1:
                privacy_enabled_temporarily = bool(self.enable_map_upload_temporarily())
        except Exception:
            pass

        baseline_raw = b""
        baseline_hash = None
        baseline_error = None
        try:
            baseline_raw, _endpoint, _status = self._download_slot("0")
            baseline_hash = self._sha12(baseline_raw)
        except Exception as exc:
            baseline_error = self._safe_http_error(exc)

        attempts = []
        current_hash = baseline_hash
        winner = None
        sequence = (
            (18, [], "upmapdata"),
            (15, [0], "upload-by-maptype-ii · Realtime"),
            (6, [0], "upload-by-maptype · Realtime"),
        )

        for aiid, params, label in sequence:
            item = self._call_realtime_upload(aiid, params, label)
            item["hash_before"] = current_hash
            attempts.append(item)
            if not item.get("ok"):
                continue

            time.sleep(self.REFRESH_SETTLE_SECONDS)
            try:
                raw, endpoint, status = self._download_slot("0")
                after_hash = self._sha12(raw)
                item["hash_after"] = after_hash
                item["http"] = status
                item["endpoint"] = endpoint
                item["bytes"] = len(raw)
                item["changed"] = bool(current_hash and after_hash and after_hash != current_hash)
                current_hash = after_hash
                if item["changed"]:
                    winner = item["action"]
                    break
            except Exception as exc:
                item["download_error"] = self._safe_http_error(exc)

        self.last_v56_upload_diagnostics = {
            "official_actions": True,
            "privacy_before": privacy_before,
            "privacy_temp": privacy_enabled_temporarily,
            "baseline_hash": baseline_hash,
            "baseline_error": baseline_error,
            "attempts": attempts,
            "winner": winner,
            "hash_after": current_hash,
            "changed": bool(winner),
            "ok": any(bool(x.get("ok")) for x in attempts),
            "map_id": next((x.get("map_id") for x in reversed(attempts) if x.get("map_id") is not None), 0),
        }
        # Mantiene compatible el diagnóstico heredado de app_v40/app_v45.
        self.last_upload_diagnostics = dict(self.last_v56_upload_diagnostics)
        return dict(self.last_v56_upload_diagnostics)

    # ------------------------------------------------------ AES -> post-hex
    def _decode_b112_payload(self, raw: bytes):
        wifi, owners, dids, macs = self._ordered_key_material()
        candidates = []

        for wifi_sn, wifi_source in wifi:
            for owner, owner_source in owners:
                for did, did_source in dids:
                    for mac, mac_source in macs:
                        for key, mode in self._known_final_keys(
                            str(wifi_sn), str(owner), str(did), str(mac)
                        ):
                            if mode != "md5-full-hex-bytes":
                                continue
                            for cipher, cipher_label in self._cipher_variants(raw):
                                try:
                                    plain = unpad(
                                        AES.new(key, AES.MODE_ECB).decrypt(cipher),
                                        AES.block_size,
                                        "pkcs7",
                                    )
                                    text = plain.strip().decode("ascii")
                                    if not text or len(text) % 2:
                                        continue
                                    payload = bytes.fromhex(text)
                                except Exception:
                                    continue

                                header_len = (
                                    int.from_bytes(payload[1:4], "big")
                                    if len(payload) >= 4
                                    else -1
                                )
                                exact = bool(
                                    len(payload) >= 4 + self.HEADER_LEN + self.GRID_BYTES
                                    and payload[0] == self.HEADER_TYPE
                                    and header_len == self.HEADER_LEN
                                )
                                candidates.append({
                                    "payload": payload,
                                    "exact_b112_grid": exact,
                                    "mode": mode,
                                    "cipher_variant": cipher_label,
                                    "sources": {
                                        "wifi_source": str(wifi_source),
                                        "owner_source": str(owner_source),
                                        "did_source": str(did_source),
                                        "mac_source": str(mac_source),
                                    },
                                })

        if not candidates:
            return None
        candidates.sort(
            key=lambda item: (
                bool(item["exact_b112_grid"]),
                len(item["payload"]),
            ),
            reverse=True,
        )
        return candidates[0]

    # ---------------------------------------------------------- header/grid
    @staticmethod
    def _parse_len_strings(data: bytes):
        values = []
        pos = 0
        raw = bytes(data or b"")
        while pos + 2 <= len(raw) and len(values) < 8:
            length = int.from_bytes(raw[pos:pos + 2], "big")
            pos += 2
            if length <= 0 or pos + length > len(raw):
                break
            chunk = raw[pos:pos + length]
            pos += length
            try:
                text = chunk.decode("ascii")
            except Exception:
                text = chunk.hex()
            values.append(text)
        return values

    @classmethod
    def _parse_header(cls, payload: bytes):
        if len(payload) < 4:
            return None
        record_type = payload[0]
        length = int.from_bytes(payload[1:4], "big")
        if length < 0 or 4 + length > len(payload):
            return None
        body = bytes(payload[4:4 + length])
        fields = cls._parse_len_strings(body)
        timestamp = None
        for value in fields:
            if isinstance(value, str) and value.isdigit() and len(value) == 10:
                try:
                    number = int(value)
                except Exception:
                    continue
                if 1_500_000_000 <= number <= 2_200_000_000:
                    timestamp = number
                    break
        return {
            "type": record_type,
            "length": length,
            "fields": fields,
            "timestamp": timestamp,
            "grid_offset": 4 + length,
        }

    @staticmethod
    def _unpack_2bpp(raw: bytes, msb_first: bool):
        cells = []
        for byte in bytes(raw or b""):
            shifts = (6, 4, 2, 0) if msb_first else (0, 2, 4, 6)
            for shift in shifts:
                cells.append((byte >> shift) & 0x03)
        return cells

    @classmethod
    def _grid_score(cls, cells):
        side = cls.GRID_SIDE
        if len(cells) != side * side:
            return -1
        nonzero = 0
        adjacency = 0
        isolated = 0
        for y in range(side):
            row = y * side
            for x in range(side):
                idx = row + x
                if cells[idx] == 0:
                    continue
                nonzero += 1
                local = 0
                if x + 1 < side and cells[idx + 1] != 0:
                    adjacency += 1
                    local += 1
                if y + 1 < side and cells[idx + side] != 0:
                    adjacency += 1
                    local += 1
                if x > 0 and cells[idx - 1] != 0:
                    local += 1
                if y > 0 and cells[idx - side] != 0:
                    local += 1
                if local == 0:
                    isolated += 1
        return adjacency * 4 + nonzero - isolated * 3

    @classmethod
    def _decode_grid(cls, grid_raw: bytes):
        options = []
        for label, msb in (("msb-first", True), ("lsb-first", False)):
            cells = cls._unpack_2bpp(grid_raw, msb)
            counts = Counter(cells)
            options.append({
                "label": label,
                "cells": cells,
                "score": cls._grid_score(cells),
                "counts": dict(counts),
            })
        options.sort(key=lambda item: item["score"], reverse=True)
        return options[0], options

    # ---------------------------------------------------------- grid geometry
    @staticmethod
    def _simplify_collinear(points):
        if len(points) <= 2:
            return points
        out = [points[0]]
        for i in range(1, len(points) - 1):
            a = out[-1]
            b = points[i]
            c = points[i + 1]
            ab = (b[0] - a[0], b[1] - a[1])
            bc = (c[0] - b[0], c[1] - b[1])
            if abs(ab[0] * bc[1] - ab[1] * bc[0]) < 1e-9:
                continue
            out.append(b)
        out.append(points[-1])
        return out

    @classmethod
    def _boundary_segments(cls, cells):
        side = cls.GRID_SIDE
        occupied = lambda x, y: (
            0 <= x < side and 0 <= y < side and cells[y * side + x] != 0
        )
        segments = set()
        for y in range(side):
            for x in range(side):
                if not occupied(x, y):
                    continue
                if not occupied(x, y - 1):
                    segments.add(((x, y), (x + 1, y)))
                if not occupied(x + 1, y):
                    segments.add(((x + 1, y), (x + 1, y + 1)))
                if not occupied(x, y + 1):
                    segments.add(((x + 1, y + 1), (x, y + 1)))
                if not occupied(x - 1, y):
                    segments.add(((x, y + 1), (x, y)))
        return segments

    @classmethod
    def _chain_segments(cls, segments):
        remaining = set(segments)
        adjacency = defaultdict(list)
        for a, b in remaining:
            adjacency[a].append(b)
            adjacency[b].append(a)

        chains = []
        while remaining:
            a, b = next(iter(remaining))
            chain = [a, b]
            remaining.remove((a, b))

            # extiende hacia delante
            while True:
                current = chain[-1]
                previous = chain[-2]
                candidates = [
                    n for n in adjacency[current]
                    if n != previous and (
                        (current, n) in remaining or (n, current) in remaining
                    )
                ]
                if not candidates:
                    break
                nxt = candidates[0]
                edge = (current, nxt) if (current, nxt) in remaining else (nxt, current)
                remaining.remove(edge)
                chain.append(nxt)
                if nxt == chain[0]:
                    break

            chains.append(cls._simplify_collinear(chain))
        return chains

    @classmethod
    def _grid_walls(cls, cells, base_cell=(60.0, 60.0)):
        bx, by = base_cell
        res = cls.GRID_RESOLUTION_M
        walls = []
        for chain in cls._chain_segments(cls._boundary_segments(cells)):
            if len(chain) < 2:
                continue
            points = []
            for x, y in chain:
                points.append({
                    "x": (float(x) - float(bx)) * res,
                    "y": (float(by) - float(y)) * res,
                })
            walls.append({"points": points, "estimated": False})
        return walls

    # ----------------------------------------------------------- device pose
    def _device_pose_grid(self):
        base = None
        robot = None
        try:
            raw = self._property_value(self.vacuum.device, 10, 22)
            base = self.vacuum.parse_position(raw)
        except Exception:
            pass
        try:
            raw = self._property_value(self.vacuum.device, 10, 24)
            robot = self.vacuum.parse_position(raw)
        except Exception:
            pass
        return base, robot

    @classmethod
    def _grid_abs_m(cls, point):
        if not isinstance(point, dict):
            return None
        try:
            return (
                float(point["x"]) * cls.GRID_RESOLUTION_M,
                float(point["y"]) * cls.GRID_RESOLUTION_M,
            )
        except Exception:
            return None

    # ------------------------------------------------------- temporal diff
    def _update_grid_track(self, cells):
        changed = []
        previous = self._v56_prev_cells
        if previous is not None and len(previous) == len(cells):
            for idx, (old, new) in enumerate(zip(previous, cells)):
                if old != new:
                    changed.append(idx)

        self._v56_prev_cells = list(cells)
        if not changed:
            return {
                "changed_cells": 0,
                "accepted": False,
                "centroid": None,
            }

        side = self.GRID_SIDE
        xs = [idx % side for idx in changed]
        ys = [idx // side for idx in changed]
        cx = sum(xs) / len(xs)
        cy = sum(ys) / len(ys)
        pose = (
            cx * self.GRID_RESOLUTION_M,
            cy * self.GRID_RESOLUTION_M,
        )

        # Una reescritura masiva del mapa (por ejemplo primer realtime fresco)
        # no representa la posición del robot.
        accepted = len(changed) <= 1000
        if accepted and self._v56_last_grid_pose is not None:
            jump = math.hypot(
                pose[0] - self._v56_last_grid_pose[0],
                pose[1] - self._v56_last_grid_pose[1],
            )
            # Un mapa completo reescrito no es una pose. Aceptamos sólo una
            # evolución local razonable entre refrescos.
            if jump > 3.0:
                accepted = False

        if accepted:
            if self._v56_last_grid_pose is None or math.hypot(
                pose[0] - self._v56_last_grid_pose[0],
                pose[1] - self._v56_last_grid_pose[1],
            ) >= 0.03:
                self._v56_grid_track.append(pose)
                self._v56_grid_track = self._v56_grid_track[-self.MAX_GRID_TRACK_POINTS:]
                self._v56_last_grid_pose = pose

        return {
            "changed_cells": len(changed),
            "accepted": accepted,
            "centroid": pose if accepted else None,
        }

    # -------------------------------------------------------------- snapshot
    def _snapshot_from_grid(self, slot, endpoint, raw, decoded):
        payload = decoded["payload"]
        header = self._parse_header(payload)
        if not header:
            raise RuntimeError("cabecera B112 inválida")
        offset = int(header["grid_offset"])
        grid_raw = payload[offset:offset + self.GRID_BYTES]
        if len(grid_raw) != self.GRID_BYTES:
            raise RuntimeError(
                f"rejilla B112 incompleta: {len(grid_raw)} / {self.GRID_BYTES} bytes"
            )

        selected, alternatives = self._decode_grid(grid_raw)
        cells = selected["cells"]
        base_grid, robot_grid = self._device_pose_grid()
        base_cell = (
            (float(base_grid["x"]), float(base_grid["y"]))
            if isinstance(base_grid, dict)
            else (60.0, 60.0)
        )
        walls = self._grid_walls(cells, base_cell=base_cell)

        grid_diff = self._update_grid_track(cells)
        raw_base = self._grid_abs_m(base_grid)
        raw_robot = self._grid_abs_m(robot_grid)
        raw_path = list(self._v56_grid_track)

        # Si el mapa cambió temporalmente y ya tenemos al menos 2 centros de
        # cambio, esa evolución prima sobre el 10/24 congelado.
        if len(raw_path) >= 2:
            raw_robot = raw_path[-1]
            if raw_base is None:
                raw_base = (
                    float(base_cell[0]) * self.GRID_RESOLUTION_M,
                    float(base_cell[1]) * self.GRID_RESOLUTION_M,
                )

        snapshot = IjaiMapSnapshot(
            map_name=str(slot),
            crypto_mode="b112-md5-full-hex+grid2bpp",
            raw_size=len(raw),
            envelope_version="b112-record-6-grid",
            map_id=None,
            resolution=self.GRID_RESOLUTION_M,
            raw_robot=raw_robot,
            raw_base=raw_base,
            raw_path=raw_path,
            parser_error=None,
            slot=str(slot),
            endpoint=endpoint,
            decrypted_size=len(payload),
            raw_prefix_hex=bytes(raw[:16]).hex(),
            wifi_sn_source=str(decoded["sources"].get("wifi_source") or ""),
            wifi_sn_length=0,
            mac_available=True,
            pose_id=None,
            upload_date=header.get("timestamp"),
        )
        snapshot.grid_cells = list(cells)
        snapshot.grid_blob_sha12 = self._sha12(raw)
        snapshot.grid_side = self.GRID_SIDE
        snapshot.grid_resolution = self.GRID_RESOLUTION_M
        snapshot.grid_base_cell = tuple(base_cell)
        snapshot.grid_walls = walls
        snapshot.grid_counts = dict(selected["counts"])
        snapshot.grid_order = selected["label"]
        snapshot.grid_score = selected["score"]
        snapshot.grid_alternatives = [
            {
                "label": item["label"],
                "score": item["score"],
                "counts": dict(item["counts"]),
            }
            for item in alternatives
        ]
        snapshot.grid_diff = dict(grid_diff)
        snapshot.b112_header = {
            "type": header["type"],
            "length": header["length"],
            "field_lengths": [len(str(x)) for x in header["fields"]],
            "timestamp": header.get("timestamp"),
        }
        snapshot.v56_sources = dict(decoded["sources"])
        return snapshot

    def load(self):
        diagnostics = {
            "route": "acciones oficiales -> slot clásico -> AES full-MD5 -> rejilla 120x120 2bpp",
            "slots": {},
            "success": False,
            "fallback_v54": False,
        }
        valid = []

        for slot in ("0", "1"):
            slot_diag = {}
            diagnostics["slots"][slot] = slot_diag
            try:
                raw, endpoint, status = self._download_slot(slot)
                slot_diag.update({
                    "http": status,
                    "endpoint": endpoint,
                    "bytes": len(raw),
                    "sha12": self._sha12(raw),
                })
                decoded = self._decode_b112_payload(raw)
                if decoded is None:
                    slot_diag["decode"] = "sin candidato AES+hex"
                    continue
                slot_diag["decode"] = "AES+hex"
                slot_diag["exact_grid"] = bool(decoded.get("exact_b112_grid"))
                snapshot = self._snapshot_from_grid(slot, endpoint, raw, decoded)
                slot_diag.update({
                    "grid_order": snapshot.grid_order,
                    "grid_counts": snapshot.grid_counts,
                    "walls": len(snapshot.grid_walls),
                    "header_timestamp": snapshot.upload_date,
                    "changed_cells": snapshot.grid_diff.get("changed_cells"),
                    "grid_track": len(snapshot.raw_path or []),
                })
                valid.append(snapshot)
            except Exception as exc:
                slot_diag["error"] = self._safe_http_error(exc)

        if valid:
            def freshness(item):
                return (
                    int(item.upload_date or 0),
                    len(item.raw_path or []),
                    int(item.raw_size or 0),
                )
            selected = max(valid, key=freshness)
            selected.valid_slots = [item.slot for item in valid]
            selected.slot_errors = {
                slot: str(info.get("error"))
                for slot, info in diagnostics["slots"].items()
                if info.get("error")
            }
            diagnostics.update({
                "success": True,
                "winner_slot": selected.slot,
                "grid_counts": getattr(selected, "grid_counts", {}),
                "grid_order": getattr(selected, "grid_order", None),
                "walls": len(getattr(selected, "grid_walls", []) or []),
                "grid_track": len(selected.raw_path or []),
                "header_timestamp": selected.upload_date,
                "winner_sources": getattr(selected, "v56_sources", {}),
            })
            self.last_v56_diagnostics = diagnostics
            return selected

        diagnostics["fallback_v54"] = True
        self.last_v56_diagnostics = diagnostics
        return super().load()
