"""
Streamlit UI
실행: streamlit run ui/app.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
import streamlit as st
from pipeline import collect_fabric_data, DuplicateURLError, LLMQuotaError
from db.database import list_all, delete, update
from scraper.receipt_parser import parse_receipt
from scraper.url_finder import find_product_url
import config

st.set_page_config(page_title="원단 DB", page_icon="🧵", layout="wide")
st.title("🧵 원단 정보 수집기")

# ── session_state 초기화 ──────────────────────────────────────
defaults = {
    # URL 수집 탭
    "pending_urls":    [],
    "force_run":       False,
    "duplicate_info":  None,
    "duplicate_url":   None,
    "results":         [],
    # 영수증 탭 — 3단계 상태
    "rcpt_step":       1,          # 1=업로드, 2=상품명 확인, 3=URL 탐색 결과 확인
    "rcpt_names":      [],         # 추출된 상품명 리스트 (편집 가능)
    "rcpt_found":      [],         # [{name, url, found}, ...] URL 탐색 결과
    "rcpt_pending":    [],         # URL 수집 대기 목록
    "rcpt_results":    [],         # 최종 수집 결과
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ════════════════════════════════════════════════════════════
tab_url, tab_rcpt = st.tabs(["🔗 URL로 수집", "🧾 영수증으로 수집"])

# ════════════════════════════════════════════════════════════
# TAB 1: URL 수집 (기존 로직)
# ════════════════════════════════════════════════════════════
with tab_url:
    with st.form("collect_form"):
        col_seller, col_date = st.columns(2)
        with col_seller:
            seller = st.text_input("판매처", placeholder="예: 패션스타트, 천가게")
        with col_date:
            purchase_date = st.date_input("구입일", value=date.today())
        url_text = st.text_area(
            "상품 URL (한 줄에 하나씩)",
            placeholder="https://...\nhttps://...",
            height=120,
        )
        submitted = st.form_submit_button("수집 시작", use_container_width=True, type="primary")

    if submitted:
        urls = [u.strip() for u in url_text.strip().splitlines() if u.strip()]
        if not urls:
            st.warning("URL을 한 줄에 하나씩 입력해주세요.")
        else:
            st.session_state.pending_urls    = urls
            st.session_state.results         = []
            st.session_state.duplicate_info  = None
            st.session_state.duplicate_url   = None
            st.session_state.force_run       = False
            st.session_state["_seller"]        = seller
            st.session_state["_purchase_date"] = str(purchase_date)

    if st.session_state.duplicate_info:
        dup = st.session_state.duplicate_info
        st.warning(
            f"⚠️ 이미 저장된 URL (id={dup['id']}, 저장일: {dup['created_at']})\n\n"
            f"**{dup['product_name']}**"
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("재수집 (덮어쓰기)", use_container_width=True, type="primary"):
                st.session_state.force_run = True
                st.session_state.duplicate_info = None
                st.rerun()
        with c2:
            if st.button("이 URL 건너뛰기", use_container_width=True):
                st.session_state.pending_urls = [
                    u for u in st.session_state.pending_urls
                    if u != st.session_state.duplicate_url
                ]
                st.session_state.duplicate_info = None
                st.session_state.duplicate_url  = None
                st.rerun()
        with c3:
            if st.button("전체 취소", use_container_width=True):
                st.session_state.pending_urls   = []
                st.session_state.duplicate_info = None
                st.session_state.duplicate_url  = None
                st.rerun()

    if st.session_state.pending_urls and not st.session_state.duplicate_info:
        url   = st.session_state.pending_urls[0]
        force = st.session_state.force_run
        st.session_state.force_run = False
        total = len(st.session_state.results) + len(st.session_state.pending_urls)
        done  = len(st.session_state.results)
        st.progress(done / total, text=f"처리 중 {done+1}/{total}: {url[:60]}...")
        with st.spinner(f"수집 중... ({url[:50]})"):
            try:
                info, row_id = collect_fabric_data(
                    url,
                    seller=st.session_state.get("_seller") or None,
                    purchase_date=st.session_state.get("_purchase_date") or None,
                    force=force,
                )
                st.session_state.results.append(("ok", url, info, row_id))
                st.session_state.pending_urls.pop(0)
                st.rerun()
            except DuplicateURLError as e:
                st.session_state.duplicate_info = e.existing
                st.session_state.duplicate_url  = url
                st.rerun()
            except LLMQuotaError as e:
                st.error(f"❌ LLM 할당량 초과 — 오늘 무료 요청 한도에 도달했습니다. 내일 다시 시도하거나 유료 API 키를 설정하세요.\n\n{e}")
                st.session_state.pending_urls = []
                st.rerun()

    if st.session_state.results and not st.session_state.pending_urls:
        st.success(f"✅ {len(st.session_state.results)}건 수집 완료")
        for _, url, info, row_id in st.session_state.results:
            with st.container(border=True):
                c_img, c_info = st.columns([1, 3])
                with c_img:
                    if info.image_url:
                        st.image(info.image_url, width="stretch")
                with c_info:
                    st.markdown(f"**{info.product_name}** `id={row_id}`")
                    st.caption(f"소재: {info.material or '—'}  |  규격: {info.size or '—'}  |  가격: {info.price or '—'}")
                    st.caption(f"색상: {info.color or '—'}  |  판매처: {info.seller or '—'}  |  구입일: {info.purchase_date or '—'}")


# ════════════════════════════════════════════════════════════
# TAB 2: 영수증 수집 — 3단계
# ════════════════════════════════════════════════════════════
with tab_rcpt:

    # ── 공통 입력 (판매처 + 구입일) ───────────────────────────
    rc1, rc2 = st.columns(2)
    with rc1:
        rcpt_seller = st.selectbox(
            "판매처",
            options=list(config.SELLER_SITES.keys()),
            key="rcpt_seller_select",
        )
    with rc2:
        rcpt_date = st.date_input("구입일", value=date.today(), key="rcpt_date_input")

    st.divider()

    # ── Step 1: 이미지 업로드 ─────────────────────────────────
    if st.session_state.rcpt_step == 1:
        st.subheader("Step 1 — 주문내역 이미지 업로드")
        uploaded = st.file_uploader(
            "영수증 / 주문목록 / 거래명세서 이미지를 드래그앤드롭 하세요",
            type=["jpg", "jpeg", "png", "webp"],
            label_visibility="collapsed",
        )
        if uploaded:
            st.image(uploaded, caption="업로드된 이미지", width="stretch")
            if st.button("상품명 추출하기", type="primary", use_container_width=True):
                mime = uploaded.type or "image/jpeg"
                with st.spinner("LLM이 상품 목록을 추출 중..."):
                    items = parse_receipt(uploaded.read(), mime_type=mime)
                if items:
                    # parse_receipt → list[dict{"name", "color"}]
                    st.session_state.rcpt_names = items
                    st.session_state.rcpt_step  = 2
                    st.rerun()
                else:
                    st.error("상품명을 추출하지 못했습니다. 이미지를 확인해주세요.")

    # ── Step 2: 상품명/색상 확인 및 편집 ─────────────────────
    elif st.session_state.rcpt_step == 2:
        st.subheader("Step 2 — 상품명 · 색상 확인")
        st.caption("추출된 정보를 확인하고 필요하면 수정하세요. 불필요한 항목은 ✕로 삭제할 수 있습니다.")

        # 헤더
        h1, h2, h3 = st.columns([4, 2, 1])
        h1.caption("상품명")
        h2.caption("색상 / 옵션")

        items = st.session_state.rcpt_names   # list[dict{"name", "color"}]
        updated = []
        for i, item in enumerate(items):
            col_name, col_color, col_del = st.columns([4, 2, 1])
            with col_name:
                new_name = st.text_input(
                    f"name_{i}", value=item["name"],
                    key=f"rcpt_name_{i}", label_visibility="collapsed",
                )
            with col_color:
                new_color = st.text_input(
                    f"color_{i}", value=item.get("color") or "",
                    key=f"rcpt_color_{i}", label_visibility="collapsed",
                    placeholder="(없음)",
                )
            with col_del:
                if st.button("✕", key=f"rcpt_del_{i}"):
                    items.pop(i)
                    st.session_state.rcpt_names = items
                    st.rerun()
            updated.append({"name": new_name, "color": new_color.strip() or None})

        st.session_state.rcpt_names = [it for it in updated if it["name"].strip()]

        col_back, col_next = st.columns(2)
        with col_back:
            if st.button("← 다시 업로드", use_container_width=True):
                st.session_state.rcpt_step = 1
                st.rerun()
        with col_next:
            if st.button("URL 탐색 시작 →", type="primary", use_container_width=True):
                seller_url = config.SELLER_SITES[rcpt_seller]
                found = []
                progress = st.progress(0)
                for idx, it in enumerate(st.session_state.rcpt_names):
                    progress.progress(
                        (idx + 1) / len(st.session_state.rcpt_names),
                        text=f"탐색 중 ({idx+1}/{len(st.session_state.rcpt_names)}): {it['name'][:30]}",
                    )
                    url = find_product_url(it["name"], seller_url)
                    found.append({
                        "name":  it["name"],
                        "color": it.get("color"),
                        "url":   url or "",
                        "found": url is not None,
                    })
                st.session_state.rcpt_found = found
                st.session_state.rcpt_step  = 3
                st.rerun()

    # ── Step 3: URL 탐색 결과 확인 ───────────────────────────
    elif st.session_state.rcpt_step == 3:
        st.subheader("Step 3 — URL 탐색 결과 확인")
        st.caption("탐색된 URL을 확인하고 잘못된 경우 직접 수정하세요. URL이 비어있는 항목은 수집에서 제외됩니다.")

        found = st.session_state.rcpt_found
        for i, item in enumerate(found):
            with st.container(border=True):
                c_name, c_url, c_status = st.columns([2, 4, 1])
                with c_name:
                    st.markdown(f"**{item['name']}**")
                    if item.get("color"):
                        st.caption(f"🎨 {item['color']}")
                with c_url:
                    new_url = st.text_input(
                        "URL", value=item["url"],
                        key=f"rcpt_url_{i}",
                        label_visibility="collapsed",
                        placeholder="URL을 직접 입력하거나 비워두면 제외됩니다",
                    )
                    found[i]["url"] = new_url
                with c_status:
                    if item["found"]:
                        st.success("자동")
                    elif new_url:
                        st.info("수동")
                    else:
                        st.warning("제외")
        st.session_state.rcpt_found = found

        col_back, col_collect = st.columns(2)
        with col_back:
            if st.button("← 상품명 수정", use_container_width=True):
                st.session_state.rcpt_step = 2
                st.rerun()
        with col_collect:
            ready = [f for f in found if f["url"].strip()]
            if st.button(f"수집 시작 ({len(ready)}건) →", type="primary", use_container_width=True):
                st.session_state.rcpt_pending = [
                    {"url": f["url"].strip(), "color": f.get("color")}
                    for f in found if f["url"].strip()
                ]
                st.session_state.rcpt_results = []
                st.session_state["_seller"]        = rcpt_seller
                st.session_state["_purchase_date"] = str(rcpt_date)
                st.rerun()

    # ── 영수증 탭 파이프라인 실행 ─────────────────────────────
    if st.session_state.rcpt_pending:
        pending_item = st.session_state.rcpt_pending[0]   # {"url": str, "color": Optional[str]}
        url   = pending_item["url"]
        color = pending_item.get("color")
        total = len(st.session_state.rcpt_results) + len(st.session_state.rcpt_pending)
        done  = len(st.session_state.rcpt_results)
        st.progress(done / total, text=f"수집 중 {done+1}/{total}: {url[:60]}...")
        with st.spinner(f"수집 중... ({url[:50]})"):
            try:
                info, row_id = collect_fabric_data(
                    url,
                    seller=st.session_state.get("_seller") or None,
                    purchase_date=st.session_state.get("_purchase_date") or None,
                    color=color,
                    force=False,
                )
                st.session_state.rcpt_results.append((url, info, row_id))
            except DuplicateURLError as e:
                # 중복은 건너뛰고 계속
                st.session_state.rcpt_results.append((url, None, None))
            except LLMQuotaError as e:
                st.error(f"❌ LLM 할당량 초과 — 오늘 무료 요청 한도에 도달했습니다. 내일 다시 시도하거나 유료 API 키를 설정하세요.\n\n{e}")
                st.session_state.rcpt_pending = []
                st.rerun()
            st.session_state.rcpt_pending.pop(0) if st.session_state.rcpt_pending else None
            st.rerun()

    if st.session_state.rcpt_results and not st.session_state.rcpt_pending:
        ok  = [(u, i, r) for u, i, r in st.session_state.rcpt_results if i is not None]
        dup = [(u, i, r) for u, i, r in st.session_state.rcpt_results if i is None]
        st.success(f"✅ {len(ok)}건 수집 완료" + (f"  |  ⚠️ {len(dup)}건 중복 건너뜀" if dup else ""))
        for url, info, row_id in ok:
            with st.container(border=True):
                c_img, c_info = st.columns([1, 3])
                with c_img:
                    if info.image_url:
                        st.image(info.image_url, width="stretch")
                with c_info:
                    st.markdown(f"**{info.product_name}** `id={row_id}`")
                    st.caption(f"소재: {info.material or '—'}  |  규격: {info.size or '—'}  |  가격: {info.price or '—'}")
                    st.caption(f"색상: {info.color or '—'}")
        if st.button("처음으로", use_container_width=True):
            st.session_state.rcpt_step    = 1
            st.session_state.rcpt_names   = []
            st.session_state.rcpt_found   = []
            st.session_state.rcpt_results = []
            st.rerun()


# ════════════════════════════════════════════════════════════
# 저장 목록 (공통)
# ════════════════════════════════════════════════════════════
st.divider()
st.subheader("저장된 원단 목록")

rows = list_all()
if not rows:
    st.caption("아직 저장된 항목이 없습니다.")
else:
    for row in rows:
        label = f"[{row['id']}] {row['product_name']}"
        if row.get("seller"):
            label += f"  —  {row['seller']}"
        with st.expander(label, expanded=False):
            col_img, col_info, col_actions = st.columns([1, 2, 1])
            with col_img:
                img_src = row.get("image_path") or row.get("image_url")
                if img_src:
                    st.image(img_src, width="stretch")
                else:
                    st.caption("이미지 없음")
            with col_info:
                edit_key = f"edit_{row['id']}"
                if st.session_state.get(edit_key):
                    with st.form(f"form_{row['id']}"):
                        new_name   = st.text_input("상품명",      value=row["product_name"])
                        new_mat    = st.text_input("소재",         value=row["material"] or "")
                        new_size   = st.text_input("규격",         value=row["size"] or "")
                        new_price  = st.text_input("가격",         value=row["price"] or "")
                        new_color  = st.text_input("색상 / 옵션",  value=row.get("color") or "")
                        new_seller = st.text_input("판매처",       value=row.get("seller") or "")
                        new_pdate  = st.text_input("구입일",       value=row.get("purchase_date") or "")
                        new_memo   = st.text_area("메모",          value=row.get("memo") or "", height=80)
                        c1, c2 = st.columns(2)
                        with c1:
                            if st.form_submit_button("저장", use_container_width=True, type="primary"):
                                update(row["id"], {
                                    "product_name":  new_name,
                                    "material":      new_mat or None,
                                    "size":          new_size or None,
                                    "price":         new_price or None,
                                    "color":         new_color or None,
                                    "seller":        new_seller or None,
                                    "purchase_date": new_pdate or None,
                                    "memo":          new_memo or None,
                                })
                                st.session_state[edit_key] = False
                                st.rerun()
                        with c2:
                            if st.form_submit_button("취소", use_container_width=True):
                                st.session_state[edit_key] = False
                                st.rerun()
                else:
                    st.markdown(f"**소재:** {row['material'] or '—'}")
                    st.markdown(f"**규격:** {row['size'] or '—'}")
                    st.markdown(f"**가격:** {row['price'] or '—'}")
                    st.markdown(f"**색상:** {row.get('color') or '—'}")
                    st.markdown(f"**판매처:** {row.get('seller') or '—'}")
                    st.markdown(f"**구입일:** {row.get('purchase_date') or '—'}")
                    if row.get("memo"):
                        st.markdown(f"**메모:** {row['memo']}")
                    st.markdown(f"**저장일:** {row['created_at']}")
                    st.markdown(f"**URL:** [{row['url'][:50]}...]({row['url']})")
            with col_actions:
                if st.button("✏️ 편집", key=f"btn_edit_{row['id']}", use_container_width=True):
                    st.session_state[f"edit_{row['id']}"] = True
                    st.rerun()
                if st.button("🗑️ 삭제", key=f"btn_del_{row['id']}", use_container_width=True):
                    delete(row["id"])
                    st.rerun()
