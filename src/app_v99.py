import math
import re
import tkinter as tk
from tkinter import messagebox, ttk

import app_v98
import app_v9


LIGHT99 = {
    **app_v98.LIGHT,
    "sidebar": "#111827",
    "sidebar_text": "#ffffff",
    "sidebar_muted": "#94a3b8",
    "action_blue": "#4f46e5",
    "action_blue_hover": "#4338ca",
    "action_blue_disabled": "#e0e7ff",
    "danger_bg": "#fef2f2",
    "danger_fg": "#dc2626",
    "danger_hover": "#fee2e2",
    "green": "#16a34a",
}
DARK99 = {
    **app_v98.DARK,
    "sidebar": "#090b10",
    "sidebar_text": "#f8fafc",
    "sidebar_muted": "#9ca3af",
    "action_blue": "#6366f1",
    "action_blue_hover": "#4f46e5",
    "action_blue_disabled": "#e0e7ff",
    "danger_bg": "#3a1719",
    "danger_fg": "#fca5a5",
    "danger_hover": "#4b1d20",
    "green": "#22c55e",
}

V99_TRANSLATIONS = {
    "Tu mapa": {"en": "Your map", "pt": "Seu mapa"},
    "Sin mapa todavía": {"en": "No map yet", "pt": "Ainda sem mapa"},
    "Acciones rápidas": {"en": "Quick actions", "pt": "Ações rápidas"},
    "Lo habitual, sin entrar en menús.": {"en": "Common actions without opening menus.", "pt": "Ações comuns sem abrir menus."},
    "Mapeo": {"en": "Mapping", "pt": "Mapeamento"},
    "Crear o continuar el plano de la vivienda.": {"en": "Create or continue the home floor plan.", "pt": "Crie ou continue a planta da residência."},
    "Abrir herramientas de mapa": {"en": "Open map tools", "pt": "Abrir ferramentas do mapa"},
    "Configurar limpieza": {"en": "Cleaning setup", "pt": "Configurar limpeza"},
    "Elegí el modo y la intensidad antes de iniciar.": {"en": "Choose mode and intensity before starting.", "pt": "Escolha o modo e a intensidade antes de iniciar."},
    "MODO": {"en": "MODE", "pt": "MODO"},
    "SUCCIÓN": {"en": "SUCTION", "pt": "SUCÇÃO"},
    "AGUA": {"en": "WATER", "pt": "ÁGUA"},
    "Silenciosa": {"en": "Quiet", "pt": "Silenciosa"},
    "Sin agua": {"en": "No water", "pt": "Sem água"},
    "Desactivada": {"en": "Disabled", "pt": "Desativada"},
    "Activala o desactivala rápidamente.": {"en": "Enable or disable it quickly.", "pt": "Ative ou desative rapidamente."},
    "Base": {"en": "Dock", "pt": "Base"},
    "Limpiar por lugar": {"en": "Clean by location", "pt": "Limpar por local"},
    "Usá zonas guardadas o elegí un punto desde el mapa.": {"en": "Use saved zones or choose a point on the map.", "pt": "Use zonas salvas ou escolha um ponto no mapa."},
    "Elegir zonas": {"en": "Choose zones", "pt": "Escolher zonas"},
    "Abrir mapa y elegir punto": {"en": "Open map and choose point", "pt": "Abrir mapa e escolher ponto"},
    "Administrar zonas y puntos": {"en": "Manage zones and points", "pt": "Gerenciar zonas e pontos"},
    "Plano de la vivienda": {"en": "Home floor plan", "pt": "Planta da residência"},
    "Mapa local listo": {"en": "Local map ready", "pt": "Mapa local pronto"},
    "Paso 1 · Perímetro": {"en": "Step 1 · Perimeter", "pt": "Etapa 1 · Perímetro"},
    "Paso 2 · Interior": {"en": "Step 2 · Interior", "pt": "Etapa 2 · Interior"},
    "Arrastrar: mover · doble clic: objetivo · Paso 1: paredes · Paso 2: interior": {
        "en": "Drag: pan · double click: target · Step 1: walls · Step 2: interior",
        "pt": "Arrastar: mover · duplo clique: alvo · Etapa 1: paredes · Etapa 2: interior",
    },
    "Objetivo": {"en": "Target", "pt": "Alvo"},
    "Hacé doble clic en el mapa para marcarlo.": {"en": "Double-click the map to place it.", "pt": "Dê duplo clique no mapa para marcar."},
    "Ningún objetivo seleccionado": {"en": "No target selected", "pt": "Nenhum alvo selecionado"},
    "Guardar punto con nombre": {"en": "Save named point", "pt": "Salvar ponto com nome"},
    "Habitaciones": {"en": "Rooms", "pt": "Cômodos"},
    "+ Añadir": {"en": "+ Add", "pt": "+ Adicionar"},
    "Estado del robot": {"en": "Robot status", "pt": "Estado do robô"},
    "Sensores, depósito y consumibles.": {"en": "Sensors, bin and consumables.", "pt": "Sensores, reservatório e consumíveis."},
    "Depósito": {"en": "Dust bin", "pt": "Reservatório"},
    "Consumibles": {"en": "Consumables", "pt": "Consumíveis"},
    "Control manual": {"en": "Manual control", "pt": "Controle manual"},
    "Mantené presionada una dirección para mover el E10.": {"en": "Hold a direction to move the E10.", "pt": "Mantenha uma direção pressionada para mover o E10."},
    "Hacer sonar": {"en": "Play sound", "pt": "Emitir som"},
    "Windows y bandeja": {"en": "Windows and tray", "pt": "Windows e bandeja"},
    "Elegí cómo querés que la aplicación viva en segundo plano.": {"en": "Choose how the app runs in the background.", "pt": "Escolha como o aplicativo funciona em segundo plano."},
    "Cuenta": {"en": "Account", "pt": "Conta"},
    "Aplicación": {"en": "Application", "pt": "Aplicativo"},
    "Buscar actualización": {"en": "Check for update", "pt": "Buscar atualização"},
    "Plano de la vivienda": {"en": "Home floor plan", "pt": "Planta da residência"},
    "Mapear vivienda": {"en": "Map home", "pt": "Mapear residência"},
    "Automático · una pasada normal ECO": {"en": "Automatic · one normal ECO pass", "pt": "Automático · uma passagem normal ECO"},
    "El robot recorrerá la vivienda y la app reconstruirá el perímetro y el interior sin intervención.": {
        "en": "The robot will explore the home and the app will reconstruct the perimeter and interior automatically.",
        "pt": "O robô percorrerá a residência e o aplicativo reconstruirá o perímetro e o interior automaticamente.",
    },
    "Mapa seleccionado": {"en": "Selected map", "pt": "Mapa selecionado"},
    "Espacio disponible": {"en": "Available slot", "pt": "Espaço disponível"},
    "Crear mapa": {"en": "Create map", "pt": "Criar mapa"},
    "Creá otro mapa sin salir de esta pestaña": {"en": "Create another map without leaving this tab", "pt": "Crie outro mapa sem sair desta aba"},
    "Administrar": {"en": "Manage", "pt": "Gerenciar"},
    "Zonas": {"en": "Zones", "pt": "Zonas"},
    "SELECCIONADO": {"en": "SELECTED", "pt": "SELECIONADO"},
    "Seleccionado": {"en": "Selected", "pt": "Selecionado"},
    "LIBRE": {"en": "FREE", "pt": "LIVRE"},
    "Sin mapear": {"en": "Not mapped", "pt": "Não mapeado"},
    "Sin datos": {"en": "No data", "pt": "Sem dados"},
    "Listo para mapear": {"en": "Ready to map", "pt": "Pronto para mapear"},
    "Perímetro": {"en": "Perimeter", "pt": "Perímetro"},
    "Interior": {"en": "Interior", "pt": "Interior"},
    "Mapa estimado": {"en": "Estimated map", "pt": "Mapa estimado"},
    "Mapa Xiaomi": {"en": "Xiaomi map", "pt": "Mapa Xiaomi"},
    "Recorrido": {"en": "Route", "pt": "Percurso"},
    "Buscando geometría Xiaomi…": {"en": "Waiting for Xiaomi geometry…", "pt": "Aguardando geometria Xiaomi…"},
    "Mapas": {"en": "Maps", "pt": "Mapas"},
    "Hasta cuatro viviendas o plantas.": {"en": "Up to four homes or floors.", "pt": "Até quatro residências ou andares."},
    "Importar .xvac": {"en": "Import .xvac", "pt": "Importar .xvac"},
    "Exportar .xvac": {"en": "Export .xvac", "pt": "Exportar .xvac"},
    "ACTIVO": {"en": "ACTIVE", "pt": "ATIVO"},
    "Usar": {"en": "Use", "pt": "Usar"},
    "Renombrar": {"en": "Rename", "pt": "Renomear"},
    "Eliminar": {"en": "Delete", "pt": "Excluir"},
    "+ Nuevo mapa": {"en": "+ New map", "pt": "+ Novo mapa"},
    "Eliminar mapa": {"en": "Delete map", "pt": "Excluir mapa"},
    "No se puede deshacer.": {"en": "This cannot be undone.", "pt": "Isto não pode ser desfeito."},
    "El último mapa se reemplazará por un slot vacío.": {
        "en": "The last map will be replaced with an empty slot.",
        "pt": "O último mapa será substituído por um slot vazio.",
    },
    "Tema oscuro aplicado.": {"en": "Dark theme applied.", "pt": "Tema escuro aplicado."},
    "Tema claro aplicado.": {"en": "Light theme applied.", "pt": "Tema claro aplicado."},
    "Los cambios se guardan automáticamente y se conservan al reiniciar.": {
        "en": "Changes are saved automatically and kept after restart.",
        "pt": "As alterações são salvas automaticamente e mantidas após reiniciar.",
    },
    "Windows y bandeja de sistema": {"en": "Windows and system tray", "pt": "Windows e bandeja do sistema"},
    "Configurar acciones rápidas": {"en": "Configure quick actions", "pt": "Configurar ações rápidas"},
    "Cuenta Xiaomi": {"en": "Xiaomi account", "pt": "Conta Xiaomi"},
    "Desvincular cuenta Xiaomi": {"en": "Unlink Xiaomi account", "pt": "Desvincular conta Xiaomi"},
    "Reiniciar configuración y credenciales": {"en": "Reset settings and credentials", "pt": "Redefinir configurações e credenciais"},
    "Conectado por QR": {"en": "Connected by QR", "pt": "Conectado por QR"},
    "Esta acción no borra mapas guardados ni programaciones.": {
        "en": "This action does not delete saved maps or schedules.",
        "pt": "Esta ação não exclui mapas salvos nem agendamentos.",
    },
    "No hay elementos todavía.": {"en": "No items yet.", "pt": "Ainda não há itens."},
    "Nueva rutina": {"en": "New routine", "pt": "Nova rotina"},
    "Rutinas": {"en": "Routines", "pt": "Rotinas"},
    "Definí cuándo, cómo y dónde limpiar.": {"en": "Choose when, how and where to clean.", "pt": "Defina quando, como e onde limpar."},
    "Guardar rutina": {"en": "Save routine", "pt": "Salvar rotina"},
    "Toda la casa": {"en": "Whole home", "pt": "Casa inteira"},
    "Solo zonas": {"en": "Zones only", "pt": "Somente zonas"},
    "DÍAS": {"en": "DAYS", "pt": "DIAS"},
    "DÓNDE": {"en": "WHERE", "pt": "ONDE"},
}

