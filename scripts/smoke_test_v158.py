"""Regresiones offline: captura sin escrituras, carreras y persistencia real."""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import app_v158
import app_v157
import app_v156
import app_v151
from local_mapping import LocalMapStore


class HeadlessApp(app_v158.App):
    def __init__(self, folder):
        self._v158_epoch = 0
        self._v158_capture = None
        self._v158_worker = False
        self._v158_status = 4
        self._v158_state = {"status": 4}
        self._v158_map_diag = {}
        self.mapping_active = self._v157_whole_active = self._v157_target_active = False
        self._closing = False
        self.vacuum = SimpleNamespace()
        self.local_map = LocalMapStore(folder)
        self.settings = {}
        self.timers = []
        self.events = []
        self.banners = []
        self._v105_frozen_previews = {}
        self._v100_live_grids = {}
        self._fresh_core = None
        self.after = lambda delay, fn: self.timers.append((delay, fn))
        self._post_ui = lambda *args: self.events.append(args)
        self._set_banner = self.banners.append
        self._cloud_session_ready = lambda: True
        self._v105_map_id = lambda: self.local_map.active_map_id
        self._render_maps = lambda: None
        self._v70_refresh_map_overview = lambda **kw: None
        self._v93_sync_map_status_label = lambda: None


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = HeadlessApp(Path(self.temp.name))
        self.grid = dict(side=2, resolution=.1, base_cell=[1, 1], cells=[1, 1, 0, 0],
                         source="xiaomi-v158-final-current", blob_sha12="abc")

    def start(self):
        self.assertTrue(self.app._v158_begin_capture("test"))
        return self.app._v158_capture

    def test_dedup_and_busy(self):
        self.start()
        self.assertFalse(self.app._v158_begin_capture("duplicate"))
        self.assertEqual(len(self.app.timers), 1)
        self.app._v157_whole_active = True
        self.app._v158_read_final(self.app._v158_capture, 0)
        self.assertFalse(self.app._v158_worker)

    def test_persistence_and_renderer_cache(self):
        cap = self.start()
        self.app._handle_ui_event("v158_final_map", (cap, 0, self.grid, None, {}))
        saved = LocalMapStore(Path(self.temp.name)).snapshot()["native_grid"]
        self.assertEqual(saved["cells"], self.grid["cells"])
        self.assertTrue(self.app._v107_final_saved)
        self.assertEqual(self.app._v100_live_grids[cap[3]]["cells"], self.grid["cells"])

    def test_late_result_cannot_write_after_new_clean(self):
        cap = self.start()
        self.app._v157_whole_active = True
        self.app._handle_ui_event("v158_final_map", (cap, 0, self.grid, None, {}))
        self.assertIsNone(self.app.local_map.snapshot()["native_grid"])

    def test_replaced_map_or_robot_rejects_response(self):
        cap = self.start()
        self.app.vacuum = SimpleNamespace()
        self.assertFalse(self.app._v158_valid(cap))
        self.app.vacuum = cap[1]
        self.app.local_map = LocalMapStore(Path(self.temp.name) / "other")
        self.assertFalse(self.app._v158_valid(cap))

    def test_failure_keeps_map_and_retries_are_bounded(self):
        cap = self.start()
        self.app.local_map.set_native_grid(self.grid)
        for attempt in range(5):
            self.app._handle_ui_event("v158_final_map", (cap, attempt, None, "Cloud error", {}))
        self.assertEqual(self.app.local_map.snapshot()["native_grid"]["cells"], self.grid["cells"])
        self.assertEqual(len(self.app.timers), 5)
        self.assertEqual(len(self.app._v158_map_diag["errors"]), 5)

    def test_no_cloud_session_creates_no_worker(self):
        cap = self.start()
        self.app._cloud_session_ready = lambda: False
        self.app._v158_read_final(cap, 0)
        self.assertFalse(self.app._v158_worker)
        self.assertEqual(self.app._v158_map_diag["attempts"], 0)

    def test_worker_only_uses_read_interface(self):
        cap = self.start()
        class ReadOnlyClient:
            def __init__(self, *args): pass
            def set_v109_reference_path(self, path): pass
            def set_v107_final_mode(self, value): pass
            def load_live_partial(self):
                return SimpleNamespace(grid_side=2, grid_resolution=.1,
                    grid_base_cell=[1, 1], grid_cells=[1, 1, 0, 0])
        class InlineThread:
            def __init__(self, target, **kw): self.target = target
            def start(self): self.target()
        with patch.object(app_v158, "XiaomiE10MapV130", ReadOnlyClient), \
             patch.object(app_v158.threading, "Thread", InlineThread):
            self.app._v158_read_final(cap, 0)
        kind, *payload = self.app.events[0]
        self.assertEqual(kind, "v158_final_map")
        self.assertIsNone(payload[3])
        self.assertEqual(payload[2]["cells"], [1, 1, 0, 0])

    def test_finish_event_after_dock_telemetry(self):
        self.app._v157_whole_active = True
        self.assertFalse(self.app._v158_begin_capture("dock"))
        def finish(app, kind, payload): app._v157_whole_active = False
        with patch.object(app_v157.App, "_handle_ui_event", finish):
            self.app._handle_ui_event("v157_whole_finished", ({}, False, {}))
        self.assertIsNotNone(self.app._v158_capture)

    def test_diagnostics_survive_failed_section(self):
        with patch.object(app_v157.App, "_diagnostic_text", side_effect=ValueError("broken")), \
             patch.object(app_v156.App, "_diagnostic_text", return_value="coordinates"), \
             patch.object(app_v151.App, "_diagnostic_text", return_value="ACTIVO legacy telemetry"):
            report = self.app._diagnostic_text()
        self.assertIn("DIAGNÓSTICO COMPLETO", report)
        self.assertIn("Sección no disponible", report)
        self.assertIn("CAPTURA FINAL XIAOMI", report)
        self.assertIn("HISTÓRICO legacy telemetry", report)

    def test_navigation_methods_unchanged(self):
        for name in ("start_clean", "_v157_whole_home", "_v155_mapping_worker",
                     "clean_local_room", "_run_schedule_now", "dock"):
            self.assertIs(getattr(app_v158.App, name), getattr(app_v157.App, name))

    def test_real_status_channel_starts_capture_and_cancels_on_motion(self):
        self.app._v158_status = 5
        with patch.object(app_v157.App, "_render_status", return_value=None):
            self.app._render_status(SimpleNamespace(status=4))
            cap = self.app._v158_capture
            self.assertIsNotNone(cap)
            self.app._render_status(SimpleNamespace(status=5))
            self.assertIsNone(self.app._v158_capture)
            self.app._handle_ui_event("v158_final_map", (cap, 0, self.grid, None, {}))
            self.assertIsNone(self.app.local_map.snapshot()["native_grid"])


if __name__ == "__main__":
    unittest.main()
