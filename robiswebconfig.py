import json
import os
from datetime import datetime

import api
import requests
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import QFormLayout, QVBoxLayout, QWidget, QLabel, QPushButton, QLineEdit, QTreeWidget, \
    QTreeWidgetItem, QProgressBar, QTreeWidgetItemIterator

ROBIS_URL = os.getenv("ARDF_ROBIS_URL", "https://rob-is.cz")


class ROBisLoginWindow(QWidget):
    def __init__(self, mw):
        super().__init__()

        self.mw = mw

        self.setWindowTitle("Přihlášení do ROBisu")

        lay = QFormLayout()
        self.setLayout(lay)

        lay.addWidget(QLabel(
            "Přihlašte se do ROBisu pomocí svého účtu.\n\nNení uložen přímo email a heslo ale pouze token,\nkterý nám poskytne ROBis, vaše údaje jsou v bezpečí."))

        self.email_input = QLineEdit()
        lay.addRow("Email:", self.email_input)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        lay.addRow("Heslo:", self.password_input)

        self.loginbtn = QPushButton("Přihlásit se")
        self.loginbtn.clicked.connect(self.login)
        lay.addRow(self.loginbtn)

        self.error_lbl = QLabel()
        lay.addRow(self.error_lbl)

    def login(self):
        login = requests.get(f"{ROBIS_URL}/api/login/",
                             params={"email": self.email_input.text(), "password": self.password_input.text()})
        if login.status_code != 200:
            self.error_lbl.setText("Chyba přihlášení, zkontrolujte email a heslo.")
            return
        token = login.cookies.get("authToken")
        if not token:
            self.error_lbl.setText("Chyba přihlášení, zkontrolujte email a heslo.")
            return
        api.set_config_value("robis-cookie", token)
        ls = login.json()
        api.set_config_value("robis-ls", json.dumps(
            {"userID": ls["userId"], "firstName": ls["first_name"], "last_name": ls["last_name"],
             "rolesByIndex": json.dumps(ls["roles"])}))


class EventLoadThread(QThread):
    data = Signal(list)

    def run(self):
        result = []

        authToken = api.get_config_value("robis-cookie")

        events = requests.get(f"{ROBIS_URL}/api/event/?year={datetime.now().year}&period=all", cookies={"authToken": authToken})

        mx = len(events.json())

        for i, event in enumerate(events.json()):
            if event["event_closed"]:
                continue

            result.append({"name": event["event_name"],
                            "date": datetime.strptime(event["event_date_start"], "%Y-%m-%d"),
                            "id": event["id"]})
        result.sort(key=lambda x: x["date"])
        self.data.emit(result)


class RaceLoadThread(QThread):
    data = Signal(list, QTreeWidgetItem)

    def __init__(self, item: QTreeWidgetItem):
        super().__init__()
        self.eid = item.data(0, Qt.UserRole)
        self.item = item

    def run(self):
        event_admin = requests.get(f"{ROBIS_URL}/api/event/edit/?id={self.eid}",
                                   cookies={"authToken": api.get_config_value("robis-cookie")})
        if event_admin.status_code != 200:
            self.data.emit([], self.item)
            return

        ev_adm = event_admin.json()

        self.data.emit(list(map(lambda x: {"name": x["race_name"],
                                           "date": datetime.strptime(x["race_date"], "%Y-%m-%d"),
                                           "apikey": x["race_api_key"]}, ev_adm["races"][1:])), self.item)


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

        lay.addWidget(QLabel("Načítají se pouze letošní neuzavřené závody.\nEtapy načtete kliknutím na závod. Etapu otevřete dvojklikem."))

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        lay.addWidget(self.progress_bar)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Datum", "Závod"])
        lay.addWidget(self.tree)

    def show(self):
        super().show()

        self.tree.clear()

        self.thr = EventLoadThread()
        self.thr.data.connect(self.data_load)
        self.thr.start()
        self.progress_bar.setRange(0, 0)
        self.tree.itemClicked.connect(self.load_races)
        self.tree.itemDoubleClicked.connect(self.open_race)
        self.tree.itemCollapsed.connect(lambda x: x.takeChildren())

    def data_load(self, data):
        for race in data:
            item = QTreeWidgetItem([race["date"].strftime("%d. %m. %Y"), race["name"]])
            item.setData(0, Qt.UserRole, race["id"])
            self.tree.addTopLevelItem(item)

        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1)

        self.adjust_size(height=True)

    def load_races(self, item: QTreeWidgetItem):
        eid = item.data(0, Qt.UserRole)
        if not eid:
            return

        self.rthr = RaceLoadThread(item)
        self.rthr.data.connect(self.race_load)
        self.rthr.start()
        self.progress_bar.setRange(0, 0)

    def race_load(self, data, item: QTreeWidgetItem):
        if len(data) == 0:
            item.addChild(QTreeWidgetItem(["", "Nejste správce!"]))
        else:
            for race in data:
                child = QTreeWidgetItem([race["date"].strftime("%d. %m. %Y"), race["name"]])
                child.setData(0, Qt.UserRole + 1, race["apikey"])
                item.addChild(child)

        for i in range(self.tree.topLevelItemCount()):
            cit = self.tree.topLevelItem(i)
            cit.setExpanded(False)

        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1)

        item.setExpanded(True)

    def open_race(self, item: QTreeWidgetItem):
        apikey = item.data(0, Qt.UserRole + 1)
        if not apikey:
            return

        api.set_basic_info(self.mw.db, {"robis_api": apikey})

        self.robiswin._show()
        self.robiswin._download()
        self.close()

    def adjust_size(self, height=False):
        for i in range(self.tree.columnCount()):
            self.tree.resizeColumnToContents(i)

        header = self.tree.header()
        total_column_width = 0
        for i in range(header.count()):
            total_column_width += header.sectionSize(i)

        total_height = 0

        iterator = QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            item = iterator.value()
            total_height += self.tree.visualItemRect(item).height()
            iterator += 1

        scrollbar_width = self.tree.verticalScrollBar().sizeHint().width()

        frame_size = self.tree.frameWidth() * 2
        final_width = total_column_width + scrollbar_width + frame_size + 10
        final_height = total_height + frame_size + 10 + 150

        self.resize(final_width, final_height if height else self.height())

    def closeEvent(self, event):
        if self.thr.isRunning():
            self.thr.terminate()
            self.thr.wait()
        if self.rthr.isRunning():
            self.rthr.terminate()
            self.rthr.wait()
