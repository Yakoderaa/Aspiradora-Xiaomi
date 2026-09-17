import threading

import app_v19
from robot_plans import sync_virtual_walls


class App(app_v19.App):
    """v20: sincronización segura de paredes virtuales entre los cuatro mapas."""

    def _sync_no_go_async(self):
        if not self.vacuum or not self.plan_store:
            return

        plan = self.plan_store.snapshot()
        all_plan = self.plan_store.snapshot_all()
        any_managed = any(
            bool(value)
            for value in (all_plan.get("virtual_walls_managed_maps", {}) or {}).values()
        )

        # Si la app jamás administró paredes, no tocamos restricciones que el
        # usuario pudiera haber creado directamente en Mi Home.
        if not any_managed and not plan.get("virtual_walls_managed", False):
            return

        vacuum = self.vacuum

        def worker():
            try:
                sync_virtual_walls(vacuum, plan, force=any_managed)
                self._post_ui("plan_sync_ok")
            except Exception as exc:
                self._post_ui(
                    "plan_sync_error",
                    str(exc).strip() or "No se pudieron sincronizar los bloqueos.",
                )

        threading.Thread(target=worker, daemon=True).start()


if __name__ == "__main__":
    app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback

        app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise
