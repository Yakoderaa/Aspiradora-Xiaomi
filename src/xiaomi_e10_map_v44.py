import hashlib
import json
from typing import Any

from xiaomi_e10_map_v42 import XiaomiE10MapV42
from xiaomi_e10_map_v43 import XiaomiE10MapV43


class XiaomiE10MapV44(XiaomiE10MapV43):
    """v44: corrige la obtención del wifi_sn usado por la clave IJAI.

    Evidencia de hardware de Xiaomi Cloud Map Extractor muestra que varios Xiaomi
    con motor IJAI publican el serial Wi-Fi en 1/5 y 7/45 con formato como
    ``57054/B2AE7F5NE03300``. La barra '/' era rechazada por V41 antes de que V42
    llegara al parser oficial, por lo que se probaba una clave derivada de otro
    valor del servicio 1 y el resultado era siempre Padding is incorrect.

    Esta versión prioriza IJAI para B112, conserva Xiaomi JSON como fallback y
    nunca imprime serial/UID/DID/MAC: sólo fuente, longitud, forma y hash corto.
    """

    def __init__(self, *args, **kwargs):
        self.last_v44_diagnostics: dict[str, Any] = {}
        super().__init__(*args, **kwargs)

    @staticmethod
    def _strict_wifi_serial(value: Any) -> bool:
        if not isinstance(value, str):
            return False
        text = value.strip().strip('"')
        if not (10 <= len(text) <= 25):
            return False
        cleaned = text.replace("/", "")
        if not cleaned.isalnum():
            return False
        return any(ch.isalpha() for ch in cleaned) and text.upper() == text

    @staticmethod
    def _serial_variants(value: Any):
        if not isinstance(value, str):
            return []
        text = value.strip().strip('"')
        if not text:
            return []
        result = [text]
        upper = text.upper()
        if upper not in result:
            result.append(upper)
        if "/" in text:
            no_slash = text.replace("/", "")
            if no_slash and no_slash not in result:
                result.append(no_slash)
        return result

    @staticmethod
    def _multi_prop_items(raw: Any):
        if raw is None:
            return []
        if isinstance(raw, (list, tuple)):
            return [str(item).strip().strip('"') for item in raw]
        text = str(raw).strip()
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(item).strip().strip('"') for item in parsed]
        except Exception:
            pass
        return [part.replace('"', "").strip() for part in text.strip("[]").split(",")]

    @classmethod
    def _serial_from_direct(cls, value: Any):
        if not isinstance(value, str):
            return []
        text = value.strip().strip('"')
        return cls._serial_variants(text) if cls._strict_wifi_serial(text) else []

    @classmethod
    def _serial_and_owner_from_multi(cls, raw: Any):
        serials = []
        owners = []
        for part in cls._multi_prop_items(raw):
            serial, sep, suffix = str(part).partition(";")
            serial = serial.strip()
            suffix = suffix.strip()
            if cls._strict_wifi_serial(serial):
                serials.extend(cls._serial_variants(serial))
                if sep and suffix:
                    owners.append(suffix)
        return serials, owners

    @staticmethod
    def _shape(value: str, source: str):
        text = str(value)
        return {
            "source": str(source),
            "length": len(text),
            "slash": "/" in text,
            "sha8": hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:8],
        }

    def _key_candidates(self):
        wifi, owners, dids, macs = super()._key_candidates()
        device = self.vacuum.device
        extra_wifi = []
        extra_owners = []

        # Orden documentado en implementaciones IJAI: 1/5, 1/3, luego 7/45.
        for piid in (5, 3):
            try:
                value = self._property_value(device, 1, piid)
            except Exception:
                value = None
            if isinstance(value, (bytes, bytearray, memoryview)):
                try:
                    value = bytes(value).decode("utf-8")
                except Exception:
                    value = None
            for serial in self._serial_from_direct(value):
                extra_wifi.append((serial, f"LAN 1/{piid}"))

        try:
            raw_745 = self._property_value(device, 7, 45)
        except Exception:
            raw_745 = None
        serials, owner_suffixes = self._serial_and_owner_from_multi(raw_745)
        extra_wifi.extend((serial, "LAN 7/45") for serial in serials)
        extra_owners.extend((owner, "UID sufijo 7/45") for owner in owner_suffixes)

        cloud_values = self._cloud_props([(1, 5), (1, 3), (7, 45)])
        for (siid, piid), value in cloud_values.items():
            if (siid, piid) == (7, 45):
                serials, owner_suffixes = self._serial_and_owner_from_multi(value)
                extra_wifi.extend((serial, "Cloud 7/45") for serial in serials)
                extra_owners.extend((owner, "Cloud UID sufijo 7/45") for owner in owner_suffixes)
            else:
                for serial in self._serial_from_direct(value):
                    extra_wifi.append((serial, f"Cloud {siid}/{piid}"))

        wifi = self._dedupe(extra_wifi + wifi)
        owners = self._dedupe(extra_owners + owners)
        dids = self._dedupe(dids)
        macs = self._dedupe(macs)

        self.last_key_diagnostics.update({
            "wifi_sources": [source for _, source in wifi],
            "owner_sources": [source for _, source in owners],
            "did_sources": [source for _, source in dids],
            "mac_sources": [source for _, source in macs],
            "wifi_count": len(wifi),
            "owner_count": len(owners),
            "did_count": len(dids),
            "mac_count": len(macs),
            "strict_wifi_count": sum(1 for value, _ in wifi if self._strict_wifi_serial(str(value))),
        })
        self.last_v44_diagnostics = {
            "wifi_shapes": [self._shape(value, source) for value, source in wifi],
            "owner_sources": [source for _, source in owners],
            "did_sources": [source for _, source in dids],
            "mac_sources": [source for _, source in macs],
            "slash_wifi_count": sum(1 for value, _ in wifi if "/" in str(value)),
            "strict_wifi_count": self.last_key_diagnostics.get("strict_wifi_count", 0),
            "route": "IJAI primario con wifi_sn flexible; Xiaomi JSON y V41 como fallback",
        }
        return wifi, owners, dids, macs

    def _mark_success(self, snapshot, route):
        self.last_v44_diagnostics.update({
            "route": route,
            "success": True,
            "crypto_mode": getattr(snapshot, "crypto_mode", None),
            "winner_wifi_source": getattr(snapshot, "wifi_sn_source", None),
            "winner_wifi_length": getattr(snapshot, "wifi_sn_length", 0),
            "winner_owner_source": getattr(snapshot, "owner_source", None),
            "winner_did_source": getattr(snapshot, "did_source", None),
            "winner_mac_source": getattr(snapshot, "mac_source", None),
            "raw_bytes": getattr(snapshot, "raw_size", 0),
            "raw_prefix_hex": getattr(snapshot, "raw_prefix_hex", ""),
            "blob_sha12": str(getattr(snapshot, "blob_sha256", ""))[:12],
            "decrypted_bytes": getattr(snapshot, "decrypted_size", 0),
        })
        return snapshot

    def load(self):
        # La evidencia más reciente para perfiles xiaomi.b112 los enruta como
        # rebrand IJAI. Lo intentamos primero para no ocultar la señal tras el
        # fallback Xiaomi JSON de V43.
        ijai_error = None
        try:
            snapshot = XiaomiE10MapV42.load(self)
            return self._mark_success(snapshot, "IJAI primario V42 + wifi_sn flexible V44")
        except Exception as exc:
            ijai_error = self._safe_http_error(exc)
            self.last_v44_diagnostics.update({
                "ijai_primary_error": ijai_error,
                "v42_native": dict(getattr(self, "last_native_diagnostics", {}) or {}),
                "slots": dict(getattr(self, "last_slot_diagnostics", {}) or {}),
            })

        # Si el firmware concreto contradice la clasificación IJAI, V43 conserva
        # la ruta Xiaomi JSON y vuelve a tener los fallbacks antiguos.
        try:
            snapshot = XiaomiE10MapV43.load(self)
            return self._mark_success(snapshot, "fallback V43 tras IJAI primario")
        except Exception as exc:
            self.last_v44_diagnostics.update({
                "success": False,
                "error": self._safe_http_error(exc),
                "ijai_primary_error": ijai_error,
                "v42_native": dict(getattr(self, "last_native_diagnostics", {}) or {}),
                "v43_xiaomi": dict(getattr(self, "last_xiaomi_diagnostics", {}) or {}),
                "slots": dict(getattr(self, "last_slot_diagnostics", {}) or {}),
            })
            raise
