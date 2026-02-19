import re

file_path = r"c:\Users\Gabriel\Documents\GitHub\AditivaFlow\acessorios\3dprinters_Hub\PythonHub\templates\index.html"

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the broken comment start
content = content.replace("< !--", "<!--")

# Remove those specific long comment lines that are causing visual clutter
# They look like <!-- ════════...════════ -->
content = re.sub(r'<!-- ════════+ .*? ════════+ -->', '', content)

# Clean up any residual markers I might have left
content = re.sub(r'<!═══+ .*? ═══+>', '', content)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Cleanup script 4 done.")
