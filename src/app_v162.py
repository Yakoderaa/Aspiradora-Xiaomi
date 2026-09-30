"""V162: repara el START de limpieza por habitación/zona del E10 B112."""
import app_v161


class App(app_v161.App):
    """Mantiene V161 CPU-safe y corrige únicamente la ruta de limpieza dirigida."""

    def _v161_compact_diagnostic_text(self):
        base = super()._v161_compact_diagnostic_text()
        base = base.replace(
            "V161-IA · DIAGNÓSTICO COMPACTO / CPU SAFE",
            "V162-IA · DIAGNÓSTICO COMPACTO / CPU SAFE + TARGET FIX",
            1,
        )
        last_target = dict(getattr(self, "_v157_last_target", {}) or {})
        section = (
            "\nLIMPIEZA DIRIGIDA V162\n"
            + repr({
                "last_target": last_target,
                "sequence": "9/8 -> 9/3; fallback 9/2 -> 9/3",
                "start_timeout_s": 20,
                "whole_home_changed": False,
                "cpu_policy_changed": False,
            })
            + "\n"
        )
        return base + section
