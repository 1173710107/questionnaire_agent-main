import os
import json
import sqlite3
import argparse
import re
from typing import Dict, Any, List, Optional
from pathlib import Path
import uvicorn
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, SecretStr
import datetime
import dashscope
from langchain_community.llms import Tongyi

class QuestionnaireServiceAgent:
    """问卷调查服务Agent，使用通义千问模型生成HTML问卷并处理提交结果"""
    
    def __init__(
        self, 
        questionnaire_path: str,
        db_path: str | None = None,
        dashscope_api_key: str | None = "sk-c7518c0cc64c491ba765b65500e6993f",  # 修改为通义千问API密钥
        host: str = "127.0.0.1",
        port: int = 8000
    ):
        """
        初始化问卷调查服务Agent
        
        Args:
            questionnaire_path: 问卷JSON文件路径
            db_path: SQLite数据库文件路径
            dashscope_api_key: 通义千问API密钥
            host: 服务主机地址
            port: 服务端口
        """
        self.questionnaire_path = questionnaire_path
        self.host = host
        self.port = port
        
        # 加载问卷数据
        with open(questionnaire_path, 'r', encoding='utf-8') as f:
            self.questionnaire = json.load(f)
            
        # 设置数据库路径
        if db_path is None:
            # 获取当前文件所在目录
            current_dir = os.path.dirname(os.path.abspath(__file__))
            # 获取项目根目录（假设是src的上一级目录）
            project_root = os.path.abspath(os.path.join(current_dir, '..'))
            # 设置数据库路径
            self.db_path = os.path.join(project_root, 'db', 'questionnaire_results.db')
        else:
            self.db_path = db_path
            
        # 确保数据库目录存在
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            
        self.dashscope_api_key = dashscope_api_key or os.getenv("DASHSCOPE_API_KEY")
        
        if not self.dashscope_api_key:
            raise ValueError("通义千问API密钥未提供，请设置DASHSCOPE_API_KEY环境变量或在初始化时提供")
        
        dashscope.api_key = self.dashscope_api_key
        
        self.llm = Tongyi(
            model="qwen-max",
            dashscope_api_key=self.dashscope_api_key,
            temperature=0.3
        )
        
        # 设置模板目录
        # 获取项目根目录的templates文件夹路径
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(current_dir, '..'))
        self.templates_dir = os.path.join(project_root, 'templates')
        os.makedirs(self.templates_dir, exist_ok=True)
        
        # 设置静态文件目录
        self.static_dir = os.path.join(project_root, 'static')
        os.makedirs(self.static_dir, exist_ok=True)
        
        # 创建FastAPI应用
        self.app = FastAPI(title="问卷调查服务")
        
        # 设置模板引擎
        self.templates = Jinja2Templates(directory=self.templates_dir)
        
        # 挂载静态文件目录
        self.app.mount("/static", StaticFiles(directory=self.static_dir), name="static")
        
        # 设置路由
        self.setup_routes()
        
        # 创建数据库表
        self.create_database_tables()
        
        # 记录问卷信息到数据库
        self.record_questionnaire_info()
    
    def generate_html_template(self):
        """生成HTML问卷模板"""
        # 获取问卷ID
        questionnaire_id = os.path.basename(self.questionnaire_path).split('.')[0]
        
        # 直接使用备用模板生成方法，跳过模型生成
        print("使用备用方法直接生成问卷模板...")
        template_path = self._generate_fallback_template()
        
        # 生成感谢页面
        thank_you_prompt = f"""
        请生成一个简单的感谢页面，感谢用户提交问卷"{self.questionnaire['title']}"。
        
        要求:
        1. 使用与问卷页面相同的样式
        2. 包含感谢信息和问卷标题
        3. 可以添加一个返回首页的链接
        4. 在页面中显示问卷ID: {questionnaire_id}
        5. 不要在HTML中包含任何markdown标记，如```或类似标记
        
        只返回完整的HTML代码，不要有其他解释。
        """
        
        thank_you_response = self.llm.invoke(thank_you_prompt)
        
        # 提取内容并处理
        if hasattr(thank_you_response, 'content'):
            thank_you_html = thank_you_response.content
        else:
            thank_you_html = str(thank_you_response)
        
        # 清理可能的markdown标记
        # 清理markdown标记
        thank_you_html = re.sub(r'```[a-zA-Z]*\n?|```', '', thank_you_html).strip()
        
        # 保存感谢页面模板，使用问卷ID命名
        thank_you_path = os.path.join(self.templates_dir, f"thank_you_{questionnaire_id}.html")
        with open(thank_you_path, 'w', encoding='utf-8') as f:
            f.write(thank_you_html)
            
        return template_path

    def _generate_fallback_template(self):
        """使用备用方法生成问卷模板"""
        questionnaire_id = os.path.basename(self.questionnaire_path).split('.')[0]
        template_path = os.path.join(self.templates_dir, f"questionnaire_{questionnaire_id}.html")
        
        # 创建基本的Bootstrap模板
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{self.questionnaire.get('title', '问卷调查')} - {questionnaire_id}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {{ padding: 20px; }}
        .question {{ margin-bottom: 25px; padding: 15px; border: 1px solid #eee; border-radius: 5px; }}
        .question-title {{ font-weight: bold; margin-bottom: 15px; color: #333; }}
        .rating-container {{ display: flex; align-items: center; }}
        .rating-item {{ margin-right: 15px; }}
        .form-check {{ margin-bottom: 8px; }}
        .card-header {{ background-color: #4a6bdf !important; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="row">
            <div class="col-md-8 offset-md-2">
                <div class="card mt-4 mb-4 shadow">
                    <div class="card-header bg-primary text-white">
                        <h2 class="text-center">{self.questionnaire.get('title', '问卷调查')}</h2>
                        <p class="text-center">问卷ID: {questionnaire_id}</p>
                    </div>
                    <div class="card-body">
                        <p class="lead">{self.questionnaire.get('description', '')}</p>
                        
                        <form action="/submit" method="post">
"""
        
        # 为每个问题生成HTML
        for question in self.questionnaire["questions"]:
            q_id = str(question["id"])
            # 使用get方法安全地获取问题标题，如果不存在则使用问题内容或ID作为标题
            q_title = question.get("title", question.get("question", question.get("content", f"问题 {q_id}")))
            q_type = question["type"]
            q_options = question.get("options", [])
            
            html += f"""
                            <div class="question">
                                <div class="question-title">{q_id}. {q_title}</div>
"""
            
            if q_type == "单选题":
                for option in q_options:
                    option_id = re.sub(r'[^a-zA-Z0-9]', '_', str(option))
                    html += f"""
                                <div class="form-check">
                                    <input class="form-check-input" type="radio" name="q{q_id}" id="q{q_id}_{option_id}" value="{option}" required>
                                    <label class="form-check-label" for="q{q_id}_{option_id}">{option}</label>
                                </div>
"""
            elif q_type == "多选题":
                for option in q_options:
                    option_id = re.sub(r'[^a-zA-Z0-9]', '_', str(option))
                    html += f"""
                                <div class="form-check">
                                    <input class="form-check-input" type="checkbox" name="q{q_id}" id="q{q_id}_{option_id}" value="{option}">
                                    <label class="form-check-label" for="q{q_id}_{option_id}">{option}</label>
                                </div>
"""
            elif q_type == "评分题":
                html += f"""
                                <div class="rating-container">
"""
                for i in range(1, 6):  # 1-5分
                    html += f"""
                                    <div class="rating-item">
                                        <input class="form-check-input" type="radio" name="q{q_id}" id="q{q_id}_{i}" value="{i}" required>
                                        <label class="form-check-label" for="q{q_id}_{i}">{i}</label>
                                    </div>
"""
                html += f"""
                                </div>
"""
            
            html += f"""
                            </div>
"""
        
        # 完成表单
        html += """
                            <div class="text-center mt-4">
                                <button type="submit" class="btn btn-primary btn-lg">提交问卷</button>
                            </div>
                        </form>
                    </div>
                </div>
            </div>
        </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""
        
        # 保存模板
        with open(template_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        print(f"已生成问卷模板: {template_path}")
        return template_path

    def setup_routes(self):
        """设置FastAPI路由"""
        @self.app.get("/", response_class=HTMLResponse)
        async def index(request: Request):
            """问卷首页"""
            questionnaire_id = os.path.basename(self.questionnaire_path).split('.')[0]
            template_path = os.path.join(self.templates_dir, f"questionnaire_{questionnaire_id}.html")
            with open(template_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            return HTMLResponse(content=html_content)
        
        @self.app.post("/submit")
        async def submit(request: Request):
            """提交问卷"""
            form_data = await request.form()
            
            # 处理表单数据
            submission = {}
            submission["submission_time"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            submission["questionnaire_id"] = os.path.basename(self.questionnaire_path).split('.')[0]
            
            # 处理每个问题的答案
            for question in self.questionnaire["questions"]:
                question_id = str(question["id"])
                question_type = question["type"]
                
                if question_type == "多选题":
                    # 多选题可能有多个值
                    answers = form_data.getlist(f"q{question_id}")
                    # 将多选答案转换为JSON格式存储，便于后续解析
                    submission[f"q{question_id}"] = json.dumps(answers, ensure_ascii=False) if answers else "[]"
                else:
                    # 单选题或评分题只有一个值
                    submission[f"q{question_id}"] = form_data.get(f"q{question_id}", "")
            
            # 保存提交结果到数据库
            self.save_submission(submission)
            
            # 重定向到感谢页面
            return RedirectResponse(url="/thank-you", status_code=303)
        
        @self.app.get("/thank-you", response_class=HTMLResponse)
        async def thank_you(request: Request):
            """感谢页面"""
            questionnaire_id = os.path.basename(self.questionnaire_path).split('.')[0]
            template_path = os.path.join(self.templates_dir, f"thank_you_{questionnaire_id}.html")
            with open(template_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            return HTMLResponse(content=html_content)

    def create_database_tables(self):
        """创建数据库表存储问卷信息和结果"""
        # 连接数据库
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 创建问卷信息表
        create_questionnaire_table_sql = """
        CREATE TABLE IF NOT EXISTS questionnaires (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            questionnaire_id TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            description TEXT,
            created_time TEXT NOT NULL,
            file_path TEXT NOT NULL,
            question_count INTEGER NOT NULL
        );
        """
        
        # 创建问卷结果表（所有问卷共用一张表）
        create_results_table_sql = """
        CREATE TABLE IF NOT EXISTS questionnaire_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            questionnaire_id TEXT NOT NULL,
            submission_time TEXT NOT NULL,
            answer_data TEXT NOT NULL
        );
        """
        
        try:
            cursor.execute(create_questionnaire_table_sql)
            cursor.execute(create_results_table_sql)
            conn.commit()
            print("成功创建数据库表")
        except Exception as e:
            print(f"创建数据库表时出错: {str(e)}")
        finally:
            conn.close()
        
        # 设置结果表名
        self.results_table_name = "questionnaire_results"

    def record_questionnaire_info(self):
        """记录问卷信息到数据库"""
        # 连接数据库
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 获取问卷ID
        questionnaire_id = os.path.basename(self.questionnaire_path).split('.')[0]
        
        # 准备问卷信息
        questionnaire_info = {
            "questionnaire_id": questionnaire_id,
            "title": self.questionnaire.get("title", "未命名问卷"),
            "description": self.questionnaire.get("description", ""),
            "created_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "file_path": self.questionnaire_path,
            "question_count": len(self.questionnaire.get("questions", []))
        }
        
        # 构建INSERT语句
        insert_sql = """
        INSERT OR REPLACE INTO questionnaires 
        (questionnaire_id, title, description, created_time, file_path, question_count)
        VALUES (?, ?, ?, ?, ?, ?)
        """
        
        values = (
            questionnaire_info["questionnaire_id"],
            questionnaire_info["title"],
            questionnaire_info["description"],
            questionnaire_info["created_time"],
            questionnaire_info["file_path"],
            questionnaire_info["question_count"]
        )
        
        try:
            cursor.execute(insert_sql, values)
            conn.commit()
            print(f"成功记录问卷信息: {questionnaire_info['title']}")
        except Exception as e:
            print(f"记录问卷信息时出错: {str(e)}")
        finally:
            conn.close()

    def save_submission(self, submission: Dict[str, Any]):
        """保存提交结果到数据库"""
        # 连接数据库
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 获取问卷ID和提交时间
        questionnaire_id = submission["questionnaire_id"]
        submission_time = submission["submission_time"]
        
        # 将所有答案数据转换为JSON格式
        answer_data = json.dumps(submission, ensure_ascii=False)
        
        # 构建INSERT语句
        insert_sql = f"""
        INSERT INTO {self.results_table_name} 
        (questionnaire_id, submission_time, answer_data)
        VALUES (?, ?, ?)
        """
        
        values = (questionnaire_id, submission_time, answer_data)
        
        try:
            cursor.execute(insert_sql, values)
            conn.commit()
            print(f"成功保存提交结果")
        except Exception as e:
            print(f"保存提交结果时出错: {str(e)}")
        finally:
            conn.close()

    def run_service(self):
        """运行问卷调查服务"""
        # 生成HTML模板
        print("正在生成HTML问卷模板...")
        template_path = self.generate_html_template()
        print(f"HTML模板已生成: {template_path}")
        
        # 启动FastAPI服务
        print(f"正在启动问卷调查服务，访问地址: http://{self.host}:{self.port}")
        uvicorn.run(self.app, host=self.host, port=self.port)
    
    @staticmethod
    def main():
        """命令行入口点"""
        parser = argparse.ArgumentParser(description='启动问卷服务')
        parser.add_argument('--questionnaire', type=str, required=True, help='问卷JSON文件路径')
        parser.add_argument('--port', type=int, default=8000, help='服务端口')
        parser.add_argument('--host', type=str, default="127.0.0.1", help='服务主机')
        parser.add_argument('--db_path', type=str, help='SQLite数据库文件路径')
        parser.add_argument('--api_key', type=str, help='通义千问API密钥（优先于环境变量）')
        
        args = parser.parse_args()
        
        # 处理问卷路径 - 修复相对路径问题
        questionnaire_path = args.questionnaire
        if not os.path.isabs(questionnaire_path):
            # 如果是相对路径，则转换为绝对路径
            # 获取当前工作目录
            cwd = os.getcwd()
            questionnaire_path = os.path.abspath(os.path.join(cwd, questionnaire_path))
        
        # 确认文件存在
        if not os.path.exists(questionnaire_path):
            print(f"错误: 问卷文件 {questionnaire_path} 不存在")
            return
            
        print(f"使用问卷文件: {questionnaire_path}")
        
        # 设置数据库路径
        if args.db_path is None:
            # 获取当前文件所在目录
            current_dir = os.path.dirname(os.path.abspath(__file__))
            # 获取项目根目录
            project_root = os.path.abspath(os.path.join(current_dir, '..'))
            # 设置数据库路径
            db_path = os.path.join(project_root, 'db', 'questionnaire_results.db')
        else:
            db_path = args.db_path
        
        # 创建服务Agent
        agent = QuestionnaireServiceAgent(
            questionnaire_path=questionnaire_path,
            db_path=db_path,
            dashscope_api_key=args.api_key
        )
        
        # 启动服务
        agent.run_service()  # 修改这里：使用 run_service() 而不是 start()

if __name__ == "__main__":
    QuestionnaireServiceAgent.main()