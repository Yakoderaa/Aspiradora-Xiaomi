import os
import threading
import time
from pathlib import Path
from tkinter import messagebox

import app_v10
from xiaomi_e10_edge import XiaomiE10Edge


class App(app_v10.App):
    """v11: Paso 1 de mapeo rehecho desde cero y exclusivamente EDGE."""

    def __init__(self):
        self._edge_session = 0
        super().__init__()

    # ------------------------------------------------------- diagnóstico EDGE
    @staticmethod
    def _edge_log(message: str):
        try:
            folder = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Aspiradora Xiaomi"
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / "mapping_edge.log"
            stamp = time.strftime("%Y-%m-%d %H:%M:%S")
            with path.open("a", encoding="utf-8") as fh:
                fh.write(f"[{stamp}] {message}\n")
        except Exception:
            pass

    # -------------------------------------------- conexión con clase EDGE nueva
    def connect_device(self, ip, token, quiet=False):
        self._set_banner("Conectando con el robot…")
        ip = str(ip).strip()
        token = str(token).strip()

        def worker():
            try:
                vacuum = XiaomiE10Edge(ip, token)
                info = vacuum.info()
                model = getattr(info, "model", "")
                if model and model != "xiaomi.vacuum.b112":
                    raise RuntimeError(f"El dispositivo respondió como {model}, no como Xiaomi Vacuum E10.")
                vacuum.status()
                self._post_ui("connect_ok", vacuum, ip)
            except Exception as exc:
                self._post_ui(
                    "connect_error",
                    str(exc).strip() or "El robot no respondió correctamente.",
                    quiet,
                )

        threading.Thread(target=worker, daemon=True).start()

    # ---------------------------------------------------------- eventos EDGE
    def _handle_ui_event(self, kind, payload):
        if kind == "edge_only_started":
            session = int(payload[0])
            self._set_banner("Paso 1 · EDGE activo: recorriendo únicamente bordes y paredes…")
            self._edge_log(f"EDGE iniciado. sesión={session}")
            threading.Thread(
                target=self._watch_edge_only,
                args=(session,),
                daemon=True,
            ).start()
            return

        if kind == "edge_only_complete":
            banner = str(payload[0])
            self.mapping_active = False
            self.mapping_phase = 0
            self.mapping_seen_moving = False
            self.mapping_transitioning = False
            self.mapping_step1_complete = self._has_perimeter_data()
            self._set_banner(banner)
            self._sync_mapping_step_buttons()
            self._render_maps()
            return

        if kind == "edge_only_error":
            message = str(payload[0])
            self.mapping_active = False
            self.mapping_phase = 0
            self.mapping_seen_moving = False
            self.mapping_transitioning = False
            self._sync_mapping_step_buttons()
            self._render_maps()
            self._set_banner("Paso 1 cancelado para evitar una limpieza global.")
            messagebox.showerror("Mapeo por bordes", message, parent=self)
            return

        return super()._handle_ui_event(kind, payload)

    # ------------------------------------------------ Paso 1 desde cero EDGE
    def start_new_mapping(self):
        if not self.vacuum:
            messagebox.showwarning("Robot desconectado", "Primero conectá el E10.", parent=self)
            return
        if self.mapping_active:
            messagebox.showinfo("Mapeo en curso", "Primero detené el paso actual.", parent=self)
            return

        ok = messagebox.askyesno(
            "Paso 1 · Solo bordes",
            "Se va a borrar el mapa local de esta aplicación y comenzar un recorrido nuevo.\n\n"
            "Este Paso 1 usa un controlador nuevo: SOLO EDGE/BORDE. No usa limpieza por habitaciones, "
            "no usa limpieza global y no inicia el Paso 2 automáticamente.\n\n"
            "Si el firmware intenta cambiar a limpieza global, la app lo detendrá inmediatamente.",
            parent=self,
        )
        if not ok:
            return

        self._edge_session += 1
        session = self._edge_session
        self.local_map.clear_map(keep_rooms=False)
        self.selected_point = None
        self.mapping_active = True
        self.mapping_phase = 1
        self.mapping_seen_moving = False
        self.mapping_transitioning = False
        self.mapping_step1_complete = False
        self.mapping_step2_complete = False
        self.show_page("map")
        self._sync_mapping_step_buttons()
        self._render_maps()
        self._set_banner("Paso 1 · configurando EDGE=2 y Start Only Sweep…")
        self._edge_log(f"Solicitando EDGE. sesión={session}")
        vacuum = self.vacuum

        def worker():
            try:
                vacuum.start_mapping_perimeter()
                self._post_ui("edge_only_started", session)
            except Exception as exc:
                self._edge_log(f"Error al iniciar EDGE: {exc}")
                self._post_ui(
                    "edge_only_error",
                    str(exc).strip() or "El E10 rechazó el recorrido exclusivo de borde.",
                )

        threading.Thread(target=worker, daemon=True).start()

    def _watch_edge_only(self, session):
        """Vigila EDGE sin reutilizar el watchdog del mapeo anterior.

        En cuanto sweep-type deje de ser 2, enviamos STOP. No esperamos a que
        el robot empiece a desplazarse en modo global.
        """
        vacuum = self.vacuum
        if not vacuum:
            return

        started_at = time.monotonic()
        deadline = started_at + 45 * 60
        seen_edge = False
        seen_moving = False
        errors = 0
        last_state = None

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
                status = int(values.get("status", -1) if values.get("status") is not None else -1)
                sweep_type = int(values.get("sweep_type", -1) if values.get("sweep_type") is not None else -1)
                errors = 0
            except Exception as exc:
                errors += 1
                if errors >= 12:
                    self._edge_log(f"Telemetría EDGE perdida: {exc}")
                    self._post_ui(
                        "edge_only_error",
                        "Perdí la comunicación mientras vigilaba el modo EDGE. Detuve el Paso 1 por seguridad.",
                    )
                    try:
                        vacuum.stop()
                    except Exception:
                        pass
                    return
                time.sleep(0.25)
                continue

            state = (status, sweep_type)
            if state != last_state:
                self._edge_log(f"status={status} sweep_type={sweep_type}")
                last_state = state

            if sweep_type == 2:
                seen_edge = True

            if status in (5, 6, 7):
                seen_moving = True

            # Regla principal: una vez confirmado EDGE, cualquier salida de 2
            # se corta ANTES de aceptar otra fase de limpieza.
            if seen_edge and sweep_type != 2:
                self._edge_log(
                    f"Firmware intentó salir de EDGE: status={status}, sweep_type={sweep_type}. STOP inmediato."
                )
                try:
                    vacuum.stop()
                except Exception:
                    pass
                self._post_ui(
                    "edge_only_complete",
                    "Paso 1 terminado · perímetro guardado. Bloqueé la transición automática a limpieza global.",
                )
                return

            # Fin normal del recorrido de borde.
            if seen_edge and seen_moving and status in (0, 1, 2, 4):
                self._edge_log(f"EDGE finalizado normalmente con status={status}")
                self._post_ui(
                    "edge_only_complete",
                    "Paso 1 terminado · recorrido de bordes guardado. Paso 2 queda esperando tu orden.",
                )
                return

            # Si nunca llegó a entrar a EDGE/movimiento, no dejamos que una
            # tarea distinta siga corriendo silenciosamente.
            if time.monotonic() - started_at > 8.0 and not seen_edge:
                try:
                    vacuum.stop()
                except Exception:
                    pass
                self._edge_log(f"EDGE no confirmado. status={status}, sweep_type={sweep_type}")
                self._post_ui(
                    "edge_only_error",
                    f"El E10 no confirmó el modo de bordes (sweep_type={sweep_type}). "
                    "Cancelé la tarea para que no aspire toda la vivienda.",
                )
                return

            time.sleep(0.25)

        try:
            vacuum.stop()
        except Exception:
            pass
        self._post_ui("edge_only_error", "El Paso 1 superó el tiempo máximo y fue detenido.")


if __name__ == "__main__":
    app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise
