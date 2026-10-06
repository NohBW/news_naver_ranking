# naver_news_ranking_app.py
# streamlit

import streamlit as st
import pandas as pd
import datetime
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup
import urllib3
import re

# 경고 문구 숨기기
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 1. 브라우저 탭 및 페이지 기본 설정
st.set_page_config(
    page_title="네이버 뉴스 랭킹 종합 분석기",
    page_icon="📊",
    layout="wide",  # 통계 리포트 테이블과 레이아웃을 넓게 쓰기 위해 wide 모드 채택
    initial_sidebar_state="collapsed"
)

# 2. UI 고도화를 위한 커스텀 CSS 반영 (PyQt 스타일의 시각적 요소 이식)
st.markdown("""
    <style>
    html, body, [data-testid="stAppViewContainer"] {
        font-family: 'Malgun Gothic', -apple-system, sans-serif;
    }
    .custom-title-bar {
        background-color: #1e3a8a;
        color: white;
        padding: 14px;
        text-align: center;
        font-size: 22px;
        font-weight: bold;
        border-radius: 8px;
        margin-bottom: 5px;
    }
    .custom-time-label {
        font-size: 16px;
        font-weight: bold;
        text-align: center;
        color: #2563eb;
        background-color: #eff6ff;
        padding: 10px;
        border: 1px solid #bfdbfe;
        border-radius: 6px;
        margin-bottom: 15px;
    }
    .report-box {
        background-color: #fffde7;
        border: 2px solid #fff59d;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 20px;
    }
    .press-header {
        font-size: 18px;
        font-weight: bold;
        color: #1e293b;
        border-bottom: 2px solid #cbd5e1;
        padding-bottom: 4px;
        margin-top: 15px;
        margin-bottom: 8px;
    }
    .summary-box {
        background-color: #f0fdf4;
        border: 1px solid #bbf7d0;
        padding: 12px;
        border-radius: 6px;
        font-size: 15px;
        line-height: 1.6;
        color: #166534;
        margin-bottom: 10px;
    }
    .content-box {
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        padding: 12px;
        border-radius: 6px;
        font-size: 14px;
        line-height: 1.6;
        white-space: pre-wrap;
    }
    </style>
""", unsafe_allow_html=True)

# 3. 기존 알고리즘 이식: 텍스트 빈도수 기반 주요 내용 요약 함수
def summarize_text(text, num_sentences=3):
    if not text or len(text.strip()) < 20:
        return "본문 내용이 너무 짧아 요약할 수 없습니다."
        
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    sentences = [s.strip() for s in sentences if len(s.strip()) > 5]
    
    if len(sentences) <= num_sentences:
        return "\n\n".join(sentences)
        
    word_counts = {}
    for sentence in sentences:
        words = re.findall(r'[가-힣\w]+', sentence)
        for word in words:
            if len(word) > 1:
                word_counts[word] = word_counts.get(word, 0) + 1
                
    sentence_scores = []
    for idx, sentence in enumerate(sentences):
        score = 0
        words = re.findall(r'[가-힣\w]+', sentence)
        for word in words:
            score += word_counts.get(word, 0)
        if idx == 0 or idx == len(sentences) - 1:
            score *= 1.5
        sentence_scores.append((score, idx, sentence))
        
    sentence_scores.sort(key=lambda x: x[0], reverse=True)
    top_sentences = sentence_scores[:num_sentences]
    top_sentences.sort(key=lambda x: x[1])
    
    summary_lines = [f"• {item[2]}" for item in top_sentences]
    return "\n\n".join(summary_lines)

