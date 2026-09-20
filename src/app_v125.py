import tkinter as tk
import webbrowser

import app_v124
import app_v9
from chatgpt_bridge import (
    CHATGPT_CONNECTORS_URL,
    PLATFORM_API_KEYS_URL,
    PLATFORM_TUNNELS_URL,
    load_runtime_key,
)


OPENAI_MCP_HELP_URL = (
    "https://help.openai.com/en/articles/"
    "12584461-developer-mode-and-mcp-apps-in-chatgpt"
)


class App(app_v124.App):
    """V125: asistente ChatGPT scrollable + estados de vínculo honestos."""

    def __init__(self):
        self._v125_wizard_canvas = None
        self._v125_wizard_inner = None
        self._v125_wizard_window_item = None
        super().__init__()

    # ==================================================== estado inequívoco
    def _v124_update_bridge_labels(self):
        connected = self._v124_tunnel.connected()
        if connected:
            text = (
                "●  Túnel OpenAI conectado · falta vincular la app en ChatGPT"
            )
            color = "#22a06b"
        elif self._v124_bridge_state == "conectando":
            text = "●  Conectando túnel… " + str(
                self._v124_bridge_detail or ""
            )
            color = "#ff6900"
        elif self._v124_bridge_state == "error":
            text = "●  Error del túnel · " + str(
                self._v124_bridge_detail or ""
            )
            color = "#d93025"
        else:
            text = "●  Túnel desconectado · " + str(
                self._v124_bridge_detail or "listo para configurar"
            )
            color = "#7b8088"

        for label in (
            self._v124_bridge_card_status,
            self._v124_bridge_status_label,
        ):
            if label is not None:
                try:
                    label.configure(text=text, fg=color)
                except Exception:
                    pass

    def _handle_ui_event(self, kind, payload):
        if kind == "v124_bridge_connected":
            self._v124_bridge_connects += 1
            self._v124_bridge_last_error = None
            self._v124_set_bridge_state(
                "conectado",
                "túnel Ready · falta vincular la app en ChatGPT",
            )
            self._set_banner(
                "Túnel OpenAI conectado. Falta vincular Aspiradora Xiaomi "
                "desde ChatGPT si tu plan admite MCP personalizado."
            )
            return None
        return super()._handle_ui_event(kind, payload)

    # ======================================================= wizard scroll
    def _v125_scroll_to_bottom(self):
        canvas = self._v125_wizard_canvas
        if canvas is not None:
            try:
                canvas.update_idletasks()
                canvas.yview_moveto(1.0)
            except Exception:
                pass

    def _v124_open_bridge_wizard(self):
        if (
            self._v124_bridge_window
            and self._v124_bridge_window.winfo_exists()
        ):
            self._v124_bridge_window.lift()
            return

        win = tk.Toplevel(self)
        win.title("Conectar ChatGPT · Aspiradora Xiaomi")
        win.geometry("735x720")
        win.minsize(650, 540)
        win.transient(self)
        win.configure(bg="#f4f5f7")
        self._v124_bridge_window = win

        shell = tk.Frame(win, bg="#f4f5f7")
        shell.pack(fill="both", expand=True)

        canvas = tk.Canvas(
            shell,
            bg="#f4f5f7",
            highlightthickness=0,
            bd=0,
        )
        scrollbar = tk.Scrollbar(
            shell,
            orient="vertical",
            command=canvas.yview,
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        body = tk.Frame(canvas, bg="#ffffff", padx=24, pady=22)
        window_item = canvas.create_window(
            (12, 12),
            window=body,
            anchor="nw",
        )
        self._v125_wizard_canvas = canvas
        self._v125_wizard_inner = body
        self._v125_wizard_window_item = window_item

        def sync_scroll(_event=None):
            try:
                canvas.configure(scrollregion=canvas.bbox("all"))
            except Exception:
                pass

        def sync_width(event):
            try:
                canvas.itemconfigure(
                    window_item,
                    width=max(560, int(event.width) - 36),
                )
            except Exception:
                pass

        def wheel(event):
            try:
                units = -1 if int(event.delta) > 0 else 1
                canvas.yview_scroll(units * 3, "units")
            except Exception:
                pass

        def close():
            try:
                canvas.unbind_all("<MouseWheel>")
            except Exception:
                pass
            self._v124_bridge_window = None
            try:
                win.destroy()
            except Exception:
                pass

        body.bind("<Configure>", sync_scroll)
        canvas.bind("<Configure>", sync_width)
        canvas.bind_all("<MouseWheel>", wheel)
        win.protocol("WM_DELETE_WINDOW", close)

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
                "La conexión tiene dos partes independientes: primero el "
                "Secure MCP Tunnel, después registrar Aspiradora Xiaomi "
                "dentro de ChatGPT."
            ),
            bg="#ffffff",
            fg="#7b8088",
            font=("Segoe UI", 9),
            justify="left",
            wraplength=620,
        ).pack(anchor="w", pady=(6, 10))

        quick = tk.Frame(body, bg="#ffffff")
        quick.pack(fill="x", pady=(0, 12))
        tk.Button(
            quick,
            text="Ya conecté el túnel · ir al Paso 4",
            command=self._v125_scroll_to_bottom,
            bg="#f1f3f5",
            fg="#17181a",
            relief="flat",
            bd=0,
            padx=12,
            pady=7,
        ).pack(side="left")

        safe = tk.Frame(body, bg="#eaf7f0", padx=12, pady=10)
        safe.pack(fill="x", pady=(0, 12))
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
                "ChatGPT puede consultar diagnóstico, estado, trayectoria, "
                "grid y eventos. No puede iniciar limpieza, mover el robot, "
                "volver a base ni modificar mapas."
            ),
            bg="#eaf7f0",
            fg="#16784a",
            font=("Segoe UI", 9),
            justify="left",
            wraplength=610,
        ).pack(anchor="w", pady=(2, 0))

        compatibility = tk.Frame(
            body,
            bg="#fff7e8",
            padx=12,
            pady=10,
        )
        compatibility.pack(fill="x", pady=(0, 14))
        tk.Label(
            compatibility,
            text="COMPATIBILIDAD ACTUAL DE CHATGPT",
            bg="#fff7e8",
            fg="#8a5a00",
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")
        tk.Label(
            compatibility,
            text=(
                "Según la documentación actual de OpenAI, Pro admite MCP "
                "personalizado para lectura/fetch y Business/Enterprise/Edu "
                "admiten soporte MCP más completo. ChatGPT Plus no figura "
                "actualmente entre los planes habilitados para registrar "
                "MCP personalizados. Por eso el túnel puede quedar Ready "
                "aunque ChatGPT no muestre la opción de agregar la app."
            ),
            bg="#fff7e8",
            fg="#8a5a00",
            font=("Segoe UI", 9),
            justify="left",
            wraplength=610,
        ).pack(anchor="w", pady=(2, 7))
        tk.Button(
            compatibility,
            text="Ver compatibilidad oficial de OpenAI",
            command=lambda: webbrowser.open(OPENAI_MCP_HELP_URL),
            bg="#ffffff",
            fg="#17181a",
            relief="flat",
            bd=0,
            padx=10,
            pady=5,
        ).pack(anchor="w")

        def section(title, text):
            tk.Label(
                body,
                text=title,
                bg="#ffffff",
                fg="#17181a",
                font=("Segoe UI", 10, "bold"),
            ).pack(anchor="w", pady=(8, 2))
            tk.Label(
                body,
                text=text,
                bg="#ffffff",
                fg="#7b8088",
                font=("Segoe UI", 9),
                justify="left",
                wraplength=620,
            ).pack(anchor="w", pady=(0, 5))

        section(
            "1 · Crear un túnel en OpenAI",
            "Creá un túnel para esta PC y copiá el tunnel_id.",
        )
        tk.Button(
            body,
            text="Abrir OpenAI Platform · Tunnels",
            command=lambda: webbrowser.open(PLATFORM_TUNNELS_URL),
            relief="flat",
            bg="#f1f3f5",
            fg="#17181a",
            padx=12,
            pady=6,
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
                "La clave se usa sólo por tunnel-client y queda cifrada con "
                "Windows DPAPI. Nunca se expone al diagnóstico MCP."
            ),
        )
        tk.Button(
            body,
            text="Abrir OpenAI Platform · API Keys",
            command=lambda: webbrowser.open(PLATFORM_API_KEYS_URL),
            relief="flat",
            bg="#f1f3f5",
            fg="#17181a",
            padx=12,
            pady=6,
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
            "3 · Conectar el túnel",
            (
                "La app inicia el servidor MCP local y el cliente oficial "
                "de OpenAI. Un estado Ready confirma el túnel, no todavía "
                "la instalación de la app dentro de ChatGPT."
            ),
        )
        actions = tk.Frame(body, bg="#ffffff")
        actions.pack(fill="x", pady=(0, 10))
        tk.Button(
            actions,
            text="Conectar túnel",
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
            wraplength=620,
        )
        self._v124_bridge_status_label.pack(
            anchor="w",
            pady=(0, 14),
        )
        self._v124_update_bridge_labels()

        separator = tk.Frame(body, bg="#e8eaed", height=1)
        separator.pack(fill="x", pady=(4, 12))

        section(
            "4 · Vincular Aspiradora Xiaomi dentro de ChatGPT",
            (
                "Este paso depende del plan de ChatGPT. Si tu cuenta muestra "
                "Apps/Developer Mode para MCP personalizado, creá la app y "
                "seleccioná la conexión por Secure MCP Tunnel usando el mismo "
                "tunnel_id. Nombre recomendado: Aspiradora Xiaomi."
            ),
        )
        tk.Button(
            body,
            text="Abrir configuración de ChatGPT",
            command=lambda: webbrowser.open(CHATGPT_CONNECTORS_URL),
            relief="flat",
            bg="#ff6900",
            fg="white",
            activebackground="#ea5f00",
            activeforeground="white",
            padx=14,
            pady=7,
        ).pack(anchor="w", pady=(0, 6))
        tk.Button(
            body,
            text="Ver ayuda oficial de MCP",
            command=lambda: webbrowser.open(OPENAI_MCP_HELP_URL),
            relief="flat",
            bg="#f1f3f5",
            fg="#17181a",
            padx=12,
            pady=6,
        ).pack(anchor="w")

        tk.Label(
            body,
            text=(
                "Si ChatGPT no ofrece la creación de una app MCP personalizada, "
                "no hay un paso oculto en Aspiradora Xiaomi: la limitación está "
                "del lado del plan/cuenta de ChatGPT. El túnel puede quedar "
                "guardado y reconectarse automáticamente para cuando esa "
                "capacidad esté disponible."
            ),
            bg="#ffffff",
            fg="#7b8088",
            font=("Segoe UI", 8),
            justify="left",
            wraplength=620,
        ).pack(anchor="w", pady=(12, 18))

        sync_scroll()

    # =========================================================== diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        lines = [
            "DIAGNÓSTICO V125 ACTIVO · wizard ChatGPT scrollable",
            "===================================================",
            "estado visual V125: túnel OpenAI != app vinculada en ChatGPT",
            "wizard: canvas vertical + rueda + botón directo al Paso 4",
            "compatibilidad mostrada: Plus sin MCP personalizado; Pro read/fetch; Business/Enterprise/Edu MCP ampliado",
            "regla V125: nunca afirmar 'ChatGPT conectado' sólo porque tunnel-client está Ready",
            "",
            "",
        ]
        return "\n".join(lines) + inherited


if __name__ == "__main__":
    app_v9._save_crash_log("")
    try:
        App().mainloop()
    except Exception:
        app_v9._save_crash_log(app_v9.traceback.format_exc())
        raise
