import requests
import time
import pandas as pd
import os
import re
import random
import json
import platform
from bs4 import BeautifulSoup
from openai import OpenAI

# 环境变量中的API密钥
api_key = os.getenv('MOONSHOT_API_KEY')
client = OpenAI(api_key=api_key, base_url="https://api.moonshot.cn/v1")
headers = {
    'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'cookie': ''，  # 没有输入cookie也能运行，似乎输入Cookie运行更稳定
}

def trans_date(v_timestamp):
    timeArray = time.localtime(v_timestamp)
    otherStyleTime = time.strftime("%Y-%m-%d %H:%M:%S", timeArray)
    return otherStyleTime

def tran_gender(gender_tag):
    return {1: '男', 0: '女', -1: '未知'}.get(gender_tag, '未知')

def clean_content(v_text):
    dr = re.compile(r'<[^>]+>', re.S)
    text2 = dr.sub('', v_text)
    return text2

def delete_duplicated_file(v_file_path):
    if os.path.exists(v_file_path):
        os.remove(v_file_path)


def process_worksheet_content(excel_file, v_date):
    """
    读取本程序所在文件夹路径下的名为"职场懂行人预备答主群登记表.xlsx"工作簿中指定工作表（v_date）的所有内容，
    并根据条件筛选数据。返回一个 DataFrame，其中包含满足条件的行，且每行只包含第4列（索引为3）的值。

    返回：
        df (pd.DataFrame): 包含满足条件的行，且每行只包含第4列（索引为3）的值。
    """

    # 获取当前程序所在文件夹路径
    current_directory = os.path.dirname(os.path.abspath(__file__))

    # 指定Excel文件完整路径
    excel_file_path = os.path.join(current_directory, excel_file)

    # 使用pandas读取指定工作表的所有内容
    df1 = pd.read_excel(excel_file_path, sheet_name=v_date)

    # 创建一个空 DataFrame 用于存放符合条件的行
    df_result = pd.DataFrame(columns=['Column_4'])

    # 遍历df1的每一行（行号为i_row）
    for i_row, row in df1.iterrows():
        # 第一级判断：检查第i_row行第4列（索引为3）内容是否非空
        if not pd.isnull(row.iloc[3]):
            # 第二级判断：检查第i_row行第8列（索引为7）内容是否为空
            if pd.isnull(row.iloc[7]) or row.iloc[7] == "":
                # 若满足条件，将第i_row行第4列的值添加到结果 DataFrame 中
                df_result.loc[len(df_result)] = [str(row.iloc[3])]

    return df_result

def question_spider(v_question_id):
    url = f'https://www.zhihu.com/question/{v_question_id}'
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')

        # 提取 <title> 标签中的文本，但不包括 " - 知乎"
        title_tag = soup.find('title')
        if title_tag:
            title_text = title_tag.text.replace(" - 知乎", "").strip()
        else:
            title_text = "无问题标题"

        script_tag = soup.find('script', id='js-initialData')
        if script_tag:
            data = json.loads(script_tag.string)
            detail_value = data.get('initialState', {}).get('entities', {}).get('questions', {}).get(v_question_id, {}).get('detail', '')
            detail_text = BeautifulSoup(detail_value, 'html.parser').get_text()
        else:
            detail_text = "无问题详述"

        # 组合 title_text 和 detail_text
        question_text = f"{title_text}\n{detail_text}"
        
        return question_text
    else:
        print("请求网页时发生错误，状态码：", response.status_code)
        return ""

def save_top10answers(V_all_data):
    V_all_data['总互动数'] = V_all_data['点赞数'] + V_all_data['评论数']
    df_top10 = V_all_data.sort_values(by='总互动数', ascending=False).head(10)
    df_top10.to_csv('top_10_answers.csv', index=False, encoding='utf-8')
    return df_top10[['回答内容']]

