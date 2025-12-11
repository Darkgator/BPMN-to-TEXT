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


def _append_to_sheet(filename: str, extracted_text: str) -> tuple[bool, str]:
    """Anexa dados na planilha do Google Sheets (se configurado em st.secrets)."""
    if "gcp_service_account" not in st.secrets or "sheets" not in st.secrets:
        return False, "Configuracao do Sheets ausente."
    try:
        creds = _sheet_credentials()
        gc = gspread.authorize(creds)
        sheets_conf = st.secrets["sheets"]
        ws = gc.open_by_key(sheets_conf["spreadsheet_id"]).worksheet(
            sheets_conf["worksheet_name"]
        )
        stamp = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M:%S")
        ws.append_row(
            [stamp, filename, extracted_text],
            value_input_option="RAW",
        )
    except Exception as exc:  # pragma: no cover - depende de servico externo
        return False, str(exc)
    return True, ""


def _drive_config_ok() -> bool:
    return ("gcp_service_account" in st.secrets or "oauth_client" in st.secrets) and "drive" in st.secrets


def _sheet_credentials():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    if "oauth_client" in st.secrets:
        conf = st.secrets["oauth_client"]
        creds = Credentials(
            None,
            refresh_token=conf["refresh_token"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=conf["client_id"],
            client_secret=conf["client_secret"],
            scopes=scopes,
        )
        creds.refresh(Request())
        return creds
    if "gcp_service_account" in st.secrets:
        return service_account.Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=scopes,
        )
    raise ValueError("Configuracao do Sheets ausente.")


def _drive_credentials():
    """Retorna credenciais do Drive usando OAuth do usuário (preferencial) ou conta de serviço."""
    scopes = ["https://www.googleapis.com/auth/drive.file"]
    if "oauth_client" in st.secrets:
        conf = st.secrets["oauth_client"]
        return Credentials(
            None,
            refresh_token=conf["refresh_token"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=conf["client_id"],
            client_secret=conf["client_secret"],
            scopes=scopes,
        )
    if "gcp_service_account" in st.secrets:
        return service_account.Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=scopes,
        )
    raise ValueError("Nenhuma configuracao de Drive encontrada")


def _upload_to_drive(filename: str, content: bytes) -> tuple[bool, str]:
    """Envia o arquivo BPMN para a pasta do Drive configurada em st.secrets."""
    if not _drive_config_ok():
        return False, "Configuracao do Drive ausente."
    try:
        creds = _drive_credentials()
        drive_conf = st.secrets["drive"]
        folder_id = drive_conf["folder_id"]
        drive = build("drive", "v3", credentials=creds)
        stamp = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d%m%Y-%H%M%S")
        safe_name = Path(filename).name
        unique_name = f"{stamp}-{safe_name}"
        media = MediaIoBaseUpload(
            io.BytesIO(content),
            mimetype="application/octet-stream",
            resumable=False,
        )
        meta = {"name": unique_name, "parents": [folder_id]}
        drive.files().create(body=meta, media_body=media, fields="id").execute()
    except Exception as exc:  # pragma: no cover - depende de servico externo
        return False, str(exc)
    return True, ""


