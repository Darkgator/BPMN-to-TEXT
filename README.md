# BPMN to TEXT (Streamlit)

Aplicação web em Streamlit para receber arquivos BPMN/XML e devolver o texto extraído. O núcleo de processamento usa o script `bpmn_to_text.py`, já validado em execução via terminal.

## Estrutura do projeto
- `app.py`: interface Streamlit com upload e exibição do texto gerado.
- `bpmn_to_text.py`: funções de parsing e conversão de BPMN para texto.
- `requirements.txt`: dependências mínimas (`streamlit`).
- `assets/`: logos e ícones usados na interface.
- `.gitignore`: regras básicas (venv, caches, .streamlit, IDE).

## Como executar localmente
1) Crie e ative um ambiente virtual (opcional, mas recomendado):
```bash
python -m venv .venv
.venv\Scripts\activate
```

2) Instale as dependências:
```bash
pip install -r requirements.txt
```

3) Suba a interface:
```bash
streamlit run app.py
```

4) No navegador, envie um arquivo `.bpmn` ou `.xml` para ver o texto extraído e baixar o resultado em `.txt`.

## Deploy no Streamlit Cloud
1) Crie um repositório no GitHub contendo `app.py`, `bpmn_to_text.py`, `requirements.txt` e a pasta `assets/`.
2) Acesse https://share.streamlit.io/ (Streamlit Community Cloud), clique em “New app”, conecte ao GitHub e selecione repositório/branch.
3) Informe o caminho do app (ex.: `app.py`) e conclua. Cada push na branch configurada refaz o deploy.
4) Se precisar de secrets, configure-os em Settings > Secrets no painel do app.

## Uso via linha de comando
O arquivo `bpmn_to_text.py` mantém a função `main()` para rodar direto pelo terminal, escolhendo um BPMN em disco:
```bash
python bpmn_to_text.py caminho/para/arquivo.bpmn
```

## Próximos passos sugeridos
- Adicionar testes automatizados para cenários de BPMN complexos.
- Ajustar mensagens/labels da interface conforme feedback dos usuários.
- Publicar o repositório no GitHub e configurar CI (formatação/segurança).
