import os
import re
import vdf
import logging
import platform

def find_steam_path():
    system = platform.system()
    try:
        if system == "Windows":
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
            return winreg.QueryValueEx(key, "SteamPath")[0]
        elif system == "Darwin": # macOS
            path = os.path.expanduser("~/Library/Application Support/Steam")
            if os.path.isdir(path):
                return path
        else: # Linux
            path = os.path.expanduser("~/.steam/steam")
            if os.path.isdir(path):
                return path
    except Exception as e:
        logging.warning(f"Не удалось найти путь к Steam для {system}: {e}")
    return None

def get_userdata_paths():
    steam_path = find_steam_path()
    if not steam_path:
        return []
    userdata_path = os.path.join(steam_path, "userdata")
    if not os.path.isdir(userdata_path):
        return []
    return [os.path.join(userdata_path, d) for d in os.listdir(userdata_path) if d.isdigit()]

def load_local_achievements(steamid, appid):
    steam_path = find_steam_path()
    if not steam_path: return set()
    stats_file = os.path.join(steam_path, "userdata", steamid, "stats", f"{appid}.bin")
    if not os.path.isfile(stats_file):
        return set()
    try:
        with open(stats_file, "rb") as f:
            data = vdf.binary_load(f.read())
        stats = data.get("stats", {}) or data.get("achievements", {})
        return {name for name, info in stats.items() if info.get("achieved") == 1}
    except Exception as e:
        logging.warning(f"Ошибка чтения локальных достижений {appid}: {e}")
        return set()

def load_local_inventory(steamid):
    steam_path = find_steam_path()
    if not steam_path: return {}, set()
    inv_path = os.path.join(steam_path, "userdata", steamid, "760", "2", "inventory.vdf")
    if not os.path.isfile(inv_path):
        return {}, set()
    try:
        with open(inv_path, "rb") as f:
            data = vdf.binary_load(f.read())
        
        inv_cards = {}
        appids = set()
        descs = data.get("rgDescriptions", {})
        
        for info in data.get("rgInventory", {}).values():
            desc = descs.get(info.get("classid"), {})
            name = desc.get("market_hash_name")
            if name and "Foil" not in desc.get("type", ""):
                inv_cards[name] = inv_cards.get(name, 0) + 1
                appid = desc.get("app_data", {}).get("appid")
                if appid:
                    appids.add(int(appid))
        return inv_cards, appids
    except Exception as e:
        logging.warning(f"Ошибка чтения локального инвентаря: {e}")
        return {}, set()

def load_price_cache():
    steam_path = find_steam_path()
    if not steam_path: return {}
    price_cache_path = os.path.join(steam_path, "appcache", "market", "cache", "pricecache.vdf")
    if not os.path.isfile(price_cache_path):
        return {}
    try:
        with open(price_cache_path, "rb") as f:
            data = vdf.binary_load(f.read())
        cache = {}
        for name, info in data.get("cache", {}).items():
            price_str = info.get("lowest_price") or info.get("median_price")
            if price_str:
                cleaned = re.sub(r"[^\d,.]", "", price_str).replace(",", ".")
                cache[name] = float(cleaned)
        return cache
    except Exception as e:
        logging.warning(f"Ошибка чтения кеша цен: {e}")
        return {}

def load_local_card_sets():
    steam_path = find_steam_path()
    if not steam_path: return {}
    community_cache_path = os.path.join(steam_path, "appcache", "communitycache.vdf")
    if not os.path.isfile(community_cache_path):
        return {}
    try:
        with open(community_cache_path, "rb") as f:
            data = vdf.binary_load(f.read())
        gamecards = data.get("CommunityCache", {}).get("GameCards", {})
        return {appid_str: list(cards.keys()) for appid_str, cards in gamecards.items()}
    except Exception as e:
        logging.warning(f"Ошибка чтения кеша карточек: {e}")
        return {}