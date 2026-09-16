import time

from xiaomi_e10 import XiaomiE10


class XiaomiE10Edge(XiaomiE10):
    """Controlador de perímetro aislado del flujo de limpieza global.

    El firmware del E10 puede volver a poner sweep-type=0 al ejecutar la acción
    de inicio. Por eso el Paso 1 no configura EDGE solamente *antes* de arrancar:
    primero inicia el motor de limpieza y luego negocia/bloquea EDGE=2 mientras
    el robot ya está en estado de limpieza.
    """

    def _edge_state(self):
        values = self._get_many([
            ("status", 2, 1),
            ("sweep_type", 2, 8),
        ])
        status = values.get("status")
        sweep_type = values.get("sweep_type")
        return (
            int(status) if status is not None else -1,
            int(sweep_type) if sweep_type is not None else -1,
        )

    def _force_edge_after_start(self):
        """Fija EDGE después del arranque y exige estabilidad antes de continuar.

        start-only-sweep puede reescribir sweep-type a Global (0). Para evitar
        ese comportamiento esperamos el inicio real y escribimos EDGE=2 después.
        Se requieren varias confirmaciones consecutivas para considerar que el
        firmware aceptó el modo de borde.
        """
        deadline = time.monotonic() + 6.0
        consecutive_edge = 0
        saw_cleaning = False
        last_status = -1
        last_sweep_type = -1

        # Dejamos que la acción de arranque termine de aplicar sus propios valores.
        time.sleep(0.20)

        while time.monotonic() < deadline:
            try:
                status, sweep_type = self._edge_state()
                last_status = status
                last_sweep_type = sweep_type
            except Exception:
                time.sleep(0.12)
                continue

            if status in (5, 6, 7):
                saw_cleaning = True

            # Una vez iniciado, cualquier valor distinto de EDGE se corrige.
            # También lo escribimos durante la breve transición inicial para que
            # el robot no tenga tiempo de establecer una trayectoria global.
            if sweep_type != 2:
                try:
                    self.set_sweep_type(2)
                except Exception:
                    consecutive_edge = 0
                    time.sleep(0.12)
                    continue
                consecutive_edge = 0
                time.sleep(0.12)
                continue

            if saw_cleaning:
                consecutive_edge += 1
                if consecutive_edge >= 4:
                    return {
                        "status": status,
                        "sweep_type": sweep_type,
                        "confirmed": True,
                    }
            else:
                # Ya quedó en EDGE pero todavía está saliendo de la base/estado
                # de espera. Lo mantenemos fijado mientras arranca.
                consecutive_edge = 0

            time.sleep(0.14)

        try:
            self.stop()
        except Exception:
            pass
        raise RuntimeError(
            "El E10 no logró mantener el modo de borde después de arrancar "
            f"(status={last_status}, sweep_type={last_sweep_type}). "
            "Cancelé la tarea antes de permitir una limpieza global."
        )

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

        # IMPORTANTE: no fijamos EDGE como única acción previa y luego confiamos
        # en que el firmware lo conserve, porque el E10 del usuario lo resetea a
        # Global al ejecutar start-only-sweep.
        #
        # Arrancamos SOLO aspirado (sin mop) y, con el motor ya iniciado,
        # imponemos EDGE=2 hasta que quede confirmado varias veces seguidas.
        result = self.device.call_action_by(2, 3)
        self._force_edge_after_start()
        return result
