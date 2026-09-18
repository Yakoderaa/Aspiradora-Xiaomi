import math
from collections import deque

import app_v84


class App(app_v84.App):
    """V85: continuidad física de 10/24 + reanclaje de discontinuidades."""

    # El E10 entrega pasos normales del orden de 0.10 m. Dejamos un margen muy
    # amplio para pérdidas de muestras, pero un salto consecutivo de 0.80 m o
    # más no puede aceptarse como una sola traslación física del robot.
    IMPOSSIBLE_RAW_STEP_METERS = 0.80
    REBASE_EPSILON_METERS = 1e-6

    def __init__(self):
        self._v85_frame_offset = (0.0, 0.0)
        self._v85_last_raw = None
        self._v85_last_transformed = None
        self._v85_rebases = 0
        self._v85_impossible_steps_blocked = 0
        self._v85_max_raw_step = 0.0
        self._v85_max_blocked_step = 0.0
        self._v85_last_rebase = None
        self._v85_recent_rebases = deque(maxlen=12)
        super().__init__()

    def _v74_reset_session(self):
        self._v85_frame_offset = (0.0, 0.0)
        self._v85_last_raw = None
        self._v85_last_transformed = None
        self._v85_rebases = 0
        self._v85_impossible_steps_blocked = 0
        self._v85_max_raw_step = 0.0
        self._v85_max_blocked_step = 0.0
        self._v85_last_rebase = None
        self._v85_recent_rebases = deque(maxlen=12)
        return super()._v74_reset_session()

    def _v85_transform_absolute(self, absolute):
        x = float(absolute["x"])
        y = float(absolute["y"])
        angle = float(
            absolute.get("phi", absolute.get("angle", 0.0)) or 0.0
        )
        raw = (x, y, angle)
        previous_raw = self._v85_last_raw
        raw_step = 0.0
        rebased = False
        old_offset = tuple(self._v85_frame_offset)

        if previous_raw is not None:
            raw_step = math.hypot(
                x - float(previous_raw[0]),
                y - float(previous_raw[1]),
            )
            self._v85_max_raw_step = max(
                float(self._v85_max_raw_step or 0.0),
                float(raw_step),
            )

        if (
            previous_raw is not None
            and raw_step >= self.IMPOSSIBLE_RAW_STEP_METERS
        ):
            # La posición visual/corregida anterior es nuestra continuidad
            # física. El punto raw nuevo se convierte en el nuevo origen del
            # marco, pero NO mueve al robot en esta muestra.
            last = getattr(self, "_v82_last_corrected", None)
            if last is None:
                if self._v85_last_transformed is not None:
                    target_x, target_y = self._v85_last_transformed[:2]
                else:
                    target_x = float(previous_raw[0]) + old_offset[0]
                    target_y = float(previous_raw[1]) + old_offset[1]
            else:
                target_x = float(last[0])
                target_y = float(last[1])

            new_offset = (
                float(target_x) - x,
                float(target_y) - y,
            )
            offset_change = math.hypot(
                new_offset[0] - old_offset[0],
                new_offset[1] - old_offset[1],
            )

            self._v85_frame_offset = new_offset
            self._v85_rebases += 1
            self._v85_impossible_steps_blocked += 1
            self._v85_max_blocked_step = max(
                float(self._v85_max_blocked_step or 0.0),
                float(raw_step),
            )
            self._v85_last_rebase = {
                "raw_step": float(raw_step),
                "offset_change": float(offset_change),
                "from": (
                    float(previous_raw[0]),
                    float(previous_raw[1]),
                ),
                "to": (x, y),
                "offset": tuple(new_offset),
            }
            self._v85_recent_rebases.append(dict(self._v85_last_rebase))
            rebased = True

        offset_x, offset_y = self._v85_frame_offset
        transformed = dict(absolute)
        transformed["x"] = x + float(offset_x)
        transformed["y"] = y + float(offset_y)
        transformed["phi"] = angle

        self._v85_last_raw = raw
        self._v85_last_transformed = (
            float(transformed["x"]),
            float(transformed["y"]),
            angle,
        )
        return transformed, {
            "rebased": bool(rebased),
            "raw_step": float(raw_step),
            "old_offset": old_offset,
            "new_offset": tuple(self._v85_frame_offset),
        }

    def _v82_correct_absolute(self, absolute):
        transformed, meta = self._v85_transform_absolute(absolute)
        result = super()._v82_correct_absolute(transformed)

        if meta.get("rebased"):
            try:
                if self._v83_recent_decisions:
                    item = self._v83_recent_decisions[-1]
                    suffix = (
                        "V85 rebase: salto raw "
                        f"{meta['raw_step']:.2f}m bloqueado"
                    )
                    previous = str(item.get("detail") or "")
                    item["detail"] = (
                        f"{previous} · {suffix}" if previous else suffix
                    )
            except Exception:
                pass

        return result

    def _v74_refresh_mapping_controls(self):
        result = super()._v74_refresh_mapping_controls()
        info = getattr(self, "mapping_steps_info", None)
        if info is not None:
            try:
                info.configure(
                    text=(
                        "Mapeo único · continuidad 10/24 · rebases anti-salto · "
                        "dock físico V84 · antiatasco prudente"
                    )
                )
            except Exception:
                pass
        return result

    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        offset = tuple(self._v85_frame_offset)
        last = dict(self._v85_last_rebase or {})

        if last:
            last_text = (
                f"{last.get('raw_step', 0.0):.2f}m · "
                f"cambio marco={last.get('offset_change', 0.0):.2f}m · "
                f"raw {last.get('from')} → {last.get('to')}"
            )
        else:
            last_text = "—"

        recent = []
        for item in list(self._v85_recent_rebases)[-6:]:
            recent.append(
                f"salto={item.get('raw_step', 0.0):.2f}m · "
                f"offset=({item.get('offset', (0.0, 0.0))[0]:+.2f}, "
                f"{item.get('offset', (0.0, 0.0))[1]:+.2f})"
            )

        lines = [
            "DIAGNÓSTICO V85 ACTIVO · continuidad 10/24 + rebase anti-teleport",
            "========================================================================",
            (
                "saltos imposibles bloqueados="
                f"{self._v85_impossible_steps_blocked} · "
                f"rebases={self._v85_rebases} · "
                f"umbral={self.IMPOSSIBLE_RAW_STEP_METERS:.2f} m"
            ),
            (
                "offset de marco activo: "
                f"X {offset[0]:+.2f} m · Y {offset[1]:+.2f} m"
            ),
            (
                "máximo paso raw visto/bloqueado: "
                f"{self._v85_max_raw_step:.2f}/"
                f"{self._v85_max_blocked_step:.2f} m"
            ),
            f"último rebase: {last_text}",
            "rebases recientes:",
        ]
        if recent:
            lines.extend(f"    {item}" for item in recent)
        else:
            lines.append("    —")

        lines.extend([
            (
                "regla V85: una sola muestra 10/24 no puede teletransportar "
                "el robot 0.80 m o más"
            ),
            (
                "regla V85: una discontinuidad del marco se reancla sobre la "
                "última posición válida sin dibujar el salto"
            ),
            (
                "regla V85: los deltas posteriores continúan desde el nuevo "
                "marco y cobertura/completitud sólo ven la trayectoria continua"
            ),
            (
                "regla V85: si el firmware vuelve al marco anterior, otro "
                "rebase absorbe el regreso sin crear una diagonal falsa"
            ),
        ])
        return "\n".join(lines) + "\n\n" + inherited
