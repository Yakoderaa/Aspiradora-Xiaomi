from xiaomi_e10_map_v128 import XiaomiE10MapV128


class XiaomiE10MapV130(XiaomiE10MapV128):
    """V130: conserva el decoder V128; añade diagnóstico de captura de retorno."""

    def __init__(self, *args, **kwargs):
        self.last_v130_diagnostics = {}
        super().__init__(*args, **kwargs)

    def note_v130_candidate(self, source, grid, metrics):
        cells = list((grid or {}).get("cells") or [])
        self.last_v130_diagnostics = {
            "source": str(source or "—"),
            "cells": int(sum(1 for value in cells if int(value))),
            "valid": bool((metrics or {}).get("valid")),
            "metrics": dict(metrics or {}),
        }
