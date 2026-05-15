#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
userfinder.py — объединённая версия визуализатора
- Загрузка данных
- Анализ изображений
- Генерация HTML (полный шаблон, объединено с visualizer_html)
"""

import sys
import random
import argparse
import hashlib
import base64
from pathlib import Path
from urllib.parse import urlparse
from typing import List, Dict, Optional
from datetime import datetime
import requests
from io import BytesIO

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# --- Настройки ---
REPORT_DIR = Path("report")


# -----------------------
# Вспомогательные функции
# -----------------------
def print_banner() -> None:
    banner = r"""
█░█░█▀█░█▀▄░█▀▀░█▀▄░█▀▀░█▀▄
░█▀█░█▀█░█▀▄░█▀▀░█▀▄░█▀▀░█░█
░▀░▀░▀░▀░▀░▀░▀▀▀░▀▀░░▀▀▀░▀▀░
▀█▀░█▀█░█▀▀░▀█▀░█▀▀░█░█░█▀▀
░█░░█▀█░█▀▀░░█░░█▀▀░█▀█░▀▀█
░▀░░▀░▀░▀▀▀░░▀░░▀▀▀░▀░▀░▀▀▀
"""
    print("\033[96m\033[1m" + banner + "\033[0m")


def load_temp_data(username: str) -> Dict:
    """Загружает временные данные из бинарного файла"""
    temp_file = REPORT_DIR / f".{username}_temp.dat"
    if not temp_file.exists():
        print(f"\033[91mНе найден временный файл данных: {temp_file}. Сначала выполните поиск.\033[0m")
        sys.exit(1)
    
    import pickle
    try:
        with temp_file.open("rb") as f:
            data = pickle.load(f)
        return data
    except Exception as e:
        print(f"\033[91mОшибка загрузки временных данных: {e}\033[0m")
        sys.exit(1)


def cleanup_temp_data(username: str) -> None:
    """Удаляет временный файл после использования"""
    temp_file = REPORT_DIR / f".{username}_temp.dat"
    if temp_file.exists():
        temp_file.unlink()
        print(f"\033[90m[*] Временный файл удалён: {temp_file}\033[0m")


def calculate_statistics(results: List[Dict]) -> Dict:
    """Рассчитывает статистику по результатам"""
    total = len(results)
    high_confidence = sum(1 for r in results if r.get('score', 0) >= 0.8)
    medium_confidence = sum(1 for r in results if 0.5 <= r.get('score', 0) < 0.8)
    low_confidence = sum(1 for r in results if 0.3 <= r.get('score', 0) < 0.5)
    no_match = sum(1 for r in results if r.get('score', 0) < 0.3)
    
    # Статистика по аватаркам
    avatars_count = sum(1 for r in results if r.get('avatar'))
    unique_avatars = len(set(r.get('avatar', '') for r in results if r.get('avatar')))
    
    avg_score = sum(r.get('score', 0) for r in results) / total if total > 0 else 0
    
    # Сортируем результаты по проценту (убывание)
    sorted_results = sorted(results, key=lambda x: x.get('score', 0), reverse=True)
    
    return {
        'total': total,
        'high_confidence': high_confidence,
        'medium_confidence': medium_confidence,
        'low_confidence': low_confidence,
        'no_match': no_match,
        'avg_score': avg_score,
        'found_count': high_confidence + medium_confidence,
        'avatars_count': avatars_count,
        'unique_avatars': unique_avatars,
        'avatar_coverage': (avatars_count / total * 100) if total > 0 else 0,
        'sorted_results': sorted_results
    }


def get_confidence_color(score: float) -> str:
    """Возвращает цвет в зависимости от уровня уверенности"""
    if score >= 0.8:
        return "#10B981"  # зеленый
    elif score >= 0.5:
        return "#F59E0B"  # желтый
    elif score >= 0.3:
        return "#EF4444"  # красный
    else:
        return "#6B7280"  # серый


def get_confidence_label(score: float) -> str:
    """Возвращает текстовое описание уровня уверенности"""
    if score >= 0.8:
        return "Высокая уверенность"
    elif score >= 0.5:
        return "Средняя уверенность"
    elif score >= 0.3:
        return "Низкая уверенность"
    else:
        return "Совпадение не найдено"


def download_image(url: str) -> Optional[bytes]:
    """Скачивает изображение по URL"""
    try:
        response = requests.get(url, timeout=10, headers={'User-Agent': 'UserFinder/2.0'})
        if response.status_code == 200:
            return response.content
    except:
        pass
    return None


def get_image_hash(image_data: bytes) -> str:
    """Вычисляет хэш изображения для сравнения"""
    return hashlib.md5(image_data).hexdigest()[:16]


def analyze_avatar_colors(image_data: bytes) -> Optional[List[str]]:
    """Анализирует доминирующие цвета аватарки"""
    if not PIL_AVAILABLE:
        return None
        
    try:
        image = Image.open(BytesIO(image_data))
        # Уменьшаем размер для быстрого анализа
        image = image.resize((50, 50))
        # Конвертируем в RGB если нужно
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Получаем доминирующие цвета
        pixels = list(image.getdata())
        # Берем случайные пиксели для анализа
        sample_pixels = random.sample(pixels, min(100, len(pixels)))
        
        colors = []
        for r, g, b in sample_pixels[:5]:  # Берем первые 5 цветов
            colors.append(f"#{r:02x}{g:02x}{b:02x}")
            
        return colors
    except:
        return None


def shorten_url(url: str, max_length: int = 50) -> str:
    """Сокращает URL для отображения"""
    if len(url) <= max_length:
        return url
    
    parsed = urlparse(url)
    domain = parsed.netloc
    path = parsed.path
    
    if len(domain) + len(path) > max_length:
        if len(path) > 20:
            path = path[:15] + "..."
    
    shortened = domain + path
    if len(shortened) > max_length:
        shortened = shortened[:max_length-3] + "..."
    
    return shortened


def detect_avatar_similarities(results: List[Dict]) -> Dict:
    """Обнаруживает совпадения аватарок между сервисами"""
    avatar_groups = {}
    avatar_hashes = {}
    
    for result in results:
        avatar_url = result.get('avatar')
        if not avatar_url:
            continue
            
        # Скачиваем и анализируем аватарку
        image_data = download_image(avatar_url)
        if image_data:
            img_hash = get_image_hash(image_data)
            
            if img_hash not in avatar_hashes:
                avatar_hashes[img_hash] = {
                    'url': avatar_url,
                    'sites': [],
                    'colors': analyze_avatar_colors(image_data)
                }
            
            avatar_hashes[img_hash]['sites'].append(result.get('site', 'Unknown'))
    
    # Группируем по хэшам (одинаковые аватарки)
    for img_hash, data in avatar_hashes.items():
        if len(data['sites']) > 1:  # Только группы с совпадениями
            avatar_groups[img_hash] = data
    
    return avatar_groups


def create_avatar_thumbnail(image_data: bytes, size: int = 80) -> Optional[str]:
    """Создает миниатюру аватарки в base64"""
    if not PIL_AVAILABLE:
        return None
        
    try:
        image = Image.open(BytesIO(image_data))
        image.thumbnail((size, size))
        
        buffered = BytesIO()
        image.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        return f"data:image/png;base64,{img_str}"
    except:
        return None


def enrich_results_data(results: List[Dict], avatar_similarities: Dict) -> List[Dict]:
    """Обогащает данные результатов для визуализации"""
    stats = calculate_statistics(results)
    high_medium_results = [r for r in stats['sorted_results'] if r.get('score', 0) >= 0.3]
    top_results = high_medium_results[:15]
    
    enriched_results = []
    for i, result in enumerate(top_results):
        score = result.get('score', 0)
        avatar_url = result.get('avatar')
        
        # Анализ аватарки
        avatar_data = None
        avatar_thumbnail = None
        avatar_colors = None
        
        if avatar_url:
            avatar_data = download_image(avatar_url)
            if avatar_data:
                avatar_thumbnail = create_avatar_thumbnail(avatar_data)
                avatar_colors = analyze_avatar_colors(avatar_data)
        
        # Поиск совпадений аватарки
        avatar_group = None
        if avatar_data:
            img_hash = get_image_hash(avatar_data)
            avatar_group = avatar_similarities.get(img_hash)
        
        enriched_results.append({
            'number': i + 1,
            'site': result.get('site', 'Unknown'),
            'url': result.get('url', '#'),
            'score': score,
            'score_percent': int(score * 100),
            'confidence_color': get_confidence_color(score),
            'confidence_label': get_confidence_label(score),
            'avatar': avatar_url,
            'avatar_thumbnail': avatar_thumbnail,
            'avatar_colors': avatar_colors,
            'avatar_group': avatar_group,
            'has_avatar': bool(avatar_url),
            'title': result.get('title', ''),
            'short_url': shorten_url(result.get('url', ''), 45)
        })
    
    return enriched_results


# -----------------------
# HTML генерация (полный шаблон перенесён сюда)
# -----------------------

def generate_enhanced_chain_html(username: str, enriched_results: List[Dict], 
                               stats: Dict, avatar_similarities: Dict, out_path: Path) -> Path:
    """
    Генерирует улучшенную визуализацию с анализом аватарок
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Генерация цветовой палитры
    accent_color = "#{:06x}".format(random.randint(0x3366CC, 0x6699FF))
    gradient_start = accent_color
    gradient_end = "#{:06x}".format(random.randint(0xCC3366, 0xFF6699))
    
    # Подготовка HTML для совпадений аватарок
    similarities_html = generate_avatar_similarities_html(avatar_similarities)
    
    # Генерация основной HTML структуры
    html_content = generate_html_structure(
        username, now, stats, enriched_results, 
        avatar_similarities, accent_color, gradient_start, 
        gradient_end, similarities_html
    )
    
    out_path.write_text(html_content, encoding="utf-8")
    return out_path


def generate_avatar_similarities_html(avatar_similarities: Dict) -> str:
    """Генерирует HTML для секции совпадений аватарок"""
    if not avatar_similarities:
        return ""
    
    similarities_html = """
        <div class="similarities-section">
            <h3><i class="fas fa-images"></i> Обнаруженные совпадения аватарок</h3>
            <div class="avatar-groups">
    """
    
    for i, (img_hash, data) in enumerate(list(avatar_similarities.items())[:5]):
        sites_list = ", ".join(data['sites'][:5])
        if len(data['sites']) > 5:
            sites_list += f" и ещё {len(data['sites']) - 5}"
            
        colors_html = ""
        if data.get('colors'):
            colors_html = '<div class="color-palette">' + \
                ''.join([f'<div class="color-swatch" style="background-color: {color};"></div>' 
                        for color in data['colors'][:5]]) + '</div>'
        
        similarities_html += f"""
            <div class="avatar-group">
                <div class="group-header">
                    <span class="group-badge">Группа {i+1}</span>
                    <span class="sites-count">{len(data['sites'])} сервисов</span>
                </div>
                <div class="group-content">
                    <div class="sites-list">{sites_list}</div>
                    {colors_html}
                </div>
            </div>
        """
    
    similarities_html += """
            </div>
        </div>
    """
    
    return similarities_html