REVERSE_I18N = {}
for _source, _langs in {**app_v98.STATIC_TRANSLATIONS, **V99_TRANSLATIONS}.items():
    for _translated in _langs.values():
        REVERSE_I18N[str(_translated)] = str(_source)


class App(app_v98.App):
    """V99: mapa estable + dark theme completo + i18n dinámica + borrar mapas."""

    EARLY_MIN_POINTS = 60
    EARLY_MIN_MAJOR_SPAN_M = 1.40
    EARLY_MIN_MINOR_SPAN_M = 0.90
    EARLY_MIN_RATIO = 0.45
    EARLY_MIN_AXIS_CELLS = 7
    V99_INITIAL_BOUNDS = (-2.0, -2.0, 2.0, 2.0)

    def __init__(self):
        self._v99_session_bounds = {}
        self._v99_native_locked = {}
        self._v99_native_lock_hits = 0
        self._v99_bounds_expansions = 0
        self._v99_bounds_shrink_blocks = 0
        self._v99_button_kind = {}
        self._v99_widget_roles = {}
        self._v99_text_state = {}
        self._v99_refresh_job = None
        self._v99_early_surface_blocks = 0
        self._v99_last_visual_mode = "—"
        super().__init__()
        self._v99_schedule_refresh()

    # =========================================================== mapa estable
    @staticmethod
    def _v99_union_bounds(first, second):
        if first is None:
            return second
        if second is None:
            return first
        return (
            min(float(first[0]), float(second[0])),
            min(float(first[1]), float(second[1])),
            max(float(first[2]), float(second[2])),
            max(float(first[3]), float(second[3])),
        )

    @classmethod
    def _v87_floor_cells(cls, snapshot):
        native = super()._v88_native_grid(snapshot)
        if native is not None:
            return set()
        metrics = cls._v97_geometry_metrics(snapshot)
        if not metrics.get("mature"):
            return set()
        return super()._v87_floor_cells(snapshot)

    def _v74_reset_session(self):
        result = super()._v74_reset_session()
        map_id = self._v72_active_map_id() or "__default__"
        self._v99_session_bounds[map_id] = tuple(self.V99_INITIAL_BOUNDS)
        self._v99_native_locked.pop(map_id, None)
        self._v99_last_visual_mode = "esperando geometría"
        return result

    def _v88_native_grid(self, snapshot):
        current = super()._v88_native_grid(snapshot)
        map_id = self._v72_active_map_id() or "__default__"
        if current is not None:
            self._v99_native_locked[map_id] = dict(current)
            self._v99_last_visual_mode = "GRID XIAOMI bloqueado"
            return current
        if bool(getattr(self, "mapping_active", False)):
            locked = self._v99_native_locked.get(map_id)
            if locked is not None:
                self._v99_native_lock_hits += 1
                self._v99_last_visual_mode = "GRID XIAOMI retenido"
                return dict(locked)
        return None

    def _v72_bounds(self, snapshot):
        current = super()._v72_bounds(snapshot)
        if not bool(getattr(self, "mapping_active", False)):
            return current
        map_id = self._v72_active_map_id() or "__default__"
        previous = self._v99_session_bounds.get(map_id, tuple(self.V99_INITIAL_BOUNDS))
        merged = self._v99_union_bounds(previous, current)
        if current is not None:
            try:
                current_area = max(0.0, float(current[2]) - float(current[0])) * max(0.0, float(current[3]) - float(current[1]))
                prev_area = max(0.0, float(previous[2]) - float(previous[0])) * max(0.0, float(previous[3]) - float(previous[1]))
                merged_area = max(0.0, float(merged[2]) - float(merged[0])) * max(0.0, float(merged[3]) - float(merged[1]))
                if current_area + 1e-9 < prev_area:
                    self._v99_bounds_shrink_blocks += 1
                if merged_area > prev_area + 1e-9:
                    self._v99_bounds_expansions += 1
            except Exception:
                pass
        self._v99_session_bounds[map_id] = merged
        return merged

    def _v70_collect_bounds(self, snapshot, plan):
        current = super()._v70_collect_bounds(snapshot, plan)
        if not bool(getattr(self, "mapping_active", False)):
            return current
        map_id = self._v72_active_map_id() or "__default__"
        previous = self._v99_session_bounds.get(map_id, tuple(self.V99_INITIAL_BOUNDS))
        merged = self._v99_union_bounds(previous, current)
        self._v99_session_bounds[map_id] = merged
        return merged

    def _v88_update_legend(self, native):
        result = super()._v88_update_legend(native)
        if not native:
            try:
                snapshot = self.local_map.snapshot() if self.local_map else {}
            except Exception:
                snapshot = {}
            metrics = self._v97_geometry_metrics(snapshot)
            if not metrics.get("mature"):
                label = getattr(self, "_v88_legend_source", None)
                if label is not None:
                    label.configure(text=self._v98_translate("Buscando geometría Xiaomi…"))
                self._v99_last_visual_mode = "sin superficie · esperando geometría"
                self._v99_early_surface_blocks += 1
        return result

    def _render_map_canvas(self, canvas, snapshot):
        result = super()._render_map_canvas(canvas, snapshot)
        if canvas is getattr(self, "map_canvas", None):
            native = self._v88_native_grid(snapshot)
            metrics = self._v97_geometry_metrics(snapshot)
            if native is None and not metrics.get("mature"):
                try:
                    canvas.delete("v99_waiting")
                    canvas.create_text(
                        max(1, canvas.winfo_width()) / 2.0,
                        max(1, canvas.winfo_height()) - 24,
                        text=self._v98_translate("Buscando geometría Xiaomi…"),
                        fill=self._v99_palette(self.settings.get("theme"))["muted"],
                        font=("Segoe UI", 9, "bold"),
                        tags=("v99_waiting",),
                    )
                except Exception:
                    pass
        return result

    # =========================================================== tema V99
    @staticmethod
    def _v99_palette(theme):
        return DARK99 if str(theme).lower() == "dark" else LIGHT99

    @staticmethod
    def _v98_palette(theme):
        return App._v99_palette(theme)

    def _button(self, parent, text, command, accent=False, compact=False, danger=False):
        button = super()._button(parent, text, command, accent=accent, compact=compact, danger=danger)
        self._v99_button_kind[str(button)] = "danger" if danger else ("accent" if accent else "neutral")
        self._v99_text_state[str(button)] = {"source": str(text), "rendered": str(button.cget("text"))}
        return button

    @staticmethod
    def _v99_bg_role(value, widget_class=""):
        value = str(value or "").lower()
        if value in ("#111827", "#090b10"):
            return "sidebar"
        if value in ("#f5f7fa", "#f4f5f7", "#0f1115"):
            return "app_bg"
        if value in ("#ffffff", "#171a21"):
            return "card"
        if value in ("#f8fafc", "#f8f9fb", "#20242d", "#eef2ff", "#eff6ff"):
            return "card_alt"
        if value in ("#f7f9fb", "#10141a", "#dfe9f2"):
            return "map_bg"
        return None

    @staticmethod
    def _v99_fg_role(value):
        value = str(value or "").lower()
        if value in ("#111827", "#17181a", "#f3f5f7", "#0f172a", "#334155"):
            return "text"
        if value in ("#64748b", "#7b8088", "#9aa3ad", "#94a3b8"):
            return "muted"
        return None

    def _v99_theme_button(self, widget, palette, kind):
        if kind == "accent":
            widget.configure(
                bg=palette["action_blue"], fg="#ffffff",
                activebackground=palette["action_blue_hover"], activeforeground="#ffffff",
                disabledforeground=palette["action_blue_disabled"],
                highlightbackground=palette["action_blue"], highlightcolor=palette["action_blue"],
            )
        elif kind == "danger":
            widget.configure(
                bg=palette["danger_bg"], fg=palette["danger_fg"],
                activebackground=palette["danger_hover"], activeforeground=palette["danger_fg"],
                disabledforeground=palette["muted"],
                highlightbackground=palette["border"], highlightcolor=palette["border"],
            )
        else:
            widget.configure(
                bg=palette["card_alt"], fg=palette["text"],
                activebackground=palette["border"], activeforeground=palette["text"],
                disabledforeground=palette["muted"],
                highlightbackground=palette["border"], highlightcolor=palette["border"],
            )

    def _v98_theme_walk(self, widget, palette):
        palette = self._v99_palette(self.settings.get("theme") if hasattr(self, "settings") else "light")
        try:
            wid = str(widget)
            wclass = str(widget.winfo_class())
        except Exception:
            return

        if wclass == "Button":
            kind = self._v99_button_kind.get(wid, "neutral")
            try:
                self._v99_theme_button(widget, palette, kind)
            except Exception:
                pass
        elif wclass in ("Frame", "Toplevel", "Labelframe"):
            try:
                current = widget.cget("background")
                role = self._v99_widget_roles.setdefault(wid, {}).get("background")
                if not role:
                    role = self._v99_bg_role(current, wclass)
                    if role:
                        self._v99_widget_roles[wid]["background"] = role
                if role:
                    widget.configure(background=palette[role])
            except Exception:
                pass
            try:
                widget.configure(highlightbackground=palette["border"])
            except Exception:
                pass
        elif wclass == "Label":
            roles = self._v99_widget_roles.setdefault(wid, {})
            try:
                bg = widget.cget("background")
                role = roles.get("background") or self._v99_bg_role(bg, wclass)
                if role:
                    roles["background"] = role
                    widget.configure(background=palette[role])
            except Exception:
                pass
            try:
                fg = widget.cget("foreground")
                role = roles.get("foreground") or self._v99_fg_role(fg)
                if role:
                    roles["foreground"] = role
                    widget.configure(foreground=palette[role])
                elif str(fg).lower() in ("white", "#ffffff", "#fff"):
                    # Blanco usado como texto (sidebar/acento) nunca se convierte
                    # en el color de una tarjeta oscura.
                    widget.configure(foreground="#ffffff")
            except Exception:
                pass
        elif wclass == "Canvas":
            try:
                current = widget.cget("background")
                role = self._v99_widget_roles.setdefault(wid, {}).get("background")
                if not role:
                    if widget is getattr(self, "map_canvas", None) or widget is getattr(self, "home_map_canvas", None):
                        role = "map_bg"
                    else:
                        role = self._v99_bg_role(current, wclass)
                    if role:
                        self._v99_widget_roles[wid]["background"] = role
                if role:
                    widget.configure(background=palette[role])
            except Exception:
                pass
        elif wclass in ("Entry", "Text"):
            try:
                widget.configure(
                    background=palette["card_alt"],
                    foreground=palette["text"],
                    insertbackground=palette["text"],
                    selectbackground=palette["action_blue"],
                    selectforeground="#ffffff",
                    highlightbackground=palette["border"],
                    highlightcolor=palette["action_blue"],
                )
            except Exception:
                pass

        try:
            children = widget.winfo_children()
        except Exception:
            children = []
        for child in children:
            self._v98_theme_walk(child, palette)

    def _v98_apply_theme(self, theme, save=True):
        result = super()._v98_apply_theme(theme, save=False)
        palette = self._v99_palette(theme)
        try:
            style = ttk.Style(self)
            style.configure(
                "TCombobox",
                fieldbackground=palette["card_alt"],
                background=palette["card_alt"],
                foreground=palette["text"],
                bordercolor=palette["border"],
                arrowcolor=palette["text"],
                selectbackground=palette["card_alt"],
                selectforeground=palette["text"],
            )
            style.map(
                "TCombobox",
                fieldbackground=[("readonly", palette["card_alt"])],
                foreground=[("readonly", palette["text"])],
                selectbackground=[("readonly", palette["card_alt"])],
                selectforeground=[("readonly", palette["text"])],
            )
        except Exception:
            pass
        self._v98_theme_walk(self, palette)
        for child in list(self.winfo_children()):
            if isinstance(child, tk.Toplevel):
                self._v98_theme_walk(child, palette)
        if save:
            self.settings["theme"] = "dark" if str(theme).lower() == "dark" else "light"
            self.store.save(self.settings)
            self._set_banner("Tema oscuro aplicado." if self.settings["theme"] == "dark" else "Tema claro aplicado.")
        return result

    # ========================================================= i18n dinámica
    @staticmethod
    def _v99_canonical_text(text):
        raw = str(text)
        if raw in REVERSE_I18N:
            return REVERSE_I18N[raw]
        replacements = (
            ("Selected map: ", "Mapa seleccionado: "),
            ("Mapa selecionado: ", "Mapa seleccionado: "),
            ("Battery ", "Batería "),
            ("Bateria ", "Batería "),
            ("Connected · ", "Conectado · "),
            ("Maps · ", "Mapas · "),
            ("Map · ", "Mapa · "),
        )
        for prefix, canonical in replacements:
            if raw.startswith(prefix):
                return canonical + raw[len(prefix):]
        return raw

    def _v98_translate(self, text):
        lang = str(getattr(self, "settings", {}).get("language") or "es")
        raw = self._v99_canonical_text(text)
        if lang == "es":
            return raw

        entry = V99_TRANSLATIONS.get(raw)
        if entry:
            return entry.get(lang, raw)

        inherited = super()._v98_translate(raw)
        if inherited != raw:
            return inherited

        if " · " in raw:
            return " · ".join(self._v98_translate(part) for part in raw.split(" · "))

        patterns = [
            (r"^Mapa seleccionado:\s*(.+)$", lambda m: ("Selected map: " if lang == "en" else "Mapa selecionado: ") + m.group(1)),
            (r"^MAPA\s*·\s*(.+)$", lambda m: ("MAP · " if lang == "en" else "MAPA · ") + m.group(1)),
            (r"^Mapa\s+(\d+)$", lambda m: ("Map " if lang == "en" else "Mapa ") + m.group(1)),
            (r"^(\d+) puntos · (\d+) zonas · (\d+) bloqueos · (\d+) rutinas$", lambda m:
                (f"{m.group(1)} points · {m.group(2)} zones · {m.group(3)} blocks · {m.group(4)} routines"
                 if lang == "en"
                 else f"{m.group(1)} pontos · {m.group(2)} zonas · {m.group(3)} bloqueios · {m.group(4)} rotinas")),
            (r"^(\d+) mapas guardados$", lambda m:
                (f"{m.group(1)} saved maps" if lang == "en" else f"{m.group(1)} mapas salvos")),
            (r"^Mapas · (\d+)/4$", lambda m: ("Maps · " if lang == "en" else "Mapas · ") + m.group(1) + "/4"),
            (r"^Mapeo terminado · Mapa seleccionado: (.+)\.$", lambda m:
                (f"Mapping complete · Selected map: {m.group(1)}." if lang == "en"
                 else f"Mapeamento concluído · Mapa selecionado: {m.group(1)}.")),
        ]
        for pattern, render in patterns:
            match = re.match(pattern, raw)
            if match:
                return render(match)
        return raw

    def _v98_language_walk(self, widget):
        try:
            wid = str(widget)
            current = str(widget.cget("text"))
        except Exception:
            current = None
            wid = None

        if current is not None and wid is not None:
            state = self._v99_text_state.get(wid)
            if state is None:
                source = self._v99_canonical_text(current)
                state = {"source": source, "rendered": None}
                self._v99_text_state[wid] = state
            elif state.get("rendered") is not None and current != state.get("rendered"):
                state["source"] = self._v99_canonical_text(current)

            translated = self._v98_translate(state.get("source", current))
            try:
                widget.configure(text=translated)
                state["rendered"] = translated
            except Exception:
                pass

        try:
            children = widget.winfo_children()
        except Exception:
            children = []
        for child in children:
            self._v98_language_walk(child)

    def _v99_refresh_all(self, root=None):
        self._v99_refresh_job = None
        root = root or self
        try:
            self._v98_language_walk(root)
            self._v98_theme_walk(root, self._v99_palette(self.settings.get("theme")))
        except Exception:
            pass

    def _v99_schedule_refresh(self, root=None):
        if root is not None:
            try:
                root.after_idle(lambda r=root: self._v99_refresh_all(r))
            except Exception:
                pass
            return
        if self._v99_refresh_job is not None:
            return
        try:
            self._v99_refresh_job = self.after(30, self._v99_refresh_all)
        except Exception:
            self._v99_refresh_job = None

    def _render_maps(self):
        result = super()._render_maps()
        self._v99_schedule_refresh()
        return result

    def _render_status(self, status):
        result = super()._render_status(status)
        self._v99_schedule_refresh()
        return result

    def show_page(self, page):
        result = super().show_page(page)
        self._v99_schedule_refresh()
        return result

    def _dialog(self, title, geometry):
        win = super()._dialog(self._v98_translate(title), geometry)
        self._v99_schedule_refresh(win)
        return win

    def _section_title(self, parent, title, subtitle=None):
        return super()._section_title(
            parent,
            self._v98_translate(title),
            self._v98_translate(subtitle) if subtitle else None,
        )

    # ====================================================== administrar mapas
    def _v99_confirm_delete_map(self, item, last):
        name = str(item.get("name") or "Mapa")
        lang = str(self.settings.get("language") or "es")
        messages = {
            "es": (
                f"¿Eliminar “{name}”?\n\nSe borrarán su geometría, habitaciones, "
                "zonas, puntos y rutinas.\n"
                + ("El último mapa se reemplazará por un slot vacío." if last else "No se puede deshacer.")
            ),
            "en": (
                f"Delete “{name}”?\n\nIts geometry, rooms, zones, points and routines will be deleted.\n"
                + ("The last map will be replaced with an empty slot." if last else "This cannot be undone.")
            ),
            "pt": (
                f"Excluir “{name}”?\n\nA geometria, cômodos, zonas, pontos e rotinas serão excluídos.\n"
                + ("O último mapa será substituído por um slot vazio." if last else "Isto não pode ser desfeito.")
            ),
        }
        return messagebox.askyesno(self._v98_translate("Eliminar mapa"), messages[lang], parent=self._map_library_window or self)

    def _delete_map(self, item, rebuild):
        if not self.local_map or not self.plan_store:
            return
        maps = list(self.local_map.list_maps())
        map_id = str(item.get("id") or "")
        if not map_id:
            return
        last = len(maps) <= 1
        if not self._v99_confirm_delete_map(item, last):
            return
        try:
            self.plan_store.delete_map_data(map_id)
            if last:
                self.local_map.clear_map(keep_rooms=False)
                self.local_map.rename_map(map_id, "Mapa 1")
                self.plan_store.set_active_map(map_id)
            else:
                self.local_map.delete_map(map_id)
                self.plan_store.set_active_map(self.local_map.active_map_id)
            self._v99_session_bounds.pop(map_id, None)
            self._v99_native_locked.pop(map_id, None)
            getattr(self, "_v72_views", {}).pop(map_id, None)
            rebuild()
            self._v70_update_active_map_labels()
            self._render_maps()
            self._set_banner("Mapa eliminado.")
        except Exception as exc:
            messagebox.showerror(self._v98_translate("Eliminar mapa"), str(exc), parent=self._map_library_window or self)

    def open_map_library(self):
        if not self.local_map or not self.plan_store:
            return
        if self._map_library_window and self._map_library_window.winfo_exists():
            self._map_library_window.destroy()
        win = self._dialog("Mapas", "800x620")
        self._map_library_window = win
        outer, body = self._surface(win, 20, 18)
        outer.pack(fill="both", expand=True, padx=16, pady=16)

        head = tk.Frame(body, bg="#ffffff")
        head.pack(fill="x", pady=(0, 12))
        title = tk.Frame(head, bg="#ffffff")
        title.pack(side="left")
        tk.Label(title, text="Mapas", bg="#ffffff", fg="#111827", font=("Segoe UI Semibold", 16)).pack(anchor="w")
        tk.Label(title, text="Hasta cuatro viviendas o plantas.", bg="#ffffff", fg="#64748b", font=("Segoe UI", 9)).pack(anchor="w")
        controls = tk.Frame(head, bg="#ffffff")
        controls.pack(side="right")
        self._button(controls, "Importar .xvac", lambda: self._import_backup(win), compact=True).pack(side="right", padx=(6, 0))
        self._button(controls, "Exportar .xvac", self._export_backup, compact=True).pack(side="right")

        list_frame = tk.Frame(body, bg="#ffffff")
        list_frame.pack(fill="both", expand=True)
        footer = tk.Frame(body, bg="#ffffff")
        footer.pack(fill="x", pady=(12, 0))

        def rebuild():
            for child in list_frame.winfo_children():
                child.destroy()
            for child in footer.winfo_children():
                child.destroy()

            maps = list(self.local_map.list_maps())
            for item in maps:
                row = tk.Frame(list_frame, bg="#f8fafc", highlightthickness=1, highlightbackground="#e2e8f0")
                row.pack(fill="x", pady=4)
                info = tk.Frame(row, bg="#f8fafc")
                info.pack(side="left", fill="x", expand=True, padx=12, pady=10)

                name = str(item.get("name") or "Mapa")
                if item.get("active"):
                    name += "  ·  ACTIVO"
                tk.Label(info, text=name, bg="#f8fafc", fg="#111827", font=("Segoe UI", 10, "bold")).pack(anchor="w")

                plan = self.plan_store.snapshot(item["id"])
                stats = (
                    f"{item.get('points', 0)} puntos · "
                    f"{len(plan.get('zones', []))} zonas · "
                    f"{len(plan.get('no_go', []))} bloqueos · "
                    f"{len(plan.get('schedules', []))} rutinas"
                )
                tk.Label(info, text=stats, bg="#f8fafc", fg="#64748b", font=("Segoe UI", 8)).pack(anchor="w", pady=(3, 0))

                actions = tk.Frame(row, bg="#f8fafc")
                actions.pack(side="right", padx=8)
                if not item.get("active"):
                    self._button(actions, "Usar", lambda mid=item["id"]: self._switch_map(mid, win), compact=True, accent=True).pack(side="left", padx=2)
                self._button(actions, "Renombrar", lambda m=dict(item): self._rename_map(m, rebuild), compact=True).pack(side="left", padx=2)
                self._button(actions, "Eliminar", lambda m=dict(item): self._delete_map(m, rebuild), compact=True, danger=True).pack(side="left", padx=2)

            new_btn = self._button(footer, "+ Nuevo mapa", lambda: self._create_map(rebuild), accent=True, compact=True)
            new_btn.pack(side="left")
            if len(maps) >= 4:
                new_btn.configure(state="disabled")
            self._v99_schedule_refresh(win)

        rebuild()

    # =========================================================== diagnóstico
    def _diagnostic_text(self):
        inherited = super()._diagnostic_text()
        try:
            snapshot = self.local_map.snapshot() if self.local_map else {}
        except Exception:
            snapshot = {}
        metrics = self._v97_geometry_metrics(snapshot)
        native = self._v88_native_grid(snapshot)
        map_id = self._v72_active_map_id() or "__default__"
        bounds = self._v99_session_bounds.get(map_id)
        lines = [
            "DIAGNÓSTICO V99 ACTIVO · viewport estable + tema/i18n/mapas",
            "================================================================",
            (
                f"visual: modo={self._v99_last_visual_mode} · native={native is not None} · "
                f"2D madura={metrics.get('mature')} · puntos={metrics.get('points')} · "
                f"bloqueos superficie temprana={self._v99_early_surface_blocks}"
            ),
            (
                f"viewport sesión: bounds={bounds} · expansiones={self._v99_bounds_expansions} · "
                f"contracciones bloqueadas={self._v99_bounds_shrink_blocks}"
            ),
            f"grid nativo retenido entre frames: hits={self._v99_native_lock_hits}",
            f"tema V99={self.settings.get('theme')} · idioma V99={self.settings.get('language')}",
            "regla V99: sin grid Xiaomi ni exploración 2D madura no se dibuja ninguna superficie estimada",
            "regla V99: durante mapping_active los bounds sólo pueden crecer; nunca saltan/encogen entre fotogramas",
            "regla V99: botones accent mantienen texto blanco en normal/hover/disabled",
            "regla V99: textos regenerados dinámicamente vuelven a pasar por i18n",
            "regla V99: Administrar mapas permite eliminar cualquier mapa; el último se reemplaza por un slot vacío",
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
