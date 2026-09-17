import time

from xiaomi_e10 import XiaomiE10


class XiaomiE10Edge(XiaomiE10):
    """Controlador de perímetro aislado del flujo de limpieza global.

    En este firmware, start-only-sweep puede resetear sweep-type a Global (0).
    Para evitar secuencias repetidas, arrancamos una sola vez, esperamos a que el
    robot entre en limpieza y fijamos EDGE=2 una única vez. Después sólo
    verificamos; no volvemos a rearmar el modo durante el recorrido.
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

    def _set_edge_once_after_start(self):
        """Fija EDGE una sola vez después del inicio y exige estabilidad.

        No reescribimos EDGE dentro de un bucle porque algunos firmwares hacen
        un pitido/recalculan la trayectoria cada vez que cambia la propiedad.
        """
        start_deadline = time.monotonic() + 4.0
        saw_cleaning = False
        last_status = -1
        last_sweep_type = -1

        # Esperamos a que la acción de arranque haya terminado de aplicar sus
        # valores internos antes de escribir EDGE.
        while time.monotonic() < start_deadline:
            try:
                status, sweep_type = self._edge_state()
                last_status = status
                last_sweep_type = sweep_type
                if status in (5, 6, 7):
                    saw_cleaning = True
                    break
            except Exception:
                pass
            time.sleep(0.12)

        if not saw_cleaning:
            try:
                self.stop()
            except Exception:
                pass
            raise RuntimeError(
                f"El E10 no llegó a iniciar la limpieza (status={last_status})."
            )

        # Una única escritura EDGE después de que el motor ya está en marcha.
        self.set_sweep_type(2)

        # Sólo verificamos. Si el firmware no lo mantiene, cancelamos en vez de
        # estar cambiando de modo repetidamente.
        verify_deadline = time.monotonic() + 2.5
        consecutive_edge = 0
        while time.monotonic() < verify_deadline:
            try:
                status, sweep_type = self._edge_state()
                last_status = status
                last_sweep_type = sweep_type
            except Exception:
                time.sleep(0.14)
                continue

            if status in (5, 6, 7) and sweep_type == 2:
                consecutive_edge += 1
                if consecutive_edge >= 3:
                    return {
                        "status": status,
                        "sweep_type": sweep_type,
                        "confirmed": True,
                    }
            else:
                consecutive_edge = 0

            time.sleep(0.16)

        try:
            self.stop()
        except Exception:
            pass
        raise RuntimeError(
            "El E10 no mantuvo el modo de borde después del inicio "
            f"(status={last_status}, sweep_type={last_sweep_type})."
        )

    def start_mapping_perimeter(self):
        # Mapeo ECO: sólo aspirar, agua 0, succión mínima.
        self.set_water(0)
        self.set_suction(1)
        self.set_mode(0)

        # Desactiva repeticiones automáticas previas si el firmware expone esa
        # propiedad. No es necesaria para mantener EDGE.
        try:
            self.device.set_property_by(7, 1, 0)
        except Exception:
            pass

        # Arranque único. No hay segundo START ni rearmado del recorrido.
        result = self.device.call_action_by(2, 3)
        self._set_edge_once_after_start()
        return result
