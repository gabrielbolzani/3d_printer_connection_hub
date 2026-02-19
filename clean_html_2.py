import re
import os

file_path = r"c:\Users\Gabriel\Documents\GitHub\AditivaFlow\acessorios\3dprinters_Hub\PythonHub\templates\index.html"

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix broken template literals with ANY amount of whitespace between $ and { and }
# Handle cases like $ { var } or $ { \n var \n }
# Pattern: \$ followed by optional whitespace, then \{, then optional whitespace (including newlines), then variable, then optional whitespace, then \}
content = re.sub(r'\$\s*\{\s*([\w\.]+)\s*\}', r'${\1}', content, flags=re.MULTILINE | re.DOTALL)

# Handle the case where the variable itself is a complex expression (optional, but good for totalL > 0 ? ...)
# We'll be careful with this one.
# For now, let's fix the specific one: $ { totalL > 0 ? `${layer} / ${totalL} ` : '--' }
# Since I can't easily regex complex nested templates, I'll fix the common ones.

# Fix the rest of the known issues
content = re.sub(r'\}\s+\[sc\]', r'}[sc]', content)
content = content.replace(r"\\' ", r"\\'")
content = re.sub(r'\}\s+;', r'};', content)

# Fix the specific broken one for layer
content = re.sub(r'\$\s*\{\s*totalL\s*>\s*0\s*\?\s*`\${\s*layer\s*}\s*/\${\s*totalL\s*}`\s*:\s*\'--\'\s*\}', r"${totalL > 0 ? `${layer}/${totalL}` : '--'}", content, flags=re.MULTILINE | re.DOTALL)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Second cleanup complete.")
