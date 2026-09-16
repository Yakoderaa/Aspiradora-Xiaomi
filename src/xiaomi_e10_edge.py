import time

from xiaomi_e10 import XiaomiE10


class XiaomiE10Edge(XiaomiE10):
    """Controlador de perímetro aislado del flujo de limpieza global.

    Para el Paso 1 NO usa set-room-clean: en el E10, una lista de habitaciones
    vacía en esa acción significa limpieza global. Tampoco usa start-sweep (2/1).
    Configura EDGE y arranca únicamente la acción start-only-sweep (2/3).
    """

    def start_mapping_perimeter(self):
        # Preparación explícita para aspirar sin agua.
        self.set_water(0)
        self.set_suction(1)
        self.set_mode(0)

        # Evita que una configuración previa de repetición encadene otra pasada.
        try:
            self.device.set_property_by(7, 1, 0)
        except Exception:
            pass

        # El tipo 2 es Edge en xiaomi.vacuum.b112.
        self.set_sweep_type(2)

        # IMPORTANTE: no hay fallback a start-sweep ni a set-room-clean.
        # Si esta acción falla, se informa el error en vez de iniciar una limpieza
        # distinta a la que pidió el usuario.
        result = self.device.call_action_by(2, 3)

        # Verificación inmediata: si el firmware descartó EDGE al arrancar,
        # frenamos antes de permitir una limpieza global accidental.
        time.sleep(0.25)
        values = self._get_many([
            ("status", 2, 1),
            ("sweep_type", 2, 8),
        ])
        sweep_type = values.get("sweep_type")
        if sweep_type is not None and int(sweep_type) != 2:
            try:
                self.stop()
            except Exception:
                pass
            raise RuntimeError(
                f"El E10 cambió el recorrido a {sweep_type} al iniciar. "
                "Cancelé la tarea para evitar una limpieza global."
            )
        return result