def generate_service_chain_html(enriched_results: List[Dict], accent_color: str) -> str:
    """Генерирует HTML для цепочки сервисов"""
    if not enriched_results:
        return '''
        <div class="empty-state">
            <i class="fas fa-search"></i>
            <h3>Совпадения не найдены</h3>
            <p>Не удалось найти профили с достаточным уровнем уверенности</p>
        </div>
        '''
    
    service_items = []
    for service in enriched_results:
        service_item = f'''
        <div class="service-item" onclick="window.open('{service['url']}', '_blank')">
            <div class="service-number">{service['number']}</div>
            {generate_avatar_html(service)}
            <div class="service-info">
                <div class="service-name">
                    {service['site']}
                    {generate_similarity_badge(service)}
                </div>
                <div class="service-url">
                    <a href="{service['url']}" target="_blank" style="color: {accent_color}; text-decoration: none;">
                        {service['short_url']}
                    </a>
                </div>
                <div class="service-meta">
                    <div class="confidence-badge" style="background-color: {service['confidence_color']};">
                        {service['confidence_label']}
                    </div>
                    {generate_avatar_badge(service)}
                    {generate_color_palette(service)}
                </div>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: {service['score_percent']}%; background-color: {service['confidence_color']};"></div>
                </div>
            </div>
            <div class="score-display" style="color: {service['confidence_color']};">
                {service['score_percent']}%
            </div>
        </div>
        '''
        service_items.append(service_item)
    
    return ''.join(service_items)


