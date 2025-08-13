
import math
import pandas as pd
import streamlit as st

# ================== Config ==================
st.set_page_config(page_title="Fiasini • Precificação", page_icon="🧮", layout="wide")

# ================== Helpers ==================
def _norm(s):
    if isinstance(s, str):
        return s.strip().lower().replace("*", "").replace("  ", " ")
    return s

def try_float(x, default=0.0):
    try:
        if pd.isna(x):
            return default
        if isinstance(x, str):
            x = x.replace("%", "").replace(",", ".").strip()
        return float(x)
    except Exception:
        return default

def scan_inputs_from_sheet(df):
    """
    Procura por rótulos em uma coluna e valores na coluna ao lado.
    Retorna um dicionário com possíveis valores padrão.
    """
    defaults = {}
    if df is None or df.empty:
        return defaults

    # Tenta identificar primeira coluna com rótulos de texto
    # Estratégia simples: varrer linhas e pegar pares consecutivos
    for r in range(len(df)):
        row = df.iloc[r].tolist()
        # Procura pares (label, valor) adjacentes
        for c in range(len(row)-1):
            label = _norm(row[c])
            val = row[c+1]
            if not isinstance(label, str):
                continue
            # Match por padrões comuns (flexível)
            if "nome do produto" in label:
                defaults["produto"] = str(val) if pd.notna(val) else ""
            if "matéria prima" in label or "materia prima" in label or "mpd" in label:
                defaults["mpd"] = try_float(val)
            if "cif" in label and "hora" in label:
                defaults["cif_hora"] = try_float(val)
            if ("mod" in label and "hora" in label) or ("mão de obra" in label and "hora" in label):
                defaults["mod_hora"] = try_float(val)
            if "tempo" in label and ("fabrica" in label or "fabricação" in label or "produc" in label) and ("min" in label or "minuto" in label):
                defaults["tempo_min"] = try_float(val)
            if "imposto" in label or "impostos" in label or "icms" in label or "pis" in label or "cofins" in label or "iss" in label:
                # Consideramos um campo % consolidado "impostos_%"
                defaults.setdefault("impostos_pct", try_float(val))
            if "comissão" in label or "comissao" in label:
                defaults["comissao_pct"] = try_float(val)
            if "despesa" in label and ("variável" in label or "variavel" in label):
                defaults["despesas_var_pct"] = try_float(val)
            if "margem" in label:
                defaults["margem_pct"] = try_float(val)
            if "taxa efetiva" in label or "antecipação" in label or "antecipacao" in label:
                defaults["taxa_efetiva_pct"] = try_float(val)

    return defaults

def calcular_precos(mpd, cif_hora, mod_hora, tempo_min, impostos, comissao, despesas_var, margem, taxa_efetiva):
    """
    Todas as alíquotas (%): informar como porcentagem (ex.: 12 para 12%).
    Regras do usuário:
      - Alíquotas (impostos, comissão, despesas variáveis, margem) aplicam sobre PV (gross-up).
      - Taxa efetiva também deve ser calculada sobre o preço de venda → gross-up final.
    Fórmulas:
      custo_fabricacao_unit = mpd + (cif_hora + mod_hora) * (tempo_min/60)
      soma_rates = (impostos + comissao + despesas_var + margem)
      PV_base = custo_fabricacao_unit / (1 - soma_rates)
      PV_final = PV_base / (1 - taxa_efetiva)
    """
    r_impostos = (impostos or 0)/100.0
    r_comissao = (comissao or 0)/100.0
    r_dv = (despesas_var or 0)/100.0
    r_margem = (margem or 0)/100.0
    r_efetiva = (taxa_efetiva or 0)/100.0

    custo_fab = (mpd or 0.0) + ((cif_hora or 0.0) + (mod_hora or 0.0)) * ((tempo_min or 0.0)/60.0)
    soma_rates = r_impostos + r_comissao + r_dv + r_margem
    if soma_rates >= 1.0:
        raise ValueError("A soma das alíquotas sobre PV é >= 100%. Ajuste os percentuais.")

    pv_base = custo_fab / (1.0 - soma_rates)
    if r_efetiva >= 1.0:
        raise ValueError("A taxa efetiva é >= 100%. Ajuste o percentual.")
    pv_final = pv_base / (1.0 - r_efetiva)

    # Quebras por componente em valor (com base no PV_final)
    impostos_val = pv_final * r_impostos
    comissao_val = pv_final * r_comissao
    dv_val = pv_final * r_dv
    margem_val = pv_final * r_margem
    efetiva_val = pv_final * r_efetiva
    # Custo embutido (líquido após retirar percentuais e taxa): aproximamos pelo custo_fab
    # conferência: custo_fab ≈ pv_final - (impostos+comissão+dv+margem+efetiva)

    breakdown = pd.DataFrame({
        "Componente": ["Custo Fabricação", "Impostos", "Comissão", "Despesas Variáveis", "Margem", "Taxa Efetiva"],
        "Valor (R$)": [custo_fab, impostos_val, comissao_val, dv_val, margem_val, efetiva_val]
    })
    breakdown["% do PV"] = breakdown["Valor (R$)"] / pv_final * 100

    return {
        "custo_fabricacao": custo_fab,
        "pv_base_sem_efetiva": pv_base,
        "pv_final": pv_final,
        "breakdown": breakdown
    }

