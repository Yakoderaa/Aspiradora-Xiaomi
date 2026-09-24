import json
import math
import queue
import threading
import time
from pathlib import Path
from tkinter import messagebox

import app_v155
import app_v87
import app_v9


class App(app_v155.App):
    """V156: mapa/guía livianos sin devolver autoridad a controladores viejos."""

    # V155 demostró que no necesitamos reconstruir el plano nueve veces por
    # segundo. La prioridad ahora es una UI fluida y una trayectoria fiable.
    LOCAL_ACTIVE_POLL_MS = 3000
    LOCAL_IDLE_POLL_MS = 10000
    LOCAL_BUSY_RETRY_MS = 1200
    RENDER_MIN_INTERVAL_SECONDS = 3.0
    UI_EVENT_BUDGET = 60

    GUIDE_SAMPLE_METERS = 0.25
    GUIDE_CELL_METERS = 0.40
    GUIDE_FLUSH_SECONDS = 12.0
    GUIDE_PROGRESS_SECONDS = 20.0
    GUIDE_MAX_SPAN_METERS = 25.0
    GUIDE_MIN_POINTS = 25
    RAW_WRAP_UNITS = 256.0
    RAW_TO_METERS_V156 = 0.10
    MAPPING_WAIT_SECONDS = 6 * 60 * 60

    ROUTE_VISIBLE = True

    def __init__(self):
        self._v156_candidate = []
        self._v156_candidate_persisted = 0
        self._v156_learning = False
        self._v156_mapping_started = False
        self._v156_started_at = 0.0
        self._v156_prestart_raw = None
        self._v156_base_raw = None
        self._v156_last_raw_mod = None
        self._v156_last_unwrapped = None
        self._v156_last_local = None
        self._v156_last_flush_at = 0.0
        self._v156_base_saved = False
        self._v156_wrap_x = 0
        self._v156_wrap_y = 0
        self._v156_rejected_jumps = 0
        self._v156_map_samples = 0
        self._v156_cloud_calls_blocked = 0
        self._v156_guide = {}
        self._v156_guide_cells = set()
        self._v156_guide_visited = set()
        self._v156_off_guide_samples = 0
        self._v156_last_guide_progress_at = 0.0
        self._v156_last_progress = {}
        self._v156_idle_notice_sent = False
        self._v156_live_motion = False
        super().__init__()
        self._v156_load_guide()

    # ============================================================ rendimiento
    def _maybe_poll_cloud_position(self):
        # V155 hizo 1735 consultas de historial sin obtener un solo punto.
        self._v156_cloud_calls_blocked += 1
        return False

    def _v38_maybe_poll_map_file(self):
        # El recorrido útil de este B112 llega por LAN 10/24. No levantamos
        # workers Cloud durante el recorrido.
        self._v156_cloud_calls_blocked += 1
        return False

    def _v95_rearm_map_streams(self, reason):
        # Recuperar sólo la lectura LAN. Nunca iniciar Cloud como reacción a un
        # watchdog de UI.
        try:
            self._v96_schedule_local_poll(0)
            return True
        except Exception:
            return False

    def _drain_ui_events(self):
        if getattr(self, "_closing", False):
            return

        processed = 0
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

        self._v96_ui_batches += 1
        try:
            pending = not self._ui_events.empty()
        except Exception:
            pending = False
        if pending:
            self._v96_ui_budget_hits += 1

        if not getattr(self, "_closing", False):
            # V96 despertaba Tk hasta ~17 veces/s aun sin eventos. V156 duerme
            # cuando está ocioso y sólo acelera cuando realmente hay cola.
            self.after(30 if pending else 250, self._drain_ui_events)

    # =============================================================== guía
    def _v156_guide_path(self):
        folder = getattr(getattr(self, "local_map", None), "folder", None)
        if folder is None:
            return None
        return Path(folder) / "route_guide_v156.json"

    @staticmethod
    def _v156_point_xy(point):
        if not isinstance(point, dict):
            return None
        try:
            x = float(point["x"])
            y = float(point["y"])
        except Exception:
            return None
        if not (math.isfinite(x) and math.isfinite(y)):
            return None
        return x, y

    @classmethod
    def _v156_stats(cls, points):
        clean = []
        total = 0.0
        previous = None
        for point in list(points or []):
            xy = cls._v156_point_xy(point)
            if xy is None:
                continue
            clean.append(xy)
            if previous is not None:
                total += math.hypot(xy[0] - previous[0], xy[1] - previous[1])
            previous = xy
        if not clean:
            return {
                "points": 0,
                "span_x": 0.0,
                "span_y": 0.0,
                "path_m": 0.0,
            }
        xs = [p[0] for p in clean]
        ys = [p[1] for p in clean]
        return {
            "points": len(clean),
            "span_x": max(xs) - min(xs),
            "span_y": max(ys) - min(ys),
            "path_m": total,
        }

    def _v156_cells_from_points(self, points):
        cell_m = float(self.GUIDE_CELL_METERS)
        result = set()
        for point in list(points or []):
            xy = self._v156_point_xy(point)
            if xy is None:
                continue
            result.add((
                int(round(xy[0] / cell_m)),
                int(round(xy[1] / cell_m)),
            ))
        return result

    def _v156_load_guide(self):
        self._v156_guide = {}
        self._v156_guide_cells = set()
        path = self._v156_guide_path()
        if path is None or not path.exists():
            # Sólo migramos un mapa local si su escala ya es físicamente
            # plausible. El mapa V155 de esta prueba (68x40 m) queda rechazado.
            try:
                snapshot = self.local_map.snapshot()
                points = list(snapshot.get("points") or [])
                stats = self._v156_stats(points)
                if (
                    stats["points"] >= self.GUIDE_MIN_POINTS
                    and max(stats["span_x"], stats["span_y"])
                    <= self.GUIDE_MAX_SPAN_METERS
                ):
                    self._v156_guide = {
                        "schema": 1,
                        "source": "migrated-local-map",
                        "points": points,
                        "stats": stats,
                    }
                    self._v156_guide_cells = self._v156_cells_from_points(points)
            except Exception:
                pass
            return

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            points = list(data.get("points") or [])
            stats = self._v156_stats(points)
            if (
                stats["points"] >= self.GUIDE_MIN_POINTS
                and max(stats["span_x"], stats["span_y"])
                <= self.GUIDE_MAX_SPAN_METERS
            ):
                data["stats"] = stats
                self._v156_guide = data
                self._v156_guide_cells = self._v156_cells_from_points(points)
        except Exception:
            self._v156_guide = {}
            self._v156_guide_cells = set()

    def _v156_save_guide(self):
        stats = self._v156_stats(self._v156_candidate)
        valid = (
            stats["points"] >= self.GUIDE_MIN_POINTS
            and max(stats["span_x"], stats["span_y"])
            <= self.GUIDE_MAX_SPAN_METERS
        )
        if not valid:
            return False, stats

        path = self._v156_guide_path()
        if path is None:
            return False, stats
        payload = {
            "schema": 1,
            "source": "V156 learned route",
            "map_id": getattr(self.local_map, "active_map_id", None),
            "cell_m": self.GUIDE_CELL_METERS,
            "created_epoch": time.time(),
            "stats": stats,
            "points": list(self._v156_candidate),
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            tmp.replace(path)
            self._v156_guide = payload
            self._v156_guide_cells = self._v156_cells_from_points(
                self._v156_candidate
            )
            return True, stats
        except Exception:
            return False, stats

    def _v156_reset_live(self, learning=False):
        self._v156_learning = bool(learning)
        self._v156_mapping_started = False
        self._v156_started_at = 0.0
        self._v156_prestart_raw = None
        self._v156_base_raw = None
        self._v156_last_raw_mod = None
        self._v156_last_unwrapped = None
        self._v156_last_local = None
        self._v156_last_flush_at = time.monotonic()
        self._v156_base_saved = False
        self._v156_wrap_x = 0
        self._v156_wrap_y = 0
        self._v156_rejected_jumps = 0
        self._v156_map_samples = 0
        self._v156_guide_visited = set()
        self._v156_off_guide_samples = 0
        self._v156_last_guide_progress_at = 0.0
        self._v156_last_progress = {}
        self._v156_idle_notice_sent = False
        self._v156_live_motion = False
        if learning:
            self._v156_candidate = []
            self._v156_candidate_persisted = 0

    def _v156_unwrap_axis(self, raw, previous, axis):
        raw = float(raw)
        if previous is None:
            base = (
                self._v156_base_raw[0]
                if axis == "x" and self._v156_base_raw is not None
                else self._v156_base_raw[1]
                if axis == "y" and self._v156_base_raw is not None
                else raw
            )
            return raw + round((float(base) - raw) / self.RAW_WRAP_UNITS) * self.RAW_WRAP_UNITS

        value = raw + round(
            (float(previous) - raw) / self.RAW_WRAP_UNITS
        ) * self.RAW_WRAP_UNITS
        shift = int(round((value - raw) / self.RAW_WRAP_UNITS))
        if axis == "x":
            self._v156_wrap_x = shift
        else:
            self._v156_wrap_y = shift
        return value

    def _v156_note_progress(self, x, y):
        if not self._v156_guide_cells:
            return
        cell_m = float(self.GUIDE_CELL_METERS)
        cell = (int(round(x / cell_m)), int(round(y / cell_m)))
        nearby = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                probe = (cell[0] + dx, cell[1] + dy)
                if probe in self._v156_guide_cells:
                    nearby = probe
                    break
            if nearby is not None:
                break
        if nearby is None:
            self._v156_off_guide_samples += 1
        else:
            self._v156_guide_visited.add(nearby)

        coverage = (
            100.0 * len(self._v156_guide_visited) / len(self._v156_guide_cells)
            if self._v156_guide_cells
            else 0.0
        )
        self._v156_last_progress = {
            "coverage_pct": round(coverage, 1),
            "visited_cells": len(self._v156_guide_visited),
            "guide_cells": len(self._v156_guide_cells),
            "off_guide_samples": self._v156_off_guide_samples,
        }
        now = time.monotonic()
        if now - self._v156_last_guide_progress_at >= self.GUIDE_PROGRESS_SECONDS:
            self._v156_last_guide_progress_at = now
            self._post_ui("v156_guide_progress", dict(self._v156_last_progress))

    def _v156_flush_candidate(self, force=False):
        if not self._v156_learning or not self._v156_candidate:
            return False
        now = time.monotonic()
        if (
            not force
            and now - self._v156_last_flush_at < self.GUIDE_FLUSH_SECONDS
        ):
            return False

        new_points = self._v156_candidate[self._v156_candidate_persisted:]
        if new_points:
            try:
                self.local_map.merge_trajectory(new_points, phase=2)
                self._v156_candidate_persisted = len(self._v156_candidate)
            except Exception:
                return False

        if not self._v156_base_saved:
            try:
                self.local_map.set_charging_base(
                    {"x": 0.0, "y": 0.0, "angle": 0.0}
                )
                self._v156_base_saved = True
            except Exception:
                pass

        last = self._v156_candidate[-1]
        try:
            self.local_map.set_robot({
                "x": float(last["x"]),
                "y": float(last["y"]),
                "angle": float(last.get("phi", 0.0) or 0.0),
            })
        except Exception:
            pass

        self._v156_last_flush_at = now
        try:
            self._render_maps()
        except Exception:
            pass
        return True

    # ================================================ mapa LAN ultraliviano
    def _apply_map_state(self, state):
        if not isinstance(state, dict):
            return

        robot = state.get("robot")
        base = state.get("charging_base")
        rxy = self._v156_point_xy(robot)
        bxy = self._v156_point_xy(base)
        if bxy is not None:
            self._v156_base_raw = bxy
        elif self._v156_base_raw is None:
            self._v156_base_raw = (60.0, 60.0)

        try:
            status = int(getattr(self, "_v94_last_status_code", -1))
        except Exception:
            status = -1
        active_motion = bool(getattr(self, "mapping_active", False)) or status in (5, 6, 7)

        if not active_motion or rxy is None:
            if not bool(getattr(self, "mapping_active", False)):
                self._v156_live_motion = False
                self._v156_last_raw_mod = None
                self._v156_last_unwrapped = None
            return

        if bool(getattr(self, "mapping_active", False)) and not self._v156_mapping_started:
            return

        raw_x, raw_y = rxy
        if (
            bool(getattr(self, "mapping_active", False))
            and not self._v156_candidate
            and self._v156_prestart_raw is not None
            and abs(raw_x - self._v156_prestart_raw[0]) < 1e-6
            and abs(raw_y - self._v156_prestart_raw[1]) < 1e-6
        ):
            return

        previous = self._v156_last_unwrapped
        ux = self._v156_unwrap_axis(
            raw_x,
            previous[0] if previous is not None else None,
            "x",
        )
        uy = self._v156_unwrap_axis(
            raw_y,
            previous[1] if previous is not None else None,
            "y",
        )

        bx, by = self._v156_base_raw
        x = (ux - bx) * self.RAW_TO_METERS_V156
        y = (uy - by) * self.RAW_TO_METERS_V156
        angle = 0.0
        if isinstance(robot, dict):
            try:
                angle = float(
                    robot.get("angle", robot.get("phi", robot.get("yaw", 0.0)))
                    or 0.0
                )
            except Exception:
                angle = 0.0

        # Primer punto de un mapa debe salir físicamente cerca del dock. Evita
        # reutilizar la última 10/24 de la limpieza anterior.
        if previous is None and bool(getattr(self, "mapping_active", False)):
            distance = math.hypot(x, y)
            age = max(0.0, time.monotonic() - self._v156_started_at)
            if distance > 1.50 and age < 30.0:
                return

        if previous is not None:
            step = math.hypot(ux - previous[0], uy - previous[1]) * self.RAW_TO_METERS_V156
            # Tras desempaquetar módulo 256 ya no deberían existir saltos de
            # 25.5 m. Un salto residual enorme es una muestra obsoleta.
            if step > 4.0:
                self._v156_rejected_jumps += 1
                return

        self._v156_last_raw_mod = (raw_x, raw_y)
        self._v156_last_unwrapped = (ux, uy)
        self._v156_last_local = (x, y, angle)
        self._v156_live_motion = True
        self._v156_map_samples += 1
        self._v156_note_progress(x, y)

        if not bool(getattr(self, "mapping_active", False)):
            return

        previous_local = None
        if self._v156_candidate:
            previous_local = self._v156_point_xy(self._v156_candidate[-1])
        if previous_local is not None:
            if math.hypot(x - previous_local[0], y - previous_local[1]) < self.GUIDE_SAMPLE_METERS:
                return

        point = {
            "id": len(self._v156_candidate) + 1,
            "phase": 2,
            "x": float(x),
            "y": float(y),
            "phi": float(angle),
            "update": 1,
        }
        self._v156_candidate.append(point)
        self._v156_flush_candidate(force=False)

    # ================================================ recorrido visible/guía
    def _v87_draw_route(self, canvas, snapshot, xy, width=2):
        # El recorrido V156 ya está simplificado a >=25 cm. Si aun así fuese
        # enorme, reducimos sólo la representación, nunca los datos aprendidos.
        clone = dict(snapshot or {})
        points = list(clone.get("points") or [])
        if len(points) > 700:
            stride = max(1, int(math.ceil(len(points) / 700.0)))
            sampled = points[::stride]
            if points and sampled[-1] is not points[-1]:
                sampled.append(points[-1])
            clone["points"] = sampled
        return app_v87.App._v87_draw_route(self, canvas, clone, xy, width=1)

    # =============================================================== mapeo
    def start_new_mapping(self):
        vacuum = getattr(self, "vacuum", None)
        if vacuum is None:
            messagebox.showwarning(
                "Robot desconectado",
                "Primero conectá el Xiaomi Vacuum E10.",
                parent=self,
            )
            return
        if bool(getattr(self, "mapping_active", False)) or bool(self._v155_mapping_owner):
            messagebox.showinfo("Mapeo en curso", "Ya hay un mapeo activo.", parent=self)
            return

        core = self._fresh()
        if bool(core.diagnostic().get("active")):
            messagebox.showinfo(
                "Robot ocupado",
                "Esperá a que termine la sesión actual antes de mapear.",
                parent=self,
            )
            return

        ok = messagebox.askyesno(
            "Mapear vivienda · V156",
            "V156 va a aprender una guía de recorrido mientras el E10 navega "
            "por sí mismo.\n\n"
            "Ruta física: build-map oficial 10/17 + un único START 2/1. "
            "No se usa 2/3, 7/3, EDGE, control remoto ni recoveries.\n\n"
            "La app además corrige el wrap 0-255 de 10/24 para que un cruce "
            "de coordenadas no se convierta en un salto falso de 25,5 m.\n\n"
            "Dejá abiertas las puertas y empezá con el robot en la base.",
            parent=self,
        )
        if not ok:
            return

        self._v156_reset_live(learning=True)
        self._v155_mapping_serial += 1
        serial = self._v155_mapping_serial
        self._v155_mapping_owner = True
        self.mapping_active = True
        self.mapping_phase = 2
        self.mapping_seen_moving = False
        self.mapping_transitioning = False
        self.mapping_step1_complete = True
        self.mapping_step2_complete = False
        self._v155_mapping_diag = {
            "serial": serial,
            "route": "read/precheck -> 10/17 build-map-ii(1) -> A2/1 unico",
            "build": None,
            "start_response": None,
            "started": False,
            "finish_reason": None,
            "read_errors": 0,
            "idle_observed": False,
            "error": None,
        }

        try:
            self._v151_prepare_map_layers()
        except Exception:
            pass
        try:
            self._v74_reset_session()
        except Exception:
            pass
        try:
            self.local_map.clear_map(keep_rooms=False)
            self.selected_point = None
        except Exception:
            pass
        try:
            self.show_page("map")
            self._sync_mapping_step_buttons()
            self._render_maps()
        except Exception:
            pass

        self._set_banner(
            "V156 · aprendiendo guía · build-map + único START 2/1 · UI liviana."
        )
        threading.Thread(
            target=self._v155_mapping_worker,
            args=(vacuum, core, serial),
            name="V156LeanMapping",
            daemon=True,
        ).start()

    def _v155_mapping_worker(self, vacuum, core, serial):
        diag = self._v155_mapping_diag
        session = None
        try:
            session = core.arbiter.begin("v156-guide-mapping", "gui")
            diag["session_id"] = session.session_id
            before = core._factory_like_precheck()
            diag["before"] = before
            try:
                parsed = vacuum.parse_position(before.get("robot"))
                if parsed:
                    self._v156_prestart_raw = (
                        float(parsed["x"]),
                        float(parsed["y"]),
                    )
            except Exception:
                self._v156_prestart_raw = None

            with core.arbiter._io_lock:
                if session.cancel_action:
                    raise RuntimeError("Mapeo cancelado antes de crear el mapa.")

                response = core.raw_device.call_action_by(10, 17, [1])
                code = vacuum._miot_action_code(response)
                ack = vacuum._miot_action_ack(response)
                empty_ack = vacuum._miot_b112_empty_result_ack(response)
                timestamp = vacuum._miot_output_value(response, 18)
                accepted = (
                    code == 0
                    or bool(ack)
                    or bool(empty_ack)
                    or timestamp is not None
                )
                diag["build"] = {
                    "action": (10, 17),
                    "response": vacuum._miot_action_response_summary(response),
                    "code": code,
                    "ack": bool(ack),
                    "b112_empty_ack": bool(empty_ack),
                    "timestamp": timestamp,
                    "accepted": bool(accepted),
                }
                core.arbiter.record("v156_map_build", diag["build"])
                if code is not None and code != 0:
                    raise RuntimeError(f"build-map 10/17 rechazado (code={code}).")
                if not accepted:
                    raise RuntimeError(
                        "build-map 10/17 no entregó un ACK reconocible; "
                        "se canceló sin mover el robot."
                    )

                if session.cancel_action:
                    raise RuntimeError("Mapeo cancelado antes del START.")

                start_response = core.raw_device.call_action_by(2, 1)
                start_code = core._explicit_code(start_response)
                if start_code is not None and start_code != 0:
                    raise RuntimeError(
                        f"START 2/1 rechazado por el E10 (code={start_code})."
                    )
                diag["start_response"] = repr(start_response)[:500]
                core.arbiter.record("v156_map_start", {
                    "siid": 2,
                    "aiid": 1,
                    "response": repr(start_response)[:220],
                })

            deadline = time.monotonic() + self.MAP_CONFIRM_TIMEOUT
            while time.monotonic() < deadline:
                try:
                    state = core._read()
                    status = core._int(state.get("status"))
                    diag["last_status"] = status
                    if status in (5, 6, 7):
                        diag["started"] = True
                        diag["started_state"] = state
                        self._v156_mapping_started = True
                        self._v156_started_at = time.monotonic()
                        self._post_ui("v155_mapping_started", serial, dict(diag))
                        break
                except Exception as exc:
                    diag["read_errors"] += 1
                    diag["last_read_error"] = str(exc).strip() or type(exc).__name__
                time.sleep(0.5)

            if not diag["started"]:
                raise RuntimeError("El START 2/1 no confirmó movimiento físico.")

            end_deadline = time.monotonic() + self.MAPPING_WAIT_SECONDS
            idle_streak = 0
            while self._v155_mapping_owner and serial == self._v155_mapping_serial:
                if session.cancel_action:
                    with core.arbiter._io_lock:
                        action = str(session.cancel_action)
                        session.cancel_action = None
                        if action == "dock":
                            core._action_locked(3, 1, "v156 dock user")
                            diag["user_dock"] = True
                        else:
                            core._action_locked(2, 2, "v156 stop user")
                            diag["finish_reason"] = "stop_requested"
                            break

                try:
                    state = core._read()
                    status = core._int(state.get("status"))
                    diag["last_status"] = status
                    diag["last_state"] = state

                    if status == 4:
                        diag["finish_reason"] = (
                            "dock_requested" if diag.get("user_dock") else "dock"
                        )
                        break

                    if status in (0, 1):
                        idle_streak += 1
                        diag["idle_observed"] = True
                        if idle_streak >= 3 and not self._v156_idle_notice_sent:
                            self._v156_idle_notice_sent = True
                            self._post_ui("v156_waiting_dock", serial)
                    else:
                        idle_streak = 0
                except Exception as exc:
                    diag["read_errors"] += 1
                    diag["last_read_error"] = str(exc).strip() or type(exc).__name__

                if time.monotonic() >= end_deadline:
                    diag["finish_reason"] = "timeout_waiting_dock"
                    break
                time.sleep(2.0)

        except Exception as exc:
            diag["error"] = str(exc).strip() or type(exc).__name__
        finally:
            if session is not None:
                core.arbiter.finish(
                    session,
                    diag.get("error") or diag.get("finish_reason") or "finished",
                )
            self._post_ui("v155_mapping_finished", serial, dict(diag))

    # =============================================================== eventos
    def _handle_ui_event(self, kind, payload):
        if kind == "v155_mapping_started":
            serial = int(payload[0]) if payload else -1
            if serial != self._v155_mapping_serial:
                return None
            self.mapping_seen_moving = True
            self._set_banner(
                "V156 · guía en aprendizaje · E10 navega solo · coordenadas 10/24 sin wrap falso."
            )
            return None

        if kind == "v156_waiting_dock":
            serial = int(payload[0]) if payload else -1
            if serial != self._v155_mapping_serial:
                return None
            self._set_banner(
                "V156 · E10 quedó en espera/sin batería. Mantengo el mapa abierto "
                "hasta que vuelva a status=4 en la base."
            )
            return None

        if kind == "v156_guide_progress":
            progress = dict(payload[0] or {}) if payload else {}
            if progress.get("guide_cells"):
                self._set_banner(
                    "V156 · siguiendo guía: "
                    f"{progress.get('coverage_pct', 0):.1f}% de celdas de referencia visitadas."
                )
            return None

        if kind == "v155_mapping_finished":
            serial = int(payload[0]) if payload else -1
            diag = dict(payload[1] or {}) if len(payload) > 1 else {}
            if serial != self._v155_mapping_serial:
                return None

            self._v156_flush_candidate(force=True)
            committed = False
            stats = self._v156_stats(self._v156_candidate)
            if not diag.get("error") and diag.get("finish_reason") in (
                "dock",
                "dock_requested",
            ):
                committed, stats = self._v156_save_guide()

            self._v155_mapping_owner = False
            self._v156_learning = False
            self.mapping_active = False
            self.mapping_phase = 0
            self.mapping_transitioning = False
            self.mapping_step2_complete = bool(committed)
            self._v155_mapping_diag = diag

            if diag.get("error"):
                self._set_banner(
                    "V156 · mapeo terminó con error: " + str(diag["error"])
                )
            elif committed:
                try:
                    self.local_map.set_robot(
                        {"x": 0.0, "y": 0.0, "angle": 0.0}
                    )
                except Exception:
                    pass
                self._set_banner(
                    "V156 · guía aprendida y guardada · "
                    f"{stats['points']} puntos · "
                    f"{stats['span_x']:.1f}×{stats['span_y']:.1f} m."
                )
            else:
                self._set_banner(
                    "V156 · recorrido conservado, pero la guía no se confirmó "
                    "porque no terminó físicamente en la base o la escala no fue plausible."
                )

            try:
                self._render_maps()
            except Exception:
                pass
            return None

        return super()._handle_ui_event(kind, payload)

    # =========================================================== diagnóstico
    def _diagnostic_text(self):
        core = getattr(self, "_fresh_core", None)
        core_diag = core.diagnostic() if core is not None else {}
        guide_stats = dict((self._v156_guide or {}).get("stats") or {})
        candidate_stats = self._v156_stats(self._v156_candidate)
        lines = [
            "V156 LEAN + GUÍA · START 2/1",
            "=============================",
            f"mapeo activo={bool(self._v155_mapping_owner)} · learning={self._v156_learning}",
            f"último mapeo={self._v155_mapping_diag or '—'}",
            (
                "coordenadas: wrap 256 activo · "
                f"wrapX={self._v156_wrap_x} · wrapY={self._v156_wrap_y} · "
                f"saltos residuales rechazados={self._v156_rejected_jumps}"
            ),
            f"última pose local={self._v156_last_local or '—'}",
            (
                "candidato guía: "
                f"{candidate_stats['points']} pts · "
                f"{candidate_stats['span_x']:.2f}×{candidate_stats['span_y']:.2f} m · "
                f"{candidate_stats['path_m']:.1f} m"
            ),
            (
                "guía guardada: "
                f"{guide_stats.get('points', 0)} pts · "
                f"{guide_stats.get('span_x', 0.0):.2f}×"
                f"{guide_stats.get('span_y', 0.0):.2f} m · "
                f"celdas={len(self._v156_guide_cells)}"
            ),
            f"progreso sobre guía={self._v156_last_progress or '—'}",
            (
                "rendimiento: "
                f"LAN polls={getattr(self, '_v95_local_polls_started', 0)} · "
                f"UI eventos={getattr(self, '_v96_ui_events_processed', 0)} · "
                f"batches={getattr(self, '_v96_ui_batches', 0)} · "
                f"renders={getattr(self, '_v96_render_executed', 0)}"
            ),
            (
                "Cloud de recorrido=DESACTIVADO · "
                f"llamadas evitadas={self._v156_cloud_calls_blocked}"
            ),
            (
                "writes heredados bloqueados="
                f"{core_diag.get('legacy_blocks', 0)} · "
                f"último={core_diag.get('last_legacy_block') or '—'}"
            ),
            "ruta física mapeo: precheck -> 10/17 build-map-ii(1) -> UN A2/1",
            "status 0/1 no cierra el mapa: V156 espera el regreso real a status=4",
            "2/3, 7/3, EDGE, remoto, recoveries y Cloud de trayectoria siguen fuera",
        ]
        return "\n".join(lines) + "\n"


if __name__ == "__main__":
    app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        app_v9._save_crash_log(app_v9.traceback.format_exc())
        raise
