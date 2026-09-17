"""Persistencia de metadatos descubiertos durante el login Xiaomi.

No modifica el flujo de autenticación: sólo guarda nombre, did y región cuando el
SetupDialog ya obtuvo un dispositivo válido. Esto permite que la pantalla de
Dispositivos muestre el nombre cloud real en logins futuros.
"""

import app_v2

_PATCHED = False


def install():
    global _PATCHED
    if _PATCHED:
        return
    cls = app_v2.SetupDialog

    original_qr = cls._qr_success
    original_password = cls._password_success

    def persist(dialog, device, method):
        try:
            app = dialog.app
            name = str(device.get("name") or "").strip()
            did = str(device.get("did") or "").strip()
            region = str(device.get("locale") or "").strip()
            if name:
                app.settings["device_name"] = name
            if did:
                app.settings["device_did"] = did
            if region:
                app.settings["device_region"] = region
            app.settings["xiaomi_login_method"] = method
            app.store.save(app.settings)
        except Exception:
            # Guardar metadatos nunca debe romper un login que ya fue exitoso.
            pass

    def qr_success(self, device, count):
        persist(self, device, "qr")
        return original_qr(self, device, count)

    def password_success(self, device, count):
        persist(self, device, "password")
        return original_password(self, device, count)

    cls._qr_success = qr_success
    cls._password_success = password_success
    _PATCHED = True
