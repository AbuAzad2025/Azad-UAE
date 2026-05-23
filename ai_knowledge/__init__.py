"""
🤖 AI Knowledge Base - قاعدة معرفة أزاد
المساعد الذكي الخبير في المحاسبة والمعدات الثقيلة
"""
import os

# تحديد المسار المطلق لمجلد المعرفة
AI_KNOWLEDGE_DIR = os.path.dirname(os.path.abspath(__file__))

def get_knowledge_path(filename):
    """الحصول على المسار المطلق لملف داخل مجلد المعرفة"""
    return os.path.join(AI_KNOWLEDGE_DIR, filename)
