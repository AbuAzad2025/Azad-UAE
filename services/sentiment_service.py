from typing import Dict


class SentimentAnalyzer:
    POSITIVE_WORDS_AR = [
        "ممتاز",
        "رائع",
        "جيد",
        "مذهل",
        "عظيم",
        "ممكن",
        "شكرا",
        "أحسنت",
        "متميز",
        "نظيف",
        "سريع",
        "دقيق",
        "محترف",
        "موثوق",
        "صادق",
    ]

    NEGATIVE_WORDS_AR = [
        "سيء",
        "فظيع",
        "مزعج",
        "متأخر",
        "غالي",
        "رديء",
        "ضعيف",
        "سيئ",
        "مشكلة",
        "خطأ",
        "عطل",
        "تأخير",
        "غش",
        "احتيال",
        "مرفوض",
    ]

    POSITIVE_WORDS_EN = [
        "excellent",
        "great",
        "good",
        "amazing",
        "wonderful",
        "perfect",
        "thank",
        "outstanding",
        "clean",
        "fast",
        "accurate",
        "professional",
        "reliable",
        "honest",
    ]

    NEGATIVE_WORDS_EN = [
        "bad",
        "terrible",
        "awful",
        "late",
        "expensive",
        "poor",
        "weak",
        "problem",
        "error",
        "issue",
        "delay",
        "fraud",
        "scam",
        "rejected",
        "worst",
    ]

    @staticmethod
    def analyze(text: str) -> Dict:
        if not text:
            return {
                "polarity": 0.0,
                "subjectivity": 0.0,
                "sentiment": "neutral",
                "confidence": 0.0,
            }

        text_lower = text.lower()

        positive_count = sum(
            1 for word in SentimentAnalyzer.POSITIVE_WORDS_AR if word in text_lower
        )
        positive_count += sum(
            1 for word in SentimentAnalyzer.POSITIVE_WORDS_EN if word in text_lower
        )

        negative_count = sum(
            1 for word in SentimentAnalyzer.NEGATIVE_WORDS_AR if word in text_lower
        )
        negative_count += sum(
            1 for word in SentimentAnalyzer.NEGATIVE_WORDS_EN if word in text_lower
        )

        total_sentiment_words = positive_count + negative_count
        total_words = len(text_lower.split())

        if total_sentiment_words == 0:
            polarity = 0.0
            sentiment = "neutral"
            confidence = 0.0
        else:
            polarity = (positive_count - negative_count) / total_sentiment_words
            if polarity > 0.2:
                sentiment = "positive"
            elif polarity < -0.2:
                sentiment = "negative"
            else:
                sentiment = "neutral"
            confidence = min(total_sentiment_words / max(total_words, 1), 1.0)

        subjectivity = total_sentiment_words / max(total_words, 1)

        return {
            "polarity": round(polarity, 2),
            "subjectivity": round(subjectivity, 2),
            "sentiment": sentiment,
            "confidence": round(confidence, 2),
            "positive_words": positive_count,
            "negative_words": negative_count,
        }

    @staticmethod
    def analyze_customer_feedback(customer_id: int) -> Dict:
        from models import Sale

        sales = Sale.query.filter_by(customer_id=customer_id).all()

        all_notes = []
        for sale in sales:
            if sale.notes:
                all_notes.append(sale.notes)

        if not all_notes:
            return {"overall_sentiment": "neutral", "feedback_count": 0}

        combined_text = " ".join(all_notes)
        sentiment = SentimentAnalyzer.analyze(combined_text)

        return {
            "overall_sentiment": sentiment["sentiment"],
            "polarity": sentiment["polarity"],
            "confidence": sentiment["confidence"],
            "feedback_count": len(all_notes),
        }
