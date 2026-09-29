import json
import logging
import os
import re
from datetime import datetime
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA_PATH = os.path.join(BASE_DIR, "data.json")


def extract_event_date(text: Optional[str], reference_date: Optional[datetime] = None) -> Optional[datetime]:
    if not text:
        return None
        
    ref_dt = reference_date or datetime.now()
    current_year = ref_dt.year
    found_dates = []

    # 1. Поиск всех числовых дат (например, 25.10.2026 или 25.10)
    for num_match in re.finditer(r'\b(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?\b', text):
        day_str, month_str, year_str = num_match.groups()
        try:
            day, month = int(day_str), int(month_str)
            has_explicit_year = bool(year_str)
            if year_str:
                year = int(year_str)
                if year < 100:
                    year += 2000
            else:
                year = current_year
            
            dt = datetime(year, month, day)
            if not has_explicit_year and dt.date() < ref_dt.date() and (ref_dt.month - month) >= 6:
                dt = datetime(year + 1, month, day)
            found_dates.append(dt)
        except ValueError:
            pass

    # 2. Поиск всех текстовых дат (например, 25 октября 2026 или 25 октября)
    months = {
        "января": 1, "январь": 1, "февраля": 2, "февраль": 2,
        "марта": 3, "март": 3, "апреля": 4, "апрель": 4,
        "мая": 5, "май": 5, "июня": 6, "июнь": 6,
        "июля": 7, "июль": 7, "августа": 8, "август": 8,
        "сентября": 9, "сентябрь": 9, "октября": 10, "октябрь": 10,
        "ноября": 11, "ноябрь": 11, "декабря": 12, "декабрь": 12
    }
    
    month_pattern = "|".join(months.keys())
    text_pattern = rf'(?i)\b(\d{{1,2}})\s+({month_pattern})(?:\s+(?:года|г\.|г)?\s*)?(\d{{4}})?\b'
    
    for text_match in re.finditer(text_pattern, text):
        day_str, month_word, year_str = text_match.groups()
        month_num = months[month_word.lower()]
        try:
            day = int(day_str)
            has_explicit_year = bool(year_str)
            year = int(year_str) if year_str else current_year
            dt = datetime(year, month_num, day)
            
            if not has_explicit_year and dt.date() < ref_dt.date() and (ref_dt.month - month_num) >= 6:
                dt = datetime(year + 1, month_num, day)
            found_dates.append(dt)
        except ValueError:
            pass

    if not found_dates:
        return None

    # Приоритет отдается ближайшей будущей дате
    future_dates = [d for d in found_dates if d.date() >= ref_dt.date()]
    if future_dates:
        return min(future_dates, key=lambda d: d.date() - ref_dt.date())
    
    # Если будущих дат нет, возвращаем самую последнюю дату
    return max(found_dates)


