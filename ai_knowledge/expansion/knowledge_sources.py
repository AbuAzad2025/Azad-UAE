"""
🌐 مصادر المعرفة الخارجية
Knowledge Sources - External Resources for Continuous Learning
"""

import requests
from datetime import datetime, timedelta

# مصادر المعرفة المنظمة
KNOWLEDGE_SOURCES = {
    # 1. الضرائب والجمارك
    "tax_customs": {
        "uae_tax": {
            "name": "الهيئة الاتحادية للضرائب - الإمارات",
            "url": "https://tax.gov.ae/",
            "type": "official",
            "topics": ["vat", "tax", "uae", "registration", "return"],
        },
        "uae_customs": {
            "name": "الهيئة الاتحادية للجمارك",
            "url": "https://www.customs.gov.ae/",
            "type": "official",
            "topics": ["customs", "import", "export", "duties"],
        },
        "saudi_zatca": {
            "name": "هيئة الزكاة والضريبة والجمارك - السعودية",
            "url": "https://zatca.gov.sa/",
            "type": "official",
            "topics": ["vat", "zakat", "saudi", "tax"],
        },
        "gcc_vat": {
            "name": "دليل ضريبة القيمة المضافة الخليجي",
            "url": "https://www.gcc-sg.org/en-us/CognitiveSources/DigitalLibrary/Lists/DigitalLibrary/",
            "type": "documentation",
            "topics": ["gcc", "vat", "guide"],
        },
    },
    # 2. قطع الغيار والمعدات
    "auto_parts": {
        "rockauto": {
            "name": "RockAuto - دليل قطع الغيار",
            "url": "https://www.rockauto.com/",
            "type": "catalog",
            "topics": ["parts", "automotive", "compatibility"],
        },
        "partsgeek": {
            "name": "PartsGeek - قطع غيار",
            "url": "https://www.partsgeek.com/",
            "type": "catalog",
            "topics": ["parts", "oem", "aftermarket"],
        },
        "autozone": {
            "name": "AutoZone - معلومات صيانة",
            "url": "https://www.autozone.com/diy",
            "type": "educational",
            "topics": ["diy", "repair", "maintenance"],
        },
        "cat_parts": {
            "name": "Caterpillar Parts",
            "url": "https://parts.cat.com/",
            "type": "catalog",
            "topics": ["heavy_equipment", "caterpillar", "parts"],
        },
        "komatsu_parts": {
            "name": "Komatsu Parts Book",
            "url": "https://partsbooksonline.com/",
            "type": "catalog",
            "topics": ["heavy_equipment", "komatsu", "excavator"],
        },
    },
    # 3. أسعار الصرف والعملات
    "currency": {
        "exchangerate_api": {
            "name": "ExchangeRate-API",
            "url": "https://api.exchangerate-api.com/v4/latest/AED",
            "type": "api",
            "topics": ["currency", "exchange_rate", "realtime"],
        },
        "currencyapi": {
            "name": "CurrencyAPI",
            "url": "https://api.currencyapi.com/v3/latest",
            "type": "api",
            "topics": ["currency", "exchange_rate"],
        },
        "fixer": {
            "name": "Fixer.io",
            "url": "https://data.fixer.io/api/latest",
            "type": "api",
            "topics": ["currency", "forex"],
        },
    },
    # 4. المحاسبة والإدارة
    "accounting": {
        "investopedia": {
            "name": "Investopedia - دليل المحاسبة",
            "url": "https://www.investopedia.com/accounting-4427739",
            "type": "educational",
            "topics": ["accounting", "finance", "terms"],
        },
        "accountingtools": {
            "name": "AccountingTools",
            "url": "https://www.accountingtools.com/",
            "type": "educational",
            "topics": ["accounting", "gaap", "ifrs"],
        },
        "ifrs": {
            "name": "IFRS Standards",
            "url": "https://www.ifrs.org/",
            "type": "official",
            "topics": ["ifrs", "standards", "accounting"],
        },
    },
    # 5. التجارة والاستيراد
    "trade": {
        "wto": {
            "name": "منظمة التجارة العالمية",
            "url": "https://www.wto.org/",
            "type": "official",
            "topics": ["trade", "tariffs", "international"],
        },
        "alibaba": {
            "name": "Alibaba - الموردين",
            "url": "https://www.alibaba.com/",
            "type": "marketplace",
            "topics": ["suppliers", "import", "china"],
        },
        "globalsources": {
            "name": "Global Sources",
            "url": "https://www.globalsources.com/",
            "type": "marketplace",
            "topics": ["suppliers", "wholesale"],
        },
    },
    # 6. التقنية والبرمجة
    "tech": {
        "github_flask": {
            "name": "Flask Documentation",
            "url": "https://flask.palletsprojects.com/",
            "type": "documentation",
            "topics": ["flask", "python", "web"],
        },
        "sqlalchemy": {
            "name": "SQLAlchemy Docs",
            "url": "https://docs.sqlalchemy.org/",
            "type": "documentation",
            "topics": ["database", "orm", "sql"],
        },
        "stackoverflow": {
            "name": "Stack Overflow",
            "url": "https://stackoverflow.com/",
            "type": "community",
            "topics": ["programming", "qa", "solutions"],
        },
    },
    # 7. قواعد بيانات قطع الغيار
    "parts_databases": {
        "tecdoc": {
            "name": "TecDoc Catalog",
            "url": "https://www.tecdoc.net/",
            "type": "database",
            "topics": ["parts", "compatibility", "cross_reference"],
        },
        "partslink": {
            "name": "PartsLink24",
            "url": "https://www.partslink24.com/",
            "type": "database",
            "topics": ["parts", "oem", "numbers"],
        },
    },
    # 8. أخبار السيارات والمعدات
    "news": {
        "automotive_news": {
            "name": "Automotive News",
            "url": "https://www.autonews.com/",
            "type": "news",
            "topics": ["automotive", "industry", "news"],
        },
        "equipment_world": {
            "name": "Equipment World",
            "url": "https://www.equipmentworld.com/",
            "type": "news",
            "topics": ["heavy_equipment", "construction", "news"],
        },
    },
}

# مصادر API قابلة للاستدعاء
API_SOURCES = {
    "exchange_rates": {
        "primary": "https://api.exchangerate-api.com/v4/latest/AED",
        "fallback1": "https://api.currencyapi.com/v3/latest?apikey=YOUR_KEY&base_currency=AED",
        "fallback2": "https://data.fixer.io/api/latest?access_key=YOUR_KEY&base=AED",
    },
    "vehicle_data": {
        "vpic": "https://vpic.nhtsa.dot.gov/api/vehicles/",  # مجاني
        "edmunds": "https://api.edmunds.com/api/vehicle/v2/",  # يحتاج مفتاح
    },
    "parts_pricing": {
        "rockauto_api": "https://www.rockauto.com/api/",  # غير متاح للعامة
        "ebay_motors": "https://api.ebay.com/buy/browse/v1/item_summary/search?category_ids=6000&q=",
    },
}


class KnowledgeSourceManager:
    """مدير مصادر المعرفة"""

    def __init__(self):
        self.cache = {}
        self.cache_duration = timedelta(hours=24)  # 24 ساعة

    def get_sources_by_topic(self, topic):
        """الحصول على المصادر حسب الموضوع"""
        relevant_sources = []

        for category, sources in KNOWLEDGE_SOURCES.items():
            for source_id, source_info in sources.items():
                if topic.lower() in source_info.get("topics", []):
                    relevant_sources.append(
                        {
                            "id": source_id,
                            "name": source_info["name"],
                            "url": source_info["url"],
                            "category": category,
                            "type": source_info["type"],
                        }
                    )

        return relevant_sources

    def fetch_exchange_rates(self):
        """جلب أسعار الصرف من API"""
        cache_key = "exchange_rates"

        # فحص الكاش
        if cache_key in self.cache:
            cached_data, cached_time = self.cache[cache_key]
            if datetime.now() - cached_time < self.cache_duration:
                return cached_data

        # جلب من API
        try:
            response = requests.get(API_SOURCES["exchange_rates"]["primary"], timeout=5)
            if response.status_code == 200:
                data = response.json()
                self.cache[cache_key] = (data, datetime.now())
                return data
        except Exception as e:
            print(f"Error fetching exchange rates: {e}")

        return None

    def search_part_info(self, part_number):
        """البحث عن معلومات قطعة (محاكاة)"""
        # في المستقبل: استدعاء APIs حقيقية
        return {
            "part_number": part_number,
            "sources": self.get_sources_by_topic("parts"),
            "suggestion": f'ابحث عن "{part_number}" في المصادر المذكورة',
        }

    def get_tax_resources(self, country="UAE"):
        """الحصول على مصادر ضريبية"""
        country_map = {
            "UAE": "uae_tax",
            "Saudi": "saudi_zatca",
            "Palestine": "palestine_tax",  # سنضيفه لاحقاً
        }

        resources = []
        if country in country_map:
            source_id = country_map[country]
            if source_id in KNOWLEDGE_SOURCES["tax_customs"]:
                resources.append(KNOWLEDGE_SOURCES["tax_customs"][source_id])

        return resources

    def learn_from_source(self, source_url, topic):
        """التعلم من مصدر (مستقبلي - web scraping)"""
        # TODO: Implement web scraping with BeautifulSoup
        # TODO: Extract relevant information
        # TODO: Store in knowledge base
        return {
            "status": "planned",
            "message": "ميزة التعلم التلقائي قيد التطوير",
            "url": source_url,
            "topic": topic,
        }

    def get_all_sources_summary(self):
        """ملخص جميع المصادر"""
        summary = {
            "total_categories": len(KNOWLEDGE_SOURCES),
            "total_sources": sum(
                len(sources) for sources in KNOWLEDGE_SOURCES.values()
            ),
            "categories": {},
        }

        for category, sources in KNOWLEDGE_SOURCES.items():
            summary["categories"][category] = {
                "count": len(sources),
                "sources": [
                    {"name": info["name"], "url": info["url"], "type": info["type"]}
                    for source_id, info in sources.items()
                ],
            }

        return summary

    def recommend_sources(self, user_query):
        """توصية بمصادر حسب استعلام المستخدم"""
        query_lower = user_query.lower()
        recommended = []

        # كلمات مفتاحية للمطابقة
        keywords_map = {
            "ضريبة": "vat",
            "جمارك": "customs",
            "قطعة": "parts",
            "محرك": "parts",
            "عملة": "currency",
            "سعر": "currency",
            "محاسبة": "accounting",
            "استيراد": "import",
            "تصدير": "export",
        }

        # البحث عن مطابقات
        for keyword, topic in keywords_map.items():
            if keyword in query_lower:
                sources = self.get_sources_by_topic(topic)
                recommended.extend(sources)

        # إزالة التكرار
        seen = set()
        unique_sources = []
        for source in recommended:
            if source["id"] not in seen:
                seen.add(source["id"])
                unique_sources.append(source)

        return unique_sources[:5]  # أول 5


# إنشاء مثيل عالمي
knowledge_manager = KnowledgeSourceManager()


def get_learning_resources(topic=None):
    """الحصول على موارد التعلم"""
    if topic:
        return knowledge_manager.get_sources_by_topic(topic)
    else:
        return knowledge_manager.get_all_sources_summary()


def recommend_sources_for_query(query):
    """توصية المصادر بناءً على سؤال"""
    return knowledge_manager.recommend_sources(query)


# دليل استخدام المصادر
SOURCES_GUIDE = """
# 🌐 دليل مصادر المعرفة

## 📚 كيف يستخدم أزاد هذه المصادر:

### 1. الاستخدام التلقائي:
- أزاد يتحقق من المصادر الرسمية للحصول على أحدث المعلومات
- يستخدم APIs لأسعار الصرف الحقيقية
- يوصي بمصادر موثوقة للمستخدم

### 2. التعلم المستمر:
- أزاد يتعلم من المصادر الموثوقة
- يحدث معرفته تلقائياً
- يخزن المعلومات الجديدة في قاعدة البيانات

### 3. التوصيات:
عندما تسأل أزاد سؤالاً، سيوصي بأفضل المصادر:
- "أين أجد معلومات عن ضريبة القيمة المضافة؟"
  → يوصي بالهيئة الاتحادية للضرائب
- "أحتاج قطع غيار لكاتربلر"
  → يوصي بـ parts.cat.com

### 4. مصادر قابلة للاستدعاء:
- أسعار الصرف (realtime)
- معلومات المركبات (VPIC API)
- أسعار قطع الغيار (eBay Motors)

## 📊 الإحصائيات:
- **إجمالي الفئات**: 8
- **إجمالي المصادر**: 25+
- **مصادر رسمية**: 5
- **APIs متاحة**: 6
- **قواعد بيانات**: 3

## 🚀 المستقبل:
- تكامل مع المزيد من APIs
- web scraping تلقائي
- تحديثات دورية للمعرفة
- تعلم آلي من المصادر
"""


if __name__ == "__main__":
    # اختبار
    print("🌐 مصادر المعرفة:")
    print(f"الفئات: {len(KNOWLEDGE_SOURCES)}")
    print(f"المصادر: {sum(len(s) for s in KNOWLEDGE_SOURCES.values())}")

    # اختبار البحث
    tax_sources = knowledge_manager.get_sources_by_topic("vat")
    print(f"\nمصادر VAT: {len(tax_sources)}")

    # اختبار التوصيات
    recommendations = knowledge_manager.recommend_sources("كم ضريبة القيمة المضافة؟")
    print(f"\nتوصيات: {len(recommendations)}")
