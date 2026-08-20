with open('tests/vitest/app_global_enhanced.test.js', encoding='utf-8') as f:
    content = f.read()

# The correct $ function definition
old_bad = '''  const $ = (sel) => {
    if (typeof sel === 'function') return api([]).ready(sel);
    if (sel && sel.nodeType) return api([sel]);
    if (sel && sel[0] && sel[0].nodeType) return sel;
    if (typeof sel === 'string') {
      const trimmed = sel.trim();
      if (trimmed.startsWith('<') && trimmed.endsWith('>')) {
        const tmp = document.createElement('div');
        tmp.innerHTML = trimmed;
        return api(Array.from(tmp.children));
      }
      return api(Array.from(document.querySelectorAll(sel)));
    }
    return api([]);
  };

  $.fn = {};
    if (typeof sel === 'function') return api([]).ready(sel);
    if (sel && sel.nodeType) return api([sel]);
    if (sel && sel[0] && sel[0].nodeType) return sel;
    if (typeof sel === 'string') {
      const trimmed = sel.trim();
      if (trimmed.startsWith('<') && trimmed.endsWith('>')) {
        const tmp = document.createElement('div');
        tmp.innerHTML = trimmed;
        return api(Array.from(tmp.children));
      }
      return api(Array.from(document.querySelectorAll(sel)));
    }
    return api([]);
  };
    if (typeof sel === 'function') return api([]).ready(sel);
    if (sel && sel.nodeType) return api([sel]);
    if (sel && sel[0] && sel[0].nodeType) return sel;
    if (typeof sel === 'string') {
      const trimmed = sel.trim();
      if (trimmed.startsWith('<') && trimmed.endsWith('>')) {
        const tmp = document.createElement('div');
        tmp.innerHTML = trimmed;
        return api(Array.from(tmp.children));
      }
      return api(Array.from(document.querySelectorAll(sel)));
    }
    return api([]);
  };'''

new_good = '''  const $ = (sel) => {
    if (typeof sel === 'function') return api([]).ready(sel);
    if (sel && sel.nodeType) return api([sel]);
    if (sel && sel[0] && sel[0].nodeType) return sel;
    if (typeof sel === 'string') {
      const trimmed = sel.trim();
      if (trimmed.startsWith('<') && trimmed.endsWith('>')) {
        const tmp = document.createElement('div');
        tmp.innerHTML = trimmed;
        return api(Array.from(tmp.children));
      }
      return api(Array.from(document.querySelectorAll(sel)));
    }
    return api([]);
  };

  $.fn = {};'''

if old_bad in content:
    content = content.replace(old_bad, new_good)
    print("Fixed duplicate")
else:
    print("Pattern not found, trying simpler approach")
    # Find all occurrences of "const $ = (sel) => {" and keep only the first one
    lines = content.split('\n')
    result = []
    found_dollar_func = False
    in_dollar_func = False
    brace_count = 0
    skip_until_semicolon = False
    
    i = 0
    while i < len(lines):
        line = lines[i]
        if 'const $ = (sel) => {' in line and not found_dollar_func:
            found_dollar_func = True
            in_dollar_func = True
            brace_count = 1
            result.append(line)
            i += 1
            continue
        
        if in_dollar_func:
            result.append(line)
            # Count braces to find end of function
            brace_count += line.count('{') - line.count('}')
            if brace_count == 0 and line.strip().endswith(';'):
                in_dollar_func = False
                # Skip any subsequent duplicate $ function definitions
                # Look ahead for another "const $ = (sel) => {"
                j = i + 1
                while j < len(lines) and 'const $ = (sel) => {' not in lines[j]:
                    j += 1
                if j < len(lines):
                    # Found another $ function - skip it and everything up to $.fn = {};
                    k = j
                    while k < len(lines) and '$.fn = {};' not in lines[k]:
                        k += 1
                    # Skip from j to k (inclusive if it's $.fn)
                    if k < len(lines):
                        i = k  # Will be incremented at end of loop
            i += 1
            continue
        
        # Skip duplicate $ function bodies
        if 'const $ = (sel) => {' in line:
            # Skip this and everything until $.fn = {};
            j = i
            while j < len(lines) and '$.fn = {};' not in lines[j]:
                j += 1
            if j < len(lines):
                i = j  # Will be incremented
            else:
                i += 1
            continue
            
        result.append(line)
        i += 1
    
    content = '\n'.join(result)

with open('tests/vitest/app_global_enhanced.test.js', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done")
