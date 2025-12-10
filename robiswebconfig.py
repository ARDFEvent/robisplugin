import json
import re

import requests
from PySide6.QtCore import QUrl, Slot
from PySide6.QtNetwork import QNetworkCookie
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget, QLabel, QPushButton

import api


class ROBisLoginWindow(QWidget):
    def __init__(self, mw):
        super().__init__()

        self.mw = mw

        self.setWindowTitle("Přihlášení do ROBisu")

        lay = QVBoxLayout()
        self.setLayout(lay)

        self.webview = QWebEngineView()
        self.webview.setUrl("https://rob-is.cz/login")
        cookiestore = self.webview.page().profile().cookieStore()
        cookiestore.cookieAdded.connect(lambda x: self.cookie_process(x))

        lay.addWidget(self.webview)

    def cookie_process(self, cookie: QNetworkCookie):
        if cookie.name().data().decode() == "authToken":
            api.set_config_value("robis-cookie", cookie.value().data().decode())
            self.webview.urlChanged.connect(
                lambda x: self.webview.page().runJavaScript("JSON.stringify(window.localStorage);",
                                                            self.handle_local_storage_result))

    @Slot(str)
    def handle_local_storage_result(self, result):
        api.set_config_value("robis-ls", result)
        self.close()


class ROBisWebConfigWindow(QWidget):
    def __init__(self, mw, robiswin):
        super().__init__()

        self.mw = mw
        self.robiswin = robiswin
        self.races = []
        self.apikeys = {}
        self.last_id = -1
        self.current_race = -1

        self.setWindowTitle("Stažení z ROBisu")

        lay = QVBoxLayout()
        self.setLayout(lay)

        self.statuslbl = QLabel()
        lay.addWidget(self.statuslbl)

        self.downloadbtn = QPushButton("Stáhnout tuto etapu (závod)")
        self.downloadbtn.setEnabled(False)
        self.downloadbtn.clicked.connect(self.ok)
        lay.addWidget(self.downloadbtn)

        self.webview = QWebEngineView()
        lay.addWidget(self.webview)
        lay.setStretch(1, 2)

    def show(self):
        cookiestore = self.webview.page().profile().cookieStore()

        if (cookie := api.get_config_value("robis-cookie")) and api.get_config_value("robis-ls"):
            qcookie = QNetworkCookie("authToken".encode(), cookie.encode())
            qcookie.setHttpOnly(True)
            qcookie.setSecure(True)
            qcookie.setSameSitePolicy(QNetworkCookie.SameSite.Strict)
            cookiestore.setCookie(qcookie, QUrl("https://rob-is.cz"))
            cookiestore.loadAllCookies()
            self.webview.loadFinished.connect(self.set_local_storage)
            self.webview.setUrl("https://rob-is.cz/")
            self.url_change()
            super().show()

    def set_local_storage(self):
        for key, value in json.loads(api.get_config_value("robis-ls")).items():
            self.webview.page().runJavaScript(f"localStorage.setItem('{key}', '{value}');")
        self.webview.page().runJavaScript("location.reload();")
        self.webview.loadFinished.disconnect(self.set_local_storage)
        self.webview.urlChanged.connect(self.url_change)

    def ok(self):
        api.set_basic_info(self.mw.db, {"robis_api": self.apikeys[self.current_race]})
        self.robiswin._show()
        self.robiswin._download()
        self.close()

    def url_change(self):
        self.downloadbtn.setEnabled(False)
        self.current_race = -1
        if match := re.fullmatch(r"https://rob-is.cz/soutez/(\d*)/?\?race=(\d*).*", self.webview.url().toString()):
            if match.group(1) != self.last_id:
                resp = requests.get(f"https://rob-is.cz/api/event/edit/?id={match.group(1)}",
                                    cookies={"authToken": api.get_config_value("robis-cookie"),
                                             "cookieConsent": "true"},
                                    headers={"Accept": "application/json",
                                             "Referer": f"https://rob-is.cz/soutez/{match.group(1)}/nastaveni",
                                             "Host": "rob-is.cz"})
                if resp.status_code != 200:
                    self.statuslbl.setText("Tuto soutěž nelze importovat (nejste správce).")
                    self.statuslbl.setStyleSheet("color: white; background-color: red; padding: .5em;")
                    return
                data = resp.json()
                self.races = []
                self.apikeys = {}
                for race in data["races"][1:]:
                    self.races.append(race["id"])
                    self.apikeys[str(race["id"])] = race["race_api_key"]
                self.last_id = match.group(1)
            self.webview.page().runJavaScript(
                'for (const elem of document.getElementsByTagName("a")) { if (elem.getAttribute("href").endsWith("nastaveni")) {elem.remove();} }')
            if int(match.group(2)) in self.races:
                if self.apikeys[match.group(2)] is None:
                    self.statuslbl.setText(f"Tato etapa je zamklá (nemá dostupný API klíč).")
                    self.statuslbl.setStyleSheet("color: black; background-color: red; padding: .5em;")
                    return
                self.statuslbl.setText(f"Tuto etapu (závod) je možno importovat.")
                self.statuslbl.setStyleSheet("color: black; background-color: green; padding: .5em;")
                self.current_race = match.group(2)
                self.downloadbtn.setEnabled(True)
            else:
                self.statuslbl.setText("Tuto soutěž lze importovat, vyberte etapu.")
                self.statuslbl.setStyleSheet("color: black; background-color: yellow; padding: .5em;")
        elif match := re.fullmatch(r"https://rob-is.cz/.*", self.webview.url().toString()):
            self.statuslbl.setText("Vyberte soutěž.")
            self.statuslbl.setStyleSheet("color: white; background-color: blue; padding: .5em;")
        else:
            self.webview.setUrl("https://rob-is.cz/")
