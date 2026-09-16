import os
import threading
import time
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

import app_v8

CARD = app_v8.CARD
MUTED = app_v8.MUTED


class App(app_v8.App):
    """v9: UI estable + pasos manuales + corte de transición borde->global."""

    def __init__(self):
        self._perimeter_watch_serial = 0
        super().__init__()

    def _build_map_page(self):
        # Importante: saltamos la implementación de app_v8 porque destruía un
        # botón y luego intentaba recorrer ese mismo widget ya destruido.
        app_v8.app_v7.App._build_map_page(self)

        page = self._pages.get("map")
        header_parent = None

        def walk(widget):
            nonlocal header_parent
            try:
                children = list(widget.winfo_children())
            except tk.TclError:
                return

            for child in children:
                removed = False
                if isinstance(child, tk.Button):
                    try:
                        text = child.cget("text")
                    except tk.TclError:
                        text = ""
                    if text in ("Crear desde cero", "Finalizar"):
                        header_parent = child.master
                        try:
                            child.destroy()
                        except tk.TclError:
                            pass
                        removed = True

                # Nunca intentamos inspeccionar un widget después de destruirlo.
                if not removed:
                    walk(child)

        if page:
            walk(page)

        if header_parent is None:
            return

        controls = tk.Frame(header_parent, bg=CARD)
        controls.pack(side="right")

        self.stop_mapping_button = self._button(
            controls,
            "Detener",
            self.finish_mapping,
            compact=True,
        )
        self.stop_mapping_button.pack(side="right", padx=(8, 0))

        self.step2_mapping_button = self._button(
            controls,
            "Paso 2 · Interior",
            self.start_interior_mapping,
            compact=True,
        )
        self.step2_mapping_button.pack(side="right", padx=(8, 0))

        self.step1_mapping_button = self._button(
            controls,
            "Paso 1 · Perímetro",
            self.start_new_mapping,
            accent=True,
            compact=True,
        )
        self.step1_mapping_button.pack(side="right")

        info_parent = self.map_status_label.master
        self.mapping_steps_info = tk.Label(
            info_parent,
            text="Paso 1: solo bordes · STOP automático · Paso 2: interior manual",
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 8),
        )
        self.mapping_steps_info.pack(side="left", padx=(12, 0))

    # ------------------------------------------------ watchdog de perímetro
    def start_new_mapping(self):
        # Conserva toda la lógica de app_v8 para iniciar edge=2.
        super().start_new_mapping()

        # Si el usuario canceló el diálogo no arrancamos el vigilante.
        if not self.mapping_active or self.mapping_phase != 1 or not self.vacuum:
            return

        self._perimeter_watch_serial += 1
        serial = self._perimeter_watch_serial
        threading.Thread(
            target=self._watch_perimeter_only,
            args=(serial,),
            daemon=True,
        ).start()

    def _watch_perimeter_only(self, serial):
        """Impide que el firmware continúe con un barrido global tras EDGE.

        El E10 puede terminar su pasada de borde y encadenar una limpieza global.
        Durante el Paso 1 observamos status (2/1) y sweep_type (2/8). Una vez que
        vimos EDGE=2, cualquier cambio a GLOBAL=0 mientras vuelve a moverse se
        corta inmediatamente con STOP (acción 2/2). También mandamos un STOP al
        detectar el fin del borde para cancelar una continuación programada por
        el firmware.
        """
        seen_edge = False
        seen_moving = False
        edge_finished_at = None
        errors = 0

        # 45 min máximo para una pasada de perímetro; después el hilo termina.
        deadline = time.monotonic() + 45 * 60

        while time.monotonic() < deadline and serial == self._perimeter_watch_serial:
            if not self.vacuum:
                return

            # Si el usuario arrancó explícitamente Paso 2, GLOBAL es intencional.
            if self.mapping_phase == 2:
                return

            try:
                values = self.vacuum._get_many([
                    ("status", 2, 1),
                    ("sweep_type", 2, 8),
                ])
                status = int(values.get("status", -1) if values.get("status") is not None else -1)
                sweep_type = int(values.get("sweep_type", -1) if values.get("sweep_type") is not None else -1)
                errors = 0
            except Exception:
                errors += 1
                if errors >= 12:
                    return
                time.sleep(0.45)
                continue

            moving = status in (5, 6, 7)
            finished = status in (0, 1, 2, 4)

            if sweep_type == 2:
                seen_edge = True
                if moving:
                    seen_moving = True

            # Caso principal: el firmware sale de EDGE y empieza GLOBAL por sí solo.
            if seen_edge and seen_moving and moving and sweep_type == 0:
                self._force_stop_after_perimeter(
                    "Paso 1 terminado · bloqueé el aspirado normal automático. Paso 2 queda esperando tu orden."
                )
                return

            # Cuando termina EDGE mandamos STOP preventivo aun estando en espera,
            # para cancelar la continuación global que algunos firmwares encadenan.
            if seen_edge and seen_moving and finished and edge_finished_at is None:
                edge_finished_at = time.monotonic()
                try:
                    self.vacuum.stop()
                except Exception:
                    pass
                self._mark_perimeter_complete(
                    "Paso 1 terminado · perímetro guardado. No iniciaré el interior automáticamente."
                )

            # Seguimos vigilando unos segundos después del fin por si el firmware
            # intenta arrancar GLOBAL con retraso. Si ocurre, volvemos a frenarlo.
            if edge_finished_at is not None:
                if moving and sweep_type != 2:
                    self._force_stop_after_perimeter(
                        "Paso 1 terminado · detuve la limpieza normal que intentó iniciar el E10."
                    )
                    return
                if time.monotonic() - edge_finished_at > 18:
                    return

            time.sleep(0.35)

    def _mark_perimeter_complete(self, banner):
        self.mapping_active = False
        self.mapping_phase = 0
        self.mapping_seen_moving = False
        self.mapping_transitioning = False
        self.mapping_step1_complete = self._has_perimeter_data()

        def ui():
            self._set_banner(banner)
            self._sync_mapping_step_buttons()
            self._render_maps()

        try:
            self.after(0, ui)
        except tk.TclError:
            pass

    def _force_stop_after_perimeter(self, banner):
        # Dos intentos cortos hacen el STOP más robusto si justo coincide con el
        # cambio de tarea interno del firmware.
        try:
            self.vacuum.stop()
        except Exception:
            pass
        time.sleep(0.45)
        try:
            values = self.vacuum._get_many([("status", 2, 1)])
            status = int(values.get("status", -1) if values.get("status") is not None else -1)
            if status in (5, 6, 7):
                self.vacuum.stop()
        except Exception:
            pass

        self._mark_perimeter_complete(banner)


def _save_crash_log(text: str):
    try:
        base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Aspiradora Xiaomi"
        base.mkdir(parents=True, exist_ok=True)
        (base / "crash.log").write_text(text, encoding="utf-8")
    except Exception:
        pass


if __name__ == "__main__":
    try:
        App().mainloop()
    except Exception:
        details = traceback.format_exc()
        _save_crash_log(details)
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "Aspiradora Xiaomi",
                "La aplicación encontró un error y guardó el detalle en:\n"
                "%LOCALAPPDATA%\\Aspiradora Xiaomi\\crash.log",
                parent=root,
            )
            root.destroy()
        except Exception:
            pass
