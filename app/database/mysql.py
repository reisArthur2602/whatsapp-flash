import mysql.connector
import logging
from config import DB_CONFIG

def conectar_mysql():
    try: 
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        logging.error(f"Erro ao conectar no MySQL: {e}")
        return None
