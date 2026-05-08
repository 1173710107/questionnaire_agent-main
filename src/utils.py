import requests
from bs4 import BeautifulSoup
import json
import os
from typing import List, Dict, Any, Optional
from datetime import datetime

class WebScraper:
    """网页抓取工具，用于获取网页内容并清洗"""
    
    @staticmethod
    def fetch_webpage(url: str) -> Optional[str]:
        """获取网页内容"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.text
        except Exception as e:
            print(f"获取网页内容失败: {url}, 错误: {str(e)}")
            return None
    
    @staticmethod
    def clean_html(html_content: str) -> str:
        """清洗HTML内容，提取正文"""
        if not html_content:
            return ""
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 移除脚本、样式和其他不需要的标签
        for script in soup(["script", "style", "nav", "footer", "header", "aside"]):
            script.decompose()
        
        # 获取文本
        text = soup.get_text(separator='\n')
        
        # 清理文本
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)
        
        return text

class QuestionnaireManager:
    """问卷管理工具，用于保存和加载问卷数据"""
    
    @staticmethod
    def save_questionnaire(questionnaire: Dict[str, Any], output_dir: str = "./output") -> str:
        """保存问卷到JSON文件"""
        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)
        
        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        topic = questionnaire.get("title", "questionnaire").replace(" ", "_").lower()
        filename = f"{topic}_{timestamp}.json"
        filepath = os.path.join(output_dir, filename)
        
        # 保存JSON文件
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(questionnaire, f, ensure_ascii=False, indent=2)
        
        return filepath
    
    @staticmethod
    def load_questionnaire(filepath: str) -> Dict[str, Any]:
        """从JSON文件加载问卷"""
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)

def score_article_relevance(topic: str, article_summary: str) -> float:
    """
    简单评分函数，根据主题词在摘要中的出现频率评分
    实际应用中可以使用更复杂的相关性评分算法
    """
    # 将主题和摘要转为小写进行比较
    topic_lower = topic.lower()
    summary_lower = article_summary.lower()
    
    # 计算主题词在摘要中出现的次数
    topic_words = topic_lower.split()
    score = 0
    
    for word in topic_words:
        if len(word) > 2:  # 忽略太短的词
            score += summary_lower.count(word) * 2
    
    # 如果完整主题短语出现，额外加分
    if topic_lower in summary_lower:
        score += 10
    
    return score