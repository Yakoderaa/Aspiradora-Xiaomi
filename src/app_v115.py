import threading
import time
from tkinter import messagebox

import app_v114
import app_v9


class App(app_v114.App):
    """V115: inicio global confirmado físicamente + mapa Xiaomi inmutable."""

    def __init__(self):
        self._v115_global_clean_active = False
        self._v115_global_clean_starts = 0
        self._v115_global_clean_confirmed = 0
        self._v115_global_clean_errors = 0
        self._v115_last_global_error = "—"
        self._v115_last_global_diag = {}
        self._v115_live_grid_updates_blocked = 0
        self._v115_mapping_ui_blocks = 0
        self._v115_global_map_fp_before = None
        self._v115_global_map_fp_after = None
        self._v115_clean_button_original_text = None
        super().__init__()

    def _v115_saved_map_context(self):
        if not self.local_map:
            raise RuntimeError("No hay un mapa activo.")
        snapshot = self.local_map.snapshot()
        native = snapshot.get("native_grid")
        if not isinstance(native, dict):
            raise RuntimeError(
                "Este mapa todavía no tiene una planta Xiaomi final. "
                "Terminá un mapeo completo antes de iniciar la limpieza."
            )
        map_id = str(self.local_map.active_map_id or "")
        if not map_id:
            raise RuntimeError("No pude identificar el mapa Xiaomi activo.")
        return map_id, snapshot, dict(native)

    def _v115_set_clean_button_busy(self, busy, text=None):
        button = getattr(self, "_v95_clean_button", None)
        if button is None:
            return
        try:
            if self._v115_clean_button_original_text is None:
                self._v115_clean_button_original_text = button.cget("text")
            if busy:
                button.configure(state="disabled", text=text or "Iniciando…")
            else:
                button.configure(
                    state="normal",
                    text=self._v115_clean_button_original_text
                    or "Iniciar limpieza",
                )
                try:
                    self._v95_sync_global_controls()
                except Exception:
                    pass
        except Exception:
            pass

    def _v114_cleaning_busy(self):
        if bool(self._v115_global_clean_active):
            self._v115_mapping_ui_blocks += 1
            messagebox.showinfo(
                "Limpieza en curso",
                "La limpieza global está usando el mapa Xiaomi guardado. "
                "Esperá a que termine o enviá el robot a la base antes de "
                "mapear, cambiar o eliminar el mapa.",
                parent=self,
            )
            return True
        return super()._v114_cleaning_busy()

    def _v88_prepare_live_grid(self, snapshot):
        if bool(self._v115_global_clean_active):
            self._v115_live_grid_updates_blocked += 1
            return None
        return super()._v88_prepare_live_grid(snapshot)

    def start_clean(self):
        if bool(getattr(self, "mapping_active", False)):
            messagebox.showinfo(
                "Mapeo en curso",
                "Terminá o detené el mapeo antes de iniciar una limpieza normal.",
                parent=self,
            )
            return
        if bool(self._v115_global_clean_active):
            self._set_banner("La limpieza global ya está en curso.")
            return
        if bool(getattr(self, "_v114_target_clean_active", False)):
            messagebox.showinfo(
                "Limpieza en curso",
                "Terminá la limpieza dirigida antes de iniciar una limpieza global.",
                parent=self,
            )
            return
        if not getattr(self, "vacuum", None):
            messagebox.showwarning(
                "Robot desconectado",
                "Primero conectá el Xiaomi Vacuum E10.",
                parent=self,
            )
            return

        try:
            map_id, _snapshot, native = self._v115_saved_map_context()
        except Exception as exc:
            messagebox.showerror(
                "Iniciar limpieza",
                str(exc).strip() or type(exc).__name__,
                parent=self,
            )
            return

        mode = self._selected_clean_mode()
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

        original_grid = dict(native)
        original_fp = self._v114_grid_fingerprint(original_grid)
        self._v115_global_map_fp_before = original_fp
        self._v115_global_map_fp_after = original_fp
        self._v115_global_clean_active = True
        self._v115_global_clean_starts += 1
        self._v115_last_global_error = "—"
        self._v115_last_global_diag = {}
        self._v115_set_clean_button_busy(True, "Iniciando…")
        self._set_banner(
            "Iniciando limpieza sobre el mapa Xiaomi guardado y "
            "verificando movimiento real…"
        )

        vacuum = self.vacuum

        def worker():
            guard_started = False
            confirmed = False
            try:
                if str(self.local_map.active_map_id or "") != str(map_id):
                    raise RuntimeError(
                        "El mapa activo cambió antes de iniciar la limpieza."
                    )

                # Reutilizamos el guard duro del E10: mientras esté activo,
                # ninguna ruta de mapeo puede ejecutar arm/build/start mapping.
                vacuum.begin_targeted_clean()
                guard_started = True

                vacuum.set_suction(suction)
                vacuum.set_water(water)
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
                method = str(diag.get("method") or "—")
                status = diag.get("status_after", "—")
                self.after(
                    0,
                    lambda m=method, s=status: self._set_banner(
                        f"Limpieza iniciada y confirmada · ruta={m} · "
                        f"estado={s}. El mapa Xiaomi queda congelado."
                    ),
                )
                self.after(
                    0,
                    lambda: self._v115_set_clean_button_busy(
                        True,
                        "Limpiando…",
                    ),
                )

                # Conservamos mapa y guard también durante el retorno. Dos
                # lecturas consecutivas fuera de limpieza/pausa/retorno cierran
                # la protección.
                inactive_samples = 0
                started_at = time.monotonic()
                while time.monotonic() - started_at < 12 * 60 * 60:
                    self._v114_restore_grid_if_needed(
                        original_grid,
                        original_fp,
                        map_id,
                    )
                    self._v115_global_map_fp_after = (
                        self._v114_map_fingerprint_after
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
                self.after(
                    0,
                    lambda msg=self._v115_last_global_error: self._set_banner(
                        "No se pudo iniciar la limpieza: " + msg
                    ),
                )
                self.after(
                    0,
                    lambda msg=self._v115_last_global_error: messagebox.showerror(
                        "Iniciar limpieza",
                        msg,
                        parent=self,
                    ),
                )
            finally:
                self._v114_restore_grid_if_needed(
                    original_grid,
                    original_fp,
                    map_id,
                )
                self._v115_global_map_fp_after = (
                    self._v114_map_fingerprint_after
                )
                if guard_started:
                    try:
                        vacuum.end_targeted_clean()
                    except Exception:
                        pass
                self._v115_global_clean_active = False
                self.after(
                    0,
                    lambda: self._v115_set_clean_button_busy(False),
                )
                if confirmed:
                    self.after(
                        0,
                        lambda: self._set_banner(
                            "Limpieza finalizada/retorno detectado. "
                            "El mapa Xiaomi guardado se mantuvo como referencia."
                        ),
                    )

        threading.Thread(
            target=worker,
            name="AspiradoraGlobalCleanV115",
            daemon=True,
        ).start()

    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        vacuum = getattr(self, "vacuum", None)
        device_diag = (
            dict(getattr(vacuum, "_last_global_start_diag", {}) or {})
            if vacuum is not None
            else {}
        )
        lines = [
            "DIAGNÓSTICO V115 ACTIVO · inicio global verificado",
            "=================================================",
            (
                f"limpieza global: activa={self._v115_global_clean_active} · "
                f"intentos={self._v115_global_clean_starts} · "
                f"confirmados={self._v115_global_clean_confirmed} · "
                f"errores={self._v115_global_clean_errors}"
            ),
            f"último error global={self._v115_last_global_error}",
            f"start diag app={self._v115_last_global_diag or '—'}",
            f"start diag E10={device_diag or '—'}",
            (
                f"mapa global protegido: antes="
                f"{self._v115_global_map_fp_before or '—'} · después="
                f"{self._v115_global_map_fp_after or '—'}"
            ),
            (
                f"updates live bloqueados durante global="
                f"{self._v115_live_grid_updates_blocked} · "
                f"intentos UI de modificar mapa bloqueados="
                f"{self._v115_mapping_ui_blocks}"
            ),
            "regla V115: el botón no informa éxito por ACK; exige status físico 5/6/7",
            "regla V115: fallback de inicio = acción por modo -> start genérico -> whole-home",
            "regla V115: ninguna ruta de inicio ejecuta arm_new_map/build-map/start_mapping",
            "regla V115: durante limpieza y retorno el native_grid guardado queda congelado",
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
