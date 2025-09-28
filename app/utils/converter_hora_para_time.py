from datetime import datetime, timedelta, time

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