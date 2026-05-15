#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
userfinder.py — основной файл для поиска профилей
- search: параллельный поиск по нику с красивым прогресс-баром
"""
from __future__ import annotations
import sys
import os
import json
import time
import random
import argparse
import hashlib
import threading
from pathlib import Path
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Tuple, List, Dict

import requests
from bs4 import BeautifulSoup
from colorama import Fore, Style, init as colorama_init

# --- Настройки ---
DB_DEFAULT = "my_sites.json"
REPORT_DIR = Path("report")
REQUEST_TIMEOUT = 10
USER_AGENT = "UserFinder/2.0 (+https://example.local)"
MAX_WORKERS = 4
SLEEP_MIN = 0.03
SLEEP_MAX = 0.15

colorama_init(autoreset=True)
_lock = threading.Lock()


# -----------------------
# Вспомогательные функции
# -----------------------
def print_banner():
    banner = r"""
▒█████    ██████  ██▓ ███▄    █ ▄▄▄█████▓     ██████ ▄▄▄█████▓ ▒█████   ██▀███   ███▄ ▄███▓
▒██▒  ██▒▒██    ▒ ▓██▒ ██ ▀█   █ ▓  ██▒ ▓▒   ▒██    ▒ ▓  ██▒ ▓▒▒██▒  ██▒▓██ ▒ ██▒▓██▒▀█▀ ██▒
▒██░  ██▒░ ▓██▄   ▒██▒▓██  ▀█ ██▒▒ ▓██░ ▒░   ░ ▓██▄   ▒ ▓██░ ▒░▒██░  ██▒▓██ ░▄█ ▒▓██    ▓██░
▒██   ██░  ▒   ██▒░██░▓██▒  ▐▌██▒░ ▓██▓ ░      ▒   ██▒░ ▓██▓ ░ ▒██   ██░▒██▀▀█▄  ▒██    ▒██ 
░ ████▓▒░▒██████▒▒░██░▒██░   ▓██░  ▒██▒ ░    ▒██████▒▒  ▒██▒ ░ ░ ████▓▒░░██▓ ▒██▒▒██▒   ░██▒
░ ▒░▒░▒░ ▒ ▒▓▒ ▒ ░░▓  ░ ▒░   ▒ ▒   ▒ ░░      ▒ ▒▓▒ ▒ ░  ▒ ░░   ░ ▒░▒░▒░ ░ ▒▓ ░▒▓░░ ▒░   ░  ░
  ░ ▒ ▒░ ░ ░▒  ░ ░ ▒ ░░ ░░   ░ ▒░    ░       ░ ░▒  ░ ░    ░      ░ ▒ ▒░   ░▒ ░ ▒░░  ░      ░
░ ░ ░ ▒  ░  ░  ░   ▒ ░   ░   ░ ░   ░         ░  ░  ░    ░      ░ ░ ░ ▒    ░░   ░ ░      ░   
    ░ ░        ░   ░           ░                   ░               ░ ░     ░            ░
