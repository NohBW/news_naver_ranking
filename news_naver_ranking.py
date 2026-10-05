
# news_naver_ranking.py

import sys
import os
import time
import ssl
import csv
import re
from datetime import datetime
from collections import Counter
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QListWidget, QListWidgetItem, QPushButton, QMessageBox, QDialog, QTextBrowser)
from PyQt5.QtCore import QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont

try:
    ssl._create_default_https_context = ssl._create_unverified_context
except AttributeError:
    pass

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

class CrawlingThread(QThread):
    crawling_finished = pyqtSignal(list)
    crawling_failed = pyqtSignal(str)

    def run(self):
        result_list = []
        chrome_options = Options()
        chrome_options.add_argument("--headless")  
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--ignore-certificate-errors")
        chrome_options.add_argument("--ignore-ssl-errors")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled") 
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
        chrome_options.add_argument("lang=ko_KR")
        
        try:
            service = Service()
            driver = webdriver.Chrome(service=service, options=chrome_options)
        except Exception as driver_err:
            self.crawling_failed.emit(f"크롬 드라이버 빌드 에러: {driver_err}")
            return
        
        url = "https://news.naver.com/main/ranking/popularDay.naver"
        try:
            driver.get(url)
            time.sleep(3.0) 
            
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.3);")
            time.sleep(1.0)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.6);")
            time.sleep(1.0)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.9);")
            time.sleep(1.0)
            
            soup = BeautifulSoup(driver.page_source, "html.parser")
        except Exception as e:
            self.crawling_failed.emit(f"페이지 로드 오류: {e}")
            driver.quit()
            return
            
        driver.quit()
        
        press_boxes = soup.select(".rankingnews_box, ._office_card, div[class*='rankingnews_box']")
        if not press_boxes:
            press_boxes = soup.find_all("div", attrs={"class": lambda x: x and "rankingnews" in x})

        if not press_boxes:
            self.crawling_failed.emit("랭킹 요소를 찾지 못했습니다.")
            return

        for box in press_boxes:
            try:
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
            except Exception:
                continue
                
        self.crawling_finished.emit(result_list)

class FetchContentThread(QThread):
    content_fetched = pyqtSignal(str, str) 
    content_failed = pyqtSignal(str)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        if not self.url:
            self.content_failed.emit("유효한 뉴스 뉴스 주소가 없습니다.")
            return
            
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--ignore-certificate-errors")
        
        try:
            service = Service()
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.get(self.url)
            time.sleep(2.0)
            soup = BeautifulSoup(driver.page_source, "html.parser")
            driver.quit()
            
            title_el = soup.select_one("#title_area, .media_end_head_title_text")
            title = title_el.get_text().strip() if title_el else "뉴스 제목을 가져올 수 없습니다."
            
            content_el = soup.select_one("#newsct_article, #articleBodyContents")
            if content_el:
                for s in content_el.select(".end_photo_org, script, style, .vod_area"):
                    s.extract()
                content = content_el.get_text().strip()
                content = re.sub(r'\n+', '\n', content)
            else:
                content = "뉴스 본문 내용을 파싱할 수 없는 유형의 페이지입니다. 링크를 확인해 주세요."
                
            self.content_fetched.emit(title, content)
        except Exception as e:
            self.content_failed.emit(f"기사 본문을 불러오는 중 오류 발생: {e}")

class NewsDialog(QDialog):
    def __init__(self, title, content, parent=None):
        super().__init__(parent)
        self.initUI(title, content)
        
    def initUI(self, title, content):
        layout = QVBoxLayout()
        
        title_label = QLabel(f"📄 기사 제목: {title}")
        title_label.setFont(QFont('Malgun Gothic', 16, QFont.Bold))
        title_label.setWordWrap(True)
        layout.addWidget(title_label)
        
        summary_text = summarize_text(content, num_sentences=3)
        
        summary_label = QLabel("🤖 AI 핵심 내용 3줄 요약")
        summary_label.setFont(QFont('Malgun Gothic', 14, QFont.Bold))
        summary_label.setStyleSheet("color: #2e7d32; margin-top: 10px;")
        layout.addWidget(summary_label)
        
        summary_browser = QTextBrowser()
        summary_browser.setFont(QFont('Malgun Gothic', 14))
        summary_browser.setStyleSheet("background-color: #f1f8e9; border: 1px solid #c5e1a5; border-radius: 4px; padding: 8px;")
        summary_browser.setText(summary_text)
        summary_browser.setMaximumHeight(200) 
        layout.addWidget(summary_browser)
        
        detail_label = QLabel("📰 뉴스 원본 본문")
        detail_label.setFont(QFont('Malgun Gothic', 13, QFont.Bold))
        detail_label.setStyleSheet("color: #555555; margin-top: 10px;")
        layout.addWidget(detail_label)
        
        browser = QTextBrowser()
        browser.setFont(QFont('Malgun Gothic', 13)) 
        browser.setText(content)
        layout.addWidget(browser)
        
        close_btn = QPushButton("닫기")
        close_btn.setFont(QFont('Malgun Gothic', 14, QFont.Bold))
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)
        
        self.setLayout(layout)
        self.setWindowTitle("뉴스 핵심 요약 및 본문 미리보기")
        self.resize(800, 700)

class NewsRankerApp(QWidget):
    def __init__(self):
        super().__init__()
        self.raw_data = []      
        self.initUI()
        
    def initUI(self):
        self.main_font = QFont('Malgun Gothic', 16)
        self.bold_font = QFont('Malgun Gothic', 16, QFont.Bold)
        
        main_layout = QVBoxLayout()
        
        self.time_label = QLabel()
        self.time_label.setFont(self.bold_font)
        self.time_label.setStyleSheet("color: #222222; padding: 10px; background-color: #e3f2fd; border: 1px solid #90caf9; border-radius: 6px;")
        main_layout.addWidget(self.time_label)
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_time)
        self.timer.start(1000)
        self.update_time()
        
        info_label = QLabel("💡 리스트의 기사 제목을 '더블클릭'하면 핵심 요약 및 본문 팝업창이 열립니다.")
        info_label.setFont(QFont('Malgun Gothic', 13, QFont.Bold))
        info_label.setStyleSheet("color: #0d47a1; padding-left: 5px;")
        main_layout.addWidget(info_label)
        
        self.summary_top_browser = QTextBrowser()
        self.summary_top_browser.setFont(QFont('Malgun Gothic', 14))
        self.summary_top_browser.setStyleSheet("background-color: #fff9c4; border: 2px solid #fff59d; border-radius: 6px; padding: 10px;")
        self.summary_top_browser.setHtml("<p style='color:gray;'>데이터를 수집하면 언론사 수와 주요 랭킹 요약 정보가 여기에 표시됩니다.</p>")
        self.summary_top_browser.setMaximumHeight(290) #230 , top 10 표시 
        main_layout.addWidget(self.summary_top_browser)
        
        self.news_list_widget = QListWidget()
        self.news_list_widget.setFont(self.main_font)
        self.news_list_widget.itemDoubleClicked.connect(self.on_item_double_clicked)
        main_layout.addWidget(self.news_list_widget)
        
        btn_layout = QHBoxLayout()
        
        self.refresh_btn = QPushButton("🔄 새로고침 (Update)")
        self.refresh_btn.setFont(self.bold_font)
        self.refresh_btn.setStyleSheet("background-color: #4caf50; color: white; padding: 10px; border-radius: 4px;")
        self.refresh_btn.clicked.connect(self.start_crawling)
        
        self.save_btn = QPushButton("📊 CSV 엑셀 파일 저장")
        self.save_btn.setFont(self.bold_font)
        self.save_btn.setEnabled(False) 
        self.save_btn.clicked.connect(self.save_to_csv)
        
        self.exit_btn = QPushButton("❌ 프로그램 종료")
        self.exit_btn.setFont(self.bold_font)
        self.exit_btn.clicked.connect(self.close)
        
        btn_layout.addWidget(self.refresh_btn)
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.exit_btn)
        main_layout.addLayout(btn_layout)
        
        self.setLayout(main_layout)
        self.setWindowTitle("네이버 뉴스 언론사별 1위~5위 종합 랭킹 수집기 (AI 요약 및 CSV 내보내기 지원)")
        
        self.showMaximized()
        self.start_crawling()

    def update_time(self):
        weeks = ['월', '화', '수', '목', '금', '토', '일']
        now = datetime.now()
        day_of_week = weeks[now.weekday()]
        time_str = now.strftime(f"%Y년 %m월 %d일({day_of_week}) %H시 %M분 %S초")
        self.time_label.setText(f"🕒 수집 시각 기준: {time_str}")

    def start_crawling(self):
        self.refresh_btn.setEnabled(False)
        self.save_btn.setEnabled(False)
        self.news_list_widget.clear()
        
        self.summary_top_browser.setHtml("<p style='color:#ff9800; font-weight:bold;'>🔄 최신 뉴스 트렌드를 실시간 분석하고 있습니다. 잠시만 기다려주세요...</p>")
        self.news_list_widget.addItem("🔄 데이터를 로딩 중입니다...")
        
        self.thread = CrawlingThread()
        self.thread.crawling_finished.connect(self.display_news)
        self.thread.crawling_failed.connect(self.handle_error)
        self.thread.start()

    def display_news(self, data):
        self.news_list_widget.clear()
        self.raw_data = data
        self.refresh_btn.setEnabled(True)

        if not data:
            self.summary_top_browser.setHtml("<p style='color:red;'>분석할 정보가 없습니다.</p>")
            self.news_list_widget.addItem("가져온 데이터가 없습니다.")
            return
            
        total_press_count = len(data)
        all_articles_flat = []
   
        for item in data:
            for art in item["articles"]:
                all_articles_flat.append((art["title"], item["press"], art["url"]))
        
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
        
        top_10_infos = []
        for group in issue_groups[:10]:
            rep_title, rep_press, rep_url = group["articles"][0]
            mention_count = len(group["articles"])
            top_10_infos.append(f"<b>[{rep_press}]</b> {rep_title} <font color='#1565c0' size='2'>({mention_count}개사 언급)</font>")
                    
        summary_html = f"<b style='font-size:16pt; color:#b71c1c;'>📊 실시간 수집 통계 리포트</b><br>"
        summary_html += f"<span style='font-size:14pt; color:#111111;'>• 수집된 총 언론사 수: <b>{total_press_count}개사</b></span><br>"
        summary_html += f"<span style='font-size:14pt; color:#111111;'>• 현재 가장 뜨거운 주요 랭킹 뉴스 Top 10 목록</span><br>"
        
        summary_html += "<table width='100%' style='border-top: 1px solid #e0e0e0; margin-top: 5px;'>"
        summary_html += "<tr>"
        
        summary_html += "<td width='50%' valign='top' style='padding-right: 15px;'>"
        for idx in range(0, min(5, len(top_10_infos))):
            summary_html += f"<p style='font-size:14pt; color:#333333; margin: 2px 0;'><b>{idx+1}위.</b> {top_10_infos[idx]}</p>"
        summary_html += "</td>"
        
        summary_html += "<td width='50%' valign='top' style='padding-left: 15px; border-left: 1px dashed #cccccc;'> "
        for idx in range(5, min(10, len(top_10_infos))):
            summary_html += f"<p style='font-size:14pt; color:#333333; margin: 2px 0;'><b>{idx+1}위.</b> {top_10_infos[idx]}</p>"
        summary_html += "</td>"
        
        summary_html += "</tr>"
        summary_html += "</table>"
            
        self.summary_top_browser.setHtml(summary_html)
        
        for item in data:
            press = item["press"]
            
            press_item = QListWidgetItem(f"[{press}]")
            press_item.setFont(QFont('Malgun Gothic', 18, QFont.Bold))
            press_item.setFlags(press_item.flags() & ~128) 
            self.news_list_widget.addItem(press_item)
            
            for art in item["articles"]:
                display_line = f"  • {art['rank']}위. {art['title']}"
                art_item = QListWidgetItem(display_line)
                art_item.setFont(QFont('Malgun Gothic', 16))
                art_item.setData(32, art['url']) 
                self.news_list_widget.addItem(art_item)
                
            space_item = QListWidgetItem("")
            space_item.setFlags(space_item.flags() & ~128)
            self.news_list_widget.addItem(space_item)
            
        self.save_btn.setEnabled(True) 

    def on_item_double_clicked(self, item):
        matched_url = item.data(32)
        if matched_url:
            self.time_label.setText("🕒 선택한 뉴스의 본문을 가져와 주요 핵심 내용 요약 수식을 적용하고 있습니다...")
            self.fetch_thread = FetchContentThread(matched_url)
            self.fetch_thread.content_fetched.connect(self.open_popup_dialog)
            self.fetch_thread.content_failed.connect(lambda err: QMessageBox.warning(self, "가져오기 실패", err))
            self.fetch_thread.start()

    def open_popup_dialog(self, title, content):
        self.update_time() 
        dialog = NewsDialog(title, content, self)
        dialog.exec_()

    def handle_error(self, err_msg):
        self.refresh_btn.setEnabled(True)
        self.summary_top_browser.setHtml("<p style='color:red;'>수집 실패</p>")
        self.news_list_widget.clear()
        self.news_list_widget.addItem(f"⚠️ 데이터 로드 실패: {err_msg}")

    def save_to_csv(self):
        if not self.raw_data:
            return
            
        filename = f"naver_news_ranking_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        try:
            with open(filename, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["수집시간", "언론사", "순위", "기사제목", "뉴스링크 주소"])
                
                current_time = self.time_label.text().replace("🕒 수집 시각 기준: ", "")
                for item in self.raw_data:
                    press_name = item["press"]
                    for art in item["articles"]:
                        writer.writerow([
                            current_time,
                            press_name,
                            f"{art['rank']}위",
                            art['title'],
                            art['url']
                        ])
                        
            QMessageBox.information(self, "CSV 저장 완료", f"엑셀 호환 CSV 연동 저장이 성공적으로 완료되었습니다!\n파일명: {filename}")
        except Exception as e:
            QMessageBox.critical(self, "저장 실패", f"CSV 파일 기록 중 에러가 발생했습니다:\n{e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    ex = NewsRankerApp()
    sys.exit(app.exec_())
