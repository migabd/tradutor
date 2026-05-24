@echo off
title VoiceDub AI - Dublador Automatico
color 0B

echo ========================================================
echo               VoiceDub AI - YouTube Dubber             
echo ========================================================
echo.
echo [1/3] Verificando e instalando pacotes necessarios...
pip install -r requirements.txt
echo.
echo [2/3] Abrindo a interface web no seu navegador...
timeout /t 2 /nobreak > nul
start http://127.0.0.1:8000
echo.
echo [3/3] Iniciando o servidor local do Dublador...
echo.
echo --------------------------------------------------------
echo   SERVIDOR ATIVO! Mantenha esta janela aberta para usar.
echo   Para encerrar a aplicacao, basta fechar esta janela.
echo --------------------------------------------------------
echo.
python server.py
pause