# 4. 고속 데이터 수집 기능 (Selenium의 무거운 부하를 지우고 requests로 최적화)
def refresh_all_data():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    url = "https://news.naver.com/main/ranking/popularDay.naver"
    result_list = []
    
    try:
        res = requests.get(url, headers=headers, timeout=7, verify=False)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            press_boxes = soup.select(".rankingnews_box, ._office_card, div[class*='rankingnews_box']")
            
            for box in press_boxes:
                press_name_el = box.select_one(".rankingnews_name, strong[class*='name'], .office_name")
                press_name = press_name_el.get_text().strip() if press_name_el else "알 수 없는 언론사"
                
                articles = box.select(".rankingnews_list li, ul li")
                press_articles = []
                
                for idx, article in enumerate(articles[:5], start=1):
                    title_el = article.select_one(".list_title, .rankingnews_title, a")
                    if not title_el:
                        continue
                    
                    title_text = title_el.get_text().strip()
                    if title_text.startswith(str(idx)) and len(title_text) > 2:
                        title_text = title_text.lstrip(f"{idx}위").lstrip(str(idx)).strip()
                    
                    link_el = article.select_one("a")
                    article_url = link_el['href'] if link_el and link_el.has_attr('href') else ""
                    if article_url and not article_url.startswith("http"):
                        article_url = "https://news.naver.com" + article_url
                        
                    press_articles.append({"rank": idx, "title": title_text, "url": article_url})
                
                if press_articles:
                    result_list.append({"press": press_name, "articles": press_articles})
                    
            st.session_state.raw_data = result_list
        else:
            st.error(f"데이터를 가져오지 못했습니다. (응답 코드: {res.status_code})")
    except Exception as e:
        st.error(f"크롤링 중 오류가 발생했습니다: {e}")

# 5. 뉴스 상세 본문 크롤링 함수
def fetch_article_content(url):
    if not url:
        return "유효한 뉴스 주소가 없습니다.", ""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        res = requests.get(url, headers=headers, timeout=5, verify=False)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            title_el = soup.select_one("#title_area, .media_end_head_title_text")
            title = title_el.get_text().strip() if title_el else "뉴스 제목을 가져올 수 없습니다."
            
            content_el = soup.select_one("#newsct_article, #articleBodyContents")
            if content_el:
                for s in content_el.select(".end_photo_org, script, style, .vod_area"):
                    s.extract()
                content = content_el.get_text().strip()
                content = re.sub(r'\n+', '\n', content)
            else:
                content = "뉴스 본문 내용을 파싱할 수 없는 유형의 페이지입니다."
            return title, content
    except Exception as e:
        return "오류 발생", f"기사 본문을 불러오는 중 오류 발생: {e}"
    return "실패", "데이터를 가져오지 못했습니다."

# --- 메인 화면 렌더링 시작 ---
st.markdown('<div class="custom-title-bar">📊 네이버 뉴스 언론사별 종합 랭킹 수집기</div>', unsafe_allow_html=True)

# 실시간 한국 시간(KST) 라벨 출력
now = datetime.datetime.now(ZoneInfo("Asia/Seoul"))
weeks = ['월', '화', '수', '목', '금', '토', '일']
time_str = now.strftime(f"%Y년 %m월 %d일({weeks[now.weekday()]}) %H시 %M분 %S초")
st.markdown(f'<div class="custom-time-label">🕒 수집 시각 기준: {time_str}</div>', unsafe_allow_html=True)

st.info("💡 리스트의 아코디언(▼) 메뉴를 확장하면 실시간 AI 핵심 요약 및 본문 전체 내용을 확인할 수 있습니다.")

# 세션 상태 변수 초기화
if "raw_data" not in st.session_state:
    st.session_state.raw_data = []

# 최초 실행 시 자동으로 데이터 로드
if not st.session_state.raw_data:
    with st.spinner("🔄 최신 뉴스 트렌드를 실시간 분석하고 있습니다. 잠시만 기다려주세요..."):
        refresh_all_data()

data = st.session_state.raw_data

