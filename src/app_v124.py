import json
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox

import app_v123
import app_v9
from chatgpt_bridge import (
    AspiradoraMCPServer,
    CHATGPT_CONNECTORS_URL,
    PLATFORM_API_KEYS_URL,
    PLATFORM_TUNNELS_URL,
    TunnelClientManager,
    atomic_write_snapshot,
    clear_runtime_key,
    load_runtime_key,
    sanitize,
    save_runtime_key,
)


class App(app_v123.App):
    """V124: integración ChatGPT read-only mediante MCP + Secure MCP Tunnel."""

    SNAPSHOT_INTERVAL_MS = 2000

    def __init__(self):
        self._v124_mcp = None
        self._v124_tunnel = TunnelClientManager()
        self._v124_bridge_state = "desconectado"
        self._v124_bridge_detail = "Sólo lectura · listo para configurar"
        self._v124_bridge_connects = 0
        self._v124_bridge_errors = 0
        self._v124_bridge_last_error = None
        self._v124_bridge_window = None
        self._v124_bridge_status_label = None
        self._v124_bridge_card_status = None
        self._v124_tunnel_var = None
        self._v124_key_var = None
        self._v124_autoconnect_var = None
        super().__init__()

        self.settings.setdefault("chatgpt_tunnel_id", "")
        self.settings.setdefault("chatgpt_autoconnect", False)
        self._v124_install_chatgpt_card()
        self.after(600, self._v124_snapshot_tick)

        if (
            bool(self.settings.get("chatgpt_autoconnect"))
            and str(self.settings.get("chatgpt_tunnel_id") or "").strip()
            and load_runtime_key()
        ):
            self.after(1800, self._v124_autoconnect)

    # ============================================================= snapshot
    def _v124_safe_map_snapshot(self):
        try:
            snapshot = dict(self.local_map.snapshot() or {})
        except Exception:
            return {}

        # Este snapshot puede contener toda la geometría, habitaciones y
        # trayectoria, pero nunca credenciales.
        return sanitize(snapshot)

    def _v124_snapshot_payload(self):
        vacuum = getattr(self, "vacuum", None)
        motor_audit = []
        if vacuum is not None:
            try:
                motor_audit = list(
                    getattr(vacuum, "_motor_start_audit", []) or []
                )[-50:]
            except Exception:
                motor_audit = []

        robot = {
            "connected": bool(vacuum),
            "status_code": getattr(vacuum, "_last_status_code", None) if vacuum else None,
            "status_name": getattr(self, "_last_tray_status_name", None),
            "battery_percent": getattr(self, "_last_tray_battery", None),
            "raw_robot": getattr(self, "_v117_last_raw_robot", None),
            "raw_base": getattr(self, "_v117_last_raw_base", None),
            "pose": getattr(self, "_v117_live_pose", None),
        }
        mapping = {
            "active": bool(getattr(self, "mapping_active", False)),
            "phase": int(getattr(self, "mapping_phase", 0) or 0),
            "stage_v121": getattr(self, "_v121_stage", None),
            "transitioning": bool(getattr(self, "mapping_transitioning", False)),
            "phase2_requested": bool(getattr(self, "_v121_phase2_requested", False)),
            "phase2_started": bool(getattr(self, "_v121_phase2_started", False)),
            "phase2_departed": bool(getattr(self, "_v121_phase2_departed", False)),
            "last_status": getattr(self, "_v74_last_status", None),
            "v120_start": getattr(self, "_v120_last_start_diag", None),
            "v121_phase2": getattr(self, "_v121_phase2_diag", None),
            "v122_phase2": getattr(self, "_v122_last_phase2_diag", None),
            "v123_native": (
                getattr(vacuum, "_last_mapping_whole_home_diag", None)
                if vacuum is not None else None
            ),
        }

        diagnostic = ""
        try:
            diagnostic = str(self._diagnostic_text())
        except Exception as exc:
            diagnostic = f"Error generando diagnóstico: {type(exc).__name__}: {exc}"

        return sanitize({
            "schema": 1,
            "available": True,
            "read_only": True,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "robot": robot,
            "mapping": mapping,
            "map": self._v124_safe_map_snapshot(),
            "recent_events": motor_audit,
            "diagnostic": diagnostic,
        })

    def _v124_snapshot_tick(self):
        if getattr(self, "_closing", False):
            return
        try:
            atomic_write_snapshot(self._v124_snapshot_payload())
        except Exception:
            pass
        self.after(self.SNAPSHOT_INTERVAL_MS, self._v124_snapshot_tick)

    # ================================================================ UI
    def _v124_install_chatgpt_card(self):
        page = getattr(self, "_pages", {}).get("settings")
        if page is None:
            return

        card = tk.Frame(
            page,
            bg="#ffffff",
            highlightthickness=1,
            highlightbackground="#e8eaed",
        )
        card.pack(fill="x", padx=5, pady=5)

        tk.Label(
            card,
            text="ChatGPT",
            bg="#ffffff",
            fg="#17181a",
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w", padx=20, pady=(18, 4))

        tk.Label(
            card,
            text=(
                "Conexión directa de diagnóstico · sólo lectura. "
                "ChatGPT puede consultar estado, mapeo, mapa y F12 sin controlar el robot."
            ),
            bg="#ffffff",
            fg="#7b8088",
            font=("Segoe UI", 9),
            justify="left",
            wraplength=760,
        ).pack(anchor="w", padx=20, pady=(0, 10))

        self._v124_bridge_card_status = tk.Label(
            card,
            text="●  Desconectado · listo para configurar",
            bg="#ffffff",
            fg="#7b8088",
            font=("Segoe UI", 9, "bold"),
        )
        self._v124_bridge_card_status.pack(anchor="w", padx=20, pady=(0, 10))

        row = tk.Frame(card, bg="#ffffff")
        row.pack(fill="x", padx=20, pady=(0, 18))

        tk.Button(
            row,
            text="Conectar ChatGPT",
            command=self._v124_open_bridge_wizard,
            bg="#ff6900",
            fg="white",
            activebackground="#ea5f00",
            activeforeground="white",
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Segoe UI", 9, "bold"),
            padx=16,
            pady=8,
        ).pack(side="left")

    def _v124_update_bridge_labels(self):
        connected = self._v124_tunnel.connected()
        if connected:
            text = "●  Conectado a OpenAI · MCP sólo lectura activo"
            color = "#22a06b"
        elif self._v124_bridge_state == "conectando":
            text = "●  Conectando… " + str(self._v124_bridge_detail or "")
            color = "#ff6900"
        elif self._v124_bridge_state == "error":
            text = "●  Error de conexión · " + str(self._v124_bridge_detail or "")
            color = "#d93025"
        else:
            text = "●  Desconectado · " + str(self._v124_bridge_detail or "listo para configurar")
            color = "#7b8088"

        for label in (self._v124_bridge_card_status, self._v124_bridge_status_label):
            if label is not None:
                try:
                    label.configure(text=text, fg=color)
                except Exception:
                    pass

    def _v124_open_bridge_wizard(self):
        if self._v124_bridge_window and self._v124_bridge_window.winfo_exists():
            self._v124_bridge_window.lift()
            return

        win = tk.Toplevel(self)
        win.title("Conectar ChatGPT · Aspiradora Xiaomi")
        win.geometry("690x690")
        win.minsize(650, 620)
        win.transient(self)
        win.configure(bg="#f4f5f7")
        self._v124_bridge_window = win

        body = tk.Frame(win, bg="#ffffff", padx=24, pady=22)
        body.pack(fill="both", expand=True, padx=12, pady=12)

        tk.Label(
            body,
            text="Conectar ChatGPT",
            bg="#ffffff",
            fg="#17181a",
            font=("Segoe UI", 17, "bold"),
        ).pack(anchor="w")

        tk.Label(
            body,
            text=(
                "Esta integración usa el Secure MCP Tunnel oficial de OpenAI. "
                "La app queda privada en tu PC y sólo hace conexiones HTTPS salientes."
            ),
            bg="#ffffff",
            fg="#7b8088",
            font=("Segoe UI", 9),
            justify="left",
            wraplength=610,
        ).pack(anchor="w", pady=(6, 12))

        safe = tk.Frame(body, bg="#eaf7f0", padx=12, pady=10)
        safe.pack(fill="x", pady=(0, 14))
        tk.Label(
            safe,
            text="SOLO LECTURA",
            bg="#eaf7f0",
            fg="#16784a",
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")
        tk.Label(
            safe,
            text=(
                "ChatGPT puede leer diagnóstico, estado, trayectoria, grid y eventos. "
                "No puede iniciar limpieza, mover la aspiradora, volver a base ni modificar mapas."
            ),
            bg="#eaf7f0",
            fg="#16784a",
            font=("Segoe UI", 9),
            justify="left",
            wraplength=580,
        ).pack(anchor="w", pady=(2, 0))

        def section(title, text):
            tk.Label(
                body, text=title, bg="#ffffff", fg="#17181a",
                font=("Segoe UI", 10, "bold"),
            ).pack(anchor="w", pady=(8, 2))
            tk.Label(
                body, text=text, bg="#ffffff", fg="#7b8088",
                font=("Segoe UI", 9), justify="left", wraplength=610,
            ).pack(anchor="w", pady=(0, 5))

        section(
            "1 · Crear un túnel en OpenAI",
            "Se abre la página oficial. Creá un túnel para esta PC y copiá el tunnel_id.",
        )
        tk.Button(
            body, text="Abrir OpenAI Platform · Tunnels",
            command=lambda: webbrowser.open(PLATFORM_TUNNELS_URL),
            relief="flat", bg="#f1f3f5", fg="#17181a", padx=12, pady=6,
        ).pack(anchor="w", pady=(0, 5))

        self._v124_tunnel_var = tk.StringVar(
            value=str(self.settings.get("chatgpt_tunnel_id") or "")
        )
        tk.Entry(
            body,
            textvariable=self._v124_tunnel_var,
            font=("Consolas", 9),
            relief="solid",
            bd=1,
        ).pack(fill="x", pady=(0, 8), ipady=5)

        section(
            "2 · Crear una clave de ejecución",
            (
                "Abrí API Keys y creá una clave para el tunnel-client. "
                "La clave se guarda cifrada por Windows (DPAPI) y jamás entra al diagnóstico."
            ),
        )
        tk.Button(
            body, text="Abrir OpenAI Platform · API Keys",
            command=lambda: webbrowser.open(PLATFORM_API_KEYS_URL),
            relief="flat", bg="#f1f3f5", fg="#17181a", padx=12, pady=6,
        ).pack(anchor="w", pady=(0, 5))

        self._v124_key_var = tk.StringVar(value=load_runtime_key())
        tk.Entry(
            body,
            textvariable=self._v124_key_var,
            show="•",
            font=("Consolas", 9),
            relief="solid",
            bd=1,
        ).pack(fill="x", pady=(0, 8), ipady=5)

        self._v124_autoconnect_var = tk.BooleanVar(
            value=bool(self.settings.get("chatgpt_autoconnect", False))
        )
        tk.Checkbutton(
            body,
            text="Reconectar automáticamente al abrir Aspiradora Xiaomi",
            variable=self._v124_autoconnect_var,
            bg="#ffffff",
            fg="#17181a",
            activebackground="#ffffff",
        ).pack(anchor="w", pady=(1, 10))

        section(
            "3 · Conectar",
            (
                "Aspiradora descarga y verifica el tunnel-client oficial de OpenAI, "
                "inicia el servidor MCP local y comprueba que el túnel quede Ready."
            ),
        )
        actions = tk.Frame(body, bg="#ffffff")
        actions.pack(fill="x", pady=(0, 12))

        tk.Button(
            actions,
            text="Conectar",
            command=self._v124_connect_from_wizard,
            bg="#ff6900",
            fg="white",
            activebackground="#ea5f00",
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=16,
            pady=8,
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left")

        tk.Button(
            actions,
            text="Desconectar",
            command=self._v124_disconnect_bridge,
            bg="#f1f3f5",
            fg="#17181a",
            relief="flat",
            bd=0,
            padx=14,
            pady=8,
        ).pack(side="left", padx=(8, 0))

        self._v124_bridge_status_label = tk.Label(
            body,
            text="",
            bg="#ffffff",
            fg="#7b8088",
            font=("Segoe UI", 9, "bold"),
            justify="left",
            wraplength=610,
        )
        self._v124_bridge_status_label.pack(anchor="w", pady=(0, 10))
        self._v124_update_bridge_labels()

        section(
            "4 · Agregarlo en ChatGPT",
            (
                "Cuando arriba figure Conectado: abrí ChatGPT → Configuración → "
                "Conectores/Complementos → + → Conexión: Túnel, elegí o pegá el mismo tunnel_id "
                "y creá la app. Nombre recomendado: Aspiradora Xiaomi."
            ),
        )
        tk.Button(
            body,
            text="Abrir configuración de ChatGPT",
            command=lambda: webbrowser.open(CHATGPT_CONNECTORS_URL),
            relief="flat",
            bg="#f1f3f5",
            fg="#17181a",
            padx=12,
            pady=6,
        ).pack(anchor="w")

        tk.Label(
            body,
            text=(
                "Si tu cuenta de ChatGPT todavía no muestra conexión por Túnel/MCP, "
                "la integración queda preparada en la app y podrás activarla cuando esa opción esté disponible."
            ),
            bg="#ffffff",
            fg="#7b8088",
            font=("Segoe UI", 8),
            justify="left",
            wraplength=610,
        ).pack(anchor="w", pady=(12, 0))

    # ========================================================= conexión
    def _v124_set_bridge_state(self, state, detail=""):
        self._v124_bridge_state = str(state)
        self._v124_bridge_detail = str(detail or "")
        self._v124_update_bridge_labels()

    def _v124_connect_from_wizard(self):
        tunnel_id = str(self._v124_tunnel_var.get() if self._v124_tunnel_var else "").strip()
        api_key = str(self._v124_key_var.get() if self._v124_key_var else "").strip()
        auto = bool(self._v124_autoconnect_var.get()) if self._v124_autoconnect_var else False

        if not tunnel_id or not api_key:
            messagebox.showinfo(
                "Conectar ChatGPT",
                "Completá el tunnel_id y la clave de ejecución.",
                parent=self._v124_bridge_window or self,
            )
            return

        self.settings["chatgpt_tunnel_id"] = tunnel_id
        self.settings["chatgpt_autoconnect"] = auto
        self.store.save(self.settings)
        try:
            save_runtime_key(api_key)
        except Exception as exc:
            messagebox.showerror(
                "Clave de ChatGPT",
                f"No pude guardar la clave de forma segura en Windows.\n\n{exc}",
                parent=self._v124_bridge_window or self,
            )
            return

        self._v124_begin_bridge_connect(tunnel_id, api_key)

    def _v124_begin_bridge_connect(self, tunnel_id, api_key):
        if self._v124_bridge_state == "conectando":
            return
        self._v124_set_bridge_state("conectando", "iniciando servidor MCP local…")

        def worker():
            try:
                if self._v124_mcp is None:
                    self._v124_mcp = AspiradoraMCPServer()
                endpoint = self._v124_mcp.start()
                self._post_ui("v124_bridge_progress", "MCP local activo · preparando túnel oficial…")

                result = self._v124_tunnel.start(
                    tunnel_id,
                    api_key,
                    endpoint,
                    progress=lambda text: self._post_ui("v124_bridge_progress", text),
                )
                self._post_ui("v124_bridge_connected", result)
            except Exception as exc:
                self._post_ui(
                    "v124_bridge_error",
                    str(exc).strip() or type(exc).__name__,
                )

        threading.Thread(
            target=worker,
            name="AspiradoraChatGPTConnect",
            daemon=True,
        ).start()

    def _v124_autoconnect(self):
        tunnel_id = str(self.settings.get("chatgpt_tunnel_id") or "").strip()
        api_key = load_runtime_key()
        if tunnel_id and api_key:
            self._v124_begin_bridge_connect(tunnel_id, api_key)

    def _v124_disconnect_bridge(self):
        try:
            self._v124_tunnel.stop()
        except Exception:
            pass
        self.settings["chatgpt_autoconnect"] = False
        self.store.save(self.settings)
        self._v124_set_bridge_state("desconectado", "conexión detenida por el usuario")

    def _handle_ui_event(self, kind, payload):
        if kind == "v124_bridge_progress":
            self._v124_set_bridge_state("conectando", str(payload[0]))
            return None

        if kind == "v124_bridge_connected":
            self._v124_bridge_connects += 1
            self._v124_bridge_last_error = None
            self._v124_set_bridge_state(
                "conectado",
                "túnel Ready · ya podés agregar Aspiradora Xiaomi en ChatGPT",
            )
            self._set_banner("ChatGPT conectado en modo sólo lectura.")
            return None

        if kind == "v124_bridge_error":
            self._v124_bridge_errors += 1
            self._v124_bridge_last_error = str(payload[0])
            self._v124_set_bridge_state("error", str(payload[0])[:220])
            return None

        return super()._handle_ui_event(kind, payload)

    # =========================================================== diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        tunnel_id = str(
            getattr(self, "settings", {}).get("chatgpt_tunnel_id") or ""
        )
        if len(tunnel_id) > 16:
            tunnel_visible = tunnel_id[:10] + "…" + tunnel_id[-6:]
        else:
            tunnel_visible = "—"

        endpoint = getattr(self._v124_mcp, "endpoint", None) if self._v124_mcp else None
        lines = [
            "DIAGNÓSTICO V124 ACTIVO · ChatGPT MCP read-only",
            "================================================",
            (
                f"estado={self._v124_bridge_state} · connects="
                f"{self._v124_bridge_connects} · errores={self._v124_bridge_errors}"
            ),
            f"tunnel_id={tunnel_visible} · clave guardada DPAPI={bool(load_runtime_key())}",
            f"MCP local={endpoint or 'apagado'} · túnel vivo={self._v124_tunnel.connected()}",
            f"último error={self._v124_bridge_last_error or '—'}",
            "tools MCP: get_robot_status, get_mapping_state, get_map_data, get_recent_events, get_full_diagnostic, get_full_snapshot",
            "seguridad V124: integración sólo lectura; no expone acciones de movimiento, limpieza, dock ni edición de mapas",
            "seguridad V124: token Xiaomi, IP, URLs firmadas y clave OpenAI se omiten/redactan del snapshot",
            "seguridad V124: la clave OpenAI se guarda cifrada con Windows DPAPI y sólo se entrega al proceso tunnel-client por variable de entorno",
            "",
            "",
        ]
        return "\n".join(lines) + inherited

    def destroy(self):
        try:
            self._v124_tunnel.stop()
        except Exception:
            pass
        try:
            if self._v124_mcp is not None:
                self._v124_mcp.stop()
        except Exception:
            pass
        return super().destroy()


if __name__ == "__main__":
    app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        app_v9._save_crash_log(app_v9.traceback.format_exc())
        raise
