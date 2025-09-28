def buscar_telefone_supervisor_do_funcionario(cursor, funcionario):
    sid = funcionario.get('supervisor_id')
    if not sid:
        return None
    cursor.execute("SELECT telefone FROM usuarios_rh WHERE id=%s AND ativo=1", (sid,))
    row = cursor.fetchone
    row = cursor.fetchone()
    return row['telefone'] if row and row.get('telefone') else None