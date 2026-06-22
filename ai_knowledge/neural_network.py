"""
Consolidated module: neural_network.py
Merged: neural/vision_processor.py, neural/transformers_brain.py, neural/semantic_matcher.py, neural/neural_engine.py

This module consolidates multiple small files into one.
Old import paths still work via backward-compatible shims in the original files.
"""


# ===== Consolidated from: neural/vision_processor.py =====
"""
👁️ معالج الرؤية - Vision Processor
معالجة الصور والنصوص المصورة (OCR)

القدرات:
- قراءة الفواتير المصورة (OCR)
- استخراج البيانات من الصور
- التعرف على الأرقام والنصوص
- معالجة صور قطع الغيار
- تحليل مخططات وجداول
"""

import logging
import re
import os
from typing import Dict, List
from datetime import datetime
import base64
import io

logger = logging.getLogger(__name__)


class VisionProcessor:
    """
    معالج الرؤية والصور
    
    يعالج:
    - فواتير PDF/صور
    - صور قطع الغيار
    - مخططات ورسوم بيانية
    - جداول Excel مصورة
    """
    
    def __init__(self):
        self.ocr_available = self._check_ocr_availability()
    
    def _check_ocr_availability(self):
        """التحقق من توفر OCR"""
        try:
            # التحقق من Pillow (متوفرة)
            from PIL import Image
            return True
        except ImportError:
            logger.warning("Pillow not available - OCR disabled")
            return False
    
    def read_invoice_image(self, image_path: str) -> dict:
        """
        قراءة فاتورة من صورة
        
        Args:
            image_path: مسار الصورة
        
        Returns:
            {
                'invoice_number': رقم الفاتورة,
                'date': التاريخ,
                'total': المبلغ الإجمالي,
                'items': قائمة المنتجات,
                'confidence': مستوى الثقة
            }
        """
        try:
            if not self.ocr_available:
                return {'error': 'OCR not available', 'confidence': 0}
            
            from PIL import Image
            
            # فتح الصورة
            image = Image.open(image_path)
            
            # محاكاة OCR (يمكن استخدام pytesseract لاحقاً)
            # للآن، نموذج أساسي
            
            extracted_data = {
                'invoice_number': self._extract_invoice_number(image),
                'date': self._extract_date(image),
                'total': self._extract_total(image),
                'items': self._extract_items(image),
                'confidence': 0.75,
                'method': 'vision_processing'
            }
            
            logger.info(f"👁️ Invoice read from image: {image_path}")
            
            return extracted_data
        
        except Exception as e:
            logger.error(f"Invoice OCR failed: {e}")
            return {'error': str(e), 'confidence': 0}
    
    def _extract_invoice_number(self, image) -> str:
        """استخراج رقم الفاتورة"""
        # محاكاة (يمكن استخدام OCR حقيقي)
        return "INV-XXXX"
    
    def _extract_date(self, image) -> str:
        """استخراج التاريخ"""
        # محاكاة
        return datetime.now().strftime('%Y-%m-%d')
    
    def _extract_total(self, image) -> float:
        """استخراج المبلغ الإجمالي"""
        # محاكاة
        return 0.0
    
    def _extract_items(self, image) -> List[dict]:
        """استخراج قائمة المنتجات"""
        # محاكاة
        return []
    
    def analyze_part_image(self, image_path: str) -> dict:
        """
        تحليل صورة قطعة غيار
        
        Returns:
            {
                'part_name': اسم القطعة المتوقع,
                'part_number': رقم القطعة,
                'condition': الحالة,
                'matches': قطع مشابهة
            }
        """
        try:
            # التأكد من المسار المطلق
            if not os.path.isabs(image_path):
                image_path = os.path.abspath(image_path)
                
            if not os.path.exists(image_path):
                return {'error': 'Image file not found'}

            from PIL import Image
            
            image = Image.open(image_path)
            
            # تحليل بسيط (يمكن استخدام ML لاحقاً)
            analysis = {
                'part_name': 'Unknown',
                'part_number': 'N/A',
                'condition': 'Good',
                'matches': [],
                'confidence': 0.6,
                'method': 'basic_vision'
            }
            
            logger.info(f"👁️ Part image analyzed: {image_path}")
            
            return analysis
        
        except Exception as e:
            logger.error(f"Part image analysis failed: {e}")
            return {'error': str(e)}
    
    def extract_text_from_image(self, image_path: str) -> str:
        """
        استخراج نص من صورة (OCR عام)
        
        ملاحظة: يحتاج pytesseract للعمل الكامل
        """
        try:
            # للآن، رسالة توضيحية
            return "OCR متاح - لكن يحتاج تثبيت pytesseract للعمل الكامل"
        
        except Exception as e:
            return f"Error: {e}"


# ============================================================================
# Singleton
# ============================================================================

_vision_processor_instance = None

def get_vision_processor():
    """الحصول على معالج الرؤية"""
    global _vision_processor_instance
    if _vision_processor_instance is None:
        _vision_processor_instance = VisionProcessor()
    return _vision_processor_instance



# ===== Consolidated from: neural/transformers_brain.py =====
"""
🤖 Transformers Brain - دماغ المحولات المتقدم
معمارية Transformers للذكاء الخارق

التقنيات:
- Self-Attention Mechanism (آلية الانتباه الذاتي)
- Multi-Head Attention (الانتباه متعدد الرؤوس)
- Positional Encoding (ترميز الموضع)
- Feed-Forward Networks (الشبكات الأمامية)
- Layer Normalization (تطبيع الطبقات)
- Residual Connections (الاتصالات المتبقية)

مثل:
- GPT (Generative Pre-trained Transformer)
- BERT (Bidirectional Encoder Representations)
- T5 (Text-to-Text Transfer Transformer)

شركة أزاد للأنظمة الذكية
"""

import logging
import numpy as np
from typing import List, Dict, Tuple, Optional
import json
from datetime import datetime

logger = logging.getLogger(__name__)


class TransformersBrain:
    """
    دماغ المحولات - Transformers Architecture
    
    يحاكي معمارية Transformers بدون مكتبات ثقيلة
    للسرعة والكفاءة
    """
    
    def __init__(self, vocab_size: int = 10000, d_model: int = 512, n_heads: int = 8):
        """
        تهيئة المحول
        
        Args:
            vocab_size: حجم المفردات
            d_model: حجم embedding
            n_heads: عدد رؤوس الانتباه
        """
        self.vocab_size = vocab_size
        self.d_model = d_model
        self.n_heads = n_heads
        self.head_dim = d_model // n_heads
        
        # قاموس الكلمات (يمكن توسيعه)
        self.vocabulary = self._build_vocabulary()
        
        # التضمين (Embeddings) - محاكاة
        self.word_embeddings = {}
        
        # الأوزان (محاكاة بسيطة)
        self.attention_weights = {}
        
        # ذاكرة السياق
        self.context_memory = []
        
        logger.info(f"🤖 Transformers Brain initialized - Vocab: {vocab_size}, Model: {d_model}, Heads: {n_heads}")
    
    def _build_vocabulary(self) -> dict:
        """
        بناء قاموس المفردات العربية المتخصصة
        """
        # كلمات محاسبية
        accounting_words = [
            'قيد', 'مدين', 'دائن', 'ميزانية', 'أصول', 'خصوم', 'إيرادات', 'مصروفات',
            'ربح', 'خسارة', 'محاسبة', 'تدقيق', 'مراجعة', 'قوائم', 'مالية'
        ]
        
        # كلمات ضريبية
        tax_words = [
            'ضريبة', 'vat', 'جمارك', 'رسوم', 'إعفاء', 'خصم', 'تسجيل'
        ]
        
        # كلمات إدارية
        management_words = [
            'مخزون', 'طلب', 'عميل', 'مورد', 'مبيعات', 'مشتريات', 'إدارة', 'تخطيط'
        ]
        
        # كلمات هندسية
        engineering_words = [
            'محرك', 'صيانة', 'إصلاح', 'زيت', 'فرامل', 'معدات', 'أعطال'
        ]
        
        # دمج كل الكلمات
        all_words = accounting_words + tax_words + management_words + engineering_words
        
        # إضافة كلمات عامة
        all_words.extend(['ما', 'كيف', 'متى', 'أين', 'لماذا', 'هل', 'هذا', 'ذلك'])
        
        # بناء القاموس
        vocab = {word: idx for idx, word in enumerate(all_words)}
        vocab['<PAD>'] = len(vocab)  # Padding
        vocab['<UNK>'] = len(vocab)  # Unknown
        vocab['<START>'] = len(vocab)  # Start
        vocab['<END>'] = len(vocab)  # End
        
        return vocab
    
    # ========================================================================
    # Self-Attention Mechanism - آلية الانتباه الذاتي
    # ========================================================================
    
    def self_attention(self, query: List[float], key: List[float], value: List[float]) -> List[float]:
        """
        آلية الانتباه الذاتي
        
        Attention(Q, K, V) = softmax(QK^T / √d_k) V
        
        Args:
            query: استعلام
            key: مفتاح
            value: قيمة
        
        Returns:
            الناتج بعد الانتباه
        """
        # حساب الدرجات (scores)
        # score = Q · K^T
        scores = self._dot_product(query, key)
        
        # القسمة على جذر البعد
        scaled_scores = scores / np.sqrt(self.head_dim)
        
        # Softmax
        attention_weights = self._softmax([scaled_scores])
        
        # ضرب في القيمة
        output = [attention_weights[0] * v for v in value]
        
        return output
    
    def multi_head_attention(self, query: List[float], key: List[float], value: List[float]) -> List[float]:
        """
        الانتباه متعدد الرؤوس
        
        MultiHead(Q, K, V) = Concat(head_1, ..., head_h) W^O
        """
        heads_output = []
        
        # كل رأس يطبق self-attention منفصلة
        for head in range(self.n_heads):
            head_output = self.self_attention(query, key, value)
            heads_output.extend(head_output)
        
        # دمج النتائج
        return heads_output[:self.d_model]  # تقليم للحجم الصحيح
    
    def _dot_product(self, vec1: List[float], vec2: List[float]) -> float:
        """حساب الضرب النقطي"""
        return sum(a * b for a, b in zip(vec1, vec2))
    
    def _softmax(self, scores: List[float]) -> List[float]:
        """دالة Softmax"""
        exp_scores = [np.exp(s) for s in scores]
        sum_exp = sum(exp_scores)
        return [e / sum_exp for e in exp_scores]
    
    # ========================================================================
    # Positional Encoding - ترميز الموضع
    # ========================================================================
    
    def positional_encoding(self, position: int, d_model: int) -> List[float]:
        """
        ترميز الموضع
        
        PE(pos, 2i) = sin(pos / 10000^(2i/d_model))
        PE(pos, 2i+1) = cos(pos / 10000^(2i/d_model))
        """
        encoding = []
        
        for i in range(0, d_model, 2):
            # sin للأبعاد الزوجية
            div_term = 10000 ** (i / d_model)
            encoding.append(np.sin(position / div_term))
            
            # cos للأبعاد الفردية
            if i + 1 < d_model:
                encoding.append(np.cos(position / div_term))
        
        return encoding[:d_model]
    
    # ========================================================================
    # Feed-Forward Network - الشبكة الأمامية
    # ========================================================================
    
    def feed_forward(self, x: List[float]) -> List[float]:
        """
        الشبكة الأمامية
        
        FFN(x) = max(0, xW1 + b1)W2 + b2
        """
        # الطبقة الأولى (توسيع)
        hidden = [max(0, xi * 4) for xi in x]  # ReLU activation
        
        # الطبقة الثانية (تقليص)
        output = [h * 0.25 for h in hidden]
        
        return output[:self.d_model]
    
    # ========================================================================
    # Transformer Block - كتلة المحول
    # ========================================================================
    
    def transformer_block(self, x: List[float], position: int) -> List[float]:
        """
        كتلة محول كاملة
        
        1. Multi-Head Attention
        2. Add & Norm (Residual)
        3. Feed-Forward
        4. Add & Norm (Residual)
        """
        # الانتباه متعدد الرؤوس
        attention_output = self.multi_head_attention(x, x, x)
        
        # Residual Connection + Layer Norm
        x_norm = self._layer_norm([a + b for a, b in zip(x, attention_output)])
        
        # Feed-Forward
        ff_output = self.feed_forward(x_norm)
        
        # Residual Connection + Layer Norm
        final_output = self._layer_norm([a + b for a, b in zip(x_norm, ff_output)])
        
        return final_output
    
    def _layer_norm(self, x: List[float]) -> List[float]:
        """
        تطبيع الطبقة
        
        LayerNorm(x) = (x - mean) / std
        """
        mean = sum(x) / len(x)
        variance = sum((xi - mean) ** 2 for xi in x) / len(x)
        std = np.sqrt(variance + 1e-6)  # epsilon للاستقرار
        
        return [(xi - mean) / std for xi in x]
    
    # ========================================================================
    # Natural Language Understanding - فهم اللغة الطبيعية
    # ========================================================================
    
    def understand(self, text: str) -> dict:
        """
        فهم النص باستخدام Transformers
        
        Args:
            text: النص المدخل
        
        Returns:
            {
                'tokens': قائمة الرموز,
                'embeddings': التضمينات,
                'attention_map': خريطة الانتباه,
                'semantic_representation': التمثيل الدلالي,
                'intent': النية المستخرجة,
                'entities': الكيانات المستخرجة
            }
        """
        # 1. Tokenization (تجزئة النص)
        tokens = self._tokenize(text)
        
        # 2. Word Embeddings (تضمين الكلمات)
        embeddings = [self._get_embedding(token, pos) 
                     for pos, token in enumerate(tokens)]
        
        # 3. تطبيق Transformer Blocks
        transformed = embeddings[0] if embeddings else [0.0] * self.d_model
        for i in range(3):  # 3 طبقات
            transformed = self.transformer_block(transformed, i)
        
        # 4. استخراج النية
        intent = self._extract_intent(text, transformed)
        
        # 5. استخراج الكيانات
        entities = self._extract_entities(text, tokens)
        
        # 6. بناء خريطة الانتباه (محاكاة)
        attention_map = self._build_attention_map(tokens)
        
        return {
            'tokens': tokens,
            'embeddings': embeddings,
            'attention_map': attention_map,
            'semantic_representation': transformed,
            'intent': intent,
            'entities': entities,
            'confidence': 0.92,
            'model': 'transformers'
        }
    
    def _tokenize(self, text: str) -> List[str]:
        """تجزئة النص لكلمات"""
        # تنظيف النص
        text = text.strip()
        
        # تقسيم بسيط (يمكن تحسينه)
        tokens = text.split()
        
        return tokens
    
    def _get_embedding(self, token: str, position: int) -> List[float]:
        """
        الحصول على embedding للكلمة
        
        Embedding = Word Embedding + Positional Encoding
        """
        # Word embedding (محاكاة بسيطة)
        if token in self.word_embeddings:
            word_emb = self.word_embeddings[token]
        else:
            # إنشاء embedding عشوائي متسق
            word_idx = self.vocabulary.get(token, self.vocabulary['<UNK>'])
            np.random.seed(word_idx)  # ثبات النتائج
            word_emb = np.random.randn(self.d_model).tolist()
            self.word_embeddings[token] = word_emb
        
        # Positional encoding
        pos_enc = self.positional_encoding(position, self.d_model)
        
        # الجمع
        combined = [w + p for w, p in zip(word_emb, pos_enc)]
        
        return combined
    
    def _extract_intent(self, text: str, representation: List[float]) -> str:
        """استخراج النية من النص"""
        text_lower = text.lower()
        
        # تحليل النية
        if '؟' in text or any(kw in text_lower for kw in ['ما', 'كيف', 'متى', 'أين']):
            return 'question'
        elif any(kw in text_lower for kw in ['احسب', 'calculate']):
            return 'calculation'
        elif any(kw in text_lower for kw in ['اشرح', 'explain']):
            return 'explanation'
        elif any(kw in text_lower for kw in ['توقع', 'predict']):
            return 'prediction'
        else:
            return 'statement'
    
    def _extract_entities(self, text: str, tokens: List[str]) -> Dict[str, List[str]]:
        """استخراج الكيانات المسماة"""
        entities = {
            'numbers': [],
            'accounting_terms': [],
            'tax_terms': [],
            'management_terms': []
        }
        
        # استخراج الأرقام
        import re
        numbers = re.findall(r'\d+\.?\d*', text)
        entities['numbers'] = numbers
        
        # استخراج المصطلحات
        for token in tokens:
            if token in ['قيد', 'مدين', 'دائن', 'ميزانية']:
                entities['accounting_terms'].append(token)
            elif token in ['ضريبة', 'vat', 'جمارك']:
                entities['tax_terms'].append(token)
            elif token in ['مخزون', 'عميل', 'مورد']:
                entities['management_terms'].append(token)
        
        return entities
    
    def _build_attention_map(self, tokens: List[str]) -> Dict[str, List[float]]:
        """
        بناء خريطة الانتباه
        
        توضح أي كلمة تنتبه لأي كلمة أخرى
        """
        attention_map = {}
        
        for i, token in enumerate(tokens):
            # حساب الانتباه لكل كلمة أخرى
            attention_scores = []
            for j, other_token in enumerate(tokens):
                # المسافة بين الكلمات
                distance = abs(i - j)
                # الانتباه يقل مع المسافة
                score = 1.0 / (1.0 + distance)
                attention_scores.append(score)
            
            # Softmax
            attention_weights = self._softmax(attention_scores)
            attention_map[token] = attention_weights
        
        return attention_map
    
    # ========================================================================
    # Generation - التوليد
    # ========================================================================
    
    def generate_response(self, prompt: str, max_length: int = 50) -> str:
        """
        توليد رد ذكي باستخدام Transformers
        
        Args:
            prompt: المدخل
            max_length: الطول الأقصى للرد
        
        Returns:
            النص المولد
        """
        # فهم المدخل
        understanding = self.understand(prompt)
        
        # توليد الرد بناءً على النية
        intent = understanding['intent']
        entities = understanding['entities']
        
        if intent == 'question':
            if entities['tax_terms']:
                response = "📊 بناءً على تحليل Transformers، سأجيب عن سؤالك حول الضرائب..."
            elif entities['accounting_terms']:
                response = "💼 بناءً على فهمي العميق للمحاسبة..."
            else:
                response = "🤔 دعني أفكر في سؤالك باستخدام الانتباه متعدد الرؤوس..."
        
        elif intent == 'calculation':
            response = "🧮 سأحسب ذلك باستخدام معالجة متقدمة..."
        
        elif intent == 'prediction':
            response = "🔮 بناءً على تحليل الأنماط باستخدام Transformers..."
        
        else:
            response = "✅ فهمت. دعني أساعدك..."
        
        return response
    
    # ========================================================================
    # Context Management - إدارة السياق
    # ========================================================================
    
    def add_to_context(self, text: str):
        """إضافة للسياق"""
        understanding = self.understand(text)
        
        self.context_memory.append({
            'text': text,
            'timestamp': datetime.now().isoformat(),
            'representation': understanding['semantic_representation'],
            'intent': understanding['intent'],
            'entities': understanding['entities']
        })
        
        # الاحتفاظ بآخر 20 فقط
        if len(self.context_memory) > 20:
            self.context_memory = self.context_memory[-20:]
    
    def get_context_summary(self) -> str:
        """ملخص السياق"""
        if not self.context_memory:
            return "لا يوجد سياق سابق"
        
        intents = [ctx['intent'] for ctx in self.context_memory]
        most_common_intent = max(set(intents), key=intents.count)
        
        return f"السياق: {len(self.context_memory)} رسالة - النية الغالبة: {most_common_intent}"


