from flask import Flask, request, jsonify
from dotenv import load_dotenv
import os
import mysql.connector
import requests
from datetime import datetime, timedelta, time
from math import radians, sin, cos, sqrt, atan2
from ftplib import FTP
from urllib.request import urlopen
from reportlab.pdfgen import canvas
import pytz
import logging
from threading import Thread
import time as time_mod

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

logging.basicConfig(level=logging.INFO)
load_dotenv()
app = Flask(__name__)
estado_usuario = {}
last_user_activity = {}
pendencias_atraso_por_supervisor = {}

TZ = pytz.timezone('America/Sao_Paulo')

FTP_HOST = "147.93.64.78"
FTP_USER = "u588900443.mastertelecom-claro.com.br"
FTP_PASS = "Mastertelecom@2025"

WEEKDAY_CODE = {0:'SEG',1:'TER',2:'QUA',3:'QUI',4:'SEX',5:'SAB',6:'DOM'}

TOLERANCIA_MINUTOS = 15

def enviar_mensagem(numero, mensagem):
    if not numero.startswith("55"):
        numero = "55" + numero
    try:
        iid   = os.getenv("ZAPI_INSTANCE_ID")
        itok  = os.getenv("ZAPI_INSTANCE_TOKEN")
        ctok  = os.getenv("ZAPI_CLIENT_TOKEN")
        url   = f"https://api.z-api.io/instances/{iid}/token/{itok}/send-text"
        headers = {"Content-Type":"application/json","Client-Token":ctok}
        payload = {"phone": numero, "message": mensagem}
        requests.post(url, json=payload, headers=headers, timeout=10)
    except Exception as e:
        logging.error(f"Erro ao enviar mensagem: {e}")

def calcular_distancia(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi, dlam = radians(lat2-lat1), radians(lon2-lon1)
    a = sin(dphi/2)**2 + cos(phi1)*cos(phi2)*sin(dlam/2)**2
    return 2 * R * atan2(sqrt(a), sqrt(1-a))

def conectar_mysql():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME")
    )

def ftp_upload(local, remote_dir, name):
    try:
        ftp = FTP(FTP_HOST)
        ftp.login(FTP_USER, FTP_PASS)
        ftp.cwd(remote_dir)
        with open(local,'rb') as f:
            ftp.storbinary(f"STOR {name}", f)
        ftp.quit()
        return True
    except Exception as e:
        logging.error(f"FTP {remote_dir}: {e}")
        return False

def upload_ftp_documento(local, name):
    if ftp_upload(local, "/public_html/ponto/documentos", name):
        return f"https://mastertelecom-claro.com.br/ponto/documentos/{name}"
    return None

def upload_ftp_imagem_rosto(local, name):
    if ftp_upload(local, "/public_html/ponto/imagem_rosto", name):
        return f"https://mastertelecom-claro.com.br/ponto/imagem_rosto/{name}"
    return None

def upload_ftp_relatorio(local, name):
    if ftp_upload(local, "/public_html/ponto/relatorios", name):
        return f"https://mastertelecom-claro.com.br/ponto/relatorios/{name}"
    return None

def timedelta_to_time(td):
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return time(hours, minutes, seconds)

def converter_hora_para_time(hora_db):
    if not hora_db:
        return None
    if isinstance(hora_db, str):
        try:
            return datetime.strptime(hora_db, "%H:%M:%S").time()
        except ValueError:
            try:
                return datetime.strptime(hora_db, "%H:%M").time()
            except Exception:
                return None
    elif isinstance(hora_db, timedelta):
        return timedelta_to_time(hora_db)
    elif isinstance(hora_db, time):
        return hora_db
    else:
        return None

def buscar_horarios_do_grupo(cursor, group_id, dia_semana):
    dia_semana = str(dia_semana).strip().upper()
    logging.info(f"Consultando group_id={group_id}, dia_semana='{dia_semana}'")
    cursor.execute(
        "SELECT horario1, horario2, horario3, horario4 FROM schedule_group_items WHERE group_id=%s AND dia_semana=%s",
        (group_id, dia_semana)
    )
    row = cursor.fetchone()
    logging.info(f"DEBUG SQL - row={row}")
    horarios = []
    if row:
        for h in row.values():
            if not h or h == '00:00:00':
                continue
            hora_local = converter_hora_para_time(h)
            if hora_local:
                horarios.append(hora_local.strftime("%H:%M:%S"))
    return horarios

def esta_no_horario_permitido(horarios, horario_atual):
    tolerancia = timedelta(minutes=TOLERANCIA_MINUTOS)
    dt_atual = datetime.combine(datetime.today(), horario_atual)
    for h_str in horarios:
        try:
            h_dt = datetime.strptime(h_str, "%H:%M:%S").time()
            dt_h = datetime.combine(datetime.today(), h_dt)
            diferenca = abs((dt_h - dt_atual).total_seconds())
            if diferenca <= tolerancia.total_seconds():
                return True
        except Exception as e:
            logging.error(f"Erro na validação do horário {h_str}: {e}")
    return False

