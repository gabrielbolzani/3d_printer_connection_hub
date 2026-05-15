import gzip
import json
import os

path = r"C:\Users\Gabriel\Documents\GitHub\ha-bambulab-main\ha-bambulab-main\custom_components\bambu_lab\pybambu\hms_error_text\hms_en.json.gz"
prefix = "050002000003"

if os.path.exists(path):
    with gzip.open(path, "rb") as f:
        data = json.load(f)
        for cat in data:
            for code in data[cat]:
                if code.startswith(prefix):
                    print(f"{cat} {code}: {json.dumps(data[cat][code], indent=2)}")
else:
    print("File not found")
