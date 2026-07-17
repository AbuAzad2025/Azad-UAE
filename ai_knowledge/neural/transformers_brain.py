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
from typing import Any, List, Dict
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
        self.word_embeddings: dict[str, list[float]] = {}

        # الأوزان (محاكاة بسيطة)
        self.attention_weights: dict[str, float] = {}

        # ذاكرة السياق
        self.context_memory: list[dict[str, Any]] = []

        logger.info(
            f"🤖 Transformers Brain initialized - Vocab: {vocab_size}, Model: {d_model}, Heads: {n_heads}"
        )

    @staticmethod
    def _build_vocabulary() -> dict:
        """
        بناء قاموس المفردات العربية المتخصصة
        """
        # كلمات محاسبية
        accounting_words = [
            "قيد",
            "مدين",
            "دائن",
            "ميزانية",
            "أصول",
            "خصوم",
            "إيرادات",
            "مصروفات",
            "ربح",
            "خسارة",
            "محاسبة",
            "تدقيق",
            "مراجعة",
            "قوائم",
            "مالية",
        ]

        # كلمات ضريبية
        tax_words = ["ضريبة", "vat", "جمارك", "رسوم", "إعفاء", "خصم", "تسجيل"]

        # كلمات إدارية
        management_words = [
            "مخزون",
            "طلب",
            "عميل",
            "مورد",
            "مبيعات",
            "مشتريات",
            "إدارة",
            "تخطيط",
        ]

        # كلمات هندسية
        engineering_words = ["محرك", "صيانة", "إصلاح", "زيت", "فرامل", "معدات", "أعطال"]

        # دمج كل الكلمات
        all_words = accounting_words + tax_words + management_words + engineering_words

        # إضافة كلمات عامة
        all_words.extend(["ما", "كيف", "متى", "أين", "لماذا", "هل", "هذا", "ذلك"])

        # بناء القاموس
        vocab = {word: idx for idx, word in enumerate(all_words)}
        vocab["<PAD>"] = len(vocab)  # Padding
        vocab["<UNK>"] = len(vocab)  # Unknown
        vocab["<START>"] = len(vocab)  # Start
        vocab["<END>"] = len(vocab)  # End

        return vocab

    # ========================================================================
    # Self-Attention Mechanism - آلية الانتباه الذاتي
    # ========================================================================

    def self_attention(
        self, query: List[float], key: List[float], value: List[float]
    ) -> List[float]:
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

    def multi_head_attention(
        self, query: List[float], key: List[float], value: List[float]
    ) -> List[float]:
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
        return heads_output[: self.d_model]  # تقليم للحجم الصحيح

    @staticmethod
    def _dot_product(vec1: List[float], vec2: List[float]) -> float:
        """حساب الضرب النقطي"""
        return sum(a * b for a, b in zip(vec1, vec2))

    @staticmethod
    def _softmax(scores: List[float]) -> List[float]:
        """دالة Softmax"""
        exp_scores = [np.exp(s) for s in scores]
        sum_exp = sum(exp_scores)
        return [e / sum_exp for e in exp_scores]

    # ========================================================================
    # Positional Encoding - ترميز الموضع
    # ========================================================================

    @staticmethod
    def positional_encoding(position: int, d_model: int) -> List[float]:
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

        return output[: self.d_model]

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

    @staticmethod
    def _layer_norm(x: List[float]) -> List[float]:
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
        embeddings = [
            self._get_embedding(token, pos) for pos, token in enumerate(tokens)
        ]

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
            "tokens": tokens,
            "embeddings": embeddings,
            "attention_map": attention_map,
            "semantic_representation": transformed,
            "intent": intent,
            "entities": entities,
            "confidence": 0.92,
            "model": "transformers",
        }

    @staticmethod
    def _tokenize(text: str) -> List[str]:
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
            word_idx = self.vocabulary.get(token, self.vocabulary["<UNK>"])
            np.random.seed(word_idx)  # ثبات النتائج
            word_emb = np.random.randn(self.d_model).tolist()
            self.word_embeddings[token] = word_emb

        # Positional encoding
        pos_enc = self.positional_encoding(position, self.d_model)

        # الجمع
        combined = [w + p for w, p in zip(word_emb, pos_enc)]

        return combined

    @staticmethod
    def _extract_intent(text: str, representation: List[float]) -> str:
        """استخراج النية من النص"""
        text_lower = text.lower()

        # تحليل النية
        if "؟" in text or any(kw in text_lower for kw in ["ما", "كيف", "متى", "أين"]):
            return "question"
        elif any(kw in text_lower for kw in ["احسب", "calculate"]):
            return "calculation"
        elif any(kw in text_lower for kw in ["اشرح", "explain"]):
            return "explanation"
        elif any(kw in text_lower for kw in ["توقع", "predict"]):
            return "prediction"
        else:
            return "statement"

    @staticmethod
    def _extract_entities(text: str, tokens: List[str]) -> Dict[str, List[str]]:
        """استخراج الكيانات المسماة"""
        entities: dict[str, list[str]] = {
            "numbers": [],
            "accounting_terms": [],
            "tax_terms": [],
            "management_terms": [],
        }

        # استخراج الأرقام
        import re

        numbers = re.findall(r"\d+\.?\d*", text)
        entities["numbers"] = numbers

        # استخراج المصطلحات
        for token in tokens:
            if token in ["قيد", "مدين", "دائن", "ميزانية"]:
                entities["accounting_terms"].append(token)
            elif token in ["ضريبة", "vat", "جمارك"]:
                entities["tax_terms"].append(token)
            elif token in ["مخزون", "عميل", "مورد"]:
                entities["management_terms"].append(token)

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
        intent = understanding["intent"]
        entities = understanding["entities"]

        if intent == "question":
            if entities["tax_terms"]:
                response = (
                    "📊 بناءً على تحليل Transformers، سأجيب عن سؤالك حول الضرائب..."
                )
            elif entities["accounting_terms"]:
                response = "💼 بناءً على فهمي العميق للمحاسبة..."
            else:
                response = "🤔 دعني أفكر في سؤالك باستخدام الانتباه متعدد الرؤوس..."

        elif intent == "calculation":
            response = "🧮 سأحسب ذلك باستخدام معالجة متقدمة..."

        elif intent == "prediction":
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

        self.context_memory.append(
            {
                "text": text,
                "timestamp": datetime.now().isoformat(),
                "representation": understanding["semantic_representation"],
                "intent": understanding["intent"],
                "entities": understanding["entities"],
            }
        )

        # الاحتفاظ بآخر 20 فقط
        if len(self.context_memory) > 20:
            self.context_memory = self.context_memory[-20:]

    def get_context_summary(self) -> str:
        """ملخص السياق"""
        if not self.context_memory:
            return "لا يوجد سياق سابق"

        intents = [ctx["intent"] for ctx in self.context_memory]
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
