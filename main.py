import os
import re
import pandas as pd
import streamlit as st
import altair as alt

# --------------------------
# 기본 페이지 설정
# --------------------------
st.set_page_config(page_title="MBTI 유형별 상위 국가 Top10", layout="wide")
st.title("MBTI 유형별 비율 상위 국가 Top 10")
st.caption("기본: 동일 폴더의 countriesMBTI_16types.csv 사용 · 없으면 업로드 파일 사용")

DEFAULT_FILE = "countriesMBTI_16types.csv"

# --------------------------
# 데이터 로더
# --------------------------
@st.cache_data(show_spinner=False)
def load_data(default_path: str, uploaded_file):
    """
    1) 동일 폴더 default_path가 있으면 해당 파일 사용
    2) 없으면 uploaded_file 사용
    3) 컬럼 정규화 및 롱포맷 변환, 비율 기준화(소수/퍼센트 자동 판별)
    """
    # 1) 파일 선택
    if os.path.exists(default_path):
        df = pd.read_csv(default_path)
        source = f"로컬 파일 사용: {default_path}"
    elif uploaded_file is not None:
        df = pd.read_csv(uploaded_file)
        source = "업로드 파일 사용"
    else:
        raise FileNotFoundError(
            f"'{default_path}'가 없고 업로드된 파일도 없습니다. 파일을 업로드하세요."
        )

    # 2) 컬럼 정리
    df.columns = [str(c).strip() for c in df.columns]
    if "Country" not in df.columns:
        # 'Country'에 해당할 법한 컬럼 자동 탐지
        candidates = [c for c in df.columns if str(c).lower() in ("country", "countries", "nation", "name")]
        if candidates:
            df = df.rename(columns={candidates[0]: "Country"})
        else:
            raise ValueError("필수 컬럼 'Country'를 찾을 수 없습니다.")

    # 3) MBTI 컬럼만 추출
    mbti_cols = [c for c in df.columns if re.fullmatch(r"[IE][NS][FT][PJ]", str(c))]
    if not mbti_cols:
        raise ValueError("MBTI 유형 컬럼(예: INFJ, ENTP)을 찾지 못했습니다.")

    # 4) 롱포맷 변환
    long_df = df.melt(id_vars="Country", value_vars=mbti_cols,
                      var_name="MBTI", value_name="value")
    long_df["value"] = pd.to_numeric(long_df["value"], errors="coerce")
    long_df = long_df.dropna(subset=["value"])
    long_df["Country"] = long_df["Country"].astype(str).str.strip()

    # 5) 비율(0~1) 표준화: 이미 % 값(0~100)인 경우 100으로 나눔
    if long_df["value"].max() > 1.5:
        long_df["ratio"] = long_df["value"] / 100.0
    else:
        long_df["ratio"] = long_df["value"]

    # 6) 유형별 순위(내림차순)
    long_df["rank"] = long_df.groupby("MBTI")["ratio"].rank(method="first", ascending=False)

    # MBTI 유형 목록(정렬)
    mbti_types = sorted(mbti_cols)

    return long_df, mbti_types, source

# --------------------------
# 파일 업로드 UI (백업용)
# --------------------------
with st.sidebar:
    st.header("데이터 선택")
    uploaded = st.file_uploader("CSV 파일 업로드", type=["csv"])

# --------------------------
# 데이터 로딩
# --------------------------
try:
    long_df, MBTI_TYPES, data_source = load_data(DEFAULT_FILE, uploaded)
    st.success(data_source)
except Exception as e:
    st.error(f"데이터 로딩 오류: {e}")
    st.stop()

# --------------------------
# 컨트롤 UI
# --------------------------
with st.sidebar:
    st.header("보기 옵션")
    view_mode = st.radio(
        "보기 모드",
        options=["단일 유형", "여러 유형 비교"],
        index=0,
        help="단일 유형의 Top10을 보거나, 여러 유형을 동시에 비교합니다."
    )
    top_n = st.slider("Top N", min_value=5, max_value=20, value=10, step=1)

    if view_mode == "단일 유형":
        sel_type = st.selectbox("MBTI 유형 선택", MBTI_TYPES, index=0)
    else:
        default_multi = ["INFJ", "INFP", "INTP", "ENTP"] if {"INFJ","INFP","INTP","ENTP"} <= set(MBTI_TYPES) else MBTI_TYPES[:4]
        sel_types = st.multiselect("MBTI 유형(복수 선택)", MBTI_TYPES, default=default_multi)

    show_table = st.checkbox("표로도 보기", value=False)

# --------------------------
# Altair 버전별 hover selection
# --------------------------
try:
    alt_major = int(alt.__version__.split(".")[0])
except Exception:
    alt_major = 5

