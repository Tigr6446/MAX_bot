"""
Эвристический анализатор текста сообщений.
Определяет категорию: volunteering / forum / science / sport / culture / workshop / pushkin_card а также регион и город
"""
import json
import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

#Путь к data.json
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA_PATH = os.path.join(BASE_DIR, "data.json")


class HeuristicAnalyzer:

    def __init__(self, data_path: str = DEFAULT_DATA_PATH) -> None:
        self.data_path = data_path
        self.categories_data: dict[str, dict[str, int]] = {}
        self.locations_data: dict[str, dict] = {}
        self._compiled_categories: dict[str, list[tuple[re.Pattern, int]]] = {}

        # Загрузка JSON и сборка RegEx 1 раз при старте
        self._load_data()
        self._compile_categories()

    def _load_data(self) -> None:
        #Чтение json
        if not os.path.exists(self.data_path):
            logger.error("Файл data.json не найден: %s", self.data_path)
            return

        try:
            with open(self.data_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.categories_data = data.get("categories", {})
                self.locations_data = data.get("locations", {})
        except Exception as e:
            logger.error("Ошибка чтения %s: %s", self.data_path, e)

    def _compile_categories(self) -> None:
        #Компиляция стем и подготовка к проверкам
        for category, keywords in self.categories_data.items():
            compiled_list = []
            for keyword, weight in keywords.items():
                parts = keyword.split()
                escaped_parts = [rf"{re.escape(p)}\w*" for p in parts]
                pattern_str = r"\b" + r"\s+".join(escaped_parts)
                compiled_list.append((re.compile(pattern_str, re.IGNORECASE), weight))
            self._compiled_categories[category] = compiled_list

    def _clean(self, text: Optional[str]) -> str:
        #Очистка текста от спецсимволов
        if not text:
            return ""
        return re.sub(r"[^\w\s]", "", text.lower())

    def analyze_topic(self, text: Optional[str], min_score: int = 5) -> Optional[str]:
        #Определение категории
        cleaned = self._clean(text)
        if not cleaned:
            return None

        #подсчитывает баллы
        scores = {cat: 0 for cat in self._compiled_categories}
        for category, patterns in self._compiled_categories.items():
            for pattern, weight in patterns:
                if pattern.search(cleaned):
                    scores[category] += weight

        #Возвращает категорию набрашую наибольшее кол-во балов
        best = max(scores, key=scores.get)

        #ЕСЛИ БАЛОВ МЕНЬШЕ ПОРОГА - ИГНОРИМ
        if scores[best] < min_score:
            return None

        return best

    def analyze(self, text: Optional[str], min_score: int = 5) -> Optional[str]:
        #Алиас для обратной совместимости
        return self.analyze_topic(text, min_score=min_score)

    def detect_location(self, text: Optional[str]) -> dict:
        #Поиск региона и города + проверка гео-конфликта
        cleaned = self._clean(text)
        if not cleaned:
            return {"region": None, "city": None, "conflict": False, "error_msg": None}

        found_region = None
        found_city = None
        found_city_real_region = None

        for region_name, reg_data in self.locations_data.items():
            #Поиск региона
            for r_stem in reg_data.get("stems", []):
                if re.search(rf"\b{re.escape(r_stem)}\w*", cleaned, re.IGNORECASE):
                    found_region = region_name
                    break

            #Поиск города
            for city_name, city_stems in reg_data.get("cities", {}).items():
                for c_stem in city_stems:
                    if re.search(rf"\b{re.escape(c_stem)}\w*", cleaned, re.IGNORECASE):
                        found_city = city_name
                        found_city_real_region = region_name
                        break

        #Проверка нестыковки региона и города
        if found_region and found_city and (found_region != found_city_real_region):
            return {
                "region": found_region,
                "city": found_city,
                "conflict": True,
                "error_msg": (
                    f"Город **{found_city}** относится к региону «{found_city_real_region}», "
                    f"а не к «{found_region}». Уточните запрос."
                )
            }

        #Привязка региона к городу, если указан только город
        if found_city and not found_region:
            found_region = found_city_real_region

        return {
            "region": found_region,
            "city": found_city,
            "conflict": False,
            "error_msg": None
        }



analyzer = HeuristicAnalyzer()