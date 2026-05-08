import os
import json
import sqlite3
import argparse
from pathlib import Path

def fix_questionnaire_ids(db_path):
    """
    修复数据库中的问卷ID
    
    Args:
        db_path: 数据库文件路径
    """
    # 连接数据库
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("开始修复数据库中的问卷ID...")
    
    # 1. 获取所有问卷信息
    cursor.execute("SELECT questionnaire_id, file_path FROM questionnaires")
    questionnaires = cursor.fetchall()
    
    for old_id, file_path in questionnaires:
        # 从文件路径中提取正确的问卷ID
        correct_id = os.path.basename(file_path).split('.')[0]
        
        if old_id != correct_id:
            print(f"发现问卷ID不匹配: {old_id} -> {correct_id}")
            
            # 更新问卷表中的ID
            cursor.execute(
                "UPDATE questionnaires SET questionnaire_id = ? WHERE questionnaire_id = ?",
                (correct_id, old_id)
            )
            
            # 更新问卷结果表中的ID
            cursor.execute(
                "UPDATE questionnaire_results SET questionnaire_id = ? WHERE questionnaire_id = ?",
                (correct_id, old_id)
            )
            
            print(f"已更新问卷ID: {old_id} -> {correct_id}")
    
    # 2. 修复问卷结果中的JSON数据
    cursor.execute("SELECT id, questionnaire_id, answer_data FROM questionnaire_results")
    results = cursor.fetchall()
    
    for result_id, questionnaire_id, answer_data in results:
        try:
            # 解析JSON数据
            data = json.loads(answer_data)
            
            # 检查并修复JSON中的问卷ID
            if "questionnaire_id" in data and data["questionnaire_id"] != questionnaire_id:
                data["questionnaire_id"] = questionnaire_id
                
                # 更新JSON数据
                updated_data = json.dumps(data, ensure_ascii=False)
                cursor.execute(
                    "UPDATE questionnaire_results SET answer_data = ? WHERE id = ?",
                    (updated_data, result_id)
                )
                
                print(f"已修复结果ID {result_id} 的JSON数据")
        except json.JSONDecodeError:
            print(f"警告: 结果ID {result_id} 的JSON数据无法解析，跳过")
    
    # 提交更改
    conn.commit()
    print("数据库修复完成")
    
    # 关闭连接
    conn.close()

def main():
    parser = argparse.ArgumentParser(description="修复问卷数据库中的ID问题")
    parser.add_argument("--db_path", type=str, help="数据库文件路径")
    
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
    
    # 检查数据库文件是否存在
    if not os.path.exists(db_path):
        print(f"错误: 数据库文件 {db_path} 不存在")
        return
    
    # 修复数据库
    fix_questionnaire_ids(db_path)

if __name__ == "__main__":
    main()