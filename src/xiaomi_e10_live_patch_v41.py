"""Parches conservadores al fallback local de trayectoria del E10.

Se instalan en v41 sin reescribir toda la clase heredada: aceptan respuestas
numéricas directas de la acción 10/12 y añaden una sonda de rango uint32 completo.
"""
from xiaomi_e10_live import XiaomiE10Live

_INSTALLED = False


def install():
    global _INSTALLED
    if _INSTALLED:
        return

    original = XiaomiE10Live._extract_action_output.__func__

    @classmethod
    def extract_action_output(cls, value, target_piid=5):
        # Algunos firmwares devuelven el payload de out directamente como
        # [pose_id, x, y, phi, update, ...], sin wrapper {out:[{piid,value}]}.
        if isinstance(value, (list, tuple)) and value:
            if all(isinstance(item, (int, float)) for item in value):
                return list(value)
        return original(cls, value, target_piid)

    XiaomiE10Live._extract_action_output = extract_action_output
    XiaomiE10Live.FALLBACK_PROBE_ENDS = (
        256, 1024, 4096, 16384, 65535, 262143, 1048575, 16777215, 4294967295
    )
    XiaomiE10Live.HISTORY_SPANS = (64, 256, 1024, 4096, 16384, 65535)
    _INSTALLED = True
