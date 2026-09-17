from xiaomi_e10 import XiaomiE10


class XiaomiE10Edge(XiaomiE10):
    """Controlador de perímetro usando la acción EDGE nativa del E10.

    El firmware B112 expone set-room-clean (7/3) con:
      clean-room-ids = ""  -> toda la vivienda
      clean-room-mode = 2 -> Edge
      clean-room-oper = 1 -> Start

    Esta ruta evita arrancar con start-only-sweep (2/3), que en algunos
    firmwares puede resetear sweep-type o devolver lecturas transitorias
    inválidas como -4 durante la salida de la base.
    """

    VALID_STATUS = set(range(0, 9))
    VALID_SWEEP_TYPES = {0, 2, 4, 5}

    @classmethod
    def normalize_status(cls, value):
        try:
            value = int(value)
        except Exception:
            return None
        return value if value in cls.VALID_STATUS else None

    @classmethod
    def normalize_sweep_type(cls, value):
        try:
            value = int(value)
        except Exception:
            return None
        return value if value in cls.VALID_SWEEP_TYPES else None

    def edge_state(self):
        values = self._get_many([
            ("status", 2, 1),
            ("sweep_type", 2, 8),
        ])
        return {
            "status": self.normalize_status(values.get("status")),
            "sweep_type": self.normalize_sweep_type(values.get("sweep_type")),
            "raw_status": values.get("status"),
            "raw_sweep_type": values.get("sweep_type"),
        }

    def start_mapping_perimeter(self):
        # Mapeo ECO: sólo aspirar, sin agua y con potencia mínima.
        self.set_water(0)
        self.set_suction(1)
        self.set_mode(0)

        # Evita una repetición heredada de una limpieza anterior.
        try:
            self.device.set_property_by(7, 1, 0)
        except Exception:
            pass

        # Preseleccionamos EDGE una sola vez. Si la propiedad está temporalmente
        # no disponible, la acción 7/3 igualmente lleva mode=2 explícitamente.
        try:
            self.set_sweep_type(2)
        except Exception:
            pass

        # Acción nativa de borde para toda la vivienda. No usamos 2/3 ni un
        # segundo START, por lo que no hay rearmado/pitido intencional.
        return self.device.call_action_by(7, 3, ["", 2, 1])
