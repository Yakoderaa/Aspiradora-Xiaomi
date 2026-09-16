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
            # Esta llamada espera hasta que Xiaomi confirme de verdad el QR.
            login.wait_for_login()
            self.after(0, lambda: _qr_authenticated(self))

            devices = discover_e10_from_qr(login, self.region.get())
            if not devices:
                raise RuntimeError(
                    "La sesión de Xiaomi se inició correctamente, pero no encontré un Xiaomi Vacuum E10 en la cuenta. "
                    "Dejá Región en 'all' y verificá que el E10 aparezca en Mi Home con esa misma cuenta."
                )

            device = devices[0]
            self.after(0, lambda: self._qr_success(device, len(devices)))
        except Exception as exc:
            msg = str(exc).strip() or "No se pudo completar el inicio de sesión por QR."
            self.after(0, lambda: self._qr_error(msg))

    threading.Thread(target=worker, daemon=True).start()


app_v2.SetupDialog._show_qr = _show_qr


if __name__ == "__main__":
    app_v2.App().mainloop()
