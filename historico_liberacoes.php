<?php
session_start();
require_once("db_config.php");

if (!isset($_SESSION['rh'])) {
    header("Location: index.php");
    exit;
}

// Consulta atualizada
$query = "
    SELECT a.id, f.nome AS funcionario_nome, f.telefone, a.data, a.criado_em, a.motivo, u.nome AS rh_nome
    FROM autorizacoes_ponto a
    JOIN funcionarios f ON a.funcionario_id = f.id
    JOIN usuarios u ON a.id_rh = u.id
    WHERE a.autorizado = 1
    ORDER BY a.criado_em DESC
";

$resultado = $conn->query($query);
?>

<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <title>Histórico de Liberações</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-light">
<div class="container mt-5">
    <h3 class="mb-4 text-primary">📄 Histórico de Liberações de Ponto Extra</h3>

    <?php if ($resultado->num_rows > 0): ?>
        <table class="table table-bordered table-striped">
            <thead class="table-dark">
                <tr>
                    <th>Funcionário</th>
                    <th>Telefone</th>
                    <th>RH que Autorizou</th>
                    <th>Motivo</th>
                    <th>Data Autorizada</th>
                    <th>Data da Liberação</th>
                </tr>
            </thead>
            <tbody>
                <?php while ($row = $resultado->fetch_assoc()): ?>
                    <tr>
                        <td><?= htmlspecialchars($row['funcionario_nome']) ?></td>
                        <td><?= htmlspecialchars($row['telefone']) ?></td>
                        <td><?= htmlspecialchars($row['rh_nome']) ?></td>
                        <td><?= htmlspecialchars($row['motivo']) ?></td>
                        <td><?= date('d/m/Y', strtotime($row['data'])) ?></td>
                        <td><?= date('d/m/Y H:i', strtotime($row['criado_em'])) ?></td>
                    </tr>
                <?php endwhile ?>
            </tbody>
        </table>
    <?php else: ?>
        <div class="alert alert-info">Nenhuma liberação registrada ainda.</div>
    <?php endif; ?>
</div>
</body>
</html>
