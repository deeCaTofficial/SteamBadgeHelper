import time
import logging
import requests
import re
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup

STEAM_API_BASE = "https://api.steampowered.com"
STEAM_COMMUNITY_BASE = "https://steamcommunity.com"
STEAM_STORE_API_BASE = "https://store.steampowered.com/api"

CURRENCIES = {
    "USD": {"id": 1, "flag": "US"}, "GBP": {"id": 2, "flag": "GB"}, "EUR": {"id": 3, "flag": "EU"},
    "CHF": {"id": 4, "flag": "CH"}, "RUB": {"id": 5, "flag": "RU"}, "PLN": {"id": 6, "flag": "PL"},
    "BRL": {"id": 7, "flag": "BR"}, "JPY": {"id": 8, "flag": "JP"}, "NOK": {"id": 9, "flag": "NO"},
    "IDR": {"id": 10, "flag": "ID"}, "MYR": {"id": 11, "flag": "MY"}, "PHP": {"id": 12, "flag": "PH"},
    "SGD": {"id": 13, "flag": "SG"}, "THB": {"id": 14, "flag": "TH"}, "VND": {"id": 15, "flag": "VN"},
    "KRW": {"id": 16, "flag": "KR"}, "TRY": {"id": 17, "flag": "TR"}, "UAH": {"id": 18, "flag": "UA"},
    "MXN": {"id": 19, "flag": "MX"}, "CAD": {"id": 20, "flag": "CA"}, "AUD": {"id": 21, "flag": "AU"},
    "NZD": {"id": 22, "flag": "NZ"}, "CNY": {"id": 23, "flag": "CN"}, "INR": {"id": 24, "flag": "IN"},
    "CLP": {"id": 25, "flag": "CL"}, "PEN": {"id": 26, "flag": "PE"}, "COP": {"id": 27, "flag": "CO"},
    "ZAR": {"id": 28, "flag": "ZA"}, "HKD": {"id": 29, "flag": "HK"}, "TWD": {"id": 30, "flag": "TW"},
    "SAR": {"id": 31, "flag": "SA"}, "AED": {"id": 32, "flag": "AE"}, "SEK": {"id": 33, "flag": "SE"},
    "ARS": {"id": 34, "flag": "AR"}, "ILS": {"id": 35, "flag": "IL"}, "BYN": {"id": 36, "flag": "BY"},
    "KZT": {"id": 37, "flag": "KZ"}, "KWD": {"id": 38, "flag": "KW"}, "QAR": {"id": 39, "flag": "QA"},
    "CRC": {"id": 40, "flag": "CR"}, "UYU": {"id": 41, "flag": "UY"}, "BGN": {"id": 42, "flag": "BG"},
    "HRK": {"id": 43, "flag": "HR"}, "CZK": {"id": 44, "flag": "CZ"}, "DKK": {"id": 45, "flag": "DK"},
    "HUF": {"id": 46, "flag": "HU"}, "RON": {"id": 47, "flag": "RO"},
}

_last_steam_request_time = 0

def prepare_session():
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    })
    session.cookies.set('steamLogin_lang', 'russian', domain='.steamcommunity.com')
    session.cookies.set('birthtime', '631152001', domain='.steamcommunity.com')
    session.cookies.set('birthtime', '631152001', domain='.store.steampowered.com')
    session.cookies.set('wants_mature_content', '1', domain='.store.steampowered.com')
    return session

def safe_get(session, url, headers=None, retries=3, timeout=15, min_interval=4):
    global _last_steam_request_time
    for attempt in range(retries):
        elapsed = time.time() - _last_steam_request_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)

        try:
            response = session.get(url, timeout=timeout, headers=headers)
            _last_steam_request_time = time.time()
            if response.status_code == 429:
                logging.warning("Получен статус 429. Длинная пауза (10 минут)...")
                time.sleep(600)
                continue
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            logging.warning(f"Ошибка запроса (попытка {attempt+1}/{retries}): {url} | {e}")
            if attempt < retries - 1:
                time.sleep((attempt + 1) * 3)
    return None

def resolve_steamid64(user_input):
    user_input = user_input.strip()
    if re.match(r'^\d{17}$', user_input):
        return user_input

    match = re.match(r'^https?://steamcommunity\\.com/(id|profiles)/([^/]+)', user_input)
    if match:
        mode, value = match.groups()
        if mode == "profiles" and re.match(r'^\d{17}$', value):
            return value
        custom_url = value
    else:
        custom_url = user_input

    url = f"{STEAM_COMMUNITY_BASE}/id/{custom_url}?xml=1"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            root = ET.fromstring(resp.content)
            sid = root.find('steamID64')
            if sid is not None and re.match(r'^\d{17}$', sid.text):
                return sid.text
    except Exception:
        pass
    return None

def get_all_card_names_from_html(html):
    soup = BeautifulSoup(html, 'html.parser')
    card_names = set()
    
    for card_div in soup.select('div.badge_card_set_card div.badge_card_set_text'):
        name = card_div.get_text(strip=True)
        if name:
            card_names.add(name)

    # Fallback selectors
    if not card_names:
        for n in soup.select('.gamecard_card_name'):
            name = n.get_text(strip=True)
            if name:
                card_names.add(name)

    return list(card_names)