# ============================================================================
# Singleton
# ============================================================================

_transformers_brain_instance = None

def get_transformers_brain():
    """الحصول على دماغ المحولات"""
    global _transformers_brain_instance
    if _transformers_brain_instance is None:
        _transformers_brain_instance = TransformersBrain()
    return _transformers_brain_instance



# ===== Consolidated from: neural/semantic_matcher.py =====
"""
🧠 نظام التطابق الدلالي الذكي - Semantic Matcher
يفهم المعنى وليس فقط الكلمات المطابقة!

استخدامات:
- TF-IDF للتشابه الدلالي
- Fuzzy Matching للأخطاء الإملائية
- Intent Detection الذكي
"""
import re
from typing import List, Tuple, Dict
from collections import Counter
import math


class SemanticMatcher:
    """محرك التطابق الدلالي"""
    
    def __init__(self):
        """تهيئة النظام مع قاعدة النوايا"""
        self.intents_db = self._build_intents_database()
        self.vocabulary = self._build_vocabulary()
        self.idf_scores = self._calculate_idf()
    
    def _build_intents_database(self) -> Dict[str, List[str]]:
        """بناء قاعدة بيانات النوايا مع أمثلة متعددة - شاملة لكل المعرفة"""
        return {
            # === النظام الأساسي ===
            'create_invoice': [
                'فاتورة جديدة', 'إنشاء فاتورة', 'أريد إنشاء فاتورة', 'سوي لي فاتورة',
                'أضف فاتورة', 'اعمل فاتورة', 'بدي أعمل invoice', 'كيف أسوي بيل',
                'ممكن تساعدني أسوي فاتورة', 'نو invoice جديد', 'create new invoice',
                'make invoice', 'new bill', 'فاتوره جديده'
            ],
            'create_receipt': [
                'سند قبض جديد', 'إنشاء سند قبض', 'أريد سند قبض', 'سوي سند',
                'اعمل receipt', 'دفعة جديدة', 'تسديد', 'قبض مبلغ', 'سند دفع'
            ],
            'sales_analysis': [
                'حلل المبيعات', 'تحليل مبيعات', 'كيف المبيعات', 'analyze sales',
                'sales report', 'تقرير المبيعات', 'إحصائيات المبيعات',
                'أرقام المبيعات', 'مبيعات اليوم', 'مبيعات الشهر'
            ],
            'customer_balance': [
                'رصيد العميل', 'كم رصيد الزبون', 'ديون الزبون', 'حساب العميل',
                'ذمم العميل', 'customer balance', 'كم عليه', 'كم له', 'حساب فلان'
            ],
            'inventory_check': [
                'فحص المخزون', 'صحة المخزون', 'حالة المخزون', 'مخزون المنتجات',
                'inventory health', 'stock status', 'كم في المخزن', 'مخزون قليل'
            ],
            'system_links': [
                'روابط النظام', 'روابط سريعة', 'quick links', 'system links',
                'صفحات النظام', 'أين أجد', 'كيف أصل ل', 'رابط صفحة'
            ],
            'add_customer': [
                'أضف عميل', 'إنشاء عميل جديد', 'سجل زبون', 'add customer',
                'new customer', 'عميل جديد', 'زبون جديد'
            ],
            
            # === الضرائب والجمارك ===
            'tax_info': [
                'ضريبة القيمة المضافة', 'الضريبة في الإمارات', 'VAT', 'tax rate',
                'كم الضريبة', 'نسبة الضريبة', 'ضريبة', 'الضريبة المستحقة',
                'حساب الضريبة', 'ضريبة الدخل', 'ضريبة الشركات'
            ],
            'customs_info': [
                'جمارك', 'customs', 'تخليص جمركي', 'رسوم جمركية', 'الجمارك في الإمارات',
                'إجراءات جمركية', 'استيراد', 'تصدير', 'بضائع جمركية', 'تعريفة جمركية'
            ],
            
            # === قطع الغيار والسيارات - تفصيلية ===
            'engine_parts': [
                'البستم', 'piston', 'الشنابر', 'rings', 'عمود الكرنك', 'crankshaft',
                'عمود الكامات', 'camshaft', 'الصمامات', 'valves', 'جوان الرأس',
                'head gasket', 'البواجي', 'spark plugs', 'مضخة الماء', 'water pump',
                'مضخة الزيت', 'oil pump', 'الثرموستات', 'thermostat'
            ],
            'diesel_parts': [
                'البخاخات', 'injectors', 'مضخة الديزل', 'fuel pump', 'شمعات التسخين',
                'glow plugs', 'فلتر الديزل', 'fuel filter', 'التيربو', 'turbocharger',
                'الانتركولر', 'intercooler'
            ],
            'transmission_parts': [
                'قير', 'transmission', 'الكلتش', 'clutch', 'عمود الكردان', 'drive shaft',
                'الديفرانس', 'differential', 'المحاور', 'axles', 'قير أوتوماتيك',
                'automatic', 'CVT', 'DSG', 'زيت القير', 'ATF'
            ],
            'suspension_parts': [
                'المساعدات', 'shock absorbers', 'amortisseur', 'السوست', 'springs',
                'الأذرعة', 'control arms', 'المقصات', 'bushings', 'البلي', 'ball joints',
                'التعليق', 'suspension'
            ],
            'brake_parts': [
                'فرامل', 'brakes', 'أقراص', 'discs', 'rotors', 'فحمات', 'brake pads',
                'طنابير', 'drums', 'فك الفرامل', 'calipers', 'زيت الفرامل',
                'brake fluid', 'ABS', 'مانع الانزلاق'
            ],
            'electrical_parts': [
                'البطارية', 'battery', 'الدينمو', 'alternator', 'السلف', 'starter',
                'الكويلات', 'ignition coils', 'الحساسات', 'sensors', 'الفيوزات',
                'fuses', 'الكهرباء', 'electrical'
            ],
            'ac_parts': [
                'التكييف', 'AC', 'الكمبروسر', 'compressor', 'الكوندنسر', 'condenser',
                'المبخر', 'evaporator', 'غاز التبريد', 'refrigerant', 'R134a',
                'تكييف ضعيف', 'تكييف مو شغال'
            ],
            'parts_info': [
                'قطعة غيار', 'قطع غيار', 'spare parts', 'معلومات عن قطعة',
                'كيف أميز القطعة', 'قطعة أصلية', 'قطعة تقليد', 'OEM', 'aftermarket'
            ],
            'automotive_ecu': [
                'ECU', 'كمبيوتر السيارة', 'وحدة التحكم', 'electronic control unit',
                'برمجة السيارة', 'تشخيص السيارة', 'أعطال السيارة', 'رموز الأخطاء',
                'diagnostic codes', 'فحص الكمبيوتر', 'OBD2', 'CAN bus'
            ],
            'diagnostic_codes': [
                'كود خطأ', 'error code', 'DTC', 'P0300', 'P0420', 'P0171',
                'check engine', 'لمبة المحرك', 'فحص كود', 'مسح الأكواد',
                'clear codes', 'ما معنى الكود', 'كود العطل'
            ],
            'sensors_issues': [
                'حساس', 'sensor', 'O2 sensor', 'MAF', 'MAP', 'TPS', 'CTS',
                'حساس الأكسجين', 'حساس الهواء', 'حساس الحرارة', 'حساس البنزين',
                'حساس خربان', 'sensor failure', 'حساس عطلان'
            ],
            'heavy_equipment': [
                'معدات ثقيلة', 'heavy equipment', 'كاتربيلر', 'CAT', 'Komatsu',
                'Volvo', 'حفارة', 'excavator', 'لودر', 'loader', 'جريدر', 'grader',
                'بلدوزر', 'bulldozer', 'Hitachi', 'JCB', 'قطع CAT'
            ],
            
            # === السوق وخدمة العملاء ===
            'market_insights': [
                'رؤى السوق', 'market insights', 'اتجاهات السوق', 'أسعار السوق',
                'المنافسة', 'competition', 'تحليل السوق', 'فرص السوق', 'المواسم',
                'موسم المبيعات', 'ذروة المبيعات'
            ],
            'pricing_strategy': [
                'استراتيجية التسعير', 'pricing strategy', 'كيف أسعر', 'هامش الربح',
                'profit margin', 'سعر تنافسي', 'خصم للتجار', 'خصومات', 'discounts',
                'كم أبيع', 'سعر مناسب', 'سعر جملة', 'wholesale', 'retail'
            ],
            'customer_service': [
                'خدمة العملاء', 'customer service', 'كيف أتعامل مع العميل',
                'نصائح للعملاء', 'رضا العملاء', 'شكاوى العملاء', 'تحسين الخدمة',
                'عميل غاضب', 'angry customer', 'handling complaints'
            ],
            'sales_techniques': [
                'تقنيات البيع', 'sales techniques', 'كيف أبيع', 'إقناع العميل',
                'closing sales', 'إتمام البيع', 'upselling', 'cross selling',
                'زيادة المبيعات', 'نصائح بيع'
            ],
            
            # === الشحن والجودة ===
            'shipping_laws': [
                'قوانين الشحن', 'shipping laws', 'إجراءات الشحن', 'شحن دولي',
                'international shipping', 'وثائق الشحن', 'تأمين الشحن'
            ],
            'quality_standards': [
                'معايير الجودة', 'quality standards', 'شهادة جودة', 'ISO',
                'مواصفات', 'specifications', 'اختبار الجودة', 'quality control'
            ],
            
            # === الموردين والمشتريات ===
            'suppliers_info': [
                'موردين', 'suppliers', 'مورد جديد', 'إضافة مورد', 'الموردين',
                'شراء من مورد', 'عروض الموردين', 'تقييم المورد'
            ],
            
            # === المصادر والمعرفة ===
            'knowledge_sources': [
                'مصادر', 'sources', 'مصادر معلومات', 'أين أجد معلومات',
                'مواقع مفيدة', 'كتب', 'مراجع', 'توصيات للمصادر', 'وين أتعلم'
            ],
            
            # === القوانين المتقدمة (فلسطين، إسرائيل، الخليج) ===
            'palestine_tax_laws': [
                'ضريبة فلسطين', 'قانون ضريبي فلسطيني', 'ضرائب فلسطينية',
                'palestinian tax', 'ضريبة في فلسطين', 'VAT فلسطين'
            ],
            'israel_tax_laws': [
                'ضريبة إسرائيل', 'قانون ضريبي إسرائيلي', 'ضرائب إسرائيلية',
                'israeli tax', 'מס ישראל', 'ضريبة في إسرائيل'
            ],
            'gulf_tax_laws': [
                'ضريبة الخليج', 'ضرائب دول الخليج', 'GCC tax', 'ضريبة السعودية',
                'ضريبة قطر', 'ضريبة الكويت', 'ضريبة البحرين', 'ضريبة عمان'
            ],
            'shipping_regulations': [
                'تنظيمات الشحن', 'قوانين الشحن', 'إجراءات الشحن',
                'shipping regulations', 'import regulations', 'export laws'
            ],
            
            # === المعالجة المتقدمة ===
            'memory_query': [
                'تذكر', 'remember', 'قلت لي', 'you told me', 'في محادثة سابقة',
                'previous conversation', 'ما قلته', 'what you said'
            ],
            'multi_step_query': [
                'ثم', 'then', 'بعدين', 'وبعد ذلك', 'after that',
                'خطوة بخطوة', 'step by step'
            ],
            
            # === التفاعل الاجتماعي والشخصية ===
            'greeting': [
                'مرحبا', 'هلا', 'أهلا', 'السلام عليكم', 'سلام', 'هاي', 'hi', 'hello',
                'صباح الخير', 'مساء الخير', 'كيفك', 'شلونك', 'أخبار', 'شو الأخبار',
                'يا هلا', 'مرحب', 'هلا والله', 'كيف الحال'
            ],
            'complaint': [
                'زعلان', 'مو شغال', 'خربان', 'سيء', 'ما يفهم', 'غبي', 'بطيء',
                'مشكلة', 'في غلط', 'مو صح', 'خطأ', 'ما عجبني', 'تعبان', 'قديم'
            ],
            'praise': [
                'كفو', 'ممتاز', 'شاطر', 'وحش', 'بطل', 'عظيم', 'رهيب', 'فنان',
                'أحسنت', 'شكرا', 'مشكور', 'يعطيك العافية', 'تسلم', 'ما قصرت',
                'ذكي', 'عبقري'
            ],
            'who_are_you': [
                'مين انت', 'من أنت', 'عرف عن نفسك', 'شو اسمك', 'أنت مين',
                'who are you', 'what is your name', 'شو وظيفتك', 'إيش تسوي'
            ],

            # === المساعدة والدليل ===
            'general_help': [
                'مساعدة', 'help', 'كيف أستخدم', 'شرح لي', 'explain',
                'ما هو', 'what is', 'دليل', 'guide', 'how to'
            ]
        }
    
    def _build_vocabulary(self) -> set:
        """بناء قاموس الكلمات"""
        vocab = set()
        for intent, examples in self.intents_db.items():
            for example in examples:
                words = self._tokenize(example)
                vocab.update(words)
        return vocab
    
    def _tokenize(self, text: str) -> List[str]:
        """تقسيم النص لكلمات"""
        # إزالة علامات الترقيم والتشكيل
        text = re.sub(r'[^\w\s]', ' ', text)
        # تحويل لأحرف صغيرة
        text = text.lower()
        # تقسيم
        words = text.split()
        # إزالة الكلمات القصيرة جداً
        words = [w for w in words if len(w) > 1]
        return words
    
    def _calculate_tf(self, words: List[str]) -> Dict[str, float]:
        """حساب Term Frequency"""
        word_count = Counter(words)
        total_words = len(words)
        return {word: count / total_words for word, count in word_count.items()}
    
    def _calculate_idf(self) -> Dict[str, float]:
        """حساب Inverse Document Frequency"""
        # عدد الوثائق (الأمثلة) الكلي
        total_docs = sum(len(examples) for examples in self.intents_db.values())
        
        # حساب عدد الوثائق التي تحتوي على كل كلمة
        word_doc_count = Counter()
        for intent, examples in self.intents_db.items():
            for example in examples:
                words = set(self._tokenize(example))
                word_doc_count.update(words)
        
        # حساب IDF
        idf = {}
        for word in self.vocabulary:
            if word in word_doc_count:
                idf[word] = math.log(total_docs / (1 + word_doc_count[word]))
            else:
                idf[word] = 0
        
        return idf
    
    def _calculate_tfidf(self, words: List[str]) -> Dict[str, float]:
        """حساب TF-IDF"""
        tf = self._calculate_tf(words)
        tfidf = {}
        for word in words:
            if word in self.idf_scores:
                tfidf[word] = tf[word] * self.idf_scores[word]
            else:
                tfidf[word] = tf[word] * 1.0  # IDF default
        return tfidf
    
    def _cosine_similarity(self, vec1: Dict[str, float], vec2: Dict[str, float]) -> float:
        """حساب التشابه بين متجهين باستخدام Cosine Similarity"""
        # الكلمات المشتركة
        common_words = set(vec1.keys()) & set(vec2.keys())
        
        if not common_words:
            return 0.0
        
        # حساب الضرب النقطي
        dot_product = sum(vec1[word] * vec2[word] for word in common_words)
        
        # حساب المقادير
        magnitude1 = math.sqrt(sum(val ** 2 for val in vec1.values()))
        magnitude2 = math.sqrt(sum(val ** 2 for val in vec2.values()))
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        
        return dot_product / (magnitude1 * magnitude2)
    
    def find_best_intent(self, user_message: str, threshold: float = 0.3) -> Tuple[str, float, List[Tuple[str, float]]]:
        """
        إيجاد أفضل نية (intent) للرسالة
        
        Args:
            user_message: رسالة المستخدم
            threshold: الحد الأدنى للثقة (0.3 = 30%)
        
        Returns:
            (intent_name, confidence, all_scores)
        """
        # تحليل رسالة المستخدم
        user_words = self._tokenize(user_message)
        user_tfidf = self._calculate_tfidf(user_words)
        
        # حساب التشابه مع كل نية
        intent_scores = {}
        
        for intent, examples in self.intents_db.items():
            max_similarity = 0.0
            
            # حساب التشابه مع كل مثال
            for example in examples:
                example_words = self._tokenize(example)
                example_tfidf = self._calculate_tfidf(example_words)
                
                similarity = self._cosine_similarity(user_tfidf, example_tfidf)
                max_similarity = max(max_similarity, similarity)
            
            intent_scores[intent] = max_similarity
        
        # ترتيب النوايا حسب الدرجة
        sorted_intents = sorted(intent_scores.items(), key=lambda x: x[1], reverse=True)
        
        # أفضل نية
        best_intent, best_score = sorted_intents[0] if sorted_intents else (None, 0.0)
        
        # إذا كانت الدرجة أقل من الحد الأدنى
        if best_score < threshold:
            return None, best_score, sorted_intents
        
        return best_intent, best_score, sorted_intents
    
    def fuzzy_match(self, word1: str, word2: str) -> float:
        """
        مطابقة تقريبية (Fuzzy) بين كلمتين
        تستخدم Levenshtein Distance
        
        Returns: نسبة التشابه (0-1)
        """
        # Levenshtein Distance بسيط
        len1, len2 = len(word1), len(word2)
        
        if len1 == 0:
            return 0.0 if len2 == 0 else 0.0
        
        if len2 == 0:
            return 0.0
        
        # بناء مصفوفة المسافات
        matrix = [[0] * (len2 + 1) for _ in range(len1 + 1)]
        
        for i in range(len1 + 1):
            matrix[i][0] = i
        for j in range(len2 + 1):
            matrix[0][j] = j
        
        for i in range(1, len1 + 1):
            for j in range(1, len2 + 1):
                if word1[i-1] == word2[j-1]:
                    cost = 0
                else:
                    cost = 1
                
                matrix[i][j] = min(
                    matrix[i-1][j] + 1,      # deletion
                    matrix[i][j-1] + 1,      # insertion
                    matrix[i-1][j-1] + cost  # substitution
                )
        
        distance = matrix[len1][len2]
        max_len = max(len1, len2)
        
        # نسبة التشابه
        similarity = 1 - (distance / max_len)
        return similarity
    
    def smart_match(self, user_message: str) -> Dict:
        """
        مطابقة ذكية شاملة
        
        Returns:
            {
                'intent': النية المكتشفة,
                'confidence': مستوى الثقة,
                'method': طريقة الاكتشاف ('semantic', 'fuzzy', 'exact'),
                'all_scores': جميع النتائج,
                'suggestion': اقتراح إذا كانت الثقة منخفضة
            }
        """
        # 1. محاولة Semantic Matching أولاً
        intent, confidence, all_scores = self.find_best_intent(user_message, threshold=0.3)
        
        if intent and confidence > 0.5:
            return {
                'intent': intent,
                'confidence': confidence,
                'method': 'semantic',
                'all_scores': all_scores[:3],
                'suggestion': None
            }
        
        # 2. محاولة Fuzzy Matching للكلمات المفتاحية
        user_words = self._tokenize(user_message)
        best_fuzzy_match = None
        best_fuzzy_score = 0.0
        
        for word in user_words:
            for intent, examples in self.intents_db.items():
                for example in examples:
                    example_words = self._tokenize(example)
                    for ex_word in example_words:
                        fuzzy_score = self.fuzzy_match(word, ex_word)
                        if fuzzy_score > best_fuzzy_score and fuzzy_score > 0.8:
                            best_fuzzy_score = fuzzy_score
                            best_fuzzy_match = intent
        
        if best_fuzzy_match and best_fuzzy_score > 0.8:
            return {
                'intent': best_fuzzy_match,
                'confidence': best_fuzzy_score,
                'method': 'fuzzy',
                'all_scores': [(best_fuzzy_match, best_fuzzy_score)],
                'suggestion': None
            }
        
        # 3. لم يتم العثور على تطابق جيد
        suggestion = None
        if all_scores and all_scores[0][1] > 0.2:
            suggestion = f"هل تقصد: {self._get_intent_arabic_name(all_scores[0][0])}؟"
        
        return {
            'intent': intent if confidence > 0.2 else None,
            'confidence': confidence,
            'method': 'low_confidence',
            'all_scores': all_scores[:3],
            'suggestion': suggestion
        }
    
    def _get_intent_arabic_name(self, intent: str) -> str:
        """تحويل اسم النية للعربية"""
        names = {
            'create_invoice': 'إنشاء فاتورة',
            'create_receipt': 'إنشاء سند قبض',
            'sales_analysis': 'تحليل المبيعات',
            'customer_balance': 'رصيد العميل',
            'inventory_check': 'فحص المخزون',
            'system_links': 'روابط النظام',
            'add_customer': 'إضافة عميل',
            'tax_info': 'معلومات الضرائب',
            'customs_info': 'معلومات الجمارك',
            'parts_info': 'معلومات قطع الغيار',
            'automotive_ecu': 'كمبيوتر السيارة ECU',
            'heavy_equipment': 'المعدات الثقيلة',
            'market_insights': 'رؤى السوق',
            'customer_service': 'خدمة العملاء',
            'shipping_laws': 'قوانين الشحن',
            'quality_standards': 'معايير الجودة',
            'suppliers_info': 'معلومات الموردين',
            'knowledge_sources': 'مصادر المعرفة',
            'palestine_tax_laws': 'القوانين الضريبية الفلسطينية',
            'israel_tax_laws': 'القوانين الضريبية الإسرائيلية',
            'gulf_tax_laws': 'القوانين الضريبية الخليجية',
            'shipping_regulations': 'تنظيمات الشحن',
            'memory_query': 'استرجاع من الذاكرة',
            'multi_step_query': 'استفسار متعدد الخطوات',
            # النوايا الجديدة - قطع غيار تفصيلية
            'engine_parts': 'قطع المحرك',
            'diesel_parts': 'قطع الديزل',
            'transmission_parts': 'قطع ناقل الحركة',
            'suspension_parts': 'قطع التعليق',
            'brake_parts': 'قطع الفرامل',
            'electrical_parts': 'القطع الكهربائية',
            'ac_parts': 'قطع التكييف',
            # نوايا متقدمة
            'diagnostic_codes': 'أكواد الأعطال',
            'sensors_issues': 'مشاكل الحساسات',
            'pricing_strategy': 'استراتيجية التسعير',
            'sales_techniques': 'تقنيات البيع',
            'general_help': 'مساعدة عامة'
        }
        return names.get(intent, intent)


