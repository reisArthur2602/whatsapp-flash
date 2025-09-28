#!/bin/sh

echo "🔹 Criando ambiente virtual..."
python -m venv venv

echo "🔹 Ativando ambiente virtual..."
. venv/bin/activate

echo "🔹 Atualizando pacotes básicos..."
pip install --upgrade pip setuptools wheel

echo "🔹 Instalando dependências..."
pip install --no-cache-dir -r requirements.txt

echo "🚀 Iniciando aplicação..."
python app.py 