if alt_major >= 5:
    hover_sel = alt.selection_point(on="mouseover", fields=["Country"])
else:
    hover_sel = alt.selection_single(on="mouseover", fields=["Country"], empty="none")

# --------------------------
# 차트 생성 함수
# --------------------------
def single_type_chart(df_long: pd.DataFrame, type_name: str, n: int) -> alt.Chart:
    data = (
        df_long.loc[df_long["MBTI"] == type_name]
        .nsmallest(n, columns="rank")  # rank 1~N
        .sort_values("ratio", ascending=False)
    )

    base = alt.Chart(data)

    bars = base.mark_bar().encode(
        x=alt.X("ratio:Q", title="비율", axis=alt.Axis(format=".1%")),
        y=alt.Y(
            "Country:N",
            sort=alt.SortField(field="ratio", order="descending"),
            title="국가"
        ),
        tooltip=[
            alt.Tooltip("MBTI:N", title="유형"),
            alt.Tooltip("Country:N", title="국가"),
            alt.Tooltip("ratio:Q", title="비율", format=".2%")
        ],
        opacity=alt.condition(hover_sel, alt.value(1.0), alt.value(0.7))
    ).add_params(hover_sel)

    labels = base.mark_text(align="left", baseline="middle", dx=3).encode(
        x="ratio:Q",
        y=alt.Y("Country:N", sort=alt.SortField(field="ratio", order="descending")),
        text=alt.Text("ratio:Q", format=".1%")
    )

    chart = (bars + labels).properties(
        title=f"{type_name} - 상위 {n}개국",
        height=28 * len(data) + 20
    )

    return chart


def multi_type_facet_chart(df_long: pd.DataFrame, types: list[str], n: int) -> alt.Chart:
    data = df_long.loc[df_long["MBTI"].isin(types) & (df_long["rank"] <= n)]

    base = alt.Chart(data)

    bars = base.mark_bar().encode(
        x=alt.X("ratio:Q", title="비율", axis=alt.Axis(format=".1%")),
        y=alt.Y(
            "Country:N",
            # 각 패싯 내에서 x(=ratio) 기준으로 내림차순 정렬
            sort="-x",
            title="국가"
        ),
        color=alt.Color("MBTI:N", title="MBTI"),
        tooltip=[
            alt.Tooltip("MBTI:N", title="유형"),
            alt.Tooltip("Country:N", title="국가"),
            alt.Tooltip("ratio:Q", title="비율", format=".2%")
        ],
        opacity=alt.condition(hover_sel, alt.value(1.0), alt.value(0.75))
    ).add_params(hover_sel)

    labels = base.mark_text(align="left", baseline="middle", dx=3).encode(
        x="ratio:Q",
        y=alt.Y("Country:N", sort="-x"),
        text=alt.Text("ratio:Q", format=".1%")
    )

    chart = (bars + labels).facet(
        column=alt.Column("MBTI:N", title=None),
        columns=4
    ).resolve_scale(y="independent").properties(
        title=f"MBTI 유형별 상위 {n}개국 비교",
        # facet 전체 높이는 스트림릿 컨테이너폭에 맞춰 유동적으로 표시
    )

    return chart

# --------------------------
# 차트 렌더링
# --------------------------
if view_mode == "단일 유형":
    chart = single_type_chart(long_df, sel_type, top_n)
else:
    if not sel_types:
        st.warning("비교할 MBTI 유형을 하나 이상 선택하세요.")
        st.stop()
    chart = multi_type_facet_chart(long_df, sel_types, top_n)

st.altair_chart(chart, use_container_width=True)

# --------------------------
# (선택) 표 보기 & 다운로드
# --------------------------
if show_table:
    if view_mode == "단일 유형":
        tbl = (
            long_df.loc[long_df["MBTI"] == sel_type]
            .nsmallest(top_n, columns="rank")
            .sort_values("ratio", ascending=False)
            .assign(Percentage=lambda d: (d["ratio"] * 100).round(2))
            [["MBTI", "Country", "Percentage"]]
            .rename(columns={"Percentage": "비율(%)"})
        )
    else:
        tbl = (
            long_df.loc[long_df["MBTI"].isin(sel_types) & (long_df["rank"] <= top_n)]
            .sort_values(["MBTI", "ratio"], ascending=[True, False])
            .assign(Percentage=lambda d: (d["ratio"] * 100).round(2))
            [["MBTI", "Country", "Percentage"]]
            .rename(columns={"Percentage": "비율(%)"})
        )

    st.dataframe(tbl, use_container_width=True, hide_index=True)

    csv = tbl.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "표 CSV 다운로드",
        data=csv,
        file_name="mbti_top_countries.csv",
        mime="text/csv"
    )
