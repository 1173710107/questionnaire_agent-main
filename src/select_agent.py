import os
import json
import sqlite3
import argparse
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime

from langchain.prompts import PromptTemplate
from langchain_community.llms import Tongyi

class UserSelectionAgent:
    """用户圈选Agent，使用通义千问模型从数据库中筛选目标用户"""
    
    def __init__(
        self, 
        db_path: str | None = None,
        dashscope_api_key: str | None = "sk-c7518c0cc64c491ba765b65500e6993f",
        output_dir: str | None = None
    ):
        """
        初始化用户圈选Agent
        
        Args:
            db_path: SQLite数据库文件路径
            dashscope_api_key: 通义千问API密钥
            output_dir: 输出目录路径
        """
        # 设置数据库路径
        if db_path is None:
            # 获取当前文件所在目录
            current_dir = os.path.dirname(os.path.abspath(__file__))
            # 获取项目根目录（假设是src的上一级目录）
            project_root = os.path.abspath(os.path.join(current_dir, '..'))
            # 设置数据库路径
            self.db_path = os.path.join(project_root, 'db', 'questionnaire.db')
        else:
            self.db_path = db_path
            
        # 设置输出目录
        if output_dir is None:
            # 获取当前文件所在目录
            current_dir = os.path.dirname(os.path.abspath(__file__))
            # 获取项目根目录（假设是src的上一级目录）
            project_root = os.path.abspath(os.path.join(current_dir, '..'))
            # 设置输出目录
            self.output_dir = os.path.join(project_root, 'output')
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
            model="qwen-max",
            dashscope_api_key=self.dashscope_api_key,
            temperature=0.3  # 使用较低的温度以获得更确定性的结果
        )
    
    def get_table_schema(self) -> str:
        """获取数据库表结构"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 获取users表的结构
            cursor.execute("PRAGMA table_info(users)")
            columns = cursor.fetchall()
            
            schema = []
            for col in columns:
                col_id, name, type_, not_null, default_value, pk = col
                schema.append({
                    "name": name,
                    "type": type_,
                    "not_null": bool(not_null),
                    "primary_key": bool(pk)
                })
            
            # 格式化表结构为字符串
            schema_str = "用户表(users)结构:\n"
            for col in schema:
                schema_str += f"- {col['name']} ({col['type']})"
                if col['primary_key']:
                    schema_str += ", 主键"
                if col['not_null']:
                    schema_str += ", 非空"
                schema_str += "\n"
                
            conn.close()
            return schema_str
            
        except Exception as e:
            print(f"获取表结构时出错: {str(e)}")
            return "无法获取表结构"
    
    def generate_sql_query(self, preference: str, scale: int, topic: str) -> str:
        """根据用户偏好、规模和调查主题生成SQL查询语句"""
        # 获取表结构
        schema = self.get_table_schema()
        
        # 构建提示
        prompt_text = f"""
        你是一位数据分析专家，需要根据用户的需求生成SQLite查询语句，从用户表中筛选出符合条件的用户。

        数据库表结构:
        {schema}

        用户需求:
        1. 人群偏好: {preference}
        2. 人群规模: {scale}人
        3. 调查主题: {topic}

        请根据以上信息，生成一个SQLite查询语句，从users表中选择最适合该调查主题的用户。
        查询应该考虑用户的偏好特征，并限制结果数量为指定的人群规模。

        注意:
        1. 只返回SQL查询语句本身，不要包含任何Markdown格式、代码块标记(```)或其他非SQL语法
        2. 使用标准SQLite语法
        3. 查询应该包含所有用户字段
        4. 如果人群偏好中提到了特定属性，请在WHERE子句中体现
        5. 使用LIMIT子句限制结果数量
        6. 可以根据调查主题的相关性对结果进行排序
        """
        
        # 调用LLM生成SQL查询
        result = self.llm.invoke(prompt_text)
        
        # 清理结果，提取SQL语句
        sql = result.strip()
        
        # 移除可能的Markdown代码块标记
        sql = sql.replace("```sql", "").replace("```", "")
        
        # 如果结果包含"SQL查询语句:"或类似前缀，则只保留其后的内容
        prefixes = ["SQL查询语句:", "SQL:", "查询语句:", "以下是SQL查询语句:"]
        for prefix in prefixes:
            if prefix in sql:
                sql = sql.split(prefix, 1)[1].strip()
                break
        
        # 确保SQL语句以分号结尾
        if not sql.endswith(";"):
            sql += ";"
            
        return sql
    
    def execute_query(self, sql: str) -> List[Dict[str, Any]]:
        """执行SQL查询并返回结果"""
        try:
            conn = sqlite3.connect(self.db_path)
            # 设置行工厂以返回字典
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 执行查询
            cursor.execute(sql)
            rows = cursor.fetchall()
            
            # 转换为字典列表
            result = [dict(row) for row in rows]
            
            conn.close()
            return result
            
        except Exception as e:
            print(f"执行查询时出错: {str(e)}")
            return []
    
    def generate_user_report(self, users: List[Dict[str, Any]], preference: str, topic: str) -> Dict[str, Any]:
        """生成用户圈选报告"""
        # 构建报告
        report = {
            "selection_criteria": {
                "preference": preference,
                "topic": topic,
                "selected_count": len(users)
            },
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "selected_users": users
        }
        
        return report
    
    def save_report(self, report: Dict[str, Any]) -> str:
        """保存用户圈选报告到JSON文件"""
        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        topic = report["selection_criteria"]["topic"].replace(" ", "_").lower()
        filename = f"user_selection_{topic}_{timestamp}.json"
        filepath = os.path.join(self.output_dir, filename)
        
        # 保存JSON文件
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        return filepath
    
    def run(self, preference: str, scale: int, topic: str) -> Dict[str, Any]:
        """运行完整的用户圈选流程"""
        print(f"开始圈选用户...")
        print(f"人群偏好: {preference}")
        print(f"人群规模: {scale}人")
        print(f"调查主题: {topic}")
        
        # 1. 生成SQL查询
        print("正在生成SQL查询...")
        sql = self.generate_sql_query(preference, scale, topic)
        print(f"生成的SQL查询: {sql}")
        
        # 2. 执行查询
        print("正在执行查询...")
        selected_users = self.execute_query(sql)
        print(f"查询到 {len(selected_users)} 个符合条件的用户")
        
        # 3. 生成报告
        print("正在生成用户圈选报告...")
        report = self.generate_user_report(selected_users, preference, topic)
        
        # 4. 保存报告
        filepath = self.save_report(report)
        print(f"用户圈选报告已保存到: {filepath}")
        
        return report
    
    @staticmethod
    def main():
        """命令行入口点"""
        parser = argparse.ArgumentParser(description='从数据库中圈选目标用户')
        parser.add_argument('--preference', type=str, required=True, help='人群偏好描述')
        parser.add_argument('--scale', type=int, required=True, help='人群规模')
        parser.add_argument('--topic', type=str, required=True, help='调查主题')
        parser.add_argument('--api_key', type=str, help='通义千问API密钥')
        parser.add_argument('--db_path', type=str, help='SQLite数据库文件路径')
        parser.add_argument('--output_dir', type=str, help='输出目录路径')
        
        args = parser.parse_args()
        
        # 创建用户圈选Agent
        agent = UserSelectionAgent(
            db_path=args.db_path,
            dashscope_api_key=args.api_key,
            output_dir=args.output_dir
        )
        
        # 运行用户圈选流程
        report = agent.run(
            preference=args.preference,
            scale=args.scale,
            topic=args.topic
        )
        
        # 打印圈选结果摘要
        print("\n用户圈选完成!")
        print(f"共圈选 {len(report['selected_users'])} 个用户")
        print(f"报告已保存到: {args.output_dir or '默认输出目录'}")

if __name__ == "__main__":
    UserSelectionAgent.main()