import threading
import time
import tkinter as tk
from tkinter import messagebox

import app_v94
import windows_audio_identity


class App(app_v94.App):
    """V95: watchdog de mapa vivo + controles globales de limpieza/base."""

    LOCAL_WORKER_STALL_SECONDS = 10.0
    CLOUD_WORKER_STALL_SECONDS = 18.0
    MAP_ACTIVITY_GRACE_SECONDS = 6.0
    MAP_RECOVERY_COOLDOWN_SECONDS = 4.0

    def __init__(self):
        self._v95_clean_button = None
        self._v95_dock_button = None

        self._v95_mapping_started_at = 0.0
        self._v95_last_local_event_at = 0.0
        self._v95_last_cloud_event_at = 0.0
        self._v95_last_recovery_at = 0.0
        self._v95_local_worker_started_at = 0.0
        self._v95_cloud_worker_started_at = 0.0

        self._v95_local_polls_started = 0
        self._v95_cloud_kicks = 0
        self._v95_recovery_attempts = 0
        self._v95_local_stall_resets = 0
        self._v95_cloud_stall_resets = 0
        self._v95_last_recovery_reason = "—"

        super().__init__()
        self._v95_install_global_controls()
        self._v95_sync_global_controls()

    # ===================================================== controles globales
    def _v95_install_global_controls(self):
        if self._v95_clean_button is not None:
            return
        battery = getattr(self, "battery_header", None)
        if battery is None:
            return

        parent = battery.master
        self._v95_clean_button = self._button(
            parent,
            "Iniciar limpieza",
            self.start_clean,
            compact=True,
            accent=True,
        )
        self._v95_dock_button = self._button(
            parent,
            "Volver a base",
            self.dock,
            compact=True,
        )

        anchor = getattr(self, "_v94_state_badge", None)
        try:
            if anchor is not None:
                self._v95_clean_button.pack(
                    side="left", padx=(0, 6), after=anchor
                )
            else:
                self._v95_clean_button.pack(side="left", padx=(0, 6))
            self._v95_dock_button.pack(
                side="left", padx=(0, 8), after=self._v95_clean_button
            )
        except Exception:
            self._v95_clean_button.pack(side="left", padx=(0, 6))
            self._v95_dock_button.pack(side="left", padx=(0, 8))

    def _v95_sync_global_controls(self):
        connected = bool(getattr(self, "vacuum", None))
        mapping = bool(getattr(self, "mapping_active", False))
        status = getattr(self, "_v94_last_status_code", None)

        clean = getattr(self, "_v95_clean_button", None)
        dock = getattr(self, "_v95_dock_button", None)

        if clean is not None:
            try:
                clean.configure(
                    state="normal" if connected and not mapping else "disabled"
                )
            except Exception:
                pass

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

    def start_clean(self):
        if bool(getattr(self, "mapping_active", False)):
            messagebox.showinfo(
                "Mapeo en curso",
                "Terminá o detené el mapeo antes de iniciar una limpieza normal.",
                parent=self,
            )
            return

        if not getattr(self, "vacuum", None):
            return super().start_clean()

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

        def command():
            # El botón global debe reproducir exactamente la configuración
            # elegida en la pantalla Limpiar, aunque la app haya sido reabierta.
            self.vacuum.set_suction(suction)
            self.vacuum.set_water(water)
            self.vacuum.start(mode)

        return self._run_command(
            "Iniciando limpieza normal con la configuración seleccionada…",
            command,
        )

    # ================================================ mapa vivo / watchdog
    @staticmethod
    def _v95_recovery_due(
        now,
        mapping_started_at,
        last_local_event_at,
        last_cloud_event_at,
        grace=6.0,
    ):
        try:
            now = float(now)
            started = float(mapping_started_at or 0.0)
            local = float(last_local_event_at or 0.0)
            cloud = float(last_cloud_event_at or 0.0)
            grace = float(grace)
        except Exception:
            return False
        if started <= 0:
            return False
        reference = max(started, local, cloud)
        return now - reference >= grace

    def _v95_reset_watchdog_for_mapping(self):
        now = time.monotonic()
        self._v95_mapping_started_at = now
        self._v95_last_local_event_at = 0.0
        self._v95_last_cloud_event_at = 0.0
        self._v95_last_recovery_at = 0.0
        self._v95_local_worker_started_at = 0.0
        self._v95_cloud_worker_started_at = 0.0
        self._v95_last_recovery_reason = "inicio de sesión"

    def _v95_rearm_map_streams(self, reason):
        if (
            not bool(getattr(self, "mapping_active", False))
            or not getattr(self, "vacuum", None)
        ):
            return False

        now = time.monotonic()
        if (
            self._v95_last_recovery_at
            and now - self._v95_last_recovery_at
            < self.MAP_RECOVERY_COOLDOWN_SECONDS
        ):
            return False

        self._v95_last_recovery_at = now
        self._v95_recovery_attempts += 1
        self._v95_last_recovery_reason = str(reason or "sin actividad")

        # En V9, map_polling=True podía quedar sin un after pendiente si
        # _poll_local_map encontraba un worker activo. Reprogramamos siempre.
        try:
            self.map_polling = True
            self.after(0, self._poll_local_map)
        except Exception:
            pass

        # Antes V40 sólo llegaba aquí desde _apply_map_state(). Si la telemetría
        # LAN se clavaba, la lectura Cloud tampoco arrancaba. V95 las desacopla.
        try:
            self._v38_maybe_poll_map_file()
            self._v95_cloud_kicks += 1
        except Exception:
            pass
        return True

    def _poll_local_map(self):
        if getattr(self, "_closing", False) or not getattr(self, "vacuum", None):
            self.map_polling = False
            return

        now = time.monotonic()
        if bool(getattr(self, "_map_worker_running", False)):
            started = float(self._v95_local_worker_started_at or 0.0)
            if started <= 0:
                self._v95_local_worker_started_at = now
                started = now
            if now - started < self.LOCAL_WORKER_STALL_SECONDS:
                # Importante: a diferencia de V9, NO abandonamos el loop.
                self.after(350, self._poll_local_map)
                return

            # La consulta vieja queda como lectura huérfana de sólo lectura.
            # Liberamos el gate para que una consulta nueva pueda recuperar
            # 10/22/10/24 sin congelar toda la sesión.
            self._v95_local_stall_resets += 1
            self._map_worker_running = False

        self.map_polling = True
        self._map_worker_running = True
        self._v95_local_worker_started_at = now
        self._v95_local_polls_started += 1
        vacuum = self.vacuum

        def worker():
            try:
                state = vacuum.local_map_state()
                self._post_ui("map_ok", state)
            except Exception as exc:
                self._post_ui(
                    "map_error",
                    str(exc).strip() or "Sin telemetría",
                )

        threading.Thread(target=worker, daemon=True).start()

    def _v38_maybe_poll_map_file(self):
        now = time.monotonic()

        if bool(getattr(self, "_v38_map_worker", False)):
            started = float(self._v95_cloud_worker_started_at or 0.0)
            if started <= 0:
                self._v95_cloud_worker_started_at = now
                started = now
            if now - started < self.CLOUD_WORKER_STALL_SECONDS:
                return

            # El cliente de mapa es de sólo lectura/subida de mapa. Si una
            # lectura quedó colgada, desbloqueamos el gate para que el siguiente
            # status=5/6/7 pueda volver a pedir un frame fresco.
            self._v95_cloud_stall_resets += 1
            self._v38_map_worker = False

        before = bool(getattr(self, "_v38_map_worker", False))
        result = super()._v38_maybe_poll_map_file()
        after = bool(getattr(self, "_v38_map_worker", False))
        if after and not before:
            self._v95_cloud_worker_started_at = now
        return result

    def _v95_maybe_recover_stalled_map(self):
        if not bool(getattr(self, "mapping_active", False)):
            return False
        now = time.monotonic()
        if not self._v95_recovery_due(
            now,
            self._v95_mapping_started_at,
            self._v95_last_local_event_at,
            self._v95_last_cloud_event_at,
            self.MAP_ACTIVITY_GRACE_SECONDS,
        ):
            return False
        return self._v95_rearm_map_streams(
            "robot limpiando pero sin telemetría/mapa reciente"
        )

    # ====================================================== integración eventos
    def _handle_ui_event(self, kind, payload):
        now = time.monotonic()

        if kind in ("map_ok", "map_error"):
            self._v95_last_local_event_at = now
            self._v95_local_worker_started_at = 0.0

        if kind in ("cloud_ijai_map_state_v40", "cloud_ijai_map_error_v40"):
            self._v95_last_cloud_event_at = now
            self._v95_cloud_worker_started_at = 0.0

        if kind == "v74_mapping_started":
            self._v95_reset_watchdog_for_mapping()

        result = super()._handle_ui_event(kind, payload)

        if kind == "v74_mapping_started" and bool(
            getattr(self, "mapping_active", False)
        ):
            # Arranque explícito: no esperamos a que 10/24 sea quien despierte
            # indirectamente el lector Cloud.
            self.after(
                120,
                lambda: self._v95_rearm_map_streams(
                    "START confirmado: activar LAN + Cloud"
                ),
            )

        self._v95_sync_global_controls()
        return result

    def _render_status(self, status):
        result = super()._render_status(status)
        try:
            physical = int(getattr(status, "status", -1))
        except Exception:
            physical = None

        if (
            bool(getattr(self, "mapping_active", False))
            and physical in (5, 6, 7)
        ):
            # Este es el fix directo para el F12 recibido: status=5 puede seguir
            # alimentando el mapa aunque el stream local todavía tenga 0 puntos.
            try:
                self._v38_maybe_poll_map_file()
                self._v95_cloud_kicks += 1
            except Exception:
                pass
            self._v95_maybe_recover_stalled_map()

        self._v95_sync_global_controls()
        return result

    def _set_connection(self, connected, text=None):
        result = super()._set_connection(connected, text)
        self._v95_sync_global_controls()
        return result

    def _sync_mapping_step_buttons(self):
        result = super()._sync_mapping_step_buttons()
        self._v95_sync_global_controls()
        return result

    # =========================================================== diagnóstico
    @staticmethod
    def _v95_age(now, value):
        try:
            value = float(value or 0.0)
            if value <= 0:
                return "—"
            return f"{max(0.0, float(now) - value):.1f}s"
        except Exception:
            return "—"

    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        now = time.monotonic()
        audio_diag = windows_audio_identity.snapshot()
        lines = [
            "DIAGNÓSTICO V95 ACTIVO · watchdog de mapa + controles globales",
            "=================================================================",
            (
                "mapa vivo: "
                f"local age={self._v95_age(now, self._v95_last_local_event_at)} · "
                f"cloud age={self._v95_age(now, self._v95_last_cloud_event_at)} · "
                f"sesión age={self._v95_age(now, self._v95_mapping_started_at)}"
            ),
            (
                "workers: "
                f"local activo={bool(getattr(self, '_map_worker_running', False))} "
                f"age={self._v95_age(now, self._v95_local_worker_started_at)} · "
                f"cloud activo={bool(getattr(self, '_v38_map_worker', False))} "
                f"age={self._v95_age(now, self._v95_cloud_worker_started_at)}"
            ),
            (
                "recuperación: "
                f"intentos={self._v95_recovery_attempts} · "
                f"local stale resets={self._v95_local_stall_resets} · "
                f"cloud stale resets={self._v95_cloud_stall_resets} · "
                f"polls local={self._v95_local_polls_started} · "
                f"kicks cloud={self._v95_cloud_kicks}"
            ),
            f"última recuperación: {self._v95_last_recovery_reason}",
            (
                "audio Windows: "
                f"nombre={audio_diag.get('display_name', '—')} · "
                f"AppUserModelID={audio_diag.get('app_user_model_id', '—')} · "
                f"sesiones renombradas={audio_diag.get('renamed_sessions', 0)} · "
                f"último error={audio_diag.get('last_error') or '—'}"
            ),
            (
                "controles superiores: "
                "Iniciar limpieza = modo/succión/agua seleccionados · "
                "Volver a base = dock directo"
            ),
            (
                "regla V95: status 5/6/7 durante mapeo despierta el lector Cloud "
                "aunque 10/24 todavía no haya producido ningún punto"
            ),
            (
                "regla V95: un worker LAN/Cloud atascado deja de bloquear "
                "indefinidamente el siguiente sondeo; las operaciones son de lectura"
            ),
            (
                "regla V95: Iniciar limpieza queda bloqueado mientras haya un "
                "mapeo activo para no pisar la sesión"
            ),
            "",
            "",
        ]
        return "\n".join(lines) + inherited
