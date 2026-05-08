import os
import json
import sqlite3
import argparse
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional
from pathlib import Path
import datetime
from dotenv import load_dotenv
import base64
from io import BytesIO
import re
import markdown  # 添加 markdown 库

from langchain_community.llms import Tongyi
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain

# 加载环境变量
load_dotenv()

class QuestionnaireReportAgent:
    """问卷分析报告Agent，使用通义千问模型分析问卷结果并生成报告"""
    
    def __init__(
        self,
        db_path: str,
        questionnaire_id: str,
        dashscope_api_key: Optional[str] = None,
        model_name: str = "qwen-max",
        output_dir: str | None = None
    ):
        """
        初始化问卷分析报告Agent
        
        Args:
            db_path: SQLite数据库文件路径
            questionnaire_id: 问卷ID
            dashscope_api_key: 通义千问API密钥
            model_name: 通义千问模型名称
            output_dir: 报告输出目录
        """
        self.db_path = db_path
        self.questionnaire_id = questionnaire_id
        
        # 设置输出目录
        if output_dir is None:
            # 获取当前文件所在目录
            current_dir = os.path.dirname(os.path.abspath(__file__))
            # 获取项目根目录
            project_root = os.path.abspath(os.path.join(current_dir, '..'))
            # 设置输出目录
            self.output_dir = os.path.join(project_root, 'reports')
        else:
            self.output_dir = output_dir
            
        # 确保输出目录存在
        os.makedirs(self.output_dir, exist_ok=True)
        
        # 设置API密钥
        self.dashscope_api_key = dashscope_api_key or os.getenv("DASHSCOPE_API_KEY")
        
        if not self.dashscope_api_key:
            raise ValueError("通义千问API密钥未提供，请设置DASHSCOPE_API_KEY环境变量或在初始化时提供")
        
        # 初始化LLM
        self.llm = Tongyi(
            model=model_name,
            dashscope_api_key=self.dashscope_api_key,
            temperature=0.3  # 使用较低的温度以获得更确定性的结果
        )
        
        # 初始化提示模板
        self._init_prompts()
        
        # 加载问卷数据和提交结果
        self.questionnaire = self._load_questionnaire()
        self.submissions = self._load_submissions()
        
        if not self.questionnaire:
            raise ValueError(f"未找到ID为 {questionnaire_id} 的问卷")
        
        if not self.submissions:
            print(f"警告: 未找到ID为 {questionnaire_id} 的问卷提交结果，将生成空报告")
    
    def _init_prompts(self):
        """初始化各种提示模板"""
        # 问卷总体分析提示
        self.overall_analysis_prompt = PromptTemplate(
            input_variables=["questionnaire", "submission_count", "summary_stats"],
            template="""
            你是一位专业的数据分析师。请根据以下问卷数据和提交结果，进行全面的分析并生成一份总体分析报告。
            
            问卷信息:
            {questionnaire}
            
            提交数量: {submission_count}
            
            统计摘要:
            {summary_stats}
            
            请提供以下内容:
            1. 问卷总体情况分析，包括参与度、完成率等
            2. 主要发现和洞察
            3. 总结和建议
            
            请使用专业的数据分析语言，避免过于技术性的术语，使报告易于理解。
            """
        )
        
        # 问题详细分析提示
        self.question_analysis_prompt = PromptTemplate(
            input_variables=["question", "question_type", "options", "answer_stats"],
            template="""
            请根据以下问题数据和回答统计，对该问题进行详细分析。
            
            问题: {question}
            问题类型: {question_type}
            选项: {options}
            
            回答统计:
            {answer_stats}
            
            请提供以下内容:
            1. 该问题的回答分布分析
            2. 主要趋势和模式
            3. 可能的原因和影响因素
            4. 针对该问题的建议或洞察
            
            请使用专业的数据分析语言，避免过于技术性的术语，使分析易于理解。
            """
        )
    
    def _load_questionnaire(self) -> Dict[str, Any]:
        """从数据库加载问卷数据"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 查询问卷信息
        query = """
        SELECT questionnaire_id, title, description, file_path
        FROM questionnaires
        WHERE questionnaire_id = ?
        """
        
        cursor.execute(query, (self.questionnaire_id,))
        result = cursor.fetchone()
        
        if not result:
            conn.close()
            print(f"警告: 未找到ID为 {self.questionnaire_id} 的问卷")
            return {
                "title": "",
                "description": "",
                "questions": []
            }
        
        questionnaire_id, title, description, file_path = result
        print(f"找到问卷: ID={questionnaire_id}, 标题={title}, 文件路径={file_path}")
        
        # 从文件加载完整问卷数据
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                questionnaire_data = json.load(f)
                
            # 打印问卷结构以便调试
            print(f"问卷包含 {len(questionnaire_data.get('questions', []))} 个问题")
            for i, q in enumerate(questionnaire_data.get('questions', [])):
                q_id = q.get('id', f'未知ID_{i}')
                q_type = q.get('type', '未知类型')
                q_title = q.get('title', q.get('question', q.get('content', f'问题 {q_id}')))
                print(f"问题 {i+1}: ID={q_id}, 类型={q_type}, 标题={q_title}")
                
        except Exception as e:
            print(f"加载问卷文件时出错: {str(e)}")
            questionnaire_data = {
                "title": title,
                "description": description,
                "questions": []
            }
        
        conn.close()
        return questionnaire_data
    
    def _load_submissions(self) -> List[Dict[str, Any]]:
        """从数据库加载问卷提交结果"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 查询提交结果
        query = """
        SELECT submission_time, answer_data
        FROM questionnaire_results
        WHERE questionnaire_id = ?
        ORDER BY submission_time
        """
        
        cursor.execute(query, (self.questionnaire_id,))
        results = cursor.fetchall()
        
        submissions = []
        for submission_time, answer_data in results:
            try:
                submission = json.loads(answer_data)
                submission['submission_time'] = submission_time
                submissions.append(submission)
            except Exception as e:
                print(f"解析提交结果时出错: {str(e)}")
        
        conn.close()
        return submissions
    
    def _analyze_submissions(self) -> Dict[str, Any]:
        """分析问卷提交结果"""
        if not self.submissions:
            return {
                "submission_count": 0,
                "question_stats": {},
                "summary": "没有提交结果"
            }
        
        submission_count = len(self.submissions)
        question_stats = {}
        
        print(f"开始分析 {submission_count} 份提交结果...")
        print(f"问卷包含 {len(self.questionnaire.get('questions', []))} 个问题")
        
        # 分析每个问题的回答
        for question in self.questionnaire["questions"]:
            question_id = str(question["id"])
            question_type = question["type"]
            question_text = question.get("title", question.get("question", question.get("content", f"问题 {question_id}")))
            options = question.get("options", [])
            
            print(f"分析问题 {question_id}: {question_text} (类型: {question_type})")
            
            # 收集该问题的所有回答
            answers = []
            for submission in self.submissions:
                answer_key = f"q{question_id}"
                if answer_key in submission:
                    answer = submission[answer_key]
                    
                    # 处理多选题的JSON格式答案
                    if question_type == "多选题":
                        try:
                            answer = json.loads(answer)
                            print(f"  解析多选题答案: {answer}")
                        except Exception as e:
                            print(f"  解析多选题答案失败: {e}, 原始数据: {answer}")
                            answer = []
                    
                    answers.append(answer)
                else:
                    print(f"  警告: 提交中未找到问题 {question_id} 的答案")
            
            print(f"  收集到 {len(answers)} 个答案")
            
            # 统计回答
            if question_type == "单选题":
                # 计算每个选项的回答数量
                option_counts = {}
                for option in options:
                    option_counts[option] = 0
                
                for answer in answers:
                    if answer in option_counts:
                        option_counts[answer] += 1
                
                # 计算百分比
                percentages = {}
                for option, count in option_counts.items():
                    percentages[option] = round(count / submission_count * 100, 2) if submission_count > 0 else 0
                
                question_stats[question_id] = {
                    "question": question_text,
                    "type": question_type,
                    "options": options,
                    "counts": option_counts,
                    "percentages": percentages,
                    "total_answers": len(answers)
                }
                
            elif question_type == "多选题":
                # 计算每个选项的选择次数
                option_counts = {}
                for option in options:
                    option_counts[option] = 0
                
                for answer_list in answers:
                    if isinstance(answer_list, list):
                        for answer in answer_list:
                            if answer in option_counts:
                                option_counts[answer] += 1
                
                # 计算百分比（相对于提交总数）
                percentages = {}
                for option, count in option_counts.items():
                    percentages[option] = round(count / submission_count * 100, 2) if submission_count > 0 else 0
                
                question_stats[question_id] = {
                    "question": question_text,
                    "type": question_type,
                    "options": options,
                    "counts": option_counts,
                    "percentages": percentages,
                    "total_answers": len(answers)
                }
                
            elif question_type == "评分题":
                # 计算评分统计
                valid_scores = [int(a) for a in answers if a.isdigit()]
                
                if valid_scores:
                    avg_score = sum(valid_scores) / len(valid_scores)
                    min_score = min(valid_scores)
                    max_score = max(valid_scores)
                    
                    # 计算评分分布
                    score_distribution = {}
                    for score in range(1, 6):  # 假设评分范围是1-5
                        score_distribution[score] = valid_scores.count(score)
                else:
                    avg_score = 0
                    min_score = 0
                    max_score = 0
                    score_distribution = {score: 0 for score in range(1, 6)}
                
                question_stats[question_id] = {
                    "question": question_text,
                    "type": question_type,
                    "avg_score": round(avg_score, 2),
                    "min_score": min_score,
                    "max_score": max_score,
                    "score_distribution": score_distribution,
                    "total_answers": len(valid_scores)
                }
        
        # 生成总体摘要
        summary = {
            "submission_count": submission_count,
            "completion_rate": 100,  # 假设所有提交都是完整的
            "submission_period": {
                "start": self.submissions[0]["submission_time"] if self.submissions else "",
                "end": self.submissions[-1]["submission_time"] if self.submissions else ""
            }
        }
        
        return {
            "submission_count": submission_count,
            "question_stats": question_stats,
            "summary": summary
        }
    
    def _generate_charts(self, analysis_results: Dict[str, Any]) -> Dict[str, str]:
        """生成数据可视化图表"""
        charts = {}
        question_stats = analysis_results["question_stats"]
        
        print(f"开始生成图表，共 {len(question_stats)} 个问题...")
        
        # 设置中文字体支持
        plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
        
        for question_id, stats in question_stats.items():
            question_type = stats["type"]
            
            try:
                print(f"生成问题 {question_id} 的图表 (类型: {question_type})")
                
                plt.figure(figsize=(10, 6))
                
                if question_type in ["单选题", "多选题"]:
                    # 准备数据
                    options = stats["options"]
                    if not options:
                        print(f"  警告: 问题 {question_id} 没有选项")
                        continue
                        
                    counts = [stats["counts"].get(option, 0) for option in options]
                    
                    print(f"  选项: {options}")
                    print(f"  计数: {counts}")
                    
                    # 创建水平条形图
                    y_pos = np.arange(len(options))
                    plt.barh(y_pos, counts, align='center', alpha=0.7)
                    plt.yticks(y_pos, options)
                    
                    # 在条形上添加数值和百分比标签
                    for i, v in enumerate(counts):
                        percentage = stats["percentages"].get(options[i], 0)
                        plt.text(v + 0.1, i, f"{v} ({percentage}%)", va='center')
                    
                    plt.xlabel('回答数量')
                    plt.title(f'问题 {question_id}: {stats["question"]}')
                    plt.tight_layout()
                    
                elif question_type == "评分题":
                    # 准备数据
                    scores = list(range(1, 6))  # 假设评分范围是1-5
                    distribution = [stats["score_distribution"].get(score, 0) for score in scores]
                    
                    print(f"  评分分布: {distribution}")
                    
                    # 创建条形图
                    plt.bar(scores, distribution, alpha=0.7)
                    plt.xticks(scores)
                    
                    # 在条形上添加数值标签
                    for i, v in enumerate(distribution):
                        plt.text(i + 1, v + 0.1, str(v), ha='center')
                    
                    plt.xlabel('评分')
                    plt.ylabel('回答数量')
                    plt.title(f'问题 {question_id}: {stats["question"]} (平均分: {stats["avg_score"]})')
                    plt.tight_layout()
                else:
                    print(f"  警告: 不支持的问题类型 {question_type}")
                    continue
                
                # 将图表保存为base64编码的字符串
                buffer = BytesIO()
                plt.savefig(buffer, format='png', dpi=100)
                buffer.seek(0)
                image_png = buffer.getvalue()
                buffer.close()
                plt.close()
                
                chart_data = base64.b64encode(image_png).decode('utf-8')
                charts[question_id] = chart_data
                print(f"  成功生成问题 {question_id} 的图表")
            except Exception as e:
                print(f"  生成问题 {question_id} 的图表时出错: {str(e)}")
                import traceback
                traceback.print_exc()
        
        return charts
    
    def _generate_overall_analysis(self, analysis_results: Dict[str, Any]) -> str:
        """生成总体分析报告"""
        if analysis_results["submission_count"] == 0:
            return "没有提交结果，无法生成分析报告。"
        
        # 准备提示输入
        questionnaire_info = {
            "title": self.questionnaire.get("title", "未命名问卷"),
            "description": self.questionnaire.get("description", ""),
            "question_count": len(self.questionnaire.get("questions", [])),
        }
        
        submission_count = analysis_results["submission_count"]
        summary = analysis_results["summary"]
        
        # 使用新的方式调用LLM
        # 替换 LLMChain 为 prompt | llm 的方式
        result = self.overall_analysis_prompt | self.llm.bind(
            questionnaire=json.dumps(questionnaire_info, ensure_ascii=False),
            submission_count=submission_count,
            summary_stats=json.dumps(summary, ensure_ascii=False)
        )
        
        # 处理返回结果
        response = result.invoke({})
        
        if hasattr(response, 'content'):
            return response.content
        return str(response)
    
    # 替换 _markdown_to_html 函数
    def _markdown_to_html(self, markdown_text: str) -> str:
        """将Markdown文本转换为HTML"""
        try:
            # 使用 markdown 库进行转换
            html = markdown.markdown(markdown_text, extensions=['extra'])
            return html
        except Exception as e:
            print(f"Markdown转HTML出错: {str(e)}")
            # 如果转换失败，至少确保换行符被正确处理
            return markdown_text.replace('\n', '<br>')
    
    def _generate_question_analyses(self, analysis_results: Dict[str, Any]) -> Dict[str, str]:
        """为每个问题生成详细分析"""
        question_analyses = {}
        question_stats = analysis_results["question_stats"]
        
        for question_id, stats in question_stats.items():
            # 准备提示输入
            question = stats["question"]
            question_type = stats["type"]
            options = stats.get("options", [])
            
            # 使用新的方式调用LLM
            # 替换 LLMChain 为 prompt | llm 的方式
            result = self.question_analysis_prompt | self.llm.bind(
                question=question,
                question_type=question_type,
                options=json.dumps(options, ensure_ascii=False),
                answer_stats=json.dumps(stats, ensure_ascii=False)
            )
            
            # 处理返回结果
            response = result.invoke({})
            
            if hasattr(response, 'content'):
                question_analyses[question_id] = response.content
            else:
                question_analyses[question_id] = str(response)
        
        return question_analyses
    
    def generate_report(self) -> str:
        """生成完整的问卷分析报告"""
        # 分析提交结果
        analysis_results = self._analyze_submissions()
        
        # 如果没有提交结果，生成空报告
        if analysis_results["submission_count"] == 0:
            report_html = self._generate_empty_report()
            report_path = os.path.join(self.output_dir, f"report_{self.questionnaire_id}.html")
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(report_html)
            return report_path
        
        # 生成图表
        charts = self._generate_charts(analysis_results)
        
        # 生成总体分析
        overall_analysis = self._generate_overall_analysis(analysis_results)
        
        # 生成问题详细分析
        question_analyses = self._generate_question_analyses(analysis_results)
        
        # 生成HTML报告
        report_html = self._generate_html_report(
            analysis_results, 
            overall_analysis, 
            question_analyses, 
            charts
        )
        
        # 保存报告
        report_path = os.path.join(self.output_dir, f"report_{self.questionnaire_id}.html")
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report_html)
        
        print(f"报告已生成: {report_path}")
        return report_path
    
    def _generate_empty_report(self) -> str:
        """生成空报告"""
        questionnaire_title = self.questionnaire.get("title", "未命名问卷")
        
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>问卷分析报告 - {questionnaire_title}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {{ padding: 20px; }}
        .report-header {{ margin-bottom: 30px; text-align: center; }}
        .empty-message {{ text-align: center; padding: 50px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="report-header">
            <h1>问卷分析报告</h1>
            <h2>{questionnaire_title}</h2>
            <p>问卷ID: {self.questionnaire_id}</p>
            <p>生成时间: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
        </div>
        
        <div class="empty-message">
            <div class="alert alert-warning">
                <h3>暂无提交数据</h3>
                <p>该问卷尚未收到任何提交结果，无法生成分析报告。</p>
                <p>请等待用户提交问卷后再生成报告。</p>
            </div>
        </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""
        return html
    
    def _generate_html_report(
        self, 
        analysis_results: Dict[str, Any], 
        overall_analysis: str, 
        question_analyses: Dict[str, str], 
        charts: Dict[str, str]
    ) -> str:
        """生成HTML格式的报告"""
        questionnaire_title = self.questionnaire.get("title", "未命名问卷")
        submission_count = analysis_results["submission_count"]
        question_stats = analysis_results["question_stats"]
        
        # 将Markdown转换为HTML
        overall_analysis_html = self._markdown_to_html(overall_analysis)
        
        # 打印调试信息
        print(f"生成HTML报告: 问卷标题={questionnaire_title}, 提交数量={submission_count}")
        print(f"问题统计数据包含 {len(question_stats)} 个问题")
        print(f"问题分析数据包含 {len(question_analyses)} 个问题")
        print(f"图表数据包含 {len(charts)} 个问题")
        
        # 创建HTML报告
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>问卷分析报告 - {questionnaire_title}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {{ padding: 20px; }}
        .report-header {{ margin-bottom: 30px; text-align: center; }}
        .section {{ margin-bottom: 40px; }}
        .question-section {{ margin-bottom: 50px; padding: 20px; border: 1px solid #eee; border-radius: 5px; }}
        .chart-container {{ text-align: center; margin: 20px 0; }}
        .stats-table {{ margin: 20px 0; }}
        pre {{ white-space: pre-wrap; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="report-header">
            <h1>问卷分析报告</h1>
            <h2>{questionnaire_title}</h2>
            <p>问卷ID: {self.questionnaire_id}</p>
            <p>提交数量: {submission_count}</p>
            <p>生成时间: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
        </div>
        
        <div class="section">
            <h3>总体分析</h3>
            <div class="card">
                <div class="card-body">
                    {overall_analysis_html}
                </div>
            </div>
        </div>
        
        <div class="section">
            <h3>问题详细分析</h3>
"""
        
        # 检查是否有问题统计数据
        if not question_stats:
            html += """
            <div class="alert alert-warning">
                <p>未能生成问题详细分析，可能是因为问卷数据格式不正确或没有足够的回答。</p>
            </div>
"""
        else:
            # 为每个问题生成详细分析部分
            for question in self.questionnaire.get("questions", []):
                question_id = str(question.get("id", ""))
                if not question_id:
                    print(f"警告: 问题缺少ID")
                    continue
                    
                if question_id not in question_stats:
                    print(f"警告: 问题 {question_id} 在统计数据中不存在")
                    continue
                    
                stats = question_stats[question_id]
                question_text = stats["question"]
                question_type = stats["type"]
                
                # 将问题分析的Markdown转换为HTML
                question_analysis = question_analyses.get(question_id, "暂无分析")
                question_analysis_html = self._markdown_to_html(question_analysis)
                
                # 检查是否有图表数据
                chart_data = charts.get(question_id, '')
                if not chart_data:
                    print(f"警告: 问题 {question_id} 没有图表数据")
                
                html += f"""
                <div class="question-section">
                    <h4>问题 {question_id}: {question_text}</h4>
                    <p>类型: {question_type}</p>
                    
                    <div class="chart-container">
                        <img src="data:image/png;base64,{chart_data}" alt="问题{question_id}图表" class="img-fluid">
                    </div>
                    
                    <div class="stats-table">
                        <h5>统计数据</h5>
                        <table class="table table-bordered">
"""
                
                if question_type in ["单选题", "多选题"]:
                    html += """
                            <thead>
                                <tr>
                                    <th>选项</th>
                                    <th>回答数量</th>
                                    <th>百分比</th>
                                </tr>
                            </thead>
                            <tbody>
"""
                    
                    for option in stats["options"]:
                        count = stats["counts"][option]
                        percentage = stats["percentages"][option]
                        html += f"""
                                <tr>
                                    <td>{option}</td>
                                    <td>{count}</td>
                                    <td>{percentage}%</td>
                                </tr>
"""
                    
                    html += """
                            </tbody>
"""
                
                elif question_type == "评分题":
                    html += """
                            <thead>
                                <tr>
                                    <th>统计指标</th>
                                    <th>值</th>
                                </tr>
                            </thead>
                            <tbody>
"""
                    
                    html += f"""
                                <tr>
                                    <td>平均分</td>
                                    <td>{stats["avg_score"]}</td>
                                </tr>
                                <tr>
                                    <td>最低分</td>
                                    <td>{stats["min_score"]}</td>
                                </tr>
                                <tr>
                                    <td>最高分</td>
                                    <td>{stats["max_score"]}</td>
                                </tr>
"""
                    
                    html += """
                            </tbody>
"""
                
                html += """
                        </table>
                    </div>
                    
                    <div class="analysis">
                        <h5>分析</h5>
"""
                
                # 添加问题分析
                html += f"""
                        <div class="card">
                            <div class="card-body">
                                {question_analysis_html}
                            </div>
                        </div>
                    </div>
                </div>
"""
        
        # 完成HTML
        html += """
        </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""
        
        return html
    
    @staticmethod
    def main():
        """命令行入口点"""
        parser = argparse.ArgumentParser(description='生成问卷分析报告')
        parser.add_argument('--questionnaire_id', type=str, required=True, help='问卷ID')
        parser.add_argument('--db_path', type=str, help='SQLite数据库文件路径')
        parser.add_argument('--api_key', type=str, help='通义千问API密钥')
        parser.add_argument('--output_dir', type=str, help='报告输出目录')
        
        args = parser.parse_args()
        
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
        
        # 创建报告生成Agent
        agent = QuestionnaireReportAgent(
            db_path=db_path,
            questionnaire_id=args.questionnaire_id,
            dashscope_api_key=args.api_key,
            output_dir=args.output_dir
        )
        
        # 生成报告
        report_path = agent.generate_report()
        print(f"报告已生成: {report_path}")

if __name__ == "__main__":
    QuestionnaireReportAgent.main()