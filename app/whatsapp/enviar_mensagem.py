import requests

import logging
from config import WHATSAPP_CONFIG , url_whatsapp_api


url = f"{url_whatsapp_api}/enviar-mensagem"

def enviar_mensagem(numero, mensagem):

    if not numero.startswith("55"):
        numero = "55" + numero
    try:
        url 
        headers = {"Content-Type":"application/json","Client-Token": WHATSAPP_CONFIG['client_token']}
        payload = {"phone": numero, "message": mensagem}
        requests.post(url, json=payload, headers=headers, timeout=10)
        
    except Exception as e:
        logging.error(f"Erro ao enviar mensagem: {e}")