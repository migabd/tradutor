# VoiceDub AI 🎙️🎬 - Dublador Automático de Vídeos do YouTube

VoiceDub AI é uma aplicação completa e moderna para dublagem automática de vídeos do YouTube para o português brasileiro. Utilizando os recursos de ponta do **Gemini 2.0** da Google (tanto para a tradução e transcrição inteligente quanto para a geração de vozes neurais realistas via TTS) e combinando-os com o processamento robusto do **FFmpeg**, este projeto fornece um fluxo de trabalho completo e profissional diretamente no seu navegador.

---

## ✨ Funcionalidades Principais

- **📥 Download Automático**: Insira qualquer link do YouTube; o `yt-dlp` se encarrega de extrair o vídeo e o áudio da melhor qualidade.
- **🧠 Transcrição & Tradução com Gemini**: Transcreve o áudio original e traduz diretamente para o português preservando o contexto e o tom original.
- **🗣️ Vozes Neurais Premium**: Geração de falas extremamente naturais utilizando as vozes integradas do Gemini 2.0 (`Puck`, `Charon`, `Aoede`, `Fenrir`, `Kore`).
- **🎛️ Ajuste Dinâmico e Alinhamento Temporal**: Sincroniza e estica/encolhe o áudio gerado para alinhar perfeitamente com os tempos de fala do vídeo original (usando filtros `atempo` e `adelay` do FFmpeg).
- **📉 Volume Ducking Inteligente**: Abaixa suavemente o volume do áudio original de fundo quando a voz em português está falando, mantendo a trilha sonora e os efeitos sonoros.
- **🖥️ Painel Web Premium**: Uma interface com design *glassmorphism* moderno, contendo:
  - Painel de configuração de chave de API do Gemini segura (armazenada localmente).
  - Acompanhamento do progresso em tempo real com barra de progresso e status detalhados.
  - Reprodutor duplo e sincronizado para comparar o vídeo original e o dublado lado a lado.
  - **Editor de Linha do Tempo de Segmentos**: Permite visualizar cada trecho traduzido, ouvir o áudio individual, ajustar a tradução textual e regenerar o áudio dinamicamente se você quiser fazer ajustes manuais finos!

---

## 🛠️ Tecnologias Utilizadas

### Backend
- **FastAPI** & **Uvicorn** - Framework web rápido e de alta performance.
- **google-genai** (v2.6.0+) - Novo SDK oficial da Google para integração completa com o Gemini 2.0 (Modelos e API de Arquivos).
- **yt-dlp** - Para extração rápida e resiliente de vídeos do YouTube.
- **static-ffmpeg** - Instalação automática e autocontida dos binários do FFmpeg (sem necessidade de configurar variáveis de ambiente de forma manual no Windows/Linux).

### Frontend
- **HTML5 & CSS3 Vanilla** - Design premium construído do zero, com sombras suaves, efeitos de desfoque de fundo (*glassmorphism*), paleta de cores moderna e responsividade total.
- **JavaScript (ES6+)** - Lógica reativa para gerenciamento de chaves de API, polling de status, sincronização de players de vídeo e edição interativa de segmentos de tempo.

---

## 🚀 Como Executar o Projeto Localmente

### Pré-requisitos
- Python 3.10 ou superior instalado.
- Acesso à internet para download dos modelos e ferramentas.

### Passo a Passo

1. **Clonar ou abrir a pasta do repositório**:
   ```bash
   git init
   ```

2. **Instalar as dependências**:
   No terminal, execute:
   ```bash
   pip install -r requirements.txt
   ```
   *Nota: O `static-ffmpeg` irá baixar automaticamente os binários necessários do FFmpeg na primeira execução.*

3. **Iniciar o Servidor**:
   ```bash
   python server.py
   ```

4. **Acessar a Aplicação**:
   Abra o seu navegador e acesse:
   [http://127.0.0.1:8000](http://127.0.0.1:8000)

5. **Configurar a API Key**:
   Insira sua chave da API do Gemini diretamente na interface web para começar a dublar seus vídeos! A chave fica salva apenas no armazenamento local do seu próprio navegador (`localStorage`) por segurança.

---

## 📁 Estrutura do Projeto

```
Dublador/
├── static/                # Frontend (HTML, CSS, JS)
│   ├── index.html         # Página principal com estrutura de interface
│   ├── index.css          # Design e efeitos visuais modernos
│   └── app.js             # Lógica e interatividade do cliente
├── utils/                 # Scripts auxiliares e lógica de negócios
│   ├── __init__.py        # Inicializador do pacote python
│   └── dubber.py          # Pipeline principal de download, tradução e dublagem
├── output/                # Vídeos dublados finais gerados [Ignorado no Git]
├── tasks/                 # Arquivos JSON de progresso de cada tarefa [Ignorado no Git]
├── temp/                  # Arquivos temporários de áudio/vídeo [Ignorado no Git]
├── .gitignore             # Arquivos ignorados pelo Git
├── requirements.txt       # Dependências do Python
├── server.py              # Ponto de entrada do servidor FastAPI
└── README.md              # Este arquivo explicativo
```

---

## 🤝 Contribuições

Sinta-se à vontade para abrir uma *Issue* ou enviar um *Pull Request* se encontrar problemas ou se tiver sugestões de novas melhorias!

Desenvolvido com carinho e inteligência artificial. 🎙️✨
