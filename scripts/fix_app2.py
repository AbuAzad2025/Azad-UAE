with open('static/js/app.js', encoding='utf-8') as f:
    content = f.read()

# Find the last occurrence of "})(jQuery);" and insert exports before it
marker = '})(jQuery);'
if marker not in content:
    print("Marker not found")
    exit(1)

# Replace the last occurrence
idx = content.rfind(marker)
exports = '''\n\t// Expose key functions for testability\n\twindow.showNotification = showNotification;\n\twindow.showSystemAlert = showSystemAlert;\n\twindow.saveFormData = saveFormData;\n\twindow.performSearch = performSearch;\n'''

new_content = content[:idx] + exports + content[idx:]

with open('static/js/app.js', 'w', encoding='utf-8') as f:
    f.write(new_content)

print("Done")
