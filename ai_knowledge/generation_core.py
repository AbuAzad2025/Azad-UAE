"""
Consolidated module: generation_core.py
Re-exports from ai_knowledge.generation sub-package (single source of truth).
"""

from ai_knowledge.generation.document_generator import DocumentGenerator, document_generator
from ai_knowledge.generation.code_generator import CodeGenerator, get_code_generator

__all__ = [
    'DocumentGenerator', 'document_generator',
    'CodeGenerator', 'get_code_generator',
]
