import os
import re

# Use the directory where this script is located
base_dir = os.path.dirname(os.path.abspath(__file__))
os.makedirs(os.path.join(base_dir, "templates"), exist_ok=True)
os.makedirs(os.path.join(base_dir, "static"), exist_ok=True)

app_path = os.path.join(base_dir, "app.py")
with open(app_path, "r", encoding="utf-8") as f:
    app_text = f.read()

# Extract HTML string (HTML = r"""...""")
match = re.search(r'HTML = r"""(.*?)"""', app_text, re.DOTALL)
if not match:
    print("Could not find HTML block in app.py")
    exit(1)

html_content = match.group(1)

# Extract CSS
css_match = re.search(r'<style>(.*?)</style>', html_content, re.DOTALL)
if css_match:
    css_content = css_match.group(1).strip()
    with open(os.path.join(base_dir, "static", "style.css"), "w", encoding="utf-8") as f:
        f.write(css_content)
    html_content = re.sub(r'<style>.*?</style>', '<link rel="stylesheet" href="{{ url_for(\'static\', filename=\'style.css\') }}">', html_content, flags=re.DOTALL)

# Extract JS
js_match = re.search(r'<script>(.*?)</script>', html_content, re.DOTALL)
if js_match:
    js_content = js_match.group(1).strip()
    with open(os.path.join(base_dir, "static", "script.js"), "w", encoding="utf-8") as f:
        f.write(js_content)
    html_content = re.sub(r'<script>.*?</script>', '<script src="{{ url_for(\'static\', filename=\'script.js\') }}"></script>', html_content, flags=re.DOTALL)

# Write index.html
with open(os.path.join(base_dir, "templates", "index.html"), "w", encoding="utf-8") as f:
    f.write(html_content)

# Update app.py
# Remove HTML variable definition
app_text = re.sub(r'HTML = r""".*?"""\n+', '', app_text, flags=re.DOTALL)

if 'render_template' not in app_text:
    app_text = app_text.replace('from flask import Flask, request, jsonify', 'from flask import Flask, request, jsonify, render_template')

app_text = app_text.replace('return HTML', 'return render_template("index.html")')
app_text = app_text.replace('app.run(debug=True,port=5000)', 'app.run(debug=True,port=5002)')

with open(app_path, "w", encoding="utf-8") as f:
    f.write(app_text)

print("Split completed successfully!")
