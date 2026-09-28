"""
Эвристический анализатор текста сообщений.
Определяет категорию: volunteering / forum / science / sport / culture / workshop / pushkin_card а также регион и город
"""
import json
import logging
import os
import re
from datetime import datetime
from typing import Optional, Tuple, Dict, Any, List

logger = logging.getLogger(__name__)

# Путь к data.json
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA_PATH = os.path.join(BASE_DIR, "data.json")

def extract_event_date(text: Optional[str], reference_date: Optional[datetime] = None) -> Optional[datetime]:
    """
    Экстрактор дат из текста. 
    Поддерживает цифровые форматы (ДД.ММ, ДД.ММ.ГГГГ) 
    и текстовые (15 октября, 25 мая 2026).
    """
    if not text:
        return None
        
    ref_dt = reference_date or datetime.now()
    current_year = ref_dt.year
    
    # Поиск числовых дат (например, 25.10.2026 или 25.10)
    num_match = re.search(r'\b(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?\b', text)
    if num_match:
        day_str, month_str, year_str = num_match.groups()
        try:
            day = int(day_str)
            month = int(month_str)
            has_explicit_year = bool(year_str)
            if year_str:
                year = int(year_str)
                if year < 100:
                    year += 2000
            else:
                year = current_year
            
            dt = datetime(year, month, day)
            # Корректировка года при переходе через Новый Год (например, анонс в декабре на январь)
            if not has_explicit_year and dt.date() < ref_dt.date() and (ref_dt.month - month) >= 6:
                dt = datetime(year + 1, month, day)
            return dt
        except ValueError:
            pass # Если попалась некорректная дата, игнорируем

    # Поиск текстовых дат (например, 15 октября 2026 или 5 мая)
    months = {
        "января": 1, "январь": 1, "февраля": 2, "февраль": 2,
        "марта": 3, "март": 3, "апреля": 4, "апрель": 4,
        "мая": 5, "май": 5, "июня": 6, "июнь": 6,
        "июля": 7, "июль": 7, "августа": 8, "август": 8,
        "сентября": 9, "сентябрь": 9, "октября": 10, "октябрь": 10,
        "ноября": 11, "ноябрь": 11, "декабря": 12, "декабрь": 12
    }
    
    # Собираем все месяцы в одно регулярное выражение
    month_pattern = "|".join(months.keys())
    
    # Ищет: число + месяц + (опционально слова "года/г.") + (опционально 4 цифры года)
    text_match = re.search(
        rf'(?i)\b(\d{{1,2}})\s+({month_pattern})(?:\s+(?:года|г\.|г)?\s*)?(\d{{4}})?\b', 
        text
    )
    
    if text_match:
        day_str, month_word, year_str = text_match.groups()
        month_num = months[month_word.lower()]
        try:
            day = int(day_str)
            has_explicit_year = bool(year_str)
            year = int(year_str) if year_str else current_year
            dt = datetime(year, month_num, day)
            
            # Корректировка года при переходе через Новый Год
            if not has_explicit_year and dt.date() < ref_dt.date() and (ref_dt.month - month_num) >= 6:
                dt = datetime(year + 1, month_num, day)
            return dt
        except ValueError:
            pass

    return None