# --- [상단 구역] 실시간 통계 리포트 및 주요이슈 이슈 매칭 알고리즘 ---
if data:
    total_press_count = len(data)
    all_articles_flat = []
    for item in data:
        for art in item["articles"]:
            all_articles_flat.append((art["title"], item["press"], art["url"]))
            
    # 키워드 자카드 유사도 분석 로직 연동
    issue_groups = []
    for title, press, url in all_articles_flat:
        words = set(re.findall(r'[가-힣\w]{2,}', title))
        if not words:
            continue
            
        matched_group = None
        for group in issue_groups:
            intersection = words.intersection(group["words"])
            union = words.union(group["words"])
            if intersection and (len(intersection) / len(union) >= 0.4):
                matched_group = group
                break
                
        if matched_group:
            matched_group["articles"].append((title, press, url))
            matched_group["words"].update(words)
        else:
            issue_groups.append({"words": words, "articles": [(title, press, url)]})
            
    issue_groups.sort(key=lambda x: len(x["articles"]), reverse=True)
    
    # 핫이슈 TOP 10 텍스트 데이터 추출
    top_10_infos = []
    for group in issue_groups[:10]:
        rep_title, rep_press, rep_url = group["articles"][0]
        mention_count = len(group["articles"])
        top_10_infos.append(f"<b>[{rep_press}]</b> {rep_title} <span style='color:#1565c0; font-size:12px;'>({mention_count}개사 언급)</span>")

    # 통계 리포트 박스 출력
    report_html = f"""
    <div class="report-box">
        <b style="font-size:18px; color:#b71c1c;">📊 실시간 수집 통계 리포트</b><br>
        <span style="font-size:15px; color:#111111;">• 수집된 총 언론사 수: <b>{total_press_count}개사</b></span><br>
        <span style="font-size:15px; color:#111111;">• 현재 가장 뜨거운 주요 랭킹 뉴스 Top 10 목록</span>
    </div>
    """
    st.markdown(report_html, unsafe_allow_html=True)
    
    # Top 10 가독성을 극대화하기 위해 2열 레이아웃으로 배치 (PyQt 테이블 대용)
    col_left, col_right = st.columns(2)
    with col_left:
        for idx in range(0, min(5, len(top_10_infos))):
            st.markdown(f"**{idx+1}위.** {top_10_infos[idx]}", unsafe_allow_html=True)
    with col_right:
        for idx in range(5, min(10, len(top_10_infos))):
            st.markdown(f"**{idx+1}위.** {top_10_infos[idx]}", unsafe_allow_html=True)

st.write("---")

# --- [하단 제어 구역] 새로고침 및 엑셀 다운로드 버튼 ---
col_btn1, col_btn2 = st.columns(2)

with col_btn1:
    if st.button("🔄 새로고침 (Update)", use_container_width=True, type="primary"):
        with st.spinner("최신 뉴스 트렌드를 가져오는 중..."):
            refresh_all_data()
            st.rerun()

with col_btn2:
    if data:
        all_rows = []
        for item in data:
            press_name = item["press"]
            for art in item["articles"]:
                all_rows.append([time_str, press_name, f"{art['rank']}위", art['title'], art['url']])
        
        df = pd.DataFrame(all_rows, columns=["수집시간", "언론사", "순위", "기사제목", "뉴스링크 주소"])
        csv_data = df.to_csv(index=False, encoding='utf-8-sig')
        
        st.download_button(
            label="📊 CSV 엑셀 파일 저장",
            data=csv_data,
            file_name=f"naver_news_ranking_{now.strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True
        )

# --- [뉴스 리스트 구역] 팝업 기능을 깔끔하게 대체하는 Streamlit Expander ---
if data:
    st.write("### 📰 언론사별 실시간 랭킹 뉴스 (1위 ~ 5위)")
    
    for item in data:
        st.markdown(f'<div class="press-header">🏢 {item["press"]}</div>', unsafe_allow_html=True)
        
        for art in item["articles"]:
            # PyQt의 더블클릭 팝업 기능을 Streamlit Expander 아코디언 메뉴로 직관적인 대체 구현
            with st.expander(f"📌 {art['rank']}위. {art['title']}"):
                with st.spinner("🤖 AI가 본문을 분석하여 핵심 내용을 추출하는 중..."):
                    title, content = fetch_article_content(art['url'])
                    summary_text = summarize_text(content, num_sentences=3)
                
                st.markdown(f"#### 📄 기사 원본 제목: {title}")
                
                st.markdown("##### 🤖 AI 핵심 내용 3줄 요약")
                st.markdown(f'<div class="summary-box">{summary_text}</div>', unsafe_allow_html=True)
                
                st.markdown("##### 📰 뉴스 원본 본문")
                st.markdown(f'<div class="content-box">{content}</div>', unsafe_allow_html=True)
else:
    st.warning("수집된 뉴스 데이터가 없습니다. 새로고침 버튼을 눌러주세요.")
