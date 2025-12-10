# BPMN to TEXT

Aplicação em Streamlit que recebe arquivos BPMN/XML e devolve a narrativa em texto. Ideal para usar em IAs generativas (ChatGPT, Gemini, Claude, etc.), que lidam melhor com texto estruturado do que com BPMN puro. O processamento fica em `bpmn_to_text.py` e a interface em `app.py`.

Principais recursos:
- Numeração hierárquica com retomada após convergência de gateways.
- Identificação de eventos intermediários de link (disparo/captura) no fluxo correto.
- Limpeza de campos (ator/sistema/documento/anotação) para saída em linha única.

## Como usar (online)
- App publicado: https://bpmn-to-text.streamlit.app/
- Envie um `.bpmn` ou `.xml`; visualize e baixe o texto em `.txt`.

## Como rodar local
1) Ambiente virtual (opcional, recomendado):
```bash
python -m venv .venv
.venv\Scripts\activate
```
2) Dependencias:
```bash
pip install -r requirements.txt
```
3) Subir o app:
```bash
streamlit run app.py
```
4) Abra `http://localhost:8501`, envie o BPMN/XML e baixe o texto.

## CLI
Processar um BPMN direto no terminal:
```bash
python bpmn_to_text.py caminho/para/arquivo.bpmn
```

## Estrutura
- `app.py`: interface Streamlit, upload e exibicao do texto.
- `bpmn_to_text.py`: parsing e conversao BPMN -> texto.
- `assets/`: logos e icones.
- `requirements.txt`: dependencias.
- `.gitignore`: itens ignorados (venv, caches, .streamlit, IDE).

## Contato
- Instagram: https://www.instagram.com/alexandre.processos?igsh=MWMydHZwNjM5c2d3
- LinkedIn: https://www.linkedin.com/in/alexandre-barroso-miranda
