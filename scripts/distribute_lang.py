import pandas as pd
import json
import argparse
import os
import random
import zipfile

"""
1、字节
2、混元
3、司南
4、superclue
5、superbench
6、智谱
7、魔搭（看对方要不要）
"""
EMPLOYEES= [
    "字节",
    "混元",
    "司南",
    "superclue",
    "superbench",
    "智谱",
    "魔搭"
]
 
    
    
def dedup_questions(questions, questions_already):
    """
    从questions DataFrame中移除在questions_already中已存在的问题
    
    参数:
    questions: 包含问题的DataFrame
    questions_already: 已存在问题的DataFrame
    
    返回:
    DataFrame: 移除重复问题后的DataFrame
    """
    # 获取已存在问题的列表
    existing_questions = set(questions_already["question"])
    
    # 筛选出不在已存在问题列表中的行
    filtered_questions = questions[~questions["question"].isin(existing_questions)]
    
    return filtered_questions

import re
def clean_excel_string(s):
    # 移除 openpyxl 不允许的字符
    if isinstance(s, str):
        # 过滤掉 ASCII 控制字符和 $ 等特殊符号（可根据实际需求调整）
        s = re.sub(r'[\x00-\x1F]', '', s)
        s = s.replace('$', '')  # 或者替换成其他符号
    return s

def distribute_questions(team_name, questions, each_num=10, output_dir=None):
    '''
    最后分发的结构：
    root_dir/
        employee_1/
            question_team_name_1.xlsx
            question_team_name_2.xlsx
            ...
        employee_2/
            question_team_name_1.xlsx
            question_team_name_2.xlsx
            ...
    '''
    os.makedirs(os.path.join(output_dir, "zips"), exist_ok=True)
    for employee in EMPLOYEES:
        # 检查数量是否足够，足够则随机抽样
        if len(questions) < each_num:
            questions_part = questions
        else:
            questions_part = questions.sample(each_num)
        employee_dir = os.path.join(output_dir, f"{employee}")
        os.makedirs(employee_dir, exist_ok=True)
        questions_part = questions_part.applymap(clean_excel_string)  # 添加这一行

        questions_part.to_excel(os.path.join(employee_dir, f"questions_{team_name}.xlsx"), index=False)
        employee_zip_dir = os.path.join(output_dir, "zips", f"{employee}.zip")

        # 使用python的zipfile 替代 os.system(f"zip -r {employee_zip_dir} {employee_dir}")
        with open(employee_zip_dir, "wb") as f:
            with zipfile.ZipFile(f, "w", zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(employee_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        zipf.write(file_path, os.path.relpath(file_path, employee_dir))
        


def save_json(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)  

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def parse_args():
    parser = argparse.ArgumentParser(description="Distribute questions") 
    parser.add_argument("--each_num", type=int, default=20, help="Number of questions per employee")
    parser.add_argument("--output_dir", type=str, default="output", help="Path to the output directory")
    return parser.parse_args()
    
    
    
def main():
    args = parse_args()
    # 读取文件夹lang_bc下面的文件夹，
    lang_bc_dir = os.path.join("lang_bc")
    
    badcase_all = []
    
    # 读取文件夹lang_bc下面的文件夹，获取文件夹名称，并且组装文件夹下方的submit.jsonl设置到 questions
    for team_dir in os.listdir(lang_bc_dir):
        team_path = os.path.join(lang_bc_dir, team_dir)
        if os.path.isdir(team_path):
            questions = {}
            submit_path = os.path.join(team_path, "submit.jsonl")
            if os.path.exists(submit_path):
                with open(submit_path, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            item = json.loads(line)
                            question = item["question"]
                            if question not in questions:
                                questions[question] = {
                                    "question": question,
                                    "answer": item["answer"],
                                    "tag": item.get("tag", ""),
                                    "comment": item.get("comment", ""),
                                }
                        except json.JSONDecodeError:
                            print(f"Error decoding JSON: {line}")

                    
            all_questions = pd.DataFrame(list(questions.values()))
            badcase_all.append({"队伍名称": team_dir, "questions": all_questions})   

    print(f"随机抽取了{len(badcase_all)}个队伍")
    
    # badcase_dedup = load_json(args.badcase_dedup_path)
    for team_item in badcase_all:
        team_name = team_item["队伍名称"]
        questions = team_item["questions"]
     
        # questions = dedup_questions(questions, badcase_dedup)
        distribute_questions(team_name, questions, args.each_num, args.output_dir)



if __name__ == "__main__":
    main()