import mysql.connector

try:
    conn = mysql.connector.connect(
        host="193.203.175.227",
        user="u588900443_ponto",
        password="Mastertelecom@2025",
        database="u588900443_ponto"
    )
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id FROM funcionarios WHERE telefone = '21987396567'")
    resultado = cursor.fetchone()
    print("✅ Resultado:", resultado)
    conn.close()
except Exception as e:
    print("❌ ERRO NO BANCO:", str(e))
