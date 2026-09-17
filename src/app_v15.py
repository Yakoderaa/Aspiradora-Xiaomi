import threading

# app_v14 usa constantes visuales que app_v9 no exportaba directamente.
# Las exponemos antes de importar app_v14 para evitar un cierre al arrancar.
import app_v8
import app_v9

app_v9.CARD = app_v8.CARD
app_v9.GREEN = app_v8.GREEN
app_v9.MUTED = app_v8.MUTED
app_v9.ACCENT = app_v8.ACCENT

import app_v14


class App(app_v14.App):
    """v15: mapeo ECO fijo + base calibrada con la posición real al cargar."""

    def __init__(self):
        self._eco_mapping_fix_running = False
        self._charging_confirmed = False
        super().__init__()
        if hasattr(self, "mapping_steps_info"):
            self.mapping_steps_info.configure(
                text="Paredes EN VIVO · ECO mínimo · Paso 1 → base → Paso 2 automático · antibloqueo activo"
            )

    # ---------------------------------------------------------- modo ECO fijo
    def _handle_ui_event(self, kind, payload):
        if kind == "status_ok" and payload:
            status_obj = payload[0]
            self._charging_confirmed = int(getattr(status_obj, "status", -1)) == 4

            # Mientras se mapea, mantenemos siempre Aspirar + agua 0 + succión 1.
            # Los métodos de inicio ya lo configuran así; esta vigilancia evita
            # que el firmware lo cambie entre fases o tras una recuperación.
            if (
                self.mapping_active
                and not self._anti_stall_worker
                and not self._eco_mapping_fix_running
            ):
                suction = int(getattr(status_obj, "suction", 0) or 0)
                water = int(getattr(status_obj, "water", 0) or 0)
                mode = int(getattr(status_obj, "mode", 0) or 0)
                if suction != 1 or water != 0 or mode != 0:
                    self._eco_mapping_fix_running = True
                    vacuum = self.vacuum
                    if vacuum:
                        threading.Thread(
                            target=self._force_mapping_eco_worker,
                            args=(vacuum,),
                            daemon=True,
                        ).start()
                    else:
                        self._eco_mapping_fix_running = False

        if kind == "eco_mapping_fixed":
            self._eco_mapping_fix_running = False
            if self.mapping_active:
                self._set_banner(
                    "Mapeo ECO · succión mínima (1), sin agua. Paredes y recorrido actualizándose en vivo…"
                )
            return

        if kind == "eco_mapping_fix_error":
            self._eco_mapping_fix_running = False
            return

        return super()._handle_ui_event(kind, payload)

    def _force_mapping_eco_worker(self, vacuum):
        try:
            vacuum.set_water(0)
            vacuum.set_suction(1)
            vacuum.set_mode(0)
            self._post_ui("eco_mapping_fixed")
        except Exception as exc:
            self._post_ui("eco_mapping_fix_error", str(exc))

    # ---------------------------------------------------- calibración de base
    @staticmethod
    def _base_pose_from_state(state):
        if not isinstance(state, dict):
            return None
        robot = state.get("robot")
        if isinstance(robot, dict) and "x" in robot and "y" in robot:
            try:
                return {
                    "x": float(robot["x"]),
                    "y": float(robot["y"]),
                    "angle": float(robot.get("angle", 0) or 0),
                }
            except Exception:
                pass

        # Fallback: si el firmware no publica 10/24 en ese instante, usamos el
        # último punto de trayectoria; estando CARGANDO corresponde al punto de
        # acople y es mejor referencia que una coordenada de base vacía/errónea.
        path = state.get("path") or []
        if path:
            try:
                point = path[-1]
                return {
                    "x": float(point["x"]),
                    "y": float(point["y"]),
                    "angle": float(point.get("phi", 0) or 0),
                }
            except Exception:
                pass
        return None

    def _apply_map_state(self, state):
        # Cuando el E10 está físicamente acoplado y reporta CARGANDO, su posición
        # es por definición la posición de la base. Reemplazamos la coordenada
        # MIoT de base por esa posición antes de guardarla/dibujarla.
        if self._charging_confirmed and isinstance(state, dict):
            base_pose = self._base_pose_from_state(state)
            if base_pose:
                state = dict(state)
                state["charging_base"] = dict(base_pose)
                # Robot y base coinciden visualmente y la posición queda
                # persistida por LocalMapStore.set_charging_base().
                if not state.get("robot"):
                    state["robot"] = dict(base_pose)

        return super()._apply_map_state(state)


if __name__ == "__main__":
    app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise
