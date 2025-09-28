import logging 
from app.utils.converter_hora_para_time import converter_hora_para_time

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