def answer_spider(v_result_file: str, v_question_id: str, max_retries=5):
    """获取答案数据，并保存到CSV文件。

    Args:
        v_result_file (str): CSV文件名，存储爬取结果。
        v_question_id (str): 知乎问题ID。

    Returns:
        dataframe: 包含所有答案的DataFrame。
    """
    # 初始化累积所有页面数据的DataFrame
    all_answers = pd.DataFrame()

    # 请求地址
    url = 'https://www.zhihu.com/api/v4/questions/{}/feeds?include=data%5B%2A%5D.is_normal%2Cadmin_closed_comment%2Creward_info%2Cis_collapsed%2Cannotation_action%2Cannotation_detail%2Ccollapse_reason%2Cis_sticky%2Ccollapsed_by%2Csuggest_edit%2Ccomment_count%2Ccan_comment%2Ccontent%2Ceditable_content%2Cattachment%2Cvoteup_count%2Creshipment_settings%2Ccomment_permission%2Ccreated_time%2Cupdated_time%2Creview_info%2Crelevant_info%2Cquestion%2Cexcerpt%2Cis_labeled%2Cpaid_info%2Cpaid_info_content%2Creaction_instruction%2Crelationship.is_authorized%2Cis_author%2Cvoting%2Cis_thanked%2Cis_nothelp%3Bdata%5B%2A%5D.mark_infos%5B%2A%5D.url%3Bdata%5B%2A%5D.author.follower_count%2Cvip_info%2Cbadge%5B%2A%5D.topics%3Bdata%5B%2A%5D.settings.table_of_content.enabled&limit=5&offset=0&order=default&platform=desktop'.format(v_question_id)

    page_count = 0  # 页面计数器

    while True:
        try:
            # 发送请求
            r = requests.get(url, headers=headers)
            r.raise_for_status()  # 主动抛出异常，如果状态码不是200
            j_data = r.json()
            answer_list = j_data['data']

            # 数据处理
            # 提取回答数据，构造DataFrame
            df = extract_data(answer_list, v_question_id)
            all_answers = pd.concat([all_answers, df], ignore_index=True)

            page_count += 1
            if page_count % 50 == 0:
                print(f"已爬取{page_count}页，暂停10秒...")
                time.sleep(10)
            else:
                print('开始爬取第{}页，本页回答数量是：{}'.format(page_count, len(answer_list)))
                time.sleep(1)  # 每爬取一页休息1秒

            # 判断是否退出
            if j_data['paging']['is_end']:  # 如果是最后一页
                print('所有页面爬取完毕!')
                break
            else:
                url = j_data['paging']['next']  # 下一页的请求地址

        except requests.exceptions.RequestException as e:
            print(f"请求错误: {e}, 正在尝试重新连接...")
            retry_count = 0
            while retry_count < max_retries:
                time.sleep(10 * (2 ** retry_count))  # 指数退避策略
                try:
                    response = requests.get(url, headers=headers)
                    response.raise_for_status()
                    # 如果重新请求成功，则跳出重试循环
                    break
                except:
                    retry_count += 1
                    print(f"重试次数 {retry_count}...")
            if retry_count == max_retries:
                print("达到最大重试次数，终止请求。")
                break

    return all_answers

def extract_data(answer_list, v_question_id):
    """提取回答数据并构建DataFrame."""
    author_name_list = []
    author_gender_list = []
    follower_count_list = []
    author_url_list = []
    headline_list = []
    answer_id_list = []
    answer_time_list = []
    answer_content_list = []
    comment_count_list = []
    voteup_count_list = []
    thanks_count_list = []

    for answer in answer_list:
        # 提取和转换各种数据
        author_name_list.append(answer['target']['author']['name'])
        author_gender_list.append(tran_gender(answer['target']['author']['gender']))
        follower_count_list.append(answer['target']['author'].get('follower_count', ''))
        author_url_list.append('https://www.zhihu.com/people/' + answer['target']['author']['url_token'])
        headline_list.append(answer['target']['author']['headline'])
        answer_id_list.append(answer['target']['id'])
        answer_time_list.append(trans_date(answer['target']['updated_time']))
        answer_content_list.append(clean_content(answer['target'].get('content', '')))
        comment_count_list.append(answer['target']['comment_count'])
        voteup_count_list.append(answer['target']['voteup_count'])
        thanks_count_list.append(answer['target'].get('thanks_count', 0))

    return pd.DataFrame({
        '问题id': v_question_id,
        '答主昵称': author_name_list,
        '答主性别': author_gender_list,
        '答主粉丝数': follower_count_list,
        '答主主页': author_url_list,
        '答主签名': headline_list,
        '回答id': answer_id_list,
        '回答时间': answer_time_list,
        '评论数': comment_count_list,
        '点赞数': voteup_count_list,
        '喜欢数': thanks_count_list,
        '回答内容': answer_content_list,
    })

