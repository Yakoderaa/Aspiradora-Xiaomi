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
        # 1 adelante, 2 izquierda, 3 derecha, 4 atrás, 5 detener, 10 salir
        if direction not in (1, 2, 3, 4, 5, 10):
            raise ValueError("Dirección inválida")
        return self.device.set_property_by(7, 16, direction)


def discover_from_xiaomi(username: str, password: str, locale: str = "all") -> list[dict[str, Any]]:
    """Obtiene E10 vinculados a la cuenta. La contraseña solo vive durante esta llamada."""
    cloud = CloudInterface(username=username.strip(), password=password)
    devices = cloud.get_devices(locale=locale)
    found = []
    for dev in devices.values():
        if dev.model == MODEL and not dev.is_child:
            found.append(
                {
                    "name": dev.name or "Xiaomi Robot Vacuum E10",
                    "ip": dev.ip,
                    "token": dev.token,
                    "locale": dev.locale,
                    "online": dev.is_online,
                    "did": dev.did,
                }
            )
    return found
