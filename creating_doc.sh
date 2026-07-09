rm -rf docs/master_backend/
python master_folder_automation.py
python concat_to_markdown.py --default models
python concat_to_markdown.py --default utils
python concat_to_markdown.py --default signals
python concat_to_markdown.py --default urls
python concat_to_markdown.py --default forms
python concat_to_markdown.py --default views