class HeuristicAnalyzer:

    def __init__(self, data_path: str = DEFAULT_DATA_PATH) -> None:
        self.data_path = data_path
        self.categories_data: dict[str, dict[str, int]] = {}
        self.locations_data: dict[str, dict] = {}
        self.event_filter_data: dict[str, Any] = {}
        self._compiled_categories: dict[str, list[tuple[re.Pattern, int]]] = {}
        self._compiled_past_keywords: list[tuple[re.Pattern, int]] = []
        self._compiled_invitation_keywords: list[tuple[re.Pattern, int]] = []

        # Загрузка JSON и сборка RegEx 1 раз при старте
        self._load_data()
        self._compile_patterns()

    def _load_data(self) -> None:
        # Чтение json
        if not os.path.exists(self.data_path):
            logger.error("Файл data.json не найден: %s", self.data_path)
            return

        try:
            with open(self.data_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.categories_data = data.get("categories", {})
                self.locations_data = data.get("locations", {})
                self.event_filter_data = data.get("event_filter", {})
        except Exception as e:
            logger.error("Ошибка чтения %s: %s", self.data_path, e)

    def _compile_phrase_pattern(self, phrase: str) -> re.Pattern:
        # Вспомогательный метод для гибкой компиляции многословных фраз со словоизменениями
        parts = re.split(r'[\s\-]+', phrase.strip().lower().replace('ё', 'е'))
        escaped_parts = [rf"{re.escape(p)}\w*" for p in parts if p]
        pattern_str = r"\b" + r"[\s\-]+".join(escaped_parts)
        return re.compile(pattern_str, re.IGNORECASE)

    def _compile_patterns(self) -> None:
        # Компиляция стем и подготовка к проверкам (категории)
        for category, keywords in self.categories_data.items():
            compiled_list = []
            for keyword, weight in keywords.items():
                pattern = self._compile_phrase_pattern(keyword)
                compiled_list.append((pattern, weight))
            self._compiled_categories[category] = compiled_list

        # Компиляция маркеров прошедших событий и новостей
        past_dict = self.event_filter_data.get("past_or_news_keywords", {})
        for kw, weight in past_dict.items():
            pattern = self._compile_phrase_pattern(kw)
            self._compiled_past_keywords.append((pattern, weight))

        # Компиляция маркеров призывов к участию
        inv_dict = self.event_filter_data.get("invitation_keywords", {})
        for kw, weight in inv_dict.items():
            pattern = self._compile_phrase_pattern(kw)
            self._compiled_invitation_keywords.append((pattern, weight))

    def _clean(self, text: Optional[str]) -> str:
        # Очистка текста от спецсимволов
        if not text:
            return ""
        text = text.lower().replace("ё", "е")
        text = re.sub(r"[^\w\s\-]", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def is_future_event(self, text: Optional[str]) -> Tuple[bool, str, Optional[datetime]]:
        """
        Проверка, является ли текст анонсом будущего мероприятия.
        Отсеивает новости, отчеты и прошедшие события.
        """
        if not text:
            return False, "Пустой текст", None

        event_date = extract_event_date(text)
        now_date = datetime.now().date()

        # Если дата извлечена и она меньше текущей — событие прошло
        if event_date and event_date.date() < now_date:
            return False, f"Дата мероприятия ({event_date.strftime('%Y-%m-%d')}) уже прошла", event_date

        cleaned_text = self._clean(text)

        # Подсчет баллов маркеров прошедшего времени / новостей
        past_score = 0
        for pattern, weight in self._compiled_past_keywords:
            if pattern.search(cleaned_text):
                past_score += weight

        # Подсчет баллов призывов к участию
        invitation_score = 0
        for pattern, weight in self._compiled_invitation_keywords:
            if pattern.search(cleaned_text):
                invitation_score += weight

        # Проверка ссылок на формы регистрации
        has_reg_link = False
        text_lower = text.lower()
        domains = self.event_filter_data.get("registration_domains", [])
        for domain in domains:
            if domain in text_lower:
                has_reg_link = True
                invitation_score += 4
                break

        # Если набралось много "прошедших" слов и нет регистраций — отбрасываем как новость/мусор
        if past_score >= 4 and invitation_score < 3:
            return False, "Текст определен как новость/отчет о прошедшем событии", event_date

        # Если есть дата в будущем
        if event_date and event_date.date() >= now_date:
            return True, "Найдена дата в будущем", event_date

        # Если есть призывы или форма регистрации
        if invitation_score >= 3 or has_reg_link:
            return True, "Найден призыв к участию/регистрация", event_date

        return False, "Отсутствуют маркеры анонса будущей активности", event_date

    def analyze_topic(self, text: Optional[str]) -> Optional[str]:
        # Определение категории
        cleaned = self._clean(text)
        if not cleaned or not self._compiled_categories:
            return None

        # подсчитывает баллы
        scores = {cat: 0 for cat in self._compiled_categories}
        for category, patterns in self._compiled_categories.items():
            for pattern, weight in patterns:
                if pattern.search(cleaned):
                    scores[category] += weight

        if not scores or max(scores.values()) == 0:
            return None

        # Возвращает категорию набравшую наибольшее кол-во балов
        best = max(scores, key=scores.get)

        return best

    def analyze(self, text: Optional[str]) -> Optional[str]:
        # Алиас для обратной совместимости
        return self.analyze_topic(text)

    def extract_location_text(self, text: Optional[str]) -> Optional[str]:
        # Извлекает место
        if not text:
            return None

        loc_match = re.search(
            r'(?:Где|Место|Локация|Адрес|Место проведения):\s*([^\n]+)', 
            text, 
            re.IGNORECASE
        )
        if loc_match:
            return loc_match.group(1).strip(" *_`\t\r")

        return None

    def detect_location(self, text: Optional[str]) -> dict:
        # Поиск региона и города + проверка гео-конфликта
        cleaned = self._clean(text)
        if not cleaned:
            return {"region": None, "city": None, "conflict": False, "error_msg": None, "venue": None}

        found_region = None
        found_city = None
        found_city_real_region = None

        for region_name, reg_data in self.locations_data.items():
            # Поиск региона
            for r_stem in reg_data.get("stems", []):
                if re.search(rf"\b{re.escape(r_stem)}\w*", cleaned, re.IGNORECASE):
                    found_region = region_name
                    break

            # Поиск города
            for city_name, city_stems in reg_data.get("cities", {}).items():
                for c_stem in city_stems:
                    if re.search(rf"\b{re.escape(c_stem)}\w*", cleaned, re.IGNORECASE):
                        found_city = city_name
                        found_city_real_region = region_name
                        break

        # Универсальный поиск конкретного места
        venue = self.extract_location_text(text)

        # Проверка нестыковки региона и города
        if found_region and found_city and (found_region != found_city_real_region):
            return {
                "region": found_region,
                "city": found_city,
                "conflict": True,
                "venue": venue,
                "error_msg": (
                    f"Город **{found_city}** относится к региону «{found_city_real_region}», "
                    f"а не к «{found_region}». Уточните запрос."
                )
            }

        # Привязка региона к городу, если указан только город
        if found_city and not found_region:
            found_region = found_city_real_region

        return {
            "region": found_region,
            "city": found_city,
            "conflict": False,
            "venue": venue,
            "error_msg": None
        }

    def analyze_message(self, text: Optional[str]) -> Dict[str, Any]:
        """
        Полный анализ сообщения. Если текст — новость или мусор, 
        возвращает is_event=False для отсечения лишнего.
        """
        is_event, reason, event_date = self.is_future_event(text)

        if not is_event:
            return {
                "is_event": False,
                "reason": reason,
                "category": None,
                "location": None,
                "date": None
            }

        category = self.analyze_topic(text)
        location_info = self.detect_location(text)

        return {
            "is_event": True,
            "reason": reason,
            "category": category,
            "location": location_info,
            "date": event_date.strftime("%Y-%m-%d") if event_date else None
        }


analyzer = HeuristicAnalyzer()