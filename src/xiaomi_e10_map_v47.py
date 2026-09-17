from xiaomi_e10_map_v45 import XiaomiE10MapV45


class XiaomiE10MapV47(XiaomiE10MapV45):
    """V47: habilita temporalmente el permiso de subida de mapa del B112.

    V45 deshabilitó correctamente las acciones de upload no documentadas, pero
    también dejó de tocar 10/23. En el B112, map-privacy usa 0=Enable y
    1=DisEnable para permitir que el robot publique datos de mapa en Xiaomi
    Cloud. V47 recupera únicamente ese cambio temporal de permiso.

    ``request_fresh_upload`` sigue siendo exactamente el de V45: sólo usa las
    acciones documentadas 10/14 o 10/2 cuando existe un map_id > 0. Esta clase
    no reactiva 10/18, 10/15 ni 10/6.
    """

    def enable_map_upload_temporarily(self):
        current = self.map_privacy_state()
        if self.privacy_original is None:
            self.privacy_original = current

        if current == 0:
            # Ya estaba habilitado por el usuario; no hay nada que restaurar.
            return True

        if current != 1:
            return False

        try:
            self.vacuum.device.set_property_by(10, 23, 0)
        except Exception:
            return False

        # Desde este punto debemos restaurar el valor original incluso si una
        # lectura de verificación posterior falla.
        self.privacy_temporarily_enabled = True
        try:
            verified = self.map_privacy_state()
        except Exception:
            verified = None
        return verified in (0, None)
