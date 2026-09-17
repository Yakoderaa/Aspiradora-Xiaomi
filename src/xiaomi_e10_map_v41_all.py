"""Última capa de fallbacks para el mapa E10.

Extiende la búsqueda IJAI de v41 con formatos Xiaomi JSON/CBC y JSON plano. Si
encuentra telemetría JSON coherente la convierte a un RobotMap sintético para
reutilizar exactamente el mismo pipeline de movimiento, sin aceptar basura como
mapa válido.
"""
import base64
import hashlib
import json
import re

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from vacuum_map_parser_ijai import RobotMap_pb2 as RobotMap

from xiaomi_e10 import MODEL
from xiaomi_e10_map_v41 import XiaomiE10MapV41


class XiaomiE10MapV41All(XiaomiE10MapV41):
    XIAOMI_IV = b"ABCDEF1234123412"

    @staticmethod
    def _json_point(value):
        if value is None:
            return None
        if isinstance(value, dict):
            try:
                return float(value["x"]), float(value["y"])
            except Exception:
                for key in ("position", "point", "pos"):
                    if key in value:
                        found = XiaomiE10MapV41All._json_point(value[key])
                        if found:
                            return found
                return None
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            try:
                return float(value[0]), float(value[1])
            except Exception:
                return None
        if isinstance(value, str):
            nums = re.findall(r"-?\d+(?:\.\d+)?", value)
            if len(nums) >= 2:
                return float(nums[0]), float(nums[1])
        return None

    @classmethod
    def _json_to_robot_map(cls, obj):
        if not isinstance(obj, dict):
            return None
        robot = None
        base = None
        path = []
        for key in ("position", "vacuum_position", "robot_position", "robot", "currentPose", "current_pose"):
            robot = cls._json_point(obj.get(key))
            if robot:
                break
        for key in ("charger", "charging_base", "chargeStation", "base", "pile"):
            base = cls._json_point(obj.get(key))
            if base:
                break
        if base is None and ("pile_x" in obj or "pile_y" in obj):
            try:
                base = (float(obj.get("pile_x", 0)), float(obj.get("pile_y", 0)))
            except Exception:
                base = None

        raw_paths = obj.get("paths") or obj.get("path") or obj.get("trajectory") or obj.get("historyPose")

        def collect(value):
            point = cls._json_point(value)
            if point:
                path.append(point)
                return
            if isinstance(value, dict):
                for key in ("points", "path", "paths", "trajectory"):
                    if key in value:
                        collect(value[key])
            elif isinstance(value, (list, tuple)):
                for item in value:
                    collect(item)

        collect(raw_paths)
        if robot is None and path:
            robot = path[-1]
        if base is None and path:
            base = path[0]
        if robot is None and not path:
            return None

        rm = RobotMap.RobotMap()
        rm.mapHead.mapHeadId = int(obj.get("map_id") or obj.get("mapId") or 1)
        try:
            rm.mapHead.resolution = float(obj.get("resolution") or 0.05)
        except Exception:
            rm.mapHead.resolution = 0.05
        rm.mapHead.sizeX = 1
        rm.mapHead.sizeY = 1
        rm.mapData.mapData = b"\x00"
        if robot:
            rm.currentPose.x, rm.currentPose.y = robot
            try:
                rm.currentPose.poseId = int(obj.get("pose_id") or obj.get("poseId") or len(path) or 1)
            except Exception:
                rm.currentPose.poseId = len(path) or 1
        if base:
            rm.chargeStation.x, rm.chargeStation.y = base
        for x, y in path:
            p = rm.historyPose.points.add()
            p.x, p.y = x, y
        return rm

    @classmethod
    def _validate_json_payload(cls, data):
        variants = cls._post_decrypt_variants(data)
        for payload, label in variants:
            try:
                obj = json.loads(payload.decode("utf-8-sig"))
            except Exception:
                continue
            # Algunos envelopes anidan el mapa en data/map/payload.
            stack = [(obj, label)]
            while stack:
                candidate, candidate_label = stack.pop()
                rm = cls._json_to_robot_map(candidate)
                if rm is not None:
                    serialized = rm.SerializeToString()
                    quality = cls._protobuf_quality(serialized)
                    if quality:
                        return quality[0], serialized, rm, "JSON validado | " + candidate_label, "json-sin-clave"
                if isinstance(candidate, dict):
                    for key in ("data", "map", "payload", "result"):
                        child = candidate.get(key)
                        if isinstance(child, dict):
                            stack.append((child, candidate_label + "." + key))
                        elif isinstance(child, str) and child.lstrip().startswith(("{", "[")):
                            try:
                                stack.append((json.loads(child), candidate_label + "." + key))
                            except Exception:
                                pass
        return None

    def _xiaomi_cbc_keys(self):
        did_candidates = [self.did]
        try:
            cloud_dev = self._cloud_device()
            if isinstance(cloud_dev, dict) and cloud_dev.get("did"):
                did_candidates.append(str(cloud_dev["did"]))
        except Exception:
            pass
        did_candidates = list(dict.fromkeys(x for x in did_candidates if x))

        model_keys = []
        suffix16 = MODEL[-16:]
        if len(suffix16.encode("latin1")) == 16:
            model_keys.append((suffix16.encode("latin1"), "model[-16:]"))
        # Variantes de case: ciertos firmwares normalizan el nombre del modelo.
        for text, label in ((suffix16.lower(), "model[-16:].lower"), (suffix16.upper(), "model[-16:].upper")):
            try:
                raw = text.encode("latin1")
                if len(raw) == 16:
                    model_keys.append((raw, label))
            except Exception:
                pass

        results = []
        seen = set()
        for model_key, model_label in model_keys:
            for did in did_candidates:
                for original in (
                    model_key + str(did).encode("latin1", errors="ignore"),
                    str(did).encode("latin1", errors="ignore") + model_key,
                ):
                    try:
                        material = AES.new(model_key, AES.MODE_CBC, self.XIAOMI_IV).encrypt(
                            pad(original, AES.block_size)
                        )
                    except Exception:
                        continue
                    for source, source_label in (
                        (material, "md5(cipher)"),
                        (base64.b64encode(material), "md5(base64)"),
                    ):
                        key = hashlib.md5(source).digest()
                        if key not in seen:
                            seen.add(key)
                            results.append((key, f"{model_label}/{source_label}/did-len-{len(str(did))}"))
        return results

    def _decode_exhaustive(self, raw, key_candidates):
        # IJAI / protobuf primero: es la familia más probable.
        try:
            return super()._decode_exhaustive(raw, key_candidates)
        except Exception as ijai_error:
            ijai_attempts = int(getattr(self, "decode_attempts", 0) or 0)

        # JSON plano/comprimido/base64 sin AES.
        for blob, blob_label in self._blob_variants(raw):
            self.decode_attempts += 1
            found = self._validate_json_payload(blob)
            if found:
                score, payload, rm, mode, label = found
                return score, payload, rm, f"{mode} | {blob_label}", label

        # Xiaomi Home AES-CBC, tanto ciphertext binario como Base64/hex wrapper.
        for key, key_label in self._xiaomi_cbc_keys():
            for blob, blob_label in self._blob_variants(raw):
                if len(blob) < 16 or len(blob) % 16:
                    continue
                for iv, iv_label in ((self.XIAOMI_IV, "iv-home"), (b"\x00" * 16, "iv-zero")):
                    try:
                        plain_raw = AES.new(key, AES.MODE_CBC, iv).decrypt(blob)
                    except Exception:
                        continue
                    plains = [(plain_raw, "raw")]
                    try:
                        plains.insert(0, (unpad(plain_raw, AES.block_size), "pkcs7"))
                    except Exception:
                        pass
                    for plain, padding_label in plains:
                        self.decode_attempts += 1
                        # Puede resultar directamente protobuf tras descomprimir.
                        for payload, post_label in self._post_decrypt_variants(plain):
                            quality = self._protobuf_quality(payload)
                            if quality:
                                return (
                                    quality[0], payload, quality[1],
                                    f"AES-CBC | {blob_label} | {iv_label} | {padding_label} | {post_label}",
                                    "CBC " + key_label,
                                )
                        found = self._validate_json_payload(plain)
                        if found:
                            score, payload, rm, mode, _ = found
                            return (
                                score, payload, rm,
                                f"AES-CBC JSON | {blob_label} | {iv_label} | {padding_label} | {mode}",
                                "CBC " + key_label,
                            )

        raise RuntimeError(
            f"falló IJAI ({ijai_attempts} intentos) y también JSON/AES-CBC; total {self.decode_attempts} validaciones"
        )
