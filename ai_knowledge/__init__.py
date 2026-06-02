"""
🤖 AI Knowledge Base - قاعدة معرفة أزاد
المساعد الذكي الخبير في المحاسبة والمعدات الثقيلة

Reorganized structure:
- core/: Core AI systems (learning, memory, context, reasoning)
- knowledge/: Knowledge bases (system, company, parts, automotive, tax, customs)
- analytics/: Analytics & predictions
- personality/: Personality & responses
- neural/: Neural & ML components
- agents/: Multi-agent systems
- learning/: Learning modules
- improvement/: Self-improvement
- expansion/: Knowledge expansion
- generation/: Content generation
- specialized/: Specialized modules
- data/training/: JSON training files
- data/models/: Model files
- data/expanded/: Expanded knowledge data
- memory/: Memory system
"""
import os

# تحديد المسار المطلق لمجلد المعرفة
AI_KNOWLEDGE_DIR = os.path.dirname(os.path.abspath(__file__))

def get_knowledge_path(filename):
    """الحصول على المسار المطلق لملف داخل مجلد المعرفة
    
    For backward compatibility, checks multiple locations:
    1. data/training/ (for JSON training files)
    2. data/models/ (for model files)
    3. data/expanded/ (for expanded knowledge)
    4. memory/ (for memory files)
    5. Root directory (fallback)
    """
    # Check data/training first (most common for JSON files)
    training_path = os.path.join(AI_KNOWLEDGE_DIR, 'data', 'training', filename)
    if os.path.exists(training_path):
        return training_path
    
    # Check data/models for model files
    models_path = os.path.join(AI_KNOWLEDGE_DIR, 'data', 'models', filename)
    if os.path.exists(models_path):
        return models_path
    
    # Check data/expanded for expanded knowledge
    expanded_path = os.path.join(AI_KNOWLEDGE_DIR, 'data', 'expanded', filename)
    if os.path.exists(expanded_path):
        return expanded_path
    
    # Check memory directory
    memory_path = os.path.join(AI_KNOWLEDGE_DIR, 'memory', filename)
    if os.path.exists(memory_path):
        return memory_path
    
    # Fallback to root directory
    return os.path.join(AI_KNOWLEDGE_DIR, filename)

def get_training_path(filename):
    """الحصول على المسار المطلق لملف تدريب في data/training/"""
    return os.path.join(AI_KNOWLEDGE_DIR, 'data', 'training', filename)

def get_model_path(filename):
    """الحصول على المسار المطلق لملف نموذج في data/models/"""
    return os.path.join(AI_KNOWLEDGE_DIR, 'data', 'models', filename)

def get_expanded_path(filename):
    """الحصول على المسار المطلق لملف معرفة موسعة في data/expanded/"""
    return os.path.join(AI_KNOWLEDGE_DIR, 'data', 'expanded', filename)
