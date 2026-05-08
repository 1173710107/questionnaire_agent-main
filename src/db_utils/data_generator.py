import os
import sqlite3
import json
from typing import List, Dict, Any
from pathlib import Path

from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from langchain_community.llms import Tongyi

class DatabaseGenerator:
    """数据库生成工具，用于创建SQLite数据库和生成样例数据"""
    
    def __init__(
        self, 
        db_path: str | None = None,
        dashscope_api_key: str | None = None
    ):
        """
        初始化数据库生成工具
        
        Args:
            db_path: SQLite数据库文件路径，默认为项目根目录下的db/questionnaire.db
            dashscope_api_key: 通义千问API密钥
        """
        # 如果未提供db_path，则使用相对于项目根目录的路径
        if db_path is None:
            # 获取当前文件所在目录
            current_dir = os.path.dirname(os.path.abspath(__file__))
            # 获取项目根目录（假设是src的上一级目录）
            project_root = os.path.abspath(os.path.join(current_dir, '..', '..'))
            # 设置数据库路径
            self.db_path = os.path.join(project_root, 'db', 'questionnaire.db')
        else:
            self.db_path = db_path
            
        self.dashscope_api_key = dashscope_api_key or os.getenv("DASHSCOPE_API_KEY")
        
        if not self.dashscope_api_key:
            raise ValueError("通义千问API密钥未提供，请设置DASHSCOPE_API_KEY环境变量或在初始化时提供")
        
        # 确保数据库目录存在
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        # 初始化LLM
        self.llm = Tongyi(
            model="qwen-max",
            dashscope_api_key=self.dashscope_api_key,
            temperature=0.7
        )
        
        # 初始化提示模板
        self._init_prompts()
    
    def _init_prompts(self):
        """初始化提示模板"""
        # 用户属性生成提示
        self.user_attrs_prompt = PromptTemplate(
            input_variables=[],
            template="""
            请生成一个用户表的常见属性列表，包括但不限于：用户ID、姓名、性别、年龄、职业、地址、爱好等。
            
            对于每个属性，请提供以下信息：
            1. 属性名称（英文，用作数据库字段名）
            2. 属性描述（中文）
            3. 数据类型（SQLite支持的类型：INTEGER, TEXT, REAL, BLOB, NULL）
            4. 是否为主键
            5. 是否允许为空
            
            请以JSON格式返回结果，格式如下：
            [
                {
                    "name": "属性名称（英文）",
                    "description": "属性描述（中文）",
                    "type": "数据类型",
                    "primary_key": true/false,
                    "nullable": true/false
                },
                ...
            ]
            
            只返回JSON格式的结果，不要有其他解释。
            """
        )
        
        # 用户数据生成提示
        self.user_data_prompt = PromptTemplate(
            input_variables=["attributes", "num_records"],
            template="""
            请根据以下用户表属性，生成{num_records}条真实、多样化的用户样例数据。
            
            用户表属性：
            {attributes}
            
            请确保：
            1. 数据真实合理，符合中国人的特点
            2. 数据多样化，覆盖不同年龄段、职业、地区等
            3. 爱好等字段内容丰富多样
            4. 主键字段唯一，不重复
            
            请以JSON格式返回结果，格式如下：
            [
                {{
                    "属性名1": 值1,
                    "属性名2": 值2,
                    ...
                }},
                ...
            ]
            
            只返回JSON格式的结果，不要有其他解释。
            """
        )
    
    def generate_user_attributes(self) -> List[Dict[str, Any]]:
        """生成用户表属性"""
        # 使用直接调用LLM而不是通过模板格式化
        prompt_text = """
        请生成一个用户表的常见属性列表，包括但不限于：用户ID、姓名、性别、年龄、职业、地址、爱好、电话号码、邮箱等。
        
        对于每个属性，请提供以下信息：
        1. 属性名称（英文，用作数据库字段名）
        2. 属性描述（中文）
        3. 数据类型（SQLite支持的类型：INTEGER, TEXT, REAL, BLOB, NULL）
        4. 是否为主键
        5. 是否允许为空
        
        请以JSON格式返回结果，格式如下：
        [
            {
                "name": "属性名称（英文）",
                "description": "属性描述（中文）",
                "type": "数据类型",
                "primary_key": true/false,
                "nullable": true/false
            },
            ...
        ]
        
        只返回JSON格式的结果，不要有其他解释。
        """
        
        result = self.llm.invoke(prompt_text)
        
        # 解析JSON结果
        try:
            # 查找JSON部分
            json_start = result.find('[')
            json_end = result.rfind(']') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = result[json_start:json_end]
                attributes = json.loads(json_str)
            else:
                raise ValueError("无法在结果中找到JSON格式的属性列表")
                
            return attributes
        except Exception as e:
            print(f"解析用户属性JSON时出错: {str(e)}")
            print(f"原始结果: {result}")
            # 返回一个基本结构，现在包含电话号码和邮箱
            return [
                {"name": "id", "description": "用户ID", "type": "INTEGER", "primary_key": True, "nullable": False},
                {"name": "name", "description": "姓名", "type": "TEXT", "primary_key": False, "nullable": False},
                {"name": "age", "description": "年龄", "type": "INTEGER", "primary_key": False, "nullable": True},
                {"name": "gender", "description": "性别", "type": "TEXT", "primary_key": False, "nullable": True},
                {"name": "occupation", "description": "职业", "type": "TEXT", "primary_key": False, "nullable": True},
                {"name": "address", "description": "地址", "type": "TEXT", "primary_key": False, "nullable": True},
                {"name": "phone", "description": "电话号码", "type": "TEXT", "primary_key": False, "nullable": True},
                {"name": "email", "description": "电子邮箱", "type": "TEXT", "primary_key": False, "nullable": True},
                {"name": "hobbies", "description": "爱好", "type": "TEXT", "primary_key": False, "nullable": True}
            ]
    
    def generate_user_data(self, attributes: List[Dict[str, Any]], num_records: int = 15) -> List[Dict[str, Any]]:
        """生成用户样例数据"""
        # 格式化属性列表用于提示
        attrs_str = "\n".join([
            f"- {attr['name']}({attr['type']}): {attr['description']}" + 
            (", 主键" if attr['primary_key'] else "") + 
            (", 可为空" if attr['nullable'] else ", 不可为空")
            for attr in attributes
        ])
        
        # 构建完整的提示文本
        prompt_text = f"""
        请根据以下用户表属性，生成{num_records}条真实、多样化的用户样例数据。
        
        用户表属性：
        {attrs_str}
        
        请确保：
        1. 数据真实合理，符合中国人的特点
        2. 数据多样化，覆盖不同年龄段、职业、地区等
        3. 爱好等字段内容丰富多样
        4. 主键字段唯一，不重复
        
        请以JSON格式返回结果，格式如下：
        [
            {{
                "属性名1": 值1,
                "属性名2": 值2,
                ...
            }},
            ...
        ]
        
        只返回JSON格式的结果，不要有其他解释。
        """
        
        # 直接调用LLM
        result = self.llm.invoke(prompt_text)
        
        # 解析JSON结果
        try:
            # 查找JSON部分
            json_start = result.find('[')
            json_end = result.rfind(']') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = result[json_start:json_end]
                user_data = json.loads(json_str)
            else:
                raise ValueError("无法在结果中找到JSON格式的用户数据")
                
            return user_data
        except Exception as e:
            print(f"解析用户数据JSON时出错: {str(e)}")
            print(f"原始结果: {result}")
            # 返回一个空列表
            return []
    
    def create_database(self, attributes: List[Dict[str, Any]]):
        """创建SQLite数据库和表"""
        # 构建CREATE TABLE语句
        columns = []
        for attr in attributes:
            column_def = f"{attr['name']} {attr['type']}"
            
            if attr['primary_key']:
                column_def += " PRIMARY KEY"
                
            if not attr['nullable']:
                column_def += " NOT NULL"
                
            columns.append(column_def)
        
        create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS users (
            {', '.join(columns)}
        );
        """
        
        # 连接数据库并创建表
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("DROP TABLE IF EXISTS users")
            cursor.execute(create_table_sql)
            conn.commit()
            print(f"成功创建users表")
        except Exception as e:
            print(f"创建表时出错: {str(e)}")
        finally:
            conn.close()
    
    def insert_user_data(self, user_data: List[Dict[str, Any]]):
        """将用户数据插入数据库"""
        if not user_data:
            print("没有用户数据可插入")
            return
        
        # 连接数据库
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # 获取第一条记录的所有键作为列名
            columns = list(user_data[0].keys())
            
            # 构建INSERT语句
            placeholders = ', '.join(['?' for _ in columns])
            insert_sql = f"INSERT INTO users ({', '.join(columns)}) VALUES ({placeholders})"
            
            # 准备数据
            values = []
            for record in user_data:
                row = [record.get(column) for column in columns]
                values.append(row)
            
            # 执行插入
            cursor.executemany(insert_sql, values)
            conn.commit()
            
            print(f"成功插入 {len(user_data)} 条用户数据")
        except Exception as e:
            print(f"插入数据时出错: {str(e)}")
        finally:
            conn.close()
    
    def run(self, num_records: int = 15):
        """运行完整的数据库生成流程"""
        print("开始生成数据库和样例数据...")
        
        # 1. 生成用户表属性
        print("正在生成用户表属性...")
        attributes = self.generate_user_attributes()
        print(f"生成了 {len(attributes)} 个用户表属性")
        
        # 2. 创建数据库和表
        print("正在创建数据库和表...")
        self.create_database(attributes)
        
        # 3. 生成用户样例数据
        print(f"正在生成 {num_records} 条用户样例数据...")
        user_data = self.generate_user_data(attributes, num_records)
        print(f"生成了 {len(user_data)} 条用户样例数据")
        
        # 4. 插入用户数据
        print("正在将用户数据插入数据库...")
        self.insert_user_data(user_data)
        
        print(f"数据库生成完成，路径: {self.db_path}")
        return self.db_path

if __name__ == "__main__":
    generator = DatabaseGenerator()
    generator.run(num_records=15)