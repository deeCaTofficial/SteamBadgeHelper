import os
import json
import re
import time
import logging
import requests
from PyQt6.QtCore import QObject, pyqtSignal

from .steam_network import (
    safe_get, prepare_session, resolve_steamid64, get_all_card_names_from_html,
    STEAM_API_BASE, STEAM_COMMUNITY_BASE, STEAM_STORE_API_BASE
)
from .steam_local import (
    get_userdata_paths, load_local_inventory, load_price_cache,
    load_local_card_sets, load_local_achievements
)

CACHE_FILE = "steam_cache.json"
RESULT_FILE = "results_autosave.json"

def load_cache():
    if not os.path.exists(CACHE_FILE):
        return {"game_names": {}, "card_sets": {}}
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"game_names": {}, "card_sets": {}}

def save_cache(cache):
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except IOError as e:
        logging.error(f"Не удалось сохранить кэш: {e}")


class AnalysisWorker(QObject):
    progress_update = pyqtSignal(int, int, str)
    result_ready = pyqtSignal(dict)
    finished = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self, api_key, steam_id_input, currency_id, language='russian'):
        super().__init__()
        self.api_key = api_key
        self.steam_id_input = steam_id_input
        self.currency_id = currency_id
        self.language = language
        self.steam_id = None
        self._is_cancelled = False
        self.cache = load_cache()
        self.results = []
        self.session = prepare_session()

        self.local_inventory, self.local_inv_appids = {}, set()
        self.local_price_cache = load_price_cache()
        self.local_card_sets = load_local_card_sets()

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            self.progress_update.emit(0, 100, "Проверка API ключа...")
            if not self._validate_api_key():
                self.error_occurred.emit("Невалидный API ключ.")
                return

            self.progress_update.emit(10, 100, "Определение SteamID64...")
            self.steam_id = resolve_steamid64(self.steam_id_input)
            if not self.steam_id:
                self.error_occurred.emit("Не удалось определить SteamID64.")
                return

            # Загружаем локальный инвентарь для определенного steam_id
            self.local_inventory, self.local_inv_appids = load_local_inventory(self.steam_id)

            if self.local_inventory:
                self.progress_update.emit(20, 100, "Загрузка инвентаря (локально)...")
                inventory_cards, inventory_appids = self.local_inventory, self.local_inv_appids
            else:
                self.progress_update.emit(20, 100, "Загрузка инвентаря (сеть)...")
                inventory_cards, inventory_appids = self._get_user_inventory_from_api()

            if inventory_cards is None:
                self.error_occurred.emit("Не удалось получить инвентарь. Проверьте приватность профиля.")
                return

            self.progress_update.emit(30, 100, "Получение информации о значках...")
            badges = self._get_user_badges()
            badges_dict = {b["appid"]: b for b in badges if b.get("appid")}
            appids_to_check = sorted(set(badges_dict.keys()) | inventory_appids)

            if not appids_to_check:
                self.error_occurred.emit("Не найдено игр со значками для анализа.")
                return

            total = len(appids_to_check)
            for i, appid in enumerate(appids_to_check):
                if self._is_cancelled: break

                if badges_dict.get(appid, {}).get("level", 0) >= 5:
                    continue
                
                name = self._get_game_name(appid)
                self.progress_update.emit(i, total, f"Анализ: {name} ({i+1}/{total})")

                appid_str = str(appid)
                if appid_str in self.local_card_sets:
                    all_cards = self.local_card_sets[appid_str]
                else:
                    all_cards = self._get_card_set_info_from_api(appid)
                    if not all_cards: continue

                to_buy = [cn for cn in all_cards if inventory_cards.get(cn, 0) == 0]
                if not to_buy:
                    self._emit_result(appid, name, 0, [], all_cards)
                    continue

                prices = {cn: self.local_price_cache.get(cn) or self._fetch_price(cn) for cn in to_buy}
                
                cost = sum(p for p in prices.values() if p is not None)
                priced_list = [{"name": k, "price": v} for k, v in prices.items()]
                owned_list = [cn for cn in all_cards if cn not in to_buy]
                
                self._emit_result(appid, name, cost, priced_list, owned_list)

        except Exception as e:
            logging.error("Критическая ошибка в потоке анализа", exc_info=e)
            self.error_occurred.emit(f"Произошла непредвиденная ошибка: {e}")
        finally:
            save_cache(self.cache)
            self.finished.emit()
    
    def _emit_result(self, appid, name, cost, to_buy_list, owned_list):
        result = {
            "appid": appid, "game": name, "cost": cost,
            "to_buy_count": len(to_buy_list), "to_buy_list": to_buy_list,
            "owned_list": owned_list
        }
        self.results.append(result)
        self.result_ready.emit(result)
        self._save_results_to_file()
        
    def _save_results_to_file(self):
        with open(RESULT_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)

    def _validate_api_key(self):
        url = f"{STEAM_API_BASE}/ISteamWebAPIUtil/GetSupportedAPIList/v1/?key={self.api_key}"
        response = safe_get(self.session, url)
        return response and response.status_code == 200

    def _get_user_badges(self):
        url = f"{STEAM_API_BASE}/IPlayerService/GetBadges/v1/?key={self.api_key}&steamid={self.steam_id}"
        response = safe_get(self.session, url)
        return response.json().get("response", {}).get("badges", []) if response else []

    def _get_user_inventory_from_api(self):
        cards, appids, last_assetid = {}, set(), None
        while True:
            if self._is_cancelled: return None, None
            url = f"{STEAM_COMMUNITY_BASE}/inventory/{self.steam_id}/753/2?l=english&count=2000"
            if last_assetid: url += f"&start_assetid={last_assetid}"

            response = safe_get(self.session, url)
            if not response: break
            
            try: data = response.json()
            except json.JSONDecodeError: break
            if not data or 'descriptions' not in data: break

            for item in data.get('descriptions', []):
                if any(t.get('internal_name') == 'item_class_2' for t in item.get('tags', [])) and 'Foil' not in item.get('type', ''):
                    cards[item['market_hash_name']] = cards.get(item['market_hash_name'], 0) + 1
                    for tag in item.get('tags', []):
                        if tag.get('category') == 'Game':
                            app_tag = tag.get('internal_name')
                            if app_tag and app_tag.startswith('app_'):
                                appids.add(int(app_tag.split('_')[1]))
                            break
            
            if data.get('more_items') and data.get('last_assetid'):
                last_assetid = data.get('last_assetid')
                time.sleep(0.5)
            else: break
        return cards, appids

    def _get_card_set_info_from_api(self, appid):
        appid_str = str(appid)
        if appid_str in self.cache['card_sets']:
            return self.cache['card_sets'][appid_str]

        url = f"{STEAM_COMMUNITY_BASE}/profiles/{self.steam_id}/gamecards/{appid}/"
        response = safe_get(self.session, url)
        if response and "gamecards" in response.url:
            names = get_all_card_names_from_html(response.text)
            if names:
                self.cache['card_sets'][appid_str] = names
                return names
        return None

    def _get_game_name(self, appid):
        appid_str = str(appid)
        if appid_str in self.cache['game_names']:
            return self.cache['game_names'][appid_str]

        url = f"{STEAM_STORE_API_BASE}/appdetails?appids={appid}&l={self.language}"
        response = safe_get(self.session, url)
        if response:
            data = response.json()
            if data.get(appid_str, {}).get("success"):
                name = data[appid_str]['data']['name']
                self.cache['game_names'][appid_str] = name
                return name
        return f"Игра (AppID: {appid})"

    def _fetch_price(self, name):
        if self._is_cancelled: return None
        
        url = f"{STEAM_COMMUNITY_BASE}/market/priceoverview/?appid=753¤cy={self.currency_id}&market_hash_name={requests.utils.quote(name)}"
        headers = {"Referer": f"{STEAM_COMMUNITY_BASE}/market/search?appid=753"}
        response = safe_get(self.session, url, headers=headers)
        
        if response:
            try:
                data = response.json()
                if data and data.get("success"):
                    price_str = data.get("lowest_price") or data.get("median_price")
                    if price_str:
                        cleaned = re.sub(r'[^\d,.]', '', price_str).replace(',', '.')
                        return float(cleaned)
            except (json.JSONDecodeError, ValueError) as e:
                logging.error(f"Ошибка парсинга цены для '{name}': {e}")
        return None