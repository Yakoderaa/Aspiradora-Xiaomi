import threading

import app_v32
from xiaomi_e10_probe import XiaomiE10Probe


class App(app_v32.App):
    """v33: 10/24-10/22 entra directo al plano + sonda servicio 10."""

    def connect_device(self, ip, token, quiet=False):
        self._set_banner("Conectando con el robot…")
        ip = str(ip).strip()
        token = str(token).strip()

        def worker():
            try:
                vacuum = XiaomiE10Probe(ip, token)
                info = vacuum.info()
                model = getattr(info, "model", "")
                if model and model != "xiaomi.vacuum.b112":
                    raise RuntimeError(f"El dispositivo respondió como {model}, no como Xiaomi Vacuum E10.")
                vacuum.status()
                self._post_ui("connect_ok", vacuum, ip)
            except Exception as exc:
                self._post_ui("connect_error", str(exc).strip() or "El robot no respondió correctamente.", quiet)

        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def _relative_robot_from_state(state):
        if not isinstance(state, dict):
            return None
        robot = state.get("robot")
        base = state.get("charging_base")
        if not isinstance(robot, dict) or not isinstance(base, dict):
            return None
        try:
            return {
                "x": float(robot["x"]) - float(base["x"]),
                "y": float(robot["y"]) - float(base["y"]),
                "angle": float(robot.get("angle", 0) or 0),
            }
        except Exception:
            return None

    def _apply_map_state(self, state):
        # Bypass deliberado de la antigua lógica de orígenes: si 10/22 y 10/24
        # comparten referencia, su resta YA ES la coordenada local que debe ver
        # el usuario. No permitimos que una capa heredada la vuelva a convertir
        # en 0,0 tomando la propia posición del robot como origen.
        normalized = dict(state or {})
        relative = self._relative_robot_from_state(normalized)
        if relative is not None and not (normalized.get("path") or []):
            normalized["robot"] = relative
            normalized["charging_base"] = {"x": 0.0, "y": 0.0, "angle": 0.0}

            if self.mapping_active and self.local_map:
                phase = int(self.mapping_phase or 0)
                previous = self._live_last_point.get(phase) if hasattr(self, "_live_last_point") else None
                current = (relative["x"], relative["y"], relative["angle"])
                if phase in (1, 2) and previous != current:
                    self._live_point_id[phase] = int(self._live_point_id.get(phase, 0)) + 1
                    self.local_map.merge_trajectory([{
                        "id": self._live_point_id[phase],
                        "x": relative["x"],
                        "y": relative["y"],
                        "phi": relative["angle"],
                        "update": 1,
                    }], phase=phase)
                    self._live_last_point[phase] = current

        result = super()._apply_map_state(normalized)

        if self.mapping_active and relative is not None and hasattr(self, "map_status_label"):
            try:
                probe = (state or {}).get("service10_probe") or {}
                changing = []
                names = probe.get("names") or {}
                for piid, count in sorted((probe.get("changes") or {}).items()):
                    try:
                        if int(count) > 0:
                            changing.append(f"10/{piid} {names.get(piid, names.get(str(piid), ''))} ×{count}".strip())
                    except Exception:
                        continue
                suffix = " · cambian: " + ", ".join(changing) if changing else " · sonda: esperando cambios"
                self.map_status_label.configure(
                    text=(
                        f"Posición LIVE · X {relative['x']:+.3f} m · Y {relative['y']:+.3f} m "
                        f"· φ {relative['angle']:.3f}{suffix}"
                    )
                )
            except Exception:
                pass
        return result

    def _diagnostic_text(self):
        text = super()._diagnostic_text()
        state = dict(getattr(self, "_last_map_state_debug", {}) or {})
        probe = state.get("service10_probe") or {}
        values = probe.get("values") or {}
        changes = probe.get("changes") or {}
        errors = probe.get("errors") or {}
        names = probe.get("names") or {}

        lines = [
            "",
            "SONDA SERVICIO MIoT 10",
            "---------------------------------------------",
        ]
        if not values and not errors:
            lines.append("sin muestras todavía")
        else:
            all_ids = sorted(set(values) | set(errors))
            for piid in all_ids:
                name = names.get(piid, names.get(str(piid), ""))
                if piid in values:
                    lines.append(
                        f"10/{piid} {name}: {values.get(piid)!r} · cambios={int(changes.get(piid, 0) or 0)}"
                    )
                else:
                    lines.append(f"10/{piid} {name}: error={errors.get(piid)}")
        return text + "\n" + "\n".join(lines)


if __name__ == "__main__":
    app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise
