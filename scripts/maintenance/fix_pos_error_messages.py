import re

path = r'D:\Data\karaj\UAE\Azad-UAE\routes\pos.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old = '''    except ValueError:
        return jsonify({"success": False, "error": "تعذر إنشاء الفاتورة من البيانات المرسلة."}), 400
    except Exception:
        return jsonify(
            {"success": False, "error": "فشل إنشاء الفاتورة. تحقق من البيانات وحاول مرة أخرى."}
        ), 500'''

new = '''    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        current_app.logger.error(f"POS checkout error: {exc}")
        return jsonify(
            {"success": False, "error": "فشل إنشاء الفاتورة. تحقق من البيانات وحاول مرة أخرى."}
        ), 500'''

if old in content:
    content = content.replace(old, new)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Fixed POS error messages")
else:
    print("Pattern not found")
