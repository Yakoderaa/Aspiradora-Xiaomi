import json
import threading

import app_v2
from xiaomi_cloud_qr_v2 import XiaomiQrLogin, discover_e10_from_qr

# app_v2 crea el diálogo y la interfaz principal. En esta versión reemplazamos
# únicamente el flujo de vinculación para usar el login QR corregido.
app_v2.XiaomiQrLogin = XiaomiQrLogin
app_v2.discover_e10_from_qr = discover_e10_from_qr


def _qr_authenticated(self):
    try:
        if self.qr_window and self.qr_window.winfo_exists():
            self.qr_window.destroy()
    except Exception:
        pass
    self.status.configure(
        text="Sesión de Xiaomi confirmada. Ahora estoy buscando tu Vacuum E10 y obteniendo sus datos de conexión…"
    )


def _show_qr(self, login, info):
    self.status.configure(text="QR listo. Escanealo con tu celular y completá el inicio de sesión de Xiaomi.")
    self.qr_window = app_v2.QrDialog(self, info)

    def worker():
        try:
            login.wait_for_login()
            self.after(0, lambda: _qr_authenticated(self))

            devices = discover_e10_from_qr(login, self.region.get())
            if not devices:
                raise RuntimeError(
                    "La sesión de Xiaomi se inició correctamente, pero no encontré un Xiaomi Vacuum E10 en la cuenta. "
                    "Dejá Región en 'all' y verificá que el E10 aparezca en Mi Home con esa misma cuenta."
                )

            device = devices[0]

            self.app.settings["xiaomi_login_method"] = "qr"
            self.app.settings["xiaomi_user_id"] = str(login.user_id or "")
            self.app.settings["xiaomi_user_name"] = str(login.account_display or login.user_id or "Cuenta Xiaomi")
            self.app.settings["device_name"] = str(device.get("name") or "Xiaomi Robot Vacuum E10")
            self.app.settings["device_did"] = str(device.get("did") or "")
            self.app.settings["device_region"] = str(device.get("locale") or "")
            self.app.settings["cloud_session"] = json.dumps(
                {
                    "method": "qr",
                    "user_id": login.user_id,
                    "cuser_id": login.cuser_id,
                    "ssecurity": login.ssecurity,
                    "pass_token": login.pass_token,
                    "service_token": login.service_token,
                    "account_display": login.account_display,
                },
                ensure_ascii=False,
            )
            # SettingsStore cifra cloud_session con DPAPI antes de escribirlo.
            self.app.store.save(self.app.settings)

            self.after(0, lambda: self._qr_success(device, len(devices)))
        except Exception as exc:
            msg = str(exc).strip() or "No se pudo completar el inicio de sesión por QR."
            self.after(0, lambda: self._qr_error(msg))

    threading.Thread(target=worker, daemon=True).start()


app_v2.SetupDialog._show_qr = _show_qr


if __name__ == "__main__":
    app_v2.App().mainloop()
