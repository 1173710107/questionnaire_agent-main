import os
import json
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
import argparse

from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from langchain_community.tools import TavilySearchResults
from langchain_community.utilities.tavily_search import TavilySearchAPIWrapper
from langchain.agents import AgentExecutor, create_react_agent
from langchain.tools import Tool
from langchain_community.llms import Tongyi

from src.utils import WebScraper, QuestionnaireManager, score_article_relevance

# 加载环境变量
load_dotenv()

class QuestionnaireGenerationAgent:
    """问卷生成Agent，使用通义千问模型生成调查问卷"""
    
    def __init__(
        self,
        dashscope_api_key: Optional[str] = None,
        tavily_api_key: Optional[str] = None,
        model_name: str = "qwen-max",
        num_rewrites: int = 3,
        num_articles: int = 10,
        num_questions: int = 10
    ):
        """
        初始化问卷生成Agent
        
        Args:
            dashscope_api_key: 通义千问API密钥
            tavily_api_key: Tavily搜索API密钥
            model_name: 通义千问模型名称
            num_rewrites: 主题改写数量
            num_articles: 筛选文章数量
            num_questions: 生成问题数量
        """
        # 设置API密钥
        self.dashscope_api_key = dashscope_api_key or os.getenv("DASHSCOPE_API_KEY")
        self.tavily_api_key = tavily_api_key or os.getenv("TAVILY_API_KEY")

        if tavily_api_key:
            os.environ["TAVILY_API_KEY"] = tavily_api_key
            self.tavily_api_key = tavily_api_key
        
        if not self.dashscope_api_key:
            raise ValueError("通义千问API密钥未提供，请设置DASHSCOPE_API_KEY环境变量或在初始化时提供")
        
        if not self.tavily_api_key:
            raise ValueError("Tavily API密钥未提供，请设置TAVILY_API_KEY环境变量或在初始化时提供")
        else:
            os.environ["TAVILY_API_KEY"] = self.tavily_api_key
        
        # 设置参数
        self.model_name = model_name
        self.num_rewrites = num_rewrites
        self.num_articles = num_articles
        self.num_questions = num_questions
        
        # 初始化LLM
        self.llm = Tongyi(
            model=self.model_name,
            dashscope_api_key=self.dashscope_api_key,
            temperature=0.7
        )
        
        # 初始化工具
        self.search_tool = TavilySearchResults(max_results=10)
        self.web_scraper = WebScraper()
        
        # 初始化提示模板
        self._init_prompts()
    
    def _init_prompts(self):
        """初始化各种提示模板"""
        # 主题改写提示
        self.rewrite_prompt = PromptTemplate(
            input_variables=["topic", "num_rewrites"],
            template="""
            请将以下主题改写成{num_rewrites}个不同的表述，以便进行更全面的搜索：
            
            原始主题: {topic}
            
            请直接返回改写后的主题列表，每行一个，不要有编号或其他格式。
            """
        )
        
        # 问卷生成提示
        self.questionnaire_prompt = PromptTemplate(
            input_variables=["topic", "article_contents", "num_questions"],
            template="""
            你是一位专业的问卷设计专家。请根据以下主题和相关文章内容，生成一份包含{num_questions}个问题的调查问卷。
            
            主题: {topic}
            
            相关文章内容:
            {article_contents}
            
            请遵循以下要求:
            1. 生成一个吸引人的问卷标题和简短的子标题
            2. 生成{num_questions}个与主题相关的问题
            3. 每个问题应有3-5个选项
            4. 问题应该覆盖主题的不同方面，避免重复
            5. 问题类型可以包括单选题、多选题或评分题
            
            请以JSON格式返回结果，格式如下:
            {{
                "title": "问卷标题",
                "subtitle": "问卷子标题",
                "questions": [
                    {{
                        "id": 1,
                        "type": "单选题/多选题/评分题",
                        "question": "问题内容",
                        "options": ["选项1", "选项2", "选项3", ...]
                    }},
                    ...
                ]
            }}
            
            只返回JSON格式的结果，不要有其他解释。
            """
        )
    
    def rewrite_topic(self, topic: str) -> List[str]:
        """改写主题以获取更多相关搜索结果"""
        chain = LLMChain(llm=self.llm, prompt=self.rewrite_prompt)
        result = chain.run(topic=topic, num_rewrites=self.num_rewrites)
        
        # 处理返回结果
        rewrites = [line.strip() for line in result.split('\n') if line.strip()]
        
        # 确保原始主题也包含在内
        if topic not in rewrites:
            rewrites.insert(0, topic)
        
        return rewrites
    
    def search_articles(self, topics: List[str]) -> List[Dict[str, Any]]:
        """使用Tavily搜索相关文章"""
        all_results = []
        
        for topic in topics:
            try:
                results = self.search_tool.run(topic)
                if isinstance(results, list):
                    all_results.extend(results)
                else:
                    print(f"搜索主题 '{topic}' 返回了非列表结果: {results}")
            except Exception as e:
                print(f"搜索主题 '{topic}' 时出错: {str(e)}")
        
        return all_results
    
    def filter_articles(self, articles: List[Dict[str, Any]], original_topic: str) -> List[Dict[str, Any]]:
        """根据相关性筛选文章"""
        # 为每篇文章评分
        scored_articles = []
        for article in articles:
            # 计算文章与主题的相关性分数
            score = score_article_relevance(original_topic, article.get('content', ''))
            scored_articles.append({
                'article': article,
                'score': score
            })
        
        # 按分数排序
        scored_articles.sort(key=lambda x: x['score'], reverse=True)
        
        # 去重 (基于URL)
        unique_urls = set()
        filtered_articles = []
        
        for item in scored_articles:
            article = item['article']
            url = article.get('url', '')
            
            if url and url not in unique_urls:
                unique_urls.add(url)
                filtered_articles.append(article)
                
                if len(filtered_articles) >= self.num_articles:
                    break
        
        return filtered_articles
    
    def fetch_article_contents(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """获取文章详细内容"""
        enriched_articles = []
        
        for article in articles:
            url = article.get('url', '')
            if not url:
                continue
                
            # 获取网页内容
            html_content = self.web_scraper.fetch_webpage(url)
            if not html_content:
                continue
                
            # 清洗HTML内容
            cleaned_content = self.web_scraper.clean_html(html_content)
            
            # 截取合适长度的内容
            max_content_length = 2000  # 限制内容长度
            if len(cleaned_content) > max_content_length:
                cleaned_content = cleaned_content[:max_content_length] + "..."
            
            # 添加清洗后的内容
            enriched_article = article.copy()
            enriched_article['full_content'] = cleaned_content
            enriched_articles.append(enriched_article)
        
        return enriched_articles
    
    def generate_questionnaire(self, topic: str, article_contents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """生成问卷"""
        # 合并文章内容
        combined_content = "\n\n".join([
            f"标题: {article.get('title', '无标题')}\n内容: {article.get('full_content', '')}"
            for article in article_contents
        ])
        
        # 如果内容太长，截取
        max_length = 8000
        if len(combined_content) > max_length:
            combined_content = combined_content[:max_length] + "..."
        
        # 生成问卷
        chain = LLMChain(llm=self.llm, prompt=self.questionnaire_prompt)
        result = chain.run(
            topic=topic,
            article_contents=combined_content,
            num_questions=self.num_questions
        )
        
        # 解析JSON结果
        try:
            # 查找JSON部分
            json_start = result.find('{')
            json_end = result.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = result[json_start:json_end]
                questionnaire = json.loads(json_str)
            else:
                raise ValueError("无法在结果中找到JSON格式的问卷")
                
            return questionnaire
        except Exception as e:
            print(f"解析问卷JSON时出错: {str(e)}")
            print(f"原始结果: {result}")
            # 返回一个基本结构
            return {
                "title": f"关于{topic}的调查问卷",
                "subtitle": "自动生成的问卷",
                "questions": [],
                "error": str(e),
                "raw_result": result
            }
    
    def run(self, topic: str, output_dir: str = "./output") -> Dict[str, Any]:
        """运行完整的问卷生成流程"""
        print(f"开始为主题 '{topic}' 生成问卷...")
        
        # 1. 改写主题
        print(f"正在改写主题...")
        rewritten_topics = self.rewrite_topic(topic)
        print(f"改写后的主题: {rewritten_topics}")
        
        # 2. 搜索相关文章
        print(f"正在搜索相关文章...")
        search_results = self.search_articles(rewritten_topics)
        print(f"找到 {len(search_results)} 篇相关文章")
        
        # 3. 筛选最相关的文章
        print(f"正在筛选最相关的文章...")
        filtered_articles = self.filter_articles(search_results, topic)
        print(f"筛选出 {len(filtered_articles)} 篇最相关文章")
        
        # 4. 获取文章详细内容
        print(f"正在获取文章详细内容...")
        enriched_articles = self.fetch_article_contents(filtered_articles)
        print(f"成功获取 {len(enriched_articles)} 篇文章的详细内容")
        
        # 5. 生成问卷
        print(f"正在生成问卷...")
        questionnaire = self.generate_questionnaire(topic, enriched_articles)
        
        # 6. 保存问卷
        filepath = QuestionnaireManager.save_questionnaire(questionnaire, output_dir)
        print(f"问卷已保存到: {filepath}")
        
        return questionnaire
    
    @staticmethod
    def main():
        """命令行入口点"""
        parser = argparse.ArgumentParser(description='生成调查问卷')
        parser.add_argument('--topic', type=str, required=True, help='问卷主题')
        parser.add_argument('--num_rewrites', type=int, default=3, help='主题改写数量')
        parser.add_argument('--num_articles', type=int, default=10, help='筛选文章数量')
        parser.add_argument('--num_questions', type=int, default=10, help='生成问题数量')
        parser.add_argument('--output_dir', type=str, default="./output", help='输出目录')
        
        args = parser.parse_args()
        
        agent = QuestionnaireGenerationAgent(
            num_rewrites=args.num_rewrites,
            num_articles=args.num_articles,
            num_questions=args.num_questions
        )
        
        questionnaire = agent.run(args.topic, args.output_dir)
        
        # 打印问卷标题和问题数量
        print("\n生成的问卷:")
        print(f"标题: {questionnaire.get('title', '无标题')}")
        print(f"子标题: {questionnaire.get('subtitle', '无子标题')}")
        print(f"问题数量: {len(questionnaire.get('questions', []))}")

if __name__ == "__main__":
    QuestionnaireGenerationAgent.main()