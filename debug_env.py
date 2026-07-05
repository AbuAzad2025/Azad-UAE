import os
from dotenv import load_dotenv
load_dotenv('.env')
print(f"SECRET_KEY: {os.environ.get('SECRET_KEY')}")
