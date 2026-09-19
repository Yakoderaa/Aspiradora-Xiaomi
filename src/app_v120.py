import threading
import time
from tkinter import messagebox

import app_v119
import app_v9


class App(app_v119.App):
    """V120: Mapear vivienda usa exploración Edge nativa, no limpieza global."""

    def __init__(self):
        self._v120_mapping_starts = 0
        self._v120_mapping_start_errors = 0
        self._v120_last_start_diag = {}
        super().__init__()

    def start_new_mapping(self):
        if not self.vacuum:
            messagebox.showwarning(
                "Robot desconectado",
                "Primero conectá el E10.",
                parent=self,
            )
            return
        if bool(getattr(self, "mapping_active", False)):
            messagebox.showinfo(
                "Mapeo en curso",
                "Primero detené el mapeo actual.",
                parent=self,
            )
            return

        ok = messagebox.askyesno(
            "Mapear vivienda",
            "Se va a borrar el mapa local seleccionado y comenzar un mapeo nuevo.\n\n"
            "V120 arma un mapa nuevo en el E10 y usa la exploración nativa de "
            "bordes para toda la vivienda, en ECO y con agua apagada. "
            "No inicia una limpieza global normal y no habrá una segunda fase "
            "automática.\n\n"
            "Dejá abiertas todas las puertas que quieras incluir y empezá con "
            "el robot acoplado a la base.",
            parent=self,
        )
        if not ok:
            return

        self._v74_reset_session()
        before = self._v71_debug_raw_pose()
        if before is not None:
            self._v71_set_origin(
                before,
                "10/24 antes de exploración vivienda V120",
            )

        self.local_map.clear_map(keep_rooms=False)
        self.selected_point = None
        self.mapping_active = True
        self.mapping_phase = 2
        self.mapping_seen_moving = False
        self.mapping_transitioning = False
        self.mapping_step1_complete = False
        self.mapping_step2_complete = False
        self.show_page("map")
        self._sync_mapping_step_buttons()
        self._render_maps()
        self._set_banner(
            "Mapeando vivienda · preparando exploración nativa de bordes…"
        )

        serial = self._v74_mapping_serial
        vacuum = self.vacuum
        self._v120_mapping_starts += 1
        self._v120_last_start_diag = {}

        def worker():
            try:
                build_diag = vacuum.arm_new_map(1)
                try:
                    vacuum.reset_live_path_session()
                except Exception:
                    pass
                vacuum.start_mapping_exploration(confirm_timeout=5.0)
                self._v120_last_start_diag = {
                    "build": dict(build_diag or {}),
                    "exploration": dict(
                        getattr(
                            vacuum,
                            "_last_mapping_exploration_diag",
                            {},
                        )
                        or {}
                    ),
                }
                self._post_ui("v74_mapping_started", serial)
            except Exception as exc:
                self._v120_mapping_start_errors += 1
                self._v120_last_start_diag = {
                    "build": dict(
                        getattr(vacuum, "last_map_build_diag", {}) or {}
                    ),
                    "exploration": dict(
                        getattr(
                            vacuum,
                            "_last_mapping_exploration_diag",
                            {},
                        )
                        or {}
                    ),
                    "error": str(exc).strip() or type(exc).__name__,
                }
                self._post_ui(
                    "v74_mapping_start_error",
                    serial,
                    str(exc).strip() or type(exc).__name__,
                )

        threading.Thread(
            target=worker,
            name="AspiradoraMapExploreV120",
            daemon=True,
        ).start()

    def _handle_ui_event(self, kind, payload):
        if kind == "v74_mapping_started":
            result = super()._handle_ui_event(kind, payload)
            if bool(getattr(self, "mapping_active", False)):
                self._set_banner(
                    "Mapeando vivienda · exploración de bordes activa · "
                    "esperando mapa Xiaomi final."
                )
            return result
        return super()._handle_ui_event(kind, payload)

    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        vacuum = getattr(self, "vacuum", None)
        device_diag = (
            dict(
                getattr(
                    vacuum,
                    "_last_mapping_exploration_diag",
                    {},
                )
                or {}
            )
            if vacuum is not None
            else {}
        )
        lines = [
            "DIAGNÓSTICO V120 ACTIVO · exploración de vivienda nativa",
            "========================================================",
            (
                f"inicios V120={self._v120_mapping_starts} · "
                f"errores={self._v120_mapping_start_errors}"
            ),
            f"start app={self._v120_last_start_diag or '—'}",
            f"exploración E10={device_diag or '—'}",
            "ruta V120: 10/17 build-map-ii(mode=1) -> ECO/agua=0 -> sweep-type=2 -> 7/3 ['', 2, 1]",
            "regla V120: Mapear vivienda NO llama start_mapping_interior ni start global 2/1/2/3",
            "regla V120: una sola orden de movimiento inicia la exploración; no hay segunda fase automática",
            "regla V120: la superficie live sigue descartada; la fidelidad se evalúa con la captura Xiaomi final en dock",
            "regla V120: V119 sigue impidiendo que corredor/no-new-area finalicen prematuramente la vivienda",
            "",
            "",
        ]
        return "\n".join(lines) + inherited


if __name__ == "__main__":
    app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        app_v9._save_crash_log(app_v9.traceback.format_exc())
        raise
