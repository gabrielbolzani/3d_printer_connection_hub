import re

file_path = r"c:\Users\Gabriel\Documents\GitHub\AditivaFlow\acessorios\3dprinters_Hub\PythonHub\templates\index.html"

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "MODAL" in line or "<!--" in line or "< !--" in line:
        print(f"Line {i+1}: {repr(line)}")