"""
    print(Fore.CYAN + Style.BRIGHT + banner + Style.RESET_ALL)


def animate_countdown(seconds: int) -> None:
    """Анимация обратного отсчета перед запуском"""
    print(Fore.YELLOW + f"[*] Запуск поиска через...")
    for i in range(seconds, 0, -1):
        print(Fore.YELLOW + f"[{i}]", end=" ", flush=True)
        time.sleep(1)
    print(Fore.GREEN + "\n[GO!] Начинаем поиск...\n" + Style.RESET_ALL)


def print_progress_bar(iteration: int, total: int, prefix: str = '', suffix: str = '', 
                      decimals: int = 1, length: int = 50, fill: str = '█', 
                      print_end: str = "\r") -> None:
    """
    Печатает красивый прогресс-бар в консоли
    """
    percent = ("{0:." + str(decimals) + "f}").format(100 * (iteration / float(total)))
    filled_length = int(length * iteration // total)
    bar = fill * filled_length + '-' * (length - filled_length)
    
    # Расчет оставшегося времени
    if iteration > 0:
        elapsed = time.time() - start_time
        time_per_item = elapsed / iteration
        remaining = time_per_item * (total - iteration)
        time_str = f"{elapsed:.0f}s (~{remaining:.0f}s, {iteration/elapsed:.1f}/s)"
    else:
        time_str = "расчет..."
    
    print(f'\r{prefix} |{bar}| {percent}% [{iteration}/{total}] {time_str} {suffix}', end=print_end, flush=True)
    
    if iteration == total: 
        print()


def short_hash(s: str, length: int = 6) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:length]


def shorten_url(url: str, max_length: int = 60) -> str:
    """Сокращает URL для красивого вывода в консоли"""
    if len(url) <= max_length:
        return url
    
    parsed = urlparse(url)
    domain = parsed.netloc
    path = parsed.path
    
    # Оставляем домен и начало пути, обрезаем середину
    if len(domain) + len(path) > max_length:
        # Сокращаем путь
        if len(path) > 30:
            path = path[:15] + "..." + path[-12:]
    
    shortened = domain + path
    if len(shortened) > max_length:
        shortened = shortened[:max_length-3] + "..."
    
    return shortened


def load_sites(path: str) -> List[Dict]:
    p = Path(path)
    if not p.exists():
        print(Fore.RED + f"Ошибка: база сайтов не найдена: {path}")
        sys.exit(1)
    try:
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(Fore.RED + f"Не удалось прочитать базу сайтов: {e}")
        sys.exit(1)
    
    sites = []
    for item in data:
        if isinstance(item, dict) and "url" in item:
            name = item.get("name") or item.get("site") or item["url"]
            sites.append({"name": name, "url": item["url"]})
    return sites


def build_url(template: str, username: str) -> str:
    return template.replace("{username}", username).replace("{user}", username)


def safe_get(url: str) -> Optional[requests.Response]:
    headers = {"User-Agent": USER_AGENT}
    try:
        r = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        return r
    except requests.RequestException:
        return None


def make_absolute(link: Optional[str], base: Optional[str]) -> Optional[str]:
    if not link:
        return None
    link = link.strip()
    if link.startswith("//"):
        return "https:" + link
    parsed = urlparse(link)
    if parsed.scheme:
        return link
    if base:
        return urljoin(base, link)
    return link


def extract_avatar_title(resp: Optional[requests.Response], base_url: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    if resp is None or resp.status_code != 200:
        return None, None
    try:
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception:
        return None, None

    title = None
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    # Try common metadata
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        return make_absolute(og.get("content"), base_url), title

    tw = soup.find("meta", attrs={"name": "twitter:image"})
    if tw and tw.get("content"):
        return make_absolute(tw.get("content"), base_url), title

    link = soup.find("link", rel="image_src")
    if link and link.get("href"):
        return make_absolute(link.get("href"), base_url), title

    # Common avatar selectors
    sel = soup.select("img.avatar, img.profile-picture, img.profile_pic, img._avatar, img.avatar__img")
    if sel:
        src = sel[0].get("src") or sel[0].get("data-src")
        if src:
            return make_absolute(src, base_url), title

    # Fallback: first few <img> with heuristics
    imgs = soup.find_all("img")
    for im in imgs[:10]:
        src = im.get("src") or im.get("data-src")
        if not src:
            continue
        w = im.get("width")
        h = im.get("height")
        try:
            if w and h and (int(w) <= 400 and int(h) <= 400):
                return make_absolute(src, base_url), title
        except Exception:
            return make_absolute(src, base_url), title

    return None, title


def score_match(resp: Optional[requests.Response], username: str, avatar: Optional[str]) -> float:
    s = 0.0
    if resp is None:
        return 0.0
    if resp.status_code == 200:
        s += 0.5
    try:
        txt = (resp.text or "").lower()
    except Exception:
        txt = ""
    if username.lower() in txt:
        s += 0.35
    if avatar:
        s += 0.15
    return min(1.0, s)


# -----------------------
# Основной рабочий поток
# -----------------------
def worker_check(site: Dict, username: str, idx: int, total: int, progress_counter: list) -> Dict:
    name = site.get("name")
    url_template = site.get("url")
    url = build_url(url_template, username)
    resp = safe_get(url)
    avatar, title = extract_avatar_title(resp, base_url=url)
    score = score_match(resp, username, avatar)

    with _lock:
        # Обновляем прогресс-бар
        progress_counter[0] += 1
        print_progress_bar(progress_counter[0], total, prefix='Searching', suffix='')
        
        # Выводим информацию о найденном профиле с сокращенными ссылками
        if resp and resp.status_code == 200 and score > 0.5:
            short_url = shorten_url(url, 50)
            if avatar:
                short_avatar = shorten_url(avatar, 40)
                print(Fore.GREEN + f"\n[+] {name}: {short_url}")
                print(Fore.CYAN + f"    └─ {short_avatar}")
            else:
                print(Fore.GREEN + f"\n[+] {name}: {short_url}")
        elif resp and resp.status_code == 404:
            pass  # Не показываем 404 ошибки в деталях
        elif resp is None:
            pass  # Не показываем ошибки соединения

    return {
        "site": name,
        "url": url,
        "status": resp.status_code if resp else None,
        "title": title,
        "avatar": avatar,
        "score": score
    }


# -----------------------
# Генерация HTML-отчёта
# -----------------------
def generate_html_report(username: str, results: List[Dict], out_path: Path) -> Path:
    found_count = sum(1 for r in results if r.get("score", 0.0) >= 0.4)
    checked = len(results)
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    accent1 = "#{:06x}".format(random.randint(0x224466, 0xFF8844))
    accent2 = "#{:06x}".format(random.randint(0x114455, 0x99CC55))

    cards_html = []
    for r in sorted(results, key=lambda x: x.get("score", 0.0), reverse=True):
        pct = int(r.get("score", 0.0) * 100)
        avatar = r.get("avatar") or ""
        if not avatar:
            avatar = "data:image/svg+xml;utf8," + (
                "<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160'>"
                "<rect fill='%23dddddd' width='100%' height='100%'/><text x='50%' y='50%' font-size='34' dominant-baseline='middle' text-anchor='middle' fill='%23666'>"
                + (r.get("site","")[:2].upper()) + "</text></svg>"
            )
        safe_avatar = avatar.replace('"', '&quot;')
        status = r.get("status") or "-"
        site_escaped = (r.get("site","")).replace("&", "&amp;").replace("<", "&lt;")
        title = (r.get("title") or "").replace("&", "&amp;").replace("<", "&lt;")
        cards_html.append(f"""
        <div class="card">
          <a class="thumb" href="{r['url']}" target="_blank" rel="noopener noreferrer" style="background-image:url('{safe_avatar}')"></a>
          <div class="info">
            <div class="toprow">
              <a class="sitename" href="{r['url']}" target="_blank">{site_escaped}</a>
              <span class="badge">{status}</span>
            </div>
            <div class="title">{title}</div>
            <div class="scorewrap">
              <div class="bar"><div class="fill" style="width:{pct}%;"></div></div>
              <div class="pct">{pct}%</div>
            </div>
          </div>
        </div>
        """)

    html = f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Отчёт — {username}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
<style>
:root{{--accent1:{accent1};--accent2:{accent2};}}
*{{box-sizing:border-box}}
body{{font-family:Inter,system-ui,Segoe UI,Roboto,Arial; background:linear-gradient(180deg,var(--accent1),var(--accent2)); margin:0;padding:28px;color:#111}}
.container{{max-width:1200px;margin:0 auto;background:#fff;border-radius:14px;padding:22px;box-shadow:0 14px 50px rgba(0,0,0,0.12)}}
.header{{display:flex;align-items:center;gap:16px}}
.logo{{width:84px;height:84px;border-radius:14px;background:linear-gradient(135deg,#fff2,#fff);display:flex;align-items:center;justify-content:center;font-weight:700;color:#444}}
.hgroup h1{{margin:0;font-size:20px}}
.hgroup p{{margin:2px 0 0;color:#666;font-size:13px}}
.metrics{{margin-left:auto;text-align:right}}
.metrics .big{{font-weight:800;font-size:18px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px;margin-top:18px}}
.card{{display:flex;gap:12px;padding:12px;border-radius:10px;border:1px solid #f0f0f0;background:#fff;align-items:center}}
.thumb{{width:88px;height:88px;border-radius:8px;background-size:cover;background-position:center;border:1px solid #e6e6e6;flex:0 0 88px;text-decoration:none}}
.info{{flex:1}}
.toprow{{display:flex;align-items:center;justify-content:space-between;gap:10px}}
.sitename{{font-weight:700;color:#0b75c9;text-decoration:none}}
.badge{{background:#f0f0f0;padding:6px 8px;border-radius:999px;font-size:12px;color:#333}}
.title{{color:#666;font-size:13px;margin-top:6px;min-height:32px}}
.scorewrap{{display:flex;align-items:center;gap:10px;margin-top:10px}}
.bar{{flex:1;height:10px;background:#eee;border-radius:999px;overflow:hidden}}
.fill{{height:100%;background:linear-gradient(90deg,var(--accent1),var(--accent2));}}
.pct{{width:44px;font-weight:700;text-align:right;color:#333}}
.footer{{margin-top:18px;color:#777;font-size:13px;display:flex;justify-content:space-between;align-items:center}}
.small{{font-size:12px;color:#999}}
@media (max-width:720px){{.grid{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="logo">UF</div>
      <div class="hgroup">
        <h1>Поиск профилей: <span style="color:var(--accent1)">{username}</span></h1>
        <p>Проверено {checked} сайтов · найдено ≈ {found_count} · сгенерировано: {now}</p>
      </div>
      <div class="metrics">
        <div class="big">{found_count}</div>
        <div class="small">вероятных совпадений</div>
      </div>
    </div>

    <div class="grid">
      {"".join(cards_html)}
    </div>

    <div class="footer">
      <div class="small">UserFinder — параллельный поиск по нику · {checked} проверок</div>
      <div class="small">Отчёт сгенерирован автоматически — использовать ответственно</div>
    </div>
  </div>
</body>
</html>
"""
    out_path.write_text(html, encoding="utf-8")
    return out_path