# ================== Sidebar ==================
with st.sidebar:
    st.markdown("## 🧮 Fiasini • Precificação")
    st.caption("Suba a planilha para preencher os padrões. Ajuste os campos e gere o preço.")
    st.divider()
    up = st.file_uploader("Planilha (.xlsx)", type=["xlsx"], key="file")

# ================== Prefill from Excel ==================
prefill = {}
if up is not None:
    try:
        xls = pd.ExcelFile(up, engine="openpyxl")
        sheet_name = "Tabela de Precificação" if "Tabela de Precificação" in xls.sheet_names else xls.sheet_names[0]
        df_sheet = xls.parse(sheet_name)
        prefill = scan_inputs_from_sheet(df_sheet)
        st.toast(f"Padrões importados da aba '{sheet_name}'.", icon="✅")
    except Exception as e:
        st.toast(f"Falha ao ler planilha: {e}", icon="⚠️")

# ================== Main ==================
st.title("Precificação de Produto")
colA, colB = st.columns([1,1])

with colA:
    produto = st.text_input("Nome do Produto", value=prefill.get("produto", ""))
    mpd = st.number_input("Matéria-prima direta (R$)", min_value=0.0, value=float(prefill.get("mpd", 0.0)), step=1.0, format="%.2f")
    cif_hora = st.number_input("CIF por hora (R$)", min_value=0.0, value=float(prefill.get("cif_hora", 0.0)), step=1.0, format="%.2f")
    mod_hora = st.number_input("MOD por hora (R$)", min_value=0.0, value=float(prefill.get("mod_hora", 0.0)), step=1.0, format="%.2f")
    tempo_min = st.number_input("Tempo de fabricação (minutos)", min_value=0.0, value=float(prefill.get("tempo_min", 0.0)), step=1.0, format="%.0f")

with colB:
    impostos_pct = st.number_input("Impostos sobre PV (%)", min_value=0.0, max_value=99.99, value=float(prefill.get("impostos_pct", 0.0)), step=0.25, format="%.2f")
    comissao_pct = st.number_input("Comissão sobre PV (%)", min_value=0.0, max_value=99.99, value=float(prefill.get("comissao_pct", 0.0)), step=0.25, format="%.2f")
    despesas_var_pct = st.number_input("Despesas variáveis sobre PV (%)", min_value=0.0, max_value=99.99, value=float(prefill.get("despesas_var_pct", 0.0)), step=0.25, format="%.2f")
    margem_pct = st.number_input("Margem desejada sobre PV (%)", min_value=0.0, max_value=99.99, value=float(prefill.get("margem_pct", 0.0)), step=0.25, format="%.2f")
    taxa_efetiva_pct = st.number_input("Taxa efetiva (%)", min_value=0.0, max_value=99.99, value=float(prefill.get("taxa_efetiva_pct", 0.0)), step=0.25, format="%.2f")

st.divider()

# Cálculo
try:
    res = calcular_precos(
        mpd=mpd,
        cif_hora=cif_hora,
        mod_hora=mod_hora,
        tempo_min=tempo_min,
        impostos=impostos_pct,
        comissao=comissao_pct,
        despesas_var=despesas_var_pct,
        margem=margem_pct,
        taxa_efetiva=taxa_efetiva_pct
    )

    pv = res["pv_final"]
    pv_base = res["pv_base_sem_efetiva"]
    custo = res["custo_fabricacao"]
    breakdown = res["breakdown"]

    met1, met2, met3, met4 = st.columns(4)
    met1.metric("PV base (sem Taxa Efetiva)", f"R$ {pv_base:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    met2.metric("PV final (com Taxa Efetiva)", f"R$ {pv:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    met3.metric("Custo de fabricação", f"R$ {custo:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    met4.metric("Soma Alíquotas s/ PV", f"{(impostos_pct+comissao_pct+despesas_var_pct+margem_pct):.2f}%")

    st.subheader("Decomposição do Preço de Venda (PV)")
    st.dataframe(breakdown, use_container_width=True)

    st.subheader("Resumo para exportação")
    export = pd.DataFrame({
        "Produto": [produto if produto else ""],
        "MPD (R$)": [mpd],
        "CIF/h (R$)": [cif_hora],
        "MOD/h (R$)": [mod_hora],
        "Tempo (min)": [tempo_min],
        "Impostos (%)": [impostos_pct],
        "Comissão (%)": [comissao_pct],
        "Despesas Variáveis (%)": [despesas_var_pct],
        "Margem (%)": [margem_pct],
        "Taxa Efetiva (%)": [taxa_efetiva_pct],
        "Custo Fabricação (R$)": [custo],
        "PV base (R$)": [pv_base],
        "PV final (R$)": [pv],
    })
    st.dataframe(export, use_container_width=True)

    csv = export.to_csv(index=False).encode("utf-8-sig")
    st.download_button("⬇️ Baixar resumo (CSV)", data=csv, file_name="precificacao_fiasini.csv", mime="text/csv")

except Exception as e:
    st.error(f"Não foi possível calcular: {e}")
    st.info("Verifique se a soma das alíquotas sobre PV é menor que 100% e os valores numéricos estão corretos.")

st.caption("Tema e identidade Fiasini aplicados. Para ajustes finos, edite `.streamlit/config.toml`.")
