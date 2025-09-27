import requests
import os

def enviar_mensagem(telefone, mensagem):
    token = os.getenv("ZAPI_TOKEN")
    instancia = os.getenv("ZAPI_INSTANCE")
    url = f"https://api.z-api.io/instances/{instancia}/token/{token}/send-text"

    payload = {
        "phone": telefone,
        "message": mensagem
    }

    print(f"📤 Enviando mensagem para {telefone}: {mensagem}")
    print(f"🔗 URL: {url}")
    print(f"📦 Payload: {payload}")

    try:
        response = requests.post(url, json=payload)
        print(f"📬 Resposta da Z-API: {response.status_code} - {response.text}")
        response.raise_for_status()
    except Exception as e:
        print(f"❌ Erro ao enviar mensagem: {e}")
