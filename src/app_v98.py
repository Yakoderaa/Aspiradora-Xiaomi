import math
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk

import app_v97
import app_v9
from updater import check_for_update, download_and_install
from version import VERSION


LIGHT = {
    "app_bg": "#f4f5f7",
    "card": "#ffffff",
    "card_alt": "#f8f9fb",
    "text": "#17181a",
    "muted": "#7b8088",
    "border": "#e8eaed",
    "accent": "#ff6900",
    "accent_soft": "#fff1e7",
    "blue_soft": "#dceeff",
    "map_bg": "#f7f9fb",
}
DARK = {
    "app_bg": "#0f1115",
    "card": "#171a21",
    "card_alt": "#20242d",
    "text": "#f3f5f7",
    "muted": "#9aa3ad",
    "border": "#2a303b",
    "accent": "#ff6900",
    "accent_soft": "#332013",
    "blue_soft": "#13283b",
    "map_bg": "#10141a",
}

STATIC_TRANSLATIONS = {
    "Inicio": {"en": "Home", "pt": "Início"},
    "Mapa local": {"en": "Local map", "pt": "Mapa local"},
    "Robot": {"en": "Robot", "pt": "Robô"},
    "Ajustes": {"en": "Settings", "pt": "Configurações"},
    "Programar": {"en": "Schedule", "pt": "Agendar"},
    "Configurar": {"en": "Configure", "pt": "Configurar"},
    "Buscar actualizaciones": {"en": "Check for updates", "pt": "Buscar atualizações"},
    "Limpieza": {"en": "Cleaning", "pt": "Limpeza"},
    "Iniciar limpieza": {"en": "Start cleaning", "pt": "Iniciar limpeza"},
    "Detener": {"en": "Stop", "pt": "Parar"},
    "Volver a base": {"en": "Return to dock", "pt": "Voltar à base"},
    "Encontrar": {"en": "Locate", "pt": "Localizar"},
    "Modo": {"en": "Mode", "pt": "Modo"},
    "Aspirar": {"en": "Vacuum", "pt": "Aspirar"},
    "Aspirar + trapear": {"en": "Vacuum + mop", "pt": "Aspirar + passar pano"},
    "Trapear": {"en": "Mop", "pt": "Passar pano"},
    "Mopa": {"en": "Mop", "pt": "Pano"},
    "Succión": {"en": "Suction", "pt": "Sucção"},
    "Agua": {"en": "Water", "pt": "Água"},
    "Silencio": {"en": "Quiet", "pt": "Silencioso"},
    "Normal": {"en": "Normal", "pt": "Normal"},
    "Fuerte": {"en": "Strong", "pt": "Forte"},
    "Turbo": {"en": "Turbo", "pt": "Turbo"},
    "Baja": {"en": "Low", "pt": "Baixa"},
    "Media": {"en": "Medium", "pt": "Média"},
    "Alta": {"en": "High", "pt": "Alta"},
    "Off": {"en": "Off", "pt": "Desligada"},
    "ESTADO": {"en": "STATUS", "pt": "ESTADO"},
    "BATERÍA": {"en": "BATTERY", "pt": "BATERIA"},
    "ÁREA": {"en": "AREA", "pt": "ÁREA"},
    "TIEMPO": {"en": "TIME", "pt": "TEMPO"},
    "Abrir mapa": {"en": "Open map", "pt": "Abrir mapa"},
    "Crear desde cero": {"en": "Create from scratch", "pt": "Criar do zero"},
    "Finalizar": {"en": "Finish", "pt": "Finalizar"},
    "Añadir habitación": {"en": "Add room", "pt": "Adicionar cômodo"},
    "Enviar robot": {"en": "Send robot", "pt": "Enviar robô"},
    "Limpiar aquí": {"en": "Clean here", "pt": "Limpar aqui"},
    "Habitaciones locales": {"en": "Local rooms", "pt": "Cômodos locais"},
    "Cuenta Xiaomi": {"en": "Xiaomi account", "pt": "Conta Xiaomi"},
    "Windows y bandeja de sistema": {"en": "Windows and system tray", "pt": "Windows e bandeja do sistema"},
    "Configurar acciones rápidas": {"en": "Configure quick actions", "pt": "Configurar ações rápidas"},
    "Tema e idioma": {"en": "Theme and language", "pt": "Tema e idioma"},
    "Tema": {"en": "Theme", "pt": "Tema"},
    "Idioma": {"en": "Language", "pt": "Idioma"},
    "Claro": {"en": "Light", "pt": "Claro"},
    "Oscuro": {"en": "Dark", "pt": "Escuro"},
    "Español": {"en": "Spanish", "pt": "Espanhol"},
    "English": {"en": "English", "pt": "English"},
    "Português": {"en": "Portuguese", "pt": "Português"},
    "Desconectado": {"en": "Disconnected", "pt": "Desconectado"},
    "Cargando": {"en": "Charging", "pt": "Carregando"},
    "Aspirando": {"en": "Cleaning", "pt": "Aspirando"},
    "Volviendo a la base": {"en": "Returning to dock", "pt": "Voltando à base"},
    "En espera": {"en": "Idle", "pt": "Em espera"},
    "Sin errores": {"en": "No errors", "pt": "Sem erros"},
    "Mapa": {"en": "Map", "pt": "Mapa"},
    "Estado": {"en": "Status", "pt": "Estado"},
}

PAGE_TITLES = {
    "es": {"home": "Inicio", "map": "Mapa local", "robot": "Robot", "settings": "Ajustes", "scheduler": "Programar"},
    "en": {"home": "Home", "map": "Local map", "robot": "Robot", "settings": "Settings", "scheduler": "Schedule"},
    "pt": {"home": "Início", "map": "Mapa local", "robot": "Robô", "settings": "Configurações", "scheduler": "Agendar"},
}
NAV_TITLES = PAGE_TITLES


class App(app_v97.App):
    """V98: tema/idioma persistentes + update integrado + arranque sin parpadeos."""

    def __init__(self):
        self._v98_start_hidden = True
        self._v98_shown_once = False
        self._v98_theme_widgets = {}
        self._v98_static_sources = {}
        self._v98_update_window = None
        self._v98_update_progress = None
        self._v98_update_stage = None
        self._v98_update_detail = None
        super().__init__()

        self.settings.setdefault("theme", "light")
        self.settings.setdefault("language", "es")
        self._v98_install_preferences_card()
        self._v98_apply_theme(self.settings.get("theme", "light"), save=False)
        self._v98_apply_language(self.settings.get("language", "es"), save=False)
        self.after_idle(self._v98_show_once)

    # ======================================================= arranque estable
    def _build_ui(self):
        # Tk ya existe en este punto, pero todavía no construimos widgets.
        # Ocultamos el root para que Windows nunca vea geometrías intermedias.
        try:
            self.withdraw()
        except Exception:
            pass
        return super()._build_ui()

    def _v39_restore_saved_window(self):
        # V39 lo hacía cuatro veces. V98 aplica la geometría una sola vez justo
        # antes de mostrar la ventana.
        return None

    def _center_initial_window(self):
        restored = None
        try:
            restored = self._validated_saved_geometry()
        except Exception:
            restored = None
        if restored:
            width, height, x, y = restored
            self.geometry(f"{width}x{height}+{x}+{y}")
            self._v38_last_normal_geometry = f"{width}x{height}+{x}+{y}"
            return
        # Primer uso: calcula el centro mientras el root sigue oculto.
        return super()._center_initial_window()

    def _v98_show_once(self):
        if self._v98_shown_once:
            return
        self._v98_shown_once = True
        try:
            restored = self._validated_saved_geometry()
            if restored:
                width, height, x, y = restored
                self.geometry(f"{width}x{height}+{x}+{y}")
                self._v38_last_normal_geometry = f"{width}x{height}+{x}+{y}"
            self.update_idletasks()

            # --tray debe permanecer oculto desde el primer frame.
            if "--tray" in sys.argv:
                return

            wanted = str((self.settings or {}).get("window_state") or "normal")
            self.deiconify()
            if wanted == "zoomed":
                try:
                    self.state("zoomed")
                except Exception:
                    pass
            else:
                try:
                    self.state("normal")
                except Exception:
                    pass
            self.lift()
        except Exception:
            try:
                self.deiconify()
            except Exception:
                pass

    # ==================================================== preferencias UI
    def _v98_install_preferences_card(self):
        page = self._pages.get("settings")
        if page is None:
            return

        card = tk.Frame(page, bg="#ffffff", highlightthickness=1, highlightbackground="#e8eaed")
        card.pack(fill="x", padx=5, pady=5)

        self._v98_preferences_title = tk.Label(
            card, text="Tema e idioma", bg="#ffffff", fg="#17181a",
            font=("Segoe UI", 14, "bold")
        )
        self._v98_preferences_title.pack(anchor="w", padx=20, pady=(18, 5))
        self._v98_preferences_hint = tk.Label(
            card,
            text="Los cambios se guardan automáticamente y se conservan al reiniciar.",
            bg="#ffffff", fg="#7b8088", font=("Segoe UI", 9),
        )
        self._v98_preferences_hint.pack(anchor="w", padx=20, pady=(0, 12))

        row = tk.Frame(card, bg="#ffffff")
        row.pack(fill="x", padx=20, pady=(0, 18))

        tk.Label(row, text="Tema", bg="#ffffff", fg="#7b8088", font=("Segoe UI", 9, "bold")).pack(side="left")
        self._v98_theme_var = tk.StringVar(value="Claro")
        self._v98_theme_combo = ttk.Combobox(
            row,
            state="readonly",
            width=12,
            textvariable=self._v98_theme_var,
            values=("Claro", "Oscuro"),
        )
        self._v98_theme_combo.pack(side="left", padx=(8, 24))
        self._v98_theme_combo.bind("<<ComboboxSelected>>", self._v98_theme_changed)

        tk.Label(row, text="Idioma", bg="#ffffff", fg="#7b8088", font=("Segoe UI", 9, "bold")).pack(side="left")
        self._v98_language_var = tk.StringVar(value="Español")
        self._v98_language_combo = ttk.Combobox(
            row,
            state="readonly",
            width=14,
            textvariable=self._v98_language_var,
            values=("Español", "English", "Português"),
        )
        self._v98_language_combo.pack(side="left", padx=(8, 0))
        self._v98_language_combo.bind("<<ComboboxSelected>>", self._v98_language_changed)

    def _v98_theme_changed(self, _event=None):
        value = str(self._v98_theme_var.get() or "")
        self._v98_apply_theme("dark" if value in ("Oscuro", "Dark", "Escuro") else "light", save=True)

    def _v98_language_changed(self, _event=None):
        value = str(self._v98_language_var.get() or "")
        code = {"Español": "es", "Spanish": "es", "English": "en", "Português": "pt", "Portuguese": "pt"}.get(value, "es")
        self._v98_apply_language(code, save=True)

    @staticmethod
    def _v98_palette(name):
        return DARK if str(name).lower() == "dark" else LIGHT

    @staticmethod
    def _v98_color_role(value):
        value = str(value or "").lower()
        roles = {
            "#f4f5f7": "app_bg", "#0f1115": "app_bg",
            "#ffffff": "card", "#171a21": "card",
            "#f8f9fb": "card_alt", "#20242d": "card_alt",
            "#17181a": "text", "#f3f5f7": "text",
            "#7b8088": "muted", "#9aa3ad": "muted",
            "#e8eaed": "border", "#2a303b": "border",
            "#ff6900": "accent",
            "#fff1e7": "accent_soft", "#332013": "accent_soft",
            "#dceeff": "blue_soft", "#13283b": "blue_soft",
            "#f7f9fb": "map_bg", "#10141a": "map_bg",
        }
        return roles.get(value)

    def _v98_theme_walk(self, widget, palette):
        try:
            wid = str(widget)
        except Exception:
            wid = repr(widget)
        role_map = self._v98_theme_widgets.setdefault(wid, {})

        for option in ("background", "foreground", "activebackground", "activeforeground", "highlightbackground", "troughcolor"):
            try:
                current = widget.cget(option)
            except Exception:
                continue
            role = role_map.get(option)
            if not role:
                role = self._v98_color_role(current)
                if role:
                    role_map[option] = role
            if role and role in palette:
                try:
                    widget.configure(**{option: palette[role]})
                except Exception:
                    pass

        for child in widget.winfo_children():
            self._v98_theme_walk(child, palette)

    def _v98_apply_theme(self, theme, save=True):
        theme = "dark" if str(theme).lower() == "dark" else "light"
        palette = self._v98_palette(theme)
        self.settings["theme"] = theme
        try:
            lang = str(self.settings.get("language") or "es")
            labels = {
                "es": {"light": "Claro", "dark": "Oscuro"},
                "en": {"light": "Light", "dark": "Dark"},
                "pt": {"light": "Claro", "dark": "Escuro"},
            }
            self._v98_theme_combo.configure(values=tuple(labels.get(lang, labels["es"]).values()))
            self._v98_theme_var.set(labels.get(lang, labels["es"])[theme])
        except Exception:
            pass

        try:
            self.configure(bg=palette["app_bg"])
            self._v98_theme_walk(self, palette)
            style = ttk.Style(self)
            style.configure(
                "TCombobox",
                fieldbackground=palette["card_alt"],
                background=palette["card_alt"],
                foreground=palette["text"],
                bordercolor=palette["border"],
                arrowcolor=palette["text"],
            )
            style.map(
                "TCombobox",
                fieldbackground=[("readonly", palette["card_alt"])],
                foreground=[("readonly", palette["text"])],
            )
            style.configure(
                "Vacuum.Horizontal.TProgressbar",
                troughcolor=palette["card_alt"],
                background=palette["accent"],
                bordercolor=palette["card_alt"],
                lightcolor=palette["accent"],
                darkcolor=palette["accent"],
            )
        except Exception:
            pass

        if save:
            self.store.save(self.settings)
            self._set_banner(
                "Tema oscuro aplicado." if theme == "dark" else "Tema claro aplicado."
            )

    # ============================================================ traducción
    def _v98_translate(self, text):
        lang = str(self.settings.get("language") or "es")
        if lang == "es":
            return str(text)
        raw = str(text)
        if raw in STATIC_TRANSLATIONS:
            return STATIC_TRANSLATIONS[raw].get(lang, raw)

        prefixes = [
            ("Batería ", "Battery " if lang == "en" else "Bateria "),
            ("Conectado · ", "Connected · " if lang == "en" else "Conectado · "),
            ("Código ", "Code " if lang == "en" else "Código "),
            ("Mapas · ", "Maps · " if lang == "en" else "Mapas · "),
            ("Actualización ", "Update " if lang == "en" else "Atualização "),
        ]
        for src, dst in prefixes:
            if raw.startswith(src):
                return dst + raw[len(src):]
        return STATIC_TRANSLATIONS.get(raw, {}).get(lang, raw)

    def _v98_language_walk(self, widget):
        try:
            text = widget.cget("text")
        except Exception:
            text = None
        if text is not None:
            wid = str(widget)
            source = self._v98_static_sources.get(wid)
            if source is None:
                source = str(text)
                self._v98_static_sources[wid] = source
            translated = self._v98_translate(source)
            try:
                widget.configure(text=translated)
            except Exception:
                pass
        for child in widget.winfo_children():
            self._v98_language_walk(child)

    def _v98_apply_language(self, language, save=True):
        language = str(language or "es").lower()
        if language not in ("es", "en", "pt"):
            language = "es"
        self.settings["language"] = language
        try:
            self._v98_language_var.set({"es": "Español", "en": "English", "pt": "Português"}[language])
            theme = str(self.settings.get("theme") or "light")
            labels = {
                "es": {"light": "Claro", "dark": "Oscuro"},
                "en": {"light": "Light", "dark": "Dark"},
                "pt": {"light": "Claro", "dark": "Escuro"},
            }
            self._v98_theme_combo.configure(values=tuple(labels[language].values()))
            self._v98_theme_var.set(labels[language].get(theme, labels[language]["light"]))
        except Exception:
            pass
        self._v98_language_walk(self)

        # Los nombres de navegación se fijan por clave, no por el texto previo.
        for key, button in getattr(self, "_nav_buttons", {}).items():
            title = NAV_TITLES.get(language, NAV_TITLES["es"]).get(key)
            if title:
                try:
                    button.configure(text=title)
                except Exception:
                    pass

        current = None
        try:
            for key, frame in self._pages.items():
                if str(frame) == str(self.page_title.master.master.nametowidget(frame.winfo_name())):
                    current = key
                    break
        except Exception:
            current = None
        # show_page terminará de sincronizar el título la próxima navegación.
        if save:
            self.store.save(self.settings)
            message = {
                "es": "Idioma cambiado a Español.",
                "en": "Language changed to English.",
                "pt": "Idioma alterado para Português.",
            }[language]
            self._set_banner(message)

    def show_page(self, page):
        result = super().show_page(page)
        lang = str(self.settings.get("language") or "es")
        title = PAGE_TITLES.get(lang, PAGE_TITLES["es"]).get(page)
        if title and hasattr(self, "page_title"):
            try:
                self.page_title.configure(text=title)
            except Exception:
                pass
        for key, button in getattr(self, "_nav_buttons", {}).items():
            title = NAV_TITLES.get(lang, NAV_TITLES["es"]).get(key)
            if title:
                try:
                    button.configure(text=title)
                except Exception:
                    pass
        return result

    def _set_banner(self, text):
        return super()._set_banner(self._v98_translate(text))

    def _set_connection(self, connected, text=None):
        if text is None:
            text = "Conectado" if connected else "Desconectado"
        return super()._set_connection(connected, self._v98_translate(text))

    def _render_status(self, status):
        result = super()._render_status(status)
        for attr in (
            "status_value", "mode_info", "deposit_info", "mop_info",
            "fault_info", "battery_header",
        ):
            widget = getattr(self, attr, None)
            if widget is None:
                continue
            try:
                widget.configure(text=self._v98_translate(widget.cget("text")))
            except Exception:
                pass
        return result

    # ================================================= updater 100% GUI
    def _v98_open_update_window(self, version):
        if self._v98_update_window and self._v98_update_window.winfo_exists():
            self._v98_update_window.destroy()

        palette = self._v98_palette(self.settings.get("theme"))
        lang = str(self.settings.get("language") or "es")
        title = {
            "es": f"Actualizando a v{version}",
            "en": f"Updating to v{version}",
            "pt": f"Atualizando para v{version}",
        }[lang]
        prep = {
            "es": "Preparando descarga…",
            "en": "Preparing download…",
            "pt": "Preparando download…",
        }[lang]

        win = tk.Toplevel(self)
        win.title("Aspiradora · Update")
        win.geometry("520x250")
        win.resizable(False, False)
        win.transient(self)
        win.protocol("WM_DELETE_WINDOW", lambda: None)
        win.configure(bg=palette["app_bg"])

        frame = tk.Frame(win, bg=palette["card"], padx=24, pady=22)
        frame.pack(fill="both", expand=True, padx=12, pady=12)
        tk.Label(frame, text=title, bg=palette["card"], fg=palette["text"], font=("Segoe UI", 14, "bold")).pack(anchor="w")
        self._v98_update_stage = tk.Label(frame, text=prep, bg=palette["card"], fg=palette["text"], font=("Segoe UI", 10))
        self._v98_update_stage.pack(anchor="w", pady=(14, 8))
        self._v98_update_progress = ttk.Progressbar(frame, mode="determinate", maximum=100, value=0)
        self._v98_update_progress.pack(fill="x")
        self._v98_update_detail = tk.Label(
            frame,
            text="0%",
            bg=palette["card"], fg=palette["muted"],
            font=("Segoe UI", 9), anchor="w", justify="left", wraplength=450,
        )
        self._v98_update_detail.pack(fill="x", pady=(9, 0))
        footer = {
            "es": "Todo el proceso continúa en la interfaz de Aspiradora; no se abrirán consolas.",
            "en": "The whole process stays in Aspiradora's UI; no console windows will open.",
            "pt": "Todo o processo continua na interface do Aspiradora; nenhum console será aberto.",
        }[lang]
        tk.Label(
            frame, text=footer, bg=palette["card"], fg=palette["muted"],
            font=("Segoe UI", 9), justify="left", wraplength=450,
        ).pack(anchor="w", pady=(14, 0))
        self._v98_update_window = win
        try:
            win.grab_set()
        except Exception:
            pass

    def _v98_update_stage_text(self, text):
        if self._v98_update_stage and self._v98_update_stage.winfo_exists():
            self._v98_update_stage.configure(text=self._v98_translate(text))
        self._set_banner(text)

    def _v98_update_progress_value(self, percent, done, total):
        if not self._v98_update_progress or not self._v98_update_progress.winfo_exists():
            return
        if percent is None:
            self._v98_update_progress.configure(mode="indeterminate")
            self._v98_update_progress.start(12)
        else:
            try:
                self._v98_update_progress.stop()
            except Exception:
                pass
            self._v98_update_progress.configure(mode="determinate", value=max(0, min(100, int(percent))))
        done_mb = float(done or 0) / (1024 * 1024)
        if total:
            total_mb = float(total) / (1024 * 1024)
            detail = f"{int(percent or 0)}% · {done_mb:.1f} MB / {total_mb:.1f} MB"
        else:
            detail = f"{done_mb:.1f} MB"
        if self._v98_update_detail and self._v98_update_detail.winfo_exists():
            self._v98_update_detail.configure(text=detail)

    def _manual_update_found_safe(self, update):
        version = str(update.get("version") or "")
        lang = str(self.settings.get("language") or "es")
        question = {
            "es": f"Hay una nueva versión: v{version}.\n\n¿Querés descargarla e instalarla ahora dentro de Aspiradora?",
            "en": f"A new version is available: v{version}.\n\nDownload and install it now inside Aspiradora?",
            "pt": f"Há uma nova versão: v{version}.\n\nDeseja baixar e instalar agora dentro do Aspiradora?",
        }[lang]
        if not messagebox.askyesno("Aspiradora · Update", question, parent=self):
            self._set_manual_update_idle()
            return

        self.manual_update_button.configure(text="Actualizando…", state="disabled")
        self._v98_open_update_window(version)

        def worker():
            try:
                download_and_install(
                    update,
                    status_callback=lambda text: self._post_ui("v98_update_stage", text),
                    progress_callback=lambda percent, done, total: self._post_ui(
                        "v98_update_progress", percent, done, total
                    ),
                    theme=str(self.settings.get("theme") or "light"),
                    language=str(self.settings.get("language") or "es"),
                )
                self._post_ui("v98_update_handoff")
            except Exception as exc:
                self._post_ui("v98_update_error", str(exc).strip() or "No se pudo instalar la actualización.")

        threading.Thread(target=worker, name="AspiradoraUpdateDownload", daemon=True).start()

    def _handle_ui_event(self, kind, payload):
        if kind == "v98_update_stage":
            self._v98_update_stage_text(str(payload[0]))
            return
        if kind == "v98_update_progress":
            self._v98_update_progress_value(*payload)
            return
        if kind == "v98_update_handoff":
            lang = str(self.settings.get("language") or "es")
            text = {
                "es": "Descarga verificada. Continuando instalación…",
                "en": "Download verified. Continuing installation…",
                "pt": "Download verificado. Continuando a instalação…",
            }[lang]
            self._v98_update_stage_text(text)
            if self._v98_update_detail and self._v98_update_detail.winfo_exists():
                self._v98_update_detail.configure(text="Aspiradora se cerrará y volverá a abrir automáticamente.")
            self.after(900, self.destroy)
            return
        if kind == "v98_update_error":
            message = str(payload[0])
            if self._v98_update_window:
                try:
                    self._v98_update_window.destroy()
                except Exception:
                    pass
                self._v98_update_window = None
            self._manual_update_error(message)
            return
        return super()._handle_ui_event(kind, payload)

    # =========================================================== diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        lines = [
            "DIAGNÓSTICO V98 ACTIVO · UX global / update / arranque",
            "========================================================",
            f"tema={self.settings.get('theme','light')} · idioma={self.settings.get('language','es')}",
            f"ventana: mostrada una sola vez={self._v98_shown_once} · estado guardado={self.settings.get('window_state','normal')} · geometría={self.settings.get('window_geometry') or '—'}",
            "arranque V98: root oculto durante construcción; V39 restore múltiple neutralizado",
            "update V98: descarga + SHA visibles en modal; helper GUI sin consola + instalador VERYSILENT",
            "idiomas V98: Español / English / Português persistentes",
            "temas V98: Claro / Oscuro persistentes",
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