class HeuristicAnalyzer:

    def __init__(self, data_path: str = DEFAULT_DATA_PATH) -> None:
        self.data_path = data_path
        self.categories_data: dict[str, dict[str, int]] = {}
        self.locations_data: dict[str, dict] = {}
        self.event_filter_data: dict[str, Any] = {}
        self._compiled_categories: dict[str, list[tuple[re.Pattern, int]]] = {}
        self._compiled_past_keywords: list[tuple[re.Pattern, int]] = []
        self._compiled_invitation_keywords: list[tuple[re.Pattern, int]] = []
        self._compiled_noise_keywords: list[tuple[re.Pattern, int]] = []

        self._load_data()
        self._compile_patterns()

    def _load_data(self) -> None:
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

    def _clean(self, text: Optional[str]) -> str:
        if not text:
            return ""
        text = text.lower().replace("ё", "е")
        text = re.sub(r"[^\w\s\-]", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def _compile_phrase_pattern(self, phrase: str) -> re.Pattern:
        # Предварительно очищаем ключевую фразу аналогично _clean
        cleaned_phrase = self._clean(phrase)
        parts = cleaned_phrase.split()
        if not parts:
            return re.compile(r"$^")
            
        escaped_parts = [rf"{re.escape(p)}\w*" for p in parts]
        pattern_str = r"\b" + r"[\s\-]+".join(escaped_parts)
        return re.compile(pattern_str, re.IGNORECASE)

    def _compile_patterns(self) -> None:
        # Категории
        for category, keywords in self.categories_data.items():
            compiled_list = []
            for keyword, weight in keywords.items():
                pattern = self._compile_phrase_pattern(keyword)
                compiled_list.append((pattern, weight))
            self._compiled_categories[category] = compiled_list

        # Маркеры прошедших событий
        past_dict = self.event_filter_data.get("past_or_news_keywords", {})
        for kw, weight in past_dict.items():
            pattern = self._compile_phrase_pattern(kw)
            self._compiled_past_keywords.append((pattern, weight))

        # Маркеры призывов к участию
        inv_dict = self.event_filter_data.get("invitation_keywords", {})
        for kw, weight in inv_dict.items():
            pattern = self._compile_phrase_pattern(kw)
            self._compiled_invitation_keywords.append((pattern, weight))

        # Маркеры шума (онлайн-челленджи, поздравления)
        noise_dict = self.event_filter_data.get("noise_keywords", {})
        for kw, weight in noise_dict.items():
            pattern = self._compile_phrase_pattern(kw)
            self._compiled_noise_keywords.append((pattern, weight))

    def is_future_event(self, text: Optional[str]) -> Tuple[bool, str, Optional[datetime]]:
        if not text:
            return False, "Пустой текст", None

        event_date = extract_event_date(text)
        now_date = datetime.now().date()
        cleaned_text = self._clean(text)

        # Подсчет баллов
        past_score = sum(w for p, w in self._compiled_past_keywords if p.search(cleaned_text))
        invitation_score = sum(w for p, w in self._compiled_invitation_keywords if p.search(cleaned_text))
        noise_score = sum(w for p, w in self._compiled_noise_keywords if p.search(cleaned_text))

        # Проверка ссылок на формы
        has_reg_link = False
        text_lower = text.lower()
        domains = self.event_filter_data.get("registration_domains", [])
        for domain in domains:
            if domain in text_lower:
                has_reg_link = True
                invitation_score += 4
                break

        # 1. Если пост определен как явный отчет прошлых лет (высокий past_score, нет формы и призывов)
        if past_score >= 5 and invitation_score < 3 and not has_reg_link:
            return False, "Текст определен как отчет о прошедшем событии", event_date

        # 2. Если единственная или актуальная найденная дата прошла
        if event_date and event_date.date() < now_date:
            return False, f"Дата мероприятия ({event_date.strftime('%Y-%m-%d')}) уже прошла", event_date

        # 3. Онлайн-акция, поздравление, флешмоб без формы регистрации и без конкретной будущей даты
        if noise_score >= 5 and invitation_score < 3 and not has_reg_link and not (event_date and event_date.date() >= now_date):
            return False, "Текст определен как инфошум/онлайн-акция/поздравление", event_date

        # 4. Есть дата в будущем
        if event_date and event_date.date() >= now_date:
            return True, "Найдена дата в будущем", event_date

        # 5. Нет даты, но есть прямая ссылка на регистрацию
        if has_reg_link and invitation_score >= 3:
            return True, "Найдена форма регистрации на анонс", event_date

        # 6. Нет даты, но есть сильный призыв к участию при отсутствии шума и отчетов
        if invitation_score >= 5 and noise_score < 3 and past_score == 0:
            return True, "Найден четкий призыв к участию без даты", event_date

        return False, "Отсутствуют маркеры анонса будущей активности", event_date

    def analyze_topic(self, text: Optional[str]) -> Optional[str]:
        cleaned = self._clean(text)
        if not cleaned or not self._compiled_categories:
            return None

        scores = {cat: 0 for cat in self._compiled_categories}
        for category, patterns in self._compiled_categories.items():
            for pattern, weight in patterns:
                if pattern.search(cleaned):
                    scores[category] += weight

        if not scores or max(scores.values()) == 0:
            return None

        return max(scores, key=scores.get)

    def analyze(self, text: Optional[str]) -> Optional[str]:
        return self.analyze_topic(text)

    def extract_location_text(self, text: Optional[str]) -> Optional[str]:
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
        cleaned = self._clean(text)
        if not cleaned:
            return {"region": None, "city": None, "conflict": False, "error_msg": None, "venue": None}

        found_region = None
        found_city = None
        found_city_real_region = None

        def make_stem_pattern(stem: str) -> re.Pattern:
            stem_clean = self._clean(stem)
            if not stem_clean:
                return re.compile(r"$^")
            # Для коротких основ (до 3 символов) требуем точную границу слова
            if len(stem_clean) <= 3:
                return re.compile(rf"\b{re.escape(stem_clean)}\b", re.IGNORECASE)
            return re.compile(rf"\b{re.escape(stem_clean)}\w*", re.IGNORECASE)

        for region_name, reg_data in self.locations_data.items():
            for r_stem in reg_data.get("stems", []):
                pattern = make_stem_pattern(r_stem)
                if pattern.search(cleaned):
                    found_region = region_name
                    break

            for city_name, city_stems in reg_data.get("cities", {}).items():
                for c_stem in city_stems:
                    pattern = make_stem_pattern(c_stem)
                    if pattern.search(cleaned):
                        found_city = city_name
                        found_city_real_region = region_name
                        break

        venue = self.extract_location_text(text)

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