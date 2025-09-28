def buscar_telefone_admin_e_rh(cursor):
    """Retorna todos os telefones de RH e ADMIN ativos."""
    cursor.execute("""
        SELECT telefone 
        FROM usuarios_rh 
        WHERE ativo=1 AND tipo_usuario IN ('rh','admin')
    """)
    
    return [r['telefone'] for r in cursor.fetchall() if r.get('telefone')]