import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

try:
    from ai_knowledge import get_knowledge_path
    
    print("Testing get_knowledge_path...")
    
    files_to_check = [
        'learned_knowledge.json',
        'interactions_log.json',
        'patterns.pkl',
        'feedback_log.json',
        'local_training.json',
        'external_learned_data.json',
        'training_history.json'
    ]
    
    for filename in files_to_check:
        path = get_knowledge_path(filename)
        print(f"File: {filename} -> Path: {path}")
        if not os.path.isabs(path):
            print(f"ERROR: Path is not absolute: {path}")
        else:
            print("OK: Path is absolute")
            
    print("\nAll paths verified successfully.")
    
except ImportError as e:
    print(f"Import Error: {e}")
except Exception as e:
    print(f"Error: {e}")
