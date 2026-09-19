import math
import queue
import threading
import time

import app_v95
import app_v9


class App(app_v95.App):
    """V96: arranque tardío seguro + un solo worker + UI desacoplada."""

    # El F12 de V95 mostró la primera secuencia útil alrededor de 0.45 m del
    # dock. V79 toleraba hasta 0.80 m, pero V80 la descartaba a partir de 0.35 m.
    # Unificamos ambos gates y exigimos continuidad temporal, no una muestra
    # aislada, antes de aceptar el arranque.
    INITIAL_GATE_RADIUS_METERS = 0.90
    INITIAL_BUFFER_START_RADIUS = 0.90
    INITIAL_BUFFER_MAX_STEP = 0.40
    INITIAL_BUFFER_MIN_POINTS = 4
    INITIAL_BUFFER_MIN_SPAN = 0.08
    INITIAL_BUFFER_MAX_POINTS = 14
    LEGACY_INITIAL_RADIUS = 0.35

    # Sondeo LAN: un único callback pendiente y un único worker real.
    LOCAL_ACTIVE_POLL_MS = 900
    LOCAL_IDLE_POLL_MS = 2500
    LOCAL_BUSY_RETRY_MS = 550

    # El decoder B112 es costoso. Nunca se solapan workers Cloud y se baja la
    # frecuencia respecto de V95/V41. Si un worker tarda, se espera a que termine.
    CLOUD_FILE_POLL_SECONDS = 12.0
    CLOUD_UPLOAD_INTERVAL_SECONDS = 12.0
    CLOUD_WORKER_STALL_SECONDS = 30.0

    # Tk no debe redibujar todo el plano por cada evento repetido.
    RENDER_MIN_INTERVAL_SECONDS = 0.35
    UI_EVENT_BUDGET = 10

    def __init__(self):
        self._v96_local_poll_job = None
        self._v96_render_job = None
        self._v96_last_render_at = 0.0
        self._v96_render_requests = 0
        self._v96_render_executed = 0
        self._v96_render_coalesced = 0
        self._v96_ui_batches = 0
        self._v96_ui_events_processed = 0
        self._v96_ui_budget_hits = 0

        self._v96_local_busy_waits = 0
        self._v96_cloud_worker_stalls_seen = 0
        self._v96_cloud_stall_marker = None
        self._v96_cloud_actual_starts = 0

        self._v96_initial_last_reason = "esperando muestras"
        self._v96_initial_first_distance = None
        self._v96_initial_span = 0.0
        self._v96_initial_late_starts = 0
        self._v96_initial_discontinuities = 0
        self._v96_prevalidation_rebase_blocks = 0
        super().__init__()

    # ============================================================ reset sesión
    def _v74_reset_session(self):
        self._v96_initial_last_reason = "sesión reiniciada"
        self._v96_initial_first_distance = None
        self._v96_initial_span = 0.0
        self._v96_initial_late_starts = 0
        self._v96_initial_discontinuities = 0
        self._v96_prevalidation_rebase_blocks = 0
        return super()._v74_reset_session()

    # ======================================== arranque físico antes de V85/V82
    def _v82_correct_absolute(self, absolute):
        """Durante el gate inicial usa 10/24 absoluto sin rebase/carril.

        V95 podía recibir una discontinuidad antes de que V80 validara el
        arranque. V85 la convertía en un offset persistente y V80 terminaba
        viendo todos los puntos lejos del dock. Hasta validar cuatro muestras
        continuas, conservamos el marco físico raw/base y dejamos que V80 sea
        quien acepte o reinicie la secuencia.
        """
        if (
            bool(getattr(self, "mapping_active", False))
            and not bool(getattr(self, "_v80_initial_validated", False))
        ):
            try:
                x = float(absolute["x"])
                y = float(absolute["y"])
                angle = float(
                    absolute.get("phi", absolute.get("angle", 0.0)) or 0.0
                )
            except Exception:
                return super()._v82_correct_absolute(absolute)

            current = (x, y, angle)
            previous = getattr(self, "_v85_last_raw", None)
            raw_step = 0.0
            if previous is not None:
                raw_step = math.hypot(
                    x - float(previous[0]),
                    y - float(previous[1]),
                )
                self._v85_max_raw_step = max(
                    float(getattr(self, "_v85_max_raw_step", 0.0) or 0.0),
                    float(raw_step),
                )

            if (
                previous is not None
                and raw_step >= float(self.IMPOSSIBLE_RAW_STEP_METERS)
            ):
                self._v96_prevalidation_rebase_blocks += 1
                # Una discontinuidad antes del gate no crea un marco nuevo.
                # También limpiamos estados geométricos transitorios.
                self._v85_frame_offset = (0.0, 0.0)
                self._v82_turn_hold = False
                self._v82_turn_origin = None
                self._v82_turn_axis = None
                self._v82_turn_pending = []
                self._v82_lane_origin = None
                self._v82_lane_axis = None
                try:
                    self._v82_lane_pending.clear()
                except Exception:
                    pass

            self._v85_frame_offset = (0.0, 0.0)
            self._v85_last_raw = current
            self._v85_last_transformed = current
            self._v82_previous_raw = current
            self._v82_last_corrected = current
            self._v79_previous_absolute = current
            self._v79_last_filtered = current
            self._v77_filter_last_raw = current
            self._v77_filter_last_output = current

            result = dict(absolute)
            result["x"] = x
            result["y"] = y
            result["phi"] = angle
            return result

        return super()._v82_correct_absolute(absolute)

    @staticmethod
    def _v96_buffer_span(points):
        values = []
        for point in list(points or []):
            try:
                values.append((float(point["x"]), float(point["y"])))
            except Exception:
                continue
        if len(values) < 2:
            return 0.0
        first = values[0]
        return max(
            math.hypot(x - first[0], y - first[1])
            for x, y in values[1:]
        )

    def _v80_buffer_initial_point(self, point):
        if self._v80_initial_validated:
            return [point]

        distance = self._v80_point_distance(point)
        radius = float(self.INITIAL_BUFFER_START_RADIUS)

        if not self._v80_initial_buffer:
            if distance > radius:
                self._v80_initial_buffer_rejected += 1
                self._v96_initial_last_reason = (
                    f"rechazado: primera muestra a {distance:.2f} m > "
                    f"{radius:.2f} m"
                )
                return []

            self._v80_initial_buffer = [dict(point)]
            self._v96_initial_first_distance = float(distance)
            if distance > float(self.LEGACY_INITIAL_RADIUS):
                self._v96_initial_late_starts += 1
                self._v96_initial_last_reason = (
                    f"arranque tardío candidato a {distance:.2f} m"
                )
            else:
                self._v96_initial_last_reason = (
                    f"arranque cercano candidato a {distance:.2f} m"
                )
            return []

        step = self._v80_step(self._v80_initial_buffer[-1], point)
        if step > float(self.INITIAL_BUFFER_MAX_STEP):
            self._v80_initial_buffer_resets += 1
            self._v80_initial_buffer_rejected += 1
            self._v96_initial_discontinuities += 1
            self._v96_initial_last_reason = (
                f"reinicio por discontinuidad {step:.2f} m > "
                f"{self.INITIAL_BUFFER_MAX_STEP:.2f} m"
            )
            if distance <= radius:
                self._v80_initial_buffer = [dict(point)]
                self._v96_initial_first_distance = float(distance)
            else:
                self._v80_initial_buffer = []
                self._v96_initial_first_distance = None
            return []

        self._v80_initial_buffer.append(dict(point))
        if len(self._v80_initial_buffer) > int(self.INITIAL_BUFFER_MAX_POINTS):
            self._v80_initial_buffer = self._v80_initial_buffer[
                -int(self.INITIAL_BUFFER_MAX_POINTS):
            ]

        span = self._v96_buffer_span(self._v80_initial_buffer)
        self._v96_initial_span = float(span)
        enough = (
            len(self._v80_initial_buffer)
            >= int(self.INITIAL_BUFFER_MIN_POINTS)
        )
        moved = span >= float(self.INITIAL_BUFFER_MIN_SPAN)
        quiet_but_safe = (
            len(self._v80_initial_buffer) >= 8
            and span <= 0.04
            and max(
                self._v80_point_distance(item)
                for item in self._v80_initial_buffer
            ) <= radius
        )

        if enough and (moved or quiet_but_safe):
            flushed = [dict(item) for item in self._v80_initial_buffer]
            self._v80_initial_buffer = []
            self._v80_initial_validated = True
            self._v80_initial_flush_count += len(flushed)
            self._v96_initial_last_reason = (
                f"VALIDADO: {len(flushed)} muestras continuas · "
                f"span={span:.2f} m"
            )
            return flushed

        self._v96_initial_last_reason = (
            f"acumulando {len(self._v80_initial_buffer)}/"
            f"{self.INITIAL_BUFFER_MIN_POINTS} · span={span:.2f} m"
        )
        return []

    # ============================================== un solo loop LAN pendiente
    def _v96_schedule_local_poll(self, delay_ms):
        if getattr(self, "_closing", False) or not getattr(self, "vacuum", None):
            self.map_polling = False
            return False

        old = getattr(self, "_v96_local_poll_job", None)
        if old is not None:
            try:
                self.after_cancel(old)
            except Exception:
                pass
            self._v96_local_poll_job = None

        def run():
            self._v96_local_poll_job = None
            self._poll_local_map()

        try:
            self.map_polling = True
            self._v96_local_poll_job = self.after(
                max(0, int(delay_ms)),
                run,
            )
            return True
        except Exception:
            self._v96_local_poll_job = None
            return False

    def _start_local_map_polling(self):
        if getattr(self, "_closing", False) or not getattr(self, "vacuum", None):
            return
        self.map_polling = True
        self._v96_schedule_local_poll(100)

    def _schedule_next_map_poll(self):
        if getattr(self, "_closing", False) or not getattr(self, "vacuum", None):
            self.map_polling = False
            return
        delay = (
            self.LOCAL_ACTIVE_POLL_MS
            if bool(getattr(self, "mapping_active", False))
            else self.LOCAL_IDLE_POLL_MS
        )
        self._v96_schedule_local_poll(delay)

    def _poll_local_map(self):
        if getattr(self, "_closing", False) or not getattr(self, "vacuum", None):
            self.map_polling = False
            return

        if bool(getattr(self, "_map_worker_running", False)):
            self._v96_local_busy_waits += 1
            self._v96_schedule_local_poll(self.LOCAL_BUSY_RETRY_MS)
            return

        self.map_polling = True
        self._map_worker_running = True
        self._v95_local_worker_started_at = time.monotonic()
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

        threading.Thread(
            target=worker,
            name="AspiradoraLocalMap",
            daemon=True,
        ).start()

    # ============================================= cloud sin workers huérfanos
    @staticmethod
    def _v96_cloud_due(worker_active, now, last_at, interval):
        if worker_active:
            return False
        try:
            return (
                float(now) - float(last_at or 0.0)
                >= float(interval)
            )
        except Exception:
            return False

    def _v38_maybe_poll_map_file(self):
        if (
            not bool(getattr(self, "mapping_active", False))
            or not getattr(self, "vacuum", None)
        ):
            return False
        try:
            if not self._cloud_session_ready():
                return False
        except Exception:
            return False

        now = time.monotonic()
        worker_active = bool(getattr(self, "_v38_map_worker", False))
        if worker_active:
            started = float(getattr(self, "_v95_cloud_worker_started_at", 0.0) or 0.0)
            if started <= 0:
                self._v95_cloud_worker_started_at = now
                started = now
            age = now - started
            if age >= float(self.CLOUD_WORKER_STALL_SECONDS):
                marker = round(started, 3)
                if marker != self._v96_cloud_stall_marker:
                    self._v96_cloud_stall_marker = marker
                    self._v96_cloud_worker_stalls_seen += 1
            # V96 NO baja _v38_map_worker a mano. Python no puede cancelar con
            # seguridad el hilo anterior; abrir otro sólo duplica RAM/CPU.
            return False

        if not self._v96_cloud_due(
            False,
            now,
            getattr(self, "_v38_map_last_at", 0.0),
            self.CLOUD_FILE_POLL_SECONDS,
        ):
            return False

        before = bool(getattr(self, "_v38_map_worker", False))
        result = super()._v38_maybe_poll_map_file()
        after = bool(getattr(self, "_v38_map_worker", False))
        if after and not before:
            self._v96_cloud_actual_starts += 1
            self._v96_cloud_stall_marker = None
        return bool(after and not before) or bool(result)

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
        self._v96_schedule_local_poll(0)
        started_cloud = self._v38_maybe_poll_map_file()
        if started_cloud:
            self._v95_cloud_kicks += 1
        return True

    # ================================================ presupuesto de eventos UI
    def _drain_ui_events(self):
        if getattr(self, "_closing", False):
            return

        processed = 0
        self._v96_ui_batches += 1
        try:
            while processed < int(self.UI_EVENT_BUDGET):
                kind, payload = self._ui_events.get_nowait()
                self._handle_ui_event(kind, payload)
                processed += 1
                self._v96_ui_events_processed += 1
        except queue.Empty:
            pass
        except Exception:
            app_v9._save_crash_log(app_v9.traceback.format_exc())

        pending = False
        try:
            pending = not self._ui_events.empty()
        except Exception:
            pending = False
        if pending:
            self._v96_ui_budget_hits += 1

        if not getattr(self, "_closing", False):
            self.after(12 if pending else 60, self._drain_ui_events)

    # ================================================== render coalescido de Tk
    def _v96_render_now(self):
        self._v96_render_job = None
        self._v96_last_render_at = time.monotonic()
        self._v96_render_executed += 1
        return super()._render_maps()

    def _render_maps(self):
        self._v96_render_requests += 1
        now = time.monotonic()
        elapsed = now - float(self._v96_last_render_at or 0.0)
        if self._v96_last_render_at <= 0 or elapsed >= self.RENDER_MIN_INTERVAL_SECONDS:
            job = getattr(self, "_v96_render_job", None)
            if job is not None:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
                self._v96_render_job = None
            return self._v96_render_now()

        self._v96_render_coalesced += 1
        if self._v96_render_job is None:
            wait_ms = max(
                1,
                int((self.RENDER_MIN_INTERVAL_SECONDS - elapsed) * 1000),
            )
            try:
                self._v96_render_job = self.after(wait_ms, self._v96_render_now)
            except Exception:
                self._v96_render_job = None
        return None

    def destroy(self):
        for attr in ("_v96_local_poll_job", "_v96_render_job"):
            job = getattr(self, attr, None)
            if job is not None:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
                setattr(self, attr, None)
        return super().destroy()

    # =========================================================== diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        now = time.monotonic()
        cloud_started = float(
            getattr(self, "_v95_cloud_worker_started_at", 0.0) or 0.0
        )
        cloud_age = (
            max(0.0, now - cloud_started)
            if cloud_started > 0
            else None
        )

        lines = [
            "DIAGNÓSTICO V96 ACTIVO · arranque tardío + rendimiento/UI",
            "==========================================================",
            (
                "gate inicial: "
                f"validado={bool(getattr(self, '_v80_initial_validated', False))} · "
                f"radio={self.INITIAL_BUFFER_START_RADIUS:.2f}m · "
                f"primer radio={self._v96_initial_first_distance!r} · "
                f"span={self._v96_initial_span:.2f}m · "
                f"motivo={self._v96_initial_last_reason}"
            ),
            (
                "protección pre-gate: "
                f"rebases V85 bloqueados={self._v96_prevalidation_rebase_blocks} · "
                f"discontinuidades buffer={self._v96_initial_discontinuities} · "
                f"arranques tardíos={self._v96_initial_late_starts}"
            ),
            (
                "LAN: "
                f"worker={bool(getattr(self, '_map_worker_running', False))} · "
                f"polls={self._v95_local_polls_started} · "
                f"esperas worker ocupado={self._v96_local_busy_waits} · "
                f"intervalo activo={self.LOCAL_ACTIVE_POLL_MS}ms"
            ),
            (
                "Cloud: "
                f"worker={bool(getattr(self, '_v38_map_worker', False))} · "
                f"age={cloud_age!r}s · starts reales={self._v96_cloud_actual_starts} · "
                f"stalls observados={self._v96_cloud_worker_stalls_seen} · "
                f"intervalo≥{self.CLOUD_FILE_POLL_SECONDS:.1f}s · "
                "solapamiento=PROHIBIDO"
            ),
            (
                "UI: "
                f"eventos={self._v96_ui_events_processed} · "
                f"batches={self._v96_ui_batches} · "
                f"budget hits={self._v96_ui_budget_hits} · "
                f"render pedidos/ejecutados/coalescidos="
                f"{self._v96_render_requests}/{self._v96_render_executed}/"
                f"{self._v96_render_coalesced}"
            ),
            (
                "regla V96: antes de validar el arranque, 10/24 conserva el "
                "marco físico base/raw y V85 no puede crear un offset persistente"
            ),
            (
                "regla V96: una primera muestra tardía hasta 0.90 m se acepta "
                "sólo tras una secuencia continua; una discontinuidad reinicia el gate"
            ),
            (
                "regla V96: un worker Cloud lento nunca se libera artificialmente; "
                "se espera su evento antes de lanzar otro"
            ),
            (
                "regla V96: Tk procesa eventos por lotes pequeños y coalescea "
                "repintados para mantener botones/ventana responsivos"
            ),
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