st.markdown(
    f"""
    <style>
    body {{
        background: radial-gradient(circle at 10% 20%, {PALETTE['cyan']}22 0, transparent 25%),
                    radial-gradient(circle at 90% 10%, {PALETTE['blue']}22 0, transparent 25%),
                    linear-gradient(135deg, {PALETTE['midnight']}, #051529 60%);
        color: #f6f9fc;
    }}
    .main {{ padding-top: 0.25rem; }}
    .hero {{
        background: #ffffff;
        border: 1px solid #e3e9ff;
        border-radius: 16px;
        padding: 1.4rem 1.6rem;
        margin: 0;
        box-shadow: 0 4px 14px rgba(10,37,64,0.08);
    }}
    .hero h1 {{
        font-size: 2.2rem;
        margin-bottom: 0.35rem;
        color: {PALETTE['midnight']};
        font-weight: 850;
        letter-spacing: -0.01em;
    }}
    .sub {{
        color: #506273;
        margin-bottom: 0;
        font-size: 1rem;
    }}
    .logo-wrap {{
        display: flex;
        align-items: center;
        justify-content: center;
        background: #ffffff;
        border: 1px solid #e3e9ff;
        border-radius: 18px;
        padding: 0.5rem;
        box-shadow: 0 4px 14px rgba(10,37,64,0.08);
    }}
    .brand-logo {{
        height: 140px;
        width: 200px;
        display: block;
        border-radius: 14px;
        object-fit: cover;
    }}
    .social {{
        display: flex;
        flex-direction: column;
        gap: 12px;
        margin-top: 0.25rem;
        align-items: flex-start;
    }}
    .social .social-title {{
        font-weight: 800;
        font-size: 0.95rem;
        color: #c7d4f5;
    }}
    .social a {{
        display: inline-flex;
        align-items: center;
        gap: 10px;
        color: {PALETTE['cyan']};
        text-decoration: none;
        font-weight: 700;
        font-size: 0.95rem;
    }}
    .social a:hover {{ color: {PALETTE['blue']}; }}
    .social img {{
        width: 20px;
        height: 20px;
        border-radius: 4px;
        display: block;
    }}
    .card {{
        background: rgba(255,255,255,0.04);
        border: 1px solid {PALETTE['gray']}33;
        border-radius: 12px;
        padding: 1rem 1.2rem;
        margin-top: 1rem;
    }}
    .result-textarea {{
        width: 100%;
        min-height: 480px;
        background: #0a1629;
        color: #e6edf7;
        border: 1px solid {PALETTE['blue']}44;
        border-radius: 12px;
        padding: 14px 16px;
        font-family: "Cascadia Mono", "Fira Code", Consolas, "SFMono-Regular", Menlo, monospace;
        font-size: 15px;
        line-height: 1.5;
        white-space: pre;
        overflow: auto;
        resize: vertical;
    }}
    .result-textarea:focus {{
        outline: 2px solid {PALETTE['blue']}66;
    }}
    [data-testid="stCodeBlock"] {{
        background: #0a1629 !important;
        border: 1px solid {PALETTE['blue']}44 !important;
        border-radius: 12px !important;
        padding: 10px 12px !important;
    }}
    [data-testid="stCodeBlock"] pre {{
        background: transparent !important;
        color: #e6edf7 !important;
        white-space: pre-wrap !important;
        line-height: 1.5 !important;
        font-family: "Cascadia Mono", "Fira Code", Consolas, "SFMono-Regular", Menlo, monospace !important;
        font-size: 15px !important;
        margin: 0 !important;
    }}
    .social a {{
        margin-right: 12px;
        color: {PALETTE['cyan']};
        text-decoration: none;
        font-weight: 600;
    }}
    .social a:hover {{ color: {PALETTE['blue']}; }}
    </style>
    """,
    unsafe_allow_html=True,
)

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
                <a href="https://www.instagram.com/alexandre.processos?igsh=MWMydHZwNjM5c2d3" target="_blank">
                    <img src="{IG_ICON}" alt="Instagram"> Instagram
                </a>
                <a href="https://www.linkedin.com/in/alexandre-barroso-miranda" target="_blank">
                    <img src="{LI_ICON}" alt="LinkedIn"> LinkedIn
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
                download_b64 = base64.b64encode(result_text.encode("utf-8")).decode("ascii")
                height_px = min(max((len(lines) + 2) * 22, 480), 1400)
                text_area_id = f"result-text-{uuid4().hex}"
                copy_btn_id = f"copy-btn-{uuid4().hex}"
                copy_status_id = f"copy-status-{uuid4().hex}"
                copy_payload = json.dumps(display_text)
                st.download_button(
                    label="Baixar texto (.txt)",
                    data=result_text,
                    file_name=default_name,
                    mime="text/plain",
                    use_container_width=False,
                )
                actions_html = f"""
                <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin-bottom:0.6rem;">
                    <a download="{default_name}" href="data:text/plain;base64,{download_b64}" style="
                        background:{PALETTE['blue']};
                        color:white;
                        padding:0.6rem 1rem;
                        border-radius:8px;
                        text-decoration:none;
                        font-weight:600;
                        display:inline-flex;
                        align-items:center;
                        justify-content:center;
                    ">Baixar texto (.txt)</a>
                    <button type="button" id="{copy_btn_id}" style="
                        background:{PALETTE['coral']};
                        color:white;
                        border:none;
                        border-radius:8px;
                        padding:0.6rem 1rem;
                        cursor:pointer;
                        font-weight:600;
                    ">Copiar texto</button>
                    <span id="{copy_status_id}" style="color:#c7d4f5;font-weight:600;font-size:0.95rem;"></span>
                </div>
                <script>
                (function() {{
                    const btn = document.getElementById("{copy_btn_id}");
                    const status = document.getElementById("{copy_status_id}");
                    const textToCopy = {copy_payload};
                    if (!btn) return;
                    const showStatus = (msg, resetMs = 1500) => {{
                        if (!status) return;
                        status.textContent = msg;
                        if (resetMs) {{
                            setTimeout(() => status.textContent = "", resetMs);
                        }}
                    }};
                    btn.addEventListener("click", async () => {{
                        btn.disabled = true;
                        showStatus("Copiando...");
                        try {{
                            if (navigator.clipboard && navigator.clipboard.writeText) {{
                                await navigator.clipboard.writeText(textToCopy);
                            }} else {{
                                const temp = document.createElement("textarea");
                                temp.value = textToCopy;
                                temp.setAttribute("readonly", "");
                                temp.style.position = "absolute";
                                temp.style.left = "-9999px";
                                document.body.appendChild(temp);
                                temp.select();
                                document.execCommand("copy");
                                temp.remove();
                            }}
                            showStatus("Copiado!", 1800);
                        }} catch (err) {{
                            console.error("Clipboard copy failed", err);
                            showStatus("Falhou ao copiar", 2500);
                        }} finally {{
                            btn.disabled = false;
                        }}
                    }});
                }})();
                </script>
                """
                st.markdown(actions_html, unsafe_allow_html=True)
                safe_text = html.escape(display_text)
                st.markdown(
                    f"<textarea id='{text_area_id}' class='result-textarea' readonly style='height:{height_px}px'>{safe_text}</textarea>",
                    unsafe_allow_html=True,
                )
else:
    result_area.info("Nenhum arquivo enviado ainda. Selecione um .bpmn ou .xml para começar.")

st.markdown(
    """
    <div style="margin-top:24px; font-size:12px; color:#b6c2d2; opacity:0.7; text-align:left;">
    💡 Sobre o envio de arquivos BPMN: Para melhorar continuamente nossa ferramenta, utilizamos os diagramas BPMN enviados para aprimorar nossa inteligência artificial. Isso nos ajuda a oferecer sugestões mais precisas e recursos cada vez melhores para você. Seus dados são tratados com segurança.
    </div>
    """,
    unsafe_allow_html=True,
)
