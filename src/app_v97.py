import math

import app_v96
import app_v9
import windows_audio_identity


class App(app_v96.App):
    """V97: fallback visual prudente + viewport estable + audio identificable."""

    EARLY_MIN_POINTS = 24
    EARLY_MIN_MAJOR_SPAN_M = 1.00
    EARLY_MIN_MINOR_SPAN_M = 0.55
    EARLY_MIN_RATIO = 0.35
    EARLY_MIN_AXIS_CELLS = 4
    EARLY_VIEWPORT_HALF_METERS = 2.0

    def __init__(self):
        self._v97_last_geometry = {}
        super().__init__()

    # ===================================================== madurez de geometría
    @classmethod
    def _v97_geometry_metrics(cls, snapshot):
        pts=[]
        for p in list((snapshot or {}).get("points") or []):
            if not isinstance(p,dict):
                continue
            try:
                x=float(p["x"]); y=float(p["y"])
            except Exception:
                continue
            if math.isfinite(x) and math.isfinite(y):
                pts.append((x,y))
        if not pts:
            return {
                "points":0,"span_x":0.0,"span_y":0.0,"major":0.0,"minor":0.0,
                "ratio":0.0,"cols":0,"rows":0,"mature":False,
            }
        xs=[x for x,_ in pts]; ys=[y for _,y in pts]
        span_x=max(xs)-min(xs); span_y=max(ys)-min(ys)
        major=max(span_x,span_y); minor=min(span_x,span_y)
        ratio=(minor/major) if major>1e-9 else 0.0
        size=float(cls.MAP_CELL)
        cols=len({int(math.floor(x/size)) for x,_ in pts})
        rows=len({int(math.floor(y/size)) for _,y in pts})
        mature=(
            len(pts)>=int(cls.EARLY_MIN_POINTS)
            and major>=float(cls.EARLY_MIN_MAJOR_SPAN_M)
            and minor>=float(cls.EARLY_MIN_MINOR_SPAN_M)
            and ratio>=float(cls.EARLY_MIN_RATIO)
            and min(cols,rows)>=int(cls.EARLY_MIN_AXIS_CELLS)
        )
        return {
            "points":len(pts),"span_x":span_x,"span_y":span_y,
            "major":major,"minor":minor,"ratio":ratio,
            "cols":cols,"rows":rows,"mature":bool(mature),
        }

    @classmethod
    def _v97_trace_cells(cls, snapshot):
        """Huella temprana: sólo recorrido observado, sin cerrar ni rellenar."""
        points=[]
        for p in list((snapshot or {}).get("points") or []):
            if not isinstance(p,dict):
                continue
            try:
                x=float(p["x"]); y=float(p["y"])
            except Exception:
                continue
            if math.isfinite(x) and math.isfinite(y):
                points.append((x,y))
        if not points:
            return set()

        size=float(cls.MAP_CELL)
        cells=set()
        def stamp(x,y):
            cx=int(math.floor(x/size)); cy=int(math.floor(y/size))
            # Cruz de 5 celdas: representa una huella prudente del robot sin
            # convertir una línea corta en una habitación.
            cells.add((cx,cy))
            cells.add((cx+1,cy)); cells.add((cx-1,cy))
            cells.add((cx,cy+1)); cells.add((cx,cy-1))

        previous=None
        for current in points:
            if previous is not None:
                dist=math.hypot(current[0]-previous[0],current[1]-previous[1])
                steps=max(1,int(math.ceil(dist/max(size*0.75,0.04))))
                for i in range(1,steps):
                    t=i/float(steps)
                    stamp(
                        previous[0]+(current[0]-previous[0])*t,
                        previous[1]+(current[1]-previous[1])*t,
                    )
            stamp(*current)
            previous=current
        return cells

    @classmethod
    def _v87_floor_cells(cls, snapshot):
        metrics=cls._v97_geometry_metrics(snapshot)
        if not metrics["mature"]:
            return cls._v97_trace_cells(snapshot)
        # Recién con exploración 2D real habilitamos cierre de huecos V91.
        return super()._v87_floor_cells(snapshot)

    def _v97_early_viewport_bounds(self, snapshot):
        metrics=self._v97_geometry_metrics(snapshot)
        if metrics["mature"] or self._v88_native_grid(snapshot) is not None:
            return None
        half=float(self.EARLY_VIEWPORT_HALF_METERS)
        return (-half,-half,half,half)

    def _v72_bounds(self, snapshot):
        inherited=super()._v72_bounds(snapshot)
        early=self._v97_early_viewport_bounds(snapshot)
        if early is None:
            return inherited
        return self._v88_union_bounds(inherited,early)

    def _v70_collect_bounds(self, snapshot, plan):
        inherited=super()._v70_collect_bounds(snapshot,plan)
        early=self._v97_early_viewport_bounds(snapshot)
        if early is None:
            return inherited
        return self._v88_union_bounds(inherited,early)

    def _diagnostic_text(self):
        inherited=super()._diagnostic_text()
        try:
            snapshot=self.local_map.snapshot() if self.local_map else {}
        except Exception:
            snapshot={}
        metrics=self._v97_geometry_metrics(snapshot)
        floor=self._v87_floor_cells(snapshot)
        native=self._v88_native_grid(snapshot)
        audio=windows_audio_identity.snapshot()
        mode=(
            "GRID XIAOMI"
            if native is not None
            else ("fallback 2D maduro" if metrics["mature"] else "huella temprana")
        )
        lines=[
            "DIAGNÓSTICO V97 ACTIVO · mapa prudente + identidad Sonar",
            "==========================================================",
            (
                "geometría observada: "
                f"puntos={metrics['points']} · X={metrics['span_x']:.2f}m · "
                f"Y={metrics['span_y']:.2f}m · ratio={metrics['ratio']:.2f} · "
                f"cols/rows={metrics['cols']}/{metrics['rows']} · "
                f"2D madura={metrics['mature']}"
            ),
            (
                f"fuente visual V97: {mode} · celdas visibles={len(floor)} · "
                f"viewport temprano={self.EARLY_VIEWPORT_HALF_METERS*2:.1f}×"
                f"{self.EARLY_VIEWPORT_HALF_METERS*2:.1f}m"
            ),
            (
                "gate fallback completo: "
                f"≥{self.EARLY_MIN_POINTS} puntos · mayor≥{self.EARLY_MIN_MAJOR_SPAN_M:.2f}m · "
                f"menor≥{self.EARLY_MIN_MINOR_SPAN_M:.2f}m · ratio≥{self.EARLY_MIN_RATIO:.2f}"
            ),
            (
                "Sonar/Core Audio: "
                f"silencio activo={audio.get('silent_session_started',False)} · "
                f"sesiones propias vistas={audio.get('own_sessions_seen',0)} · "
                f"renombradas={audio.get('renamed_sessions',0)} · "
                f"último nombre={audio.get('last_session_name') or '—'} · "
                f"error={audio.get('last_error') or '—'}"
            ),
            (
                "regla V97: una trayectoria casi lineal nunca ejecuta cierre de "
                "huecos ni relleno de superficie"
            ),
            (
                "regla V97: antes de geometría 2D válida el viewport conserva "
                "4×4 m alrededor de la base y no hace zoom agresivo"
            ),
            (
                "regla V97: la app mantiene una sesión de audio silenciosa propia "
                "y la etiqueta Aspiradora para SteelSeries Sonar"
            ),
            "",
            "",
        ]
        return "\n".join(lines)+inherited


if __name__=="__main__":
    app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        app_v9._save_crash_log(app_v9.traceback.format_exc())
        raise
