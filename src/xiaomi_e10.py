import json
import math
import re
from dataclasses import dataclass
from typing import Any

from miio import CloudInterface, MiotDevice

MODEL = "xiaomi.vacuum.b112"

STATUS_NAMES = {
    0: "Dormido",
    1: "En espera",
    2: "Pausado",
    3: "Volviendo a la base",
    4: "Cargando",
    5: "Aspirando",
    6: "Aspirando y trapeando",
    7: "Trapeando",
    8: "Actualizando firmware",
}
MODE_NAMES = {0: "Aspirar", 1: "Aspirar + trapear", 2: "Trapear"}
DOOR_NAMES = {0: "Sin depósito", 1: "Depósito de polvo", 2: "Depósito de agua", 3: "Depósito 2 en 1"}
CLOTH_NAMES = {0: "Sin mopa", 1: "Mopa colocada"}


@dataclass
class VacuumStatus:
    status: int = -1
    fault: int = 0
    mode: int = 0
    battery: int = 0
    suction: int = 0
    water: int = 0
    cleaning_time: int = 0
    cleaning_area: int = 0
    door_state: int = 0
    cloth_state: int = 0
    side_brush_life: int = 0
    main_brush_life: int = 0
    hepa_life: int = 0
    mop_life: int = 0

    @property
    def status_name(self):
        return STATUS_NAMES.get(self.status, f"Estado {self.status}")

    @property
    def mode_name(self):
        return MODE_NAMES.get(self.mode, f"Modo {self.mode}")

    @property
    def door_name(self):
        return DOOR_NAMES.get(self.door_state, f"Estado {self.door_state}")

    @property
    def cloth_name(self):
        return CLOTH_NAMES.get(self.cloth_state, f"Estado {self.cloth_state}")


class XiaomiE10:
    def __init__(self, ip: str, token: str):
        self.ip = ip.strip()
        self.token = token.strip()
        self.device = MiotDevice(self.ip, self.token, model=MODEL, timeout=5)

    def info(self):
        return self.device.info(skip_cache=True)

    def _get_many(self, definitions):
        payload = [
            {"did": name, "siid": siid, "piid": piid}
            for name, siid, piid in definitions
        ]
        result = self.device.send("get_properties", payload)
        values = {}
        for item in result:
            if isinstance(item, dict) and item.get("code", 0) == 0:
                values[item.get("did")] = item.get("value")
        return values

    def _value(self, siid: int, piid: int):
        result = self.device.get_property_by(siid, piid)
        if isinstance(result, list) and result:
            item = result[0]
            if isinstance(item, dict):
                if item.get("code", 0) != 0:
                    raise RuntimeError(f"El robot rechazó la propiedad {siid}/{piid}: {item.get('code')}")
                return item.get("value")
        return None

    def status(self) -> VacuumStatus:
        defs = [
            ("status", 2, 1),
            ("fault", 2, 2),
            ("mode", 2, 4),
            ("battery", 3, 1),
            ("door_state", 7, 3),
            ("cloth_state", 7, 4),
            ("suction", 7, 5),
            ("water", 7, 6),
            ("side_brush_life", 7, 8),
            ("main_brush_life", 7, 10),
            ("hepa_life", 7, 12),
            ("mop_life", 7, 14),
            ("cleaning_time", 7, 22),
            ("cleaning_area", 7, 23),
        ]
        v = self._get_many(defs)
        return VacuumStatus(**{k: int(v.get(k, 0) or 0) for k, _, _ in defs})

    def set_mode(self, mode: int):
        if mode not in (0, 1, 2):
            raise ValueError("Modo inválido")
        return self.device.set_property_by(2, 4, mode)

    def set_sweep_type(self, sweep_type: int):
        # xiaomi.vacuum.b112: 0 global, 2 borde/perímetro, 4 punto, 5 remoto.
        if int(sweep_type) not in (0, 2, 4, 5):
            raise ValueError("Tipo de recorrido inválido")
        return self.device.set_property_by(2, 8, int(sweep_type))

    def set_mop_enabled(self, enabled: bool, water_level: int = 1):
        if enabled:
            water_level = max(1, min(3, int(water_level)))
            self.set_mode(1)
            return self.set_water(water_level)
        self.set_water(0)
        return self.set_mode(0)

    def start(self, mode: int):
        self.set_mode(mode)
        action = {0: 3, 1: 5, 2: 6}[mode]
        return self.device.call_action_by(2, action)

    def stop(self):
        return self.device.call_action_by(2, 2)

    def dock(self):
        return self.device.call_action_by(3, 1)

    def set_suction(self, level: int):
        if level not in (0, 1, 2, 3, 4):
            raise ValueError("Nivel de succión inválido")
        return self.device.set_property_by(7, 5, level)

    def set_water(self, level: int):
        if level not in (0, 1, 2, 3):
            raise ValueError("Nivel de agua inválido")
        return self.device.set_property_by(7, 6, level)

    def locate(self):
        return self.device.set_property_by(4, 1, 1)

    def manual(self, direction: int):
        if direction not in (1, 2, 3, 4, 5, 10):
            raise ValueError("Dirección inválida")
        return self.device.set_property_by(7, 16, direction)

    # --- Telemetría y mapa local ------------------------------------------
    # El E10 expone por MIoT la trayectoria de limpieza (10/5), la base
    # (10/22) y la posición del robot (10/24). La aplicación usa esos datos
    # directamente por LAN para construir su propio mapa sin descargar la
    # imagen de Xiaomi Cloud.

    @staticmethod
    def _numeric_values(value: Any) -> list[float]:
        if value is None:
            return []
        if isinstance(value, (list, tuple)):
            result = []
            for item in value:
                if isinstance(item, (int, float)) and math.isfinite(float(item)):
                    result.append(float(item))
            return result
        if isinstance(value, dict):
            for key in ("data", "value", "position", "point"):
                if key in value:
                    values = XiaomiE10._numeric_values(value[key])
                    if values:
                        return values
            ordered = []
            for key in ("x", "y", "phi", "yaw", "angle"):
                if key in value and isinstance(value[key], (int, float)):
                    ordered.append(float(value[key]))
            return ordered
        text = str(value).strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            if parsed != value:
                values = XiaomiE10._numeric_values(parsed)
                if values:
                    return values
        except Exception:
            pass
        return [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", text)]

    @classmethod
    def parse_position(cls, value: Any) -> dict[str, float] | None:
        if isinstance(value, dict) and "x" in value and "y" in value:
            try:
                x, y = float(value["x"]), float(value["y"])
                angle = float(value.get("phi", value.get("yaw", value.get("angle", 0))) or 0)
                if math.isfinite(x) and math.isfinite(y):
                    return {"x": x, "y": y, "angle": angle}
            except Exception:
                return None
        values = cls._numeric_values(value)
        if len(values) < 2:
            return None
        x, y = values[0], values[1]
        angle = values[2] if len(values) > 2 else 0.0
        if not math.isfinite(x) or not math.isfinite(y):
            return None
        return {"x": x, "y": y, "angle": angle}

    @classmethod
    def parse_trajectory(cls, value: Any) -> list[dict[str, float | int]]:
        if value is None:
            return []
        try:
            parsed = json.loads(value) if isinstance(value, str) else value
        except Exception:
            parsed = value

        if isinstance(parsed, list) and parsed and all(isinstance(p, dict) for p in parsed):
            points = []
            for index, p in enumerate(parsed):
                pos = cls.parse_position(p)
                if pos:
                    points.append({"id": int(p.get("id", index)), "x": pos["x"], "y": pos["y"], "phi": pos["angle"], "update": int(p.get("update", 1))})
            return points

        values = cls._numeric_values(parsed)
        if len(values) < 5:
            return []

        first_pose_id = int(values[0])
        payload = values[1:]
        count = len(payload) // 4
        points = []
        for i in range(count):
            x, y, phi, update = payload[i * 4:i * 4 + 4]
            if not (math.isfinite(x) and math.isfinite(y)):
                continue
            points.append({
                "id": first_pose_id + i,
                "x": float(x),
                "y": float(y),
                "phi": float(phi),
                "update": int(update),
            })
        return points

    def local_map_state(self) -> dict[str, Any]:
        values = self._get_many([
            ("path", 10, 5),
            ("charging_base", 10, 22),
            ("robot", 10, 24),
        ])
        return {
            "path": self.parse_trajectory(values.get("path")),
            "charging_base": self.parse_position(values.get("charging_base")),
            "robot": self.parse_position(values.get("robot")),
            "raw_path": values.get("path"),
        }

    def set_map_remembering(self, enabled: bool = True):
        """Activa/desactiva el guardado persistente de mapas del servicio Map.

        En la familia B112/IJAI, 10/1 es remember-state:
        0 = Close, 1 = Open. Sólo lo activamos desde un mapeo iniciado
        explícitamente por el usuario; los sondeos/diagnósticos nunca lo cambian.
        """
        return self.device.set_property_by(10, 1, 1 if enabled else 0)

    def _prepare_mapping_vacuum(self):
        """Prepara el robot para mapear, guardando el mapa y sin usar agua."""
        # Sin remember-state=1 el E10 puede recorrer la vivienda pero terminar
        # con map-num=0/cur-map-id=0, por lo que Xiaomi Cloud no tiene un mapa
        # persistente que la app pueda recuperar después.
        try:
            self.set_map_remembering(True)
        except Exception:
            # Mantener el mapeo local como fallback si un firmware no acepta la
            # propiedad; V61 lo deja visible en diagnóstico.
            pass
        self.set_water(0)
        self.set_suction(1)
        self.set_mode(0)

    def _start_mapping_sweep(self, sweep_type: int):
        """Recorrido genérico; se usa únicamente para el Paso 2 global."""
        self._prepare_mapping_vacuum()
        self.set_sweep_type(sweep_type)
        try:
            return self.device.call_action_by(2, 1)
        except Exception:
            return self.device.call_action_by(2, 3)

    def start_mapping_perimeter(self):
        """Paso 1: inicia DIRECTAMENTE limpieza de borde en toda la vivienda.

        El E10 expone en el servicio Sweep (siid 7) la acción set-room-clean
        (aiid 3) con tres entradas:
          piid 24: clean-room-ids (vacío = toda la vivienda)
          piid 25: clean-room-mode (2 = Edge)
          piid 26: clean-room-oper (1 = Start)

        Usamos esta acción específica para no ejecutar start-sweep/start-only-sweep,
        que el firmware puede interpretar como una limpieza global después del borde.
        """
        self._prepare_mapping_vacuum()
        return self.device.call_action_by(7, 3, ["", 2, 1])

    def start_mapping_interior(self):
        """Paso 2: recorrido global para completar el interior."""
        return self._start_mapping_sweep(0)

    def start_mapping_run(self):
        """Compatibilidad: un recorrido global de mapeo."""
        return self.start_mapping_interior()

    # --- Limpieza localizada ----------------------------------------------

    def current_map_reference(self):
        return self._value(10, 2)

    def current_map_name(self) -> str:
        value = self.current_map_reference()
        if value is None:
            raise RuntimeError("El E10 no devolvió un mapa actual.")
        if isinstance(value, (int, float)):
            return str(int(value))
        text = str(value).strip()
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                obj_name = parsed.get("obj_name") or parsed.get("map_name")
                if obj_name:
                    return str(obj_name).rstrip("/").split("/")[-1]
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
        if "/" in text:
            return text.rstrip("/").split("/")[-1]
        return text

    def get_map_room_list(self):
        map_id = self.current_map_reference()
        if map_id is None:
            raise RuntimeError("No hay un mapa activo para consultar habitaciones.")
        return self.device.call_action_by(10, 13, [map_id])

    @staticmethod
    def _coord(value: float) -> str:
        value = float(value)
        if value.is_integer():
            return str(int(value))
        return f"{value:.2f}".rstrip("0").rstrip(".")

    def clean_point(self, x: float, y: float):
        target = f"{self._coord(x)},{self._coord(y)}"
        self.device.set_property_by(9, 5, target)
        self.device.set_property_by(2, 8, 4)
        return self.device.call_action_by(9, 1)

    def clean_zone(self, x0: float, y0: float, x1: float, y1: float):
        left, right = sorted((float(x0), float(x1)))
        bottom, top = sorted((float(y0), float(y1)))
        points = [(left, bottom), (left, top), (right, top), (right, bottom)]
        zone = ",".join(self._coord(v) for point in points for v in point)
        try:
            self.device.call_action_by(9, 8, [zone])
        except Exception:
            self.device.set_property_by(9, 2, zone)
        return self.device.call_action_by(9, 3)

    def clean_rooms(self, room_ids: list[int]):
        if not room_ids:
            raise ValueError("Elegí al menos una habitación.")
        value = ",".join(str(int(room_id)) for room_id in room_ids)
        return self.device.call_action_by(7, 3, [value, 0, 1])


def discover_from_xiaomi(username: str, password: str, locale: str = "all") -> list[dict[str, Any]]:
    """Obtiene E10 vinculados a la cuenta. La contraseña solo vive durante esta llamada."""
    cloud = CloudInterface(username=username.strip(), password=password)
    cloud.login()
    regions = [locale] if locale != "all" else ["cn", "de", "us", "ru", "tw", "sg", "in", "i2"]
    found = []
    for region in regions:
        try:
            for dev in cloud.get_devices(region):
                if dev.get("model") == MODEL:
                    found.append({
                        "name": dev.get("name", "Xiaomi Vacuum E10"),
                        "model": dev.get("model"),
                        "ip": dev.get("localip", ""),
                        "token": dev.get("token", ""),
                        "did": dev.get("did", ""),
                        "locale": region,
                    })
        except Exception:
            continue
    return [d for d in found if d["ip"] and d["token"]]
