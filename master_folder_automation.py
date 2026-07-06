# This script automates the process of copying the models.py, views.py, forms.py, and utils.py files from each Django app into a centralized "master_backend" directory for documentation purposes. It creates the necessary subdirectories and renames the files to include the app name for clarity. This helps in organizing the code snippets in the documentation while keeping the original project structure intact.
import os, shutil

base = "docs/master_backend"
for module in (
    "signals",
    "models",
    "views",
    "forms",
    "utils",
    "admin",
    "urls",
    "resources",
):
    os.makedirs(os.path.join(base, module), exist_ok=True)

for app in os.listdir("."):
    for module in (
        "signals",
        "models",
        "views",
        "forms",
        "utils",
        "admin",
        "urls",
        "resources",
    ):
        src = os.path.join(app, f"{module}.py")
        if os.path.isfile(src):
            dst = os.path.join(base, module, f"{app}_{module}.py")
            shutil.copy(src, dst)
            print(f"copied {src}")
