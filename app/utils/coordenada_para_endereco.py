import requests

def coordenada_para_endereco(lat, lon):
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=18&addressdetails=1"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=8)
        if r.status_code == 200:
            data = r.json()
            if 'display_name' in data:
                return data['display_name']
        return "Endereço não encontrado"
    except Exception:
        return "Endereço não encontrado"