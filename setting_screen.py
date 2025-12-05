from kivy.uix.screenmanager import Screen
from kivy.core.audio import SoundLoader
from kivy.properties import BooleanProperty, StringProperty
from kivy.uix.popup import Popup
from kivy.uix.label import Label
from kivy.uix.boxlayout import BoxLayout
from kivy.clock import Clock
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
import threading
import requests
import os
import webbrowser

from utils.settings_utils import save_user_settings
try:
    from utils import storage
except Exception:
    storage = None


class SettingsScreen(Screen):
    music_playing = BooleanProperty(False)
    profile_image = StringProperty("assets/default.png")

    WALLET_WEB_URL = os.getenv("WALLET_WEB_URL", "").rstrip("/")

    def on_pre_enter(self):
        if not hasattr(self, "sound"):
            self.sound = SoundLoader.load("assets/background.mp3")
            if self.sound:
                self.sound.loop = True

        self.refresh_wallet_balance()

        if storage:
            user = storage.get_user() or {}
            if user.get("profile_image"):
                self.profile_image = user["profile_image"]

        token = storage.get_token() if storage else None
        backend = storage.get_backend_url() if storage else None

        def worker():
            if not (token and backend):
                return
            try:
                resp = requests.get(
                    f"{backend}/users/me",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10,
                    verify=False,
                )
                if resp.status_code == 200:
                    user = resp.json()
                    storage.set_user(user)

                    def update_inputs(dt):
                        if self.ids.get("name_input"):
                            self.ids.name_input.text = user.get("name") or ""
                        if self.ids.get("desc_input"):
                            self.ids.desc_input.text = user.get("description") or ""
                        if self.ids.get("phone_input"):
                            self.ids.phone_input.text = user.get("phone") or ""
                        if self.ids.get("upi_input"):
                            self.ids.upi_input.text = user.get("upi_id") or ""
                        if self.ids.get("paypal_input"):
                            self.ids.paypal_input.text = user.get("paypal_id") or ""
                    Clock.schedule_once(update_inputs, 0)
            except Exception as e:
                print(f"[WARN] Failed to preload settings: {e}")

        threading.Thread(target=worker, daemon=True).start()

    # ------------------ Audio ------------------
    def toggle_audio(self):
        if not hasattr(self, "sound") or not self.sound:
            return
        if self.music_playing:
            self.sound.stop()
            self.music_playing = False
        else:
            self.sound.play()
            self.music_playing = True

    # ------------------ Profile ------------------
    def change_profile_picture(self):
        layout = BoxLayout(orientation="vertical", spacing=5, padding=5)
        filechooser = FileChooserIconView(path=".", filters=["*.png", "*.jpg", "*.jpeg"])
        layout.add_widget(filechooser)

        btn_box = BoxLayout(size_hint_y=None, height=40, spacing=5)
        btn_select = Button(text="Select")
        btn_cancel = Button(text="Cancel")
        btn_box.add_widget(btn_select)
        btn_box.add_widget(btn_cancel)
        layout.add_widget(btn_box)

        popup = Popup(title="Select Profile Picture", content=layout, size_hint=(0.9, 0.9))

        def select_and_upload(*_):
            if filechooser.selection:
                file_path = filechooser.selection[0]
                self.profile_image = file_path

                def worker():
                    try:
                        token = storage.get_token() if storage else None
                        backend = storage.get_backend_url() if storage else None
                        if not (token and backend):
                            raise Exception("Missing token or backend")

                        with open(file_path, "rb") as f:
                            resp = requests.post(
                                f"{backend}/users/upload-profile-image",
                                headers={"Authorization": f"Bearer {token}"},
                                files={"file": (os.path.basename(file_path), f, "image/jpeg")},
                                timeout=15,
                                verify=False,
                            )

                        if resp.status_code == 200:
                            data = resp.json()
                            new_url = data.get("url") or file_path
                            self.profile_image = new_url
                            if storage:
                                user = storage.get_user() or {}
                                user["profile_image"] = new_url
                                storage.set_user(user)
                            Clock.schedule_once(lambda dt: self.show_popup("Success", "Profile picture updated!"), 0)
                        else:
                            err = resp.text
                            Clock.schedule_once(lambda dt, msg=err: self.show_popup("Error", f"Upload failed: {msg}"), 0)
                    except Exception as e:
                        err = str(e)
                        Clock.schedule_once(lambda dt, msg=err: self.show_popup("Error", f"Upload failed: {msg}"), 0)

                threading.Thread(target=worker, daemon=True).start()
            popup.dismiss()

        btn_select.bind(on_release=select_and_upload)
        btn_cancel.bind(on_release=popup.dismiss)
        popup.open()

    # ------------------ Settings ------------------
    def save_settings(self):
        name = self.ids.name_input.text.strip()
        desc = self.ids.desc_input.text.strip()
        paypal_widget = self.ids.get("paypal_input")
        paypal = paypal_widget.text.strip() if paypal_widget else ""

        payload = {}
        if name:
            payload["name"] = name
        if desc:
            payload["description"] = desc
        if paypal:
            payload["paypal_id"] = paypal

        if not payload:
            self.show_popup("Nothing to update", "Please edit a field first.")
            return

        token = storage.get_token() if storage else None
        backend = storage.get_backend_url() if storage else None
        if not (token and backend):
            self.show_popup("Error", "Missing token or backend.")
            return

        def worker():
            try:
                resp = requests.patch(
                    f"{backend}/users/me",
                    headers={"Authorization": f"Bearer {token}"},
                    json=payload,
                    timeout=10,
                    verify=False,
                )
                if resp.status_code == 200:
                    user = resp.json()
                    storage.set_user(user)
                    Clock.schedule_once(lambda dt: self.show_popup("Success", "Settings updated!"), 0)
                    Clock.schedule_once(lambda dt: self.refresh_wallet_balance(), 0)
                else:
                    Clock.schedule_once(lambda dt: self.show_popup("Error", f"Update failed: {resp.text}"), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self.show_popup("Error", f"Request failed: {e}"), 0)

        threading.Thread(target=worker, daemon=True).start()

    # ------------------ Wallet portal helpers ------------------
    def _resolve_wallet_base_url(self) -> str:
        if storage:
            custom = getattr(storage, "get_wallet_url", lambda: None)()
            if custom:
                return custom.rstrip("/")
        if self.WALLET_WEB_URL:
            return self.WALLET_WEB_URL
        backend = storage.get_backend_url() if storage else ""
        if backend:
            return backend.rstrip("/").replace("/api", "")
        return ""

    def open_wallet_portal(self, reason: str = "wallet"):
        token = storage.get_token() if storage else None
        backend = storage.get_backend_url() if storage else None
        wallet_url = self._resolve_wallet_base_url()

        if not (token, backend, wallet_url):
            self.show_popup("Error", "Wallet portal not configured. Update WALLET_WEB_URL.")
            return

        def worker():
            try:
                resp = requests.post(
                    f"{backend}/auth/wallet-link",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10,
                    verify=False,
                )
                if resp.status_code != 200:
                    raise Exception(resp.text or "Failed to create wallet link")

                link_token = resp.json().get("token")
                if not link_token:
                    raise Exception("Wallet link token missing")

                final_url = f"{wallet_url}/link?token={link_token}&source={reason}"
                Clock.schedule_once(lambda dt: webbrowser.open(final_url), 0)
                Clock.schedule_once(
                    lambda dt: self.show_popup(
                        "Wallet Portal",
                        "Wallet site opened in your browser. Complete recharge/withdraw there.",
                    ),
                    0,
                )
            except Exception as exc:
                Clock.schedule_once(
                    lambda dt, msg=str(exc): self.show_popup("Error", f"Unable to open wallet portal: {msg}"),
                    0,
                )

        threading.Thread(target=worker, daemon=True).start()

    def recharge(self):
        self.open_wallet_portal("recharge")

    def withdraw_coins(self):
        self.open_wallet_portal("withdraw")

    # ------------------ Wallet History ------------------
    def show_wallet_history(self):
        token = storage.get_token() if storage else None
        backend = storage.get_backend_url() if storage else None
        if not (token and backend):
            self.show_popup("Error", "Not logged in or backend missing")
            return

        def worker():
            try:
                resp = requests.get(
                    f"{backend}/wallet/history",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"limit": 20},
                    timeout=10,
                    verify=False,
                )
                if resp.status_code != 200:
                    raise Exception(resp.text)
                data = resp.json()
                txs = data if isinstance(data, list) else data.get("transactions", [])
                if not txs:
                    Clock.schedule_once(lambda dt: self.show_popup("Wallet History", "No transactions found."), 0)
                    return

                layout = BoxLayout(orientation="vertical", spacing=5, padding=10, size_hint_y=None)
                layout.bind(minimum_height=layout.setter("height"))

                for tx in txs:
                    timestamp = tx.get("timestamp") or ""
                    amount = tx.get("amount") or tx.get("coins") or 0
                    lbl = Label(
                        text=f"[{timestamp[:16]}] {tx['type']} {amount} coins ({tx['status']})",
                        halign="left",
                        valign="middle",
                        size_hint_y=None,
                        height=30,
                    )
                    lbl.bind(size=lambda inst, val: setattr(inst, "text_size", inst.size))
                    layout.add_widget(lbl)

                scroll = ScrollView(size_hint=(1, 1))
                scroll.add_widget(layout)

                popup = Popup(
                    title="Wallet History (Last 20)",
                    content=scroll,
                    size_hint=(0.9, 0.7),
                )
                Clock.schedule_once(lambda dt: popup.open(), 0)

            except Exception as e:
                err = str(e)
                Clock.schedule_once(lambda dt, msg=err: self.show_popup("Error", f"Failed to fetch history: {msg}"), 0)

        threading.Thread(target=worker, daemon=True).start()

    # ------------------ Wallet Refresh ------------------
    def refresh_wallet_balance(self):
        token = storage.get_token() if storage else None
        backend = storage.get_backend_url() if storage else None

        def worker():
            balance_text = "Wallet: 0 coins"
            if token and backend:
                try:
                    resp = requests.get(
                        f"{backend}/users/me",
                        headers={"Authorization": f"Bearer {token}"},
                        timeout=10,
                        verify=False,
                    )
                    if resp.status_code == 200:
                        user = resp.json()
                        if storage:
                            storage.set_user(user)
                        balance = (
                            user.get("wallet_balance")
                            if user.get("wallet_balance") is not None
                            else user.get("coin_balance", 0)
                        )
                        balance_text = f"Wallet: {balance} coins"
                except Exception as e:
                    print(f"[WARN] Wallet refresh failed: {e}")

            def update_label(dt):
                wallet_lbl = self.ids.get("wallet_label")
                if wallet_lbl:
                    wallet_lbl.text = balance_text

            Clock.schedule_once(update_label, 0)

        threading.Thread(target=worker, daemon=True).start()

    # ------------------ Popup helper ------------------
    def show_popup(self, title: str, message: str):
        popup = Popup(
            title=title,
            content=Label(text=message),
            size_hint=(0.7, 0.3),
        )
        popup.open()
