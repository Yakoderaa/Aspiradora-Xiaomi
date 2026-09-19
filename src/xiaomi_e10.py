import json
import math
import re
import time
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
    cleaning_area: float = 0.0
    cleaning_area_raw: int = 0
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
        self._last_status_code = -1
        self._last_cleaning_area_raw = 0
        self._targeted_clean_guard = 0
        self._targeted_clean_blocked_mapping_calls = 0
        self._targeted_clean_last_blocked = None
        self._last_global_start_diag = {}
        self._locate_calls = 0
        self._last_locate_at = 0.0
        self._global_clean_guard = 0
        self._global_clean_seen_active = False
        self._global_clean_terminal_streak = 0
        self._global_clean_guard_source = None
        self._global_clean_guard_started_at = 0.0
        self._global_clean_guard_cleared_at = 0.0
        self._blocked_duplicate_starts = 0
        self._last_blocked_duplicate_start = None
        self._motor_start_audit = []
        self._last_mapping_exploration_diag = {}

    def info(self):
        return self.device.info(skip_cache=True)

    def begin_targeted_clean(self):
        self._targeted_clean_guard = int(
            getattr(self, "_targeted_clean_guard", 0) or 0
        ) + 1
        return self._targeted_clean_guard

    def end_targeted_clean(self):
        self._targeted_clean_guard = max(
            0,
            int(getattr(self, "_targeted_clean_guard", 0) or 0) - 1,
        )
        return self._targeted_clean_guard

    def targeted_clean_guard_active(self):
        return int(getattr(self, "_targeted_clean_guard", 0) or 0) > 0

    def global_clean_guard_active(self):
        return int(getattr(self, "_global_clean_guard", 0) or 0) > 0

    def begin_global_clean_guard(self, source="global-start"):
        self._global_clean_guard = 1
        self._global_clean_seen_active = True
        self._global_clean_terminal_streak = 0
        self._global_clean_guard_source = str(source or "global-start")
        self._global_clean_guard_started_at = time.monotonic()
        return True

    def end_global_clean_guard(self, source="terminal"):
        was_active = self.global_clean_guard_active()
        self._global_clean_guard = 0
        self._global_clean_terminal_streak = 0
        self._global_clean_guard_source = str(source or "terminal")
        self._global_clean_guard_cleared_at = time.monotonic()
        return was_active

    def reset_motor_start_audit(self):
        self._motor_start_audit = []
        self._blocked_duplicate_starts = 0
        self._last_blocked_duplicate_start = None

    def _record_motor_start(
        self,
        operation,
        siid,
        aiid,
        params=None,
        blocked=False,
        response=None,
        error=None,
    ):
        rows = list(getattr(self, "_motor_start_audit", []) or [])
        rows.append({
            "t": round(time.monotonic(), 3),
            "operation": str(operation),
            "siid": int(siid),
            "aiid": int(aiid),
            "params": repr(params)[:180],
            "blocked": bool(blocked),
            "response": repr(response)[:180] if response is not None else None,
            "error": str(error)[:240] if error else None,
        })
        self._motor_start_audit = rows[-40:]

    def _send_motor_start(
        self,
        operation,
        siid,
        aiid,
        params=None,
        allow_when_guarded=False,
    ):
        if self.global_clean_guard_active() and not allow_when_guarded:
            self._blocked_duplicate_starts = int(
                getattr(self, "_blocked_duplicate_starts", 0) or 0
            ) + 1
            self._last_blocked_duplicate_start = {
                "operation": str(operation),
                "siid": int(siid),
                "aiid": int(aiid),
                "params": repr(params)[:180],
            }
            self._record_motor_start(
                operation,
                siid,
                aiid,
                params,
                blocked=True,
                error="bloqueado por candado físico V118",
            )
            raise RuntimeError(
                "Seguridad V118: el E10 ya está en una limpieza física activa; "
                "se bloqueó una segunda orden de arranque."
            )

        try:
            if params is None:
                response = self.device.call_action_by(int(siid), int(aiid))
            else:
                response = self.device.call_action_by(
                    int(siid),
                    int(aiid),
                    params,
                )
            self._record_motor_start(
                operation,
                siid,
                aiid,
                params,
                blocked=False,
                response=response,
            )
            return response
        except Exception as exc:
            self._record_motor_start(
                operation,
                siid,
                aiid,
                params,
                blocked=False,
                error=str(exc).strip() or type(exc).__name__,
            )
            raise

    def _note_global_clean_status(self, status_code):
        if not self.global_clean_guard_active():
            return
        try:
            status_code = int(status_code)
        except Exception:
            return

        if status_code in (2, 3, 5, 6, 7):
            if status_code in (5, 6, 7):
                self._global_clean_seen_active = True
            self._global_clean_terminal_streak = 0
            return

        # Carga es evidencia física fuerte de cierre. 0/1 pueden aparecer de
        # forma transitoria durante una limpieza B112, así que requieren seis
        # lecturas consecutivas antes de liberar el candado.
        if status_code == 4:
            self.end_global_clean_guard("status=4 · dock físico")
            return

        if status_code in (0, 1) and self._global_clean_seen_active:
            self._global_clean_terminal_streak = int(
                getattr(self, "_global_clean_terminal_streak", 0) or 0
            ) + 1
            if self._global_clean_terminal_streak >= 6:
                self.end_global_clean_guard(
                    f"status={status_code} estable ×6"
                )
            return

        self._global_clean_terminal_streak = 0

    def _reject_mapping_during_targeted_clean(self, operation):
        if not (
            self.targeted_clean_guard_active()
            or self.global_clean_guard_active()
        ):
            return
        self._targeted_clean_blocked_mapping_calls = int(
            getattr(self, "_targeted_clean_blocked_mapping_calls", 0) or 0
        ) + 1
        self._targeted_clean_last_blocked = str(operation)
        raise RuntimeError(
            "Seguridad V114: una limpieza dirigida no puede iniciar, "
            "armar ni reconstruir un mapa."
        )

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
        values = {}

        try:
            status_code = int(v.get("status", -1))
        except Exception:
            status_code = -1

        self._note_global_clean_status(status_code)

        active_states = (2, 5, 6, 7)
        tail_states = (3, 4)

        # Una sesión nueva debe empezar sin arrastrar el área anterior.
        if (
            status_code in active_states
            and self._last_status_code not in active_states
        ):
            self._last_cleaning_area_raw = 0

        try:
            cleaning_area_raw = int(v.get("cleaning_area", 0) or 0)
        except Exception:
            cleaning_area_raw = 0

        # Algunos firmwares B112 omiten 7/23 en el get_properties múltiple.
        # Si estamos limpiando/retornando/cargando, probamos la propiedad sola.
        if cleaning_area_raw <= 0 and status_code in active_states + tail_states:
            try:
                direct_area = self._value(7, 23)
                cleaning_area_raw = int(direct_area or 0)
            except Exception:
                cleaning_area_raw = 0

        if cleaning_area_raw > 0:
            self._last_cleaning_area_raw = max(
                int(self._last_cleaning_area_raw or 0),
                int(cleaning_area_raw),
            )
        elif status_code in tail_states and self._last_cleaning_area_raw > 0:
            # El dock puede devolver 0 aunque Mi Home siga mostrando el área
            # de la limpieza recién terminada. Conservamos el último acumulado.
            cleaning_area_raw = int(self._last_cleaning_area_raw)

        for key, _siid, _piid in defs:
            if key == "cleaning_area":
                # En xiaomi.vacuum.b112 7/23 usa décimas de m² en la práctica.
                # El raw se conserva aparte para que el selector de mapa pueda
                # validar/inferir el factor sin depender de esta presentación.
                values[key] = float(cleaning_area_raw) * 0.1
                continue

            raw = v.get(key, 0) or 0
            try:
                values[key] = int(raw)
            except Exception:
                values[key] = 0

        values["cleaning_area_raw"] = int(cleaning_area_raw)
        self._last_status_code = int(status_code)
        return VacuumStatus(**values)

    def set_mode(self, mode: int):
        if mode not in (0, 1, 2):
            raise ValueError("Modo inválido")
        return self.device.set_property_by(2, 4, mode)

    def set_sweep_type(self, sweep_type: int):
        # xiaomi.vacuum.b112: 0 global, 2 bordes, 4 espiral/punto, 5 remoto.
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

    def _start_with_sweep_type(self, mode: int, sweep_type: int):
        if mode not in (0, 1, 2):
            raise ValueError("Modo inválido")
        if int(sweep_type) not in (0, 2, 4):
            raise ValueError("Tipo de limpieza inválido")
        if self.global_clean_guard_active():
            self._send_motor_start(
                f"start sweep_type={int(sweep_type)}",
                2,
                {0: 3, 1: 5, 2: 6}[mode],
            )
        self.set_mode(mode)
        self.set_sweep_type(int(sweep_type))
        action = {0: 3, 1: 5, 2: 6}[mode]
        return self._send_motor_start(
            f"start sweep_type={int(sweep_type)}",
            2,
            action,
        )

    def start(self, mode: int):
        # La limpieza normal siempre vuelve a Global=0.
        return self._start_with_sweep_type(mode, 0)

    def start_global_verified(self, mode: int, confirm_timeout: float = 3.0):
        """Inicia limpieza global y exige confirmación física del E10.

        El B112 puede devolver una respuesta válida sin abandonar el dock.
        V115 prueba rutas de inicio conocidas, pero sólo confirma éxito cuando
        2/1 informa un estado físico de limpieza (5, 6 o 7).
        Ninguna de estas rutas arma, crea ni reconstruye mapas.
        """
        if mode not in (0, 1, 2):
            raise ValueError("Modo inválido")

        self.set_mode(mode)
        self.set_sweep_type(0)

        def read_status_code():
            try:
                return int(self._value(2, 1))
            except Exception:
                return int(self.status().status)

        try:
            before = read_status_code()
        except Exception:
            before = -1

        if before in (5, 6, 7):
            self.begin_global_clean_guard("already_active")
            self._last_global_start_diag = {
                "success": True,
                "method": "already_active",
                "status_before": before,
                "status_after": before,
                "attempts": [],
            }
            return dict(self._last_global_start_diag)

        timeout = max(0.15, float(confirm_timeout or 0.0))
        mode_action = {0: 3, 1: 5, 2: 6}[mode]
        candidates = [
            (
                "mode_action",
                lambda: self._send_motor_start(
                    "start_global_verified/mode_action",
                    2,
                    mode_action,
                    allow_when_guarded=True,
                ),
            ),
            (
                "generic_start",
                lambda: self._send_motor_start(
                    "start_global_verified/generic_start",
                    2,
                    1,
                    allow_when_guarded=True,
                ),
            ),
            (
                "whole_home",
                lambda: self._send_motor_start(
                    "start_global_verified/whole_home",
                    7,
                    3,
                    ["", 0, 1],
                    allow_when_guarded=True,
                ),
            ),
        ]

        attempts = []
        last_status = before
        last_error = None

        for name, command in candidates:
            item = {
                "method": name,
                "status_before": last_status,
                "response": None,
                "error": None,
                "status_after": last_status,
            }
            try:
                response = command()
                item["response"] = repr(response)[:500]
            except Exception as exc:
                item["error"] = str(exc).strip() or type(exc).__name__
                last_error = item["error"]

            # Incluso si la respuesta MIoT fue rara/errónea, verificamos el
            # estado: algunos firmwares ejecutan el comando antes del ACK.
            deadline = time.monotonic() + timeout
            while True:
                try:
                    current = read_status_code()
                    last_status = current
                    item["status_after"] = current
                    if current in (5, 6, 7):
                        attempts.append(item)
                        self.begin_global_clean_guard(name)
                        self._last_global_start_diag = {
                            "success": True,
                            "method": name,
                            "status_before": before,
                            "status_after": current,
                            "attempts": attempts,
                        }
                        return dict(self._last_global_start_diag)
                except Exception as exc:
                    item["status_error"] = (
                        str(exc).strip() or type(exc).__name__
                    )

                if time.monotonic() >= deadline:
                    break
                time.sleep(0.35)

            attempts.append(item)

        self._last_global_start_diag = {
            "success": False,
            "method": None,
            "status_before": before,
            "status_after": last_status,
            "attempts": attempts,
            "error": last_error,
        }
        raise RuntimeError(
            "El E10 recibió los intentos de inicio pero no confirmó movimiento "
            f"(estado final {last_status}). Revisá el diagnóstico V115."
        )

    def start_edge(self, mode: int = 0):
        return self._start_with_sweep_type(mode, 2)

    def start_spiral(self, mode: int = 0):
        return self._start_with_sweep_type(mode, 4)

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
        self._locate_calls = int(getattr(self, "_locate_calls", 0) or 0) + 1
        self._last_locate_at = time.monotonic()
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

    @staticmethod
    def _miot_set_code(response):
        """Extrae el primer code MIoT de una respuesta set_properties."""
        rows = response
        if isinstance(rows, dict):
            rows = rows.get("result") or rows.get("data") or rows.get("out") or [rows]
        if not isinstance(rows, list):
            return None
        for row in rows:
            if isinstance(row, dict) and "code" in row:
                try:
                    return int(row.get("code"))
                except Exception:
                    return None
        return None

    @classmethod
    def _miot_action_code(cls, response):
        """Extrae el code principal de una respuesta MIoT de acción."""
        if isinstance(response, dict):
            if "code" in response:
                try:
                    return int(response.get("code"))
                except Exception:
                    return None
            for key in ("result", "data"):
                if key in response:
                    code = cls._miot_action_code(response.get(key))
                    if code is not None:
                        return code
            return None
        if isinstance(response, (list, tuple)):
            for item in response:
                code = cls._miot_action_code(item)
                if code is not None:
                    return code
        return None

    @classmethod
    def _miot_action_ack(cls, response) -> bool:
        """Detecta el ACK simple que devuelve python-miio para acciones MIoT.

        MiIOProtocol devuelve directamente payload["result"]. Para acciones
        MIoT sin salida estructurada, python-miio y muchos dispositivos usan
        ["ok"] (o "ok"), por lo que la ausencia de code NO implica rechazo.
        """
        if response is None:
            return False
        if isinstance(response, (bytes, bytearray, memoryview)):
            try:
                response = bytes(response).decode("utf-8", errors="ignore")
            except Exception:
                return False
        if isinstance(response, str):
            return response.strip().lower() == "ok"
        if isinstance(response, dict):
            for key in ("result", "data", "out", "status"):
                if key in response and cls._miot_action_ack(response.get(key)):
                    return True
            return False
        if isinstance(response, (list, tuple)):
            return any(cls._miot_action_ack(item) for item in response)
        return False

    @classmethod
    def _miot_b112_empty_result_ack(cls, response) -> bool:
        """Reconoce el quirk de respuesta vacía documentado para xiaomi.vacuum.b112.

        python-miio incluye un test específico para este modelo donde el robot
        responde con JSON inválido equivalente a:
            {"id":2,"result":,"exe_time":0}
        Tras el repair del parser, call_action_by() recibe un dict con id y
        exe_time pero sin result/code. Como los errores MIoT son elevados antes
        por MiIOProtocol, esta forma concreta es un ACK de resultado vacío.
        """
        if not isinstance(response, dict):
            return False
        if "error" in response:
            return False
        if "id" not in response or "exe_time" not in response:
            return False
        if "code" in response:
            try:
                if int(response.get("code")) != 0:
                    return False
            except Exception:
                return False
        # Este ACK específico no debe aceptar un result sustantivo ambiguo.
        if "result" in response and response.get("result") not in (None, "", [], {}):
            return False
        try:
            int(response.get("id"))
            exe_time = float(response.get("exe_time"))
        except Exception:
            return False
        return exe_time >= 0

    @classmethod
    def _miot_action_response_summary(cls, response) -> str:
        """Resume la forma de la respuesta sin volcar payloads extensos."""
        if response is None:
            return "None"
        if isinstance(response, (bytes, bytearray, memoryview)):
            return f"{type(response).__name__}[{len(response)}]"
        if isinstance(response, str):
            text = response.strip()
            return repr(text[:80] + ("…" if len(text) > 80 else ""))
        if isinstance(response, dict):
            keys = sorted(str(k) for k in response.keys())
            code = cls._miot_action_code(response)
            return f"dict(keys={keys[:10]}, code={code!r})"
        if isinstance(response, (list, tuple)):
            preview = []
            for item in list(response)[:4]:
                if isinstance(item, str):
                    preview.append(repr(item[:40]))
                elif isinstance(item, (int, float, bool)) or item is None:
                    preview.append(repr(item))
                else:
                    preview.append(type(item).__name__)
            return f"{type(response).__name__}[{len(response)}]({', '.join(preview)})"
        return type(response).__name__

    @classmethod
    def _miot_output_value(cls, response, target_piid: int):
        """Busca recursivamente un valor de salida por PIID."""
        if isinstance(response, dict):
            if "value" in response:
                try:
                    piid = int(response.get("piid"))
                except Exception:
                    piid = None
                if piid == int(target_piid):
                    return response.get("value")
            for key in ("out", "result", "data"):
                if key in response:
                    found = cls._miot_output_value(response.get(key), target_piid)
                    if found is not None:
                        return found
        elif isinstance(response, (list, tuple)):
            for item in response:
                found = cls._miot_output_value(item, target_piid)
                if found is not None:
                    return found
        return None

    def arm_new_map(self, build_mode: int = 1):
        self._reject_mapping_during_targeted_clean("arm_new_map")
        """Arma la creación de un mapa nuevo usando las acciones B112 oficiales.

        xiaomi.vacuum.b112 define 10/17 build-map-ii con PIID 14 como entrada y
        PIID 18 (timestamp) como salida. También conserva 10/11 build-new-map
        como variante anterior. V66 usa 10/17 primero y sólo cae a 10/11 si la
        acción nueva es rechazada.

        Importante: 10/1 remember-state deja de ser un gate. En el B112 real
        observado puede rechazar el valor 1 aunque la acción de creación de
        mapa exista y esté documentada.
        """
        import time

        mode = int(build_mode)
        if mode not in (1, 2):
            raise ValueError("Modo build-map inválido")

        try:
            before = self._get_many([
                ("build_map", 10, 14),
                ("has_new_map", 10, 19),
                ("map_privacy", 10, 23),
            ])
        except Exception:
            before = {}

        attempts = []
        success = False
        winner = None
        final_state = {}
        for aiid, name in ((17, "build-map-ii"), (11, "build-new-map")):
            item = {"aiid": aiid, "action": name, "mode": mode}
            try:
                response = self.device.call_action_by(10, aiid, [mode])
                code = self._miot_action_code(response)
                ack = self._miot_action_ack(response)
                b112_empty_ack = self._miot_b112_empty_result_ack(response)
                timestamp = self._miot_output_value(response, 18)
                item["code"] = code
                item["ack"] = bool(ack)
                item["b112_empty_ack"] = bool(b112_empty_ack)
                item["response_type"] = type(response).__name__
                item["response_summary"] = self._miot_action_response_summary(response)
                item["timestamp"] = timestamp
            except Exception as exc:
                item["error"] = str(exc).strip() or type(exc).__name__
                attempts.append(item)
                continue

            time.sleep(0.22)
            try:
                final_state = self._get_many([
                    ("build_map", 10, 14),
                    ("has_new_map", 10, 19),
                    ("map_privacy", 10, 23),
                ])
            except Exception as exc:
                item["readback_error"] = str(exc).strip() or type(exc).__name__
                final_state = {}

            item["build_map_readback"] = final_state.get("build_map")
            item["has_new_map_readback"] = final_state.get("has_new_map")
            item["map_privacy_readback"] = final_state.get("map_privacy")

            # V66: además del ACK ["ok"] de V65, xiaomi.vacuum.b112 tiene un
            # quirk documentado por python-miio: result vacío/malformado que se
            # repara como {"id": ..., "exe_time": ...}. Esa forma exacta cuenta
            # como ACK fuerte del B112. Un code negativo sigue mandando.
            explicit_reject = code is not None and code != 0
            accepted = (
                not explicit_reject
                and (
                    code == 0
                    or bool(ack)
                    or bool(b112_empty_ack)
                    or timestamp is not None
                    or self._numeric_values(final_state.get("build_map"))[:1] == [float(mode)]
                )
            )
            item["accepted"] = bool(accepted)
            attempts.append(item)
            if accepted:
                success = True
                winner = name
                break

        self.last_map_build_diag = {
            "requested_mode": mode,
            "before": dict(before or {}),
            "after": dict(final_state or {}),
            "success": bool(success),
            "winner": winner,
            "attempts": attempts,
        }

        if not success:
            detail = "; ".join(
                (
                    f"{x.get('action')}: {x.get('error')}"
                    if x.get("error")
                    else (
                        f"{x.get('action')}: code={x.get('code')!r}, "
                        f"ack={bool(x.get('ack'))}, b112-empty={bool(x.get('b112_empty_ack'))}, "
                        f"resp={x.get('response_summary') or '—'}"
                    )
                )
                for x in attempts
            ) or "sin respuesta"
            raise RuntimeError(
                "El E10 no aceptó la orden oficial de crear un mapa nuevo "
                "(10/17 build-map-ii ni 10/11 build-new-map). "
                "Cancelé el recorrido antes de mover el robot. "
                + detail
            )
        return dict(self.last_map_build_diag)

    def set_map_remembering(self, enabled: bool = True, verify: bool = True, retries: int = 3):
        """Cambia 10/1 remember-state y verifica que el B112 lo haya aplicado.

        10/1 es escribible (Switch / set_properties) en la familia IJAI. V61
        enviaba el setter pero ignoraba por completo su respuesta; un rechazo
        silencioso permitía iniciar el recorrido con remember-state todavía en 0.

        V62 exige confirmación por lectura antes de mover el robot. Si el
        firmware no acepta el cambio, el mapeo se aborta antes de arrancar.
        """
        import time

        desired = 1 if enabled else 0
        attempts = []
        try:
            before = self._value(10, 1)
        except Exception as exc:
            before = None
            attempts.append({
                "stage": "read-before",
                "error": str(exc).strip() or type(exc).__name__,
            })

        strategies = (
            ("set_property_by", lambda: self.device.set_property_by(
                10, 1, desired, name="remember-state"
            )),
            ("raw_set_properties", lambda: self.device.send(
                "set_properties",
                [{"did": "remember-state", "siid": 10, "piid": 1, "value": desired}],
            )),
        )

        final_value = before
        success = False
        last_error = None
        total = max(1, int(retries or 1))
        for index in range(total):
            strategy_name, setter = strategies[min(index, len(strategies) - 1)]
            item = {"attempt": index + 1, "strategy": strategy_name}
            try:
                response = setter()
                item["code"] = self._miot_set_code(response)
            except Exception as exc:
                item["error"] = str(exc).strip() or type(exc).__name__
                last_error = item["error"]
                attempts.append(item)
                time.sleep(0.18 * (index + 1))
                continue

            if not verify:
                success = item.get("code") in (None, 0)
                final_value = desired if success else before
                attempts.append(item)
                if success:
                    break
                time.sleep(0.18 * (index + 1))
                continue

            time.sleep(0.22 + (0.12 * index))
            try:
                final_value = self._value(10, 1)
                item["readback"] = final_value
                success = int(final_value) == desired
            except Exception as exc:
                item["verify_error"] = str(exc).strip() or type(exc).__name__
                last_error = item["verify_error"]
                success = False

            item["verified"] = bool(success)
            attempts.append(item)
            if success:
                break

        self.last_map_persistence_diag = {
            "desired": desired,
            "before": before,
            "after": final_value,
            "success": bool(success),
            "attempts": attempts,
        }

        if not success:
            detail = last_error or (
                f"lectura final={final_value!r}; respuesta MIoT no confirmó {desired}"
            )
            raise RuntimeError(
                "El E10 no confirmó remember-state="
                + str(desired)
                + ". Cancelé el mapeo antes de mover el robot. "
                + detail
            )
        return final_value

    def _prepare_mapping_vacuum(self):
        self._reject_mapping_during_targeted_clean("_prepare_mapping_vacuum")
        """Prepara el robot físicamente para mapear en ECO.

        V64 ya no escribe 10/1 remember-state. La creación del mapa se arma de
        forma explícita mediante 10/17 build-map-ii antes del Paso 1.
        """
        self.set_water(0)
        self.set_suction(1)
        self.set_mode(0)

    def _start_mapping_sweep(self, sweep_type: int):
        self._reject_mapping_during_targeted_clean("_start_mapping_sweep")
        """Recorrido genérico; se usa únicamente para el Paso 2 global."""
        self._prepare_mapping_vacuum()
        self.set_sweep_type(sweep_type)
        try:
            return self.device.call_action_by(2, 1)
        except Exception:
            return self.device.call_action_by(2, 3)

    def start_mapping_perimeter(self):
        self._reject_mapping_during_targeted_clean("start_mapping_perimeter")
        """Paso 1: inicia DIRECTAMENTE limpieza de borde en toda la vivienda.

        El E10 expone en el servicio Sweep (siid 7) la acción set-room-clean
        (aiid 3) con tres entradas:
          piid 24: clean-room-ids (vacío = toda la vivienda)
          piid 25: clean-room-mode (2 = Edge)
          piid 26: clean-room-oper (1 = Start)

        Usamos esta acción específica para no ejecutar start-sweep/start-only-sweep,
        que el firmware puede interpretar como una limpieza global después del borde.
        """
        self.arm_new_map(1)
        self._prepare_mapping_vacuum()
        return self.device.call_action_by(7, 3, ["", 2, 1])

    def start_mapping_exploration(self, confirm_timeout: float = 5.0):
        """V120: explora toda la vivienda con el modo Edge nativo del B112.

        Debe llamarse después de arm_new_map(). A diferencia de
        start_mapping_interior(), no lanza un sweep global normal.
        """
        self._reject_mapping_during_targeted_clean("start_mapping_exploration")
        self._prepare_mapping_vacuum()

        diag = {
            "command": "7/3 set-room-clean",
            "params": ["", 2, 1],
            "sweep_type_requested": 2,
            "status_before": None,
            "status_after": None,
            "sweep_type_after": None,
            "response": None,
            "success": False,
            "error": None,
        }

        try:
            before = self._get_many([
                ("status", 2, 1),
                ("sweep_type", 2, 8),
            ])
            diag["status_before"] = before.get("status")
        except Exception as exc:
            diag["status_before_error"] = (
                str(exc).strip() or type(exc).__name__
            )

        # Evita heredar repetición o un patrón anterior.
        try:
            self.device.set_property_by(7, 1, 0)
        except Exception as exc:
            diag["repeat_reset_error"] = (
                str(exc).strip() or type(exc).__name__
            )

        try:
            self.set_sweep_type(2)
        except Exception as exc:
            diag["sweep_type_set_error"] = (
                str(exc).strip() or type(exc).__name__
            )

        try:
            response = self.device.call_action_by(7, 3, ["", 2, 1])
            diag["response"] = repr(response)[:500]
        except Exception as exc:
            diag["error"] = str(exc).strip() or type(exc).__name__
            self._last_mapping_exploration_diag = dict(diag)
            raise

        deadline = time.monotonic() + max(0.5, float(confirm_timeout or 0.0))
        last_status = None
        last_sweep = None
        while True:
            try:
                state = self._get_many([
                    ("status", 2, 1),
                    ("sweep_type", 2, 8),
                ])
                last_status = state.get("status")
                last_sweep = state.get("sweep_type")
                diag["status_after"] = last_status
                diag["sweep_type_after"] = last_sweep
                try:
                    if int(last_status) in (5, 6, 7):
                        diag["success"] = True
                        self._last_mapping_exploration_diag = dict(diag)
                        return response
                except Exception:
                    pass
            except Exception as exc:
                diag["readback_error"] = (
                    str(exc).strip() or type(exc).__name__
                )

            if time.monotonic() >= deadline:
                break
            time.sleep(0.35)

        diag["error"] = (
            "El E10 no confirmó movimiento físico en modo exploración "
            f"(status={last_status!r}, sweep-type={last_sweep!r})."
        )
        self._last_mapping_exploration_diag = dict(diag)
        raise RuntimeError(diag["error"])

    def start_mapping_interior(self):
        self._reject_mapping_during_targeted_clean("start_mapping_interior")
        """Paso 2: recorrido global para completar el interior."""
        return self._start_mapping_sweep(0)

    def start_mapping_run(self):
        self._reject_mapping_during_targeted_clean("start_mapping_run")
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
        if self.global_clean_guard_active():
            return self._send_motor_start("clean_point", 9, 1, [target])
        self.device.set_property_by(9, 5, target)
        self.device.set_property_by(2, 8, 4)
        return self._send_motor_start("clean_point", 9, 1)

    def clean_zone(self, x0: float, y0: float, x1: float, y1: float):
        left, right = sorted((float(x0), float(x1)))
        bottom, top = sorted((float(y0), float(y1)))
        points = [(left, bottom), (left, top), (right, top), (right, bottom)]
        zone = ",".join(self._coord(v) for point in points for v in point)
        try:
            self.device.call_action_by(9, 8, [zone])
        except Exception:
            self.device.set_property_by(9, 2, zone)
        return self._send_motor_start("clean_zone", 9, 3)

    def clean_rooms(self, room_ids: list[int]):
        if not room_ids:
            raise ValueError("Elegí al menos una habitación.")
        value = ",".join(str(int(room_id)) for room_id in room_ids)
        return self._send_motor_start(
            "clean_rooms",
            7,
            3,
            [value, 0, 1],
        )


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
