from app.ftp.adapter import ftp_upload_adapter

base_path = "/public_html/ponto"


def upload_ftp_documento(local, name):
    if ftp_upload_adapter(local, base_path + "documentos", name):
        return f"https://mastertelecom-claro.com.br/ponto/documentos/{name}"
    return None

def upload_ftp_imagem_rosto(local, name):
    if ftp_upload_adapter(local, base_path + "imagem_rosto", name):
        return f"https://mastertelecom-claro.com.br/ponto/imagem_rosto/{name}"
    return None

def upload_ftp_relatorio(local, name):
    if ftp_upload_adapter(local, base_path + "documentos", name):
        return f"https://mastertelecom-claro.com.br/ponto/relatorios/{name}"
    return None