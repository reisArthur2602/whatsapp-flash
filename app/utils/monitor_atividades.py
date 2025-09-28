

from config import ultima_atividade_usuario , estado_usuario 
import time as time_mod
from app.whatsapp.enviar_mensagem import enviar_mensagem

def monitor_inatividade(intervalo=60, tempo_oi=300, tempo_encerrar=420):
    while True:
        agora = time_mod.time()
        for tel, last in list(ultima_atividade_usuario.items()):
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
                        ultima_atividade_usuario.pop(tel, None)
        time_mod.sleep(intervalo)