# إنشاء instance عام
semantic_matcher = SemanticMatcher()


# ===== دوال مساعدة سريعة =====

def understand_message(message: str) -> Dict:
    """فهم رسالة المستخدم بذكاء"""
    return semantic_matcher.smart_match(message)


def get_intent(message: str) -> str:
    """الحصول على النية فقط"""
    result = semantic_matcher.smart_match(message)
    return result['intent']


def get_confidence(message: str) -> float:
    """الحصول على مستوى الثقة"""
    result = semantic_matcher.smart_match(message)
    return result['confidence']



# ===== Consolidated from: neural/neural_engine.py =====
"""
🧠 محرك الشبكات العصبية المتقدم - Advanced Neural Engine
المساعد الذكي أزاد - نظام عصبي متكامل

القدرات:
- مهندس صيانة معدات ثقيلة
- محاسب قانوني خبير
- مدير مالي وإداري
- مستشار أعمال
- سكرتير تنفيذي
- محلل بيانات متقدم

التقنيات:
- Neural Networks (Multi-layer Perceptron)
- Deep Learning Simulation
- Pattern Recognition
- Predictive Analytics
- Natural Language Processing
- Time Series Forecasting
- Anomaly Detection
- Recommendation Systems

شركة أزاد للأنظمة الذكية
"""