def generate_avatar_html(service: Dict) -> str:
    """Генерирует HTML для аватарки"""
    if service['has_avatar']:
        return f"<img class='avatar-thumbnail' src='{service['avatar_thumbnail'] or service['avatar']}' alt='Аватар' onerror=\"this.style.display='none';this.nextElementSibling.style.display='flex';\">"
    else:
        return '<div class="no-avatar"><i class="fas fa-user"></i></div>'


def generate_similarity_badge(service: Dict) -> str:
    """Генерирует бейдж совпадения аватарки"""
    if service['avatar_group'] and len(service['avatar_group']['sites']) > 1:
        return '<span class="similarity-badge"><i class="fas fa-clone"></i> Совпадение</span>'
    return ''


def generate_avatar_badge(service: Dict) -> str:
    """Генерирует бейдж наличия аватарки"""
    avatar_status = '✓' if service['has_avatar'] else '✗'
    return f'''
    <div class="avatar-badge">
        <i class="fas {'fa-check-circle' if service['has_avatar'] else 'fa-times-circle'}"></i>
        Аватар: {avatar_status}
    </div>
    '''


def generate_color_palette(service: Dict) -> str:
    """Генерирует цветовую палитру"""
    if service['avatar_colors']:
        colors_html = ''.join([
            f'<div class="color-swatch" style="background-color: {color};" title="{color}"></div>' 
            for color in service['avatar_colors'][:3]
        ])
        return f'<div class="color-palette">{colors_html}</div>'
    return ''


def generate_html_structure(username: str, now: str, stats: Dict, enriched_results: List[Dict],
                          avatar_similarities: Dict, accent_color: str, gradient_start: str,
                          gradient_end: str, similarities_html: str) -> str:
    """Генерирует полную HTML структуру"""
    
    service_chain_html = generate_service_chain_html(enriched_results, accent_color)
    
    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🔗 Расширенная цепочка — {username}</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        {generate_css_styles(accent_color, gradient_start, gradient_end)}
    </style>
</head>
<body>
    <div class="container">
        {generate_header_html(username, now, stats, accent_color, gradient_end, avatar_similarities)}
        {generate_chain_container_html(service_chain_html, similarities_html, avatar_similarities, accent_color)}
        {generate_footer_html()}
    </div>

    <script>
        {generate_js_scripts()}
    </script>
