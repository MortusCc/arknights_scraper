import os
import time
import re
import requests
import concurrent.futures
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import unquote
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# 设置爬取图片的网址
base_url = "https://prts.wiki/index.php?title=%E7%89%B9%E6%AE%8A:%E6%90%9C%E7%B4%A2&limit=500&profile=images&search=%E7%AB%8B%E7%BB%98"

# 重定义请求头
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

def fetch_html(url, driver):
    """使用Selenium获取动态加载的网页内容"""
    try:
        driver.get(url)
        # 使用显式等待，直到搜索结果容器出现，最多等待30秒
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CLASS_NAME, "searchresults"))
        )
        return driver.page_source
    except Exception as e:
        print(f"使用Selenium获取网页 {url} 时发生错误: {e}")
        return None

def parse_image_links(html):
    soup = BeautifulSoup(html, "html.parser")
    search_results = soup.find("div", class_="searchresults")
    image_links = []
    if not search_results:
        print("未能找到搜索结果容器，请检查网页结构或URL。")
        return image_links
        
    for result in search_results.find_all("li", class_="mw-search-result"):
        table = result.find("table", class_="searchResultImage")
        if table:
            td = table.find("td", style="vertical-align: top")
            if td:
                link = td.find("a")
                if link and link.get("href"):
                    image_page_url = "https://prts.wiki" + link.get("href")
                    image_links.append(image_page_url)
    return image_links

def download_image(image_page_url, headers):
    try:
        image_page_response = requests.get(image_page_url, headers=headers, timeout=20)
        image_page_response.raise_for_status()
        image_page_response.encoding = "utf-8"
        
        image_page_soup = BeautifulSoup(image_page_response.text, "html.parser")
        
        char_name = ""
        # 方案一：从分类中提取干员名称
        cat_links = image_page_soup.select("#mw-normal-catlinks ul li a")
        for link in cat_links:
            cat_text = link.get_text(strip=True)
            if "立绘" in cat_text and "分类" not in cat_text:
                char_name = cat_text.replace("立绘", "").strip()
                break
        
        # 方案二：如果分类找不到，从标题解析
        if not char_name:
            heading = image_page_soup.find("h1", id="firstHeading")
            if heading:
                base_name = heading.get_text(strip=True).replace("文件:", "").rsplit('.png', 1)[0]
                match = re.search(r"立绘_([^_]+)", base_name) or re.search(r"([^(]+)", base_name)
                if match:
                    char_name = match.group(1).strip()

        if not char_name or char_name.startswith("预备干员"):
            return True # 跳过非干员图片，不计为失败

        char_name = re.sub(r'[\\/*?:"<>|]', "", char_name)

        full_image_link = image_page_soup.find("div", class_="fullImageLink", id="file")
        if full_image_link:
            image_link = full_image_link.find("a")
            if image_link and image_link.get("href"):
                image_download_url = image_link.get("href")
                
                image_name = f"{char_name}.png"
                
                if os.path.exists(image_name):
                    print(f"图片已存在，跳过下载：{image_name}")
                    return True

                image_download_response = requests.get(image_download_url, headers=headers, timeout=25)
                image_download_response.raise_for_status()
                with open(image_name, "wb") as f:
                    f.write(image_download_response.content)
                print(f"已成功下载图片：{image_name}")
                return True
        
        return False
    except requests.RequestException as e:
        print(f"下载图片失败：{image_page_url}，错误原因：{e}")
        return False

def main():
    print("正在启动浏览器...")
    chrome_options = Options()
    # chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument(f"user-agent={headers['User-Agent']}")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    all_image_links = []
    offset = 0
    
    try:
        while True:
            print(f"\n正在处理页面，偏移量: {offset}...")
            url = f"{base_url}&offset={offset}"
            html = fetch_html(url, driver)
            
            if not html:
                print("无法获取HTML，终止抓取。")
                break
                
            image_links = parse_image_links(html)
            if not image_links:
                print("当前页面未找到新的图片链接，抓取完成。")
                break
            
            all_image_links.extend(image_links)
            print(f"找到 {len(image_links)} 个新链接，总计 {len(all_image_links)} 个。")
            offset += 500
            time.sleep(2) # 等待一下，避免过快请求
            
    finally:
        driver.quit()
        print("浏览器已关闭。")

    if not all_image_links:
        print("未能获取到任何图片链接，程序退出。")
        return

    output_dir = "Arknights_PRTS"
    if not os.path.exists(output_dir):
        os.mkdir(output_dir)
    os.chdir(output_dir)
    
    print(f"\n开始下载 {len(all_image_links)} 张图片到 {output_dir} 文件夹...")
    
    failure_count = 0
    max_failures = 3
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_url = {executor.submit(download_image, link, headers): link for link in all_image_links}
        for future in concurrent.futures.as_completed(future_to_url):
            try:
                success = future.result()
                if not success:
                    failure_count += 1
                else:
                    failure_count = 0
            except Exception as exc:
                print(f'任务生成异常: {exc}')
                failure_count += 1

            if failure_count >= max_failures:
                print(f"\n连续失败达到 {max_failures} 次，正在终止所有下载任务...")
                for f in future_to_url:
                    f.cancel()
                break

    if failure_count >= max_failures:
        print("程序因失败次数过多而终止。")
    else:
        print("\n所有图片下载任务已处理完毕。")

if __name__ == "__main__":
    main()
