import re
import os

file_path = r"c:\Users\Gabriel\Documents\GitHub\AditivaFlow\acessorios\3dprinters_Hub\PythonHub\templates\index.html"

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix broken template literals like $ {\n p.name \n }
# This regex looks for $ then optional space, then { then optional space/newline, then a variable name (can include dots), then optional space/newline, then }
content = re.sub(r'\$\s*\{\s*([\w\.]+)\s*\}', r'${\1}', content, flags=re.MULTILINE)

# Some are even more broken with multiple newlines
content = re.sub(r'\$\s*\{\s*([\w\.]+)\s*\}', r'${\1}', content)

# Fix the badgeCls [sc] being on a new line
content = re.sub(r'\}\s+\[sc\]', r'}[sc]', content)

# Fix the esc function replace space
content = content.replace(r"\\' ", r"\\'")

# Fix semicolon on new line
content = re.sub(r'\}\s+;', r'};', content)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Cleanup complete.")