# -----------------------
# Сохранение временных данных для визуализации
# -----------------------
def save_temp_data(username: str, results: List[Dict]) -> Path:
    """Сохраняет временные данные в бинарный файл для визуализации"""
    temp_file = REPORT_DIR / f".{username}_temp.dat"
    import pickle
    data = {
        "username": username,
        "results": results,
        "timestamp": time.time()
    }
    with temp_file.open("wb") as f:
        pickle.dump(data, f)
    return temp_file


# -----------------------
# CLI: только search
# -----------------------
def run_search(username: str, db_path: str, save_html: bool) -> None:
    username = username.strip()
    
    # Задержка перед запуском
    animate_countdown(3)
    
    sites = load_sites(db_path)
    total = len(sites)
    
    print(Fore.CYAN + f"[*] Цель: {username}")
    print(Fore.CYAN + f"[*] База данных: {db_path} ({total} сайтов)")
    print(Fore.CYAN + f"[*] Потоков: {MAX_WORKERS}")
    print(Fore.YELLOW + "[*] Запуск поиска..." + Style.RESET_ALL)
    print()
    
    REPORT_DIR.mkdir(exist_ok=True)
    results = [None] * total
    
    # Глобальная переменная для времени старта
    global start_time
    start_time = time.time()
    
    # Счетчик для прогресс-бара
    progress_counter = [0]

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(worker_check, site, username, i, total, progress_counter): i - 1 
                  for i, site in enumerate(sites, start=1)}
        
        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                res = fut.result()
            except Exception:
                res = {"site": sites[idx]["name"], "url": build_url(sites[idx]["url"], username),
                       "status": None, "title": None, "avatar": None, "score": 0.0}
            results[idx] = res
            time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))

    print("\n")
    print(Fore.GREEN + "[*] Поиск завершен!" + Style.RESET_ALL)

    # Сохраняем временные данные для визуализации
    temp_file = save_temp_data(username, results)
    print(Fore.CYAN + f"[*] Временные данные для визуализации: {temp_file}")

    if save_html:
        out_html = REPORT_DIR / f"{username}_report.html"
        generate_html_report(username, results, out_html)
        print(Fore.CYAN + f"[*] HTML отчет: {out_html}")

    # Статистика
    found_count = sum(1 for r in results if r.get("score", 0.0) >= 0.5)
    total_time = time.time() - start_time
    
    print(Fore.CYAN + f"[*] Статистика:")
    print(Fore.CYAN + f"    └─ Найдено профилей: {found_count}/{total}")
    print(Fore.CYAN + f"    └─ Общее время: {total_time:.1f} сек")
    print(Fore.CYAN + f"    └─ Скорость: {total/total_time:.1f} сайтов/сек")
    print(Fore.GREEN + f"[*] Для визуализации выполните: python visualizer.py {username}" + Style.RESET_ALL)


def main() -> None:
    parser = argparse.ArgumentParser(description="UserFinder — поиск профилей по нику")
    parser.add_argument("username", help="Ник для поиска (например: asasin)")
    parser.add_argument("--db", default=DB_DEFAULT, help="JSON база сайтов (по умолчанию my_sites.json)")
    parser.add_argument("--html", action="store_true", help="Генерировать красивый HTML-отчёт (report/<nick>_report.html)")

    args = parser.parse_args()
    print_banner()
    run_search(args.username, args.db, args.html)


if __name__ == "__main__":
    main()