import logging 
from datetime import datetime, timedelta
from config import TOLERANCIA_MINUTOS

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