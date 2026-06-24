#!/bin/bash
cd "$(dirname "$0")"
echo "Instalando dependências..."
pip install -q -r requirements.txt
echo "Iniciando sistema de audiências..."
python app.py
