import os
import json
from google import genai

api_key = os.environ.get('GEMINI_API_KEY')
client = genai.Client(api_key=api_key)

print('--- Available Models ---')
try:
    for m in client.models.list():
        print(f'Model: {m.name}')
    
    target = os.environ.get('GEMINI_MODEL', 'gemini-1.5-flash')
    print(f'\n--- Testing Generation with: {target} ---')
    response = client.models.generate_content(model=target, contents='hi')
    print(f'Response: {response.text}')
except Exception as e:
    print(f'Error: {e}')
