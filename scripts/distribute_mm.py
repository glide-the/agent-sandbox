import pandas as pd
import json
import argparse
import os
import random
import zipfile
from PIL import Image
from openpyxl import Workbook
from openpyxl.drawing.image import Image as ExcelImage
from openpyxl.utils import get_column_letter
from io import BytesIO
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



def save_questions_with_images(df, save_path):
    wb = Workbook()
    ws = wb.active

    headers = list(df.columns)
    img_col_name = "img"
    img_col_index = headers.index(img_col_name) + 1
    img_col_letter = get_column_letter(img_col_index)

    img_width_px = 100
    img_height_px = 100

    # 写入标题行（第1行）
    for col_idx, col_name in enumerate(headers, start=1):
        ws.cell(row=1, column=col_idx, value=col_name)

        # 设置列宽
        if col_name == img_col_name:
            ws.column_dimensions[get_column_letter(col_idx)].width = img_width_px / 7.0 + 2

    # 写入每一行数据（从第2行开始）
    for row_idx, row in enumerate(df.itertuples(index=False), start=2):
        for col_idx, value in enumerate(row, start=1):
            col_name = headers[col_idx - 1]
            if col_name == img_col_name:
                if isinstance(value, Image.Image):
                    img_bytes = BytesIO()
                    value.save(img_bytes, format="PNG")
                    img_bytes.seek(0)
                    img = ExcelImage(img_bytes)
                    img.width = img_width_px
                    img.height = img_height_px

                    ws.row_dimensions[row_idx].height = img_height_px * 0.75
                    cell_position = f"{get_column_letter(col_idx)}{row_idx}"
                    ws.add_image(img, cell_position)
            else:
                ws.cell(row=row_idx, column=col_idx, value=value)

    wb.save(save_path)


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
        save_path = os.path.join(employee_dir, f"questions_{team_name}.xlsx")
        save_questions_with_images(questions_part, save_path)
      
def zip_distribute(output_dir=None):
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
        employee_zip_dir = os.path.join(output_dir, "zips", f"{employee}.zip")

        employee_dir = os.path.join(output_dir, f"{employee}")
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
    parser.add_argument("--each_num", type=int, default=10, help="Number of questions per employee")
    parser.add_argument("--output_dir", type=str, default="output", help="Path to the output directory")
    return parser.parse_args()
    
def safe_open_image(img_path):
    try:
        return Image.open(img_path)
    except Exception as e:
        print(f"无法打开图片 {img_path}，原因：{e}")
        return None
    
def main():
    args = parse_args()
    # 读取文件夹mm_bc下面的文件夹，
    mm_bc_dir = os.path.join("mm_bc")
    
    badcase_all = []
    
    # 读取文件夹mm_bc下面的文件夹，获取文件夹名称，并且组装文件夹下方的submit.jsonl设置到 questions
    for team_dir in os.listdir(mm_bc_dir):
        team_path = os.path.join(mm_bc_dir, team_dir)
        if os.path.isdir(team_path):
            questions = {}
            submit_path = os.path.join(team_path, "submit_mm.jsonl")
            if os.path.exists(submit_path):
                with open(submit_path, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            item = json.loads(line)
                            question = item["question"]
                            if question not in questions:
                                questions[question] = {
                                    "question": question,
                                    "img_path": item['img'],
                                    "answer": item["answer"],
                                    "tag": item.get("tag", ""),
                                    "comment": item.get("comment", ""),
                                }
                        except json.JSONDecodeError:
                            print(f"Error decoding JSON: {line}")

                    
            all_questions = pd.DataFrame(list(questions.values()))
            # 转换图片路径成图片对象
            # 当前执行文件的路径
            current_path = os.path.dirname(os.path.abspath(__file__))
 
            all_questions["img"] = all_questions["img_path"].apply(
                lambda x: safe_open_image(os.path.join(current_path, mm_bc_dir, team_dir, "imgs", x))
            )
            badcase_all.append({"队伍名称": team_dir, "questions": all_questions})   

    print(f"随机抽取了{len(badcase_all)}个队伍")
    
    # badcase_dedup = load_json(args.badcase_dedup_path)
    for team_item in badcase_all:
        team_name = team_item["队伍名称"]
        questions = team_item["questions"]
     
        # questions = dedup_questions(questions, badcase_dedup)
        distribute_questions(team_name, questions, args.each_num, args.output_dir)
    zip_distribute(args.output_dir)



if __name__ == "__main__":
    main()