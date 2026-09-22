import re
import threading
import time
import tkinter as tk
from tkinter import messagebox

import app_v139
import app_v9


class App(app_v139.App):
    """V140: restablecimiento profundo de navegación/limpieza sin borrar Wi-Fi."""

    def __init__(self):
        self._v140_reset_button = None
        self._v140_reset_running = False
        self._v140_reset_count = 0
        self._v140_last_reset = {}
        self._v140_last_reset_error = None
        super().__init__()
        self.after_idle(self._v140_install_maintenance_card)

    # ===================================================== UI mantenimiento
    def _v140_install_maintenance_card(self):
        page = getattr(self, "_pages", {}).get("settings")
        if page is None or self._v140_reset_button is not None:
            return False

        try:
            palette = self._v98_palette(
                str((self.settings or {}).get("theme") or "light")
            )
        except Exception:
            palette = {
                "card": "#ffffff",
                "text": "#17181a",
                "muted": "#7b8088",
                "border": "#e8eaed",
            }

        card = tk.Frame(
            page,
            bg=palette["card"],
            highlightthickness=1,
            highlightbackground=palette["border"],
        )
        card.pack(fill="x", padx=5, pady=5)

        tk.Label(
            card,
            text="Mantenimiento avanzado",
            bg=palette["card"],
            fg=palette["text"],
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w", padx=20, pady=(18, 5))

        tk.Label(
            card,
            text=(
                "Restablece mapas, navegación y estados de limpieza del E10 "
                "sin borrar la red Wi-Fi ni la vinculación Xiaomi."
            ),
            bg=palette["card"],
            fg=palette["muted"],
            font=("Segoe UI", 9),
            justify="left",
            wraplength=780,
        ).pack(anchor="w", padx=20, pady=(0, 8))

        tk.Label(
            card,
            text=(
                "También limpia los mapas, habitaciones, zonas y rutinas "
                "guardados por esta aplicación para que el próximo mapeo "
                "empiece realmente desde cero."
            ),
            bg=palette["card"],
            fg=palette["muted"],
            font=("Segoe UI", 8),
            justify="left",
            wraplength=780,
        ).pack(anchor="w", padx=20, pady=(0, 12))

        self._v140_reset_button = self._button(
            card,
            "Restablecer aspiradora (conservar Wi-Fi)",
            self._v140_confirm_reset,
            compact=True,
        )
        self._v140_reset_button.pack(anchor="w", padx=20, pady=(0, 18))

        try:
            self._v99_schedule_refresh(card)
        except Exception:
            pass
        return True

    def _v140_confirm_reset(self):
        if self._v140_reset_running:
            messagebox.showinfo(
                "Restablecimiento",
                "El restablecimiento ya está en curso.",
                parent=self,
            )
            return False

        if not getattr(self, "vacuum", None):
            messagebox.showwarning(
                "Robot desconectado",
                "Conectá el E10 antes de restablecerlo.",
                parent=self,
            )
            return False

        first = messagebox.askyesno(
            "Restablecer aspiradora",
            "¿Querés restablecer navegación y limpieza del E10?\n\n"
            "Se borrarán los mapas internos del robot y los mapas, habitaciones, "
            "zonas y rutinas de esta aplicación.\n\n"
            "La red Wi-Fi, IP/token y la vinculación Xiaomi se conservarán.",
            parent=self,
        )
        if not first:
            return False

        second = messagebox.askyesno(
            "Confirmar restablecimiento",
            "Confirmá una segunda vez.\n\n"
            "Después del proceso la aspiradora quedará en la base y el próximo "
            "Mapear vivienda empezará desde cero.\n\n"
            "¿Continuar?",
            parent=self,
        )
        if not second:
            return False

        self._v140_reset_running = True
        try:
            self._v140_reset_button.configure(
                state="disabled",
                text="Restableciendo…",
            )
        except Exception:
            pass
        self._set_banner(
            "Restablecimiento avanzado · preparando el E10 y conservando Wi-Fi…"
        )

        vacuum = self.vacuum
        threading.Thread(
            target=self._v140_reset_worker,
            args=(vacuum,),
            name="AspiradoraDeepResetPreserveWifiV140",
            daemon=True,
        ).start()
        return True

    # ========================================================= robot reset
    @staticmethod
    def _v140_action_accepted(vacuum, response, output_piid=None):
        try:
            code = vacuum._miot_action_code(response)
        except Exception:
            code = None
        try:
            ack = bool(vacuum._miot_action_ack(response))
        except Exception:
            ack = False
        try:
            empty_ack = bool(vacuum._miot_b112_empty_result_ack(response))
        except Exception:
            empty_ack = False
        output = None
        if output_piid is not None:
            try:
                output = vacuum._miot_output_value(response, int(output_piid))
            except Exception:
                output = None
        return bool(code == 0 or ack or empty_ack or output is not None), {
            "code": code,
            "ack": ack,
            "empty_ack": empty_ack,
            "output": output,
            "summary": (
                vacuum._miot_action_response_summary(response)
                if hasattr(vacuum, "_miot_action_response_summary")
                else repr(response)[:260]
            ),
        }

    @staticmethod
    def _v140_parse_order_ids(order_data):
        if order_data is None:
            return []
        text = str(order_data).strip()
        if not text:
            return []
        found = []
        # El B112 documenta N reservas separadas por coma y cada registro
        # comienza con order-id. Aceptamos "_" y ":" como separadores vistos
        # en firmwares de la misma familia.
        for chunk in re.split(r"[,;|]+", text):
            match = re.match(r"\s*(\d{1,3})(?:[_:\s]|$)", chunk)
            if not match:
                continue
            value = int(match.group(1))
            if 0 <= value <= 100 and value not in found:
                found.append(value)
        return found

    def _v140_delete_robot_orders(self, vacuum):
        diag = {
            "get": None,
            "order_data": None,
            "ids": [],
            "deleted": [],
            "errors": [],
        }
        try:
            response = vacuum.device.call_action_by(8, 3)
            diag["get"] = (
                vacuum._miot_action_response_summary(response)
                if hasattr(vacuum, "_miot_action_response_summary")
                else repr(response)[:260]
            )
            try:
                order_data = vacuum._miot_output_value(response, 15)
            except Exception:
                order_data = None
            diag["order_data"] = (
                str(order_data)[:600] if order_data is not None else None
            )
            ids = self._v140_parse_order_ids(order_data)
            diag["ids"] = list(ids)
        except Exception as exc:
            diag["errors"].append(
                "get: " + (str(exc).strip() or type(exc).__name__)
            )
            return diag

        for order_id in diag["ids"]:
            try:
                response = vacuum.device.call_action_by(8, 2, [int(order_id)])
                accepted, meta = self._v140_action_accepted(vacuum, response)
                diag["deleted"].append({
                    "id": int(order_id),
                    "accepted": bool(accepted),
                    **meta,
                })
            except Exception as exc:
                diag["errors"].append(
                    f"del {order_id}: "
                    + (str(exc).strip() or type(exc).__name__)
                )
        return diag

    def _v140_reset_robot_maps(self, vacuum):
        attempts = []
        for aiid, name, output_piid in (
            (16, "reset-map-ii", 18),
            (10, "reset-map", None),
        ):
            item = {"aiid": aiid, "action": name, "accepted": False}
            try:
                response = vacuum.device.call_action_by(10, aiid)
                accepted, meta = self._v140_action_accepted(
                    vacuum,
                    response,
                    output_piid=output_piid,
                )
                item.update(meta)
                item["accepted"] = bool(accepted)
                attempts.append(item)
                if accepted:
                    return {
                        "success": True,
                        "winner": name,
                        "attempts": attempts,
                    }
            except Exception as exc:
                item["error"] = str(exc).strip() or type(exc).__name__
                attempts.append(item)
        raise RuntimeError(
            "El E10 rechazó reset-map-ii y reset-map: "
            + repr(attempts)[:900]
        )

    def _v140_reset_local_app_state(self):
        result = {
            "maps": False,
            "plan": False,
            "active_map": None,
            "errors": [],
        }
        try:
            blank = self.local_map._library_defaults()
            self.local_map.replace_library(blank)
            result["maps"] = True
            result["active_map"] = self.local_map.active_map_id
        except Exception as exc:
            result["errors"].append(
                "maps: " + (str(exc).strip() or type(exc).__name__)
            )

        try:
            if getattr(self, "plan_store", None):
                self.plan_store.replace_all({})
                if result["active_map"]:
                    self.plan_store.set_active_map(result["active_map"])
            result["plan"] = True
        except Exception as exc:
            result["errors"].append(
                "plan: " + (str(exc).strip() or type(exc).__name__)
            )

        # Limpiamos únicamente caches de geometría/UI, nunca SettingsStore.
        for name in (
            "_v99_session_bounds",
            "_v99_native_locked",
            "_v72_views",
            "_v130_final_return_grid",
        ):
            obj = getattr(self, name, None)
            try:
                if hasattr(obj, "clear"):
                    obj.clear()
            except Exception:
                pass

        self.selected_point = None
        self.mapping_active = False
        self.mapping_phase = 0
        self.mapping_transitioning = False
        self.mapping_step1_complete = False
        self.mapping_step2_complete = False
        self.map_polling = False
        return result

    def _v140_reset_worker(self, vacuum):
        diag = {
            "started_at": round(time.monotonic(), 3),
            "wifi_touched": False,
            "account_touched": False,
            "clean_reset_before": None,
            "orders": None,
            "remember_state": None,
            "mop_route": None,
            "maps": None,
            "clean_reset_after": None,
            "readback": None,
            "local": None,
            "success": False,
            "error": None,
        }
        try:
            if vacuum is not getattr(self, "vacuum", None):
                raise RuntimeError("La conexión con el E10 cambió durante el reset.")

            # 1) Estado operativo neutro + dock confirmado.
            diag["clean_reset_before"] = self._v138_reset_cleaning_state(
                vacuum,
                "V140 pre-reset profundo",
                ensure_dock=True,
            )

            # 2) Borrar reservas del propio robot que el firmware nos enumere.
            diag["orders"] = self._v140_delete_robot_orders(vacuum)

            # 3) Valores persistentes de navegación que sí tienen setter.
            try:
                diag["remember_state"] = repr(
                    vacuum.device.set_property_by(10, 1, 0)
                )[:350]
            except Exception as exc:
                diag["remember_state"] = (
                    "error: " + (str(exc).strip() or type(exc).__name__)
                )

            try:
                diag["mop_route"] = repr(
                    vacuum.device.set_property_by(7, 7, 0)
                )[:350]
            except Exception as exc:
                diag["mop_route"] = (
                    "error: " + (str(exc).strip() or type(exc).__name__)
                )

            # 4) Borrado oficial de todos los mapas B112. reset-map-ii es la
            # acción moderna; reset-map queda como fallback documentado.
            diag["maps"] = self._v140_reset_robot_maps(vacuum)
            time.sleep(1.20)

            # 5) Normalización final. No hay ninguna escritura a servicios de
            # red, credenciales, cuenta Xiaomi ni SettingsStore.
            diag["clean_reset_after"] = self._v138_reset_cleaning_state(
                vacuum,
                "V140 post-reset profundo",
                ensure_dock=True,
            )

            try:
                vacuum.reset_live_path_session()
            except Exception:
                pass

            try:
                diag["readback"] = vacuum._get_many([
                    ("status", 2, 1),
                    ("mode", 2, 4),
                    ("sweep_type", 2, 8),
                    ("repeat", 7, 1),
                    ("remember_state", 10, 1),
                    ("cur_map_id", 10, 2),
                    ("map_num", 10, 3),
                    ("build_map", 10, 14),
                    ("has_new_map", 10, 19),
                ])
            except Exception as exc:
                diag["readback_error"] = (
                    str(exc).strip() or type(exc).__name__
                )

            # 6) Borrar el espejo local para no mezclar geometría previa con el
            # próximo mapa. Esto no toca IP/token/QR ni preferencias generales.
            diag["local"] = self._v140_reset_local_app_state()
            if diag["local"].get("errors"):
                raise RuntimeError(
                    "El robot se restableció pero falló la limpieza local: "
                    + "; ".join(diag["local"]["errors"])
                )

            diag["success"] = True
            self._v140_reset_count += 1
            self._v140_last_reset = dict(diag)
            self._v140_last_reset_error = None
            self._post_ui("v140_reset_done", diag)
        except Exception as exc:
            diag["error"] = str(exc).strip() or type(exc).__name__
            self._v140_last_reset = dict(diag)
            self._v140_last_reset_error = diag["error"]
            self._post_ui("v140_reset_error", diag)

    # ========================================================== eventos/UI
    def _handle_ui_event(self, kind, payload):
        if kind == "v140_reset_done":
            self._v140_reset_running = False
            try:
                if self._v140_reset_button is not None:
                    self._v140_reset_button.configure(
                        state="normal",
                        text="Restablecer aspiradora (conservar Wi-Fi)",
                    )
            except Exception:
                pass
            try:
                self._sync_mapping_step_buttons()
                self._v70_update_active_map_labels()
                self._v70_refresh_map_overview(force=True)
                self._render_maps()
            except Exception:
                pass
            self._set_banner(
                "Restablecimiento finalizado · proceso finalizó. "
                "Wi-Fi conservado; ya podés iniciar Mapear vivienda."
            )
            messagebox.showinfo(
                "Restablecimiento finalizado",
                "La navegación y los estados de limpieza fueron restablecidos.\n\n"
                "La red Wi-Fi y la vinculación Xiaomi se conservaron.\n\n"
                "Ahora podés ir a Mapa → Mapear vivienda.",
                parent=self,
            )
            return None

        if kind == "v140_reset_error":
            self._v140_reset_running = False
            try:
                if self._v140_reset_button is not None:
                    self._v140_reset_button.configure(
                        state="normal",
                        text="Restablecer aspiradora (conservar Wi-Fi)",
                    )
            except Exception:
                pass
            diag = payload[0] if payload else {}
            error = str((diag or {}).get("error") or "Error desconocido")
            self._set_banner(
                "Restablecimiento finalizado con error · proceso finalizó."
            )
            messagebox.showerror(
                "Restablecimiento incompleto",
                error,
                parent=self,
            )
            return None

        return super()._handle_ui_event(kind, payload)

    # =========================================================== diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        lines = [
            "DIAGNÓSTICO V140 ACTIVO · reset profundo sin Wi-Fi",
            "===================================================",
            (
                f"reset en curso={self._v140_reset_running} · "
                f"completados={self._v140_reset_count}"
            ),
            f"último reset={self._v140_last_reset or '—'}",
            f"último error={self._v140_last_reset_error or '—'}",
            "robot: reset limpieza V138 + borrar reservas detectadas + remember-state=0 + mop-route=0",
            "mapas B112: 10/16 reset-map-ii; fallback 10/10 reset-map",
            "local: se recrea biblioteca de mapas y plan/rutinas desde cero",
            "red: NO se escriben propiedades Wi-Fi, IP, token ni cuenta Xiaomi",
            "voz/idioma y contadores de consumibles: no se modifican",
            "uso previsto: Ajustes > Mantenimiento avanzado > Restablecer aspiradora (conservar Wi-Fi) > Mapear vivienda",
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
