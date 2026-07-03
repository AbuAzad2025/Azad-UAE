with open('routes/ai.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add import re after import os
content = content.replace('import os\nfrom flask', 'import os\nimport re\nfrom flask')

with open('routes/ai.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed: added import re at module level")
