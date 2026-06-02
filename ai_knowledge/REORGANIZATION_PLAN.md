# AI Knowledge Directory Reorganization Plan

## Current Structure Issues
- 46 Python files mixed in root directory
- JSON training files scattered
- Model files mixed with code
- No clear separation of concerns
- Difficult to add new training data

## Proposed Structure

```
ai_knowledge/
├── __init__.py                    # Main package init
│
├── core/                          # Core AI systems
│   ├── __init__.py
│   ├── learning_system.py         # Main learning system
│   ├── memory_system.py           # Memory management
│   ├── context_engine.py          # Context handling
│   ├── conversation_manager.py    # Conversation flow
│   └── reasoning_engine.py       # AI reasoning
│
├── knowledge/                     # Knowledge bases
│   ├── __init__.py
│   ├── system_knowledge.py        # System-specific knowledge
│   ├── company_info.py            # Company information
│   ├── parts_knowledge.py         # Auto parts knowledge
│   ├── automotive_ecu_knowledge.py # ECU diagnostics
│   ├── tax_customs_knowledge.py   # Tax & customs
│   └── customs.py                 # Customs procedures
│
├── analytics/                     # Analytics & predictions
│   ├── __init__.py
│   ├── data_analyzer.py           # Data analysis
│   ├── analytics_predictions.py   # Predictive analytics
│   └── market_insights.py         # Market intelligence
│
├── personality/                   # Personality & responses
│   ├── __init__.py
│   ├── azad_personality.py       # AI personality
│   ├── azad_responses.py         # Response templates
│   ├── dialects.py                # Language dialects
│   └── beginners_mode.py         # Beginner-friendly mode
│
├── neural/                        # Neural & ML components
│   ├── __init__.py
│   ├── neural_engine.py          # Neural network engine
│   ├── transformers_brain.py     # Transformers integration
│   ├── semantic_matcher.py       # Semantic matching
│   └── vision_processor.py       # Vision processing
│
├── agents/                        # Multi-agent systems
│   ├── __init__.py
│   ├── multi_agent_system.py     # Multi-agent coordination
│   ├── intelligent_assistant.py  # Main assistant agent
│   └── master_brain.py           # Master brain controller
│
├── learning/                      # Learning modules
│   ├── __init__.py
│   ├── continuous_learner.py     # Continuous learning
│   ├── quick_learner.py          # Quick learning
│   ├── auto_retraining.py        # Auto-retraining
│   └── external_learning.py      # External data learning
│
├── improvement/                   # Self-improvement
│   ├── __init__.py
│   ├── self_improvement.py       # Self-improvement logic
│   ├── self_reflection.py        # Self-reflection
│   └── improvement_goals.json     # Improvement goals
│
├── expansion/                     # Knowledge expansion
│   ├── __init__.py
│   ├── knowledge_expansion.py     # Knowledge expansion
│   ├── knowledge_sources.py       # Knowledge sources
│   └── global_knowledge.py        # Global knowledge
│
├── generation/                    # Content generation
│   ├── __init__.py
│   ├── document_generator.py     # Document generation
│   └── code_generator.py         # Code generation
│
├── specialized/                   # Specialized modules
│   ├── __init__.py
│   ├── advanced_laws.py          # Advanced laws knowledge
│   ├── security_rules.py         # Security rules
│   ├── system_guide.py           # System guide
│   ├── user_guide.py             # User guide
│   ├── customer_service.py      # Customer service
│   └── tax_system.py            # Tax system
│
├── data/                          # Data files (separated from code)
│   ├── training/                  # JSON training files
│   │   ├── .gitkeep
│   │   ├── learned_knowledge.json
│   │   ├── interactions_log.json
│   │   ├── self_improvement.json
│   │   ├── intensive_learning_results.json
│   │   ├── auto_learning_log.json
│   │   ├── local_training.json
│   │   └── performance_metrics.json
│   │
│   ├── models/                    # Model files
│   │   ├── .gitkeep
│   │   └── patterns.pkl
│   │
│   └── expanded/                 # Expanded knowledge data
│       └── (move expanded_knowledge/ here)
│
└── memory/                        # Memory system (existing)
    ├── .gitkeep
    ├── README.md
    ├── episodic_memory.json
    └── episodic_memory.example.json
```

## Migration Steps

1. Create new directory structure
2. Move Python files to appropriate subdirectories
3. Move JSON files to data/training/
4. Move model files to data/models/
5. Move expanded_knowledge/ to data/expanded/
6. Update __init__.py files for proper imports
7. Update all import statements in affected files
8. Test the reorganized structure

## Benefits

- Clear separation of concerns
- Easy to add new training data to data/training/
- Easy to add new models to data/models/
- Organized code structure
- Better maintainability
- No file clutter in root directory
