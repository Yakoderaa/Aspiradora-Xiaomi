import sys
import traceback

import app_v141
import app_v9
import device_metadata_patch
import windows_audio_identity


def main():
    if "--packaging-smoke-test" in sys.argv:
        return 0

    device_metadata_patch.install()
    windows_audio_identity.install()
    app_v9._save_crash_log("")
    try:
        app_v141.App().mainloop()
    except Exception:
        app_v9._save_crash_log(traceback.format_exc())
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