def get_completion(system_content, user_content):
    # messages = [{"role": "system", "content": system_content}, {"role": "user", "content": user_content}]  # 我怀疑role用System的效果不如assistant效果好
    messages = [{"role": "assistant", "content": system_content}, {"role": "user", "content": user_content}]
    try:
        completion = client.chat.completions.create(
            model="moonshot-v1-32k", 
            messages=messages, 
            temperature=0.3
        )
        return completion.choices[0].message.content
    except Exception as e:
        print(f"An error occurred: {e}")
        return None


def build_system_content(answers):
    """
    构建提示信息的函数。
    
    参数:
    answers - 一个包含多个答案的列表，每个答案都是一个字符串。
    
    返回值:
    返回一个字符串，该字符串包含一个指导说明和格式化后的答案示例。
    """
    instruction = """你作为一位资深的职业经理，你将与问题的提出问题的职场年轻人以及更多读到你回复的职场人进行一场思想的交流，请分享你的经验和智慧，并确保：
- 你的回答既权威又接地气，能够以平实的语言传达深刻的见解。
- 保持语言风格娓娓道来，深入浅出，使内容易于理解，同时不失专业性。
- 回答中蕴含寓意，含蓄委婉，能够启发思考，同时点明问题的关键所在。
- 适当运用风趣幽默，让交流更加生动，增强说服力。
- 避免抄袭，确保内容的原创性，引用资料时请注明出处。
- 建议进行网络搜索，阅读相关文献以丰富回答内容，但不要过度堆砌资料，保持回答的流畅性和可读性。
"""

    output_format = """你的回答应该是一篇流畅的、口语化的文章。文章内容在整体上应该像一次与提问者的对话。文字表达自然流畅，避免过于刻板的格式，让所有读到你回复文章的人感觉就像在听一个有趣的故事或者一个智者的分享。
特别提醒你一定要：
- 避免使用居高临下的语气
- 避免夸夸其谈、夸大其词
- 避免在文章里面出现标题、索引、目录、编号等标示结构和逻辑顺序的内容
- 避免存在任何抄袭的痕迹
- 避免出现任何形式的广告，包括但不限于：
    - 链接到任何网站、博客、公众号、群组等
    - 引用任何第三方的资料、文章、书籍等
    - 引用任何第三方的代码、工具、工具库等
    - 引用任何第三方的模型、模型库、模型框架等
    - 引用任何第三方的算法、算法库、算法框架等
    - 引用任何第三方的模型、模型库、模型框架等
注意：字数控制在2000字以内，使用中文，避免抄袭.
"""

    # 格式化优秀回答示例
    example_answers = "\n".join([f"供你借鉴的优秀回答{i+1}：\n\n{answer}\n\n" for i, answer in enumerate(answers)])
    # 将指导说明、输出格式要求、输入问题和优秀回答示例组合成完整的提示信息
    system_content = f"{instruction}\n{output_format}\n{example_answers}"
    return system_content


def build_user_content(question_txt):
    """
    构建提示信息的函数。
    
    参数:
    answers - 一个包含多个答案的列表，每个答案都是一个字符串。
    
    返回值:
    返回一个字符串，该字符串包含一个指导说明和格式化后的答案示例。
    """
    # 构建输入问题的文本格式
    user_content = f"这里是职场年轻人提出的问题：\n{question_txt}"

    return user_content


def save_to_markdown(prompts, responses, question_id):
    """
    将回答列表保存为Markdown文件，每个回答一个文件。
    
    :param responses: 包含回答内容的列表
    :param question_id: 问题的ID，用于在文件名中标识问题
    """
    # 获取基础文件路径，指向用户家目录下的SyncSpace/Zhihu文件夹
    base_path = os.path.expanduser("~") + "/SyncSpace/Zhihu/"
    # 遍历回答列表，为每个回答创建一个Markdown文件
    for i, response in enumerate(responses):
        # 构建Markdown文件的完整路径
        md_filepath = f"{base_path}问题{question_id}_回答0{i+1}.md"
        # 删除可能存在的重复文件，避免重复写入
        delete_duplicated_file(md_filepath)
        # 打开Markdown文件，写入内容
        with open(md_filepath, 'w', encoding='utf-8') as file:
            # 写入Markdown文件内容，包含答案的链接、问题文本和回答文本
            file.write(f"{prompts[i][0]}\n{prompts[i][1]}\n#! https://www.zhihu.com/question/{question_id}\n{response}")

if __name__ == '__main__':

    excel_file = "职场懂行人预备答主群登记表.xlsx"

    df_questionId = process_worksheet_content(excel_file, '0421')

    # 遍历问题ID列表，依次处理每个问题
    for index, row in df_questionId.iterrows():

        question_id = row['Column_4']

        print("################################################################################################")
        print(f'正在处理问题{question_id}...')

        # 生成CSV文件名，包含问题ID作为标识
        csv_file = f'知乎回答_{question_id}.csv'

        # 删除可能存在的重复CSV文件，确保数据唯一性
        delete_duplicated_file(csv_file)

        # 使用爬虫获取指定问题的文字描述
        question_txt = question_spider(question_id)

        # 使用爬虫从CSV文件中抓取所有回答
        all_answers = answer_spider(csv_file, question_id)

        # 保存前10个最佳回答
        top10answers = save_top10answers(all_answers)

        # 新增：分三次调用Kimi API，每次传入四个不同的示例回答
        zhihu_answers = []

        # 定义每次调用API时使用的示例回答索引集
        answer_sets = [
            [0, 1, 2, 3],  # 第一次赋值
            [0, 4, 5, 6],  # 第二次赋值
            [0, 7, 8, 9]   # 第三次赋值
        ]

        # 定义记录三次生成prompt的数组
        prompts = []
        index_prompt = 0

        # 遍历每组示例回答索引集
        for index_set in answer_sets:

            print("**************************************************************************************************")
            print(f"当前索引集：{index_set}")

            # 提取对应的示例回答内容
            answers_for_prompt = [top10answers.iloc[i]['回答内容'] for i in index_set]


            # 利用数组prompts构建提示信息，包含问题描述和示例回答
            prompt_entry = []  # 初始化一个用于存储本次生成prompt的列表
            prompt_entry.append(build_system_content(answers_for_prompt))  # 添加问题描述和示例回答
            prompt_entry.append(build_user_content(question_txt))  # 添加用户内容

            prompts.append(prompt_entry)  # 将本次生成的prompt添加到prompts列表中

            print(f"{prompts[index_prompt][0]}\n{prompts[index_prompt][1]}")  # 打印当前生成的prompt

            # 调用Kimi API，根据提示信息获取AI生成的回答
            response = get_completion(prompts[index_prompt][0], prompts[index_prompt][1])

            print(f"\n{response}")

            index_prompt = index_prompt + 1

            # 将AI生成的回答添加到结果列表中
            zhihu_answers.append(response)

        # 将所有AI生成的回答保存为Markdown文件，文件名包含问题ID
        save_to_markdown(prompts, zhihu_answers, question_id)