</body>
</html>
"""
    return html


def generate_header_html(username: str, now: str, stats: Dict, accent_color: str, gradient_end: str, avatar_similarities: Dict) -> str:
    """Генерирует HTML заголовка"""
    return f"""
        <div class="header">
            <div class="user-info">
                <div class="user-avatar">{username[0].upper() if username else 'U'}</div>
                <div class="user-details">
                    <h1>Расширенная цепочка профилей — {username}</h1>
                    <p>Сгенерировано: {now} • Сервисов: {stats['total']} • Найдено: {stats['found_count']} • Аватарок: {stats['avatars_count']}</p>
                </div>
            </div>

            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-number stat-total">{stats['total']}</div>
                    <div class="stat-label">Всего проверено сервисов</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number stat-high">{stats['high_confidence']}</div>
                    <div class="stat-label">Высокая уверенность</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number stat-medium">{stats['medium_confidence']}</div>
                    <div class="stat-label">Средняя уверенность</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number stat-avatar">{stats['avatars_count']}</div>
                    <div class="stat-label">Обнаружено аватарок</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" style="color: {accent_color};">{int(stats['avg_score'] * 100)}%</div>
                    <div class="stat-label">Средний процент совпадения</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number stat-avatar">{len(avatar_similarities)}</div>
                    <div class="stat-label">Групп совпадений аватарок</div>
                </div>
            </div>
        </div>
    """


def generate_chain_container_html(service_chain_html: str, similarities_html: str, 
                                avatar_similarities: Dict, accent_color: str) -> str:
    """Генерирует HTML контейнера цепочки"""
    return f"""
        <div class="chain-container">
            <div class="chain-title">
                <h2><i class="fas fa-link"></i> Цепочка профилей по сервисам</h2>
                <p>Сервисы отсортированы по уровню уверенности совпадения</p>
            </div>

            <div class="service-chain">
                {service_chain_html}
            </div>

            {similarities_html if avatar_similarities else ''}

            {generate_legend_html(accent_color)}
        </div>
    """


def generate_legend_html(accent_color: str) -> str:
    """Генерирует HTML легенды"""
    return """
        <div class="legend">
            <div class="legend-item">
                <div class="legend-color" style="background-color: #10B981;"></div>
                <span>Высокая уверенность (80-100%)</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background-color: #F59E0B;"></div>
                <span>Средняя уверенность (50-79%)</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background-color: #EF4444;"></div>
                <span>Низкая уверенность (0-49%)</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background-color: #8B5CF6;"></div>
                <span>Совпадения аватарок</span>
            </div>
        </div>
    """


def generate_footer_html() -> str:
    """Генерирует HTML футера"""
    
    pil_status = 'Включен' if PIL_AVAILABLE else 'Требуется PIL'
    
    return f"""
        <div class="footer">
            <p>UserFinder Enhanced Visualizer • Анализ цифрового следа • Сгенерировано автоматически</p>
            <p style="font-size: 12px; margin-top: 5px;">
                <i class="fas {'fa-check' if PIL_AVAILABLE else 'fa-times'}"></i> Анализ изображений: {pil_status}
            </p>
        </div>
    """


def generate_css_styles(accent_color: str, gradient_start: str, gradient_end: str) -> str:
    """Генерирует CSS стили"""
    return f"""
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Inter', sans-serif;
            background: linear-gradient(135deg, {gradient_start}, {gradient_end});
            min-height: 100vh;
            color: #2D3748;
            overflow-x: hidden;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }}

        .header {{
            background: rgba(255, 255, 255, 0.98);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 30px;
            margin-bottom: 20px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }}

        .user-info {{
            display: flex;
            align-items: center;
            gap: 20px;
            margin-bottom: 20px;
        }}

        .user-avatar {{
            width: 80px;
            height: 80px;
            border-radius: 50%;
            background: linear-gradient(135deg, {accent_color}, {gradient_end});
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 32px;
            font-weight: bold;
            color: white;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
        }}

        .user-details h1 {{
            font-size: 28px;
            font-weight: 700;
            margin-bottom: 5px;
            background: linear-gradient(135deg, {accent_color}, {gradient_end});
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}

        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 15px;
            margin-top: 20px;
        }}

        .stat-card {{
            background: linear-gradient(135deg, rgba(255, 255, 255, 0.95), rgba(255, 255, 255, 0.8));
            padding: 20px;
            border-radius: 15px;
            text-align: center;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.3);
            transition: transform 0.3s ease;
        }}

        .stat-card:hover {{
            transform: translateY(-2px);
        }}

        .stat-number {{
            font-size: 32px;
            font-weight: 700;
            margin-bottom: 5px;
        }}

        .stat-high {{ color: #10B981; }}
        .stat-medium {{ color: #F59E0B; }}
        .stat-low {{ color: #EF4444; }}
        .stat-total {{ color: {accent_color}; }}
        .stat-avatar {{ color: #8B5CF6; }}

        .stat-label {{
            font-size: 14px;
            color: #6B7280;
            font-weight: 500;
        }}

        .chain-container {{
            background: rgba(255, 255, 255, 0.98);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 30px;
            margin-bottom: 20px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }}

        .chain-title {{
            text-align: center;
            margin-bottom: 30px;
        }}

        .chain-title h2 {{
            font-size: 24px;
            font-weight: 600;
            color: {accent_color};
            margin-bottom: 10px;
        }}

        .service-chain {{
            display: flex;
            flex-direction: column;
            gap: 15px;
        }}

        .service-item {{
            display: flex;
            align-items: center;
            background: rgba(255, 255, 255, 0.9);
            border-radius: 15px;
            padding: 20px;
            transition: all 0.3s ease;
            border-left: 4px solid {accent_color};
            cursor: pointer;
            position: relative;
        }}

        .service-item:hover {{
            transform: translateY(-2px);
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.1);
            background: rgba(255, 255, 255, 0.95);
        }}

        .service-number {{
            width: 40px;
            height: 40px;
            border-radius: 50%;
            background: {accent_color};
            color: white;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            margin-right: 20px;
            flex-shrink: 0;
            font-size: 14px;
        }}

        .avatar-thumbnail {{
            width: 50px;
            height: 50px;
            border-radius: 8px;
            margin-right: 15px;
            object-fit: cover;
            border: 2px solid #E5E7EB;
            flex-shrink: 0;
        }}

        .no-avatar {{
            width: 50px;
            height: 50px;
            border-radius: 8px;
            margin-right: 15px;
            background: #F3F4F6;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #9CA3AF;
            font-size: 20px;
            flex-shrink: 0;
        }}

        .service-info {{
            flex: 1;
        }}

        .service-name {{
            font-size: 18px;
            font-weight: 600;
            margin-bottom: 5px;
            color: #2D3748;
            display: flex;
            align-items: center;
            gap: 10px;
        }}

        .service-url {{
            font-size: 14px;
            color: #6B7280;
            margin-bottom: 8px;
            word-break: break-all;
        }}

        .service-meta {{
            display: flex;
            gap: 15px;
            align-items: center;
            flex-wrap: wrap;
        }}

        .confidence-badge {{
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 500;
            color: white;
        }}

        .avatar-badge {{
            display: flex;
            align-items: center;
            gap: 5px;
            font-size: 12px;
            color: #6B7280;
        }}

        .similarity-badge {{
            background: #8B5CF6;
            color: white;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 500;
        }}

        .color-palette {{
            display: flex;
            gap: 3px;
        }}

        .color-swatch {{
            width: 15px;
            height: 15px;
            border-radius: 3px;
            border: 1px solid #E5E7EB;
        }}

        .progress-bar {{
            width: 100%;
            height: 6px;
            background: #E5E7EB;
            border-radius: 3px;
            margin-top: 8px;
            overflow: hidden;
        }}

        .progress-fill {{
            height: 100%;
            border-radius: 3px;
            transition: width 0.5s ease;
        }}

        .score-display {{
            font-size: 24px;
            font-weight: 700;
            margin-left: 20px;
            flex-shrink: 0;
        }}

        .similarities-section {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #E5E7EB;
        }}

        .avatar-groups {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 15px;
            margin-top: 20px;
        }}

        .avatar-group {{
            background: rgba(139, 92, 246, 0.1);
            border: 1px solid rgba(139, 92, 246, 0.2);
            border-radius: 12px;
            padding: 15px;
        }}

        .group-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }}

        .group-badge {{
            background: #8B5CF6;
            color: white;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 500;
        }}

        .sites-count {{
            font-size: 12px;
            color: #6B7280;
        }}

        .legend {{
            display: flex;
            justify-content: center;
            gap: 30px;
            margin-top: 30px;
            flex-wrap: wrap;
        }}

        .legend-item {{
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 14px;
        }}

        .legend-color {{
            width: 15px;
            height: 15px;
            border-radius: 3px;
        }}

        .footer {{
            text-align: center;
            color: white;
            padding: 20px;
            font-size: 14px;
        }}

        .empty-state {{
            text-align: center;
            padding: 60px 20px;
            color: #6B7280;
        }}

        .empty-state i {{
            font-size: 48px;
            margin-bottom: 20px;
            color: #D1D5DB;
        }}

        @media (max-width: 768px) {{
            .container {{
                padding: 10px;
            }}
            
            .header, .chain-container {{
                padding: 20px;
            }}
            
            .service-item {{
                flex-direction: column;
                align-items: flex-start;
                gap: 15px;
            }}
            
            .service-number {{
                margin-right: 0;
            }}
            
            .stats-grid {{
                grid-template-columns: 1fr;
            }}
            
            .legend {{
                flex-direction: column;
                align-items: center;
                gap: 15px;
            }}
        }}
    """


def generate_js_scripts() -> str:
    """Генерирует JavaScript скрипты"""
    return """
        // Анимация появления элементов
        document.addEventListener('DOMContentLoaded', function() {
            const serviceItems = document.querySelectorAll('.service-item');
            serviceItems.forEach((item, index) => {
                setTimeout(() => {
                    item.style.opacity = '0';
                    item.style.transform = 'translateY(20px)';
                    item.style.transition = 'all 0.5s ease';
                    
                    setTimeout(() => {
                        item.style.opacity = '1';
                        item.style.transform = 'translateY(0)';
                    }, 50);
                }, index * 100);
            });
            
            // Анимация статистики
            const statNumbers = document.querySelectorAll('.stat-number');
            statNumbers.forEach(stat => {
                const target = parseInt(stat.textContent);
                let current = 0;
                const increment = target / 50;
                const timer = setInterval(() => {
                    current += increment;
                    if (current >= target) {
                        current = target;
                        clearInterval(timer);
                    }
                    stat.textContent = Math.round(current).toString();
                }, 30);
            });
        });
        
        // Обработка ошибок загрузки изображений
        document.addEventListener('error', function(e) {
            if (e.target.classList.contains('avatar-thumbnail')) {
                e.target.style.display = 'none';
                const noAvatar = document.createElement('div');
                noAvatar.className = 'no-avatar';
                noAvatar.innerHTML = '<i class="fas fa-user"></i>';
                e.target.parentNode.insertBefore(noAvatar, e.target.nextSibling);
            }
        }, true);
    """


# -----------------------
# Основная логика визуализации
# -----------------------
def run_visualize(username: str) -> None:
    username = username.strip()
    print(f"\033[93m[*] Загрузка данных для: {username}\033[0m")
    
    # Проверяем зависимости
    if not PIL_AVAILABLE:
        print(f"\033[93m[*] Предупреждение: PIL не установлен. Анализ изображений будет ограничен.\033[0m")
        print(f"\033[93m[*] Установите: pip install Pillow\033[0m")
    
    # Загружаем временные данные
    data = load_temp_data(username)
    results = data.get("results", [])
    
    if not results:
        print(f"\033[91mНет данных для визуализации\033[0m")
        sys.exit(1)
    
    print(f"\033[92m[*] Найдено результатов: {len(results)}\033[0m")
    
    # Анализ совпадений аватарок
    avatar_similarities = detect_avatar_similarities(results)
    
    # Обогащаем данные для визуализации
    enriched_results = enrich_results_data(results, avatar_similarities)
    stats = calculate_statistics(results)
    
    # Генерируем улучшенную логическую цепочку
    out_html = REPORT_DIR / f"{username}_enhanced_chain.html"
    generate_enhanced_chain_html(username, enriched_results, stats, avatar_similarities, out_html)
    print(f"\033[96m[*] 🔗 Улучшенная цепочка создана: {out_html}\033[0m")
    
    # Очищаем временные данные
    cleanup_temp_data(username)
    print(f"\033[92m[*] ✅ Визуализация завершена! Откройте HTML-файл в браузере.\033[0m")


def main() -> None:
    parser = argparse.ArgumentParser(description="Enhanced Visualizer — улучшенная визуализация цепочки профилей")
    parser.add_argument("username", help="Ник для визуализации (например: asasin)")

    args = parser.parse_args()
    print_banner()
    run_visualize(args.username)


if __name__ == "__main__":
    main()
