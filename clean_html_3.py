import re
import os

file_path = r"c:\Users\Gabriel\Documents\GitHub\AditivaFlow\acessorios\3dprinters_Hub\PythonHub\templates\index.html"

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix broken template literals with ANY content inside ${ }
# This one is more permissive with the content inside the braces
# It matches $ followed by optional space, then {, then optional space/newline, then ANYTHING that is not a }, then optional space/newline, then }
content = re.sub(r'\$\s*\{\s*(.*?)\s*\}', r'${\1}', content, flags=re.MULTILINE | re.DOTALL)

# Clean up any residual spaces in common expressions
content = content.replace(r'${ p.state || \'unknown\' }', r"${p.state || 'unknown'}")
content = content.replace(r'${ enabled ? \'checked\' : \'\' }', r"${enabled ? 'checked' : ''}")

# Fix the badgeCls and esc again just in case
content = re.sub(r'\}\s+\[sc\]', r'}[sc]', content)
content = content.replace(r"\\' ", r"\\'")
content = re.sub(r'\}\s+;', r'};', content)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Third cleanup complete.")
