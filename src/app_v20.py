import threading
import tkinter as tk
from tkinter import messagebox

import app_v2
import app_v19
from robot_plans import sync_virtual_walls
from windows_integration import apply_window_icon

CARD = app_v19.CARD
CARD_ALT = app_v19.CARD_ALT
TEXT = app_v19.TEXT
MUTED = app_v19.MUTED
BORDER = app_v19.BORDER
GREEN = app_v19.GREEN
RED = app_v19.RED
ACCENT = app_v19.ACCENT


def _patch_dialog_icons():
    """Aplica Mi Home también a los diálogos heredados de configuración/QR."""
    for cls in (app_v2.SetupDialog, app_v2.QrDialog):
        if getattr(cls, "_mi_home_icon_patched", False):
            continue
        original = cls.__init__

        def wrapped(self, *args, __original=original, **kwargs):
            __original(self, *args, **kwargs)
            apply_window_icon(self)

        cls.__init__ = wrapped
        cls._mi_home_icon_patched = True


_patch_dialog_icons()


class LinkedAccountDialog(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Cuenta Xiaomi")
        self.geometry("520x360")
        self.resizable(False, False)
        self.transient(app)
        self.grab_set()
        apply_window_icon(self)

        body = tk.Frame(self, padx=22, pady=20)
        body.pack(fill="both", expand=True)
        tk.Label(body, text="Cuenta Xiaomi", font=("Segoe UI", 16, "bold")).pack(anchor="w")

        method = str(app.settings.get("xiaomi_login_method") or "")
        legacy = method == "qr_legacy"
        status = "Conectado con Xiaomi mediante QR"
        if legacy:
            status += " · sesión anterior"
        tk.Label(body, text=status, fg=GREEN, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(8, 2))
        tk.Label(body, text=f"Usuario: {app._xiaomi_account_display()}", font=("Segoe UI", 10)).pack(anchor="w", pady=2)
        tk.Label(
            body,
            text=f"Robot: {app.settings.get('device_name') or 'Xiaomi Robot Vacuum E10'}",
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=2)
        region = str(app.settings.get("device_region") or "").strip()
        if region:
            tk.Label(body, text=f"Región: {region}", font=("Segoe UI", 10)).pack(anchor="w", pady=2)

        if legacy:
            tk.Label(
                body,
                text=(
                    "Esta vinculación viene de una versión anterior, que no guardaba el nombre de usuario. "
                    "El control local del E10 sigue funcionando normalmente."
                ),
                fg="#777",
                wraplength=460,
                justify="left",
                font=("Segoe UI", 9),
            ).pack(anchor="w", pady=(12, 4))

        tk.Label(
            body,
            text=(
                "Desconectar la cuenta borra la sesión/identidad de Xiaomi guardada por la app. "
                "No borra el token local del robot ni tus mapas, zonas o programaciones."
            ),
            fg="#777",
            wraplength=460,
            justify="left",
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(12, 14))

        row = tk.Frame(body)
        row.pack(fill="x", side="bottom")
        tk.Button(row, text="Cerrar", command=self.destroy, relief="flat", padx=14, pady=8).pack(side="right")
        tk.Button(
            row,
            text="Desconectar cuenta Xiaomi",
            command=self._logout,
            relief="flat",
            fg=RED,
            padx=14,
            pady=8,
        ).pack(side="left")

    def _logout(self):
        if not messagebox.askyesno(
            "Desconectar cuenta Xiaomi",
            "¿Desconectar la cuenta Xiaomi de esta aplicación?\n\nEl control local del E10 seguirá guardado.",
            parent=self,
        ):
            return
        self.app.logout_xiaomi_account()
        self.destroy()


class App(app_v19.App):
    """v20: paredes por mapa + cuenta QR + pan/doble clic + flyout estable."""

    def __init__(self):
        self._map_pan = {}
        self._map_pan_drag_start = None
        self._map_pan_origin = (0.0, 0.0)
        self._account_card = None
        self._account_status_label = None
        self._account_user_label = None
        self._account_button = None
        self._quick_panel_hover = False
        self._quick_panel_close_job = None
        self._quick_panel_open_grace_until = 0
        super().__init__()

        # Las versiones anteriores no guardaban identidad de la cuenta. No
        # inventamos un usuario: sólo marcamos la vinculación como heredada.
        if (
            not self.settings.get("xiaomi_login_method")
            and self.settings.get("ip")
            and self.settings.get("token")
        ):
            self.settings["xiaomi_login_method"] = "qr_legacy"
            self.settings.setdefault("xiaomi_user_name", "")
            self.store.save(self.settings)

        self._install_xiaomi_account_card()
        self._refresh_xiaomi_account_card()

        if hasattr(self, "map_canvas"):
            self.map_canvas.configure(cursor="fleur")
            self.map_canvas.bind("<Double-Button-1>", self._map_double_click)

    # ---------------------------------------- paredes virtuales por mapa activo
    def _sync_no_go_async(self):
        if not self.vacuum or not self.plan_store:
            return

        plan = self.plan_store.snapshot()
        all_plan = self.plan_store.snapshot_all()
        any_managed = any(
            bool(value)
            for value in (all_plan.get("virtual_walls_managed_maps", {}) or {}).values()
        )

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

    # ----------------------------------------------------------- cuenta Xiaomi
    def _xiaomi_linked(self):
        return str(self.settings.get("xiaomi_login_method") or "") in ("qr", "qr_legacy")

    def _xiaomi_account_display(self):
        value = str(self.settings.get("xiaomi_user_name") or self.settings.get("xiaomi_user_id") or "").strip()
        if value:
            return value
        return "Usuario no guardado por la versión anterior"

    def _install_xiaomi_account_card(self):
        # Reutilizamos la página de Ajustes ya creada; no generamos otra página
        # encima porque eso ocultaría opciones anteriores.
        page = self._pages.get("settings")
        if page is None:
            return
        card = tk.Frame(page, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        card.pack(fill="x", padx=5, pady=5)
        self._account_card = card

        head = tk.Frame(card, bg=CARD)
        head.pack(fill="x", padx=20, pady=(16, 5))
        tk.Label(head, text="Cuenta Xiaomi", bg=CARD, fg=TEXT, font=("Segoe UI", 14, "bold")).pack(side="left")
        self._account_status_label = tk.Label(head, text="", bg=CARD, fg=MUTED, font=("Segoe UI", 9, "bold"))
        self._account_status_label.pack(side="right")

        self._account_user_label = tk.Label(card, text="", bg=CARD, fg=MUTED, font=("Segoe UI", 9), anchor="w")
        self._account_user_label.pack(fill="x", padx=20, pady=(3, 10))
        self._account_button = self._button(card, "", self.open_setup, accent=True, compact=True)
        self._account_button.pack(anchor="w", padx=20, pady=(0, 16))

    def _refresh_xiaomi_account_card(self):
        if not self._account_card:
            return
        if self._xiaomi_linked():
            self._account_status_label.configure(text="CONECTADO · QR", fg=GREEN)
            self._account_user_label.configure(
                text=f"{self._xiaomi_account_display()} · {self.settings.get('device_name') or 'Xiaomi Robot Vacuum E10'}"
            )
            self._account_button.configure(text="Ver cuenta / desconectar")
        else:
            self._account_status_label.configure(text="NO VINCULADO", fg=MUTED)
            self._account_user_label.configure(
                text="Podés vincular Xiaomi mediante QR para obtener y recordar la conexión del E10."
            )
            self._account_button.configure(text="Conectar con Xiaomi")

    def open_setup(self):
        if self._xiaomi_linked():
            LinkedAccountDialog(self)
            return
        app_v2.SetupDialog(self)

    def logout_xiaomi_account(self):
        for key in (
            "xiaomi_login_method",
            "xiaomi_user_id",
            "xiaomi_user_name",
            "cloud_session",
        ):
            self.settings[key] = ""
        self.store.save(self.settings)
        self._refresh_xiaomi_account_card()
        self._set_banner("Cuenta Xiaomi desconectada. El control local del E10 sigue disponible.")

    def _on_connected(self, ip):
        result = super()._on_connected(ip)
        self._refresh_xiaomi_account_card()
        return result

    # ----------------------------------------------------- flyout de bandeja
    def _quick_panel_pointer_inside(self, win):
        """True si el cursor está físicamente dentro del panel rápido."""
        try:
            if not win or not win.winfo_exists():
                return False
            px, py = self.winfo_pointerxy()
            x0 = win.winfo_rootx()
            y0 = win.winfo_rooty()
            x1 = x0 + win.winfo_width()
            y1 = y0 + win.winfo_height()
            return x0 <= px < x1 and y0 <= py < y1
        except Exception:
            return False

    def _cancel_quick_panel_close(self):
        job = self._quick_panel_close_job
        self._quick_panel_close_job = None
        if job:
            try:
                self.after_cancel(job)
            except Exception:
                pass

    def _schedule_quick_panel_close(self, delay=420):
        self._cancel_quick_panel_close()
        win = self._quick_panel
        if not win or not win.winfo_exists():
            return

        def check():
            self._quick_panel_close_job = None
            current = self._quick_panel
            if current is not win or not win.winfo_exists():
                return
            # Nunca cerramos si el mouse está sobre el panel, aunque Explorer
            # haya cerrado el flyout de iconos ocultos o haya cambiado el foco.
            if self._quick_panel_hover or self._quick_panel_pointer_inside(win):
                return
            try:
                import time
                if time.monotonic() < self._quick_panel_open_grace_until:
                    self._schedule_quick_panel_close(180)
                    return
            except Exception:
                pass
            try:
                win.destroy()
            except Exception:
                pass
            if self._quick_panel is win:
                self._quick_panel = None

        self._quick_panel_close_job = self.after(max(80, int(delay)), check)

    def _show_quick_panel(self):
        super()._show_quick_panel()
        win = self._quick_panel
        if not win or not win.winfo_exists():
            return

        import time
        self._quick_panel_hover = self._quick_panel_pointer_inside(win)
        # Da tiempo para mover el cursor desde el icono/flyout de Windows hasta
        # nuestro panel sin que desaparezca durante el pequeño hueco entre ambos.
        self._quick_panel_open_grace_until = time.monotonic() + 1.15
        self._cancel_quick_panel_close()

        def enter(_event=None):
            self._quick_panel_hover = True
            self._cancel_quick_panel_close()

        def leave(_event=None):
            self._quick_panel_hover = False
            self._schedule_quick_panel_close(460)

        def focus_out(_event=None):
            # El foco puede irse porque Explorer cerró su bandeja. Sólo cerramos
            # si además el cursor no está usando nuestro panel.
            if not self._quick_panel_pointer_inside(win):
                self._schedule_quick_panel_close(260)

        def close_now(_event=None):
            self._cancel_quick_panel_close()
            try:
                win.destroy()
            except Exception:
                pass
            if self._quick_panel is win:
                self._quick_panel = None

        win.bind("<Enter>", enter, add="+")
        win.bind("<Leave>", leave, add="+")
        win.bind("<FocusOut>", focus_out, add="+")
        win.bind("<Escape>", close_now, add="+")

    # ---------------------------------------------------------- pan del mapa
    def _reset_coordinate_session(self):
        result = super()._reset_coordinate_session()
        self._map_pan.clear()
        self._map_pan_drag_start = None
        return result

    def _render_map_canvas(self, canvas, snapshot):
        result = super()._render_map_canvas(canvas, snapshot)
        if canvas is getattr(self, "map_canvas", None):
            dx, dy = self._map_pan.get(canvas, (0.0, 0.0))
            if dx or dy:
                canvas.move("all", dx, dy)
            transform = self._map_transforms.get(canvas)
            if transform:
                transform["pan_x"] = dx
                transform["pan_y"] = dy
        return result

    def _canvas_to_world(self, canvas, x, y):
        dx, dy = self._map_pan.get(canvas, (0.0, 0.0))
        return super()._canvas_to_world(canvas, float(x) - dx, float(y) - dy)

    def _drawing_on_map(self):
        return bool(getattr(self, "_plan_draw_mode", None) or getattr(self, "room_edit_mode", False))

    def _map_press(self, event):
        if self._drawing_on_map():
            return super()._map_press(event)
        canvas = self.map_canvas
        self._map_pan_drag_start = (event.x, event.y)
        self._map_pan_origin = self._map_pan.get(canvas, (0.0, 0.0))
        canvas.configure(cursor="fleur")
        return "break"

    def _map_drag(self, event):
        if self._drawing_on_map():
            return super()._map_drag(event)
        if not self._map_pan_drag_start:
            return "break"
        canvas = self.map_canvas
        sx, sy = self._map_pan_drag_start
        ox, oy = self._map_pan_origin
        new_pan = (ox + event.x - sx, oy + event.y - sy)
        old_pan = self._map_pan.get(canvas, (0.0, 0.0))
        delta_x = new_pan[0] - old_pan[0]
        delta_y = new_pan[1] - old_pan[1]
        if delta_x or delta_y:
            canvas.move("all", delta_x, delta_y)
            self._map_pan[canvas] = new_pan
            transform = self._map_transforms.get(canvas)
            if transform:
                transform["pan_x"] = new_pan[0]
                transform["pan_y"] = new_pan[1]
        return "break"

    def _map_release(self, event):
        if self._drawing_on_map():
            return super()._map_release(event)
        self._map_pan_drag_start = None
        return "break"

    def _map_double_click(self, event):
        if self._drawing_on_map():
            return "break"
        point = self._canvas_to_world(self.map_canvas, event.x, event.y)
        if not point:
            return "break"
        self.selected_point = point
        if hasattr(self, "point_label"):
            self.point_label.configure(text=f"Objetivo · x {point[0]:.2f} · y {point[1]:.2f}")
        if hasattr(self, "point_clean_button"):
            self.point_clean_button.configure(state="normal")
        self._set_banner("Objetivo seleccionado. Usá “Limpiar aquí” para enviar el E10.")
        self._render_maps()
        return "break"


if __name__ == "__main__":
    app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        import traceback

        app_v19.app_v18.app_v17.app_v16.app_v15.app_v14.app_v13.app_v12.app_v11.app_v10.app_v9._save_crash_log(traceback.format_exc())
        raise
