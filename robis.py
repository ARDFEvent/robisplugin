import time

import jwt
from PySide6.QtWidgets import QMessageBox

import api
import plugin
import robiswin, robiswebconfig

import qtawesome as qta

class ROBisPlugin(plugin.Plugin):
    name = "ROBis"
    author = "JJ"
    version = "1.1.1"

    def __init__(self, mw):
        super().__init__(mw)
        self.robis_win = robiswin.ROBisWindow(self.mw, self)
        self.robis_login_win = robiswebconfig.ROBisLoginWindow(self.mw)
        self.register_mw_tab(self.robis_win, qta.icon("mdi6.web"))
        self.register_ww_menu("Přihlášení do ROBisu")

    def on_startup(self):
        if cookie := api.get_config_value("robis-cookie"):
            if time.time() > jwt.decode(cookie, options={"verify_signature": False})["exp"]:
                if QMessageBox.information(self.mw, "Přihlášení do ROBisu",
                                           "Přihlášení do ROBisu vypršelo. Chcete se přihlástit znovu?") == QMessageBox.StandardButton.Ok:
                    self.robis_login_win.show()

    def on_readout(self, sinum: int):
        self.robis_win._send_online_readout(self.mw.db, sinum)

    def on_menu(self):
        self.robis_login_win.show()


fileplugin = ROBisPlugin
