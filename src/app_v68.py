import time

import app_v67


class App(app_v67.App):
    """V68: fin de Paso 1 por retorno/base real, no por sweep_type obligatorio."""

    EDGE_WATCH_SECONDS = 2 * 60 * 60
    EDGE_POLL_SECONDS = 0.35
    EDGE_IDLE_COMPLETE_SECONDS = 2.5

    def __init__(self):
        self._v68_edge_diag = {
            "watch_started": False,
            "session": 0,
            "samples": 0,
            "seen_moving": False,
            "seen_edge_type": False,
            "departed_base": False,
            "initial_base": None,
            "last_status": None,
            "last_sweep_type": None,
            "last_charging_state": None,
            "completion_reason": None,
            "timeout": False,
            "errors": 0,
        }
        super().__init__()

    # ----------------------------------------------------- helpers puros
    @classmethod
    def _v68_completion_reason(
        cls,
        *,
        seen_moving,
        departed_base,
        status,
        charging_state,
        idle_stable_seconds=0.0,
    ):
        """Devuelve una razón de fin sólo después de actividad/departida real."""
        active_run = bool(seen_moving or departed_base)
        if not active_run:
            return None

        status = cls._v67_int(status)
        charging_state = cls._v67_int(charging_state)

        if status == 3:
            return "status=3 · regresando a base"
        if charging_state == 1:
            return "charging-state=1 · acoplado/cargando"
        if status == 4:
            return "status=4 · cargando"
        if status in (0, 1, 2) and float(idle_stable_seconds or 0.0) >= cls.EDGE_IDLE_COMPLETE_SECONDS:
            return f"status={status} estable tras movimiento"
        return None

    @classmethod
    def _v68_timeout_completion_reason(
        cls,
        *,
        seen_moving,
        departed_base,
        status,
        charging_state,
    ):
        """Última comprobación antes de declarar timeout."""
        active_run = bool(seen_moving or departed_base)
        if not active_run:
            return None

        status = cls._v67_int(status)
        charging_state = cls._v67_int(charging_state)
        if status == 3:
            return "timeout-check: status=3 · regresando"
        if charging_state == 1:
            return "timeout-check: charging-state=1 · base"
        if status == 4:
            return "timeout-check: status=4 · base"
        if status in (0, 1, 2):
            return f"timeout-check: status={status} inactivo tras recorrido"
        return None

    @staticmethod
    def _v68_read_edge_state(vacuum):
        values = vacuum._get_many([
            ("status", 2, 1),
            ("sweep_type", 2, 8),
            ("charging_state", 3, 2),
        ])
        return {
            "status": values.get("status"),
            "sweep_type": values.get("sweep_type"),
            "charging_state": values.get("charging_state"),
        }

    def _v68_store_diag(self, **changes):
        diag = dict(getattr(self, "_v68_edge_diag", {}) or {})
        diag.update(changes)
        self._v68_edge_diag = diag

    def start_new_mapping(self):
        self._v68_edge_diag = {
            "watch_started": False,
            "session": int(getattr(self, "_edge_session", 0) or 0) + 1,
            "samples": 0,
            "seen_moving": False,
            "seen_edge_type": False,
            "departed_base": False,
            "initial_base": None,
            "last_status": None,
            "last_sweep_type": None,
            "last_charging_state": None,
            "completion_reason": None,
            "timeout": False,
            "errors": 0,
        }
        return super().start_new_mapping()

    # ------------------------------------------------ EDGE robusto B112
    def _watch_edge_only(self, session):
        """Vigila el Paso 1 sin exigir que sweep-type publique 2.

        El E10 real puede completar EDGE y volver a base aunque 2/8 no refleje
        de forma fiable el modo. V68 considera suficiente haber visto movimiento
        o una salida real de base y después retorno/carga/estado inactivo estable.
        """
        vacuum = self.vacuum
        if not vacuum:
            return

        started_at = time.monotonic()
        deadline = started_at + self.EDGE_WATCH_SECONDS
        seen_moving = False
        seen_edge_type = False
        departed_base = False
        initial_base = None
        non_edge_since = None
        idle_since = None
        errors = 0
        samples = 0
        last_state = None

        self._v68_store_diag(
            watch_started=True,
            session=int(session),
            samples=0,
            timeout=False,
            completion_reason=None,
        )

        while time.monotonic() < deadline:
            if session != self._edge_session or int(getattr(self, "mapping_phase", 0) or 0) != 1:
                return
            vacuum = self.vacuum
            if not vacuum:
                return

            try:
                state = self._v68_read_edge_state(vacuum)
                status = self._v67_int(state.get("status"))
                sweep_type = self._v67_int(state.get("sweep_type"))
                charging = self._v67_int(state.get("charging_state"))
                errors = 0
            except Exception as exc:
                errors += 1
                self._v68_store_diag(errors=errors, last_error=str(exc).strip() or type(exc).__name__)
                if errors >= 20:
                    try:
                        vacuum.stop()
                    except Exception:
                        pass
                    self._post_ui(
                        "edge_only_error",
                        "Perdí la comunicación durante el Paso 1. Lo detuve por seguridad.",
                    )
                    return
                time.sleep(self.EDGE_POLL_SECONDS)
                continue

            samples += 1
            at_base, _ = self._v67_base_evidence(status, charging)
            if initial_base is None:
                initial_base = bool(at_base)

            moving = status in (5, 6, 7)
            if moving:
                seen_moving = True
            if sweep_type == 2:
                seen_edge_type = True

            # Si arrancamos acoplados, una lectura posterior fuera de base
            # confirma que el recorrido realmente comenzó. Si la primera lectura
            # ya nos encuentra moviendo, también cuenta como salida de base.
            if not at_base and (seen_moving or initial_base is True):
                departed_base = True

            # Si alguna vez vimos EDGE=2, mantenemos la antigua protección contra
            # una transición persistente a limpieza global. Si nunca lo publica,
            # NO consideramos eso un error: usamos movimiento/retorno reales.
            if seen_edge_type and moving and sweep_type != 2:
                if non_edge_since is None:
                    non_edge_since = time.monotonic()
                elif time.monotonic() - non_edge_since >= 1.1:
                    try:
                        vacuum.stop()
                    except Exception:
                        pass
                    reason = (
                        f"sweep-type salió de EDGE durante movimiento "
                        f"(status={status}, sweep_type={sweep_type})"
                    )
                    self._v68_store_diag(
                        completion_reason=reason,
                        seen_moving=seen_moving,
                        seen_edge_type=seen_edge_type,
                        departed_base=departed_base,
                    )
                    self._post_ui(
                        "edge_only_complete",
                        "Paso 1 terminado · bloqueé una transición a limpieza global. "
                        "Esperando base para iniciar Paso 2.",
                    )
                    return
            else:
                non_edge_since = None

            if status in (0, 1, 2) and (seen_moving or departed_base):
                if idle_since is None:
                    idle_since = time.monotonic()
            else:
                idle_since = None

            idle_stable = (
                time.monotonic() - idle_since
                if idle_since is not None
                else 0.0
            )
            reason = self._v68_completion_reason(
                seen_moving=seen_moving,
                departed_base=departed_base,
                status=status,
                charging_state=charging,
                idle_stable_seconds=idle_stable,
            )

            current = (status, sweep_type, charging)
            if current != last_state or reason:
                self._edge_log(
                    "V68 EDGE: "
                    f"status={status} sweep_type={sweep_type} charging={charging} "
                    f"moving={seen_moving} departed={departed_base}"
                )
                last_state = current

            self._v68_store_diag(
                samples=samples,
                seen_moving=seen_moving,
                seen_edge_type=seen_edge_type,
                departed_base=departed_base,
                initial_base=initial_base,
                last_status=status,
                last_sweep_type=sweep_type,
                last_charging_state=charging,
                errors=errors,
            )

            if reason:
                self._v68_store_diag(completion_reason=reason, timeout=False)
                self._post_ui(
                    "edge_only_complete",
                    "Paso 1 terminado · detecté el fin real del recorrido. "
                    "Esperando/confirmando base para iniciar Paso 2 automáticamente.",
                )
                return

            time.sleep(self.EDGE_POLL_SECONDS)

        # Última lectura antes de declarar timeout. Si el robot ya terminó,
        # convertimos el supuesto timeout en un cierre normal y dejamos que V67
        # gestione base -> Paso 2.
        status = None
        charging = None
        sweep_type = None
        try:
            state = self._v68_read_edge_state(vacuum)
            status = self._v67_int(state.get("status"))
            sweep_type = self._v67_int(state.get("sweep_type"))
            charging = self._v67_int(state.get("charging_state"))
        except Exception as exc:
            self._v68_store_diag(last_error=str(exc).strip() or type(exc).__name__)

        reason = self._v68_timeout_completion_reason(
            seen_moving=seen_moving,
            departed_base=departed_base,
            status=status,
            charging_state=charging,
        )
        self._v68_store_diag(
            last_status=status,
            last_sweep_type=sweep_type,
            last_charging_state=charging,
            seen_moving=seen_moving,
            seen_edge_type=seen_edge_type,
            departed_base=departed_base,
        )

        if reason:
            self._v68_store_diag(completion_reason=reason, timeout=False)
            self._post_ui(
                "edge_only_complete",
                "Paso 1 terminó y el E10 ya está regresando/en base. "
                "Continuando con la transición automática a Paso 2.",
            )
            return

        try:
            vacuum.stop()
        except Exception:
            pass
        self._v68_store_diag(timeout=True, completion_reason=None)
        self._post_ui(
            "edge_only_error",
            "El Paso 1 alcanzó el límite de seguridad sin poder confirmar "
            "movimiento seguido de regreso/base. Fue detenido.",
        )

    # ---------------------------------------------------------- diagnóstico
    def _diagnostic_text(self):
        diag = dict(getattr(self, "_v68_edge_diag", {}) or {})
        inherited = super()._diagnostic_text()
        lines = [
            "DIAGNÓSTICO V68 ACTIVO · fin real de Paso 1",
            "================================================",
            f"watch EDGE iniciado: {bool(diag.get('watch_started'))} · sesión={diag.get('session', 0)} · muestras={diag.get('samples', 0)}",
            f"movimiento visto: {bool(diag.get('seen_moving'))} · salió de base: {bool(diag.get('departed_base'))} · base inicial={diag.get('initial_base')!r}",
            f"sweep-type=2 visto: {bool(diag.get('seen_edge_type'))} · último sweep-type={diag.get('last_sweep_type')!r}",
            f"último status: {diag.get('last_status')!r} · charging-state: {diag.get('last_charging_state')!r}",
            f"fin detectado: {diag.get('completion_reason') or '—'} · timeout real={bool(diag.get('timeout'))}",
            f"errores consecutivos: {diag.get('errors', 0)} · último error={diag.get('last_error') or '—'}",
            "regla V68: sweep-type=2 ya no es requisito para declarar completo el Paso 1",
            "regla V68: movimiento/salida de base + retorno(status=3), carga(status=4/charging=1) o inactividad estable = fin válido",
            "regla V68: antes de cualquier timeout se vuelve a comprobar el estado físico del E10",
            "",
            "",
        ]
        return "\n".join(lines) + inherited


if __name__ == "__main__":
    app_v67.app_v66.app_v65.app_v64.app_v63.app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v67.app_v66.app_v65.app_v64.app_v63.app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise
