from app.services.buscar_telefone_supervisor_do_funcionario import buscar_telefone_supervisor_do_funcionario
from app.services.buscar_telefone_admin_e_rh import buscar_telefone_admin_e_rh
from app.whatsapp.enviar_mensagem import enviar_mensagem

def notificar_admin_e_rh(cursor, funcionario, mensagem):
    """
    Regra:
      - RH e ADMIN SEMPRE recebem
      - Supervisor SOMENTE se for o supervisor do funcionário
      - Nunca o próprio funcionário (se ele existir em usuarios_rh)
    """
    telefones = set(buscar_telefone_admin_e_rh(cursor))
    tel_sup = buscar_telefone_supervisor_do_funcionario(cursor, funcionario)
    if tel_sup:
        telefones.add(tel_sup)

    # remove telefone do próprio funcionário, caso conste em usuarios_rh
    if funcionario.get('telefone'):
        telefones.discard(funcionario['telefone'])

    for t in telefones:
        if t:
            enviar_mensagem(t, mensagem)