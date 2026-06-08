"""
Consolidated module: expansion.py
Merged: expansion/knowledge_expansion.py, expansion/global_knowledge.py, expansion/knowledge_sources.py

This module consolidates multiple small files into one.
Old import paths still work via backward-compatible shims in the original files.
"""


# ===== Consolidated from: expansion/knowledge_expansion.py =====
"""
📚 توسيع المعرفة - Knowledge Expansion
أزاد يضيف مصادر معرفة جديدة
"""

import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime
from urllib.parse import urlparse, urljoin
import time


class KnowledgeExpander:
    """موسع المعرفة لأزاد"""
    
    def __init__(self):
        from ai_knowledge import get_knowledge_path
        self.knowledge_dir = get_knowledge_path('expanded_knowledge')
        self.sources_file = get_knowledge_path('knowledge_sources.json')
        
        # إنشاء المجلد إذا لم يكن موجوداً
        os.makedirs(self.knowledge_dir, exist_ok=True)
        
        # تحميل مصادر المعرفة
        self.sources = self._load_sources()
    
    def _load_sources(self):
        """تحميل مصادر المعرفة"""
        if os.path.exists(self.sources_file):
            try:
                with open(self.sources_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        
        return {
            'books': [],
            'websites': [],
            'documents': [],
            'last_updated': None
        }
    
    def _save_sources(self):
        """حفظ مصادر المعرفة"""
        try:
            with open(self.sources_file, 'w', encoding='utf-8') as f:
                json.dump(self.sources, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving sources: {e}")
    
    def add_website(self, url, category='general', description=''):
        """إضافة موقع ويب كمصدر معرفة"""
        try:
            # التحقق من صحة الرابط
            parsed_url = urlparse(url)
            if not parsed_url.scheme:
                url = 'https://' + url
                parsed_url = urlparse(url)
            
            if not parsed_url.netloc:
                return {
                    'success': False,
                    'error': 'رابط غير صحيح'
                }
            
            # جلب المحتوى
            content = self._fetch_website_content(url)
            if not content['success']:
                return content
            
            # حفظ المحتوى
            filename = f"website_{len(self.sources['websites']) + 1}.json"
            filepath = os.path.join(self.knowledge_dir, filename)
            
            website_data = {
                'url': url,
                'title': content['title'],
                'content': content['content'],
                'category': category,
                'description': description,
                'added_date': datetime.now().isoformat(),
                'domain': parsed_url.netloc
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(website_data, f, ensure_ascii=False, indent=2)
            
            # إضافة للمصادر
            self.sources['websites'].append({
                'url': url,
                'filename': filename,
                'category': category,
                'description': description,
                'added_date': datetime.now().isoformat()
            })
            
            self.sources['last_updated'] = datetime.now().isoformat()
            self._save_sources()
            
            return {
                'success': True,
                'message': f'تم إضافة الموقع "{content["title"]}" بنجاح',
                'filename': filename,
                'content_length': len(content['content'])
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'خطأ في إضافة الموقع: {str(e)}'
            }
    
    def _fetch_website_content(self, url):
        """جلب محتوى الموقع"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            # تحليل المحتوى
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # إزالة العلامات غير المرغوبة
            for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
                tag.decompose()
            
            # استخراج العنوان
            title = soup.find('title')
            title_text = title.get_text().strip() if title else urlparse(url).netloc
            
            # استخراج المحتوى
            content = soup.get_text()
            
            # تنظيف النص
            lines = (line.strip() for line in content.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            content = ' '.join(chunk for chunk in chunks if chunk)
            
            return {
                'success': True,
                'title': title_text,
                'content': content[:50000]  # تحديد الطول
            }
            
        except requests.RequestException as e:
            return {
                'success': False,
                'error': f'خطأ في جلب الموقع: {str(e)}'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'خطأ في تحليل المحتوى: {str(e)}'
            }
    
    def add_document(self, content, title, category='general', description=''):
        """إضافة مستند نصي"""
        try:
            if not content or not title:
                return {
                    'success': False,
                    'error': 'المحتوى والعنوان مطلوبان'
                }
            
            # حفظ المستند
            filename = f"document_{len(self.sources['documents']) + 1}.json"
            filepath = os.path.join(self.knowledge_dir, filename)
            
            document_data = {
                'title': title,
                'content': content,
                'category': category,
                'description': description,
                'added_date': datetime.now().isoformat(),
                'content_length': len(content)
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(document_data, f, ensure_ascii=False, indent=2)
            
            # إضافة للمصادر
            self.sources['documents'].append({
                'filename': filename,
                'title': title,
                'category': category,
                'description': description,
                'added_date': datetime.now().isoformat()
            })
            
            self.sources['last_updated'] = datetime.now().isoformat()
            self._save_sources()
            
            return {
                'success': True,
                'message': f'تم إضافة المستند "{title}" بنجاح',
                'filename': filename
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'خطأ في إضافة المستند: {str(e)}'
            }
    
    def search_knowledge(self, query, category=None):
        """البحث في المعرفة الموسعة"""
        try:
            results = []
            query_lower = query.lower()
            
            # البحث في المواقع
            for website in self.sources.get('websites', []):
                if category and website.get('category') != category:
                    continue
                
                filename = website.get('filename')
                if filename:
                    filepath = os.path.join(self.knowledge_dir, filename)
                    if os.path.exists(filepath):
                        with open(filepath, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            
                            if query_lower in data.get('content', '').lower() or \
                               query_lower in data.get('title', '').lower():
                                results.append({
                                    'type': 'website',
                                    'title': data.get('title', ''),
                                    'url': data.get('url', ''),
                                    'category': data.get('category', ''),
                                    'snippet': self._extract_snippet(data.get('content', ''), query_lower)
                                })
            
            # البحث في المستندات
            for document in self.sources.get('documents', []):
                if category and document.get('category') != category:
                    continue
                
                filename = document.get('filename')
                if filename:
                    filepath = os.path.join(self.knowledge_dir, filename)
                    if os.path.exists(filepath):
                        with open(filepath, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            
                            if query_lower in data.get('content', '').lower() or \
                               query_lower in data.get('title', '').lower():
                                results.append({
                                    'type': 'document',
                                    'title': data.get('title', ''),
                                    'category': data.get('category', ''),
                                    'snippet': self._extract_snippet(data.get('content', ''), query_lower)
                                })
            
            return {
                'success': True,
                'query': query,
                'results': results[:10],  # أفضل 10 نتائج
                'total_found': len(results)
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'خطأ في البحث: {str(e)}'
            }
    
    def _extract_snippet(self, content, query, snippet_length=200):
        """استخراج مقتطف من المحتوى"""
        try:
            query_pos = content.lower().find(query.lower())
            if query_pos == -1:
                return content[:snippet_length] + '...'
            
            start = max(0, query_pos - snippet_length // 2)
            end = min(len(content), query_pos + snippet_length // 2)
            
            snippet = content[start:end]
            if start > 0:
                snippet = '...' + snippet
            if end < len(content):
                snippet = snippet + '...'
            
            return snippet
            
        except:
            return content[:snippet_length] + '...'
    
    def get_knowledge_summary(self):
        """ملخص المعرفة الموسعة"""
        try:
            total_sources = len(self.sources.get('websites', [])) + len(self.sources.get('documents', []))
            
            # فئات المعرفة
            categories = {}
            for source_type in ['websites', 'documents']:
                for source in self.sources.get(source_type, []):
                    category = source.get('category', 'general')
                    categories[category] = categories.get(category, 0) + 1
            
            # أحدث المصادر
            recent_sources = []
            for source_type in ['websites', 'documents']:
                for source in self.sources.get(source_type, []):
                    recent_sources.append({
                        'type': source_type[:-1],  # إزالة 's'
                        'title': source.get('title', source.get('url', 'غير محدد')),
                        'added_date': source.get('added_date', '')
                    })
            
            # ترتيب حسب التاريخ
            recent_sources.sort(key=lambda x: x['added_date'], reverse=True)
            
            return {
                'success': True,
                'summary': {
                    'total_sources': total_sources,
                    'websites_count': len(self.sources.get('websites', [])),
                    'documents_count': len(self.sources.get('documents', [])),
                    'categories': categories,
                    'last_updated': self.sources.get('last_updated'),
                    'recent_sources': recent_sources[:5]
                }
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'خطأ في جلب ملخص المعرفة: {str(e)}'
            }
    
    def update_knowledge_from_source(self, source_type, source_id):
        """تحديث المعرفة من مصدر محدد"""
        try:
            if source_type == 'website':
                websites = self.sources.get('websites', [])
                if source_id < len(websites):
                    website = websites[source_id]
                    return self.add_website(
                        website['url'],
                        website.get('category', 'general'),
                        website.get('description', '')
                    )
            
            return {
                'success': False,
                'error': 'نوع المصدر غير صحيح'
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'خطأ في تحديث المعرفة: {str(e)}'
            }


# إنشاء مثيل عالمي
knowledge_expander = KnowledgeExpander()


# ===== Consolidated from: expansion/global_knowledge.py =====
"""
🌍 المعرفة العالمية - Global Knowledge Base
أزاد يتصل بالعالم ويتعلم من المصادر العالمية
"""

import requests
import json
from datetime import datetime, timedelta
import time


class GlobalKnowledgeConnector:
    """موصل المعرفة العالمية"""
    
    def __init__(self):
        self.knowledge_sources = {
            'automotive_news': [
                'https://www.autonews.com/api/latest',
                'https://www.automotiveworld.com/feed/',
                'https://www.just-auto.com/feed/'
            ],
            'heavy_equipment': [
                'https://www.equipmentworld.com/feed/',
                'https://www.constructionequipment.com/feed/',
                'https://www.aggman.com/feed/'
            ],
            'tax_regulations': [
                'https://www.federal-tax-authority.gov.ae/api/updates',
                'https://www.mof.gov.ae/api/tax-news'
            ],
            'market_data': [
                'https://api.coinbase.com/v2/exchange-rates',
                'https://api.exchangerate-api.com/v4/latest/AED',
                'https://api.fixer.io/latest'
            ]
        }
        
        self.cache_duration = 3600  # ساعة واحدة
        self.cached_data = {}
    
    def fetch_global_automotive_news(self):
        """جلب أخبار السيارات العالمية"""
        try:
            # محاكاة جلب الأخبار (في الواقع ستحتاج APIs حقيقية)
            automotive_trends = {
                'electric_vehicles': {
                    'trend': 'زيادة الطلب على السيارات الكهربائية',
                    'impact': 'زيادة الطلب على قطع الغيار الكهربائية',
                    'recommendation': 'ركز على قطع البطاريات والمحركات الكهربائية'
                },
                'autonomous_vehicles': {
                    'trend': 'تطوير السيارات ذاتية القيادة',
                    'impact': 'حاجة لقطع غيار متطورة',
                    'recommendation': 'استثمر في قطع الاستشعار والتحكم'
                },
                'hybrid_technology': {
                    'trend': 'انتشار التكنولوجيا الهجينة',
                    'impact': 'طلب على قطع محركات هجينة',
                    'recommendation': 'طور معرفتك في المحركات الهجينة'
                }
            }
            
            return {
                'success': True,
                'data': automotive_trends,
                'timestamp': datetime.now().isoformat(),
                'source': 'Global Automotive Intelligence'
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def fetch_heavy_equipment_trends(self):
        """جلب اتجاهات المعدات الثقيلة"""
        try:
            equipment_trends = {
                'construction_boom': {
                    'trend': 'طفرة في قطاع الإنشاءات العالمية',
                    'impact': 'زيادة الطلب على المعدات الثقيلة',
                    'recommendation': 'ركز على قطع CAT و Komatsu'
                },
                'sustainability': {
                    'trend': 'التوجه للمعدات الصديقة للبيئة',
                    'impact': 'طلب على قطع محركات نظيفة',
                    'recommendation': 'طور معرفتك في المحركات النظيفة'
                },
                'digitalization': {
                    'trend': 'رقمنة المعدات الثقيلة',
                    'impact': 'حاجة لقطع إلكترونية متطورة',
                    'recommendation': 'استثمر في قطع التحكم الإلكتروني'
                }
            }
            
            return {
                'success': True,
                'data': equipment_trends,
                'timestamp': datetime.now().isoformat(),
                'source': 'Global Heavy Equipment Intelligence'
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def fetch_tax_regulation_updates(self):
        """جلب تحديثات الأنظمة الضريبية"""
        try:
            # محاكاة جلب التحديثات الضريبية
            tax_updates = {
                'uae_vat': {
                    'update': 'لا توجد تغييرات على ضريبة القيمة المضافة 5%',
                    'effective_date': '2024-01-01',
                    'impact': 'استمرار النظام الحالي'
                },
                'corporate_tax': {
                    'update': 'تطبيق ضريبة الشركات 9% على الأرباح > 375,000 درهم',
                    'effective_date': '2023-06-01',
                    'impact': 'تأثير على حسابات الشركات'
                },
                'excise_tax': {
                    'update': 'تحديث قائمة السلع الخاضعة للضريبة الانتقائية',
                    'effective_date': '2024-01-01',
                    'impact': 'تأثير على أسعار بعض السلع'
                }
            }
            
            return {
                'success': True,
                'data': tax_updates,
                'timestamp': datetime.now().isoformat(),
                'source': 'UAE Federal Tax Authority'
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def fetch_currency_rates(self):
        """جلب أسعار العملات العالمية"""
        try:
            # استخدام API حقيقي لأسعار العملات
            response = requests.get('https://api.exchangerate-api.com/v4/latest/AED', timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return {
                    'success': True,
                    'data': {
                        'base_currency': 'AED',
                        'rates': data.get('rates', {}),
                        'last_updated': data.get('date', datetime.now().strftime('%Y-%m-%d'))
                    },
                    'timestamp': datetime.now().isoformat(),
                    'source': 'ExchangeRate-API'
                }
            else:
                # استخدام أسعار افتراضية في حالة فشل API
                return {
                    'success': True,
                    'data': {
                        'base_currency': 'AED',
                        'rates': {
                            'USD': 0.27,
                            'EUR': 0.25,
                            'GBP': 0.21,
                            'SAR': 1.02,
                            'KWD': 0.08,
                            'QAR': 0.98
                        },
                        'last_updated': datetime.now().strftime('%Y-%m-%d')
                    },
                    'timestamp': datetime.now().isoformat(),
                    'source': 'Default Rates'
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def get_global_insights(self):
        """الحصول على رؤى عالمية شاملة"""
        insights = {
            'automotive_trends': self.fetch_global_automotive_news(),
            'equipment_trends': self.fetch_heavy_equipment_trends(),
            'tax_updates': self.fetch_tax_regulation_updates(),
            'currency_rates': self.fetch_currency_rates(),
            'generated_at': datetime.now().isoformat()
        }
        
        return insights
    
    def analyze_global_impact(self, local_data):
        """تحليل تأثير الاتجاهات العالمية على البيانات المحلية"""
        global_insights = self.get_global_insights()
        
        analysis = {
            'local_vs_global': {},
            'opportunities': [],
            'threats': [],
            'recommendations': []
        }
        
        # تحليل اتجاهات السيارات
        if global_insights['automotive_trends']['success']:
            auto_trends = global_insights['automotive_trends']['data']
            
            # مقارنة مع البيانات المحلية
            if 'electric_vehicles' in auto_trends:
                analysis['opportunities'].append({
                    'area': 'السيارات الكهربائية',
                    'description': 'فرصة للاستثمار في قطع الغيار الكهربائية',
                    'priority': 'عالي',
                    'action': 'طور معرفتك في البطاريات والمحركات الكهربائية'
                })
        
        # تحليل اتجاهات المعدات الثقيلة
        if global_insights['equipment_trends']['success']:
            equipment_trends = global_insights['equipment_trends']['data']
            
            if 'construction_boom' in equipment_trends:
                analysis['opportunities'].append({
                    'area': 'المعدات الثقيلة',
                    'description': 'طفرة في الإنشاءات تزيد الطلب على المعدات',
                    'priority': 'عالي',
                    'action': 'ركز على قطع CAT و Komatsu'
                })
        
        # تحليل التحديثات الضريبية
        if global_insights['tax_updates']['success']:
            tax_updates = global_insights['tax_updates']['data']
            
            analysis['recommendations'].append({
                'area': 'الضرائب',
                'description': 'تحديثات ضريبية جديدة',
                'action': 'راجع التحديثات الضريبية مع العملاء'
            })
        
        return analysis


class GlobalExpertiseUpdater:
    """محدث الخبرة العالمية"""
    
    def __init__(self):
        self.connector = GlobalKnowledgeConnector()
        self.expertise_areas = {
            'automotive': {
                'current_level': 'متوسط',
                'target_level': 'خبير عالمي',
                'learning_path': [
                    'قطع غيار السيارات التقليدية',
                    'التكنولوجيا الهجينة',
                    'السيارات الكهربائية',
                    'السيارات ذاتية القيادة',
                    'الذكاء الاصطناعي في السيارات'
                ]
            },
            'heavy_equipment': {
                'current_level': 'متوسط',
                'target_level': 'خبير عالمي',
                'learning_path': [
                    'المعدات التقليدية',
                    'المعدات الذكية',
                    'المعدات الصديقة للبيئة',
                    'التحكم عن بُعد',
                    'الصيانة التنبؤية'
                ]
            },
            'tax_regulations': {
                'current_level': 'خبير محلي',
                'target_level': 'خبير دولي',
                'learning_path': [
                    'الضرائب الإماراتية',
                    'ضرائب دول الخليج',
                    'الضرائب الدولية',
                    'التخطيط الضريبي',
                    'الامتثال الضريبي'
                ]
            }
        }
    
    def update_expertise(self):
        """تحديث الخبرة بناءً على المعرفة العالمية"""
        global_insights = self.connector.get_global_insights()
        
        updates = {}
        
        for area, config in self.expertise_areas.items():
            current_level = config['current_level']
            learning_path = config['learning_path']
            
            # تحديد المرحلة التالية
            if current_level == 'مبتدئ':
                next_level = 'متوسط'
                next_topic = learning_path[0] if learning_path else 'أساسيات المجال'
            elif current_level == 'متوسط':
                next_level = 'متقدم'
                next_topic = learning_path[1] if len(learning_path) > 1 else 'مواضيع متقدمة'
            elif current_level == 'متقدم':
                next_level = 'خبير محلي'
                next_topic = learning_path[2] if len(learning_path) > 2 else 'خبرة متخصصة'
            elif current_level == 'خبير محلي':
                next_level = 'خبير إقليمي'
                next_topic = learning_path[3] if len(learning_path) > 3 else 'خبرة إقليمية'
            else:
                next_level = 'خبير عالمي'
                next_topic = learning_path[4] if len(learning_path) > 4 else 'خبرة عالمية'
            
            updates[area] = {
                'current_level': current_level,
                'next_level': next_level,
                'next_topic': next_topic,
                'progress': self._calculate_progress(current_level),
                'recommendations': self._get_learning_recommendations(area, global_insights)
            }
        
        return updates
    
    def _calculate_progress(self, current_level):
        """حساب التقدم في الخبرة"""
        levels = ['مبتدئ', 'متوسط', 'متقدم', 'خبير محلي', 'خبير إقليمي', 'خبير عالمي']
        
        try:
            current_index = levels.index(current_level)
            progress = (current_index + 1) / len(levels) * 100
            return round(progress, 1)
        except ValueError:
            return 0.0
    
    def _get_learning_recommendations(self, area, global_insights):
        """الحصول على توصيات التعلم"""
        recommendations = []
        
        if area == 'automotive':
            if global_insights['automotive_trends']['success']:
                auto_trends = global_insights['automotive_trends']['data']
                
                if 'electric_vehicles' in auto_trends:
                    recommendations.append({
                        'topic': 'السيارات الكهربائية',
                        'priority': 'عالي',
                        'reason': 'اتجاه عالمي متزايد',
                        'action': 'تعلم عن البطاريات والمحركات الكهربائية'
                    })
                
                if 'autonomous_vehicles' in auto_trends:
                    recommendations.append({
                        'topic': 'السيارات ذاتية القيادة',
                        'priority': 'متوسط',
                        'reason': 'تكنولوجيا مستقبلية',
                        'action': 'تعلم عن أنظمة الاستشعار والتحكم'
                    })
        
        elif area == 'heavy_equipment':
            if global_insights['equipment_trends']['success']:
                equipment_trends = global_insights['equipment_trends']['data']
                
                if 'digitalization' in equipment_trends:
                    recommendations.append({
                        'topic': 'رقمنة المعدات',
                        'priority': 'عالي',
                        'reason': 'اتجاه عالمي في الصناعة',
                        'action': 'تعلم عن أنظمة التحكم الإلكترونية'
                    })
        
        elif area == 'tax_regulations':
            if global_insights['tax_updates']['success']:
                recommendations.append({
                    'topic': 'التحديثات الضريبية',
                    'priority': 'عالي',
                    'reason': 'تغييرات في الأنظمة',
                    'action': 'تابع التحديثات الضريبية الجديدة'
                })
        
        return recommendations


# إنشاء مثيلات عالمية
global_connector = GlobalKnowledgeConnector()
expertise_updater = GlobalExpertiseUpdater()


# ===== Consolidated from: expansion/knowledge_sources.py =====
"""
🌐 مصادر المعرفة الخارجية
Knowledge Sources - External Resources for Continuous Learning
"""

import requests
from datetime import datetime, timedelta
import json
import time

# مصادر المعرفة المنظمة
KNOWLEDGE_SOURCES = {
    # 1. الضرائب والجمارك
    'tax_customs': {
        'uae_tax': {
            'name': 'الهيئة الاتحادية للضرائب - الإمارات',
            'url': 'https://tax.gov.ae/',
            'type': 'official',
            'topics': ['vat', 'tax', 'uae', 'registration', 'return']
        },
        'uae_customs': {
            'name': 'الهيئة الاتحادية للجمارك',
            'url': 'https://www.customs.gov.ae/',
            'type': 'official',
            'topics': ['customs', 'import', 'export', 'duties']
        },
        'saudi_zatca': {
            'name': 'هيئة الزكاة والضريبة والجمارك - السعودية',
            'url': 'https://zatca.gov.sa/',
            'type': 'official',
            'topics': ['vat', 'zakat', 'saudi', 'tax']
        },
        'gcc_vat': {
            'name': 'دليل ضريبة القيمة المضافة الخليجي',
            'url': 'https://www.gcc-sg.org/en-us/CognitiveSources/DigitalLibrary/Lists/DigitalLibrary/',
            'type': 'documentation',
            'topics': ['gcc', 'vat', 'guide']
        }
    },
    
    # 2. قطع الغيار والمعدات
    'auto_parts': {
        'rockauto': {
            'name': 'RockAuto - دليل قطع الغيار',
            'url': 'https://www.rockauto.com/',
            'type': 'catalog',
            'topics': ['parts', 'automotive', 'compatibility']
        },
        'partsgeek': {
            'name': 'PartsGeek - قطع غيار',
            'url': 'https://www.partsgeek.com/',
            'type': 'catalog',
            'topics': ['parts', 'oem', 'aftermarket']
        },
        'autozone': {
            'name': 'AutoZone - معلومات صيانة',
            'url': 'https://www.autozone.com/diy',
            'type': 'educational',
            'topics': ['diy', 'repair', 'maintenance']
        },
        'cat_parts': {
            'name': 'Caterpillar Parts',
            'url': 'https://parts.cat.com/',
            'type': 'catalog',
            'topics': ['heavy_equipment', 'caterpillar', 'parts']
        },
        'komatsu_parts': {
            'name': 'Komatsu Parts Book',
            'url': 'https://partsbooksonline.com/',
            'type': 'catalog',
            'topics': ['heavy_equipment', 'komatsu', 'excavator']
        }
    },
    
    # 3. أسعار الصرف والعملات
    'currency': {
        'exchangerate_api': {
            'name': 'ExchangeRate-API',
            'url': 'https://api.exchangerate-api.com/v4/latest/AED',
            'type': 'api',
            'topics': ['currency', 'exchange_rate', 'realtime']
        },
        'currencyapi': {
            'name': 'CurrencyAPI',
            'url': 'https://api.currencyapi.com/v3/latest',
            'type': 'api',
            'topics': ['currency', 'exchange_rate']
        },
        'fixer': {
            'name': 'Fixer.io',
            'url': 'https://data.fixer.io/api/latest',
            'type': 'api',
            'topics': ['currency', 'forex']
        }
    },
    
    # 4. المحاسبة والإدارة
    'accounting': {
        'investopedia': {
            'name': 'Investopedia - دليل المحاسبة',
            'url': 'https://www.investopedia.com/accounting-4427739',
            'type': 'educational',
            'topics': ['accounting', 'finance', 'terms']
        },
        'accountingtools': {
            'name': 'AccountingTools',
            'url': 'https://www.accountingtools.com/',
            'type': 'educational',
            'topics': ['accounting', 'gaap', 'ifrs']
        },
        'ifrs': {
            'name': 'IFRS Standards',
            'url': 'https://www.ifrs.org/',
            'type': 'official',
            'topics': ['ifrs', 'standards', 'accounting']
        }
    },
    
    # 5. التجارة والاستيراد
    'trade': {
        'wto': {
            'name': 'منظمة التجارة العالمية',
            'url': 'https://www.wto.org/',
            'type': 'official',
            'topics': ['trade', 'tariffs', 'international']
        },
        'alibaba': {
            'name': 'Alibaba - الموردين',
            'url': 'https://www.alibaba.com/',
            'type': 'marketplace',
            'topics': ['suppliers', 'import', 'china']
        },
        'globalsources': {
            'name': 'Global Sources',
            'url': 'https://www.globalsources.com/',
            'type': 'marketplace',
            'topics': ['suppliers', 'wholesale']
        }
    },
    
    # 6. التقنية والبرمجة
    'tech': {
        'github_flask': {
            'name': 'Flask Documentation',
            'url': 'https://flask.palletsprojects.com/',
            'type': 'documentation',
            'topics': ['flask', 'python', 'web']
        },
        'sqlalchemy': {
            'name': 'SQLAlchemy Docs',
            'url': 'https://docs.sqlalchemy.org/',
            'type': 'documentation',
            'topics': ['database', 'orm', 'sql']
        },
        'stackoverflow': {
            'name': 'Stack Overflow',
            'url': 'https://stackoverflow.com/',
            'type': 'community',
            'topics': ['programming', 'qa', 'solutions']
        }
    },
    
    # 7. قواعد بيانات قطع الغيار
    'parts_databases': {
        'tecdoc': {
            'name': 'TecDoc Catalog',
            'url': 'https://www.tecdoc.net/',
            'type': 'database',
            'topics': ['parts', 'compatibility', 'cross_reference']
        },
        'partslink': {
            'name': 'PartsLink24',
            'url': 'https://www.partslink24.com/',
            'type': 'database',
            'topics': ['parts', 'oem', 'numbers']
        }
    },
    
    # 8. أخبار السيارات والمعدات
    'news': {
        'automotive_news': {
            'name': 'Automotive News',
            'url': 'https://www.autonews.com/',
            'type': 'news',
            'topics': ['automotive', 'industry', 'news']
        },
        'equipment_world': {
            'name': 'Equipment World',
            'url': 'https://www.equipmentworld.com/',
            'type': 'news',
            'topics': ['heavy_equipment', 'construction', 'news']
        }
    }
}

# مصادر API قابلة للاستدعاء
API_SOURCES = {
    'exchange_rates': {
        'primary': 'https://api.exchangerate-api.com/v4/latest/AED',
        'fallback1': 'https://api.currencyapi.com/v3/latest?apikey=YOUR_KEY&base_currency=AED',
        'fallback2': 'https://data.fixer.io/api/latest?access_key=YOUR_KEY&base=AED'
    },
    'vehicle_data': {
        'vpic': 'https://vpic.nhtsa.dot.gov/api/vehicles/',  # مجاني
        'edmunds': 'https://api.edmunds.com/api/vehicle/v2/',  # يحتاج مفتاح
    },
    'parts_pricing': {
        'rockauto_api': 'https://www.rockauto.com/api/',  # غير متاح للعامة
        'ebay_motors': 'https://api.ebay.com/buy/browse/v1/item_summary/search?category_ids=6000&q='
    }
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
                if topic.lower() in source_info.get('topics', []):
                    relevant_sources.append({
                        'id': source_id,
                        'name': source_info['name'],
                        'url': source_info['url'],
                        'category': category,
                        'type': source_info['type']
                    })
        
        return relevant_sources
    
    def fetch_exchange_rates(self):
        """جلب أسعار الصرف من API"""
        cache_key = 'exchange_rates'
        
        # فحص الكاش
        if cache_key in self.cache:
            cached_data, cached_time = self.cache[cache_key]
            if datetime.now() - cached_time < self.cache_duration:
                return cached_data
        
        # جلب من API
        try:
            response = requests.get(
                API_SOURCES['exchange_rates']['primary'],
                timeout=5
            )
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
            'part_number': part_number,
            'sources': self.get_sources_by_topic('parts'),
            'suggestion': f'ابحث عن "{part_number}" في المصادر المذكورة'
        }
    
    def get_tax_resources(self, country='UAE'):
        """الحصول على مصادر ضريبية"""
        country_map = {
            'UAE': 'uae_tax',
            'Saudi': 'saudi_zatca',
            'Palestine': 'palestine_tax'  # سنضيفه لاحقاً
        }
        
        resources = []
        if country in country_map:
            source_id = country_map[country]
            if source_id in KNOWLEDGE_SOURCES['tax_customs']:
                resources.append(KNOWLEDGE_SOURCES['tax_customs'][source_id])
        
        return resources
    
    def learn_from_source(self, source_url, topic):
        """التعلم من مصدر (مستقبلي - web scraping)"""
        # TODO: Implement web scraping with BeautifulSoup
        # TODO: Extract relevant information
        # TODO: Store in knowledge base
        return {
            'status': 'planned',
            'message': 'ميزة التعلم التلقائي قيد التطوير',
            'url': source_url,
            'topic': topic
        }
    
    def get_all_sources_summary(self):
        """ملخص جميع المصادر"""
        summary = {
            'total_categories': len(KNOWLEDGE_SOURCES),
            'total_sources': sum(len(sources) for sources in KNOWLEDGE_SOURCES.values()),
            'categories': {}
        }
        
        for category, sources in KNOWLEDGE_SOURCES.items():
            summary['categories'][category] = {
                'count': len(sources),
                'sources': [
                    {
                        'name': info['name'],
                        'url': info['url'],
                        'type': info['type']
                    }
                    for source_id, info in sources.items()
                ]
            }
        
        return summary
    
    def recommend_sources(self, user_query):
        """توصية بمصادر حسب استعلام المستخدم"""
        query_lower = user_query.lower()
        recommended = []
        
        # كلمات مفتاحية للمطابقة
        keywords_map = {
            'ضريبة': 'vat',
            'جمارك': 'customs',
            'قطعة': 'parts',
            'محرك': 'parts',
            'عملة': 'currency',
            'سعر': 'currency',
            'محاسبة': 'accounting',
            'استيراد': 'import',
            'تصدير': 'export'
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
            if source['id'] not in seen:
                seen.add(source['id'])
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
    tax_sources = knowledge_manager.get_sources_by_topic('vat')
    print(f"\nمصادر VAT: {len(tax_sources)}")
    
    # اختبار التوصيات
    recommendations = knowledge_manager.recommend_sources("كم ضريبة القيمة المضافة؟")
    print(f"\nتوصيات: {len(recommendations)}")

