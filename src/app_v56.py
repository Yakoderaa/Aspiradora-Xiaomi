import threading

import app_v55
from xiaomi_e10_map_v56 import XiaomiE10MapV56


class App(app_v55.App):
    """V56: mapa funcional B112 desde upload realtime oficial + rejilla 2bpp."""

    def __init__(self):
        self._v56_diag = {}
        self._v56_grid_cells = []
        self._v56_grid_side = 0
        self._v56_grid_resolution = 0.1
        self._v56_grid_base_cell = (60.0, 60.0)
        self._v56_grid_counts = {}
        self._v56_grid_order = None
        self._v56_grid_walls = []
        self._v56_grid_diff = {}
        self._v56_grid_timestamp = None
        self._v56_grid_blob_sha12 = None
        self._v56_last_applied_signature = None
        super().__init__()

    # -------------------------------------------------------- cliente Cloud
    def _v40_map_client(self, vacuum, settings):
        if self._v40_client is None or self._v40_client_vacuum is not vacuum:
            self._v40_client = XiaomiE10MapV56(vacuum, settings)
            self._v40_client_vacuum = vacuum
        return self._v40_client

    # ------------------------------------------------------------ grid state
    def _v56_capture_snapshot(self, snapshot):
        if snapshot is None or not hasattr(snapshot, "grid_cells"):
            return False

        self._v56_grid_cells = list(getattr(snapshot, "grid_cells", []) or [])
        self._v56_grid_side = int(getattr(snapshot, "grid_side", 0) or 0)
        self._v56_grid_resolution = float(
            getattr(snapshot, "grid_resolution", 0.1) or 0.1
        )
        self._v56_grid_base_cell = tuple(
            getattr(snapshot, "grid_base_cell", (60.0, 60.0)) or (60.0, 60.0)
        )
        self._v56_grid_counts = dict(getattr(snapshot, "grid_counts", {}) or {})
        self._v56_grid_order = getattr(snapshot, "grid_order", None)
        self._v56_grid_walls = list(getattr(snapshot, "grid_walls", []) or [])
        self._v56_grid_diff = dict(getattr(snapshot, "grid_diff", {}) or {})
        self._v56_grid_timestamp = getattr(snapshot, "upload_date", None)
        self._v56_grid_blob_sha12 = getattr(snapshot, "grid_blob_sha12", None)

        signature = (
            self._v56_grid_blob_sha12,
            self._v56_grid_timestamp,
            tuple(sorted(self._v56_grid_counts.items())),
            len(self._v56_grid_walls),
        )
        if self.local_map and signature != self._v56_last_applied_signature:
            self.local_map.set_mapped_walls(self._v56_grid_walls)
            self._v56_last_applied_signature = signature
        return True

    def _v56_apply_static_pose(self, snapshot):
        """Muestra base/robot del grid sin declararlo movimiento."""
        if not self.local_map or snapshot is None:
            return
        base = getattr(snapshot, "raw_base", None)
        robot = getattr(snapshot, "raw_robot", None)
        if base is None:
            return
        try:
            bx, by = float(base[0]), float(base[1])
            self.local_map.set_charging_base({"x": 0.0, "y": 0.0, "angle": 0.0})
            if robot is not None:
                rx, ry = float(robot[0]), float(robot[1])
                self.local_map.set_robot({
                    "x": rx - bx,
                    "y": ry - by,
                    "angle": 0.0,
                })
        except Exception:
            return

    # ------------------------------------------------------------ eventos UI
    def _handle_ui_event(self, kind, payload):
        snapshot = payload[0] if kind == "cloud_ijai_map_state_v40" and payload else None
        had_grid = self._v56_capture_snapshot(snapshot) if snapshot is not None else False

        result = super()._handle_ui_event(kind, payload)

        if kind in ("cloud_ijai_map_state_v40", "cloud_ijai_map_error_v40"):
            client = getattr(self, "_v40_client", None)
            self._v56_diag = dict(
                getattr(client, "last_v56_diagnostics", {}) or {}
            ) if client else {}

        if kind == "cloud_ijai_map_state_v40" and had_grid:
            # Si todavía no hubo dos cambios temporales de grid, esto sólo ubica
            # la pose sin convertirla en trayectoria/movimiento confirmado.
            if len(getattr(snapshot, "raw_path", []) or []) < 2:
                self._v56_apply_static_pose(snapshot)

            try:
                nonzero = sum(
                    count for value, count in self._v56_grid_counts.items()
                    if int(value) != 0
                )
                track = len(getattr(snapshot, "raw_path", []) or [])
                suffix = (
                    f" · trayectoria por cambios de mapa: {track} puntos"
                    if track >= 2 else ""
                )
                self.map_status_label.configure(
                    text=(
                        f"Mapa realtime B112 · {nonzero} celdas conocidas · "
                        f"{len(self._v56_grid_walls)} contornos{suffix}"
                    )
                )
                self.mapping_steps_info.configure(
                    text=(
                        "Mapa obtenido del upload realtime oficial de Xiaomi · "
                        "rejilla 120×120 persistida localmente"
                    )
                )
            except Exception:
                pass
            self._render_maps()
        return result

    # --------------------------------------------------------------- renderer
    def _render_map_canvas(self, canvas, snapshot):
        result = super()._render_map_canvas(canvas, snapshot)

        cells = self._v56_grid_cells
        side = int(self._v56_grid_side or 0)
        transform = self._map_transforms.get(canvas)
        if not cells or side <= 0 or len(cells) != side * side or not transform:
            return result

        scale = float(transform["scale"])
        min_x = float(transform["min_x"])
        max_y = float(transform["max_y"])
        pad = float(transform["pad"])
        pan_x = float(transform.get("pan_x", 0.0) or 0.0)
        pan_y = float(transform.get("pan_y", 0.0) or 0.0)
        if canvas is getattr(self, "home_map_canvas", None):
            try:
                hx, hy = self._home_map_pan
                pan_x += float(hx)
                pan_y += float(hy)
            except Exception:
                pass

        bx, by = self._v56_grid_base_cell
        res = float(self._v56_grid_resolution)

        def to_screen(x, y):
            return (
                pad + (float(x) - min_x) * scale + pan_x,
                pad + (max_y - float(y)) * scale + pan_y,
            )

        fills = {
            1: "#e2e8f0",
            2: "#cbd5e1",
            3: "#94a3b8",
        }

        # Run-length horizontal: una habitación llena produce decenas de
        # rectángulos, no miles de celdas Tk individuales.
        for gy in range(side):
            gx = 0
            while gx < side:
                value = int(cells[gy * side + gx])
                if value == 0:
                    gx += 1
                    continue
                end = gx + 1
                while end < side and int(cells[gy * side + end]) == value:
                    end += 1

                x0 = (float(gx) - float(bx)) * res
                x1 = (float(end) - float(bx)) * res
                y0 = (float(by) - float(gy)) * res
                y1 = (float(by) - float(gy + 1)) * res
                sx0, sy0 = to_screen(x0, y0)
                sx1, sy1 = to_screen(x1, y1)
                canvas.create_rectangle(
                    min(sx0, sx1), min(sy0, sy1),
                    max(sx0, sx1), max(sy0, sy1),
                    fill=fills.get(value, "#cbd5e1"),
                    outline="",
                    tags=("v56_grid",),
                )
                gx = end

        try:
            canvas.tag_lower("v56_grid")
            for tag in ("mapped_wall", "pose_v34", "robot_v35", "robot_v34"):
                canvas.tag_raise(tag)
        except Exception:
            pass
        return result

    # ------------------------------------------------------------- diagnóstico
    @staticmethod
    def _upload_line(item):
        if not isinstance(item, dict):
            return "—"
        return (
            f"{item.get('action') or '—'} {item.get('label') or ''} · "
            f"ok={bool(item.get('ok'))} · code={item.get('code')!r} · "
            f"map_id={item.get('map_id')!r} · type={item.get('map_type')!r} · "
            f"timestamp={item.get('timestamp')!r} · renew={item.get('renew_map')!r} · "
            f"hash {item.get('hash_before') or '—'}→{item.get('hash_after') or '—'} · "
            f"cambió={bool(item.get('changed'))}"
        )

    def _diagnostic_text(self):
        client = getattr(self, "_v40_client", None)
        if client is not None:
            self._v56_diag = dict(
                getattr(client, "last_v56_diagnostics", {}) or {}
            )
            upload = dict(
                getattr(client, "last_v56_upload_diagnostics", {}) or {}
            )
        else:
            upload = {}

        diag = dict(self._v56_diag or {})
        slots = dict(diag.get("slots") or {})
        inherited = super()._diagnostic_text()

        lines = [
            "DIAGNÓSTICO V56 ACTIVO · mapa B112 funcional",
            "================================================",
            f"ruta: {diag.get('route') or '—'} · éxito mapa: {bool(diag.get('success'))}",
            "refresco realtime oficial: 10/18 → 10/15(type=0) → 10/6(type=0), deteniéndose cuando cambia el blob",
            f"hash inicial: {upload.get('baseline_hash') or '—'} · final: {upload.get('hash_after') or '—'} · "
            f"cambio confirmado: {bool(upload.get('changed'))} · ganador: {upload.get('winner') or '—'}",
            f"privacidad antes: {upload.get('privacy_before')!r} · habilitación temporal: {bool(upload.get('privacy_temp'))}",
        ]
        for item in list(upload.get("attempts") or []):
            lines.append("    " + self._upload_line(item))

        lines.extend([
            f"slot ganador: {diag.get('winner_slot') or '—'} · timestamp header: {diag.get('header_timestamp')!r}",
            f"rejilla: orden={diag.get('grid_order') or self._v56_grid_order or '—'} · "
            f"conteos={diag.get('grid_counts') or self._v56_grid_counts or {}}",
            f"contornos aplicados: {int(diag.get('walls', len(self._v56_grid_walls)) or 0)} · "
            f"trayectoria por cambios de grid: {int(diag.get('grid_track', 0) or 0)} puntos",
        ])

        for slot, item in sorted(slots.items()):
            lines.append(
                f"slot {slot}: HTTP={item.get('http')!r} · bytes={item.get('bytes', 0)} · "
                f"sha12={item.get('sha12') or '—'} · decode={item.get('decode') or '—'} · "
                f"grid={bool(item.get('exact_grid'))} · timestamp={item.get('header_timestamp')!r} · "
                f"celdas cambiadas={item.get('changed_cells')!r} · error={item.get('error') or '—'}"
            )

        lines.extend([
            "funcionamiento: la geometría del grid se dibuja y persiste aunque 10/24 siga congelado; "
            "el robot sólo usa diferencias temporales de dos mapas distintos como fallback de movimiento",
            "",
        ])
        return "\n".join(lines) + "\n" + inherited


if __name__ == "__main__":
    app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise
