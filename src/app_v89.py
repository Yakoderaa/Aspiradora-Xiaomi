import math
import tkinter as tk

import app_v88


class App(app_v88.App):
    """V89: mapa limpio; recorrido físico oculto sólo en la presentación.

    La trayectoria sigue existiendo íntegra en LocalMapStore y en todos los
    diagnósticos/cálculos heredados. V89 únicamente impide crear las líneas
    v87_route en el canvas para que la vista se parezca más a Mi Home:
    perímetro + relleno + base + robot.
    """

    def __init__(self):
        self._v89_route_draw_calls_blocked = 0
        super().__init__()

    # ==================================================== recorrido invisible
    def _v87_draw_route(self, canvas, snapshot, xy, width=2):
        """No dibuja el recorrido, pero no toca ni transforma sus datos."""
        self._v89_route_draw_calls_blocked += 1
        return None

    # ============================================================= leyenda
    def _v88_install_legend(self):
        canvas = getattr(self, "map_canvas", None)
        if canvas is None or not canvas.winfo_exists():
            return

        old = getattr(self, "_v72_legend", None)
        try:
            if old is not None:
                old.destroy()
        except Exception:
            pass

        legend = tk.Frame(
            canvas,
            bg="#ffffff",
            highlightthickness=1,
            highlightbackground="#d8e3ec",
        )
        legend.place(x=14, y=14)

        row = tk.Frame(legend, bg="#ffffff")
        row.pack(padx=9, pady=6)

        swatch = tk.Canvas(
            row,
            width=18,
            height=11,
            bg="#ffffff",
            highlightthickness=0,
        )
        swatch.pack(side="left")
        swatch.create_rectangle(
            1,
            1,
            17,
            10,
            fill=self.MAP_FLOOR,
            outline=self.MAP_OUTLINE,
            width=1,
        )

        self._v88_legend_source = tk.Label(
            row,
            text="Mapa estimado",
            bg="#ffffff",
            fg="#64748b",
            font=("Segoe UI", 8, "bold"),
        )
        self._v88_legend_source.pack(side="left", padx=(4, 0))

        self._v72_legend = legend
        legend.lift()

    # =========================================================== diagnóstico
    @staticmethod
    def _v89_route_length(points):
        total = 0.0
        previous = None
        for point in list(points or []):
            if not isinstance(point, dict):
                continue
            try:
                current = (float(point["x"]), float(point["y"]))
            except Exception:
                continue
            if previous is not None:
                total += math.hypot(
                    current[0] - previous[0],
                    current[1] - previous[1],
                )
            previous = current
        return total

    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        try:
            snapshot = self.local_map.snapshot() if self.local_map else {}
        except Exception:
            snapshot = {}

        points = list((snapshot or {}).get("points") or [])
        try:
            segments = list(self._v87_path_segments(snapshot))
        except Exception:
            segments = []

        length = self._v89_route_length(points)
        first = None
        last = None
        for point in points:
            if isinstance(point, dict) and "x" in point and "y" in point:
                try:
                    xy = (float(point["x"]), float(point["y"]))
                except Exception:
                    continue
                if first is None:
                    first = xy
                last = xy

        lines = [
            "DIAGNÓSTICO V89 ACTIVO · recorrido oculto sólo visualmente",
            "===========================================================",
            "presentación: perímetro + relleno + base + robot; sin líneas internas",
            (
                "recorrido interno: OCULTO EN UI · "
                f"guardado={len(points)} puntos · segmentos={len(segments)} · "
                f"largo={length:.2f} m"
            ),
            f"extremos del recorrido conservado: inicio={first!r} · fin={last!r}",
            f"intentos de dibujo de recorrido bloqueados: {self._v89_route_draw_calls_blocked}",
            "regla V89: ocultar el recorrido no elimina ni modifica puntos de LocalMapStore",
            "regla V89: cobertura, completitud, antiatasco, V85/V86 y F12 siguen viendo la trayectoria completa",
            "regla V89: mapa grande y miniaturas comparten la misma política visual sin recorrido",
            "",
            "",
        ]
        return "\n".join(lines) + inherited


if __name__ == "__main__":
    app_v88.app_v87.app_v86.app_v85.app_v84.app_v83.app_v82.app_v81.app_v80.app_v79.app_v78.app_v77.app_v76.app_v75.app_v74.app_v73.app_v72.app_v71.app_v70.app_v69.app_v68.app_v67.app_v66.app_v65.app_v64.app_v63.app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v88.app_v87.app_v86.app_v85.app_v84.app_v83.app_v82.app_v81.app_v80.app_v79.app_v78.app_v77.app_v76.app_v75.app_v74.app_v73.app_v72.app_v71.app_v70.app_v69.app_v68.app_v67.app_v66.app_v65.app_v64.app_v63.app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise
