"""
📚 توسيع المعرفة - Knowledge Expansion
أزاد يضيف مصادر معرفة جديدة
"""

import requests
from bs4 import BeautifulSoup
import json
import logging
import os
from datetime import datetime
from urllib.parse import urlparse
from typing import Any

logger = logging.getLogger(__name__)


class KnowledgeExpander:
    """موسع المعرفة لأزاد"""

    def __init__(self) -> None:
        from ai_knowledge import get_knowledge_path

        self.knowledge_dir = get_knowledge_path("expanded_knowledge")
        self.sources_file = get_knowledge_path("knowledge_sources.json")

        # إنشاء المجلد إذا لم يكن موجوداً
        os.makedirs(self.knowledge_dir, exist_ok=True)

        # تحميل مصادر المعرفة
        self.sources: dict[str, Any] = self._load_sources()

    def _load_sources(self) -> dict[str, Any]:
        """تحميل مصادر المعرفة"""
        if os.path.exists(self.sources_file):
            try:
                with open(self.sources_file, "r", encoding="utf-8") as f:
                    result = json.load(f)
                    if isinstance(result, dict):
                        return result
            except (json.JSONDecodeError, OSError) as exc:
                logger.debug("Could not load knowledge sources: %s", exc)

        return {"books": [], "websites": [], "documents": [], "last_updated": None}

    def _save_sources(self):
        """حفظ مصادر المعرفة"""
        try:
            with open(self.sources_file, "w", encoding="utf-8") as f:
                json.dump(self.sources, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving sources: {e}")

    def add_website(self, url, category="general", description="") -> dict[str, Any]:
        """إضافة موقع ويب كمصدر معرفة"""
        try:
            # التحقق من صحة الرابط
            parsed_url = urlparse(url)
            if not parsed_url.scheme:
                url = "https://" + url
                parsed_url = urlparse(url)

            if not parsed_url.netloc:
                return {"success": False, "error": "رابط غير صحيح"}

            # جلب المحتوى
            content: dict[str, Any] = self._fetch_website_content(url)
            if not content["success"]:
                return content

            # حفظ المحتوى
            filename = f"website_{len(self.sources.get('websites') or []) + 1}.json"
            filepath = os.path.join(self.knowledge_dir, filename)

            website_data = {
                "url": url,
                "title": content["title"],
                "content": content["content"],
                "category": category,
                "description": description,
                "added_date": datetime.now().isoformat(),
                "domain": parsed_url.netloc,
            }

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(website_data, f, ensure_ascii=False, indent=2)

            # إضافة للمصادر
            self.sources["websites"].append(
                {  # type: ignore[union-attr]
                    "url": url,
                    "filename": filename,
                    "category": category,
                    "description": description,
                    "added_date": datetime.now().isoformat(),
                }
            )

            self.sources["last_updated"] = datetime.now().isoformat()
            self._save_sources()

            return {
                "success": True,
                "message": f'تم إضافة الموقع "{content["title"]}" بنجاح',
                "filename": filename,
                "content_length": len(content["content"]),
            }

        except Exception as e:
            return {"success": False, "error": f"خطأ في إضافة الموقع: {str(e)}"}

    def _fetch_website_content(self, url) -> dict[str, Any]:
        """جلب محتوى الموقع"""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }

            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            # تحليل المحتوى
            soup = BeautifulSoup(response.content, "html.parser")

            # إزالة العلامات غير المرغوبة
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()

            # استخراج العنوان
            title = soup.find("title")
            title_text = title.get_text().strip() if title else urlparse(url).netloc

            # استخراج المحتوى
            content = soup.get_text()

            # تنظيف النص
            lines = (line.strip() for line in content.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            content = " ".join(chunk for chunk in chunks if chunk)

            return {
                "success": True,
                "title": title_text,
                "content": content[:50000],  # تحديد الطول
            }

        except requests.RequestException as e:
            return {"success": False, "error": f"خطأ في جلب الموقع: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": f"خطأ في تحليل المحتوى: {str(e)}"}

    def add_document(self, content, title, category="general", description=""):
        """إضافة مستند نصي"""
        try:
            if not content or not title:
                return {"success": False, "error": "المحتوى والعنوان مطلوبان"}

            # حفظ المستند
            filename = f"document_{len(self.sources.get('documents') or []) + 1}.json"
            filepath = os.path.join(self.knowledge_dir, filename)

            document_data = {
                "title": title,
                "content": content,
                "category": category,
                "description": description,
                "added_date": datetime.now().isoformat(),
                "content_length": len(content),
            }

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(document_data, f, ensure_ascii=False, indent=2)

            # إضافة للمصادر
            self.sources["documents"].append(
                {  # type: ignore[union-attr]
                    "filename": filename,
                    "title": title,
                    "category": category,
                    "description": description,
                    "added_date": datetime.now().isoformat(),
                }
            )

            self.sources["last_updated"] = datetime.now().isoformat()
            self._save_sources()

            return {
                "success": True,
                "message": f'تم إضافة المستند "{title}" بنجاح',
                "filename": filename,
            }

        except Exception as e:
            return {"success": False, "error": f"خطأ في إضافة المستند: {str(e)}"}

    def search_knowledge(self, query, category=None):
        """البحث في المعرفة الموسعة"""
        try:
            results = []
            query_lower = query.lower()

            # البحث في المواقع
            for website in self.sources.get("websites", []):
                if category and website.get("category") != category:
                    continue

                filename = website.get("filename")
                if filename:
                    filepath = os.path.join(self.knowledge_dir, filename)
                    if os.path.exists(filepath):
                        with open(filepath, "r", encoding="utf-8") as f:
                            data = json.load(f)

                            if (
                                query_lower in data.get("content", "").lower()
                                or query_lower in data.get("title", "").lower()
                            ):
                                results.append(
                                    {
                                        "type": "website",
                                        "title": data.get("title", ""),
                                        "url": data.get("url", ""),
                                        "category": data.get("category", ""),
                                        "snippet": self._extract_snippet(
                                            data.get("content", ""), query_lower
                                        ),
                                    }
                                )

            # البحث في المستندات
            for document in self.sources.get("documents", []):
                if category and document.get("category") != category:
                    continue

                filename = document.get("filename")
                if filename:
                    filepath = os.path.join(self.knowledge_dir, filename)
                    if os.path.exists(filepath):
                        with open(filepath, "r", encoding="utf-8") as f:
                            data = json.load(f)

                            if (
                                query_lower in data.get("content", "").lower()
                                or query_lower in data.get("title", "").lower()
                            ):
                                results.append(
                                    {
                                        "type": "document",
                                        "title": data.get("title", ""),
                                        "category": data.get("category", ""),
                                        "snippet": self._extract_snippet(
                                            data.get("content", ""), query_lower
                                        ),
                                    }
                                )

            return {
                "success": True,
                "query": query,
                "results": results[:10],  # أفضل 10 نتائج
                "total_found": len(results),
            }

        except Exception as e:
            return {"success": False, "error": f"خطأ في البحث: {str(e)}"}

    def _extract_snippet(self, content, query, snippet_length=200):
        """استخراج مقتطف من المحتوى"""
        try:
            query_pos = content.lower().find(query.lower())
            if query_pos == -1:
                return content[:snippet_length] + "..."

            start = max(0, query_pos - snippet_length // 2)
            end = min(len(content), query_pos + snippet_length // 2)

            snippet = content[start:end]
            if start > 0:
                snippet = "..." + snippet
            if end < len(content):
                snippet = snippet + "..."

            return snippet

        except Exception:
            return content[:snippet_length] + "..."

    def get_knowledge_summary(self):
        """ملخص المعرفة الموسعة"""
        try:
            total_sources = len(self.sources.get("websites") or []) + len(
                self.sources.get("documents") or []
            )

            # فئات المعرفة
            categories = {}
            for source_type in ["websites", "documents"]:
                for source in self.sources.get(source_type) or []:
                    category = source.get("category", "general")
                    categories[category] = categories.get(category, 0) + 1

            # أحدث المصادر
            recent_sources = []
            for source_type in ["websites", "documents"]:
                for source in self.sources.get(source_type) or []:
                    recent_sources.append(
                        {
                            "type": source_type[:-1],  # إزالة 's'
                            "title": source.get("title", source.get("url", "غير محدد")),
                            "added_date": source.get("added_date", ""),
                        }
                    )

            # ترتيب حسب التاريخ
            recent_sources.sort(key=lambda x: x["added_date"], reverse=True)

            return {
                "success": True,
                "summary": {
                    "total_sources": total_sources,
                    "websites_count": len(self.sources.get("websites") or []),
                    "documents_count": len(self.sources.get("documents") or []),
                    "categories": categories,
                    "last_updated": self.sources.get("last_updated"),
                    "recent_sources": recent_sources[:5],
                },
            }

        except Exception as e:
            return {"success": False, "error": f"خطأ في جلب ملخص المعرفة: {str(e)}"}

    def update_knowledge_from_source(self, source_type, source_id):
        """تحديث المعرفة من مصدر محدد"""
        try:
            if source_type == "website":
                websites = self.sources.get("websites", [])
                if websites is not None and source_id < len(websites):
                    website = websites[source_id]
                    return self.add_website(
                        website["url"],  # type: ignore[index]
                        website.get("category", "general"),  # type: ignore[union-attr]
                        website.get("description", ""),  # type: ignore[union-attr]
                    )

            return {"success": False, "error": "نوع المصدر غير صحيح"}

        except Exception as e:
            return {"success": False, "error": f"خطأ في تحديث المعرفة: {str(e)}"}


# إنشاء مثيل عالمي
knowledge_expander = KnowledgeExpander()