def gerar_pdf_completo(func, mes, ano, cursor, path):
    from calendar import monthrange
    c = canvas.Canvas(path, pagesize=(600, 820))
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, 800, f"Relatório de Ponto: {func['nome']} - {mes:02d}/{ano}")
    c.setFont("Helvetica", 11)
    y = 780
    last_day = monthrange(ano, mes)[1]
    for dia in range(1, last_day+1):
        data_str = f"{ano}-{mes:02d}-{dia:02d}"
        data_dt = datetime.strptime(data_str, "%Y-%m-%d")
        dow = WEEKDAY_CODE[data_dt.weekday()]
        cursor.execute(
            "SELECT * FROM ponto_registro WHERE funcionario_id=%s AND DATE(data_hora)=%s",
            (func['id'], data_str)
        )
        pontos = cursor.fetchall()
        c.setFont("Helvetica-Bold", 11)
        c.drawString(35, y, f"Dia {dia:02d}/{mes:02d}/{ano} - {dow}")
        y -= 16
        c.setFont("Helvetica", 10)
        if pontos:
            for p in sorted(pontos, key=lambda x:x['data_hora']):
                dt = p['data_hora']
                if isinstance(dt, str):
                    dt = datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")
                c.drawString(75, y, f"Ponto: {dt.strftime('%H:%M:%S')} - Status: {p['status']} - {p['distancia_metros']:.1f}m")
                y -= 13
        y -= 6
        c.line(35, y, 540, y)
        y -= 12
        if y < 60:
            c.showPage()
            c.setFont("Helvetica-Bold", 14)
            c.drawString(40, 800, f"Relatório de Ponto: {func['nome']} - {mes:02d}/{ano}")
            y = 780
            c.setFont("Helvetica", 11)
    c.save()

def monitor_inatividade(intervalo=60, tempo_oi=300, tempo_encerrar=420):
    while True:
        agora = time_mod.time()
        for tel, last in list(last_user_activity.items()):
            if tel in estado_usuario:
                tempo_parado = agora - last
                user_state = estado_usuario[tel]
                if user_state.get("stage") in (
                    "menu", "awaiting_location", "awaiting_mes_ano", "awaiting_documento", "awaiting_delay_location",
                    "awaiting_delay_reason", "awaiting_out_loc_photo", "awaiting_extra_photo", "awaiting_out_both_photo",
                    "awaiting_foto", "awaiting_doc_observacao", "awaiting_extra_location", "awaiting_extra_location_photo",
                    "awaiting_pendencia_resposta"
                ):
                    if  tempo_oi < tempo_parado < tempo_encerrar and not user_state.get('inatividade_avisada'):
                        enviar_mensagem(tel, "👋 Oi, você ainda está aí? Responda ou a conversa será encerrada em instantes.")
                        estado_usuario[tel]['inatividade_avisada'] = True
                    elif tempo_parado >= tempo_encerrar:
                        enviar_mensagem(tel, "⏰ Sua sessão foi encerrada por inatividade. Digite qualquer coisa para recomeçar.")
                        estado_usuario.pop(tel, None)
                        last_user_activity.pop(tel, None)
        time_mod.sleep(intervalo)

Thread(target=monitor_inatividade, daemon=True).start()

def buscar_telefone_supervisor(cursor, supervisor_id):
    cursor.execute("SELECT telefone FROM usuarios_rh WHERE id=%s AND ativo=1", (supervisor_id,))
    row = cursor.fetchone()
    if row:
        return row['telefone']
    return None

# =======================
# HELPERS DE NOTIFICAÇÃO
# =======================

def get_admin_rh_phones(cursor):
    """Retorna todos os telefones de RH e ADMIN ativos."""
    cursor.execute("""
        SELECT telefone 
        FROM usuarios_rh 
        WHERE ativo=1 AND tipo_usuario IN ('rh','admin')
    """)
    return [r['telefone'] for r in cursor.fetchall() if r.get('telefone')]

def get_supervisor_phone_for_func(cursor, funcionario):
    """Retorna o telefone do supervisor do funcionário (se existir e ativo)."""
    sid = funcionario.get('supervisor_id')
    if not sid:
        return None
    cursor.execute("SELECT telefone FROM usuarios_rh WHERE id=%s AND ativo=1", (sid,))
    row = cursor.fetchone
    # bug fix: row() vs fetchone above
    row = cursor.fetchone()
    return row['telefone'] if row and row.get('telefone') else None

