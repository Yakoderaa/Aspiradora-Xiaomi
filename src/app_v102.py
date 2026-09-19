import app_v101
import app_v9


class App(app_v101.App):
    """V102: corrige el corte V88/V87 y mantiene geometría/pose Xiaomi visibles."""

    def __init__(self):
        self._v102_rooms_contract_hits = 0
        self._v102_pose_main_redraws = 0
        self._v102_pose_thumb_redraws = 0
        self._v102_live_status_updates = 0
        self._v102_main_base_objects = 0
        self._v102_main_robot_objects = 0
        self._v102_thumb_base_objects = 0
        self._v102_thumb_robot_objects = 0
        super().__init__()

    # ================================================= fix raíz V88 -> V87
    def _v87_draw_rooms_and_plan(self, canvas, snapshot, xy, transform=None):
        """Acepta el cuarto argumento heredado que V88 envía por error.

        V87 define (canvas, snapshot, xy), mientras V88 todavía llama
        (canvas, snapshot, xy, transform). V102 absorbe transform y delega al
        contrato real de V87. Esto evita que el render se corte antes de
        dibujar base, robot y leyenda Xiaomi.
        """
        self._v102_rooms_contract_hits += 1
        return super()._v87_draw_rooms_and_plan(canvas, snapshot, xy)

    # ============================================== overlays base + aspiradora
    @staticmethod
    def _v102_tag_count(canvas, tag):
        try:
            return len(canvas.find_withtag(tag))
        except Exception:
            return 0

    def _v102_snapshot_has_pose(self, snapshot):
        try:
            base = self._v87_xy((snapshot or {}).get("charging_base"))
            robot = self._v87_xy((snapshot or {}).get("robot"))
        except Exception:
            return False
        return base is not None or robot is not None

    def _v102_redraw_main_pose(self, canvas, snapshot):
        if not self._v102_snapshot_has_pose(snapshot):
            return False
        transform = getattr(self, "_map_transforms", {}).get(canvas)
        if not transform:
            return False
        try:
            xy = self._v87_xy(canvas, transform)
            canvas.delete("v87_base")
            canvas.delete("v87_robot")
            self._v87_draw_base_and_robot(
                canvas, snapshot, xy, miniature=False
            )
            canvas.tag_raise("v87_base")
            canvas.tag_raise("v87_robot")
            canvas.delete("v99_waiting")
            self._v102_pose_main_redraws += 1
            self._v102_main_base_objects = self._v102_tag_count(
                canvas, "v87_base"
            )
            self._v102_main_robot_objects = self._v102_tag_count(
                canvas, "v87_robot"
            )
            return True
        except Exception:
            return False

    def _v102_redraw_thumb_pose(self, canvas, snapshot, plan):
        if not self._v102_snapshot_has_pose(snapshot):
            return False
        grid = self._v88_native_grid(snapshot)
        if grid is None:
            return False

        try:
            cw = max(80, int(canvas.winfo_width() or 175))
            ch = max(54, int(canvas.winfo_height() or 88))
            inherited = self._v70_collect_bounds(snapshot, plan or {})
            bounds = self._v88_union_bounds(
                inherited, self._v88_grid_bounds(grid)
            )
            if bounds is None:
                bounds = (-2.0, -2.0, 2.0, 2.0)
            min_x, min_y, max_x, max_y = bounds
            span_x = max(0.35, max_x - min_x)
            span_y = max(0.35, max_y - min_y)
            pad = 7.0
            scale = min(
                (float(cw) - 2.0 * pad) / span_x,
                (float(ch) - 2.0 * pad) / span_y,
            )

            def xy(x, y):
                return (
                    pad + (float(x) - min_x) * scale,
                    pad + (max_y - float(y)) * scale,
                )

            canvas.delete("v87_base")
            canvas.delete("v87_robot")
            self._v87_draw_base_and_robot(
                canvas, snapshot, xy, miniature=True
            )
            canvas.tag_raise("v87_base")
            canvas.tag_raise("v87_robot")
            self._v102_pose_thumb_redraws += 1
            self._v102_thumb_base_objects = self._v102_tag_count(
                canvas, "v87_base"
            )
            self._v102_thumb_robot_objects = self._v102_tag_count(
                canvas, "v87_robot"
            )
            return True
        except Exception:
            return False

    def _render_map_canvas(self, canvas, snapshot):
        result = super()._render_map_canvas(canvas, snapshot)
        if canvas is getattr(self, "map_canvas", None):
            grid = self._v88_native_grid(snapshot)
            if grid is not None:
                try:
                    canvas.delete("v99_waiting")
                    self._v88_update_legend(True)
                except Exception:
                    pass
                self._v102_redraw_main_pose(canvas, snapshot)
        return result

    def _v70_render_thumbnail(
        self, canvas, snapshot, plan=None, active=False
    ):
        result = super()._v70_render_thumbnail(
            canvas, snapshot, plan, active
        )
        if self._v88_native_grid(snapshot) is not None:
            self._v102_redraw_thumb_pose(canvas, snapshot, plan or {})
        return result

    # ============================================== estado Xiaomi live correcto
    def _v102_live_status_text(self, nonzero):
        language = str(
            (getattr(self, "settings", {}) or {}).get("language", "es")
        ).lower()
        if language.startswith("en"):
            return f"Mapping live · Xiaomi map · {nonzero} cells"
        if language.startswith("pt"):
            return f"Mapeando em tempo real · mapa Xiaomi · {nonzero} células"
        return f"Mapeando en tiempo real · mapa Xiaomi en vivo · {nonzero} celdas"

    def _v93_sync_map_status_label(self):
        result = super()._v93_sync_map_status_label()
        if not bool(getattr(self, "mapping_active", False)):
            return result

        label = getattr(self, "map_status_label", None)
        if label is None:
            return result

        try:
            snapshot = self.local_map.snapshot() if self.local_map else {}
        except Exception:
            snapshot = {}
        grid = self._v88_native_grid(snapshot)
        if not isinstance(grid, dict):
            return result

        try:
            nonzero = sum(
                1 for value in list(grid.get("cells") or []) if int(value)
            )
        except Exception:
            nonzero = 0

        text = self._v102_live_status_text(nonzero)
        self._v93_last_status_text = text
        try:
            label.configure(text=text, fg="#16a34a")
            self._v102_live_status_updates += 1
        except Exception:
            pass
        return result

    # =========================================================== diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        try:
            snapshot = self.local_map.snapshot() if self.local_map else {}
        except Exception:
            snapshot = {}
        grid = self._v88_native_grid(snapshot)
        nonzero = 0
        preview = False
        if isinstance(grid, dict):
            preview = bool(grid.get("preview"))
            try:
                nonzero = sum(
                    1
                    for value in list(grid.get("cells") or [])
                    if int(value)
                )
            except Exception:
                nonzero = 0

        lines = [
            "DIAGNÓSTICO V102 ACTIVO · contrato renderer + pose Xiaomi",
            "================================================================",
            (
                f"grid Xiaomi={grid is not None} · preview={preview} · "
                f"celdas={nonzero}"
            ),
            (
                f"contrato rooms V88→V87 corregido: hits="
                f"{self._v102_rooms_contract_hits}"
            ),
            (
                f"pose mapa grande: base={self._v102_main_base_objects} · "
                f"robot={self._v102_main_robot_objects} · "
                f"redraws={self._v102_pose_main_redraws}"
            ),
            (
                f"pose miniatura: base={self._v102_thumb_base_objects} · "
                f"robot={self._v102_thumb_robot_objects} · "
                f"redraws={self._v102_pose_thumb_redraws}"
            ),
            (
                f"estado Xiaomi live aplicado={self._v102_live_status_updates} · "
                f"texto={getattr(self, '_v93_last_status_text', '—')}"
            ),
            (
                "regla V102: un grid Xiaomi usable elimina inmediatamente "
                "'Buscando geometría Xiaomi…' aunque todavía sea preview"
            ),
            (
                "regla V102: base y aspiradora se redibujan al final y se "
                "elevan sobre la planta Xiaomi en mapa grande y miniatura"
            ),
            (
                "regla V102: la planta sigue saliendo del grid Xiaomi 120x120 "
                "a 0,20 m; no se sustituye por geometría estimada"
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
