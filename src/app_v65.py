import app_v64


class App(app_v64.App):
    """V65: reconoce ACK MIoT ["ok"] devuelto por python-miio."""

    def _diagnostic_text(self):
        vacuum = getattr(self, "vacuum", None)
        build = dict(getattr(vacuum, "last_map_build_diag", {}) or {}) if vacuum else {}
        attempts = list(build.get("attempts") or [])
        inherited = super()._diagnostic_text()

        lines = [
            "DIAGNÓSTICO V65 ACTIVO · ACK MIoT de acciones",
            "===============================================",
            f"build éxito: {bool(build.get('success')) if build else '—'} · ganador={build.get('winner') or '—'}",
            "regla V65: code=0, ACK 'ok', timestamp o readback build-map confirman la acción",
            "regla V65: code negativo siempre rechaza; None/vacío solo nunca autoriza movimiento",
            "respuestas de build-map:",
        ]
        if attempts:
            for item in attempts[-4:]:
                if not isinstance(item, dict):
                    continue
                lines.append(
                    "    "
                    + f"10/{item.get('aiid', '—')} {item.get('action') or '—'}"
                    + f" · code={item.get('code')!r}"
                    + f" · ack={bool(item.get('ack'))}"
                    + f" · resp={item.get('response_summary') or '—'}"
                    + f" · accepted={bool(item.get('accepted'))}"
                    + (f" · error={item.get('error')}" if item.get("error") else "")
                )
        else:
            lines.append("    — todavía no se intentó crear un mapa en esta sesión")

        lines.extend([
            "regla fallback: si 10/17 devuelve ACK válido, 10/11 NO se ejecuta",
            "",
            "",
        ])
        return "\n".join(lines) + inherited


if __name__ == "__main__":
    app_v64.app_v63.app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback
        app_v64.app_v63.app_v62.app_v61.app_v60.app_v58.app_v57.app_v56.app_v55.app_v54.app_v53.app_v52.app_v51.app_v50.app_v49.app_v48.app_v47.app_v46.app_v45.app_v44.app_v43.app_v42.app_v41.app_v40.app_v39.app_v38.app_v37.app_v36.app_v35.app_v34.app_v33.app_v32.app_v31.app_v30.app_v29.app_v28.app_v27.app_v26.app_v25.app_v24.app_v23.app_v22.app_v21.app_v20.app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise
