from reportlab.pdfgen import canvas

from config import WEEKDAY_CODE
from datetime import datetime

def gerar_pdf(func, mes, ano, cursor, path):
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