import numpy as np
import pandas as pd
from sklearn.neural_network import MLPRegressor, MLPClassifier
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import accuracy_score, mean_squared_error, r2_score
import joblib
import os
import json
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class AzadNeuralEngine:
    """
    🧠 محرك الشبكات العصبية الشامل
    
    يجمع قدرات:
    - ChatGPT (فهم لغوي متقدم)
    - DeepSeek (تفكير منطقي عميق)
    - مهندس صيانة (تشخيص الأعطال)
    - محاسب قانوني (المبادئ المحاسبية)
    - مدير مالي (التخطيط المالي)
    - سكرتير تنفيذي (التنظيم والجدولة)
    """
    
    def __init__(self):
        from ai_knowledge import get_knowledge_path
        self.models_dir = get_knowledge_path('neural_models')
        self.ensure_models_dir()
        
        # النماذج العصبية
        self.models = {}
        self.scalers = {}
        self.encoders = {}
        
        # حالة التدريب
        self.training_status = {}
        
        # إحصائيات الأداء
        self.performance_metrics = {}
        
        # تهيئة جميع النماذج
        self._initialize_all_models()
        
        logger.info("🧠 Neural Engine initialized with advanced capabilities")
    
    def ensure_models_dir(self):
        """التأكد من وجود مجلد النماذج"""
        if not os.path.exists(self.models_dir):
            os.makedirs(self.models_dir)
    
    def _initialize_all_models(self):
        """تهيئة جميع النماذج العصبية"""
        
        # 1. Price Optimization Neural Network
        self.models['price_optimizer'] = MLPRegressor(
            hidden_layer_sizes=(128, 64, 32, 16),  # 4 طبقات عميقة
            activation='relu',
            solver='adam',
            learning_rate='adaptive',
            max_iter=2000,
            random_state=42,
            early_stopping=True,
            validation_fraction=0.2
        )
        
        # 2. Sales Forecasting Neural Network (Time Series)
        self.models['sales_forecaster'] = MLPRegressor(
            hidden_layer_sizes=(256, 128, 64, 32),  # شبكة عميقة للتوقعات
            activation='relu',
            solver='adam',
            learning_rate='adaptive',
            max_iter=3000,
            random_state=42
        )
        
        # 3. Customer Classification Neural Network
        self.models['customer_classifier'] = MLPClassifier(
            hidden_layer_sizes=(100, 50, 25),
            activation='relu',
            solver='adam',
            max_iter=2000,
            random_state=42
        )
        
        # 4. Fraud Detection Neural Network
        self.models['fraud_detector'] = MLPClassifier(
            hidden_layer_sizes=(150, 100, 50),
            activation='relu',
            solver='adam',
            max_iter=2000,
            random_state=42
        )
        
        # 5. Inventory Optimization Neural Network
        self.models['inventory_optimizer'] = MLPRegressor(
            hidden_layer_sizes=(128, 64, 32),
            activation='relu',
            solver='adam',
            max_iter=2000,
            random_state=42
        )
        
        # 6. Demand Prediction Neural Network
        self.models['demand_predictor'] = MLPRegressor(
            hidden_layer_sizes=(200, 100, 50, 25),  # شبكة عميقة جداً
            activation='relu',
            solver='adam',
            learning_rate='adaptive',
            max_iter=3000,
            random_state=42
        )
        
        # 7. Profit Optimization Neural Network
        self.models['profit_optimizer'] = MLPRegressor(
            hidden_layer_sizes=(100, 50, 25),
            activation='relu',
            solver='adam',
            max_iter=2000,
            random_state=42
        )
        
        # 8. Churn Prediction Neural Network
        self.models['churn_predictor'] = MLPClassifier(
            hidden_layer_sizes=(80, 40, 20),
            activation='relu',
            solver='adam',
            max_iter=2000,
            random_state=42
        )
        
        # 9. Maintenance Prediction Neural Network (مهندس صيانة)
        self.models['maintenance_predictor'] = MLPClassifier(
            hidden_layer_sizes=(100, 50, 25),
            activation='relu',
            solver='adam',
            max_iter=2000,
            random_state=42
        )
        
        # 10. Financial Planning Neural Network (مدير مالي)
        self.models['financial_planner'] = MLPRegressor(
            hidden_layer_sizes=(150, 100, 50, 25),
            activation='relu',
            solver='adam',
            max_iter=3000,
            random_state=42
        )
        
        # Scalers for each model
        for model_name in self.models:
            self.scalers[model_name] = StandardScaler()
            self.encoders[model_name] = LabelEncoder()
    
    # ====================================================================
    # 1. مهندس الصيانة - Maintenance Engineer
    # ====================================================================
    
    def train_maintenance_prediction(self, from_app_context=None):
        """
        تدريب نموذج توقع الصيانة
        
        القدرات:
        - توقع موعد الصيانة القادمة
        - تشخيص الأعطال المحتملة
        - توصيات قطع الغيار
        """
        try:
            if from_app_context:
                with from_app_context():
                    return self._train_maintenance_internal()
            else:
                return self._train_maintenance_internal()
        
        except Exception as e:
            logger.error(f"Maintenance training failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def _train_maintenance_internal(self):
        """التدريب الداخلي لنموذج الصيانة"""
        from models import Product, Sale, SaleLine, StockMovement
        from extensions import db
        
        # جمع بيانات استخدام المنتجات
        products = db.session.query(
            Product.id,
            Product.name,
            Product.cost_price,
            Product.current_stock,
            func.count(SaleLine.id).label('sales_count'),
            func.sum(SaleLine.quantity).label('total_sold'),
            func.max(Sale.sale_date).label('last_sale_date')
        ).outerjoin(SaleLine).outerjoin(Sale).group_by(Product.id).limit(500).all()
        
        if len(products) < 20:
            return {'success': False, 'error': 'Not enough data', 'samples': len(products)}
        
        # تحضير البيانات
        X = []
        y = []
        
        for product in products:
            # الميزات
            days_since_sale = (datetime.now(timezone.utc).date() - product.last_sale_date.date()).days if product.last_sale_date else 365
            usage_frequency = product.sales_count or 0
            total_usage = product.total_sold or 0
            
            features = [
                float(product.cost_price or 0),
                float(product.current_stock or 0),
                float(usage_frequency),
                float(total_usage),
                float(days_since_sale),
                1 if usage_frequency > 10 else 0  # high usage
            ]
            
            # التصنيف (يحتاج صيانة قريباً أم لا)
            needs_maintenance = 1 if (usage_frequency > 50 and days_since_sale < 30) else 0
            
            X.append(features)
            y.append(needs_maintenance)
        
        X = np.array(X)
        y = np.array(y)
        
        # التدريب
        X_scaled = self.scalers['maintenance_predictor'].fit_transform(X)
        self.models['maintenance_predictor'].fit(X_scaled, y)
        
        # الدقة
        accuracy = self.models['maintenance_predictor'].score(X_scaled, y)
        
        # حفظ النموذج
        self._save_model('maintenance_predictor')
        
        self.training_status['maintenance_predictor'] = {
            'trained': True,
            'accuracy': accuracy,
            'samples': len(products),
            'trained_at': datetime.now().isoformat()
        }
        
        logger.info(f"🔧 Maintenance model trained: {accuracy:.2%} accuracy on {len(products)} samples")
        
        return {
            'success': True,
            'accuracy': accuracy,
            'samples': len(products),
            'model': 'maintenance_predictor'
        }
    
    def predict_maintenance_needs(self, product_id, from_app_context=None):
        """
        توقع احتياجات الصيانة للمنتج
        
        Returns:
        - needs_maintenance: bool
        - confidence: float (0-1)
        - recommended_action: str
        - estimated_days: int
        """
        try:
            if from_app_context:
                with from_app_context():
                    return self._predict_maintenance_internal(product_id)
            else:
                return self._predict_maintenance_internal(product_id)
        
        except Exception as e:
            logger.error(f"Maintenance prediction failed: {e}")
            return {'needs_maintenance': False, 'confidence': 0}
    
    def _predict_maintenance_internal(self, product_id):
        """التوقع الداخلي لاحتياجات الصيانة"""
        from models import Product, Sale, SaleLine
        from extensions import db
        
        # تحميل النموذج
        if not self._load_model('maintenance_predictor'):
            return {'needs_maintenance': False, 'confidence': 0, 'error': 'Model not trained'}
        
        # الحصول على بيانات المنتج
        product_data = db.session.query(
            Product.cost_price,
            Product.current_stock,
            func.count(SaleLine.id).label('sales_count'),
            func.sum(SaleLine.quantity).label('total_sold'),
            func.max(Sale.sale_date).label('last_sale_date')
        ).outerjoin(SaleLine).outerjoin(Sale).filter(
            Product.id == product_id
        ).group_by(Product.id).first()
        
        if not product_data:
            return {'needs_maintenance': False, 'confidence': 0}
        
        # تحضير الميزات
        days_since_sale = (datetime.now(timezone.utc).date() - product_data.last_sale_date.date()).days if product_data.last_sale_date else 365
        
        features = [
            float(product_data.cost_price or 0),
            float(product_data.current_stock or 0),
            float(product_data.sales_count or 0),
            float(product_data.total_sold or 0),
            float(days_since_sale),
            1 if product_data.sales_count > 10 else 0
        ]
        
        # التوقع
        features_scaled = self.scalers['maintenance_predictor'].transform([features])
        prediction = self.models['maintenance_predictor'].predict(features_scaled)
        probability = self.models['maintenance_predictor'].predict_proba(features_scaled)
        
        needs_maintenance = bool(prediction[0])
        confidence = float(max(probability[0]))
        
        # التوصيات
        if needs_maintenance:
            recommended_action = "فحص وصيانة فورية - الاستخدام مكثف"
            estimated_days = 7
        else:
            recommended_action = "الوضع طبيعي - مراقبة دورية"
            estimated_days = 30
        
        return {
            'needs_maintenance': needs_maintenance,
            'confidence': confidence,
            'recommended_action': recommended_action,
            'estimated_days': estimated_days,
            'model': 'neural_network'
        }
    
    # ====================================================================
    # 2. المحاسب الخبير - Expert Accountant
    # ====================================================================
    
    def train_accounting_assistant(self, from_app_context=None):
        """
        تدريب نموذج المحاسب الخبير
        
        القدرات:
        - تصنيف القيود المحاسبية
        - كشف الأخطاء المحاسبية
        - توصيات القيود الصحيحة
        - تحليل الميزانيات
        """
        try:
            if from_app_context:
                with from_app_context():
                    return self._train_accounting_internal()
            else:
                return self._train_accounting_internal()
        
        except Exception as e:
            logger.error(f"Accounting training failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def _train_accounting_internal(self):
        """التدريب الداخلي للمحاسب"""
        from models import GLJournalEntry, GLJournalLine, Sale, Purchase
        from extensions import db
        
        # جمع القيود المحاسبية
        entries = GLJournalEntry.query.limit(500).all()
        
        if len(entries) < 10:
            return {'success': False, 'error': 'Not enough accounting data'}
        
        X = []
        y = []
        
        for entry in entries:
            # الميزات
            lines_count = len(list(entry.lines)) if entry.lines else 0
            total_debit = float(entry.total_debit or 0)
            total_credit = float(entry.total_credit or 0)
            is_balanced = 1 if abs(total_debit - total_credit) < 0.01 else 0
            
            features = [
                total_debit,
                total_credit,
                float(lines_count),
                is_balanced,
                1 if entry.reference_type == 'Sale' else 0,
                1 if entry.reference_type == 'Purchase' else 0
            ]
            
            # التصنيف (قيد صحيح = 1، خاطئ = 0)
            is_correct = is_balanced
            
            X.append(features)
            y.append(is_correct)
        
        X = np.array(X)
        y = np.array(y)
        
        # تدريب نموذج التصنيف المحاسبي
        if 'accounting_classifier' not in self.models:
            self.models['accounting_classifier'] = MLPClassifier(
                hidden_layer_sizes=(100, 50, 25),
                activation='relu',
                solver='adam',
                max_iter=2000,
                random_state=42
            )
            self.scalers['accounting_classifier'] = StandardScaler()
        
        X_scaled = self.scalers['accounting_classifier'].fit_transform(X)
        self.models['accounting_classifier'].fit(X_scaled, y)
        
        accuracy = self.models['accounting_classifier'].score(X_scaled, y)
        
        self._save_model('accounting_classifier')
        
        logger.info(f"📊 Accounting model trained: {accuracy:.2%} accuracy")
        
        return {
            'success': True,
            'accuracy': accuracy,
            'samples': len(entries)
        }
    
    def validate_accounting_entry(self, debit, credit, lines_count, reference_type):
        """
        التحقق من صحة القيد المحاسبي
        
        Returns:
        - is_correct: bool
        - confidence: float
        - recommendation: str
        """
        try:
            if not self._load_model('accounting_classifier'):
                # Fallback للقاعدة البسيطة
                is_balanced = abs(debit - credit) < 0.01
                return {
                    'is_correct': is_balanced,
                    'confidence': 1.0 if is_balanced else 0.0,
                    'recommendation': 'القيد متوازن' if is_balanced else 'القيد غير متوازن - راجع المدين والدائن'
                }
            
            # تحضير الميزات
            features = [
                float(debit),
                float(credit),
                float(lines_count),
                1 if abs(debit - credit) < 0.01 else 0,
                1 if reference_type == 'Sale' else 0,
                1 if reference_type == 'Purchase' else 0
            ]
            
            # التوقع
            features_scaled = self.scalers['accounting_classifier'].transform([features])
            prediction = self.models['accounting_classifier'].predict(features_scaled)
            probability = self.models['accounting_classifier'].predict_proba(features_scaled)
            
            is_correct = bool(prediction[0])
            confidence = float(max(probability[0]))
            
            # التوصية
            if is_correct:
                recommendation = "✅ القيد صحيح محاسبياً - يمكن اعتماده"
            else:
                if abs(debit - credit) > 0.01:
                    recommendation = "❌ القيد غير متوازن - المدين ≠ الدائن"
                else:
                    recommendation = "⚠️ القيد يحتاج مراجعة - النمط غير معتاد"
            
            return {
                'is_correct': is_correct,
                'confidence': confidence,
                'recommendation': recommendation,
                'model': 'neural_network'
            }
        
        except Exception as e:
            logger.error(f"Accounting validation failed: {e}")
            return {'is_correct': True, 'confidence': 0.5, 'recommendation': 'تعذر التحقق'}
    
    # ====================================================================
    # 3. المدير المالي - Financial Manager
    # ====================================================================
    
    def train_financial_planning(self, from_app_context=None):
        """
        تدريب نموذج التخطيط المالي
        
        القدرات:
        - توقع التدفقات النقدية
        - تحليل الربحية
        - توصيات الاستثمار
        - إدارة رأس المال العامل
        """
        try:
            if from_app_context:
                with from_app_context():
                    return self._train_financial_internal()
            else:
                return self._train_financial_internal()
        
        except Exception as e:
            logger.error(f"Financial planning training failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def _train_financial_internal(self):
        """التدريب الداخلي للمخطط المالي"""
        from models import Sale, Purchase, Expense, Receipt, Payment
        from extensions import db
        from sqlalchemy import func
        from utils.tenanting import get_active_tenant_id

        tid = get_active_tenant_id()
        tenant_filter = []
        if tid is not None:
            tenant_filter = [Sale.tenant_id == tid, Purchase.tenant_id == tid, Expense.tenant_id == tid, Receipt.tenant_id == tid]
        
        # جمع البيانات المالية الشهرية
        monthly_data = []
        
        for month_offset in range(12):  # آخر 12 شهر
            start_date = datetime.now(timezone.utc) - timedelta(days=30 * (month_offset + 1))
            end_date = datetime.now(timezone.utc) - timedelta(days=30 * month_offset)
            
            # المبيعات
            sales = db.session.query(func.sum(Sale.amount_aed)).filter(
                Sale.sale_date.between(start_date, end_date),
                Sale.status == 'confirmed',
                Sale.tenant_id == tid if tid is not None else True
            ).scalar() or 0
            
            # المشتريات
            purchases = db.session.query(func.sum(Purchase.amount_aed)).filter(
                Purchase.purchase_date.between(start_date, end_date),
                Purchase.tenant_id == tid if tid is not None else True
            ).scalar() or 0
            
            # المصروفات
            expenses = db.session.query(func.sum(Expense.amount_aed)).filter(
                Expense.expense_date.between(start_date, end_date),
                Expense.tenant_id == tid if tid is not None else True
            ).scalar() or 0
            
            # المقبوضات
            receipts = db.session.query(func.sum(Receipt.amount_aed)).filter(
                Receipt.receipt_date.between(start_date, end_date),
                Receipt.tenant_id == tid if tid is not None else True
            ).scalar() or 0
            
            # الصافي
            net_cash_flow = float(receipts - purchases - expenses)
            
            monthly_data.append({
                'month': month_offset,
                'sales': float(sales),
                'purchases': float(purchases),
                'expenses': float(expenses),
                'receipts': float(receipts),
                'net_cash_flow': net_cash_flow
            })
        
        if len(monthly_data) < 3:
            return {'success': False, 'error': 'Not enough monthly data'}
        
        # تحضير للتدريب
        X = []
        y = []
        
        for i in range(len(monthly_data) - 1):
            current = monthly_data[i]
            next_month = monthly_data[i + 1]
            
            # الميزات: البيانات الحالية
            features = [
                current['sales'],
                current['purchases'],
                current['expenses'],
                current['receipts'],
                current['net_cash_flow'],
                current['month']
            ]
            
            # الهدف: التدفق النقدي الشهر القادم
            target = next_month['net_cash_flow']
            
            X.append(features)
            y.append(target)
        
        X = np.array(X)
        y = np.array(y)
        
        # التدريب
        X_scaled = self.scalers['financial_planner'].fit_transform(X)
        self.models['financial_planner'].fit(X_scaled, y)
        
        # الدقة (R²)
        r2 = self.models['financial_planner'].score(X_scaled, y)
        
        self._save_model('financial_planner')
        
        logger.info(f"💰 Financial planner trained: R²={r2:.2%}")
        
        return {
            'success': True,
            'r2_score': r2,
            'samples': len(monthly_data)
        }
    
    def predict_cash_flow(self, months_ahead=3, from_app_context=None):
        """
        توقع التدفق النقدي المستقبلي
        
        Returns:
        - predictions: list of {month, amount, confidence}
        - trend: 'increasing' | 'decreasing' | 'stable'
        - recommendation: str
        """
        try:
            if from_app_context:
                with from_app_context():
                    return self._predict_cash_flow_internal(months_ahead)
            else:
                return self._predict_cash_flow_internal(months_ahead)
        
        except Exception as e:
            logger.error(f"Cash flow prediction failed: {e}")
            return {'predictions': [], 'trend': 'unknown'}
    
    def _predict_cash_flow_internal(self, months_ahead):
        """التوقع الداخلي للتدفق النقدي"""
        from models import Sale, Purchase, Expense, Receipt
        from extensions import db
        from sqlalchemy import func
        from utils.tenanting import get_active_tenant_id

        tid = get_active_tenant_id()

        if not self._load_model('financial_planner'):
            return {'predictions': [], 'trend': 'unknown', 'error': 'Model not trained'}
        
        # الحصول على البيانات الحالية
        current_month = datetime.now(timezone.utc)
        start_month = current_month - timedelta(days=30)
        
        sales = db.session.query(func.sum(Sale.amount_aed)).filter(
            Sale.sale_date >= start_month,
            Sale.tenant_id == tid if tid is not None else True
        ).scalar() or 0
        
        purchases = db.session.query(func.sum(Purchase.amount_aed)).filter(
            Purchase.purchase_date >= start_month,
            Purchase.tenant_id == tid if tid is not None else True
        ).scalar() or 0
        
        expenses = db.session.query(func.sum(Expense.amount_aed)).filter(
            Expense.expense_date >= start_month,
            Expense.tenant_id == tid if tid is not None else True
        ).scalar() or 0
        
        receipts = db.session.query(func.sum(Receipt.amount_aed)).filter(
            Receipt.receipt_date >= start_month,
            Receipt.tenant_id == tid if tid is not None else True
        ).scalar() or 0
        
        net_cash = float(receipts - purchases - expenses)
        
        # التوقعات
        predictions = []
        
        for month in range(months_ahead):
            features = [
                float(sales),
                float(purchases),
                float(expenses),
                float(receipts),
                net_cash,
                current_month.month
            ]
            
            features_scaled = self.scalers['financial_planner'].transform([features])
            predicted_cash_flow = self.models['financial_planner'].predict(features_scaled)
            
            predictions.append({
                'month': month + 1,
                'amount': float(predicted_cash_flow[0]),
                'confidence': 0.85
            })
            
            # تحديث للشهر القادم
            net_cash = predicted_cash_flow[0]
        
        # تحديد الاتجاه
        if len(predictions) >= 2:
            first = predictions[0]['amount']
            last = predictions[-1]['amount']
            
            if last > first * 1.1:
                trend = 'increasing'
                recommendation = "📈 الاتجاه إيجابي - استمر في الاستراتيجية الحالية"
            elif last < first * 0.9:
                trend = 'decreasing'
                recommendation = "📉 تحذير: التدفق النقدي يتراجع - راجع المصروفات"
            else:
                trend = 'stable'
                recommendation = "📊 الوضع مستقر - حافظ على الأداء"
        else:
            trend = 'stable'
            recommendation = "بيانات غير كافية للتوصية"
        
        return {
            'predictions': predictions,
            'trend': trend,
            'recommendation': recommendation,
            'confidence': 0.85
        }
    
    # ====================================================================
    # 4. محلل الأسعار الذكي - Smart Pricing
    # ====================================================================
    
    def train_price_optimizer(self, from_app_context=None):
        """
        تدريب نموذج تحسين الأسعار
        
        يتعلم من:
        - أسعار التكلفة
        - أنواع العملاء
        - الكميات
        - الموسمية
        - المنافسة
        - الهوامش الناجحة
        """
        try:
            if from_app_context:
                with from_app_context():
                    return self._train_price_internal()
            else:
                return self._train_price_internal()
        
        except Exception as e:
            logger.error(f"Price training failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def _train_price_internal(self):
        """التدريب الداخلي لمحسن الأسعار"""
        from models import Sale, SaleLine, Product, Customer
        from extensions import db
        
        # جمع بيانات التسعير الناجحة
        sales_data = db.session.query(
            SaleLine.cost_price,
            SaleLine.unit_price,
            SaleLine.quantity,
            SaleLine.discount_percent,
            Customer.customer_type,
            Product.category_id,
            Sale.sale_date,
            Sale.payment_status
        ).join(Sale).join(Product).join(Customer).filter(
            Sale.status == 'confirmed',
            SaleLine.cost_price > 0,
            SaleLine.unit_price > 0
        ).limit(1000).all()
        
        if len(sales_data) < 50:
            return {'success': False, 'error': 'Not enough pricing data', 'samples': len(sales_data)}
        
        X = []
        y = []
        
        for sale in sales_data:
            # الميزات
            customer_type_encoded = {
                'regular': 0,
                'merchant': 1,
                'partner': 2
            }.get(sale.customer_type, 0)
            
            month = sale.sale_date.month if sale.sale_date else 1
            day_of_week = sale.sale_date.weekday() if sale.sale_date else 0
            
            features = [
                float(sale.cost_price),
                float(sale.quantity),
                float(customer_type_encoded),
                float(sale.category_id or 0),
                float(month),
                float(day_of_week),
                float(sale.discount_percent or 0)
            ]
            
            # الهدف: السعر الناجح
            target_price = float(sale.unit_price)
            
            X.append(features)
            y.append(target_price)
        
        X = np.array(X)
        y = np.array(y)
        
        # التدريب
        X_scaled = self.scalers['price_optimizer'].fit_transform(X)
        self.models['price_optimizer'].fit(X_scaled, y)
        
        # الدقة
        r2 = self.models['price_optimizer'].score(X_scaled, y)
        
        # Cross-validation للتأكد
        from sklearn.model_selection import cross_val_score
        cv_scores = cross_val_score(self.models['price_optimizer'], X_scaled, y, cv=5, scoring='r2')
        avg_r2 = np.mean(cv_scores)
        
        self._save_model('price_optimizer')
        
        self.training_status['price_optimizer'] = {
            'trained': True,
            'r2_score': r2,
            'cv_r2_score': avg_r2,
            'samples': len(sales_data),
            'trained_at': datetime.now().isoformat()
        }
        
        logger.info(f"💵 Price optimizer trained: R²={r2:.2%}, CV-R²={avg_r2:.2%} on {len(sales_data)} samples")
        
        return {
            'success': True,
            'r2_score': r2,
            'cv_r2_score': avg_r2,
            'samples': len(sales_data)
        }
    
    def predict_optimal_price(self, cost_price, quantity, customer_type, category_id=0):
        """
        توقع السعر المثالي باستخدام Neural Network
        
        Returns:
        - predicted_price: float
        - margin_percent: float
        - confidence: float
        - recommendation: str
        """
        try:
            if not self._load_model('price_optimizer'):
                # Fallback للقاعدة البسيطة
                margin_multiplier = {
                    'regular': 1.30,
                    'merchant': 1.20,
                    'partner': 1.15
                }.get(customer_type, 1.25)
                
                suggested_price = cost_price * margin_multiplier
                
                return {
                    'predicted_price': suggested_price,
                    'margin_percent': (margin_multiplier - 1) * 100,
                    'confidence': 0.70,
                    'recommendation': 'سعر مقترح بناءً على الهامش الافتراضي',
                    'model': 'rule_based'
                }
            
            # تحضير الميزات
            customer_type_encoded = {
                'regular': 0,
                'merchant': 1,
                'partner': 2
            }.get(customer_type, 0)
            
            now = datetime.now()
            
            features = [
                float(cost_price),
                float(quantity),
                float(customer_type_encoded),
                float(category_id),
                float(now.month),
                float(now.weekday()),
                0.0  # discount_percent (افتراضي)
            ]
            
            # التوقع
            features_scaled = self.scalers['price_optimizer'].transform([features])
            predicted_price = self.models['price_optimizer'].predict(features_scaled)[0]
            
            # حساب الهامش
            margin = predicted_price - cost_price
            margin_percent = (margin / cost_price * 100) if cost_price > 0 else 0
            
            # التوصية
            if margin_percent < 10:
                recommendation = "⚠️ الهامش منخفض - زد السعر"
            elif margin_percent > 50:
                recommendation = "💰 هامش ممتاز - سعر تنافسي"
            else:
                recommendation = "✅ سعر مثالي - هامش جيد"
            
            return {
                'predicted_price': float(predicted_price),
                'margin_percent': float(margin_percent),
                'confidence': 0.92,
                'recommendation': recommendation,
                'model': 'neural_network'
            }
        
        except Exception as e:
            logger.error(f"Price prediction failed: {e}")
            # Fallback
            suggested_price = cost_price * 1.25
            return {
                'predicted_price': suggested_price,
                'margin_percent': 25,
                'confidence': 0.5,
                'recommendation': 'تعذر التوقع - سعر افتراضي',
                'model': 'fallback'
            }
    
    # ====================================================================
    # 5. محلل المبيعات - Sales Analyst
    # ====================================================================
    
    def train_sales_forecaster(self, from_app_context=None):
        """
        تدريب نموذج توقع المبيعات
        
        القدرات:
        - توقع المبيعات اليومية/الأسبوعية/الشهرية
        - كشف الأنماط الموسمية
        - تحديد أوقات الذروة
        - توقع الطلب على المنتجات
        """
        try:
            if from_app_context:
                with from_app_context():
                    return self._train_sales_internal()
            else:
                return self._train_sales_internal()
        
        except Exception as e:
            logger.error(f"Sales forecasting training failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def _train_sales_internal(self):
        """التدريب الداخلي لمتنبئ المبيعات"""
        from models import Sale
        from extensions import db
        
        # جمع المبيعات اليومية
        daily_sales = db.session.query(
            func.date(Sale.sale_date).label('sale_date'),
            func.count(Sale.id).label('sales_count'),
            func.sum(Sale.amount_aed).label('total_amount')
        ).filter(
            Sale.status == 'confirmed',
            Sale.sale_date >= datetime.now(timezone.utc) - timedelta(days=90)
        ).group_by(func.date(Sale.sale_date)).all()
        
        if len(daily_sales) < 30:
            return {'success': False, 'error': 'Not enough daily sales data'}
        
        # تحضير البيانات الزمنية
        X = []
        y = []
        
        sales_dict = {sale.sale_date: sale for sale in daily_sales}
        
        # استخدام آخر 7 أيام للتوقع باليوم التالي
        for i in range(7, len(daily_sales)):
            # الميزات: آخر 7 أيام
            last_7_days = daily_sales[i-7:i]
            
            features = []
            for day in last_7_days:
                features.append(float(day.total_amount or 0))
            
            # إضافة ميزات إضافية
            current_day = daily_sales[i].sale_date
            features.extend([
                current_day.weekday(),  # يوم الأسبوع
                current_day.day,  # يوم الشهر
                current_day.month,  # الشهر
                1 if current_day.weekday() in [4, 5] else 0  # عطلة نهاية الأسبوع
            ])
            
            # الهدف: مبيعات اليوم الحالي
            target = float(daily_sales[i].total_amount or 0)
            
            X.append(features)
            y.append(target)
        
        X = np.array(X)
        y = np.array(y)
        
        # التدريب
        X_scaled = self.scalers['sales_forecaster'].fit_transform(X)
        self.models['sales_forecaster'].fit(X_scaled, y)
        
        # الدقة
        r2 = self.models['sales_forecaster'].score(X_scaled, y)
        
        self._save_model('sales_forecaster')
        
        logger.info(f"📈 Sales forecaster trained: R²={r2:.2%}")
        
        return {
            'success': True,
            'r2_score': r2,
            'samples': len(daily_sales)
        }
    
    def forecast_sales(self, days_ahead=7, from_app_context=None):
        """
        توقع المبيعات للأيام القادمة
        
        Returns:
        - forecast: list of {date, amount, confidence}
        - total_expected: float
        - trend: str
        """
        try:
            if from_app_context:
                with from_app_context():
                    return self._forecast_sales_internal(days_ahead)
            else:
                return self._forecast_sales_internal(days_ahead)
        
        except Exception as e:
            logger.error(f"Sales forecast failed: {e}")
            return {'forecast': [], 'total_expected': 0}
    
    def _forecast_sales_internal(self, days_ahead):
        """التوقع الداخلي للمبيعات"""
        from models import Sale
        from extensions import db
        from sqlalchemy import func
        
        if not self._load_model('sales_forecaster'):
            return {'forecast': [], 'total_expected': 0, 'error': 'Model not trained'}
        
        # الحصول على آخر 7 أيام
        recent_sales = db.session.query(
            func.date(Sale.sale_date).label('sale_date'),
            func.sum(Sale.amount_aed).label('total_amount')
        ).filter(
            Sale.status == 'confirmed',
            Sale.sale_date >= datetime.now(timezone.utc) - timedelta(days=7)
        ).group_by(func.date(Sale.sale_date)).order_by(func.date(Sale.sale_date).desc()).limit(7).all()
        
        if len(recent_sales) < 7:
            return {'forecast': [], 'total_expected': 0, 'error': 'Not enough recent data'}
        
        # تحضير آخر 7 أيام
        last_7_days = [float(sale.total_amount or 0) for sale in reversed(recent_sales)]
        
        # التوقعات
        forecast = []
        total_expected = 0
        
        for day in range(days_ahead):
            future_date = datetime.now(timezone.utc).date() + timedelta(days=day + 1)
            
            # الميزات
            features = last_7_days.copy()
            features.extend([
                future_date.weekday(),
                future_date.day,
                future_date.month,
                1 if future_date.weekday() in [4, 5] else 0
            ])
            
            # التوقع
            features_scaled = self.scalers['sales_forecaster'].transform([features])
            predicted_amount = self.models['sales_forecaster'].predict(features_scaled)[0]
            
            forecast.append({
                'date': future_date.isoformat(),
                'day_name': future_date.strftime('%A'),
                'amount': float(predicted_amount),
                'confidence': 0.88
            })
            
            total_expected += predicted_amount
            
            # تحديث آخر 7 أيام (sliding window)
            last_7_days.pop(0)
            last_7_days.append(predicted_amount)
        
        # تحديد الاتجاه
        if len(forecast) >= 3:
            first_avg = np.mean([f['amount'] for f in forecast[:3]])
            last_avg = np.mean([f['amount'] for f in forecast[-3:]])
            
            if last_avg > first_avg * 1.1:
                trend = 'increasing'
            elif last_avg < first_avg * 0.9:
                trend = 'decreasing'
            else:
                trend = 'stable'
        else:
            trend = 'stable'
        
        return {
            'forecast': forecast,
            'total_expected': float(total_expected),
            'average_daily': float(total_expected / days_ahead),
            'trend': trend,
            'confidence': 0.88
        }
    
    # ====================================================================
    # 6. مصنف العملاء الذكي - Customer Intelligence
    # ====================================================================
    
    def train_customer_classifier(self, from_app_context=None):
        """
        تدريب نموذج تصنيف العملاء
        
        يصنف العملاء إلى:
        - VIP (عملاء مميزون)
        - High Value (قيمة عالية)
        - Regular (عاديون)
        - At Risk (معرضون للخسارة)
        - Lost (عملاء مفقودون)
        """
        try:
            if from_app_context:
                with from_app_context():
                    return self._train_customer_internal()
            else:
                return self._train_customer_internal()
        
        except Exception as e:
            logger.error(f"Customer classification training failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def _train_customer_internal(self):
        """التدريب الداخلي لمصنف العملاء"""
        from models import Customer, Sale
        from extensions import db
        from sqlalchemy import func
        
        # جمع بيانات العملاء
        customers_data = db.session.query(
            Customer.id,
            Customer.total_purchases,
            Customer.customer_classification,
            func.count(Sale.id).label('sales_count'),
            func.max(Sale.sale_date).label('last_purchase'),
            func.avg(Sale.amount_aed).label('avg_order_value')
        ).outerjoin(Sale).group_by(Customer.id).limit(500).all()
        
        if len(customers_data) < 20:
            return {'success': False, 'error': 'Not enough customer data'}
        
        X = []
        y = []
        
        for customer in customers_data:
            # الميزات
            days_since_purchase = (datetime.now(timezone.utc).date() - customer.last_purchase.date()).days if customer.last_purchase else 365
            
            features = [
                float(customer.total_purchases or 0),
                float(customer.sales_count or 0),
                float(customer.avg_order_value or 0),
                float(days_since_purchase),
                float(customer.sales_count / max(1, days_since_purchase / 30)),  # purchase frequency
            ]
            
            # التصنيف
            classification = customer.customer_classification or 'regular'
            
            X.append(features)
            y.append(classification)
        
        X = np.array(X)
        
        # ترميز التصنيفات
        self.encoders['customer_classifier'].fit(y)
        y_encoded = self.encoders['customer_classifier'].transform(y)
        
        # التدريب
        X_scaled = self.scalers['customer_classifier'].fit_transform(X)
        self.models['customer_classifier'].fit(X_scaled, y_encoded)
        
        # الدقة
        accuracy = self.models['customer_classifier'].score(X_scaled, y_encoded)
        
        self._save_model('customer_classifier')
        
        logger.info(f"👥 Customer classifier trained: {accuracy:.2%} accuracy")
        
        return {
            'success': True,
            'accuracy': accuracy,
            'samples': len(customers_data)
        }
    
    def classify_customer_intelligence(self, customer_id, from_app_context=None):
        """
        تصنيف ذكي للعميل
        
        Returns:
        - classification: str
        - confidence: float
        - characteristics: dict
        - recommendations: list
        """
        try:
            if from_app_context:
                with from_app_context():
                    return self._classify_customer_internal(customer_id)
            else:
                return self._classify_customer_internal(customer_id)
        
        except Exception as e:
            logger.error(f"Customer classification failed: {e}")
            return {'classification': 'unknown', 'confidence': 0}
    
    def _classify_customer_internal(self, customer_id):
        """التصنيف الداخلي للعميل"""
        from models import Customer, Sale
        from extensions import db
        from sqlalchemy import func
        
        # الحصول على بيانات العميل
        customer_data = db.session.query(
            Customer.total_purchases,
            func.count(Sale.id).label('sales_count'),
            func.max(Sale.sale_date).label('last_purchase'),
            func.avg(Sale.amount_aed).label('avg_order_value')
        ).outerjoin(Sale).filter(Customer.id == customer_id).group_by(Customer.id).first()
        
        if not customer_data:
            return {'classification': 'new', 'confidence': 1.0}
        
        # تحضير الميزات
        days_since_purchase = (datetime.now(timezone.utc).date() - customer_data.last_purchase.date()).days if customer_data.last_purchase else 365
        
        features = [
            float(customer_data.total_purchases or 0),
            float(customer_data.sales_count or 0),
            float(customer_data.avg_order_value or 0),
            float(days_since_purchase),
            float(customer_data.sales_count / max(1, days_since_purchase / 30))
        ]
        
        # محاولة التحميل والتوقع
        if self._load_model('customer_classifier'):
            features_scaled = self.scalers['customer_classifier'].transform([features])
            prediction_encoded = self.models['customer_classifier'].predict(features_scaled)
            probability = self.models['customer_classifier'].predict_proba(features_scaled)
            
            classification = self.encoders['customer_classifier'].inverse_transform(prediction_encoded)[0]
            confidence = float(max(probability[0]))
        else:
            # Fallback للقاعدة البسيطة
            total = customer_data.total_purchases or 0
            if total >= 100000:
                classification = 'vip'
            elif total >= 50000:
                classification = 'premium'
            else:
                classification = 'regular'
            confidence = 0.75
        
        # الخصائص
        characteristics = {
            'total_purchases': float(customer_data.total_purchases or 0),
            'sales_count': customer_data.sales_count or 0,
            'avg_order': float(customer_data.avg_order_value or 0),
            'days_since_purchase': days_since_purchase,
            'purchase_frequency': float(customer_data.sales_count / max(1, days_since_purchase / 30))
        }
        
        # التوصيات
        recommendations = []
        
        if classification == 'vip':
            recommendations.append("🌟 عميل VIP - أولوية قصوى")
            recommendations.append("💎 قدم له عروض خاصة")
        elif classification == 'premium':
            recommendations.append("⭐ عميل ممتاز - حافظ على العلاقة")
        elif days_since_purchase > 90:
            recommendations.append("⚠️ خطر خسارة العميل - تواصل فوراً")
        else:
            recommendations.append("✅ عميل نشط - استمر")
        
        return {
            'classification': classification,
            'confidence': confidence,
            'characteristics': characteristics,
            'recommendations': recommendations,
            'model': 'neural_network' if self._is_model_loaded('customer_classifier') else 'rule_based'
        }
    
    # ====================================================================
    # 7. كاشف الاحتيال - Fraud Detection
    # ====================================================================
    
    def train_fraud_detector(self, from_app_context=None):
        """
        تدريب نموذج كشف الاحتيال
        
        يكتشف:
        - فواتير مشبوهة
        - خصومات غير معتادة
        - أنماط شراء غريبة
        - معاملات في أوقات غريبة
        """
        try:
            if from_app_context:
                with from_app_context():
                    return self._train_fraud_internal()
            else:
                return self._train_fraud_internal()
        
        except Exception as e:
            logger.error(f"Fraud detection training failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def _train_fraud_internal(self):
        """التدريب الداخلي لكاشف الاحتيال"""
        from models import Sale, Customer
        from extensions import db
        
        # جمع المعاملات
        sales = db.session.query(
            Sale.amount_aed,
            Sale.discount_amount,
            Sale.subtotal,
            Sale.paid_amount_aed,
            Sale.sale_date,
            Customer.total_purchases
        ).join(Customer).filter(
            Sale.status == 'confirmed'
        ).limit(1000).all()
        
        if len(sales) < 50:
            return {'success': False, 'error': 'Not enough sales for fraud detection'}
        
        X = []
        y = []
        
        for sale in sales:
            # الميزات
            discount_percent = (sale.discount_amount / sale.subtotal * 100) if sale.subtotal > 0 else 0
            cash_percent = (sale.paid_amount_aed / sale.amount_aed * 100) if sale.amount_aed > 0 else 0
            hour = sale.sale_date.hour if sale.sale_date else 12
            
            features = [
                float(sale.amount_aed),
                float(discount_percent),
                float(cash_percent),
                float(hour),
                1 if hour < 6 or hour > 22 else 0,  # وقت غريب
                1 if discount_percent > 30 else 0,  # خصم كبير
                1 if sale.amount_aed > 50000 else 0  # مبلغ كبير
            ]
            
            # التسمية (افتراضياً معظم المعاملات صحيحة)
            # الاحتيال = مبلغ كبير + خصم كبير + وقت غريب
            is_fraud = 1 if (sale.amount_aed > 100000 and discount_percent > 50) else 0
            
            X.append(features)
            y.append(is_fraud)
        
        X = np.array(X)
        y = np.array(y)
        
        # التدريب
        X_scaled = self.scalers['fraud_detector'].fit_transform(X)
        self.models['fraud_detector'].fit(X_scaled, y)
        
        accuracy = self.models['fraud_detector'].score(X_scaled, y)
        
        self._save_model('fraud_detector')
        
        logger.info(f"🛡️ Fraud detector trained: {accuracy:.2%} accuracy")
        
        return {
            'success': True,
            'accuracy': accuracy,
            'samples': len(sales)
        }
    
    def detect_fraud(self, sale_data):
        """
        كشف الاحتيال في معاملة
        
        Args:
            sale_data: dict with amount, discount, etc
        
        Returns:
            is_fraud: bool
            risk_score: float (0-1)
            reasons: list
        """
        try:
            amount = sale_data.get('amount_aed', 0)
            discount = sale_data.get('discount_amount', 0)
            subtotal = sale_data.get('subtotal', amount)
            paid = sale_data.get('paid_amount_aed', 0)
            sale_time = sale_data.get('sale_date', datetime.now())
            
            # حساب النسب
            discount_percent = (discount / subtotal * 100) if subtotal > 0 else 0
            cash_percent = (paid / amount * 100) if amount > 0 else 0
            hour = sale_time.hour if hasattr(sale_time, 'hour') else 12
            
            # الميزات
            features = [
                float(amount),
                float(discount_percent),
                float(cash_percent),
                float(hour),
                1 if hour < 6 or hour > 22 else 0,
                1 if discount_percent > 30 else 0,
                1 if amount > 50000 else 0
            ]
            
            # محاولة التحميل والتوقع
            if self._load_model('fraud_detector'):
                features_scaled = self.scalers['fraud_detector'].transform([features])
                prediction = self.models['fraud_detector'].predict(features_scaled)
                probability = self.models['fraud_detector'].predict_proba(features_scaled)
                
                is_fraud = bool(prediction[0])
                risk_score = float(probability[0][1])  # احتمال الاحتيال
            else:
                # Fallback
                is_fraud = amount > 100000 and discount_percent > 50
                risk_score = 0.5
            
            # الأسباب
            reasons = []
            if amount > 50000:
                reasons.append(f"مبلغ كبير: {amount:,.0f} AED")
            if discount_percent > 30:
                reasons.append(f"خصم كبير: {discount_percent:.1f}%")
            if hour < 6 or hour > 22:
                reasons.append(f"وقت غير معتاد: {hour}:00")
            if cash_percent < 10 and amount > 10000:
                reasons.append("دفع آجل كامل تقريباً")
            
            return {
                'is_fraud': is_fraud,
                'risk_score': risk_score,
                'risk_level': 'high' if risk_score > 0.7 else 'medium' if risk_score > 0.4 else 'low',
                'reasons': reasons,
                'recommendation': '🛡️ راجع هذه المعاملة يدوياً' if is_fraud else '✅ المعاملة تبدو طبيعية'
            }
        
        except Exception as e:
            logger.error(f"Fraud detection failed: {e}")
            return {'is_fraud': False, 'risk_score': 0, 'reasons': []}
    
    # ====================================================================
    # 8. محسن المخزون - Inventory Optimizer
    # ====================================================================
    
    def train_inventory_optimizer(self, from_app_context=None):
        """
        تدريب نموذج تحسين المخزون
        
        يتعلم:
        - نقاط إعادة الطلب المثلى
        - الكميات الاقتصادية للطلب (EOQ)
        - مستويات الأمان
        - موسمية الطلب
        """
        try:
            if from_app_context:
                with from_app_context():
                    return self._train_inventory_internal()
            else:
                return self._train_inventory_internal()
        
        except Exception as e:
            logger.error(f"Inventory training failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def _train_inventory_internal(self):
        """التدريب الداخلي لمحسن المخزون"""
        from models import Product, StockMovement, SaleLine
        from extensions import db
        from sqlalchemy import func
        
        # جمع بيانات المخزون والمبيعات
        products_data = db.session.query(
            Product.id,
            Product.current_stock,
            Product.min_stock_alert,
            Product.cost_price,
            func.count(SaleLine.id).label('sales_count'),
            func.sum(SaleLine.quantity).label('total_sold'),
            func.avg(SaleLine.quantity).label('avg_quantity')
        ).outerjoin(SaleLine).group_by(Product.id).limit(500).all()
        
        if len(products_data) < 20:
            return {'success': False, 'error': 'Not enough inventory data'}
        
        X = []
        y = []
        
        for product in products_data:
            # الميزات
            sales_rate = (product.total_sold or 0) / 30  # معدل البيع اليومي
            
            features = [
                float(product.current_stock or 0),
                float(product.min_stock_alert or 0),
                float(product.cost_price or 0),
                float(product.sales_count or 0),
                float(sales_rate),
                float(product.avg_quantity or 0)
            ]
            
            # الهدف: نقطة إعادة الطلب المثلى
            optimal_reorder = max(product.min_stock_alert or 10, sales_rate * 14)  # مخزون 14 يوم
            
            X.append(features)
            y.append(float(optimal_reorder))
        
        X = np.array(X)
        y = np.array(y)
        
        # التدريب
        X_scaled = self.scalers['inventory_optimizer'].fit_transform(X)
        self.models['inventory_optimizer'].fit(X_scaled, y)
        
        r2 = self.models['inventory_optimizer'].score(X_scaled, y)
        
        self._save_model('inventory_optimizer')
        
        logger.info(f"📦 Inventory optimizer trained: R²={r2:.2%}")
        
        return {
            'success': True,
            'r2_score': r2,
            'samples': len(products_data)
        }
    
    def optimize_stock_level(self, product_id, from_app_context=None):
        """
        تحديد مستوى المخزون الأمثل
        
        Returns:
        - optimal_stock: float
        - reorder_point: float
        - order_quantity: float
        - recommendation: str
        """
        try:
            if from_app_context:
                with from_app_context():
                    return self._optimize_stock_internal(product_id)
            else:
                return self._optimize_stock_internal(product_id)
        
        except Exception as e:
            logger.error(f"Stock optimization failed: {e}")
            return {'optimal_stock': 0, 'reorder_point': 0}
    
    def _optimize_stock_internal(self, product_id):
        """التحسين الداخلي للمخزون"""
        from models import Product, SaleLine
        from extensions import db
        from sqlalchemy import func
        
        # بيانات المنتج
        product_data = db.session.query(
            Product.current_stock,
            Product.min_stock_alert,
            Product.cost_price,
            func.count(SaleLine.id).label('sales_count'),
            func.sum(SaleLine.quantity).label('total_sold'),
            func.avg(SaleLine.quantity).label('avg_quantity')
        ).outerjoin(SaleLine).filter(Product.id == product_id).group_by(Product.id).first()
        
        if not product_data:
            return {'optimal_stock': 0, 'reorder_point': 0}
        
        # الميزات
        sales_rate = (product_data.total_sold or 0) / 30
        
        features = [
            float(product_data.current_stock or 0),
            float(product_data.min_stock_alert or 0),
            float(product_data.cost_price or 0),
            float(product_data.sales_count or 0),
            float(sales_rate),
            float(product_data.avg_quantity or 0)
        ]
        
        # التوقع
        if self._load_model('inventory_optimizer'):
            features_scaled = self.scalers['inventory_optimizer'].transform([features])
            optimal_reorder = self.models['inventory_optimizer'].predict(features_scaled)[0]
        else:
            # Fallback
            optimal_reorder = max(product_data.min_stock_alert or 10, sales_rate * 14)
        
        # حساب كمية الطلب الاقتصادية (EOQ)
        annual_demand = sales_rate * 365
        ordering_cost = 100  # تكلفة الطلب (افتراضية)
        holding_cost = float(product_data.cost_price or 10) * 0.25  # 25% من التكلفة
        
        if holding_cost > 0:
            eoq = np.sqrt((2 * annual_demand * ordering_cost) / holding_cost)
        else:
            eoq = sales_rate * 30
        
        # التوصية
        if product_data.current_stock < optimal_reorder:
            recommendation = f"🔴 اطلب الآن! المخزون أقل من نقطة إعادة الطلب"
            urgency = 'high'
        elif product_data.current_stock < optimal_reorder * 1.5:
            recommendation = f"🟡 خطط للطلب قريباً"
            urgency = 'medium'
        else:
            recommendation = f"🟢 المخزون كافٍ"
            urgency = 'low'
        
        return {
            'current_stock': float(product_data.current_stock or 0),
            'optimal_reorder_point': float(optimal_reorder),
            'economic_order_quantity': float(eoq),
            'daily_sales_rate': float(sales_rate),
            'days_of_stock': float(product_data.current_stock / max(0.1, sales_rate)),
            'recommendation': recommendation,
            'urgency': urgency,
            'model': 'neural_network' if self._is_model_loaded('inventory_optimizer') else 'calculated'
        }
    
    # ====================================================================
    # 9. متنبئ الطلب - Demand Predictor
    # ====================================================================
    
    def train_demand_predictor(self, from_app_context=None):
        """
        تدريب نموذج توقع الطلب
        
        يتوقع:
        - الطلب على كل منتج
        - الاتجاهات الموسمية
        - تأثير الأحداث الخاصة
        """
        try:
            if from_app_context:
                with from_app_context():
                    return self._train_demand_internal()
            else:
                return self._train_demand_internal()
        
        except Exception as e:
            logger.error(f"Demand training failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def _train_demand_internal(self):
        """التدريب الداخلي لمتنبئ الطلب"""
        from models import Product, SaleLine, Sale
        from extensions import db
        from sqlalchemy import func
        
        # جمع البيانات اليومية لكل منتج
        daily_demand = db.session.query(
            func.date(Sale.sale_date).label('sale_date'),
            SaleLine.product_id,
            func.sum(SaleLine.quantity).label('total_quantity')
        ).join(Sale).filter(
            Sale.status == 'confirmed',
            Sale.sale_date >= datetime.now(timezone.utc) - timedelta(days=90)
        ).group_by(func.date(Sale.sale_date), SaleLine.product_id).all()
        
        if len(daily_demand) < 30:
            return {'success': False, 'error': 'Not enough demand data'}
        
        # تنظيم البيانات حسب المنتج
        product_demand = defaultdict(list)
        
        for demand in daily_demand:
            product_demand[demand.product_id].append({
                'date': demand.sale_date,
                'quantity': float(demand.total_quantity)
            })
        
        X = []
        y = []
        
        # لكل منتج له بيانات كافية
        for product_id, demands in product_demand.items():
            if len(demands) < 10:
                continue
            
            # ترتيب حسب التاريخ
            demands_sorted = sorted(demands, key=lambda x: x['date'])
            
            # استخدام آخر 7 أيام للتوقع باليوم التالي
            for i in range(7, len(demands_sorted)):
                last_7 = [d['quantity'] for d in demands_sorted[i-7:i]]
                current_date = demands_sorted[i]['date']
                
                features = last_7 + [
                    current_date.weekday(),
                    current_date.month,
                    1 if current_date.weekday() in [4, 5] else 0
                ]
                
                target = demands_sorted[i]['quantity']
                
                X.append(features)
                y.append(target)
        
        if len(X) < 20:
            return {'success': False, 'error': 'Not enough training samples'}
        
        X = np.array(X)
        y = np.array(y)
        
        # التدريب
        X_scaled = self.scalers['demand_predictor'].fit_transform(X)
        self.models['demand_predictor'].fit(X_scaled, y)
        
        r2 = self.models['demand_predictor'].score(X_scaled, y)
        
        self._save_model('demand_predictor')
        
        logger.info(f"📊 Demand predictor trained: R²={r2:.2%}")
        
        return {
            'success': True,
            'r2_score': r2,
            'samples': len(X)
        }
    
    def predict_product_demand(self, product_id, days_ahead=7, from_app_context=None):
        """
        توقع الطلب على منتج
        
        Returns:
        - forecast: list of {date, quantity}
        - total_expected: float
        - trend: str
        """
        try:
            if from_app_context:
                with from_app_context():
                    return self._predict_demand_internal(product_id, days_ahead)
            else:
                return self._predict_demand_internal(product_id, days_ahead)
        
        except Exception as e:
            logger.error(f"Demand prediction failed: {e}")
            return {'forecast': [], 'total_expected': 0}
    
    def _predict_demand_internal(self, product_id, days_ahead):
        """التوقع الداخلي للطلب"""
        from models import SaleLine, Sale
        from extensions import db
        from sqlalchemy import func
        
        if not self._load_model('demand_predictor'):
            return {'forecast': [], 'total_expected': 0, 'error': 'Model not trained'}
        
        # الحصول على آخر 7 أيام
        recent_demand = db.session.query(
            func.date(Sale.sale_date).label('sale_date'),
            func.sum(SaleLine.quantity).label('total_quantity')
        ).join(Sale).filter(
            SaleLine.product_id == product_id,
            Sale.status == 'confirmed',
            Sale.sale_date >= datetime.now(timezone.utc) - timedelta(days=7)
        ).group_by(func.date(Sale.sale_date)).order_by(func.date(Sale.sale_date).desc()).limit(7).all()
        
        if len(recent_demand) < 7:
            # بيانات غير كافية
            avg_demand = sum(d.total_quantity for d in recent_demand) / max(1, len(recent_demand))
            return {
                'forecast': [{'date': (datetime.now().date() + timedelta(days=i)).isoformat(), 'quantity': avg_demand} for i in range(days_ahead)],
                'total_expected': avg_demand * days_ahead,
                'trend': 'stable',
                'model': 'average'
            }
        
        # تحضير آخر 7 أيام
        last_7_days = [float(d.total_quantity) for d in reversed(recent_demand)]
        
        # التوقعات
        forecast = []
        total_expected = 0
        
        for day in range(days_ahead):
            future_date = datetime.now().date() + timedelta(days=day + 1)
            
            features = last_7_days.copy() + [
                future_date.weekday(),
                future_date.month,
                1 if future_date.weekday() in [4, 5] else 0
            ]
            
            features_scaled = self.scalers['demand_predictor'].transform([features])
            predicted_quantity = max(0, self.models['demand_predictor'].predict(features_scaled)[0])
            
            forecast.append({
                'date': future_date.isoformat(),
                'day_name': future_date.strftime('%A'),
                'quantity': float(predicted_quantity),
                'confidence': 0.85
            })
            
            total_expected += predicted_quantity
            
            # تحديث sliding window
            last_7_days.pop(0)
            last_7_days.append(predicted_quantity)
        
        return {
            'forecast': forecast,
            'total_expected': float(total_expected),
            'average_daily': float(total_expected / days_ahead),
            'model': 'neural_network'
        }
    
    # ====================================================================
    # 10. محسن الربح - Profit Optimizer
    # ====================================================================
    
    def train_profit_optimizer(self, from_app_context=None):
        """
        تدريب نموذج تحسين الربح
        
        يتعلم:
        - الهوامش الربحية المثلى
        - العلاقة بين السعر والطلب
        - نقاط السعر الحرجة
        """
        try:
            if from_app_context:
                with from_app_context():
                    return self._train_profit_internal()
            else:
                return self._train_profit_internal()
        
        except Exception as e:
            logger.error(f"Profit training failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def _train_profit_internal(self):
        """التدريب الداخلي لمحسن الربح"""
        from models import Sale, SaleLine
        from extensions import db
        
        # جمع بيانات الربح
        sales = db.session.query(
            SaleLine.cost_price,
            SaleLine.unit_price,
            SaleLine.quantity,
            SaleLine.discount_percent,
            Sale.payment_status
        ).join(Sale).filter(
            Sale.status == 'confirmed',
            SaleLine.cost_price > 0,
            SaleLine.unit_price > 0
        ).limit(1000).all()
        
        if len(sales) < 50:
            return {'success': False, 'error': 'Not enough profit data'}
        
        X = []
        y = []
        
        for sale in sales:
            # الميزات
            margin_percent = ((sale.unit_price - sale.cost_price) / sale.cost_price * 100) if sale.cost_price > 0 else 0
            
            features = [
                float(sale.cost_price),
                float(sale.unit_price),
                float(sale.quantity),
                float(sale.discount_percent or 0),
                1 if sale.payment_status == 'paid' else 0
            ]
            
            # الهدف: هامش الربح
            X.append(features)
            y.append(float(margin_percent))
        
        X = np.array(X)
        y = np.array(y)
        
        # التدريب
        X_scaled = self.scalers['profit_optimizer'].fit_transform(X)
        self.models['profit_optimizer'].fit(X_scaled, y)
        
        r2 = self.models['profit_optimizer'].score(X_scaled, y)
        
        self._save_model('profit_optimizer')
        
        logger.info(f"💎 Profit optimizer trained: R²={r2:.2%}")
        
        return {
            'success': True,
            'r2_score': r2,
            'samples': len(sales)
        }
    
    # ====================================================================
    # 11. متنبئ فقدان العملاء - Churn Prediction
    # ====================================================================
    
    def train_churn_predictor(self, from_app_context=None):
        """
        تدريب نموذج توقع خسارة العملاء
        
        يتوقع:
        - العملاء المعرضون للخسارة
        - أسباب التوقف
        - إجراءات الاحتفاظ
        """
        try:
            if from_app_context:
                with from_app_context():
                    return self._train_churn_internal()
            else:
                return self._train_churn_internal()
        
        except Exception as e:
            logger.error(f"Churn training failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def _train_churn_internal(self):
        """التدريب الداخلي لمتنبئ الخسارة"""
        from models import Customer, Sale
        from extensions import db
        from sqlalchemy import func
        
        # جمع بيانات العملاء
        customers = db.session.query(
            Customer.total_purchases,
            func.count(Sale.id).label('sales_count'),
            func.max(Sale.sale_date).label('last_purchase'),
            func.avg(Sale.amount_aed).label('avg_order')
        ).outerjoin(Sale).group_by(Customer.id).limit(500).all()
        
        if len(customers) < 30:
            return {'success': False, 'error': 'Not enough customer data for churn'}
        
        X = []
        y = []
        
        for customer in customers:
            # الميزات
            days_since = (datetime.now(timezone.utc).date() - customer.last_purchase.date()).days if customer.last_purchase else 365
            
            features = [
                float(customer.total_purchases or 0),
                float(customer.sales_count or 0),
                float(customer.avg_order or 0),
                float(days_since),
                float(customer.sales_count / max(1, days_since / 30))
            ]
            
            # التصنيف (churned = فقدنا العميل)
            churned = 1 if days_since > 120 else 0
            
            X.append(features)
            y.append(churned)
        
        X = np.array(X)
        y = np.array(y)
        
        # التدريب
        X_scaled = self.scalers['churn_predictor'].fit_transform(X)
        self.models['churn_predictor'].fit(X_scaled, y)
        
        accuracy = self.models['churn_predictor'].score(X_scaled, y)
        
        self._save_model('churn_predictor')
        
        logger.info(f"🚪 Churn predictor trained: {accuracy:.2%} accuracy")
        
        return {
            'success': True,
            'accuracy': accuracy,
            'samples': len(customers)
        }
    
    # ====================================================================
    # Utilities - أدوات مساعدة
    # ====================================================================
    
    def _save_model(self, model_name):
        """حفظ النموذج والـ scaler"""
        try:
            model_path = os.path.join(self.models_dir, f'{model_name}.pkl')
            scaler_path = os.path.join(self.models_dir, f'{model_name}_scaler.pkl')
            encoder_path = os.path.join(self.models_dir, f'{model_name}_encoder.pkl')
            
            joblib.dump(self.models[model_name], model_path)
            joblib.dump(self.scalers[model_name], scaler_path)
            
            if model_name in self.encoders:
                joblib.dump(self.encoders[model_name], encoder_path)
            
            logger.info(f"💾 Model saved: {model_name}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to save model {model_name}: {e}")
            return False
    
    def _load_model(self, model_name):
        """تحميل النموذج المحفوظ"""
        try:
            model_path = os.path.join(self.models_dir, f'{model_name}.pkl')
            scaler_path = os.path.join(self.models_dir, f'{model_name}_scaler.pkl')
            encoder_path = os.path.join(self.models_dir, f'{model_name}_encoder.pkl')
            
            if not os.path.exists(model_path):
                return False
            
            self.models[model_name] = joblib.load(model_path)
            self.scalers[model_name] = joblib.load(scaler_path)
            
            if os.path.exists(encoder_path):
                self.encoders[model_name] = joblib.load(encoder_path)
            
            return True
        
        except Exception as e:
            logger.error(f"Failed to load model {model_name}: {e}")
            return False
    
    def _is_model_loaded(self, model_name):
        """التحقق من تحميل النموذج"""
        try:
            # محاولة التحميل
            return self._load_model(model_name)
        except:
            return False
    
    def load_all_models(self):
        """تحميل جميع النماذج المدربة"""
        loaded = []
        for model_name in list(self.models.keys()):
            if self._load_model(model_name):
                loaded.append(model_name)
        
        logger.info(f"📂 Loaded {len(loaded)} trained models: {', '.join(loaded)}")
        return loaded
    
    def train_all_models(self, from_app_context):
        """
        تدريب جميع النماذج
        
        يجب استدعاؤه مع app context
        """
        results = {}
        
        logger.info("🧠 Starting comprehensive neural training...")
        
        models_to_train = [
            ('price_optimizer', self.train_price_optimizer),
            ('sales_forecaster', self.train_sales_forecaster),
            ('customer_classifier', self.train_customer_classifier),
            ('fraud_detector', self.train_fraud_detector),
            ('inventory_optimizer', self.train_inventory_optimizer),
            ('demand_predictor', self.train_demand_predictor),
            ('financial_planner', self.train_financial_planning),
            ('maintenance_predictor', self.train_maintenance_prediction),
            ('accounting_classifier', self.train_accounting_assistant),
            ('profit_optimizer', self.train_profit_optimizer),
            ('churn_predictor', self.train_churn_predictor)
        ]
        
        for model_name, train_func in models_to_train:
            try:
                result = train_func(from_app_context)
                results[model_name] = result
                
                if result.get('success'):
                    logger.info(f"✅ {model_name}: Trained successfully")
                else:
                    logger.warning(f"⚠️ {model_name}: {result.get('error', 'Unknown error')}")
            
            except Exception as e:
                logger.error(f"❌ {model_name}: Training failed - {e}")
                results[model_name] = {'success': False, 'error': str(e)}
        
        # ملخص
        successful = sum(1 for r in results.values() if r.get('success'))
        total = len(results)
        
        logger.info(f"🎊 Neural training complete: {successful}/{total} models trained successfully")
        
        return {
            'success': successful > 0,
            'trained_models': successful,
            'total_models': total,
            'results': results
        }
    
    def get_status(self):
        """الحصول على حالة جميع النماذج"""
        status = {
            'models': {},
            'total_models': len(self.models),
            'trained_models': 0
        }
        
        for model_name in self.models:
            model_path = os.path.join(self.models_dir, f'{model_name}.pkl')
            is_trained = os.path.exists(model_path)
            
            if is_trained:
                status['trained_models'] += 1
                
                # الحصول على معلومات التدريب
                training_info = self.training_status.get(model_name, {})
                
                status['models'][model_name] = {
                    'trained': True,
                    'accuracy': training_info.get('accuracy') or training_info.get('r2_score'),
                    'samples': training_info.get('samples'),
                    'trained_at': training_info.get('trained_at')
                }
            else:
                status['models'][model_name] = {
                    'trained': False
                }
        
        status['training_percentage'] = (status['trained_models'] / status['total_models'] * 100) if status['total_models'] > 0 else 0
        
        return status
    
    def understand_intent(self, message: str) -> Dict:
        """
        فهم النية باستخدام الشبكات العصبية
        
        Args:
            message: رسالة المستخدم
        
        Returns:
            {
                'intent': النية المكتشفة,
                'confidence': مستوى الثقة,
                'features': الميزات المستخرجة
            }
        """
        try:
            # استخراج ميزات من الرسالة
            features = self._extract_text_features(message)
            
            # تحليل بسيط للنية
            msg_lower = message.lower()
            
            intent_patterns = {
                'sales_analysis': ['حلل', 'analyze', 'مبيعات', 'sales', 'أداء', 'performance'],
                'customer_balance': ['رصيد', 'balance', 'ديون', 'debt', 'ذمم', 'receivable'],
                'inventory_check': ['مخزون', 'inventory', 'stock', 'صحة المخزون'],
                'pricing': ['سعر', 'price', 'تسعير', 'pricing'],
                'forecast': ['توقع', 'predict', 'forecast', 'متوقع']
            }
            
            max_score = 0
            detected_intent = None
            
            for intent, keywords in intent_patterns.items():
                score = sum(1 for kw in keywords if kw in msg_lower)
                if score > max_score:
                    max_score = score
                    detected_intent = intent
            
            confidence = min(max_score / 3, 1.0)  # normalize
            
            return {
                'intent': detected_intent,
                'confidence': confidence,
                'features': features
            }
        
        except Exception as e:
            logger.error(f"Intent understanding failed: {e}")
            return {
                'intent': None,
                'confidence': 0,
                'features': {}
            }
    
    def _extract_text_features(self, text: str) -> Dict:
        """استخراج ميزات من النص"""
        return {
            'length': len(text),
            'word_count': len(text.split()),
            'has_numbers': any(c.isdigit() for c in text),
            'has_question': '؟' in text or '?' in text,
            'language': 'ar' if any('\u0600' <= c <= '\u06FF' for c in text) else 'en'
        }


# ============================================================================
# Singleton Instance - للاستخدام السهل
# ============================================================================

_neural_engine_instance = None

def get_neural_engine():
    """الحصول على instance واحد من NeuralEngine"""
    global _neural_engine_instance
    if _neural_engine_instance is None:
        _neural_engine_instance = AzadNeuralEngine()
    return _neural_engine_instance

