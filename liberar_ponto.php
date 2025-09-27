<?php
session_start();
require_once("db_config.php");

if (!isset($_SESSION['rh'])) {
    header("Location: index.php");
    exit;
}

$data_hoje = date('Y-m-d');

// Consulta autorizações pendentes
$query = "
    SELECT a.id AS autorizacao_id, f.id AS funcionario_id, f.nome, f.telefone, 
           COUNT(p.id) AS total_pontos
    FROM autorizacoes_ponto a
    JOIN funcionarios f ON a.funcionario_id = f.id
    LEFT JOIN ponto_registro p ON f.id = p.funcionario_id AND DATE(p.data_hora) = a.data
    WHERE a.data = ? AND a.autorizado = 0
    GROUP BY a.id
";

$stmt = $conn->prepare($query);
$stmt->bind_param("s", $data_hoje);
$stmt->execute();
$result = $stmt->get_result();
$funcionarios = $result->fetch_all(MYSQLI_ASSOC);

if ($_SERVER["REQUEST_METHOD"] == "POST" && isset($_POST['autorizacao_id'])) {
    $autorizacao_id = $_POST['autorizacao_id'];
    $funcionario_id = $_POST['funcionario_id'];
    $id_rh = $_SESSION['rh'];
    $motivo = trim($_POST['motivo'] ?? '');

    $stmt = $conn->prepare("
        UPDATE autorizacoes_ponto 
        SET autorizado = 1, id_rh = ?, motivo = ? 
        WHERE id = ?
    ");
    $stmt->bind_param("isi", $id_rh, $motivo, $autorizacao_id);
    $stmt->execute();

    header("Location: liberar_ponto.php");
    exit;
}
?>

<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <title>Liberar Ponto Extra</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-light">

<div class="container mt-5">
    <h3 class="mb-4">📍 Funcionários com Pontos Extras Pendentes (<?= date('d/m/Y') ?>)</h3>

    <?php if (count($funcionarios) > 0): ?>
        <table class="table table-bordered table-striped">
            <thead>
                <tr>
                    <th>Nome</th>
                    <th>Telefone</th>
                    <th>Total de Pontos Hoje</th>
                    <th>Motivo da Liberação</th>
                    <th>Ação</th>
                </tr>
            </thead>
            <tbody>
                <?php foreach ($funcionarios as $f): ?>
                    <tr>
                        <td><?= htmlspecialchars($f['nome']) ?></td>
                        <td><?= htmlspecialchars($f['telefone']) ?></td>
                        <td><?= $f['total_pontos'] ?></td>
                        <td>
                            <form method="POST" class="d-flex">
                                <input type="hidden" name="autorizacao_id" value="<?= $f['autorizacao_id'] ?>">
                                <input type="hidden" name="funcionario_id" value="<?= $f['funcionario_id'] ?>">
                                <input type="text" name="motivo" class="form-control me-2" placeholder="Ex: esquecimento" required>
                                <button class="btn btn-success btn-sm" onclick="return confirm('Liberar novo ponto para <?= $f['nome'] ?>?')">
                                    ✅ Liberar
                                </button>
                            </form>
                        </td>
                    </tr>
                <?php endforeach ?>
            </tbody>
        </table>
    <?php else: ?>
        <div class="alert alert-info">Nenhum ponto extra pendente de liberação hoje.</div>
    <?php endif; ?>
</div>

</body>
</html>
