import math
import statistics
import time

import app_v77


class App(app_v77.App):
    """V78: captura de base tolerante al sentinela 255_255 del B112."""

    BASE_CAPTURE_SAMPLES = 10
    BASE_CAPTURE_INTERVAL = 0.28
    BASE_MIN_VALID_SAMPLES = 3
    CHARGING_CONFIRM_SAMPLES = 3

    # Los diagnósticos repetidos de este xiaomi.vacuum.b112 mostraron
    # chargingbase=60_60 cuando 10/22 entrega un valor real y 255_255 cuando
    # temporalmente expone el sentinela. Sólo se usa este fallback si status=4
    # queda confirmado varias veces durante la captura.
    B112_DOCK_FALLBACK_RAW = (60.0, 60.0)

    def __init__(self):
        self._v78_base_method = None
        self._v78_charging_samples = 0
        self._v78_sentinel_samples = 0
        super().__init__()

    def _v74_reset_session(self):
        self._v78_base_method = None
        self._v78_charging_samples = 0
        self._v78_sentinel_samples = 0
        return super()._v74_reset_session()

    def _v77_capture_base_reference(self, vacuum):
        valid = []
        statuses = []
        charging_samples = 0
        sentinel_samples = 0

        for _ in range(self.BASE_CAPTURE_SAMPLES):
            try:
                values = vacuum._get_many([
                    ("charging_base", 10, 22),
                    ("status", 2, 1),
                ])
                status = self._v67_int(values.get("status"))
                if status is not None:
                    statuses.append(status)
                if status == 4:
                    charging_samples += 1

                parsed = vacuum.parse_position(values.get("charging_base"))
                xy = self._v77_valid_base_xy(parsed)
                if xy is not None:
                    valid.append(xy)
                elif parsed is not None:
                    try:
                        px = float(parsed.get("x"))
                        py = float(parsed.get("y"))
                        if px >= 250.0 and py >= 250.0:
                            sentinel_samples += 1
                    except Exception:
                        pass
            except Exception:
                pass

            if self.BASE_CAPTURE_INTERVAL > 0:
                time.sleep(self.BASE_CAPTURE_INTERVAL)

        self._v77_base_capture_valid = len(valid)
        self._v77_base_capture_status = statuses[-1] if statuses else None
        self._v78_charging_samples = charging_samples
        self._v78_sentinel_samples = sentinel_samples

        # Ruta preferida: 10/22 real y espacialmente estable.
        if len(valid) >= self.BASE_MIN_VALID_SAMPLES:
            mx = float(statistics.median([p[0] for p in valid]))
            my = float(statistics.median([p[1] for p in valid]))
            spread = max(math.hypot(x - mx, y - my) for x, y in valid)
            self._v77_base_capture_spread = spread
            if spread <= self.BASE_STABILITY_RAW:
                self._v78_base_method = "10/22 real"
                return mx, my

        # Quirk observado del B112: durante carga puede devolver 255_255 en
        # 10/22 aunque físicamente siga acoplado. No bloqueamos el mapeo si el
        # estado de carga confirma repetidamente el dock.
        if charging_samples >= self.CHARGING_CONFIRM_SAMPLES:
            self._v77_base_capture_spread = (
                None if not valid else self._v77_base_capture_spread
            )
            self._v78_base_method = "fallback dock B112 60_60"
            return tuple(self.B112_DOCK_FALLBACK_RAW)

        self._v78_base_method = "rechazado"
        raise RuntimeError(
            "No pude confirmar la base. El E10 no entregó un 10/22 estable "
            "ni confirmó carga varias veces. Dejalo acoplado hasta que figure "
            "Cargando y volvé a iniciar el mapa."
        )

    def _v71_set_origin(self, xy, source):
        source_text = str(source or "")
        if "10/22 estable antes del sweep" in source_text:
            if self._v78_base_method == "fallback dock B112 60_60":
                source = (
                    "fallback dock B112 60_60 confirmado por status=4 · V78"
                )
            elif self._v78_base_method == "10/22 real":
                source = "10/22 estable real antes del sweep · V78"
        return super()._v71_set_origin(xy, source)

    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        lines = [
            "DIAGNÓSTICO V78 ACTIVO · base tolerante al sentinela B112",
            "===========================================================",
            f"método de base: {self._v78_base_method or '—'}",
            f"muestras status=4: {self._v78_charging_samples}/{self.BASE_CAPTURE_SAMPLES}",
            f"muestras 255_255: {self._v78_sentinel_samples}",
            f"10/22 válidas: {self._v77_base_capture_valid}/{self.BASE_CAPTURE_SAMPLES}",
            f"base raw resultante: {self._v77_base_raw!r}",
            "regla V78: 10/22 real estable sigue siendo la fuente preferida",
            "regla V78: si 10/22 devuelve 255_255/None pero status=4 se confirma varias veces, el B112 usa dock raw 60_60",
            "regla V78: el fallback 60_60 nunca se usa si el robot no confirma que está cargando",
            "",
            "",
        ]
        return "\n".join(lines) + inherited


if __name__ == "__main__":
    app_v77.app_v76.app_v75.app_v74.app_v73.app_v72.app_v71.app_v70.app_v69.app_v68.app_v67.app_v66.app_v65.app_v64.app_v63.app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback

        app_v77.app_v76.app_v75.app_v74.app_v73.app_v72.app_v71.app_v70.app_v69.app_v68.app_v67.app_v66.app_v65.app_v64.app_v63.app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise
