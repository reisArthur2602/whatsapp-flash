import os
from dotenv import load_dotenv
import pytz

load_dotenv()

TZ = pytz.timezone('America/Sao_Paulo')

FTP_HOST = os.getenv("FTP_HOST")
FTP_USER = os.getenv("FTP_USER")
FTP_PASS = os.getenv("FTP_PASS")

WEEKDAY_CODE = {0:'SEG',1:'TER',2:'QUA',3:'QUI',4:'SEX',5:'SAB',6:'DOM'}

FTP_CONFIG =  {
    "host": os.getenv("FTP_HOST"),
    "user": os.getenv("FTP_USER"),
    "password": os.getenv("FTP_PASS"),
}

WHATSAPP_CONFIG =  {
    "instance_id": os.getenv("ZAPI_INSTANCE_ID"),
    "instance_token": os.getenv("ZAPI_INSTANCE_TOKEN"),
    "client_token": os.getenv("ZAPI_CLIENT_TOKEN"),
}

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME")
}

TOLERANCIA_MINUTOS = 15

estado_usuario = {}
ultima_atividade_usuario = {}
pendencias_atraso_por_supervisor = {}

url_whatsapp_api = os.getenv("URL_API_WHATSAPP")