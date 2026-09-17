import math
import statistics
import threading
import time
import tkinter as tk
from tkinter import messagebox

import app_v13

# Las constantes visuales viven en app_v8; los módulos intermedios no reexportan
# todas ellas. Usamos esa fuente estable para evitar errores al arrancar.
_PALETTE = app_v13.app_v12.app_v11.app_v10.app_v9.app_v8
CARD = _PALETTE.CARD
GREEN = _PALETTE.GREEN
MUTED = _PALETTE.MUTED
ACCENT = _PALETTE.ACCENT


class App(app_v13.App):
    """v14: paredes/perímetro en vivo + recuperación automática de atascos."""

    STALL_SECONDS = 9.5
    MAX_UNSTICK_ATTEMPTS = 3

    def __init__(self):
        self._anti_stall_last_pose = None
        self._anti_stall_last_motion_at = time.monotonic()
        self._anti_stall_worker = False
        self._anti_stall_attempts = 0
        self._anti_stall_cooldown_until = 0.0
        self._anti_stall_abort_sent = False
        super().__init__()
        if hasattr(self, "mapping_steps_info"):
            self.mapping_steps_info.configure(
                text="Paredes/perímetro EN VIVO · Paso 1 → base → Paso 2 automático · antibloqueo activo"
            )

    # ------------------------------------------------------------- UI mapa
    def _build_map_page(self):
        super()._build_map_page()
        parent = self.map_status_label.master
        self.anti_stall_label = tk.Label(
            parent,
            text="Antibloqueo · activo",
            bg=CARD,
            fg=GREEN,
            font=("Segoe UI", 8, "bold"),
        )
        self.anti_stall_label.pack(side="left", padx=(12, 0))

    def _handle_ui_event(self, kind, payload):
        if kind == "unstick_started":
            attempt = int(payload[0])
            if hasattr(self, "anti_stall_label"):
                self.anti_stall_label.configure(
                    text=f"Antibloqueo · liberando {attempt}/{self.MAX_UNSTICK_ATTEMPTS}",
                    fg=ACCENT,
                )
            self._set_banner(
                f"Antibloqueo · el E10 lleva varios segundos sin avanzar. "
                f"Ejecutando maniobra de liberación {attempt}/{self.MAX_UNSTICK_ATTEMPTS}…"
            )
            return

        if kind == "unstick_done":
            attempt = int(payload[0])
            self._anti_stall_worker = False
            self._anti_stall_cooldown_until = time.monotonic() + 6.0
            self._anti_stall_last_pose = None
            self._anti_stall_last_motion_at = time.monotonic()
            if hasattr(self, "anti_stall_label"):
                self.anti_stall_label.configure(text="Antibloqueo · comprobando movimiento…", fg=GREEN)
            self._set_banner(
                f"Antibloqueo · maniobra {attempt} completada. Verificando que el E10 vuelva a avanzar…"
            )
            return

        if kind == "unstick_error":
            self._anti_stall_worker = False
            self._anti_stall_cooldown_until = time.monotonic() + 8.0
            if hasattr(self, "anti_stall_label"):
                self.anti_stall_label.configure(text="Antibloqueo · reintentará", fg=ACCENT)
            self._set_banner(f"Antibloqueo · la maniobra falló: {payload[0]}. Voy a reintentar si sigue quieto.")
            return

        if kind == "unstick_abort":
            self._anti_stall_worker = False
            self._anti_stall_abort_sent = True
            self.mapping_active = False
            self.mapping_phase = 0
            self.mapping_transitioning = False
            self._auto_step2_pending = False
            self._auto_step2_scheduled = False
            self._sync_mapping_step_buttons()
            self._render_maps()
            if hasattr(self, "anti_stall_label"):
                self.anti_stall_label.configure(text="Antibloqueo · requiere ayuda", fg="#d93025")
            message = str(payload[0])
            self._set_banner(message)
            messagebox.showwarning("Antibloqueo", message, parent=self)
            return

        return super()._handle_ui_event(kind, payload)

    # ------------------------------------------------------ telemetría rápida
    def _apply_map_state(self, state):
        super()._apply_map_state(state)
        self._anti_stall_observe(state)

    def _schedule_next_map_poll(self):
        if self._closing or not self.vacuum:
            self.map_polling = False
            return
        if self.mapping_active:
            delay = 340
        elif self._last_robot_status in (3, 5, 6, 7):
            delay = 650
        else:
            delay = 2200
        self.after(delay, self._poll_local_map)

    # -------------------------------------------------------- paredes en vivo
    @staticmethod
    def _split_wall_segments(points):
        if len(points) < 2:
            return []
        distances = []
        for a, b in zip(points, points[1:]):
            try:
                d = math.hypot(float(b["x"]) - float(a["x"]), float(b["y"]) - float(a["y"]))
            except Exception:
                continue
            if math.isfinite(d) and d > 0:
                distances.append(d)
        typical = statistics.median(distances) if distances else 0.0
        gap_limit = typical * 5.0 if typical > 0 else float("inf")

        segments = [[points[0]]]
        for point in points[1:]:
            prev = segments[-1][-1]
            try:
                d = math.hypot(float(point["x"]) - float(prev["x"]), float(point["y"]) - float(prev["y"]))
            except Exception:
                continue
            if d > gap_limit and len(segments[-1]) > 1:
                segments.append([point])
            else:
                segments[-1].append(point)
        return [segment for segment in segments if len(segment) > 1]

    def _render_map_canvas(self, canvas, snapshot):
        super()._render_map_canvas(canvas, snapshot)
        transform = self._map_transforms.get(canvas)
        if not transform:
            return

        points = [
            p for p in (snapshot.get("points", []) or [])
            if int(p.get("phase", 0) or 0) == 1
        ]
        if len(points) < 2:
            return

        scale = transform["scale"]
        min_x = transform["min_x"]
        max_y = transform["max_y"]
        pad = transform["pad"]

        def to_screen(x, y):
            return pad + (float(x) - min_x) * scale, pad + (max_y - float(y)) * scale

        # El E10 no entrega una nube LiDAR de pared. Durante EDGE, su trayectoria
        # sigue el contorno; la mostramos como pared/perímetro estimado en vivo.
        for segment in self._split_wall_segments(points):
            coords = []
            for point in segment:
                coords.extend(to_screen(point["x"], point["y"]))
            if len(coords) < 4:
                continue
            canvas.create_line(
                *coords,
                fill="#49515c",
                width=8,
                capstyle=tk.ROUND,
                joinstyle=tk.ROUND,
            )
            canvas.create_line(
                *coords,
                fill=ACCENT,
                width=3,
                capstyle=tk.ROUND,
                joinstyle=tk.ROUND,
            )

        last = points[-1]
        x, y = to_screen(last["x"], last["y"])
        canvas.create_oval(x - 5, y - 5, x + 5, y + 5, fill=ACCENT, outline="white", width=2)

        if canvas is getattr(self, "map_canvas", None):
            canvas.create_rectangle(12, 48, 248, 76, fill=CARD, outline="#e8eaed")
            canvas.create_text(
                22,
                62,
                text=f"PAREDES EN VIVO · {len(points)} puntos de borde",
                anchor="w",
                fill=GREEN if self.mapping_phase == 1 else MUTED,
                font=("Segoe UI", 8, "bold"),
            )

    # ---------------------------------------------------------- antibloqueo
    @staticmethod
    def _pose_from_state(state):
        robot = state.get("robot") if isinstance(state, dict) else None
        if isinstance(robot, dict):
            try:
                return (
                    float(robot["x"]),
                    float(robot["y"]),
                    float(robot.get("angle", 0) or 0),
                )
            except Exception:
                pass
        path = state.get("path") if isinstance(state, dict) else None
        if path:
            try:
                last = path[-1]
                return (
                    float(last["x"]),
                    float(last["y"]),
                    float(last.get("phi", 0) or 0),
                )
            except Exception:
                pass
        return None

    @staticmethod
    def _motion_epsilon(state):
        path = state.get("path") if isinstance(state, dict) else None
        if not path or len(path) < 3:
            return 1e-4
        distances = []
        recent = path[-10:]
        for a, b in zip(recent, recent[1:]):
            try:
                d = math.hypot(float(b["x"]) - float(a["x"]), float(b["y"]) - float(a["y"]))
            except Exception:
                continue
            if math.isfinite(d) and d > 0:
                distances.append(d)
        if not distances:
            return 1e-4
        return max(statistics.median(distances) * 0.12, 1e-6)

    @staticmethod
    def _angle_moved(a, b):
        try:
            a = float(a)
            b = float(b)
        except Exception:
            return False
        max_abs = max(abs(a), abs(b))
        threshold = 0.08 if max_abs <= math.tau * 2.0 else 5.0
        return abs(a - b) >= threshold

    def _reset_anti_stall_monitor(self):
        self._anti_stall_last_pose = None
        self._anti_stall_last_motion_at = time.monotonic()
        self._anti_stall_attempts = 0
        self._anti_stall_abort_sent = False
        if hasattr(self, "anti_stall_label"):
            self.anti_stall_label.configure(text="Antibloqueo · activo", fg=GREEN)

    def _anti_stall_observe(self, state):
        if not self.vacuum or self._anti_stall_abort_sent:
            return
        status = int(self._last_robot_status)
        if status not in (5, 6, 7):
            if not self._anti_stall_worker:
                self._anti_stall_last_pose = None
                self._anti_stall_last_motion_at = time.monotonic()
                self._anti_stall_attempts = 0
            return

        pose = self._pose_from_state(state)
        if pose is None:
            return

        now = time.monotonic()
        if self._anti_stall_last_pose is None:
            self._anti_stall_last_pose = pose
            self._anti_stall_last_motion_at = now
            return

        prev = self._anti_stall_last_pose
        moved = math.hypot(pose[0] - prev[0], pose[1] - prev[1])
        eps = self._motion_epsilon(state)
        rotated = self._angle_moved(pose[2], prev[2])

        if moved >= eps or rotated:
            self._anti_stall_last_pose = pose
            self._anti_stall_last_motion_at = now
            self._anti_stall_attempts = 0
            if hasattr(self, "anti_stall_label") and not self._anti_stall_worker:
                self.anti_stall_label.configure(text="Antibloqueo · movimiento OK", fg=GREEN)
            return

        if self._anti_stall_worker or now < self._anti_stall_cooldown_until:
            return
        stalled_for = now - self._anti_stall_last_motion_at
        if stalled_for < self.STALL_SECONDS:
            return

        if self._anti_stall_attempts >= self.MAX_UNSTICK_ATTEMPTS:
            self._anti_stall_worker = True
            vacuum = self.vacuum
            threading.Thread(
                target=self._anti_stall_abort_worker,
                args=(vacuum,),
                daemon=True,
            ).start()
            return

        self._anti_stall_attempts += 1
        attempt = self._anti_stall_attempts
        self._anti_stall_worker = True
        vacuum = self.vacuum
        phase = int(self.mapping_phase or 0)
        self._post_ui("unstick_started", attempt)
        threading.Thread(
            target=self._anti_stall_recovery_worker,
            args=(vacuum, attempt, phase),
            daemon=True,
        ).start()

    def _anti_stall_recovery_worker(self, vacuum, attempt, phase):
        try:
            values = vacuum._get_many([
                ("status", 2, 1),
                ("mode", 2, 4),
                ("sweep_type", 2, 8),
            ])
            status = int(values.get("status", -1) if values.get("status") is not None else -1)
            mode = int(values.get("mode", 0) if values.get("mode") is not None else 0)
            sweep_type = int(values.get("sweep_type", 0) if values.get("sweep_type") is not None else 0)
            if status not in (5, 6, 7):
                self._post_ui("unstick_done", attempt)
                return

            try:
                vacuum.set_sweep_type(5)
            except Exception:
                pass

            back_time = 0.65 + (attempt * 0.18)
            turn_time = 0.45 + (attempt * 0.16)
            forward_time = 0.45 + (attempt * 0.12)
            turn = 2 if attempt % 2 else 3

            vacuum.manual(4)
            time.sleep(back_time)
            vacuum.manual(5)
            time.sleep(0.15)
            vacuum.manual(turn)
            time.sleep(turn_time)
            vacuum.manual(5)
            time.sleep(0.15)
            vacuum.manual(1)
            time.sleep(forward_time)
            vacuum.manual(5)
            time.sleep(0.15)
            vacuum.manual(10)

            target_sweep = 2 if phase == 1 else (0 if phase == 2 else sweep_type)
            if target_sweep in (0, 2, 4):
                try:
                    vacuum.set_sweep_type(target_sweep)
                except Exception:
                    pass

            time.sleep(0.5)
            state = vacuum._get_many([("status", 2, 1)])
            resumed_status = int(state.get("status", -1) if state.get("status") is not None else -1)
            if resumed_status not in (5, 6, 7):
                if phase == 1:
                    vacuum.start_mapping_perimeter()
                elif phase == 2:
                    vacuum.start_mapping_interior()
                else:
                    vacuum.start(max(0, min(2, mode)))

            self._post_ui("unstick_done", attempt)
        except Exception as exc:
            try:
                vacuum.manual(5)
                vacuum.manual(10)
            except Exception:
                pass
            self._post_ui("unstick_error", str(exc).strip() or "el robot rechazó la maniobra")

    def _anti_stall_abort_worker(self, vacuum):
        try:
            try:
                vacuum.stop()
            except Exception:
                pass
            self._post_ui(
                "unstick_abort",
                "El E10 sigue sin avanzar después de 3 maniobras automáticas. "
                "Detuve el mapeo para no dejar las ruedas forzando contra un obstáculo.",
            )
        except Exception as exc:
            self._post_ui("unstick_error", str(exc).strip() or "no pude detener el robot")


if __name__ == "__main__":
    app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise
