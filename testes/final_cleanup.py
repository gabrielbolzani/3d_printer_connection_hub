import re
import os

file_path = r"c:\Users\Gabriel\Documents\GitHub\AditivaFlow\acessorios\3dprinters_Hub\PythonHub\templates\index.html"

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix corrupted Jinja tags at the end
content = re.sub(r'</script>\s*\{\s*%\s*endblock\s*%\s*\}', '</script>\n{% endblock %}', content, flags=re.MULTILINE | re.DOTALL)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Final cleanup complete.")
