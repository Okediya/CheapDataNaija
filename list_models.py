import google.generativeai as genai
from config import GOOGLE_API_KEY
genai.configure(api_key=GOOGLE_API_KEY)
for m in genai.list_models():
    if "flash" in m.name:
        print(m.name)