def notificar_doc_option3(cursor, funcionario, mensagem):
    """
    Regra:
      - RH e ADMIN SEMPRE recebem
      - Supervisor SOMENTE se for o supervisor do funcionário
      - Nunca o próprio funcionário (se ele existir em usuarios_rh)
    """
    telefones = set(get_admin_rh_phones(cursor))
    tel_sup = get_supervisor_phone_for_func(cursor, funcionario)
    if tel_sup:
        telefones.add(tel_sup)

    # remove telefone do próprio funcionário, caso conste em usuarios_rh
    if funcionario.get('telefone'):
        telefones.discard(funcionario['telefone'])

    for t in telefones:
        if t:
            enviar_mensagem(t, mensagem)

@app.route("/webhook", methods=["POST"])
def webhook():
    dados = request.get_json()
    logging.info(f"Payload recebido: {dados}")

    tel = dados.get("phone", "").replace("55", "", 1)
    msg = dados.get("text", {}).get("message", "").strip().lower()
    last_user_activity[tel] = time_mod.time()
    if tel in estado_usuario and 'inatividade_avisada' in estado_usuario[tel]:
        estado_usuario[tel].pop('inatividade_avisada', None)

    try:
        conn = conectar_mysql()
        cursor = conn.cursor(dictionary=True, buffered=True)
    except Exception as e:
        logging.error(e)
        enviar_mensagem(tel, "❌ Erro de conexão ao banco.")
        return jsonify(status="db_error")

    # Responder pendencia de atraso para supervisor (aprovar ou negar)
    if tel in estado_usuario and estado_usuario[tel].get('stage') == 'awaiting_pendencia_resposta':
        resp = msg.strip()
        pendencia = estado_usuario[tel].get('pendencia_info')
        if not pendencia:
            enviar_mensagem(tel, "⚠️ Pendência não encontrada.")
            estado_usuario.pop(tel)
            return jsonify(status="pendencia_nao_encontrada")

        func_tel = pendencia['func_telefone']
        func_nome = pendencia['func_nome']
        pend_id = pendencia['pendencia_id']

        try:
            if resp == '1':
                cursor.execute(
                    "UPDATE atrasos_funcionario SET status=1, respondido_por=%s, respondido_em=NOW() WHERE id=%s",
                    (tel, pend_id)
                )
                conn.commit()
                enviar_mensagem(func_tel, f"✅ Seu pedido de atraso foi *APROVADO* pelo supervisor.")
                enviar_mensagem(tel, "✅ Você aprovou o atraso.")
            elif resp == '2':
                cursor.execute(
                    "UPDATE atrasos_funcionario SET status=2, respondido_por=%s, respondido_em=NOW() WHERE id=%s",
                    (tel, pend_id)
                )
                conn.commit()
                enviar_mensagem(func_tel, f"❌ Seu pedido de atraso foi *NEGADO* pelo supervisor.")
                enviar_mensagem(tel, "✅ Você negou o atraso.")
            else:
                enviar_mensagem(tel, "❌ Opção inválida. Responda 1 para Aprovar ou 2 para Negar.")
                return jsonify(status="resposta_invalida")
        except Exception as e:
            logging.error(f"Erro ao atualizar pendência: {e}")
            enviar_mensagem(tel, "❌ Erro ao processar sua resposta.")
            return jsonify(status="erro_resposta")

        # Remove pendência da fila e do estado
        pendencias = pendencias_atraso_por_supervisor.get(tel, [])
        pendencias = [p for p in pendencias if p['pendencia_id'] != pend_id]
        pendencias_atraso_por_supervisor[tel] = pendencias
        estado_usuario.pop(tel, None)

        # Enviar próxima pendência, se houver
        if pendencias:
            prox = pendencias[0]
            texto_pend = (
                f"🚨 Funcionário *{prox['func_nome']}* notificou atraso.\n"
                f"Motivo: {prox['motivo']}\n"
                f"Endereço: {prox['endereco']}\n\n"
                "Responda:\n1 - Aprovar\n2 - Negar"
            )
            enviar_mensagem(tel, texto_pend)
            estado_usuario[tel] = {
                'stage': 'awaiting_pendencia_resposta',
                'pendencia_info': prox
            }
        return jsonify(status="pendencia_respondida")

    # Consulta funcionário pelo telefone
    cursor.execute(
        "SELECT id, group_id, nome, telefone, razao_social, cnpj, pis, supervisor_id FROM funcionarios WHERE telefone=%s",
        (tel,)
    )
    func = cursor.fetchone()
    if not func:
        enviar_mensagem(tel, "❌ Funcionário não encontrado.")
        return jsonify(status="no_func")

    cursor.execute("SELECT ativo FROM funcionario_status WHERE funcionario_id=%s ORDER BY id DESC LIMIT 1", (func['id'],))
    st = cursor.fetchone()
    if not st or st['ativo'] == 0:
        enviar_mensagem(tel, "🚫 Seu usuário está inativo. Consulte o RH.")
        return jsonify(status="func_inativo")

    state = estado_usuario.get(tel, {})
    stage = state.get("stage")

    # Menu inicial
    if not stage:
        enviar_mensagem(
            tel,
            "📋 *Menu*:\n"
            "1 – Registrar ponto\n"
            "2 – Relatório\n"
            "3 – Documento\n"
            "4 – Notificar atraso\n"
            "5 – Solicitar liberação fora de horário\n"
            "Digite 1–5."
        )
        estado_usuario[tel] = {"stage": "menu"}
        return jsonify(status="menu_sent")

    if stage == "menu":
        if msg == "1":
            enviar_mensagem(tel, "📍 Envie sua localização para registrar ponto.")
            estado_usuario[tel] = {"stage": "awaiting_location"}
        elif msg == "2":
            enviar_mensagem(tel, "📅 Informe mês/ano (MM/AAAA):")
            estado_usuario[tel] = {"stage": "awaiting_mes_ano"}
        elif msg == "3":
            enviar_mensagem(tel, "📎 Envie documento (PDF ou imagem).")
            estado_usuario[tel] = {"stage": "awaiting_documento"}
        elif msg == "4":
            enviar_mensagem(tel, "📍 Envie sua localização para notificar atraso.")
            estado_usuario[tel] = {"stage": "awaiting_delay_location"}
        elif msg == "5":
            enviar_mensagem(tel, "📍 Envie sua localização para solicitar liberação fora do horário.")
            estado_usuario[tel] = {"stage": "awaiting_extra_location"}
        else:
            enviar_mensagem(tel, "❌ Opção inválida. Digite 1–5.")
        return jsonify(status="menu_processed")

    # =====================================
    # Validação de localização nos 3 fluxos
    # =====================================

    # 1. Registrar ponto (awaiting_location)
    if stage == "awaiting_location":
        if 'text' in dados and any(
            x in dados['text'].get('message', '').lower() for x in [
                "https://goo.gl/maps", "https://maps.app.goo.gl", "maps.google.com", "mapa.app.goo.gl", "wa.me/p/", "http", ".com", ".br", "waze.com"
            ]
        ):
            enviar_mensagem(
                tel,
                "❌ Envie sua localização usando o botão de *clipe* > *Localização* > *Enviar minha localização atual* pelo WhatsApp.\n\n*Não cole links ou envie locais pesquisados!*"
            )
            return jsonify(status="link_rejeitado")

        if 'location' in dados:
            loc = dados['location']
            address = loc.get('address', '').lower()
            url = loc.get('url', '').lower() if 'url' in loc else ""
            # Bloqueio: local pesquisado, site, etc
            if (
                (address and len(address) > 25) or
                ("rua" in address) or ("avenida" in address) or
                ("cep" in address) or ("bairro" in address) or
                ("http" in address) or ("www." in address) or
                ("gov.br" in address) or (".com" in address) or
                url or
                ("@" in address)
            ):
                enviar_mensagem(
                    tel,
                    "❌ Não foi possível aceitar este local.\n\n*Envie sua localização real usando o botão de localização do WhatsApp (clipe > Localização > Enviar minha localização atual)*.\n\nNão pesquise o endereço ou envie links/sites!"
                )
                return jsonify(status="endereco_nao_aceito")

            # Fluxo normal a partir daqui (registro de ponto)
            lat, lon = loc['latitude'], loc['longitude']
            hoje = datetime.now(TZ).strftime("%Y-%m-%d")
            dow = datetime.now(TZ).weekday()
            codigo_dia = WEEKDAY_CODE[dow]
            group_id = func.get('group_id')

            # --- ESCALA EXCECAO (verifica antes do grupo) ---
            data_hoje = datetime.now(TZ).date()
            cursor.execute(
                """
                SELECT * FROM escalas_excecao 
                WHERE funcionario_id=%s AND active=1 
                  AND data_inicio <= %s AND data_fim >= %s
                ORDER BY data_inicio DESC LIMIT 1
                """,
                (func['id'], data_hoje, data_hoje)
            )
            escala_excecao = cursor.fetchone()

            # BLOQUEIA ponto se FOLGA/FERIAS/FALTA/OUTROS
            if escala_excecao and escala_excecao['tipo'] in ['FOLGA', 'FERIAS', 'FALTA', 'OUTROS']:
                motivo = escala_excecao['tipo'].capitalize()
                obs = escala_excecao.get('observacoes') or ""
                mensagem = f"❌ Não é possível registrar o ponto hoje.\nMotivo: {motivo}."
                if obs:
                    mensagem += f"\nObs: {obs}"
                enviar_mensagem(tel, mensagem)
                return jsonify(status="bloqueado_excecao")

            # Se for exceção ESCALA, usa horários dela, senão do grupo
            if escala_excecao and escala_excecao['tipo'] == 'ESCALA':
                horarios = []
                for key in ['horario1','horario2','horario3','horario4']:
                    h = escala_excecao.get(key)
                    if h and str(h) not in ('', '00:00:00'):
                        if isinstance(h, str):
                            horarios.append(h)
                        else:
                            horarios.append(str(h))
                logging.info(f"[ESCALA EXCECAO] Horários usados: {horarios}")
            else:
                horarios = []
                if group_id:
                    horarios = buscar_horarios_do_grupo(cursor, group_id, codigo_dia)
                logging.info(f"[ESCALA NORMAL] Horarios do grupo {group_id} para {codigo_dia}: {horarios}")

            horario_atual = datetime.now(TZ).time()
            horario_permitido = esta_no_horario_permitido(horarios, horario_atual)
            logging.info(f"Está no horário permitido? {horario_permitido}")

            # Busca endereços autorizados
            cursor.execute(
                """
                SELECT * FROM enderecos_funcionario
                WHERE funcionario_id=%s
                  AND (data_inicio IS NULL OR data_inicio <= %s)
                  AND (data_fim IS NULL OR data_fim >= %s)
                  AND (ativo IS NULL OR ativo = 1)
                """,
                (func['id'], hoje, hoje)
            )
            enderecos = cursor.fetchall()
            endereco_autorizado = None
            distancia = 0
            for endereco in enderecos:
                dist = calcular_distancia(lat, lon,
                                          float(endereco['latitude']),
                                          float(endereco['longitude']))
                if dist <= float(endereco['raio_metros']):
                    endereco_autorizado = endereco
                    distancia = dist
                    break

            cursor.execute(
                "SELECT COUNT(*) AS total FROM ponto_registro WHERE funcionario_id=%s AND DATE(data_hora)=%s",
                (func['id'], hoje)
            )
            total = cursor.fetchone()['total']
            ordem = total + 1

            if not group_id:
                horario_permitido = True

            msg_pendencia = None
            tipo_pendencia = None

            if not horario_permitido and not endereco_autorizado:
                msg_pendencia = "Você está fora do horário permitido *e* fora do local autorizado. Envie uma foto de rosto para solicitar liberação ao RH."
                tipo_pendencia = "ambos"
            elif not endereco_autorizado and ordem > 4:
                msg_pendencia = "Você está fora do local autorizado *e* já atingiu o limite diário de pontos. Envie uma foto de rosto para solicitar liberação ao RH."
                tipo_pendencia = "local_e_limite"
            elif not endereco_autorizado:
                msg_pendencia = "Você está fora do local autorizado. Envie uma foto de rosto para solicitar liberação ao RH."
                tipo_pendencia = "local"
            elif not horario_permitido:
                msg_pendencia = "Você está fora do horário permitido. Envie uma foto de rosto para solicitar liberação ao RH."
                tipo_pendencia = "horario"
            elif ordem > 4:
                msg_pendencia = "Você já atingiu o limite diário de pontos. Envie uma foto de rosto para solicitar liberação ao RH."
                tipo_pendencia = "limite"
            else:
                msg_pendencia = None

            if msg_pendencia:
                estado_usuario[tel] = {
                    "stage": "awaiting_pendencia_photo",
                    "latitude": lat,
                    "longitude": lon,
                    "distancia": distancia,
                    "tipo_pendencia": tipo_pendencia
                }
                enviar_mensagem(tel, msg_pendencia)
                return jsonify(status="pendencia_aguardando_foto")

            # Registro normal
            estado_usuario[tel] = {
                "stage": "awaiting_foto",
                "latitude": lat,
                "longitude": lon,
                "distancia": distancia,
                "endereco_id": endereco_autorizado['id'] if endereco_autorizado else None
            }
            enviar_mensagem(tel, "📸 Envie sua foto de rosto.")
            return jsonify(status="local_ok")
        else:
            enviar_mensagem(
                tel,
                "❌ Por favor, envie sua localização usando o *botão de localização do WhatsApp* (clipe > Localização > Enviar minha localização atual)."
            )
            return jsonify(status="esperando_localizacao_valida")

    # 2. Notificar atraso (awaiting_delay_location)
    if stage == "awaiting_delay_location":
        if 'text' in dados and any(
            x in dados['text'].get('message', '').lower() for x in [
                "https://goo.gl/maps", "https://maps.app.goo.gl", "maps.google.com", "mapa.app.goo.gl", "wa.me/p/", "http", ".com", ".br", "waze.com"
            ]
        ):
            enviar_mensagem(
                tel,
                "❌ Envie sua localização usando o botão de *clipe* > *Localização* > *Enviar minha localização atual* pelo WhatsApp.\n\n*Não cole links ou envie locais pesquisados!*"
            )
            return jsonify(status="link_rejeitado")

        if 'location' in dados:
            loc = dados['location']
            address = loc.get('address', '').lower()
            url = loc.get('url', '').lower() if 'url' in loc else ""
            if (
                (address and len(address) > 25) or
                ("rua" in address) or ("avenida" in address) or
                ("cep" in address) or ("bairro" in address) or
                ("http" in address) or ("www." in address) or
                ("gov.br" in address) or (".com" in address) or
                url or
                ("@" in address)
            ):
                enviar_mensagem(
                    tel,
                    "❌ Não foi possível aceitar este local.\n\n*Envie sua localização real usando o botão de localização do WhatsApp (clipe > Localização > Enviar minha localização atual)*.\n\nNão pesquise o endereço ou envie links/sites!"
                )
                return jsonify(status="endereco_nao_aceito")

            lat, lon = loc['latitude'], loc['longitude']
            estado_usuario[tel] = {
                "stage": "awaiting_delay_reason",
                "latitude": lat,
                "longitude": lon
            }
            enviar_mensagem(tel, "✏️ Informe o motivo do seu atraso:")
            return jsonify(status="aguardando_motivo_atraso")
        else:
            enviar_mensagem(
                tel,
                "❌ Por favor, envie sua localização usando o *botão de localização do WhatsApp* (clipe > Localização > Enviar minha localização atual)."
            )
            return jsonify(status="esperando_localizacao_valida")

    # 3. Liberação fora do horário (awaiting_extra_location)
    if stage == "awaiting_extra_location":
        if 'text' in dados and any(
            x in dados['text'].get('message', '').lower() for x in [
                "https://goo.gl/maps", "https://maps.app.goo.gl", "maps.google.com", "mapa.app.goo.gl", "wa.me/p/", "http", ".com", ".br", "waze.com"
            ]
        ):
            enviar_mensagem(
                tel,
                "❌ Envie sua localização usando o botão de *clipe* > *Localização* > *Enviar minha localização atual* pelo WhatsApp.\n\n*Não cole links ou envie locais pesquisados!*"
            )
            return jsonify(status="link_rejeitado")

        if 'location' in dados:
            loc = dados['location']
            address = loc.get('address', '').lower()
            url = loc.get('url', '').lower() if 'url' in loc else ""
            if (
                (address and len(address) > 25) or
                ("rua" in address) or ("avenida" in address) or
                ("cep" in address) or ("bairro" in address) or
                ("http" in address) or ("www." in address) or
                ("gov.br" in address) or (".com" in address) or
                url or
                ("@" in address)
            ):
                enviar_mensagem(
                    tel,
                    "❌ Não foi possível aceitar este local.\n\n*Envie sua localização real usando o botão de localização do WhatsApp (clipe > Localização > Enviar minha localização atual)*.\n\nNão pesquise o endereço ou envie links/sites!"
                )
                return jsonify(status="endereco_nao_aceito")

            lat, lon = loc['latitude'], loc['longitude']
            estado_usuario[tel] = {
                "stage": "awaiting_extra_location_photo",
                "latitude": lat,
                "longitude": lon,
                "distancia": 0
            }
            enviar_mensagem(tel, "📸 Envie uma foto de rosto para solicitar liberação fora do horário.")
            return jsonify(status="aguardando_foto_fora_horario")
        else:
            enviar_mensagem(
                tel,
                "❌ Por favor, envie sua localização usando o *botão de localização do WhatsApp* (clipe > Localização > Enviar minha localização atual)."
            )
            return jsonify(status="esperando_localizacao_valida")

    # Motivo atraso (após localização validada)
    if stage == "awaiting_delay_reason":
        motivo = msg.strip()
        if not motivo:
            enviar_mensagem(tel, "❌ Informe um motivo válido para o atraso.")
            return jsonify(status="motivo_invalido")

        info = estado_usuario.get(tel)
        lat = info.get("latitude")
        lon = info.get("longitude")
        endereco = coordenada_para_endereco(lat, lon)

        try:
            cursor.execute(
                "INSERT INTO atrasos_funcionario (funcionario_id, criado_em, motivo, status) "
                "VALUES (%s, %s, %s, 0)",
                (
                    func['id'],
                    datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S"),
                    motivo
                )
            )
            conn.commit()
            pendencia_id = cursor.lastrowid
        except Exception as e:
            logging.error(f"Erro ao salvar atraso: {e}")
            enviar_mensagem(tel, "❌ Erro ao salvar atraso.")
            estado_usuario.pop(tel, None)
            return jsonify(status="erro_ao_salvar_atraso")

        supervisor_id = func.get('supervisor_id')
        if supervisor_id:
            tel_sup = buscar_telefone_supervisor(cursor, supervisor_id)
            if tel_sup:
                pendencia_info = {
                    'pendencia_id': pendencia_id,
                    'func_nome': func['nome'],
                    'func_telefone': tel,
                    'motivo': motivo,
                    'endereco': endereco
                }
                fila = pendencias_atraso_por_supervisor.get(tel_sup, [])
                if fila:
                    # Já tem pendencias, só adiciona no final da fila
                    fila.append(pendencia_info)
                    pendencias_atraso_por_supervisor[tel_sup] = fila
                    enviar_mensagem(tel, "✅ Pedido registrado. Aguarde a resposta do supervisor.")
                else:
                    # Nenhuma pendência ativa, envia agora e cria fila
                    pendencias_atraso_por_supervisor[tel_sup] = [pendencia_info]
                    texto_pend = (
                        f"🚨 Funcionário *{func['nome']}* notificou atraso.\n"
                        f"Motivo: {motivo}\n"
                        f"Endereço: {endereco}\n\n"
                        "Responda:\n1 - Aprovar\n2 - Negar"
                    )
                    enviar_mensagem(tel_sup, texto_pend)
                    estado_usuario[tel_sup] = {
                        'stage': 'awaiting_pendencia_resposta',
                        'pendencia_info': pendencia_info
                    }
                    enviar_mensagem(tel, "✅ Pedido registrado e enviado ao supervisor.")
            else:
                enviar_mensagem(tel, "❌ Supervisor não encontrado ou inativo.")
                estado_usuario.pop(tel, None)
                return jsonify(status="supervisor_nao_encontrado")
        else:
            enviar_mensagem(tel, "❌ Supervisor não definido para você.")
            estado_usuario.pop(tel, None)
            return jsonify(status="sem_supervisor")

        estado_usuario.pop(tel, None)
        return jsonify(status="pedido_atraso_registrado")

    # REGISTRO NORMAL: recebendo foto para registrar ponto (com comprovante)
    if stage == "awaiting_foto" and "image" in dados:
        info = estado_usuario.pop(tel)
        agora = datetime.now(TZ)
        fn = f"{agora.strftime('%Y%m%d%H%M%S')}_{tel}_ponto.jpg"
        with open(fn, 'wb') as f:
            f.write(urlopen(dados['image']['imageUrl']).read())
        urlf = upload_ftp_imagem_rosto(fn, fn)
        os.remove(fn)

        # Salva ponto
        cursor.execute(
            "INSERT INTO ponto_registro "
            "(funcionario_id, local_autorizado_id, data_hora, latitude, longitude, distancia_metros, status, imagem_rosto) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                func['id'],
                info.get('endereco_id'),
                agora.strftime("%Y-%m-%d %H:%M:%S"),
                info['latitude'],
                info['longitude'],
                info['distancia'],
                "liberado_rh",
                urlf
            )
        )
        conn.commit()
        nsr = agora.strftime("%Y%m%d%H%M%S")

        comprovante = (
            "📗 *Comprovante de Ponto*\n"
            f"Nome: {func.get('nome')}\n"
            f"Razão Social: {func.get('razao_social')}\n"
            f"CNPJ: {func.get('cnpj')}\n"
            f"PIS: {func.get('pis')}\n"
            f"CRO: 000000000000\n"
            f"Data: {agora.strftime('%d/%m/%Y')}\n"
            f"Hora: {agora.strftime('%H:%M:%S')}\n"
            f"Status: liberado_rh\n"
            f"NSR: {nsr}"
        )
        enviar_mensagem(tel, comprovante)
        return jsonify(status="ponto_registrado")

    # Pendência: recebendo foto para pendência
    if stage == "awaiting_pendencia_photo" and "image" in dados:
        info = estado_usuario.pop(tel)
        agora = datetime.now(TZ)
        fn = f"{agora.strftime('%Y%m%d%H%M%S')}_{tel}_pendencia.jpg"
        with open(fn, 'wb') as f:
            f.write(urlopen(dados['image']['imageUrl']).read())
        urlf = upload_ftp_imagem_rosto(fn, fn)
        os.remove(fn)

        tipo = info.get('tipo_pendencia')
        pendencia_valida = ['ambos', 'local', 'horario', 'local_e_limite', 'limite']
        if tipo not in pendencia_valida:
            tipo = 'horario'

        cursor.execute(
            "INSERT INTO autorizacoes_ponto "
            "(funcionario_id, data, autorizado, criado_em, latitude, longitude, distancia_metros, imagem_rosto, data_hora_solicitada, tipo_pendencia) "
            "VALUES (%s, %s, 0, %s, %s, %s, %s, %s, %s, %s)",
            (
                func['id'],
                agora.strftime("%Y-%m-%d"),
                agora.strftime("%Y-%m-%d %H:%M:%S"),
                info['latitude'],
                info['longitude'],
                info['distancia'],
                urlf,
                agora.strftime("%Y-%m-%d %H:%M:%S"),
                tipo
            )
        )
        conn.commit()
        enviar_mensagem(tel, "✅ Solicitação enviada ao RH. Aguarde a liberação.")
        return jsonify(status="pendencia_criada")

    # Outras etapas: opção 5 fora do horário, envio de foto
    if stage == "awaiting_extra_location_photo" and "image" in dados:
        info = estado_usuario.pop(tel)
        agora = datetime.now(TZ)
        fn = f"{agora.strftime('%Y%m%d%H%M%S')}_{tel}_fora_horario.jpg"
        with open(fn, 'wb') as f:
            f.write(urlopen(dados['image']['imageUrl']).read())
        urlf = upload_ftp_imagem_rosto(fn, fn)
        os.remove(fn)
        cursor.execute(
            "INSERT INTO autorizacoes_ponto "
            "(funcionario_id, data, autorizado, criado_em, latitude, longitude, distancia_metros, imagem_rosto, data_hora_solicitada, tipo_pendencia) "
            "VALUES (%s, %s, 0, %s, %s, %s, %s, %s, %s, 'fora_horario_solicitacao')",
            (
                func['id'],
                agora.strftime("%Y-%m-%d"),
                agora.strftime("%Y-%m-%d %H:%M:%S"),
                info['latitude'],
                info['longitude'],
                info['distancia'],
                urlf,
                agora.strftime("%Y-%m-%d %H:%M:%S")
            )
        )
        conn.commit()
        enviar_mensagem(tel, "✅ Solicitação enviada ao RH. Aguarde a liberação.")
        return jsonify(status="solicitacao_fora_horario_criada")

    # Observação documento
    if stage == "awaiting_doc_observacao":
        doc_id = state["documento_id"]
        obs = msg[:500]
        cursor.execute(
            "UPDATE documentos_funcionario SET observacao_rh=%s WHERE id=%s",
            (obs, doc_id)
        )
        conn.commit()

        # Notificar conforme regra (RH/Admin sempre + supervisor do funcionário)
        notificar_doc_option3(
            cursor,
            func,
            f"📄 Documento #{doc_id} de {func['nome']}: {obs[:100]}..."
        )

        enviar_mensagem(tel, "👍 Observação registrada.")
        estado_usuario.pop(tel)
        return jsonify(status="doc_obs_saved")

    # Relatório mensal
    if stage == "awaiting_mes_ano":
        try:
            mes, ano = map(int, msg.split("/"))
            agora = datetime.now(TZ)
            fn = f"rel_{tel}_{mes}{ano}_{agora.strftime('%Y%m%d%H%M%S')}.pdf"
            gerar_pdf_completo(func, mes, ano, cursor, fn)
            urlp = upload_ftp_relatorio(fn, fn)
            os.remove(fn)
            if urlp:
                enviar_mensagem(tel, f"📄 Relatório: {urlp}")
            else:
                enviar_mensagem(tel, "❌ Erro ao enviar relatório.")
        except Exception as e:
            logging.error(e)
            enviar_mensagem(tel, "❌ Formato inválido ou erro ao gerar relatório. Use MM/AAAA.")
        estado_usuario.pop(tel)
        return jsonify(status="rel_done")

    # Documento (upload)
    if stage == "awaiting_documento" and any(k in dados for k in ['file', 'document', 'media', 'image']):
        info = next((dados[k] for k in ['file', 'document', 'media', 'image'] if k in dados), {})
        file_url = (info.get('fileUrl') or info.get('documentUrl') or info.get('imageUrl') or '')
        nome = info.get('fileName') or info.get('filename') or 'doc'
        ext = os.path.splitext(nome)[1]
        agora = datetime.now(TZ)
        local = f"{tel}_{agora.strftime('%Y%m%d%H%M%S')}{ext}"
        try:
            with open(local, 'wb') as f:
                f.write(urlopen(file_url).read())
            urlp = upload_ftp_documento(local, local)
            os.remove(local)
            if not urlp:
                raise Exception("FTP")
            cursor.execute(
                "INSERT INTO documentos_funcionario (funcionario_id, caminho_arquivo, data_hora, tipo_documento) VALUES (%s, %s, %s, %s)",
                (
                    func['id'], urlp,
                    agora.strftime("%Y-%m-%d %H:%M:%S"),
                    ext.replace('.', '')
                )
            )
            conn.commit()
            doc_id = cursor.lastrowid

            # Notificação conforme regra (RH/Admin sempre + supervisor do funcionário)
            mensagem = f"📄 Documento #{doc_id} enviado por {func['nome']}. Aguarde análise/validação."
            notificar_doc_option3(cursor, func, mensagem)

            enviar_mensagem(tel, "📝 Por favor, informe uma observação do documento enviado.")
            estado_usuario[tel] = {"stage": "awaiting_doc_observacao", "documento_id": doc_id}
            return jsonify(status="awaiting_doc_obs")
        except Exception as e:
            logging.error(f"Erro ao salvar documento: {e}")
            enviar_mensagem(tel, "❌ Erro ao salvar documento.")
            estado_usuario.pop(tel)
            return jsonify(status="doc_fail")

    # Fallback: qualquer situação inesperada volta ao menu
    estado_usuario.pop(tel, None)
    enviar_mensagem(
        tel,
        "⚠️ Algo deu errado. Voltando ao menu...\nDigite 1–5."
    )
    return jsonify(status="reset")

if __name__ == "__main__":
    app.run(host="0.0.0.0")
