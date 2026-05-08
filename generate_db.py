import argparse
from src.db_utils.data_generator import DatabaseGenerator

if __name__ == "__main__":
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description='生成SQLite数据库和样例用户数据')
    parser.add_argument('--api_key', type=str, help='通义千问API密钥')
    parser.add_argument('--num_records', type=int, default=30, help='生成的样例数据数量')
    args = parser.parse_args()
    
    # 创建数据库生成器
    generator = DatabaseGenerator(dashscope_api_key=args.api_key)
    
    # 运行数据库生成流程，生成样例数据
    db_path = generator.run(num_records=args.num_records)
    
    print(f"\n数据库生成完成！")
    print(f"数据库路径: {db_path}")
    print("您可以使用SQLite工具查看和操作该数据库。")