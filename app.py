import base64
import html
import io
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from uuid import uuid4

import gspread
import streamlit as st
import streamlit.components.v1 as components
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from bpmn_to_text import render_bpmn_bytes


st.set_page_config(page_title="BPMN para Texto", layout="wide")
st.session_state.setdefault("last_text", "")
st.session_state.setdefault("last_filename", "bpmn.txt")

PALETTE = {
    "midnight": "#0A2540",
    "blue": "#2979FF",
    "cyan": "#00ACC1",
    "gray": "#607D8B",
    "coral": "#FF7043",
}

LOGO_LOCAL = "assets/logo.png"
IG_ICON_PATH = "assets/instagram.png"
LI_ICON_PATH = "assets/linkedin.png"
LOGO_DATA_URI = ""

# stubs de integração externa (mantêm app rodando mesmo sem credenciais)
def _append_to_sheet(filename: str, extracted_text: str) -> tuple[bool, str]:
    return False, ""


def _upload_to_drive(filename: str, content: bytes) -> tuple[bool, str]:
    return False, ""


# renderiza botão de download com base no último resultado
def render_actions(container):
    last_text = st.session_state.get("last_text", "")
    last_filename = st.session_state.get("last_filename", "bpmn.txt")
    with container:
        st.markdown("### Ações")
        st.download_button(
            label="Baixar texto (.txt)",
            data=last_text if last_text else "",
            file_name=last_filename,
            mime="text/plain",
            use_container_width=True,
            disabled=not bool(last_text),
            key=f"download-top-{uuid4().hex}",
        )

def _img_data_uri(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    data = p.read_bytes()
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:image/{p.suffix.lstrip('.')};base64,{encoded}"


IG_ICON = _img_data_uri(IG_ICON_PATH)
LI_ICON = _img_data_uri(LI_ICON_PATH)
LOGO_DATA_URI = _img_data_uri(LOGO_LOCAL)

with st.container():
    col_logo, col_title, col_social = st.columns([1.2, 3.6, 1], gap="medium")
    with col_logo:
        if LOGO_DATA_URI:
            st.markdown(
                f"<div class='logo-wrap'><img src='{LOGO_DATA_URI}' class='brand-logo' alt='Logo'></div>",
                unsafe_allow_html=True,
            )
        else:
            st.image(LOGO_LOCAL, caption="", width=200)
    with col_title:
        st.markdown(
            """
            <div class="hero">
                <h1>BPMN para Texto</h1>
                <div class="sub">Envie um BPMN/XML e receba a narrativa estruturada.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col_social:
        st.markdown(
            f"""
            <div class="social">
                <div class="social-title">Criador:</div>
                <a href="https://www.instagram.com/alexandre.processos?igsh=MWMydHZwNjM5c2d3" target="_blank" style="display:flex;align-items:center;gap:8px;font-size:0.95rem;">
                    <img src="{IG_ICON}" alt="Instagram" style="width:20px;height:20px;"> Instagram
                </a>
                <a href="https://www.linkedin.com/in/alexandre-barroso-miranda" target="_blank" style="display:flex;align-items:center;gap:8px;font-size:0.95rem;">
                    <img src="{LI_ICON}" alt="LinkedIn" style="width:20px;height:20px;"> LinkedIn
                </a>
            </div>
            """,
            unsafe_allow_html=True,
        )

with st.container():
    st.markdown(
        """
        <div class="card">
            <strong>Como usar</strong><br>
            1) Arraste um .bpmn ou .xml.<br>
            2) Aguarde o processamento.<br>
            3) Visualize e baixe o texto.
        </div>
        """,
        unsafe_allow_html=True,
    )

actions_placeholder = st.empty()
def render_actions_inline():
    with actions_placeholder:
        st.markdown("### Ações")
        st.download_button(
            label="Baixar texto (.txt)",
            data=st.session_state.get("last_text", ""),
            file_name=st.session_state.get("last_filename", "bpmn.txt"),
            mime="text/plain",
            use_container_width=True,
            disabled=not bool(st.session_state.get("last_text")),
            key=f"download-inline-{uuid4().hex}",
        )

render_actions_inline()

uploaded = st.file_uploader("Arquivo BPMN ou XML", type=["bpmn", "xml"])
result_area = st.empty()

if uploaded:
    data = uploaded.getvalue()
    if not data:
        result_area.warning("O arquivo enviado está vazio.")
    else:
        _upload_to_drive(uploaded.name, data)
        try:
            result_text = render_bpmn_bytes(data, filename=uploaded.name)
        except Exception as exc:
            result_area.error(f"Erro ao processar o BPMN: {exc}")
        else:
            with result_area:
                st.success("Processamento concluído.")
                default_name = f"{Path(uploaded.name).stem or 'bpmn'}.txt"
                lines = result_text.splitlines()
                if lines and lines[0].strip().lower().startswith("titulo:"):
                    lines.insert(1, "")
                display_text = "\n".join(lines)
                sheet_text = display_text
                if len(sheet_text) > 48000:
                    sheet_text = sheet_text[:48000] + "\n...[truncado para caber no Sheets]"
                _append_to_sheet(uploaded.name, sheet_text)
                height_px = min(max((len(lines) + 2) * 22, 480), 1400)
                text_area_id = f"result-text-{uuid4().hex}"
                st.markdown(f"**Arquivo:** {uploaded.name}")
                st.code(display_text, language="markdown")
                safe_text = html.escape(display_text)
                st.markdown(
                    f"<textarea id='{text_area_id}' class='result-textarea' readonly style='height:{height_px}px'>{safe_text}</textarea>",
                    unsafe_allow_html=True,
                )
                st.session_state["last_text"] = display_text
                st.session_state["last_filename"] = default_name
                render_actions_inline()

else:
    result_area.info("Nenhum arquivo enviado ainda. Selecione um .bpmn ou .xml para comecar.")
st.markdown(
    """
    <div style="margin-top:24px; font-size:12px; color:#b6c2d2; opacity:0.7; text-align:left;">
    💡 Sobre o envio de arquivos BPMN: Para melhorar continuamente nossa ferramenta, utilizamos os diagramas BPMN enviados para aprimorar nossa inteligência artificial. Isso nos ajuda a oferecer sugestões mais precisas e recursos cada vez melhores para você. Seus dados são tratados com segurança.
    </div>
    """,
    unsafe_allow_html=True,
)
