import os
import queue
import threading
import time
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

import app_v8
from updater import check_for_update, download_and_install
from version import VERSION
from xiaomi_e10 import XiaomiE10

CARD = app_v8.CARD
MUTED = app_v8.MUTED
RED = app_v8.RED


class App(app_v8.App):
    """UI estable: Tk solo se toca desde el hilo principal."""

    def __init__(self):
        self._perimeter_watch_serial = 0
        self._ui_events = queue.Queue()
        self._closing = False
        self._status_worker_running = False
        self._map_worker_running = False
        self._saved_connect_scheduled = False
        super().__init__()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.after(50, self._drain_ui_events)

    # ----------------------------------------------------------- puente UI
    def _post_ui(self, kind, *payload):
        if not self._closing:
            self._ui_events.put((kind, payload))

    def _drain_ui_events(self):
        if self._closing:
            return
        try:
            while True:
                kind, payload = self._ui_events.get_nowait()
                self._handle_ui_event(kind, payload)
        except queue.Empty:
            pass
        except Exception:
            _save_crash_log(traceback.format_exc())
        if not self._closing:
            self.after(60, self._drain_ui_events)

    def _handle_ui_event(self, kind, payload):
        if kind == "banner":
            self._set_banner(str(payload[0]))
        elif kind == "connect_ok":
            vacuum, ip = payload
            self.vacuum = vacuum
            self.settings["ip"] = ip
            self.settings["token"] = vacuum.token
            self.store.save(self.settings)
            self._on_connected(ip)
        elif kind == "connect_error":
            message, quiet = payload
            self.vacuum = None
            self._set_connection(False)
            self._set_banner("No se pudo conectar. Revisá que el robot siga conectado al mismo router.")
            if not quiet:
                messagebox.showerror("No se pudo conectar", message, parent=self)
        elif kind == "status_ok":
            self._status_worker_running = False
            status = payload[0]
            try:
                self._render_status(status)
            except Exception:
                _save_crash_log(traceback.format_exc())
            self._schedule_next_status_poll()
        elif kind == "status_error":
            self._status_worker_running = False
            self._set_banner(f"Robot sin respuesta: {payload[0]}")
            self._schedule_next_status_poll()
        elif kind == "map_ok":
            self._map_worker_running = False
            self._apply_map_state(payload[0])
            self._schedule_next_map_poll()
        elif kind == "map_error":
            self._map_worker_running = False
            if hasattr(self, "map_status_label"):
                self.map_status_label.configure(text=f"Telemetría de mapa: {str(payload[0])[:90]}", fg=RED)
            self._schedule_next_map_poll()
        elif kind == "perimeter_started":
            self._set_banner("Paso 1 · recorriendo bordes y paredes en tiempo real…")
            self._perimeter_watch_serial += 1
            serial = self._perimeter_watch_serial
            threading.Thread(target=self._watch_perimeter_only, args=(serial,), daemon=True).start()
        elif kind == "mapping_error":
            title, message = payload
            self.mapping_active = False
            self.mapping_phase = 0
            self.mapping_transitioning = False
            self._sync_mapping_step_buttons()
            self._render_maps()
            messagebox.showerror(title, message, parent=self)
        elif kind == "perimeter_complete":
            banner = payload[0]
            self.mapping_active = False
            self.mapping_phase = 0
            self.mapping_seen_moving = False
            self.mapping_transitioning = False
            self.mapping_step1_complete = self._has_perimeter_data()
            self._set_banner(banner)
            self._sync_mapping_step_buttons()
            self._render_maps()
        elif kind == "update_checked":
            update = payload[0]
            if not update:
                self._manual_no_update()
            else:
                self._manual_update_found_safe(update)
        elif kind == "update_error":
            self._manual_update_error(str(payload[0]))
        elif kind == "update_install_done":
            self.destroy()

    # --------------------------------------------- inicio y conexión seguros
    def _schedule_update_check(self):
        # No cerramos ni reemplazamos la app automáticamente al abrir.
        # Las actualizaciones se hacen solo con el botón visible.
        self.updating = False

    def _connect_from_saved(self):
        # app_v2 llama esto a los 400 ms. Damos tiempo a terminar de montar toda
        # la interfaz antes de empezar red/MIoT.
        if self._saved_connect_scheduled:
            return
        self._saved_connect_scheduled = True
        self.after(1200, self._connect_saved_now)

    def _connect_saved_now(self):
        if self._closing:
            return
        ip = self.settings.get("ip")
        token = self.settings.get("token")
        if ip and token:
            self.connect_device(ip, token, quiet=True)
        else:
            self._set_banner("Configurá el robot. La opción recomendada es vincular tu cuenta Xiaomi mediante QR.")

    def connect_device(self, ip, token, quiet=False):
        self._set_banner("Conectando con el robot…")
        ip = str(ip).strip()
        token = str(token).strip()

        def worker():
            try:
                vacuum = XiaomiE10(ip, token)
                info = vacuum.info()
                model = getattr(info, "model", "")
                if model and model != "xiaomi.vacuum.b112":
                    raise RuntimeError(f"El dispositivo respondió como {model}, no como Xiaomi Vacuum E10.")
                vacuum.status()
                self._post_ui("connect_ok", vacuum, ip)
            except Exception as exc:
                self._post_ui("connect_error", str(exc).strip() or "El robot no respondió correctamente.", quiet)

        threading.Thread(target=worker, daemon=True).start()

    def _on_connected(self, ip):
        self._set_connection(True, f"Conectado · {ip}")
        self._set_banner("Control local activo. PC y robot se comunican por tu router.")
        self._start_polling()
        self.after(1500, self._start_local_map_polling)

    # --------------------------------------------------------- estado seguro
    def _start_polling(self):
        if self.polling:
            return
        self.polling = True
        self.after(100, self._poll_status)

    def _poll_status(self):
        if self._closing or not self.vacuum:
            self.polling = False
            return
        if self._status_worker_running:
            return
        self._status_worker_running = True
        vacuum = self.vacuum

        def worker():
            try:
                self._post_ui("status_ok", vacuum.status())
            except Exception as exc:
                self._post_ui("status_error", str(exc).strip() or "Sin respuesta")

        threading.Thread(target=worker, daemon=True).start()

    def _schedule_next_status_poll(self):
        if self._closing or not self.vacuum:
            self.polling = False
            return
        delay = max(2, int(self.settings.get("poll_seconds", 5) or 5)) * 1000
        self.after(delay, self._poll_status)

    # ----------------------------------------------------------- mapa seguro
    def _start_local_map_polling(self):
        if self._closing or not self.vacuum:
            return
        if self.map_polling:
            return
        self.map_polling = True
        self.after(100, self._poll_local_map)

    def _poll_local_map(self):
        if self._closing or not self.vacuum:
            self.map_polling = False
            return
        if self._map_worker_running:
            return
        self._map_worker_running = True
        vacuum = self.vacuum

        def worker():
            try:
                self._post_ui("map_ok", vacuum.local_map_state())
            except Exception as exc:
                self._post_ui("map_error", str(exc).strip() or "Sin telemetría")

        threading.Thread(target=worker, daemon=True).start()

    def _apply_map_state(self, state):
        if not self.local_map:
            return
        path = state.get("path") or []
        if self.mapping_active and path and not (
            self.mapping_phase == 2 and self.mapping_transitioning
        ):
            self.local_map.merge_trajectory(path, phase=self.mapping_phase)
        self.local_map.set_robot(state.get("robot"))
        self.local_map.set_charging_base(state.get("charging_base"))
        if hasattr(self, "map_last_update"):
            self.map_last_update = time.time()
        self._render_maps()

    def _schedule_next_map_poll(self):
        if self._closing or not self.vacuum:
            self.map_polling = False
            return
        delay = 700 if self.mapping_active else 2200
        self.after(delay, self._poll_local_map)

    # ------------------------------------------------------------ UI mapeo
    def _build_map_page(self):
        # Saltamos la implementación problemática de app_v8 y partimos de la
        # pantalla estable anterior.
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
                if not removed:
                    walk(child)

        if page:
            walk(page)
        if header_parent is None:
            return

        controls = tk.Frame(header_parent, bg=CARD)
        controls.pack(side="right")
        self.stop_mapping_button = self._button(controls, "Detener", self.finish_mapping, compact=True)
        self.stop_mapping_button.pack(side="right", padx=(8, 0))
        self.step2_mapping_button = self._button(controls, "Paso 2 · Interior", self.start_interior_mapping, compact=True)
        self.step2_mapping_button.pack(side="right", padx=(8, 0))
        self.step1_mapping_button = self._button(controls, "Paso 1 · Perímetro", self.start_new_mapping, accent=True, compact=True)
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

    def start_new_mapping(self):
        if not self.vacuum:
            messagebox.showwarning("Robot desconectado", "Primero conectá el E10.", parent=self)
            return
        if self.mapping_active:
            messagebox.showinfo("Mapeo en curso", "Primero detené el paso actual.", parent=self)
            return
        ok = messagebox.askyesno(
            "Paso 1 · Perímetro",
            "Se va a borrar el mapa local guardado por esta aplicación y empezar desde cero.\n\n"
            "Voy a mandar al E10 el comando real de recorrido de BORDE/PERÍMETRO (edge = 2). "
            "Al terminar, la app enviará STOP para impedir que siga con una limpieza normal.\n\n"
            "El Paso 2 NO arrancará solo.",
            parent=self,
        )
        if not ok:
            return

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
        self._set_banner("Paso 1 · enviando comando EDGE al E10…")
        vacuum = self.vacuum

        def worker():
            try:
                vacuum.start_mapping_perimeter()
                self._post_ui("perimeter_started")
            except Exception as exc:
                self._post_ui("mapping_error", "No se pudo iniciar el perímetro", str(exc).strip() or "El E10 rechazó el modo de borde/perímetro.")

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------ watchdog de perímetro
    def _watch_perimeter_only(self, serial):
        seen_edge = False
        seen_moving = False
        edge_finished_at = None
        errors = 0
        deadline = time.monotonic() + 45 * 60

        while time.monotonic() < deadline and serial == self._perimeter_watch_serial:
            vacuum = self.vacuum
            if not vacuum or self.mapping_phase == 2:
                return
            try:
                values = vacuum._get_many([
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

            if seen_edge and seen_moving and moving and sweep_type == 0:
                self._force_stop_after_perimeter(
                    "Paso 1 terminado · bloqueé el aspirado normal automático. Paso 2 queda esperando tu orden."
                )
                return

            if seen_edge and seen_moving and finished and edge_finished_at is None:
                edge_finished_at = time.monotonic()
                try:
                    vacuum.stop()
                except Exception:
                    pass
                self._post_ui(
                    "perimeter_complete",
                    "Paso 1 terminado · perímetro guardado. No iniciaré el interior automáticamente.",
                )

            if edge_finished_at is not None:
                if moving and sweep_type != 2:
                    self._force_stop_after_perimeter(
                        "Paso 1 terminado · detuve la limpieza normal que intentó iniciar el E10."
                    )
                    return
                if time.monotonic() - edge_finished_at > 18:
                    return
            time.sleep(0.35)

    def _force_stop_after_perimeter(self, banner):
        vacuum = self.vacuum
        if not vacuum:
            return
        try:
            vacuum.stop()
        except Exception:
            pass
        time.sleep(0.45)
        try:
            values = vacuum._get_many([("status", 2, 1)])
            status = int(values.get("status", -1) if values.get("status") is not None else -1)
            if status in (5, 6, 7):
                vacuum.stop()
        except Exception:
            pass
        self._post_ui("perimeter_complete", banner)

    # --------------------------------------------------- actualización manual
    def manual_check_for_updates(self):
        if self.updating:
            messagebox.showinfo("Actualizaciones", "Ya estoy comprobando o instalando una actualización.", parent=self)
            return
        self.updating = True
        self.manual_update_button.configure(text="Buscando…", state="disabled")
        self._set_banner("Buscando actualizaciones en GitHub…")

        def worker():
            try:
                self._post_ui("update_checked", check_for_update())
            except Exception as exc:
                self._post_ui("update_error", str(exc).strip() or "No se pudo consultar GitHub.")

        threading.Thread(target=worker, daemon=True).start()

    def _manual_update_found_safe(self, update):
        version = update.get("version", "nueva")
        self._set_banner(f"Actualización v{version} disponible.")
        if not messagebox.askyesno(
            "Actualización disponible",
            f"Hay una nueva versión: v{version}.\n\n¿Querés descargarla e instalarla ahora?",
            parent=self,
        ):
            self._set_manual_update_idle()
            return
        self.manual_update_button.configure(text="Descargando…", state="disabled")

        def worker():
            try:
                download_and_install(update, lambda text: self._post_ui("banner", text))
                self._post_ui("update_install_done")
            except Exception as exc:
                self._post_ui("update_error", str(exc).strip() or "No se pudo instalar la actualización.")

        threading.Thread(target=worker, daemon=True).start()

    def destroy(self):
        self._closing = True
        self.polling = False
        self.map_polling = False
        self._perimeter_watch_serial += 1
        try:
            super().destroy()
        except tk.TclError:
            pass


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
