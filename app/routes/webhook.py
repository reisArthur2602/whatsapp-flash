from flask import Blueprint, request, jsonify

import os
from datetime import datetime
from urllib.request import urlopen
from threading import Thread
import logging
import time as time_mod
# Database
from app.database.mysql import conectar_mysql
# Configurações globais
from config import ultima_atividade_usuario,estado_usuario,pendencias_atraso_por_supervisor,WEEKDAY_CODE,TZ
# WhatsApp
from app.whatsapp.enviar_mensagem import enviar_mensagem
# Serviços
from app.services.buscar_horarios_do_grupo import buscar_horarios_do_grupo
from app.services.buscar_telefone_supervisor import buscar_telefone_supervisor
from app.services.notificar_admin_e_rh import notificar_admin_e_rh

# Utils
from app.utils.calcular_distancia import calcular_distancia
from app.utils.coordenada_para_endereco import coordenada_para_endereco
from app.utils.esta_no_horario_permitido import esta_no_horario_permitido
from app.utils.monitor_atividades import monitor_inatividade

# FTP e Canvas
from app.ftp.uploads import upload_ftp_documento, upload_ftp_imagem_rosto, upload_ftp_relatorio
from app.canvas.gerar_pdf import gerar_pdf


logging.basicConfig(level=logging.INFO)

Thread(target=monitor_inatividade, daemon=True).start()

webhook_bp = Blueprint("webhook", __name__)

@webhook_bp.route("/webhook", methods=["POST"])

def webhook():
    dados = request.get_json()
    logging.info(f"Payload recebido: {dados}")
    tel = dados.get("phone", "").replace("55", "", 1)
    msg = dados.get("text", {}).get("message", "").strip().lower()

    
    ultima_atividade_usuario[tel] = time_mod.time()

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
        notificar_admin_e_rh(
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
            gerar_pdf(func, mes, ano, cursor, fn)
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
            notificar_admin_e_rh(cursor, func, mensagem)

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
