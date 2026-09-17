import time

import app_v25


class App(app_v25.App):
    """v26: Paso 1 EDGE nativo y watchdog tolerante a lecturas transitorias."""

    def start_new_mapping(self):
        result = super().start_new_mapping()
        if getattr(self, "mapping_active", False) and getattr(self, "mapping_phase", 0) == 1:
            self._set_banner("Paso 1 · iniciando recorrido de perímetro EDGE nativo…")
        return result

    @staticmethod
    def _valid_edge_status(vacuum, raw):
        normalizer = getattr(vacuum, "normalize_status", None)
        if callable(normalizer):
            return normalizer(raw)
        try:
            value = int(raw)
        except Exception:
            return None
        return value if 0 <= value <= 8 else None

    @staticmethod
    def _valid_sweep_type(vacuum, raw):
        normalizer = getattr(vacuum, "normalize_sweep_type", None)
        if callable(normalizer):
            return normalizer(raw)
        try:
            value = int(raw)
        except Exception:
            return None
        return value if value in (0, 2, 4, 5) else None

    def _watch_edge_only(self, session):
        """Vigila EDGE sin tratar -4/-1 u otros sentinelas como estados reales.

        La orden inicial ya codifica EDGE=2 en la acción nativa 7/3. Las lecturas
        MIoT son únicamente telemetría de seguridad: una muestra inválida nunca
        detiene el robot. Una transición a Global debe ser válida y sostenida.
        """
        vacuum = self.vacuum
        if not vacuum:
            return

        started_at = time.monotonic()
        deadline = started_at + 45 * 60
        seen_edge = False
        seen_cleaning = False
        consecutive_errors = 0
        last_raw_state = None
        global_since = None
        idle_since = None

        while time.monotonic() < deadline:
            if session != self._edge_session or self.mapping_phase != 1:
                return
            vacuum = self.vacuum
            if not vacuum:
                return

            try:
                values = vacuum._get_many([
                    ("status", 2, 1),
                    ("sweep_type", 2, 8),
                ])
                raw_status = values.get("status")
                raw_sweep = values.get("sweep_type")
                status = self._valid_edge_status(vacuum, raw_status)
                sweep_type = self._valid_sweep_type(vacuum, raw_sweep)
                consecutive_errors = 0
            except Exception as exc:
                consecutive_errors += 1
                if consecutive_errors >= 20:
                    self._edge_log(f"Telemetría EDGE perdida: {exc}")
                    try:
                        vacuum.stop()
                    except Exception:
                        pass
                    self._post_ui(
                        "edge_only_error",
                        "Perdí la comunicación con el E10 durante varios segundos. Detuve el Paso 1 por seguridad.",
                    )
                    return
                time.sleep(0.20)
                continue

            raw_state = (raw_status, raw_sweep)
            if raw_state != last_raw_state:
                self._edge_log(
                    f"EDGE raw status={raw_status!r} sweep_type={raw_sweep!r} "
                    f"=> valid status={status!r} sweep_type={sweep_type!r}"
                )
                last_raw_state = raw_state

            # -4, -1 y cualquier valor fuera del rango MIoT son muestras
            # transitorias/no disponibles. Se registran pero no cambian estado.
            if sweep_type == 2:
                seen_edge = True
                global_since = None

            if status in (5, 6, 7):
                seen_cleaning = True
                idle_since = None
            elif status in (0, 1, 2, 4) and (seen_edge or seen_cleaning):
                if idle_since is None:
                    idle_since = time.monotonic()

            # Si EDGE ya fue confirmado y el firmware cambia de verdad a Global,
            # exigimos que el 0 sea sostenido. Una única muestra no corta nada.
            if seen_edge and sweep_type == 0:
                if global_since is None:
                    global_since = time.monotonic()
                elif time.monotonic() - global_since >= 1.25:
                    self._edge_log("Transición EDGE->Global confirmada durante 1.25 s. STOP.")
                    try:
                        vacuum.stop()
                    except Exception:
                        pass
                    self._post_ui(
                        "edge_only_complete",
                        "Paso 1 terminado · perímetro guardado. Detuve la transición a limpieza global.",
                    )
                    return
            elif sweep_type is not None and sweep_type != 0:
                global_since = None

            # Fin normal: tras haber limpiado en EDGE, el robot queda en espera,
            # pausa o carga durante al menos medio segundo.
            if seen_edge and seen_cleaning and idle_since is not None:
                if time.monotonic() - idle_since >= 0.55:
                    self._edge_log(f"EDGE finalizado normalmente con status={status}")
                    self._post_ui(
                        "edge_only_complete",
                        "Paso 1 terminado · recorrido de bordes guardado.",
                    )
                    return

            elapsed = time.monotonic() - started_at

            # Si recibimos telemetría válida que confirma una limpieza Global y
            # nunca apareció EDGE, ahí sí detenemos. No aplicamos esta regla a
            # status/sweep inválidos como -4.
            if elapsed >= 10.0 and not seen_edge and seen_cleaning and sweep_type == 0:
                self._edge_log("EDGE no apareció y Global=0 fue válido durante el arranque. STOP.")
                try:
                    vacuum.stop()
                except Exception:
                    pass
                self._post_ui(
                    "edge_only_error",
                    "El E10 inició una limpieza global en vez del recorrido de borde. La detuve antes de continuar.",
                )
                return

            # Si tras bastante tiempo tenemos un estado válido de reposo/carga y
            # nunca hubo ni EDGE ni limpieza, la acción no arrancó realmente.
            if elapsed >= 18.0 and not seen_edge and not seen_cleaning and status in (0, 1, 2, 4):
                self._edge_log(f"EDGE no arrancó: status={status}, sweep_type={sweep_type}")
                self._post_ui(
                    "edge_only_error",
                    "El E10 no empezó el recorrido de perímetro. No se detectó una limpieza en curso.",
                )
                return

            time.sleep(0.20)

        try:
            vacuum.stop()
        except Exception:
            pass
        self._post_ui("edge_only_error", "El Paso 1 superó el tiempo máximo y fue detenido.")


if __name__ == "__main__":
    app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise
