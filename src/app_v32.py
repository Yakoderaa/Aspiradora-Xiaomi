import app_v31


class App(app_v31.App):
    """v32: la base 10/22 es el origen real + Diagnóstico con estilo normal."""

    def _install_global_diagnostics_access(self):
        """Mismo componente y estilo que el botón Buscar actualizaciones."""
        parent = self.connection_label.master
        self.global_map_diag_button = self._button(
            parent,
            "Diagnóstico",
            self._open_map_diagnostics,
            compact=True,
        )
        self.global_map_diag_button.pack(side="left", padx=(8, 0))

    def start_new_mapping(self):
        # Las versiones anteriores podían conservar como origen la primera pose
        # del robot. En el E10 del usuario 10/24=59_60 mientras 10/22=60_60;
        # tomar 59_60 como origen convertía una posición real en X=0/Y=0.
        try:
            self._coord_origins.pop("robot", None)
            self._coord_prev_local.pop("robot", None)
            self._coord_last_change.pop("robot", None)
        except Exception:
            pass
        return super().start_new_mapping()

    def _coordinate_candidates(self, state):
        """Usa chargingbase 10/22 como origen de robot-location 10/24.

        El firmware B112 puede no entregar una trayectoria útil en 10/5 (en la
        unidad diagnosticada devuelve literalmente 'hello'), pero sí entrega
        robot-location y chargingbase. Esas dos coordenadas comparten referencia,
        por lo que su diferencia es una posición local válida.
        """
        result = super()._coordinate_candidates(state)
        if not isinstance(state, dict):
            return result

        robot = self._pose_from_dict(state.get("robot"))
        if not robot:
            return result

        base = self._pose_from_dict(state.get("charging_base"))
        if base:
            origin_hint = base
        elif getattr(self, "_charging_confirmed", False):
            origin_hint = robot
        else:
            # Sin 10/22 no inventamos un origen nuevo. El código heredado puede
            # conservar uno ya calibrado; de lo contrario esperará una referencia.
            origin_hint = None

        result["robot"] = (robot, origin_hint)
        return result

    def _diagnostic_text(self):
        base_text = super()._diagnostic_text()
        state = dict(getattr(self, "_last_map_state_debug", {}) or {})
        raw_robot = state.get("raw_robot")
        raw_base = state.get("raw_base")
        delta_text = "—"
        try:
            parser = getattr(self.vacuum, "parse_position", None)
            robot = parser(raw_robot) if callable(parser) else None
            base = parser(raw_base) if callable(parser) else None
            if robot and base:
                dx = float(robot["x"]) - float(base["x"])
                dy = float(robot["y"]) - float(base["y"])
                delta_text = f"X {dx:+.6f} · Y {dy:+.6f}"
        except Exception:
            pass

        return (
            "DIAGNÓSTICO V32 ACTIVO · F12\n"
            "=============================================\n"
            f"delta 10/24 - 10/22: {delta_text}\n"
            "origen visual: chargingbase 10/22 cuando está disponible\n\n"
            + base_text
        )


if __name__ == "__main__":
    app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise
