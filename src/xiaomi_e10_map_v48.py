from xiaomi_e10_map_v47 import XiaomiE10MapV47


class XiaomiE10MapV48(XiaomiE10MapV47):
    """V48: hace robusta la restauración de map-privacy.

    V45 conserva una ruta segura de upload por map_id, pero su
    ``request_fresh_upload`` pone ``privacy_temporarily_enabled=False`` porque
    en V45 la privacidad no se tocaba. V47 volvió a habilitar 10/23
    temporalmente, así que ese reset podía borrar la responsabilidad de
    restaurar 1 al terminar el mapeo.

    V48 mantiene exactamente las acciones seguras de V45 y sólo preserva el
    estado de restauración cuando el valor original era 1 y el dispositivo
    sigue actualmente en 0.
    """

    def request_fresh_upload(self):
        original = self.privacy_original
        was_temporary = bool(self.privacy_temporarily_enabled)
        result = super().request_fresh_upload()

        if was_temporary and original == 1:
            try:
                current = self.map_privacy_state()
            except Exception:
                current = None
            if current in (0, None):
                self.privacy_original = 1
                self.privacy_temporarily_enabled = True
                if isinstance(result, dict):
                    result["privacy_original"] = 1
                    result["privacy_now"] = current
                    result["privacy_temp"] = True
                    self.last_upload_diagnostics = dict(result)
                    self.last_v45_upload_diagnostics = dict(result)
        return result

    def restore_map_privacy(self):
        """Restaura también si una capa heredada perdió la bandera temporal."""
        try:
            current = self.map_privacy_state()
        except Exception:
            current = None

        if self.privacy_original == 1 and current == 0:
            try:
                self.vacuum.device.set_property_by(10, 23, 1)
                self.privacy_temporarily_enabled = False
                return True
            except Exception:
                return False

        return super().restore_map_privacy()
