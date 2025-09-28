def buscar_telefone_supervisor(cursor, supervisor_id):
    cursor.execute("SELECT telefone FROM usuarios_rh WHERE id=%s AND ativo=1", (supervisor_id,))
    row = cursor.fetchone()
    if row:
        return row['telefone']
    return None