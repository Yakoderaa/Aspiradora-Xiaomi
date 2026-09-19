import threading
import time
import tkinter as tk
from tkinter import messagebox

import app_v115
import app_v9


class App(app_v115.App):
    """V116: botones de limpieza siempre enlazados al estado físico real."""

    CLEAN_LABELS = {
        "Iniciar limpieza",
        "Start cleaning",
        "Iniciar limpeza",
    }

    def __init__(self):
        self._v116_clean_clicks = 0
        self._v116_button_rebinds = 0
        self._v116_buttons_found = 0
        self._v116_stale_mapping_clears = 0
        self._v116_status_before_click = None
        self._v116_last_click_at = 0.0
        self._v116_last_click_stage = "—"
        self._v116_last_config_errors = []
        self._v116_last_optional_map = "—"
        super().__init__()

        # Tk conserva el objeto callback con el que se creó cada Button.
        # Reenlazamos explícitamente los botones visibles a V116 para eliminar
        # cualquier callback heredado/obsoleto.
        self.after_idle(self._v116_rebind_clean_buttons)
        self.after(700, self._v116_rebind_clean_buttons)
        self.after(2500, self._v116_rebind_clean_buttons)

    # ======================================================= botones / estado
    @staticmethod
    def _v116_mapping_flag_is_stale(mapping_active, physical_status):
        if not bool(mapping_active):
            return False
        try:
            status = int(physical_status)
        except Exception:
            return False
        return status in (0, 1, 3, 4)

    def _v116_walk_widgets(self, widget):
        yield widget
        try:
            children = widget.winfo_children()
        except Exception:
            children = []
        for child in children:
            yield from self._v116_walk_widgets(child)

    def _v116_is_clean_button(self, widget):
        try:
            if str(widget.winfo_class()) != "Button":
                return False
            text = str(widget.cget("text") or "").strip()
        except Exception:
            return False
        if text in self.CLEAN_LABELS:
            return True
        try:
            state = getattr(self, "_v99_text_state", {}).get(str(widget), {})
            source = str(state.get("source") or "").strip()
            return source == "Iniciar limpieza"
        except Exception:
            return False

    def _v116_known_clean_buttons(self):
        found = []
        for widget in (
            getattr(self, "_v95_clean_button", None),
            getattr(self, "clean_action_button", None),
        ):
            if widget is not None and widget not in found:
                found.append(widget)

        for widget in self._v116_walk_widgets(self):
            if widget in found:
                continue
            if self._v116_is_clean_button(widget):
                found.append(widget)
        return found

    def _v116_rebind_clean_buttons(self):
        connected = bool(getattr(self, "vacuum", None))
        busy = bool(getattr(self, "_v115_global_clean_active", False))
        buttons = self._v116_known_clean_buttons()
        self._v116_buttons_found = len(buttons)
        for button in buttons:
            try:
                button.configure(command=self.start_clean)
                if connected and not busy:
                    button.configure(state="normal")
                self._v116_button_rebinds += 1
            except Exception:
                pass
        return len(buttons)

    def _v116_set_all_clean_buttons(self, text=None, disabled=None):
        for button in self._v116_known_clean_buttons():
            try:
                if text is not None:
                    button.configure(text=str(text))
                if disabled is not None:
                    button.configure(
                        state="disabled" if disabled else "normal"
                    )
            except Exception:
                pass

    def _v95_sync_global_controls(self):
        """V116: una bandera vieja de mapeo no deshabilita el botón.

        Sólo se bloquea por desconexión, por una limpieza V116 activa o por
        mapeo físicamente activo (status 5/6/7 + mapping_active).
        """
        connected = bool(getattr(self, "vacuum", None))
        mapping_flag = bool(getattr(self, "mapping_active", False))
        status = getattr(self, "_v94_last_status_code", None)
        physically_mapping = False
        try:
            physically_mapping = mapping_flag and int(status) in (5, 6, 7)
        except Exception:
            physically_mapping = False

        busy = bool(getattr(self, "_v115_global_clean_active", False))
        enable_clean = connected and not busy and not physically_mapping

        for button in (
            getattr(self, "_v95_clean_button", None),
            getattr(self, "clean_action_button", None),
        ):
            if button is None:
                continue
            try:
                button.configure(
                    command=self.start_clean,
                    state="normal" if enable_clean else "disabled",
                )
            except Exception:
                pass

        dock = getattr(self, "_v95_dock_button", None)
        if dock is not None:
            try:
                dock.configure(
                    state=(
                        "normal"
                        if connected and status != 4
                        else "disabled"
                    )
                )
            except Exception:
                pass

    def _v116_clear_stale_mapping_state(self, physical_status):
        if not self._v116_mapping_flag_is_stale(
            getattr(self, "mapping_active", False),
            physical_status,
        ):
            return False

        self.mapping_active = False
        self.mapping_phase = 0
        self.mapping_transitioning = False
        if hasattr(self, "_auto_step2_pending"):
            self._auto_step2_pending = False
        if hasattr(self, "_auto_step2_scheduled"):
            self._auto_step2_scheduled = False
        if hasattr(self, "map_polling"):
            self.map_polling = False
        self._v116_stale_mapping_clears += 1
        self._v116_last_click_stage = "mapping_active obsoleto limpiado"
        try:
            self._sync_mapping_step_buttons()
        except Exception:
            pass
        return True

    # ====================================================== mapa opcional
    def _v116_optional_saved_grid(self):
        if not getattr(self, "local_map", None):
            self._v116_last_optional_map = "sin LocalMapStore"
            return None, None, None
        try:
            map_id = str(self.local_map.active_map_id or "")
            snapshot = self.local_map.snapshot()
            native = snapshot.get("native_grid")
        except Exception as exc:
            self._v116_last_optional_map = (
                str(exc).strip() or type(exc).__name__
            )
            return None, None, None

        if not map_id or not isinstance(native, dict):
            self._v116_last_optional_map = (
                "sin native_grid final; limpieza global permitida"
            )
            return None, None, None

        grid = dict(native)
        fp = self._v114_grid_fingerprint(grid)
        self._v116_last_optional_map = f"{map_id} · {fp or 'sin hash'}"
        return map_id, grid, fp

    def _v116_restore_optional_grid(self, map_id, grid, fp):
        if not map_id or not isinstance(grid, dict):
            return
        try:
            self._v114_restore_grid_if_needed(grid, fp, map_id)
        except Exception:
            pass

    # ======================================================= limpieza global
    def start_clean(self):
        # Este bloque ocurre ANTES de cualquier validación/red. Si el clic llegó,
        # F12 y el banner deben reflejarlo inmediatamente.
        self._v116_clean_clicks += 1
        self._v116_last_click_at = time.monotonic()
        self._v116_last_click_stage = "clic recibido"
        self._set_banner(
            f"Iniciar limpieza · clic recibido #{self._v116_clean_clicks}. "
            "Preparando el E10…"
        )

        if bool(getattr(self, "_v115_global_clean_active", False)):
            self._v116_last_click_stage = "ya hay limpieza global activa"
            self._set_banner("La limpieza global ya está en curso.")
            return

        if bool(getattr(self, "_v114_target_clean_active", False)):
            self._v116_last_click_stage = "bloqueado por limpieza dirigida"
            messagebox.showinfo(
                "Limpieza en curso",
                "Terminá la limpieza dirigida antes de iniciar una limpieza global.",
                parent=self,
            )
            return

        vacuum = getattr(self, "vacuum", None)
        if vacuum is None:
            self._v116_last_click_stage = "robot desconectado"
            messagebox.showwarning(
                "Robot desconectado",
                "Primero conectá el Xiaomi Vacuum E10.",
                parent=self,
            )
            return

        try:
            mode = self._selected_clean_mode()
        except Exception:
            mode = 0

        try:
            suction = int(self.suction_var.get())
        except Exception:
            suction = int(self.settings.get("suction", 2) or 2)
        try:
            water = int(self.water_var.get())
        except Exception:
            water = int(self.settings.get("mop_water_level", 1) or 1)

        suction = max(1, min(4, suction))
        water = max(0, min(3, water))

        # El mapa local es una protección, NO un requisito para que una
        # limpieza global pueda arrancar.
        map_id, original_grid, original_fp = self._v116_optional_saved_grid()
        self._v115_global_map_fp_before = original_fp
        self._v115_global_map_fp_after = original_fp

        self._v115_global_clean_active = True
        self._v115_global_clean_starts += 1
        self._v115_last_global_error = "—"
        self._v115_last_global_diag = {}
        self._v116_last_config_errors = []
        self._v116_last_click_stage = "worker lanzado"
        self._v116_set_all_clean_buttons("Iniciando…", True)

        def worker():
            guard_started = False
            confirmed = False
            try:
                try:
                    physical_before = int(vacuum._value(2, 1))
                except Exception:
                    physical_before = int(vacuum.status().status)
                self._v116_status_before_click = physical_before

                # La captura del usuario muestra status=4. Si quedó
                # mapping_active=True de la sesión anterior, esa bandera es
                # obsoleta y se descarta: el estado físico manda.
                if self._v116_mapping_flag_is_stale(
                    getattr(self, "mapping_active", False),
                    physical_before,
                ):
                    self.after(
                        0,
                        lambda s=physical_before:
                        self._v116_clear_stale_mapping_state(s),
                    )

                vacuum.begin_targeted_clean()
                guard_started = True

                # Succión/agua no pueden impedir el START. Si el firmware
                # rechaza una preferencia, registramos el error y seguimos.
                try:
                    vacuum.set_suction(suction)
                except Exception as exc:
                    self._v116_last_config_errors.append(
                        "succión: " + (str(exc).strip() or type(exc).__name__)
                    )
                try:
                    vacuum.set_water(water)
                except Exception as exc:
                    self._v116_last_config_errors.append(
                        "agua: " + (str(exc).strip() or type(exc).__name__)
                    )

                self._v116_last_click_stage = "enviando START verificado"
                diag = vacuum.start_global_verified(
                    mode,
                    confirm_timeout=3.0,
                )
                self._v115_last_global_diag = dict(diag or {})
                confirmed = bool(diag and diag.get("success"))
                if not confirmed:
                    raise RuntimeError(
                        "El E10 no confirmó el inicio de la limpieza."
                    )

                self._v115_global_clean_confirmed += 1
                self._v116_last_click_stage = "movimiento confirmado"
                method = str(diag.get("method") or "—")
                status = diag.get("status_after", "—")
                self.after(
                    0,
                    lambda m=method, s=status: self._set_banner(
                        f"Limpieza iniciada · movimiento confirmado · "
                        f"ruta={m} · estado={s}."
                    ),
                )
                self.after(
                    0,
                    lambda: self._v116_set_all_clean_buttons(
                        "Limpiando…",
                        True,
                    ),
                )

                inactive_samples = 0
                started_at = time.monotonic()
                while time.monotonic() - started_at < 12 * 60 * 60:
                    self._v116_restore_optional_grid(
                        map_id,
                        original_grid,
                        original_fp,
                    )
                    try:
                        current = int(vacuum.status().status)
                    except Exception:
                        time.sleep(2.0)
                        continue

                    if current in (2, 3, 5, 6, 7):
                        inactive_samples = 0
                    else:
                        inactive_samples += 1
                        if inactive_samples >= 2:
                            break
                    time.sleep(2.0)

            except Exception as exc:
                self._v115_global_clean_errors += 1
                self._v115_last_global_error = (
                    str(exc).strip() or type(exc).__name__
                )
                self._v116_last_click_stage = "error: " + self._v115_last_global_error
                self.after(
                    0,
                    lambda msg=self._v115_last_global_error:
                    self._set_banner("No se pudo iniciar la limpieza: " + msg),
                )
                self.after(
                    0,
                    lambda msg=self._v115_last_global_error:
                    messagebox.showerror(
                        "Iniciar limpieza",
                        msg,
                        parent=self,
                    ),
                )
            finally:
                self._v116_restore_optional_grid(
                    map_id,
                    original_grid,
                    original_fp,
                )
                if guard_started:
                    try:
                        vacuum.end_targeted_clean()
                    except Exception:
                        pass
                self._v115_global_clean_active = False
                self.after(
                    0,
                    lambda: self._v116_set_all_clean_buttons(
                        "Iniciar limpieza",
                        False,
                    ),
                )
                self.after(50, self._v95_sync_global_controls)
                if confirmed:
                    self._v116_last_click_stage = "sesión finalizada"
                    self.after(
                        0,
                        lambda: self._set_banner(
                            "Limpieza finalizada/retorno detectado. "
                            "El mapa guardado no fue reemplazado."
                        ),
                    )

        threading.Thread(
            target=worker,
            name="AspiradoraGlobalCleanV116",
            daemon=True,
        ).start()

    # =========================================================== diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        try:
            top_state = getattr(
                self._v95_clean_button,
                "cget",
                lambda _x: "—",
            )("state")
        except Exception:
            top_state = "—"
        try:
            quick_state = getattr(
                self.clean_action_button,
                "cget",
                lambda _x: "—",
            )("state")
        except Exception:
            quick_state = "—"

        lines = [
            "DIAGNÓSTICO V116 ACTIVO · botones + estado físico",
            "==================================================",
            (
                f"clics recibidos={self._v116_clean_clicks} · "
                f"etapa={self._v116_last_click_stage} · "
                f"status antes={self._v116_status_before_click}"
            ),
            (
                f"botones detectados={self._v116_buttons_found} · "
                f"reenlaces={self._v116_button_rebinds} · "
                f"top state={top_state} · quick state={quick_state}"
            ),
            (
                f"mapping_active={bool(getattr(self, 'mapping_active', False))} · "
                f"mapping_phase={getattr(self, 'mapping_phase', '—')} · "
                f"flags obsoletos limpiados={self._v116_stale_mapping_clears}"
            ),
            f"mapa opcional={self._v116_last_optional_map}",
            (
                "errores de preferencias antes del START="
                f"{self._v116_last_config_errors or '—'}"
            ),
            "regla V116: un status físico 0/1/3/4 invalida un mapping_active residual para el botón de limpieza",
            "regla V116: todos los botones Iniciar limpieza se reenlazan explícitamente a App.start_clean V116",
            "regla V116: el clic se registra antes de cualquier lectura de red o validación de mapa",
            "regla V116: la limpieza global no exige native_grid; si existe, se protege sin convertirlo en un bloqueo",
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
